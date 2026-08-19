"""
模块: vgm.py (v0.5.3 新增)
功能: van Genuchten-Mualem 土壤水分特征纯函数 (决策 D8/Q2/Q11)

  - vgm_theta_from_psi: VGM 正算 ψ → θ (初始 θ / θ_FC 用)
  - calc_psi:          VGM 反算 θ → ψ (Feddes α(ψ) / 层间水势用)
  - calc_Kr / calc_K:  Mualem 相对导水率 K_r(θ) (l=0.5 固定, 层间达西通量用)
  - get_vgm_params:    三级参数优先级 ①layer_overrides 显式 ②clay_pct 回归 ③红壤兜底
  - theta_to_water_L / water_L_to_theta: θ ↔ L/ha 换算 (规范状态 θ 的唯一换算出口,
    专家★1: 往返恒等, 不依赖孔隙度)

参考: van Genuchten (1980); Mualem (1976); Saxton & Rawls (2006);
      VGM参数化方案.txt (D8 定案)。
"""

from src.constants import (VGM_CLAY_THETA_R_A, VGM_CLAY_THETA_R_B,
                           VGM_CLAY_ALPHA_A, VGM_CLAY_ALPHA_B,
                           VGM_CLAY_N_A, VGM_CLAY_N_B,
                           VGM_FALLBACK_THETA_R, VGM_FALLBACK_ALPHA,
                           VGM_FALLBACK_N, VGM_MUALEM_L)


def vgm_theta_from_psi(psi_cm: float, theta_s: float, theta_r: float,
                       alpha: float, n: float) -> float:
    """VGM 正算: 基质势 ψ (cm) → 体积含水量 θ (m³/m³)

    Se = (1 + (α·|ψ|)^n)^(−m), m = 1−1/n;  θ = θ_r + (θ_s−θ_r)·Se
    ψ ≥ 0 (饱和/压力水头) → θ = θ_s。

    参数:
        psi_cm: 基质势 (cm, 负值吸力)
        theta_s: 饱和含水量 (≡ porosity, D8)
        theta_r: 残余含水量
        alpha: 进气值倒数 (1/cm)
        n: 孔隙分布指数 (>1)
    """
    if psi_cm >= 0:
        return theta_s
    m = 1.0 - 1.0 / n
    se = (1.0 + (alpha * abs(psi_cm)) ** n) ** (-m)
    return theta_r + (theta_s - theta_r) * se


def calc_psi(theta: float, theta_s: float, theta_r: float,
             alpha: float, n: float) -> float:
    """VGM 反算: θ → ψ (cm, 负值吸力)

    Se 截断到 (0,1) 防数值溢出; |ψ| = (Se^(−1/m) − 1)^(1/n) / α。
    """
    m = 1.0 - 1.0 / n
    se = max(1e-6, min(0.999999, (theta - theta_r) / (theta_s - theta_r)))
    h = (se ** (-1.0 / m) - 1.0) ** (1.0 / n) / alpha
    return -h


def calc_Kr(theta: float, theta_s: float, theta_r: float,
            alpha: float, n: float, l: float = VGM_MUALEM_L) -> float:
    """Mualem 相对导水率 K_r(θ) (l=0.5 固定, D8)

    K_r = Se^l · [1 − (1 − Se^(1/m))^m]²;  Se=(θ−θ_r)/(θ_s−θ_r)
    θ→θ_s → K_r→1 (饱和); θ→θ_r → K_r→0。
    """
    m = 1.0 - 1.0 / n
    se = (theta - theta_r) / (theta_s - theta_r)
    if se <= 0.0:
        return 0.0
    se = min(se, 1.0)
    return se ** l * (1.0 - (1.0 - se ** (1.0 / m)) ** m) ** 2


def calc_K(theta: float, ksat: float, theta_s: float, theta_r: float,
           alpha: float, n: float, l: float = VGM_MUALEM_L) -> float:
    """非饱和导水率 K(θ) = K_s·K_r(θ) (cm/day)

    参数:
        ksat: 饱和导水率 (cm/day, 层间排水 ksat_i)
    """
    return ksat * calc_Kr(theta, theta_s, theta_r, alpha, n, l)


def get_vgm_params(profile):
    """VGM 参数三级优先级 (D8): ①显式 vgm_* → ②clay_pct 回归 → ③红壤兜底

    参数:
        profile: 含属性 clay_pct / vgm_theta_r / vgm_alpha / vgm_n
            (SoilProfile; None=未显式配置, 部分覆盖语义逐参数独立)
    返回:
        (theta_r, alpha, n)
    """
    clay = getattr(profile, 'clay_pct', None)
    if clay is not None and clay > 0:
        # ②基于 clay_pct 的连续回归 (Saxton & Rawls 2006 + 红壤修正,
        # 避免 Carsel & Parrish 离散查表突变, VGM参数化方案.txt)
        theta_r = VGM_CLAY_THETA_R_A + VGM_CLAY_THETA_R_B * clay
        alpha = VGM_CLAY_ALPHA_A + VGM_CLAY_ALPHA_B * clay
        n = VGM_CLAY_N_A + VGM_CLAY_N_B * clay
    else:
        # ③华南红壤兜底
        theta_r, alpha, n = (VGM_FALLBACK_THETA_R,
                             VGM_FALLBACK_ALPHA, VGM_FALLBACK_N)
    # ①layer_overrides 显式覆盖 (逐参数, 部分覆盖语义)
    if getattr(profile, 'vgm_theta_r', None) is not None:
        theta_r = profile.vgm_theta_r
    if getattr(profile, 'vgm_alpha', None) is not None:
        alpha = profile.vgm_alpha
    if getattr(profile, 'vgm_n', None) is not None:
        n = profile.vgm_n
    return theta_r, alpha, n


def theta_to_water_L(theta: float, depth_cm: float) -> float:
    """θ (m³/m³) → 层内水量 (L/ha): θ × depth_cm × 1e5

    推导: V_water(m³)=θ×depth_m×1e4 m²; L = ×1000;
         = θ × depth_cm/100 × 1e4 × 1000 = θ × depth_cm × 1e5。
    """
    return theta * depth_cm * 1e5


def water_L_to_theta(water_L: float, depth_cm: float) -> float:
    """层内水量 (L/ha) → θ (m³/m³): water_L / (depth_cm × 1e5)"""
    return water_L / (depth_cm * 1e5)
