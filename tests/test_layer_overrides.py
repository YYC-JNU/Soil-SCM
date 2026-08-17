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
