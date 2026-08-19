"""测试 v0.5.3 VGM 水分特征模块 (src/vgm.py) — S1 新 seam (spec 49):

  - VGM 正算 vgm_theta_from_psi (ψ→θ, 手算验证, 饱和退化 θ_s)
  - VGM 反算 calc_psi (θ→ψ, 与正算往返恒等)
  - Mualem 相对导水率 calc_Kr / calc_K (θ_s→1, θ_r→0, 单调)
  - get_vgm_params 三级优先级 (显式 > clay_pct 回归 > 红壤兜底, 部分覆盖)
  - θ↔L/ha 换算往返恒等 (专家★1: 覆盖 depth 20/20/20/40、θ=0、θ=θ_s)
"""

import pytest
import types
from src.vgm import (vgm_theta_from_psi, calc_psi, calc_Kr, calc_K,
                     get_vgm_params, theta_to_water_L, water_L_to_theta,
                     feddes_alpha)

# 4 层内置默认 L1 剖面 VGM 参数 (VGM参数化方案.txt: 粘粒 25%)
L1_THETA_S = 0.55
L1_THETA_R = 0.06
L1_ALPHA = 0.025
L1_N = 1.30


def _profile(clay_pct=25.0, vgm_theta_r=None, vgm_alpha=None, vgm_n=None):
    """构造 get_vgm_params 输入对象 (SoilProfile 鸭子类型)"""
    return types.SimpleNamespace(clay_pct=clay_pct,
                                 vgm_theta_r=vgm_theta_r,
                                 vgm_alpha=vgm_alpha,
                                 vgm_n=vgm_n)


# ==================== VGM 正算 ====================

def test_theta_from_psi_saturated():
    """ψ ≥ 0 → θ = θ_s (饱和/压力水头)"""
    assert vgm_theta_from_psi(0.0, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N) \
        == pytest.approx(L1_THETA_S)
    assert vgm_theta_from_psi(10.0, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N) \
        == pytest.approx(L1_THETA_S)


def test_theta_from_psi_handcalc():
    """VGM 正算手算: θ_s=0.55, θ_r=0.06, α=0.025, n=1.3, ψ=-100cm

    m=1−1/1.3=0.2308; Se=(1+2.5^1.3)^(−0.2308)=4.2913^−0.2308=0.7146
    θ = 0.06 + 0.49×0.7146 = 0.4101 (独立手算, 非代码自证)
    """
    theta = vgm_theta_from_psi(-100.0, L1_THETA_S, L1_THETA_R,
                               L1_ALPHA, L1_N)
    assert theta == pytest.approx(0.4101, abs=0.0005)


def test_theta_from_psi_bounds_and_monotonic():
    """θ ∈ (θ_r, θ_s); 更干 (ψ 更负) → 更小 θ (单调)"""
    d1 = vgm_theta_from_psi(-10.0, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N)
    d2 = vgm_theta_from_psi(-100.0, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N)
    d3 = vgm_theta_from_psi(-1000.0, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N)
    assert L1_THETA_R < d3 < d2 < d1 < L1_THETA_S
    # 幂律尾收敛 (n=1.3 → m=0.23, Se~ψ^-0.3): ψ=-1e6 时 θ 已接近但未达 θ_r;
    # ψ→-∞ 渐近 θ_r (VGM 数学属性, 非缺陷)
    d1e6 = vgm_theta_from_psi(-1e6, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N)
    assert d1e6 == pytest.approx(L1_THETA_R, abs=0.03)
    d1e9 = vgm_theta_from_psi(-1e9, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N)
    assert d1e9 == pytest.approx(L1_THETA_R, abs=0.01)


# ==================== VGM 反算 ====================

def test_calc_psi_roundtrip():
    """calc_psi(vgm_theta_from_psi(ψ)) ≈ ψ (往返恒等)"""
    for psi in (-10.0, -50.0, -100.0, -500.0, -1500.0):
        theta = vgm_theta_from_psi(psi, L1_THETA_S, L1_THETA_R,
                                   L1_ALPHA, L1_N)
        assert calc_psi(theta, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N) \
            == pytest.approx(psi, rel=1e-3)


def test_calc_psi_monotonic():
    """更湿 (大 θ) → 更不吸力 (ψ 更接近 0)"""
    p_wet = calc_psi(0.45, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N)
    p_dry = calc_psi(0.30, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N)
    assert p_dry < p_wet < 0.0


# ==================== Mualem 相对导水率 ====================

def test_calc_Kr_boundaries():
    """K_r(θ_s)=1 (饱和); K_r(θ_r)=0 (残余)"""
    assert calc_Kr(L1_THETA_S, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N) \
        == pytest.approx(1.0)
    assert calc_Kr(L1_THETA_R, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N) \
        == pytest.approx(0.0)


def test_calc_Kr_monotonic():
    """更湿 → K_r 单调增大 (非饱和导水率物理)"""
    ks = [calc_Kr(t, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N)
          for t in (0.10, 0.20, 0.30, 0.40, 0.50)]
    assert ks == sorted(ks)


def test_calc_K_scales_with_ksat():
    """K(θ) = ksat × K_r(θ)"""
    k1 = calc_K(0.30, 12.0, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N)
    k2 = calc_K(0.30, 1.2, L1_THETA_S, L1_THETA_R, L1_ALPHA, L1_N)
    assert k1 == pytest.approx(12.0 / 1.2 * k2)
    # 饱和时 K = ksat
    assert calc_K(L1_THETA_S, 12.0, L1_THETA_S, L1_THETA_R,
                  L1_ALPHA, L1_N) == pytest.approx(12.0)


