"""测试 v0.5.0 逐层土壤水文盒子模型 (src/hydrology.py):

  - 随机日降雨生成 (seed 可复现, 场次 U(4,12), 指数分配, 月总量守恒)
  - Horton 单场入渗 (k=5/h, 表层入渗系数 0.75, 降水耗尽全入渗)
  - 层间级联 (50% 饱和度持水, Ksat 限制渗漏, stored_water 跨月累积, 超饱和溢出)
"""

import pytest
import numpy as np
from src.hydrology import (generate_rainfall, horton_event_infiltration,
                           monthly_hydrology, LayerCascade,
                           HORTON_DECAY_K_PER_H)
from src.constants import DEFAULT_SURFACE_INFILTRATION_COEFF
from src.input_reader import InputReader
from src.config_manager import LayerOverrideConfig
from src.phreeqc_engine import SoilState

_reader = InputReader("data/soil_survey.csv", "data/exchangeable_ions.csv")


def _surface_profile(porosity=0.55, depth=20.0, ksat=76.8, f0=1.0, fc=0.4):
    base = _reader.build_soil_profile()
    lo = LayerOverrideConfig(porosity=porosity, ksat=ksat,
                             infiltration_initial=f0,
                             infiltration_steady=fc)
    return _reader.apply_layer_override(base, lo, depth)


def test_rainfall_reproducible_with_seed():
    """同 seed 可复现, 不同 seed 不同"""
    a1 = generate_rainfall(150.0, 0, 0, seed=42)
    a2 = generate_rainfall(150.0, 0, 0, seed=42)
    b = generate_rainfall(150.0, 0, 0, seed=7)
    assert a1 == a2
    assert a1 != b


def test_rainfall_total_conserved_and_range():
    """月降水总量守恒, 场次数 ∈ [4,12]"""
    for m in range(12):
        events = generate_rainfall(158.0, 0, m, seed=42)
        assert len(events) == len(set(id(e) for e in events))  # 非空
        assert 4 <= len(events) <= 12
        assert sum(events) == pytest.approx(158.0, rel=1e-6)
        assert all(e > 0 for e in events)


def test_horton_event_capacity_handcalc():
    """Horton 单场入渗能力手算: f0=1.0/fc=0.4/k=5/h/T=2h → A≈55.2mm"""
    # A = fc×T + (f0−fc)/k×(1−e^(−kT)), k/min=5/60, T=120min
    k_min = HORTON_DECAY_K_PER_H / 60.0
    A = (0.4 * 120 + (1.0 - 0.4) / k_min * (1 - np.exp(-k_min * 120)))
    assert A == pytest.approx(55.2, abs=0.1)


def test_horton_event_infiltration_cap_and_depletion():
    """入渗 = min(场降水×0.75, Horton 能力); 降水耗尽则全入渗"""
    surf = _surface_profile()
    # 大降水 (200mm): 受 Horton 能力限制 (≈55.2mm)
    inf = horton_event_infiltration(200.0, surf.infiltration_initial,
                                    surf.infiltration_steady)
    assert inf == pytest.approx(55.2, abs=0.5)
    # 小降水 (10mm): 10×0.75=7.5 < 55.2 → 全入渗 (降水耗尽)
    inf2 = horton_event_infiltration(10.0, surf.infiltration_initial,
                                     surf.infiltration_steady)
    assert inf2 == pytest.approx(10.0 * DEFAULT_SURFACE_INFILTRATION_COEFF)


def test_horton_surface_coeff_parameter():
    """v0.5.1: surface_coeff 参数控制入渗上限 (config 驱动)"""
    surf = _surface_profile()
    # 50×0.9=45 < 能力55.2 → 45; 50×0.2=10 < 55.2 → 10
    inf_high = horton_event_infiltration(50.0, surf.infiltration_initial,
                                         surf.infiltration_steady,
                                         surface_coeff=0.9)
    inf_low = horton_event_infiltration(50.0, surf.infiltration_initial,
                                        surf.infiltration_steady,
                                        surface_coeff=0.2)
    assert inf_high == pytest.approx(45.0)
    assert inf_low == pytest.approx(10.0)


def test_monthly_hydrology_conserves_water():
    """月度入渗+径流 = 月降水"""
    surf = _surface_profile()
    inf, runoff, events = monthly_hydrology(158.0, 0, 0, surf, seed=42)
    assert inf + runoff == pytest.approx(158.0)
    assert inf <= 158.0
    assert inf > 0


def test_cascade_fills_storage_before_drain():
    """级联: 先填 50%→100% 持水增量, 超出才排水"""
    profiles = [
        _surface_profile(porosity=0.55, depth=20, ksat=76.8),
        _surface_profile(porosity=0.47, depth=20, ksat=24.5),
    ]
    states = [SoilState(), SoilState()]
    # 层1 sat=0.55×20×1e5=1.1e6, space=5.5e5; 来水 1e6 < sat
    cascade = LayerCascade(profiles)
    drains, runoff, deep = cascade.run(1.0e6, states)
    assert drains[0] == pytest.approx(1.0e6 - 5.5e5)  # 超持水部分排
    assert states[0].stored_water == pytest.approx(5.5e5)  # 填满至饱和
    assert drains[1] == 0.0  # 层2来水 4.5e5 < space 4.7e5, 无排水
    assert runoff == 0.0
    assert deep == 0.0


def test_cascade_ksat_limits_drain_and_overflow():
    """Ksat 限制排水 + 超饱和溢出计入径流"""
    profiles = [
        _surface_profile(porosity=0.30, depth=10, ksat=0.1),
        # ksat_cap = 0.1cm/day×30天×1e8cm² = 3e5 L/ha/月
    ]
    states = [SoilState()]
    # sat=0.3×10×1e5=3e5, space=1.5e5; 来水 1e6
    cascade = LayerCascade(profiles)
    drains, runoff, deep = cascade.run(1.0e6, states)
    assert drains[0] == pytest.approx(3.0e5)  # Ksat 限制 (cap=3e5)
    assert states[0].stored_water == pytest.approx(3.0e5)  # 饱和
    assert runoff == pytest.approx(1.0e6 - 3.0e5 - 3.0e5)  # 溢出=4e5


def test_cascade_stored_water_carries_to_next_month():
    """跨月滞水: 上月末 stored_water 作为下月初始 (饱和后新来水全排)"""
    profiles = [_surface_profile(porosity=0.5, depth=10, ksat=76.8)]
    state = SoilState(stored_water=2.5e5)  # 上月已填满 50% 增量 (sat=5e5)
    cascade = LayerCascade(profiles)
    # 新来水 2e5 → avail=4.5e5 > space=2.5e5 → 排水 2e5
    drains, _, _ = cascade.run(2.0e5, [state])
    assert drains[0] == pytest.approx(2.0e5)
    assert state.stored_water == pytest.approx(2.5e5)