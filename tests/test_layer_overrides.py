"""
测试 L6 逐层参数覆盖 (v0.4.0):
  T3: 引擎逐层应用 — 初始态差异化 (build_initial_state) + 月度 pCO₂ 按层注入
  T4: main.py 多层编排集成 (逐层 profile/预平衡/layer_depths 输出)
"""

import pytest
from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction
from src.input_reader import InputReader
from src.config_manager import LayerOverrideConfig
from src.soil_database import apply_mineral_overrides


FORCING = {"precip": 100.0, "temp": 25.0, "pCO2": 0.015}
ACTION = MonthlyAction()


def _reader():
    return InputReader("data/soil_survey.csv", "data/exchangeable_ions.csv")


def _profile(profile, cec=18.0, ph=4.5, exch_al=3.5, exch_ca=5.0, depth=10.0):
    """按 L6 覆盖语义构建表层差异 profile (高 CEC/低 pH/高交换 Al/高交换 Ca)"""
    lo = LayerOverrideConfig(cec=cec, ph=ph, exch_al=exch_al, exch_ca=exch_ca)
    return _reader().apply_layer_override(profile, lo, depth=depth)


def test_build_initial_state_layer_differentiated(profile, soil_info):
    """L6/T3: 覆盖 profile/矿物/pCO2 → 逐层初始态差异化 (同深度控制厚度变量)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    p_override = _profile(profile)
    p_default = _reader().apply_layer_override(
        profile, LayerOverrideConfig(), depth=10.0)
    # 覆盖 goethite=0.30 (默认 red_soil 约 0.15) → 富铁氧化物
    m_override = apply_mineral_overrides(soil_info, {"goethite": 0.30})

    s_default = e.build_initial_state(p_default, soil_info, 0.015)
    s_override = e.build_initial_state(p_override, m_override, 0.030)

    # 高交换 Ca/Al (cmol/kg 覆盖) → 交换位点摩尔量更大
    assert s_override.exchange["CaX2"] > s_default.exchange["CaX2"]
    assert s_override.exchange["AlX3"] > s_default.exchange["AlX3"]
    # 富铁氧化物 (0.30 > 0.15) → goethite 摩尔量更高
    assert s_override.minerals["goethite"] > s_default.minerals["goethite"]
    # 逐层 pCO2 → 初始气相不同
    assert s_override.gas_phase["CO2(g)"] == pytest.approx(0.030)
    assert s_default.gas_phase["CO2(g)"] == pytest.approx(0.015)
    # 逐层 pH → 初始状态 pH 不同
    assert s_override.ph == pytest.approx(4.5)
    assert s_default.ph == pytest.approx(5.0)
    # 同深度同容重 → 溶液体积相同 (厚度/容重变量已控制)
    assert s_override.volume == pytest.approx(s_default.volume)


def test_build_initial_state_sets_theta(profile, soil_info):
    """v0.5.3/T1 (S5): build_initial_state 设 state.theta = VGM 田间持水量正算

    θ 与化学初始溶液体积严格联动: state.volume = θ×depth×1e5 (Q8)。
    """
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    assert 0 < state.theta < profile.porosity
    assert state.volume == pytest.approx(
        state.theta * profile.effective_depth * 1e5)
    # 显式 vgm 覆盖 → θ 变化 (D8 ① 优先级生效于引擎初始化)
    lo = LayerOverrideConfig(vgm_theta_r=0.05, vgm_alpha=0.03, vgm_n=1.35)
    p_custom = _reader().apply_layer_override(profile, lo, depth=20.0)
    s_custom = e.build_initial_state(p_custom, soil_info, 0.015)
    assert s_custom.theta != pytest.approx(state.theta)


def test_multi_layer_pco2_injection(profile, soil_info, monkeypatch):
    """L6/T3: run_monthly_multi_layer(layer_pco2s) → 月度 GAS_PHASE 分压按层注入"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(2)]

    captured = []
    orig = e.run_monthly_step

    def spy(state, forcing, action, soil_profile):
        captured.append(forcing.get("pCO2"))
        return orig(state, forcing, action, soil_profile)

    monkeypatch.setattr(e, "run_monthly_step", spy)
    e.run_monthly_multi_layer(states, FORCING, ACTION, profile,
                              layer_pco2s=[0.020, 0.030])
    assert captured == [0.020, 0.030]


