import pytest
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
