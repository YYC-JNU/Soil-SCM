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


def _surface_profile(porosity=0.55, depth=20.0, ksat=76.8, ksat_surface=7.2):
    base = _reader.build_soil_profile()
    lo = LayerOverrideConfig(porosity=porosity, ksat=ksat, ksat_surface=ksat_surface)
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


# ==================== v0.6.0 事件生成 (S3, Q1/Q11) ====================

def test_generate_events_reproducible_with_seed():
    """v0.6.0 (Q11): 同 seed 同事件序列, 不同 seed 不同"""
    from src.hydrology import generate_events
    a1 = generate_events(150.0, 0, 0, seed=42)
    a2 = generate_events(150.0, 0, 0, seed=42)
    b = generate_events(150.0, 0, 0, seed=7)
    assert [e.precip_mm for e in a1] == [e.precip_mm for e in a2]
    assert [e.precip_mm for e in a1] != [e.precip_mm for e in b]


def test_generate_events_total_conserved_and_range():
    """v0.6.0: Σ 事件降水 = 月总量 (质量守恒不变量), 场次数 ∈ [4,12]"""
    from src.hydrology import generate_events
    for m in range(12):
        events = generate_events(158.0, 0, m, seed=42)
        assert 4 <= len(events) <= 12
        assert sum(e.precip_mm for e in events) == pytest.approx(158.0, rel=1e-6)
        assert all(e.precip_mm > 0 for e in events)


def test_rainevent_defaults():
    """v0.6.0 (Q1): RainEvent 默认历时 2.0h, date_hint 记录年/月/场序"""
    from src.hydrology import RainEvent, generate_events
    ev = RainEvent(precip_mm=10.0)
    assert ev.duration_h == 2.0
    assert ev.precip_chem is None
    assert ev.date_hint is None
    events = generate_events(158.0, 2, 5, seed=42)   # year=2, month=5 (0-indexed)
    assert all(e.date_hint is not None for e in events)


# ==================== v0.6.1 基流/侧向排水 (S1/S5, spec 62 Q1/Q2/Q4/Q10) ====================

def _vgm_params(prof):
    from src.vgm import get_vgm_params
    return get_vgm_params(prof)


def test_calc_baseflow_endpoints():
    """v0.6.1 (Q1): VIC 基流纯函数端点 — θ≤θ_r→0、θ→θ_s→D_max、防抽干 min"""
    from src.hydrology import calc_baseflow
    prof = _surface_profile(porosity=0.55, depth=40, ksat=0.05)
    theta_r, alpha, n = _vgm_params(prof)
    # θ ≤ θ_r → 0
    assert calc_baseflow(theta_r, prof) == 0.0
    assert calc_baseflow(0.0, prof) == 0.0
    # θ → θ_s (饱和): Q → D_max (默认 100 mm/month)
    q_sat = calc_baseflow(prof.porosity, prof)
    assert q_sat == pytest.approx(100.0, rel=1e-3)
    # 防抽干: 极小 (θ−θ_r) 时 cap 限制公式值
    q_near = calc_baseflow(theta_r + 0.001, prof)
    assert q_near <= 0.001 * 40.0 * 10.0  # cap = 0.4 mm


def test_calc_baseflow_config_override():
    """v0.6.1 (Q1): baseflow_cfg 覆盖 D_max/D_s/n_base + 防抽干 cap"""
    from src.hydrology import calc_baseflow
    from src.vgm import get_vgm_params
    prof = _surface_profile(porosity=0.55, depth=40, ksat=0.05)
    theta_r, alpha, n = get_vgm_params(prof)
    cfg = {'D_max': 200.0, 'D_s': 0.2, 'n_base': 2.0}
    q = calc_baseflow(prof.porosity, prof, cfg)
    # 饱和时公式=D_max=200, 但防抽干 cap=(θ_s−θ_r)·d·10 钳制 (物理上限:
    # 一次排水不可能超过"可降至 θ_r"的水量)
    cap = (prof.porosity - theta_r) * 40.0 * 10.0
    assert q == pytest.approx(min(200.0, cap), rel=1e-6)
    # 中段含水量: 公式值 < 饱和 (单调)
    mid = 0.5 * (0.55 + 0.08)
    q_mid = calc_baseflow(mid, prof, cfg)
    assert 0.0 < q_mid < q