# ==================== get_vgm_params 三级优先级 (D8) ====================

def test_get_vgm_params_explicit_priority():
    """①layer_overrides 显式 vgm_* 最高优先级"""
    p = _profile(clay_pct=25.0, vgm_theta_r=0.10, vgm_alpha=0.02, vgm_n=1.40)
    assert get_vgm_params(p) == (0.10, 0.02, 1.40)


def test_get_vgm_params_clay_regression():
    """②clay_pct 连续回归: θ_r=0.01+0.002×clay; α=0.04−0.0006×clay; n=1.5−0.008×clay"""
    p = _profile(clay_pct=35.0)
    tr, a, n = get_vgm_params(p)
    assert tr == pytest.approx(0.01 + 0.002 * 35.0)   # 0.08
    assert a == pytest.approx(0.04 - 0.0006 * 35.0)   # 0.019
    assert n == pytest.approx(1.5 - 0.008 * 35.0)     # 1.22


def test_get_vgm_params_fallback():
    """③无 clay_pct → 红壤兜底 (0.08/0.015/1.25)"""
    p = _profile(clay_pct=None)
    assert get_vgm_params(p) == (0.08, 0.015, 1.25)


def test_get_vgm_params_partial_override():
    """部分覆盖: 仅 vgm_n 显式 → n 用显式, 其余走回归 (部分覆盖语义)"""
    p = _profile(clay_pct=25.0, vgm_n=1.45)
    tr, a, n = get_vgm_params(p)
    assert n == pytest.approx(1.45)
    assert tr == pytest.approx(0.06)     # 回归值
    assert a == pytest.approx(0.025)     # 回归值


# ==================== θ↔L/ha 换算 (专家★1) ====================

def test_conversion_hand_values():
    """换算手算: 0.25×20×1e5 = 5e5 L/ha"""
    assert theta_to_water_L(0.25, 20.0) == pytest.approx(5.0e5)
    assert water_L_to_theta(5.0e5, 20.0) == pytest.approx(0.25)


def test_conversion_roundtrip():
    """往返恒等: θ→L→θ (覆盖 4 层 depth 20/20/20/40 与不同 θ)"""
    for depth, theta in zip((20.0, 20.0, 20.0, 40.0),
                            (0.0, 0.20, 0.40, 0.55)):
        water = theta_to_water_L(theta, depth)
        assert water_L_to_theta(water, depth) == pytest.approx(theta)


def test_conversion_boundaries():
    """边界: θ=0 → 0 L; θ=θ_s → 饱和水量; θ=0 时 L→θ 亦为 0"""
    assert theta_to_water_L(0.0, 20.0) == 0.0
    sat = theta_to_water_L(L1_THETA_S, 20.0)
    assert sat == pytest.approx(0.55 * 20.0 * 1e5)   # 1.1e6
    assert water_L_to_theta(0.0, 20.0) == 0.0
    assert water_L_to_theta(sat, 20.0) == pytest.approx(L1_THETA_S)


# ==================== Feddes α(ψ) 四阈值 (Q3/Q9) ====================

H1, H2, H3, H4 = -25.0, -100.0, -800.0, -15000.0


def test_feddes_alpha_piecewise():
    """α(ψ) 四阈值分段 (S1 专家★2): 厌氧0/线性升/平台1/线性降/萎蔫0"""
    assert feddes_alpha(0.0, H1, H2, H3, H4) == 0.0       # 积水/饱和
    assert feddes_alpha(-25.0, H1, H2, H3, H4) == 0.0     # h1 厌氧点
    assert feddes_alpha(-50.0, H1, H2, H3, H4) == pytest.approx(
        (-50 + 25) / (-100 + 25))                         # h1→h2 线性升 0.333
    assert feddes_alpha(-100.0, H1, H2, H3, H4) == 1.0    # h2 最适上界
    assert feddes_alpha(-500.0, H1, H2, H3, H4) == 1.0    # 平台
    assert feddes_alpha(-800.0, H1, H2, H3, H4) == 1.0    # h3 最适下界
    assert feddes_alpha(-2000.0, H1, H2, H3, H4) == pytest.approx(
        (-2000 + 15000) / (-800 + 15000))                 # h3→h4 线性降
    assert feddes_alpha(-15000.0, H1, H2, H3, H4) == 0.0  # h4 永久萎蔫
    assert feddes_alpha(-20000.0, H1, H2, H3, H4) == 0.0  # 更深


def test_feddes_alpha_monotonic_dry_side():
    """旱端 (ψ<h2) 单调下降; 湿端为厌氧斜坡 (0→1, 非单调, Feddes 梯形)"""
    # 旱端: 从最适区到永久萎蔫单调不增
    dry_psis = [-100.0, -400.0, -800.0, -4000.0, -15000.0]
    dry_alphas = [feddes_alpha(p, H1, H2, H3, H4) for p in dry_psis]
    assert all(a1 >= a2 for a1, a2 in zip(dry_alphas, dry_alphas[1:]))
    # 湿端厌氧斜坡: 饱和/积水 α=0, 向 h2 上升 (梯形, 非全局单调)
    assert feddes_alpha(0.0, H1, H2, H3, H4) < feddes_alpha(-50.0, H1, H2, H3, H4)