def test_multi_layer_pco2s_fallback_global(profile, soil_info, monkeypatch):
    """L6/T3: 不传 layer_pco2s → 各层回退全局 forcing['pCO2']"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(2)]

    captured = []
    orig = e.run_monthly_step

    def spy(state, forcing, action, soil_profile):
        captured.append(forcing.get("pCO2"))
        return orig(state, forcing, action, soil_profile)

    monkeypatch.setattr(e, "run_monthly_step", spy)
    e.run_monthly_multi_layer(states, FORCING, ACTION, profile)
    assert captured == [0.015, 0.015]


def test_multi_layer_pco2s_single_layer_ignored(profile, soil_info):
    """L6/T3: n=1 走单层路径 (回归护栏), layer_pco2s 不影响"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    new_multi, _ = e.run_monthly_multi_layer(
        [state], FORCING, ACTION, profile, layer_pco2s=[0.5])
    assert new_multi[0].ph > 0


# ==================== T4: main.py 多层编排集成 ====================

import main
from src.phreeqc_engine import PhreeqcEngine
from src.config_manager import SimulationConfig


def test_build_initial_layer_states_no_overrides(profile, soil_info):
    """L6/T4: 无 overrides → 各层相同, layer_pco2s/profiles 为 None"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    cfg = SimulationConfig(n_layers=2)
    s0, states, pco2s, profiles = main._build_initial_layer_states(
        e, _reader(), profile, soil_info, 0.015, cfg)
    assert len(states) == 2
    assert states[0].exchange == states[1].exchange
    assert pco2s is None
    assert profiles is None


def test_build_initial_layer_states_with_overrides(profile, soil_info):
    """L6/T4: 逐层 overrides → 各层差异化 + layer_pco2s/profiles 正确"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    lo0 = LayerOverrideConfig(cec=18.0, ph=4.5, exch_al=3.5,
                              exch_ca=5.0, pCO2=0.030)
    lo1 = LayerOverrideConfig(bulk_density=1.4)
    cfg = SimulationConfig(n_layers=2, layer_depths=[10.0, 20.0],
                           layer_overrides=[lo0, lo1])
    s0, states, pco2s, profiles = main._build_initial_layer_states(
        e, _reader(), profile, soil_info, 0.015, cfg)
    assert len(states) == 2
    # 逐层覆盖生效: 各层初始状态差异化 (ph/交换/气相不同)
    assert states[0].exchange != states[1].exchange
    assert states[0].gas_phase != states[1].gas_phase
    assert states[0].ph == pytest.approx(4.5)
    assert states[1].ph == pytest.approx(5.0)
    # pCO2: 第 1 层覆盖 0.03, 第 2 层回退全局 0.015
    assert pco2s == [0.030, 0.015]
    assert states[0].gas_phase["CO2(g)"] == pytest.approx(0.030)
    assert states[1].gas_phase["CO2(g)"] == pytest.approx(0.015)
    # 层深派生
    assert profiles[0].effective_depth == 10.0
    assert profiles[1].effective_depth == 20.0