def test_calc_baseflow_theta_r_c_theta_r():
    """v0.6.1 (Q1): θ_c=θ_r — 旱季 θ_r<θ<θ_FC 有裂隙基流 (D_s 线性项 > 0)"""
    from src.hydrology import calc_baseflow
    from src.vgm import vgm_theta_from_psi
    prof = _surface_profile(porosity=0.55, depth=40, ksat=0.05)
    theta_r, alpha, n = _vgm_params(prof)
    theta_fc = vgm_theta_from_psi(-100.0, prof.porosity, theta_r, alpha, n)
    mid = 0.5 * (theta_r + theta_fc)
    q = calc_baseflow(mid, prof)
    assert q > 0.0
    assert q < 100.0
    q_fc = calc_baseflow(theta_fc, prof)
    assert q_fc > q


def test_calc_lateral_drainage_fc_gate_and_antidrain():
    """v0.6.1 (Q1): 侧向严格 FC 闸门 (θ≤θ_FC→0) + 防抽干 min"""
    from src.hydrology import calc_lateral_drainage
    prof = _surface_profile(porosity=0.55, depth=20, ksat=76.8)
    theta_fc = 0.4101  # 该 profile θ_FC
    assert calc_lateral_drainage(theta_fc, prof, theta_fc=theta_fc) == 0.0
    assert calc_lateral_drainage(0.30, prof, theta_fc=theta_fc) == 0.0
    q = calc_lateral_drainage(0.50, prof, theta_fc=theta_fc, layer_index=0)
    expect = 0.04 * 0.10 * (0.50 - 0.4101) * 20.0 * 10.0
    assert q == pytest.approx(expect, rel=1e-6)
    assert q <= (0.50 - 0.4101) * 20.0 * 10.0


def test_cascade_run_extended_backward_compat():
    """v0.6.1 (Q4): run() 保持 3 元组 (向后兼容), run_extended() 返回 5 元组"""
    prof = _surface_profile(porosity=0.55, depth=20, ksat=76.8)
    state = SoilState(theta=0.50)
    drains, runoff, deep = LayerCascade([prof]).run(0.0, [state])
    assert drains[0] == pytest.approx((0.50 - 0.4101) * 20.0 * 1e5, rel=1e-3)
    assert deep == drains[0]
    state2 = SoilState(theta=0.50)
    d, r, b, lat, theta_out = LayerCascade([prof]).run_extended(0.0, [state2])
    assert d[0] == pytest.approx((0.50 - 0.4101) * 20.0 * 1e5, rel=1e-3)
    assert b == [0.0]
    assert lat == [0.0]
    assert theta_out == [pytest.approx(0.4101, rel=1e-3)]


def test_cascade_run_extended_with_exports():
    """v0.6.1 (Q1/Q2/Q4): 配置 baseflow/lateral 后出口非零 + θ 更新含出口"""
    prof = _surface_profile(porosity=0.55, depth=20, ksat=76.8)
    state = SoilState(theta=0.50)
    cascade = LayerCascade(
        [prof],
        baseflow_cfg={'D_max': 100.0, 'D_s': 0.10, 'n_base': 2.5},
        lateral_cfg={'f_slope': 0.10, 'k_lat': [0.04]})
    drains, runoff, baseflow, lateral, theta_out = cascade.run_extended(0.0, [state])
    assert drains[0] > 0.0
    # 垂直排水后 θ=θ_FC → 侧向闸门关闭 → 0
    assert lateral[0] == 0.0
    # 基流: θ_c=θ_r → θ_FC>θ_r 有裂隙基流
    assert baseflow[0] > 0.0
    # 水量守恒: 垂直 + 基流 + 剩余水量 = 初始可排量 + θ_r 以下束缚水
    init_water = 0.50 * 20.0 * 1e5
    final_water = theta_out[0] * 20.0 * 1e5
    assert init_water - final_water == pytest.approx(drains[0] + baseflow[0], rel=1e-6)


