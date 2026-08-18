"""测试 v0.5.2 逐层土壤水文物理模型 (src/hydrology.py):

  - 随机日降雨生成 (seed 可复现, 场次 U(4,12), 指数分配, 月总量守恒)
  - Green-Ampt 单场入渗 (隐式方程牛顿迭代, 超渗产流自然产生, 饱和退化 Ks·t)
  - 月度分配 (逐场 Green-Ampt, ksat_surface 基质导水率, theta_i 含水量)
  - 层间级联 (50% 饱和度持水, ksat 排水上限, stored_water 跨月累积, 超饱和溢出)
"""

import pytest
from src.hydrology import (generate_rainfall,
                           monthly_hydrology, LayerCascade,
                           green_ampt_infiltration, solve_green_ampt_F)
from src.input_reader import InputReader
from src.config_manager import LayerOverrideConfig
from src.phreeqc_engine import SoilState

_reader = InputReader("data/soil_survey.csv", "data/exchangeable_ions.csv")


def _surface_profile(porosity=0.55, depth=20.0, ksat=76.8, f0=1.0, fc=0.4,
                     ksat_surface=7.2):
    base = _reader.build_soil_profile()
    lo = LayerOverrideConfig(porosity=porosity, ksat=ksat, ksat_surface=ksat_surface,
                             infiltration_initial=f0, infiltration_steady=fc)
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


def test_monthly_hydrology_conserves_water():
    """月度入渗+径流 = 月降水 (Green-Ampt 守恒)"""
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


# ==================== v0.5.2 Green-Ampt 入渗 (S1 seam) ====================

def test_green_ampt_solve_F_handcalc():
    """牛顿迭代解隐式方程手算: Ks=3mm/h, ψ_f·Δθ=41.25mm, t=2h → F≈26.4mm

    F - 41.25·ln(1+F/41.25) = 6 → F ≈ 26.41 (独立手算, 非代码自证)
    """
    F = solve_green_ampt_F(Ks_mm_h=3.0, psi_f_dtheta_mm=41.25, t_h=2.0)
    assert F == pytest.approx(26.41, abs=0.1)


def test_green_ampt_infiltration_full_and_runoff():
    """小雨 (2.5mm/h < Ks=3mm/h) 全入渗; 暴雨 (20mm/h > Ks) 超渗产流, 守恒"""
    # 小雨 5mm/2h: F(2h)≈26.4 > 5 → 全入渗
    inf_low, runoff_low = green_ampt_infiltration(
        5.0, Ks_cm_day=7.2, psi_f_mm=150.0, theta_s=0.55, theta_i=0.275)
    assert inf_low == pytest.approx(5.0)
    assert runoff_low == pytest.approx(0.0)
    # 暴雨 40mm/2h: 入渗≈26.4, 径流=13.6 (自然超渗产流)
    inf_high, runoff_high = green_ampt_infiltration(
        40.0, Ks_cm_day=7.2, psi_f_mm=150.0, theta_s=0.55, theta_i=0.275)
    assert inf_high == pytest.approx(26.41, abs=0.2)
    assert inf_high + runoff_high == pytest.approx(40.0)
    assert runoff_high > 0.0


def test_green_ampt_saturated_degenerates_to_ks_t():
    """饱和土壤 (Δθ→0) 入渗能力退化为 Ks·t = 6mm"""
    inf, _ = green_ampt_infiltration(
        40.0, Ks_cm_day=7.2, psi_f_mm=150.0, theta_s=0.55, theta_i=0.55)
    assert inf == pytest.approx(6.0, abs=0.05)


def test_monthly_hydrology_green_ampt_uses_ksat_surface():
    """v0.5.2: monthly_hydrology 用 Green-Ampt (ksat_surface 基质导水率), 月守恒

    基质导水率 3mm/h → 单场能力约 26.4mm, 大场次自然超渗产流 → 月径流 > 0
    (对比 Horton 0.75×月降水几乎全入渗)。
    """
    surf = _surface_profile(ksat=12.0, ksat_surface=7.2)
    inf, runoff, events = monthly_hydrology(158.0, 0, 0, surf, seed=42)
    assert inf + runoff == pytest.approx(158.0)
    assert inf <= 158.0
    assert inf > 0
    assert runoff > 0


def test_monthly_hydrology_theta_i_from_stored_water():
    """v0.5.2: theta_i 参数改变入渗能力 (湿土 Δθ 小 → 能力低, 径流多)"""
    surf = _surface_profile(ksat=12.0, ksat_surface=7.2)
    # 干土 θ_i=0.2 (Δθ=0.35) vs 湿土 θ_i=0.5 (Δθ=0.05)
    inf_dry, r_dry, _ = monthly_hydrology(158.0, 0, 0, surf, seed=42, theta_i=0.20)
    inf_wet, r_wet, _ = monthly_hydrology(158.0, 0, 0, surf, seed=42, theta_i=0.50)
    assert inf_dry > inf_wet
    assert r_dry < r_wet