def test_build_initial_layer_states_single_layer_ignores(profile, soil_info):
    """L6/T4: n_layers=1 + overrides → 忽略覆盖 (单层回归护栏)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    lo = LayerOverrideConfig(cec=18.0)
    cfg = SimulationConfig(n_layers=1, layer_overrides=[lo])
    s0, states, pco2s, profiles = main._build_initial_layer_states(
        e, _reader(), profile, soil_info, 0.015, cfg)
    assert len(states) == 1
    # 单层使用默认 profile (忽略覆盖)
    ref = e.build_initial_state(profile, soil_info, 0.015)
    assert states[0].exchange == ref.exchange
    assert pco2s is None
    assert profiles is None


def test_build_initial_layer_states_n4_auto_hydrology_defaults(profile, soil_info):
    """v0.5.0/T3: n_layers=4 且未配置 layer_overrides → 自动注入内置物理剖面默认 (水文)"""
    from src.constants import (DEFAULT_4LAYER_DEPTHS, DEFAULT_4LAYER_CLAY_PCT,
                               DEFAULT_4LAYER_POROSITY, DEFAULT_4LAYER_KSAT,
                               DEFAULT_4LAYER_F0, DEFAULT_4LAYER_FC)
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    cfg = SimulationConfig(n_layers=4)
    s0, states, pco2s, profiles = main._build_initial_layer_states(
        e, _reader(), profile, soil_info, 0.015, cfg)
    assert len(states) == 4
    assert len(profiles) == 4
    assert pco2s is not None
    # 层厚默认 [20,20,20,40]
    for i, d in enumerate(DEFAULT_4LAYER_DEPTHS):
        assert profiles[i].effective_depth == d
    # 孔隙度 + 反推容重 ρ=2.65(1−φ)
    for i in range(4):
        assert profiles[i].porosity == pytest.approx(DEFAULT_4LAYER_POROSITY[i])
        assert profiles[i].bulk_density == pytest.approx(
            2.65 * (1 - DEFAULT_4LAYER_POROSITY[i]))
    # 水文参数 + 粘粒
    assert profiles[0].ksat == DEFAULT_4LAYER_KSAT[0]
    assert profiles[3].ksat == DEFAULT_4LAYER_KSAT[3]
    assert profiles[0].infiltration_initial == DEFAULT_4LAYER_F0[0]
    assert profiles[3].infiltration_steady == DEFAULT_4LAYER_FC[3]
    assert profiles[0].clay_pct == DEFAULT_4LAYER_CLAY_PCT[0]
    assert profiles[3].clay_pct == DEFAULT_4LAYER_CLAY_PCT[3]


# ==================== v0.5.2: Ksat 字段拆分 (S2/S3 seam) ====================

def test_ksat_drainage_defaults_and_surface():
    """v0.5.2/T2: 排水 Ksat 默认更新 + ksat_surface 默认 (Green-Ampt 基质导水率)"""
    from src.constants import DEFAULT_4LAYER_KSAT, DEFAULT_KSAT_SURFACE
    assert DEFAULT_4LAYER_KSAT == pytest.approx([12.0, 1.9, 0.48, 0.05])
    assert DEFAULT_KSAT_SURFACE == 7.2


def test_apply_layer_override_ksat_surface():
    """v0.5.2/T2: apply_layer_override 应用 ksat (排水) + ksat_surface (入渗)"""
    base = _reader().build_soil_profile()
    lo = LayerOverrideConfig(ksat=12.0, ksat_surface=7.2)
    prof = _reader().apply_layer_override(base, lo, depth=20.0)
    assert prof.ksat == 12.0
    assert prof.ksat_surface == 7.2


def test_build_initial_layer_states_n4_injects_ksat_surface(profile, soil_info):
    """v0.5.2/T2: 4 层内置默认注入 ksat_surface (Green-Ampt 地表入渗用)"""
    from src.constants import DEFAULT_KSAT_SURFACE
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    cfg = SimulationConfig(n_layers=4)
    s0, states, pco2s, profiles = main._build_initial_layer_states(
        e, _reader(), profile, soil_info, 0.015, cfg)
    for i in range(4):
        assert profiles[i].ksat_surface == DEFAULT_KSAT_SURFACE


# ==================== v0.5.2: 大孔隙优先流 bypass (S4/S5 seam) ====================

def test_apply_hydrology_month_bypass_water(profile, soil_info):
    """v0.5.2/T3: _apply_hydrology_month 返回 bypass_water_L (径流×bypass_fraction)"""
    from src.config_manager import SimulationConfig as _SC
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    cfg = _SC(n_layers=4, bypass_fraction=0.2)
    s0, states, _, profiles = main._build_initial_layer_states(
        e, _reader(), profile, soil_info, 0.015, cfg)
    hydrology, runoff_mm, runoff_extra = main._apply_hydrology_month(
        states, profiles, FORCING, 0, 0, seed=42)
    assert 'bypass_water_L' in hydrology
    # 优先流 = 径流水量 × β
    assert hydrology['bypass_water_L'] == pytest.approx(
        runoff_mm * 10000.0 * 0.2)


def test_multi_layer_bypass_injected_to_L2(profile, soil_info, monkeypatch):
    """v0.5.2/T3: run_monthly_multi_layer 对 L2 注入 bypass_water_L, L1 无"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(2)]
    captured = []

    def spy(state, forcing, action, soil_profile):
        captured.append(forcing.get('bypass_water_L', None))
        return orig(state, forcing, action, soil_profile)

    orig = e.run_monthly_step
    monkeypatch.setattr(e, "run_monthly_step", spy)
    inflows = [1.0e5, 3.0e4]
    drains = [3.0e4, 2.0e4]
    e.run_monthly_multi_layer(
        states, FORCING, ACTION, profile,
        hydrology={'inflows': inflows, 'drains': drains,
                   'bypass_water_L': 1.0e4})
    assert captured == [None, 1.0e4]  # L1 无优先流, L2 注入


