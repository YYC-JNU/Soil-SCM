import pytest
import logging
from src.config_manager import ConfigManager


@pytest.fixture(scope="module")
def cfg():
    return ConfigManager("config/config.yaml")


def test_default_scenario(cfg):
    assert cfg.config.simulation.scenario == "natural"


def test_default_n_years(cfg):
    assert cfg.config.simulation.n_years > 0


def test_default_engine_auto(cfg):
    """T1-S3: 默认引擎应为 auto (官方引擎优先)"""
    assert cfg.config.simulation.engine_mode == "auto"


def test_precip_data_loaded(cfg):
    data = cfg.config.precip_chemistry.data
    assert data, "降水数据未加载"
    assert data["pH"] == 5.75
    assert "ions" in data


def test_soil_type(cfg):
    assert cfg.config.soil_data.soil_type == "red_soil"


def test_invalid_n_years(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("simulation:\n  n_years: -1\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        ConfigManager(str(p))


def test_invalid_scenario(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("simulation:\n  n_years: 10\n  scenario: invalid_scen\n",
                 encoding="utf-8")
    with pytest.raises(AssertionError):
        ConfigManager(str(p))


def test_invalid_engine_mode(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("simulation:\n  n_years: 10\n  engine_mode: invalid\n",
                 encoding="utf-8")
    with pytest.raises(AssertionError):
        ConfigManager(str(p))


def test_invalid_output_format(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("simulation:\n  n_years: 10\noutput:\n  format: parquet\n",
                 encoding="utf-8")
    with pytest.raises(AssertionError):
        ConfigManager(str(p))


# ==================== v0.2.3: soil_data 内联字段 ====================

FULL_SURVEY_YAML = """\
simulation:
  n_years: 2
soil_data:
  survey:
    ph: 5.5
    organic_matter: 25.0
    cec: 14.0
    bulk_density: 1.3
    area: 1.0
    effective_depth: 35.0
    available_p: 20.0
    available_k: 120.0
    texture: 5
    sand_pct: 40.0
    silt_pct: 35.0
    clay_pct: 25.0
  exchangeable_ions:
    exch_ca: 4.0
    exch_mg: 1.0
    exch_k: 0.8
    exch_na: 0.3
    exch_al: 1.5
    exch_h: 0.8
"""


def test_soil_data_default_all_minus_one(cfg):
    """默认 config (全 -1): 正常加载, 字段保持 -1 待回退 CSV"""
    survey = cfg.config.soil_data.survey
    assert survey.ph == -1.0
    assert survey.texture == -1
    assert survey.sand_pct == -1.0
    assert cfg.config.soil_data.exchangeable_ions.exch_al == -1.0


def test_soil_data_survey_full_valid(tmp_path):
    """survey 全有效值: 正常加载, 值从 config 读取"""
    p = tmp_path / "cfg.yaml"
    p.write_text(FULL_SURVEY_YAML, encoding="utf-8")
    cfg = ConfigManager(str(p))
    assert cfg.config.soil_data.survey.ph == 5.5
    assert cfg.config.soil_data.survey.cec == 14.0
    assert cfg.config.soil_data.survey.texture == 5
    assert cfg.config.soil_data.exchangeable_ions.exch_ca == 4.0


def test_soil_data_survey_mixed_raises(tmp_path):
    """survey 混合填写 (部分 -1) → 报错并列出问题字段"""
    p = tmp_path / "cfg.yaml"
    p.write_text("soil_data:\n  survey:\n    ph: 5.5\n    cec: -1\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="请确认后再输入"):
        ConfigManager(str(p))


def test_soil_data_exchangeable_mixed_raises(tmp_path):
    """exchangeable_ions 混合填写 → 报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "soil_data:\n  exchangeable_ions:\n    exch_ca: 3.0\n    exch_mg: -1\n",
        encoding="utf-8")
    with pytest.raises(ValueError, match="请确认后再输入"):
        ConfigManager(str(p))


def test_soil_data_texture_sum_invalid(tmp_path):
    """砂粉黏三者之和 != 100 → 报错"""
    yaml_text = FULL_SURVEY_YAML.replace("clay_pct: 25.0", "clay_pct: 20.0")
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="必须等于 100"):
        ConfigManager(str(p))


def test_soil_data_texture_code_invalid(tmp_path):
    """质地编码不在编码表 → 报错"""
    yaml_text = FULL_SURVEY_YAML.replace("texture: 5", "texture: 99")
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="texture"):
        ConfigManager(str(p))


# ==================== v0.2.3: precipitation_chemistry 内联字段 ====================

FULL_PRECIP_YAML = """\
simulation:
  n_years: 2
precipitation_chemistry:
  input_file: config/precip_chemistry_default.json
  ph: 5.5
  ions:
    Cl: 20.0
    SO4: 12.0
    NO3: 11.0
    F: 2.0
    Ca: 21.0
    NH4: 15.0
    Na: 11.0
    Mg: 5.0
    K: 2.0
    H: 1.0
"""


def test_precip_default_all_minus_one(cfg):
    """默认 config (全 -1): 字段保持 -1, data 回退 JSON"""
    pc = cfg.config.precip_chemistry
    assert pc.ph == -1.0
    assert pc.ions.Cl == -1.0
    assert pc.ions.H == -1.0
    assert pc.data["pH"] == 5.75          # JSON 默认值
    assert pc.data["ions"]["Cl"] == 18.4  # JSON 默认值


def test_precip_full_valid(tmp_path):
    """全有效值: data 从 config 内联构建"""
    p = tmp_path / "cfg.yaml"
    p.write_text(FULL_PRECIP_YAML, encoding="utf-8")
    cfg = ConfigManager(str(p))
    pc = cfg.config.precip_chemistry
    assert pc.ph == 5.5
    assert pc.ions.Ca == 21.0
    assert pc.data["pH"] == 5.5
    assert pc.data["ions"]["Cl"] == 20.0


def test_precip_mixed_raises(tmp_path):
    """ph 填了但离子全 -1 → 混合填写报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "precipitation_chemistry:\n  ph: 5.5\n  ions:\n    Cl: -1\n    H: -1\n",
        encoding="utf-8")
    with pytest.raises(ValueError, match="请确认后再输入"):
        ConfigManager(str(p))


def test_precip_ions_sum_invalid(tmp_path):
    """10 种离子占比之和 != 100 → 报错"""
    yaml_text = FULL_PRECIP_YAML.replace("Cl: 20.0", "Cl: 25.0")
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="必须等于 100"):
        ConfigManager(str(p))


def test_precip_h_nonpositive_raises(tmp_path):
    """H⁺ 占比 = 0 (总和仍=100) → 报错"""
    yaml_text = (FULL_PRECIP_YAML.replace("H: 1.0", "H: 0.0")
                 .replace("Cl: 20.0", "Cl: 21.0"))  # 保持总和=100
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="H"):
        ConfigManager(str(p))


def test_precip_json_missing_raises(tmp_path):
    """全 -1 但 JSON 文件不存在 → FileNotFoundError (Q7)"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "precipitation_chemistry:\n  input_file: no_such_dir/no_file.json\n"
        "  ph: -1\n",
        encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        ConfigManager(str(p))


# ==================== L6 (v0.4.0): layer_overrides / layer_depths ====================

FULL_LAYER_OVERRIDES_YAML = """\
simulation:
  n_years: 2
  n_layers: 4
  layer_depths: [10, 10, 20, 20]
  layer_overrides:
    - ph: 4.5
      organic_matter: 30.0
      cec: 15.0
      bulk_density: 1.1
      exch_ca: 3.5
      exch_mg: 1.0
      exch_k: 0.4
      exch_na: 0.2
      exch_al: 3.0
      exch_h: 1.0
      pCO2: 0.020
      minerals:
        goethite: 0.08
    - {}
    - cec: 10.0
      bulk_density: 1.35
    - bulk_density: 1.5
      pCO2: 0.030
"""


def test_layer_overrides_default_empty(cfg):
    """默认 config: layer_overrides 为空列表, layer_depths 为 None"""
    assert cfg.config.simulation.layer_overrides == []
    assert cfg.config.simulation.layer_depths is None


def test_layer_overrides_full_parse(tmp_path):
    """L6/T1: 密集列表解析 — 7 类覆盖字段正确映射到 dataclass"""
    p = tmp_path / "cfg.yaml"
    p.write_text(FULL_LAYER_OVERRIDES_YAML, encoding="utf-8")
    cfg = ConfigManager(str(p))
    sim = cfg.config.simulation
    assert sim.layer_depths == [10, 10, 20, 20]
    assert len(sim.layer_overrides) == 4

    lo0 = sim.layer_overrides[0]
    assert lo0.ph == 4.5
    assert lo0.organic_matter == 30.0
    assert lo0.cec == 15.0
    assert lo0.bulk_density == 1.1
    assert lo0.exch_al == 3.0
    assert lo0.pCO2 == 0.020
    assert lo0.minerals == {"goethite": 0.08}

    # 空 dict 层: 全字段 None
    lo1 = sim.layer_overrides[1]
    assert lo1.ph is None
    assert lo1.cec is None
    assert lo1.minerals == {}

    lo2 = sim.layer_overrides[2]
    assert lo2.cec == 10.0
    assert lo2.bulk_density == 1.35
    assert lo2.ph is None


def test_layer_overrides_length_mismatch_raises(tmp_path):
    """L6/T1: 密集列表长度 != n_layers → 报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  n_layers: 4\n  layer_overrides:\n"
        "    - cec: 15.0\n    - {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="layer_overrides"):
        ConfigManager(str(p))


def test_layer_depths_length_mismatch_raises(tmp_path):
    """L6/T1: layer_depths 长度 != n_layers → 报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  n_layers: 4\n  layer_depths: [10, 10]\n",
        encoding="utf-8")
    with pytest.raises(ValueError, match="layer_depths"):
        ConfigManager(str(p))


def test_layer_overrides_invalid_ph_raises(tmp_path):
    """L6/T1: 覆盖字段值域非法 (ph=12 越界) → 报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  n_layers: 2\n  layer_overrides:\n"
        "    - ph: 12.0\n    - {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ph"):
        ConfigManager(str(p))


def test_layer_overrides_single_layer_ignored(tmp_path, caplog):
    """L6/T1: n_layers=1 时 overrides 不报错, 警告被忽略"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  n_layers: 1\n  layer_overrides:\n"
        "    - cec: 15.0\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        cfg = ConfigManager(str(p))
    assert cfg.config.simulation.layer_overrides[0].cec == 15.0
    assert any("忽略" in r.message for r in caplog.records)


def test_layer_overrides_minerals_sum_warns(tmp_path, caplog):
    """L6/T1: 矿物质量分数总和 != 1 → 警告不报错 (不归一化)"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  n_layers: 2\n  layer_overrides:\n"
        "    - minerals:\n        goethite: 0.08\n    - {}\n",
        encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        cfg = ConfigManager(str(p))
    assert cfg.config.simulation.layer_overrides[0].minerals == {"goethite": 0.08}
    assert any("总和" in r.message for r in caplog.records)


# ==================== v0.4.0+: 显式化参数 + 硝化速率 ====================

def test_simulation_explicit_extra_fields(tmp_path):
    """config.yaml 显式列出预平衡/层参数/硝化速率 → 正确解析"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  n_layers: 2\n"
        "  enable_pre_equilibration: true\n  pre_equilibration_max_steps: 60\n"
        "  layer_depths: null\n  layer_overrides: []\n"
        "  nitrification_k1: 0.8\n  nitrification_k2: 0.3\n",
        encoding="utf-8")
    sim = ConfigManager(str(p)).config.simulation
    assert sim.enable_pre_equilibration is True
    assert sim.pre_equilibration_max_steps == 60
    assert sim.layer_depths is None          # null → None (等分兜底)
    assert sim.layer_overrides == []         # [] → 无覆盖
    assert sim.nitrification_k1 == 0.8
    assert sim.nitrification_k2 == 0.3


def test_nitrification_rates_default(cfg):
    """默认 config: 硝化速率 k1=1.0/k2=0.4 (constants 默认值)"""
    assert cfg.config.simulation.nitrification_k1 == 1.0
    assert cfg.config.simulation.nitrification_k2 == 0.4


def test_nitrification_rates_parse(tmp_path):
    """YAML 覆盖硝化速率 → 解析生效"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  nitrification_k1: 0.8\n"
        "  nitrification_k2: 0.2\n", encoding="utf-8")
    sim = ConfigManager(str(p)).config.simulation
    assert sim.nitrification_k1 == 0.8
    assert sim.nitrification_k2 == 0.2


def test_nitrification_rates_invalid(tmp_path):
    """硝化速率值域校验: k>1 或 k<0 → 报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n  nitrification_k2: 1.5\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="nitrification"):
        ConfigManager(str(p))
    p2 = tmp_path / "cfg.yaml"
    p2.write_text("simulation:\n  n_years: 2\n  nitrification_k1: -0.1\n",
                  encoding="utf-8")
    with pytest.raises(ValueError, match="nitrification"):
        ConfigManager(str(p2))


# ==================== v0.5.0: 水文配置扩展 (T1) ====================

def test_hydrology_fields_parse(tmp_path):
    """layer_overrides 含水文字段 (v0.5.3: f0/fc 已移除) + hydrology_seed 解析"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  n_layers: 4\n  hydrology_seed: 123\n"
        "  layer_overrides:\n"
        "    - clay_pct: 25\n      porosity: 0.55\n      ksat: 76.8\n"
        "    - {}\n    - {}\n    - {}\n", encoding="utf-8")
    sim = ConfigManager(str(p)).config.simulation
    assert sim.hydrology_seed == 123
    lo = sim.layer_overrides[0]
    assert lo.clay_pct == 25
    assert lo.porosity == 0.55
    assert lo.ksat == 76.8
    # 未覆盖水文字段保持 None
    assert sim.layer_overrides[1].ksat is None


