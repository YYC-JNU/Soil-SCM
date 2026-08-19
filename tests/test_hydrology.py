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


def test_cascade_drains_only_above_field_capacity():
    """v0.5.3 (D3/Q11): 可排水量 = max(0, θ−θ_FC)×depth×1e5

    Q6: 原 test_cascade_fills_storage_before_drain 断言 50% 饱和持水语义,
    v0.5.3 重构为 VGM 田间持水量 θ_FC (L1≈0.410) 以下不排水。
    """
    prof = _surface_profile(porosity=0.55, depth=20, ksat=76.8)
    # θ=θ_FC → 无排水
    state_fc = SoilState(theta=0.4101)
    drains, runoff, deep = LayerCascade([prof]).run(0.0, [state_fc])
    assert drains[0] == pytest.approx(0.0)
    assert runoff == 0.0
    # θ>θ_FC → 排水至 θ_FC (可排水量 = (0.50−0.4101)×20×1e5)
    state_wet = SoilState(theta=0.50)
    drains, runoff, deep = LayerCascade([prof]).run(0.0, [state_wet])
    assert drains[0] == pytest.approx((0.50 - 0.4101) * 20.0 * 1e5, rel=1e-3)
    assert state_wet.theta == pytest.approx(0.4101, rel=1e-3)


def test_cascade_interface_min_ksat_bucket():
    """v0.5.3 (D3): 界面通量受 min(K_r(θ)·ksat_i, ksat_{i+1}) 木桶短板限制

    θ_L1=θ_s → K_r=1 → 界面 = min(76.8, 0.05)=0.05 cm/day → 1.5e5 L/ha/月。
    """
    up = _surface_profile(porosity=0.55, depth=20, ksat=76.8)
    dn = _surface_profile(porosity=0.47, depth=20, ksat=0.05)
    state_up = SoilState(theta=0.55)   # 饱和, K_r=1
    state_dn = SoilState(theta=0.30)
    drains, runoff, _ = LayerCascade([up, dn]).run(0.0, [state_up, state_dn])
    assert drains[0] == pytest.approx(0.05 * 1e5 * 30.0)  # 1.5e5
    assert runoff == 0.0
    # L1 仅排到可排水量上限下的界面通量, θ 相应下降
    assert state_up.theta == pytest.approx(0.55 - 1.5e5 / (20.0 * 1e5))


def test_cascade_saturation_overflow_to_runoff():
    """v0.5.3: 来水使 θ>θ_s → 超饱和溢出计入 runoff (既有语义保留)"""
    prof = _surface_profile(porosity=0.55, depth=20, ksat=76.8)
    state = SoilState(theta=0.55)     # 已饱和
    drains, runoff, _ = LayerCascade([prof]).run(5.0e5, [state])
    # 入渗 5e5 全部溢出 (θ 已饱和), 随后排到 θ_FC
    assert runoff == pytest.approx(5.0e5)
    assert drains[0] == pytest.approx((0.55 - 0.4101) * 20.0 * 1e5, rel=1e-3)
    assert state.theta == pytest.approx(0.4101, rel=1e-3)


def test_cascade_bottom_deep_drainage():
    """v0.5.3: 最底层无接收层 → 通量=K_r(θ)·ksat (深层排水)"""
    prof = _surface_profile(porosity=0.55, depth=20, ksat=76.8)
    state_up = SoilState(theta=0.50)
    state_dn = SoilState(theta=0.4101)   # 起始于 θ_FC, 接收上层排水
    drains, runoff, deep = LayerCascade([prof, prof]).run(
        0.0, [state_up, state_dn])
    assert drains[0] == pytest.approx(
        (0.50 - 0.4101) * 20.0 * 1e5, rel=1e-3)
    assert drains[1] > 0.0
    assert deep == drains[1]              # 底层排水 = 深层排水流失
    assert runoff == 0.0