def test_build_input_bypass_precip_chemistry(profile, soil_info):
    """v0.5.2/T3: _build_phreeqc_input 对 bypass 水量追加 H2O + 降水化学"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    forcing = dict(FORCING)
    forcing['inflow_water_L'] = 1000.0
    forcing['bypass_water_L'] = 2000.0
    inp = e._build_phreeqc_input(state, forcing, ACTION, profile)
    assert "# 优先流" in inp  # bypass H2O 注释行
    # bypass 2000L → 2000×55.5 mol H2O 追加
    assert "1.110000e+05" in inp or "1.11000e+05" in inp


# ==================== v0.5.2: 硝化产酸限 L1 (S4 seam) ====================

def test_multi_layer_nitrification_L1_only(profile, soil_info, monkeypatch):
    """v0.5.2/T4: 硝化产酸仅 L1 (表层酸化源强化); L2~L4 跳过氮过程"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(2)]
    captured = []

    def spy(state, forcing, action, soil_profile):
        captured.append(forcing.get('skip_nitrification', False))
        return orig(state, forcing, action, soil_profile)

    orig = e.run_monthly_step
    monkeypatch.setattr(e, "run_monthly_step", spy)
    e.run_monthly_multi_layer(states, FORCING, ACTION, profile)
    assert captured == [False, True]  # L1 正常产酸, L2 跳过


def test_run_official_step_skips_nitrification(profile, soil_info, monkeypatch):
    """v0.5.2/T4: _run_official_step 在 skip_nitrification 时不推进氮库存/产酸"""
    from src.phreeqc_engine import advance_nitrification
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    calls = []

    def fake_advance(state, action, k1, k2):
        calls.append(1)
        return {'H+': 1.0}

    monkeypatch.setattr("src.phreeqc_engine.advance_nitrification", fake_advance)
    # 正常: 调用 advance_nitrification
    e._run_official_step(state, dict(FORCING), ACTION, profile)
    assert len(calls) == 1
    # skip: 不调用
    forcing_skip = dict(FORCING)
    forcing_skip['skip_nitrification'] = True
    e._run_official_step(state, forcing_skip, ACTION, profile)
    assert len(calls) == 1  # 未再调用


