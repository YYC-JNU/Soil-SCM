"""工单D (C1, 2026-08-31): 分层 pCO₂ 覆盖测试 — 深层碳酸缓冲标定机制

覆盖:
  - 访问器 layer_pco2_override 单一来源行为 (默认 None / L4 覆盖 / 越界护栏)
  - main._build_initial_layer_states 默认 None 不覆盖 (v85 基线逐位不变)
  - L4 覆盖生效 (PCO2_4LAYER_OVERRIDE[3]=0.04) → layer_pco2s[3] 与
    GAS_PHASE CO2(g) 跟随, L1~L3 不变
"""

import pytest

import main as sim_main
from src.config_manager import SimulationConfig
from src.phreeqc_engine import PhreeqcEngine
from src.input_reader import InputReader
from src.utils import layer_pco2_override
import src.constants as C


def _reader():
    return InputReader("data/soil_survey.csv", "data/exchangeable_ions.csv")


def _build(e, profile, soil_info, pco2=0.015):
    cfg = SimulationConfig(n_layers=4)
    return sim_main._build_initial_layer_states(
        e, _reader(), profile, soil_info, pco2, cfg)


# ==================== 访问器 (单一来源) ====================

def test_pco2_override_accessor_default_none():
    """默认全 None → 不覆盖 (v85 基线)"""
    assert layer_pco2_override() is None
    for li in range(4):
        assert layer_pco2_override(li, 4) is None


def test_pco2_override_accessor_guard():
    """单层/越界护栏 → None"""
    assert layer_pco2_override(0, 1) is None
    assert layer_pco2_override(9, 4) is None


def test_pco2_override_accessor_value(monkeypatch):
    """L4 覆盖值 → 仅 L4 非 None, L1~L3 None"""
    monkeypatch.setattr(C, "PCO2_4LAYER_OVERRIDE", [None, None, None, 0.04])
    assert layer_pco2_override(3, 4) == pytest.approx(0.04)
    assert layer_pco2_override(0, 4) is None
    assert layer_pco2_override(2, 4) is None


# ==================== main 集成 ====================

def test_pco2_override_default_baseline(profile, soil_info):
    """默认 None 不覆盖 → layer_pco2s = apply_om_pco2 基线 (v85 逐位不变)"""
    from src.constants import OM_PROFILE_4LAYER
    from src.climate_forcing import apply_om_pco2
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    _, _, pco2s, _ = _build(e, profile, soil_info)
    assert pco2s is not None
    for i in range(4):
        assert pco2s[i] == pytest.approx(
            apply_om_pco2(0.015, OM_PROFILE_4LAYER[i]))
    assert pco2s[0] > pco2s[1] > pco2s[2] > pco2s[3]   # 垂直梯度保持


def test_pco2_override_l4_only(profile, soil_info, monkeypatch):
    """L4 覆盖 0.04 → layer_pco2s[3] 与 GAS_PHASE 跟随, L1~L3 不变"""
    monkeypatch.setattr(C, "PCO2_4LAYER_OVERRIDE", [None, None, None, 0.04])
    from src.constants import OM_PROFILE_4LAYER
    from src.climate_forcing import apply_om_pco2
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    _, states, pco2s, _ = _build(e, profile, soil_info)
    for i in (0, 1, 2):
        assert pco2s[i] == pytest.approx(
            apply_om_pco2(0.015, OM_PROFILE_4LAYER[i]))
    assert pco2s[3] == pytest.approx(0.04)          # L4 覆盖生效
    assert states[3].gas_phase["CO2(g)"] == pytest.approx(0.04)  # GAS_PHASE 注入
    # L1~L3 气相不受影响
    assert states[0].gas_phase["CO2(g)"] == pytest.approx(pco2s[0])
    assert states[1].gas_phase["CO2(g)"] == pytest.approx(pco2s[1])