def test_calc_interface_flux_downward_only():
    """v0.5.3 (S2 专家★2): 纯向下方向约束 — q≥0 恒成立, 干源层 q=0,
    饱和退化 min(ksat_up, ksat_dn) (D3); bidirectional 预留报错
    """
    from src.hydrology import calc_interface_flux
    up = _surface_profile(porosity=0.55, depth=20, ksat=12.0)
    dn = _surface_profile(porosity=0.47, depth=20, ksat=1.9)
    # 饱和源层 → K_r=1 → 界面 = min(12, 1.9) = 1.9 cm/day
    q_sat = calc_interface_flux(up, 0.55, dn, 0.40, 30)
    assert q_sat == pytest.approx(1.9 * 1e5 * 30.0)
    # 残余含水量 → K_r=0 → 无下行通量 (干源层不"抽"上层水, 无逆向回流)
    assert calc_interface_flux(up, 0.06, dn, 0.40, 30) == 0.0
    # 任意 θ ∈ [θ_r, θ_s] → q ≥ 0
    for th in (0.10, 0.25, 0.40, 0.55):
        assert calc_interface_flux(up, th, dn, 0.40, 30) >= 0.0
    # bidirectional 接口预留 (v0.6.0+ 毛细上升)
    with pytest.raises(NotImplementedError):
        calc_interface_flux(up, 0.55, dn, 0.40, 30, mode="bidirectional")


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


# ==================== v0.5.3 Feddes ET (S2, Q3/Q9) ====================

def test_apply_feddes_et_alpha_one():
    """最适水分 (α=1): AET = PET×f_root (无亏缺, θ 按水柱换算下降)"""
    from src.hydrology import apply_feddes_et
    prof = _surface_profile(porosity=0.55, depth=20)
    state = SoilState(theta=0.40)   # ψ≈-110cm ∈ (h3,h2) → α=1
    aet, deficit = apply_feddes_et([state], 30.0, [prof], root_weights=[1.0])
    assert aet[0] == pytest.approx(30.0)          # 需求 30mm < 可提取 51.5mm
    assert deficit == pytest.approx(0.0)
    # Δθ = AET/(depth×10) = 30/200 = 0.15
    assert state.theta == pytest.approx(0.40 - 0.15)


def test_apply_feddes_et_alpha_zero_wilting():
    """永久萎蔫以下 (α=0): AET=0, θ 不变 (θ 不取负的天然钳制)"""
    from src.hydrology import apply_feddes_et
    prof = _surface_profile(porosity=0.55, depth=20)
    state = SoilState(theta=0.10)   # < θ(ψ=h4)≈0.143 → α=0
    aet, deficit = apply_feddes_et([state], 100.0, [prof], root_weights=[1.0])
    assert aet[0] == pytest.approx(0.0)
    assert deficit == pytest.approx(0.0)          # 需求因 α=0 归零, 非亏缺
    assert state.theta == pytest.approx(0.10)


def test_apply_feddes_et_deficit_clamped():
    """需求超出可提取水量 → AET 截断至 θ(ψ=h4), 差额计入 et_deficit"""
    from src.hydrology import apply_feddes_et
    prof = _surface_profile(porosity=0.55, depth=20)
    state = SoilState(theta=0.40)
    aet, deficit = apply_feddes_et([state], 100.0, [prof], root_weights=[1.0])
    # 可提取 = (0.40−θ_wp)×20×10 ≈ 51.5mm; 需求 100 → AET≈51.5, 亏缺≈48.5
    assert aet[0] == pytest.approx(51.5, abs=0.5)
    assert deficit == pytest.approx(100.0 - 51.5, abs=0.5)
    # θ 回落到 θ_wp (不再低于萎蔫点)
    assert state.theta == pytest.approx(0.143, abs=0.003)


def test_apply_feddes_et_root_weights_4layer():
    """4 层根系权重 60/30/10/0: AET 按权重分配, ΣAET = PET (α=1 无钳制)"""
    from src.hydrology import apply_feddes_et
    prof = _surface_profile(porosity=0.55, depth=20)
    states = [SoilState(theta=0.40) for _ in range(4)]
    aet, deficit = apply_feddes_et(states, 20.0, [prof] * 4)
    assert aet == pytest.approx([12.0, 6.0, 2.0, 0.0])
    assert sum(aet) == pytest.approx(20.0)
    assert deficit == pytest.approx(0.0)
    # L4 根权重 0: θ 不变
    assert states[3].theta == pytest.approx(0.40)