def test_hydrology_seed_default(cfg):
    """默认 hydrology_seed = 42 (可复现随机降雨)"""
    assert cfg.config.simulation.hydrology_seed == 42


def test_hydrology_porosity_invalid_raises(tmp_path):
    """孔隙度越界 (φ=1.5) → 报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  n_layers: 2\n  layer_overrides:\n"
        "    - porosity: 1.5\n    - {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="porosity"):
        ConfigManager(str(p))


def test_hydrology_ksat_nonpositive_raises(tmp_path):
    """Ksat ≤ 0 → 报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  n_layers: 2\n  layer_overrides:\n"
        "    - ksat: 0.0\n    - {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="ksat"):
        ConfigManager(str(p))

def test_hydrology_ksat_surface_parse_and_validate(tmp_path):
    """v0.5.2/T2: layer_overrides 解析 ksat_surface; ≤0 报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation: {n_years: 2, n_layers: 4, "
        "layer_overrides: [{ksat: 12.0, ksat_surface: 7.2}, {}, {}, {}]}",
        encoding="utf-8")
    sim = ConfigManager(str(p)).config.simulation
    assert sim.layer_overrides[0].ksat == 12.0
    assert sim.layer_overrides[0].ksat_surface == 7.2
    assert sim.layer_overrides[1].ksat_surface is None
    p2 = tmp_path / "cfg2.yaml"
    p2.write_text(
        "simulation: {n_years: 2, n_layers: 2, "
        "layer_overrides: [{ksat_surface: 0.0}, {}]}",
        encoding="utf-8")
    with pytest.raises(ValueError, match="ksat_surface"):
        ConfigManager(str(p2))


def test_bypass_fraction_default_and_parse(tmp_path):
    """v0.5.2/T3: bypass_fraction 默认 0.2, 解析覆盖, 越界报错"""
    cfg = ConfigManager("config/config.yaml")
    assert cfg.config.simulation.bypass_fraction == 0.2
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation: {n_years: 2, bypass_fraction: 0.35}",
                 encoding="utf-8")
    sim = ConfigManager(str(p)).config.simulation
    assert sim.bypass_fraction == 0.35
    p2 = tmp_path / "cfg2.yaml"
    p2.write_text("simulation: {n_years: 2, bypass_fraction: 1.5}",
                  encoding="utf-8")
    with pytest.raises(ValueError, match="bypass"):
        ConfigManager(str(p2))



def test_hydrology_f0_lt_fc_raises(tmp_path):
    """初渗率 f0 < 稳渗率 fc → 报错 (物理不合理)"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  n_layers: 2\n  layer_overrides:\n"
        "    - infiltration_initial: 0.1\n      infiltration_steady: 0.4\n"
        "    - {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="infiltration"):
        ConfigManager(str(p))