def test_hydrology_diagnostics_bypass_column(profile, soil_info):
    """v0.5.2/T5: _extract_diagnostics_with_hydrology 对 L2 注入 bypass_drainage"""
    from src.config_manager import SimulationConfig as _SC
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    cfg = _SC(n_layers=4, bypass_fraction=0.2)
    s0, states, _, profiles = main._build_initial_layer_states(
        e, _reader(), profile, soil_info, 0.015, cfg)
    hydrology, runoff_mm, runoff_extra = main._apply_hydrology_month(
        states, profiles, FORCING, 0, 0, seed=42, theta_i=0.275,
        bypass_fraction=0.2)
    # 构造与层数匹配的诊断对象 (用 None 占位, 函数仅访问 hydrology 字段)
    diag_objs = [None] * 4
    layer_diags = main._extract_diagnostics_with_hydrology(
        states, hydrology, runoff_mm, runoff_extra, diag_objs,
        ["bypass_drainage"], profiles)
    assert layer_diags[1]["bypass_drainage"] == pytest.approx(
        hydrology["bypass_water_L"])


# ==================== v0.5.0/T4: 引擎水文集成 ====================

def test_multi_layer_hydrology_inflow_and_drain(profile, soil_info, monkeypatch):
    """v0.5.0/T4: run_monthly_multi_layer(hydrology) → 各层注入水量 + 层间排水"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(2)]
    inflows = [1.0e5, 3.0e4]  # 层1 入渗, 层2 接收上层排水
    drains = [3.0e4, 2.0e4]

    captured = []
    orig = e.run_monthly_step

    def spy(state, forcing, action, soil_profile):
        captured.append(forcing.get('inflow_water_L', None))
        return orig(state, forcing, action, soil_profile)

    monkeypatch.setattr(e, "run_monthly_step", spy)
    e.run_monthly_multi_layer(states, FORCING, ACTION, profile,
                              hydrology={'inflows': inflows, 'drains': drains})
    assert captured == inflows


def test_engine_build_input_uses_inflow_water(profile, soil_info):
    """v0.5.0/T4: _build_phreeqc_input REACTION H2O 用该层来水量"""
    from src.scenario_controller import MonthlyAction as _MA
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    forcing = dict(FORCING)
    forcing['inflow_water_L'] = 1000.0
    inp = e._build_phreeqc_input(state, forcing, _MA(), profile)
    assert "H2O" in inp
    # 该层来水为 0 → 无 H2O 行
    forcing2 = dict(FORCING)
    forcing2['inflow_water_L'] = 0.0
    inp2 = e._build_phreeqc_input(state, forcing2, _MA(), profile)
    assert "H2O" not in inp2


# ==================== v0.5.0/T5: main 水文集成 + 输出 ====================

def test_apply_hydrology_month(profile, soil_info):
    """v0.5.0/T5: 月度水文 (随机降雨+Horton+级联) → inflows/drains/stored_water"""
    from src.config_manager import SimulationConfig as _SC
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    cfg = _SC(n_layers=4)
    _, states, _, profiles = main._build_initial_layer_states(
        e, _reader(), profile, soil_info, 0.015, cfg)
    hydrology, runoff_mm, runoff_extra = main._apply_hydrology_month(
        states, profiles, FORCING, 0, 0, seed=42)
    assert len(hydrology['inflows']) == 4
    assert len(hydrology['drains']) == 4
    assert hydrology['inflows'][0] > 0                      # 层1 入渗水
    assert hydrology['inflows'][1] == hydrology['drains'][0]  # 层2 接收上层排水
    # 月降水守恒: 入渗(mm) + 径流(mm) = 月降水
    inf_mm = hydrology['inflows'][0] / 10000.0
    assert inf_mm + runoff_mm == pytest.approx(FORCING['precip'])
    # 持水生效: 至少一层有滞水 (v0.5.3: θ 状态)
    assert any(s.theta > 0 for s in states)


def test_hydrology_multi_layer_month_step(profile, soil_info):
    """v0.5.0/T5: 4 层水文模式月度步 E2E 运行"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    cfg = SimulationConfig(n_layers=4)
    _, states, pco2s, profiles = main._build_initial_layer_states(
        e, _reader(), profile, soil_info, 0.015, cfg)
    hydrology, _, _ = main._apply_hydrology_month(
        states, profiles, FORCING, 0, 0, seed=42)
    new_states, diags = e.run_monthly_multi_layer(
        states, FORCING, ACTION, profile,
        layer_pco2s=pco2s, hydrology=hydrology)
    assert len(new_states) == 4
    assert len(diags) == 4
    assert all(s.ph > 0 for s in new_states)