def test_cascade_4layer_baseflow_lateral_exports():
    """v0.6.1 (Q1/Q2): 4 层 L4 基流 + 各层侧向出口 (逐层出系统)"""
    depths = [20.0, 20.0, 20.0, 40.0]
    profs = [_surface_profile(porosity=0.55, depth=d, ksat=k)
             for d, k in zip(depths, [12.0, 1.9, 0.48, 0.05])]
    states = [SoilState(theta=0.50) for _ in range(4)]
    init_thetas = [s.theta for s in states]  # run 前快照 (states 就地修改)
    cascade = LayerCascade(
        profs,
        baseflow_cfg={'D_max': 100.0, 'D_s': 0.10, 'n_base': 2.5},
        lateral_cfg={'f_slope': 0.10, 'k_lat': [0.04, 0.025, 0.015, 0.008]})
    drains, runoff, baseflow, lateral, theta_out = cascade.run_extended(0.0, states)
    assert len(drains) == 4
    assert all(l >= 0.0 for l in lateral)
    # 物理行为: 表层 L1 垂直排水快 → 侧向闸门关闭 (θ→θ_FC); 深层 L4 ksat 慢
    # → θ 仍高 → 侧向/基流成为深层主出口 (正是缓解"深层盐分累积"的核心价值)
    assert lateral[0] == 0.0
    assert lateral[3] > 0.0
    assert baseflow[0] == 0.0 and baseflow[1] == 0.0 and baseflow[2] == 0.0
    assert baseflow[3] > 0.0
    # 出口总量守恒: 系统总水量减少 = Σ侧向 + Σ基流 + L4 垂直出口 + 超饱和溢出
    # (层间 drains 只是层间转移, 不减少系统总量; 溢出计入 runoff_extra)
    total_out = sum(lateral) + sum(baseflow) + drains[-1] + runoff
    init_water = sum(t0 * p.effective_depth * 1e5
                     for t0, p in zip(init_thetas, profs))
    final_water = sum(t * p.effective_depth * 1e5
                      for t, p in zip(theta_out, profs))
    assert init_water - final_water == pytest.approx(total_out, rel=1e-4)


def test_cascade_single_layer_baseflow_works():
    """v0.6.1 (Q10): 单层 + baseflow_cfg → 基流生效 (n_layers=1 护栏由 config 层禁用)"""
    prof = _surface_profile(porosity=0.55, depth=20, ksat=76.8)
    state = SoilState(theta=0.50)
    cascade = LayerCascade(
        [prof], baseflow_cfg={'D_max': 100.0, 'D_s': 0.10, 'n_base': 2.5})
    d, r, b, lat, theta_out = cascade.run_extended(0.0, [state])
    assert b[0] > 0.0


def test_calc_lateral_drainage_layer_index():
    """v0.6.1 (Q1): 分层 k_lat 索引 (L1 快 / L4 慢)"""
    from src.hydrology import calc_lateral_drainage
    prof = _surface_profile(porosity=0.55, depth=20, ksat=76.8)
    q_l1 = calc_lateral_drainage(0.50, prof, theta_fc=0.4101, layer_index=0)
    q_l4 = calc_lateral_drainage(0.50, prof, theta_fc=0.4101, layer_index=3)
    assert q_l1 > q_l4
    assert q_l1 == pytest.approx(0.04 * 0.10 * (0.50 - 0.4101) * 20.0 * 10.0)
    assert q_l4 == pytest.approx(0.008 * 0.10 * (0.50 - 0.4101) * 20.0 * 10.0)