# ==================== v0.5.1 → v0.5.2: 表层入渗系数废弃 ====================

def test_surface_infiltration_coeff_removed_raises(tmp_path):
    """v0.5.2/T5: surface_infiltration_coeff 残留配置 → 显式报错 (breaking change)"""
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation: {n_years: 2, surface_infiltration_coeff: 0.75}",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="surface_infiltration_coeff"):
        ConfigManager(str(p))


# ==================== v0.5.3: 初始水势 + VGM 显式参数 ====================

def test_initial_psi_cm_default(cfg):
    """默认 config: initial_psi_cm=-100 (田间持水量, VGM 正算 θ_init)"""
    assert cfg.config.simulation.initial_psi_cm == -100.0


def test_initial_psi_cm_parse(tmp_path):
    """YAML 覆盖 initial_psi_cm → 解析生效"""
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n  initial_psi_cm: -330.0\n",
                 encoding="utf-8")
    assert ConfigManager(str(p)).config.simulation.initial_psi_cm == -330.0


def test_initial_psi_cm_invalid_raises(tmp_path):
    """v0.5.3: initial_psi_cm ≥ 0 → 显式报错 (必须为负吸力水头)"""
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n  initial_psi_cm: 100.0\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="initial_psi_cm"):
        ConfigManager(str(p))