def test_hydrology_diagnostics_extracted(profile, soil_info):
    """v0.5.0/T5: 层诊断附加水文列 (infiltration/drainage/stored_water)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    cfg = SimulationConfig(n_layers=4)
    _, states, pco2s, profiles = main._build_initial_layer_states(
        e, _reader(), profile, soil_info, 0.015, cfg)
    hydrology, runoff_mm, runoff_extra = main._apply_hydrology_month(
        states, profiles, FORCING, 0, 0, seed=42)
    new_states, diags = e.run_monthly_multi_layer(
        states, FORCING, ACTION, profile,
        layer_pco2s=pco2s, hydrology=hydrology)
    layer_diags = main._extract_diagnostics_with_hydrology(
        new_states, hydrology, runoff_mm, runoff_extra, diags,
        ["pH", "base_saturation", "CEC_occupied", "exchangeable_Ca",
         "exchangeable_Al", "mineral_mass", "solution_ions"], profiles)
    assert "infiltration" in layer_diags[0]
    assert "drainage" in layer_diags[0]
    assert "stored_water" in layer_diags[0]
    assert "runoff" in layer_diags[0]
    # v0.5.3: stored_water 列向后兼容 (L/ha, 由 θ 换算, 专家★5)
    assert layer_diags[0]["stored_water"] == pytest.approx(
        new_states[0].theta * profiles[0].effective_depth * 1e5)


# ==================== T5: 诊断实验逻辑 (impact_tag/depletion_year) ====================

import sys
from pathlib import Path
_TOOLS_DIR = str(Path(__file__).parent.parent / "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
from plot_L6_layer_overrides import impact_tag, depletion_year


def test_depletion_year():
    """L6/T5: 耗尽年判定 (阈值 1000 mol)"""
    assert depletion_year([5000.0, 800.0, 100.0]) == 2
    assert depletion_year([5000.0, 4000.0, 3000.0]) is None


def test_impact_tag_good_delay():
    """L6/T5: 真实剖面耗尽推迟 (y2→y5) → good"""
    base = [5000.0, 800.0, 100.0, 50.0]
    real = [5000.0, 4000.0, 3000.0, 2000.0, 1000.0, 900.0]
    assert impact_tag(base, real) == 'good'


def test_impact_tag_good_real_never_depletes():
    """L6/T5: 真实剖面未耗尽而基线耗尽 → good"""
    base = [5000.0, 800.0, 100.0]
    real = [5000.0, 4000.0, 3000.0]
    assert impact_tag(base, real) == 'good'


def test_impact_tag_bad_earlier():
    """L6/T5: 真实剖面更早耗尽 (y4→y2) → bad"""
    base = [5000.0, 4000.0, 3000.0, 800.0]
    real = [5000.0, 800.0, 100.0, 50.0]
    assert impact_tag(base, real) == 'bad'


def test_impact_tag_bad_real_depletes_base_not():
    """L6/T5: 真实剖面耗尽而基线未耗尽 → bad"""
    base = [5000.0, 4000.0, 3000.0]
    real = [5000.0, 800.0, 100.0]
    assert impact_tag(base, real) == 'bad'


def test_impact_tag_neutral():
    """L6/T5: 两者耗尽情况一致 → neutral"""
    base = [5000.0, 4000.0, 3000.0]
    real = [5000.0, 4000.0, 3000.0]
    assert impact_tag(base, real) == 'neutral'