def test_layer_override_vgm_fields_parse(tmp_path):
    """v0.5.3/T1: layer_overrides 显式 vgm_theta_r/vgm_alpha/vgm_n → 解析映射"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  n_layers: 2\n  layer_overrides:\n"
        "    - vgm_theta_r: 0.10\n      vgm_alpha: 0.02\n      vgm_n: 1.40\n"
        "    - {}\n", encoding="utf-8")
    lo0 = ConfigManager(str(p)).config.simulation.layer_overrides[0]
    assert lo0.vgm_theta_r == 0.10
    assert lo0.vgm_alpha == 0.02
    assert lo0.vgm_n == 1.40
    lo1 = ConfigManager(str(p)).config.simulation.layer_overrides[1]
    assert lo1.vgm_theta_r is None
    assert lo1.vgm_n is None


def test_layer_override_vgm_invalid_raises(tmp_path):
    """v0.5.3: vgm_n≤1 / vgm_alpha≤0 → 显式报错 (值域校验)"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  n_layers: 2\n  layer_overrides:\n"
        "    - vgm_n: 1.0\n    - {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="vgm_n"):
        ConfigManager(str(p))
    p2 = tmp_path / "cfg2.yaml"
    p2.write_text(
        "simulation:\n  n_years: 2\n  n_layers: 2\n  layer_overrides:\n"
        "    - vgm_alpha: 0.0\n    - {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="vgm_alpha"):
        ConfigManager(str(p2))


# ==================== v0.5.3: PET 通道配置 (D5) ====================

def test_climate_pet_defaults(cfg):
    """默认 config: latitude=23.1, pet_method=oudin, 修正系数恒等, 无气候态"""
    clim = cfg.config.climate
    assert clim.latitude == 23.1
    assert clim.pet_method == "oudin"
    assert clim.pet_monthly_climate is None
    assert clim.pet_correction_factor == [1.0] * 12


def test_climate_pet_parse(tmp_path):
    """YAML 覆盖 PET 通道字段 → 解析生效"""
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "climate:\n  latitude: 28.2\n  pet_method: fixed\n"
        "  pet_monthly_climate: [30, 35, 50, 70, 90, 100, 115, 110, 90, 65, 45, 30]\n"
        "  pet_correction_factor: [0.95, 0.95, 1, 1, 1, 0.9, 0.85, 0.85, 0.9, 1, 1.05, 1.05]\n",
        encoding="utf-8")
    clim = ConfigManager(str(p)).config.climate
    assert clim.latitude == 28.2
    assert clim.pet_method == "fixed"
    assert len(clim.pet_monthly_climate) == 12
    assert clim.pet_correction_factor[5] == 0.9


def test_climate_pet_hargreaves_valid_v060(tmp_path):
    """v0.6.0 (Q9): pet_method=hargreaves 现已有效 (日较差 config 可配)"""
    p = tmp_path / "cfg.yaml"
    p.write_text("climate:\n  pet_method: hargreaves\n"
                 "  diurnal_range_deg: 9.5\n", encoding="utf-8")
    clim = ConfigManager(str(p)).config.climate
    assert clim.pet_method == "hargreaves"
    assert clim.diurnal_range_deg == 9.5


def test_climate_pet_hargreaves_enhanced_reserved_raises(tmp_path):
    """v0.6.0: pet_method=hargreaves_enhanced → 显式报错 (v0.7.0 预留)"""
    p = tmp_path / "cfg.yaml"
    p.write_text("climate:\n  pet_method: hargreaves_enhanced\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="hargreaves_enhanced"):
        ConfigManager(str(p))


def test_climate_diurnal_range_invalid_raises(tmp_path):
    """v0.6.0 (Q8): diurnal_range_deg <= 0 → 报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text("climate:\n  diurnal_range_deg: -2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="diurnal_range_deg"):
        ConfigManager(str(p))


def test_climate_pet_invalid_method_raises(tmp_path):
    """pet_method 非法值 → 报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text("climate:\n  pet_method: unknown\n", encoding="utf-8")
    with pytest.raises(ValueError, match="pet_method"):
        ConfigManager(str(p))


def test_climate_pet_fixed_requires_climate(tmp_path):
    """pet_method=fixed 但未提供 pet_monthly_climate → 报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text("climate:\n  pet_method: fixed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="pet_monthly_climate"):
        ConfigManager(str(p))


def test_climate_pet_climate_length_raises(tmp_path):
    """pet_monthly_climate 长度 ≠ 12 → 报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text("climate:\n  pet_monthly_climate: [1, 2, 3]\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="pet_monthly_climate"):
        ConfigManager(str(p))


def test_climate_latitude_invalid_raises(tmp_path):
    """latitude 越界 → 报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text("climate:\n  latitude: 90.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="latitude"):
        ConfigManager(str(p))



# ==================== v0.6.1: VIC 基流 + 侧向排水 config (S5, spec 62 Q10) ====================

def test_baseflow_default_none(cfg):
    """v0.6.1 (Q10): 默认无 baseflow/lateral 节点 → 禁用 (None)"""
    assert cfg.config.simulation.baseflow is None
    assert cfg.config.simulation.lateral is None


def test_baseflow_parse(tmp_path):
    """v0.6.1 (Q10): simulation.baseflow 节点解析"""
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n  baseflow:\n"
                 "    D_max: 120.0\n    D_s: 0.15\n    n_base: 2.0\n"
                 "    theta_c: auto\n", encoding="utf-8")
    bf = ConfigManager(str(p)).config.simulation.baseflow
    assert bf is not None
    assert bf.D_max == 120.0
    assert bf.D_s == 0.15
    assert bf.n_base == 2.0
    assert bf.theta_c == "auto"


def test_baseflow_invalid_raises(tmp_path):
    """v0.6.1 (Q10): baseflow 值域校验 (D_max≤0 / D_s 越界 / n_base≤1 / theta_c≠auto)"""
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n  baseflow:\n    D_max: -5.0\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="D_max"):
        ConfigManager(str(p))
    p2 = tmp_path / "cfg2.yaml"
    p2.write_text("simulation:\n  n_years: 2\n  baseflow:\n    D_s: 1.5\n",
                  encoding="utf-8")
    with pytest.raises(ValueError, match="D_s"):
        ConfigManager(str(p2))
    p3 = tmp_path / "cfg3.yaml"
    p3.write_text("simulation:\n  n_years: 2\n  baseflow:\n    theta_c: manual\n",
                  encoding="utf-8")
    with pytest.raises(ValueError, match="theta_c"):
        ConfigManager(str(p3))


def test_lateral_parse_and_validate(tmp_path):
    """v0.6.1 (Q10): simulation.lateral 节点解析 + k_lat 长度校验"""
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n  n_layers: 4\n  lateral:\n"
                 "    f_slope: 0.10\n    k_lat: [0.04, 0.025, 0.015, 0.008]\n",
                 encoding="utf-8")
    lat = ConfigManager(str(p)).config.simulation.lateral
    assert lat is not None
    assert lat.f_slope == 0.10
    assert lat.k_lat == [0.04, 0.025, 0.015, 0.008]
    # k_lat 长度 ≠ n_layers → 报错
    p2 = tmp_path / "cfg2.yaml"
    p2.write_text("simulation:\n  n_years: 2\n  n_layers: 4\n  lateral:\n"
                  "    k_lat: [0.04, 0.025]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="k_lat"):
        ConfigManager(str(p2))
    # f_slope 越界 → 报错
    p3 = tmp_path / "cfg3.yaml"
    p3.write_text("simulation:\n  n_years: 2\n  lateral:\n    f_slope: 1.5\n",
                  encoding="utf-8")
    with pytest.raises(ValueError, match="f_slope"):
        ConfigManager(str(p3))


# ==================== v0.7.0 (spec 69, 工单70): companion 配置 ====================

def test_companion_default_enabled(cfg):
    """v0.7.0 (工单70): 默认 companion 启用 (D3 为 v0.7.0 主线, enable:false 才回退)"""
    comp = cfg.config.simulation.companion
    assert comp is not None
    assert comp.enable is True
    assert comp.bypass_no3_carry is True


def test_companion_parse(tmp_path):
    """v0.7.0 (工单70): simulation.companion 节点解析 (bypass 携带可关)"""
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n  companion:\n"
                 "    enable: true\n    bypass_no3_carry: false\n",
                 encoding="utf-8")
    comp = ConfigManager(str(p)).config.simulation.companion
    assert comp is not None
    assert comp.enable is True
    assert comp.bypass_no3_carry is False


def test_companion_disable_rollback(tmp_path):
    """v0.7.0 (工单70): enable: false → 显式关闭 (完全回退 v0.6.1)"""
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n  companion:\n    enable: false\n",
                 encoding="utf-8")
    comp = ConfigManager(str(p)).config.simulation.companion
    assert comp.enable is False


def test_companion_invalid_type_raises(tmp_path):
    """v0.7.0 (工单70): 非布尔开关 → 报错"""
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n  companion:\n"
                 "    enable: \"yes\"\n", encoding="utf-8")
    with pytest.raises(ValueError, match="enable"):
        ConfigManager(str(p))


def test_companion_nh4_exchange_default_and_parse(tmp_path):
    """v0.7.0 (工单72): nh4_exchange 默认 true (NH4+ 等效置换为 v0.7.0 主线)"""
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n", encoding="utf-8")
    comp = ConfigManager(str(p)).config.simulation.companion
    assert comp.nh4_exchange is True
    # 可显式关闭 (回退: 仅 D3 无 NH4+ 置换)
    p2 = tmp_path / "cfg2.yaml"
    p2.write_text("simulation:\n  n_years: 2\n  companion:\n"
                  "    nh4_exchange: false\n", encoding="utf-8")
    comp2 = ConfigManager(str(p2)).config.simulation.companion
    assert comp2.nh4_exchange is False
    # 非布尔 → 报错
    p3 = tmp_path / "cfg3.yaml"
    p3.write_text("simulation:\n  n_years: 2\n  companion:\n"
                  "    nh4_exchange: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="nh4_exchange"):
        ConfigManager(str(p3))


# ==================== v0.7.0 (spec 69, 工单73): weathering 配置 ====================

def test_weathering_default_disabled(cfg):
    """v0.7.0 (工单73): 默认 weathering 不启用 (D2 为可回退增强)"""
    wth = cfg.config.simulation.weathering
    assert wth is not None
    assert wth.enable is False
    assert wth.rate_molc_ha_yr == 500.0


def test_weathering_parse(tmp_path):
    """v0.7.0 (工单73): simulation.weathering 节点解析"""
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n  weathering:\n"
                 "    enable: true\n    rate_molc_ha_yr: 800.0\n"
                 "    ca_frac: 0.6\n    mg_frac: 0.3\n    k_frac: 0.1\n"
                 "    activation_energy_kJ: 50.0\n"
                 "    degrade_minerals: [gibbsite, kaolinite]\n",
                 encoding="utf-8")
    wth = ConfigManager(str(p)).config.simulation.weathering
    assert wth.enable is True
    assert wth.rate_molc_ha_yr == 800.0
    assert wth.ca_frac == 0.6 and wth.mg_frac == 0.3 and wth.k_frac == 0.1
    assert wth.activation_energy_kJ == 50.0
    assert wth.degrade_minerals == ['gibbsite', 'kaolinite']


def test_weathering_invalid_raises(tmp_path):
    """v0.7.0 (工单73): weathering 值域校验 (rate≤0 / 占比和≠1 / 活化能≤0)"""
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n  weathering:\n"
                 "    enable: true\n    rate_molc_ha_yr: 0.0\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="rate"):
        ConfigManager(str(p))
    p2 = tmp_path / "cfg2.yaml"
    p2.write_text("simulation:\n  n_years: 2\n  weathering:\n"
                  "    enable: true\n    ca_frac: 0.7\n    mg_frac: 0.3\n"
                  "    k_frac: 0.2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frac"):
        ConfigManager(str(p2))
    p3 = tmp_path / "cfg3.yaml"
    p3.write_text("simulation:\n  n_years: 2\n  weathering:\n"
                  "    enable: true\n    activation_energy_kJ: -1.0\n",
                  encoding="utf-8")
    with pytest.raises(ValueError, match="activation"):
        ConfigManager(str(p3))
