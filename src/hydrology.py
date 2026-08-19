"""
模块: hydrology.py
功能: 逐层土壤水文物理模型 (v0.5.2)

将模型从"全局入渗系数"升级为物理水文过程:
  1. 随机日降雨生成: 每月场次 U(4,12), 每场降水指数分布拆分 (月总量守恒),
     单场历时 2h, 种子可复现 (默认 42, config 可配)
  2. Green-Ampt 入渗 (v0.5.2, 替代 Horton + surface_coeff):
     累积入渗能力 F 由隐式方程 F − ψ_f·Δθ·ln(1+F/(ψ_f·Δθ)) = K_s·t 解出,
     降雨强度 > 入渗能力 → 超渗产流自然产生; K_s 用基质导水率 ksat_surface
  3. 层间级联: 每层持水 (50%→100% 饱和增量), ksat 层间排水上限,
     stored_water 跨月累积, 超饱和溢出计入径流

参考: Green & Ampt (1911); Rawls et al. (1983); Horton (1940, 已废弃)。
"""

import numpy as np
from src.logging_config import get_logger
from src.constants import (GREEN_AMPT_PSI_F_MM, GREEN_AMPT_NEWTON_TOL,
                           GREEN_AMPT_NEWTON_MAX_ITER,
                           FEDDES_H1, FEDDES_H2, FEDDES_H3, FEDDES_H4,
                           ROOT_FRACTION_4LAYER)
from src.vgm import theta_to_water_L, water_L_to_theta

logger = get_logger("hydrology")

# ---- 水文默认常量 (Q19 收敛) ----
EVENT_HOURS = 2.0                   # 单场降雨历时 (h)
N_EVENTS_MIN = 4                    # 每月最少场次
N_EVENTS_MAX = 12                   # 每月最多场次
PARTICLE_DENSITY = 2.65             # 土壤颗粒密度 (g/cm³), 孔隙度反推容重
DEFAULT_SEED = 42                   # 随机降雨默认种子


def generate_rainfall(monthly_precip_mm: float, year: int, month: int,
                      seed: int = DEFAULT_SEED,
                      n_events_range=(N_EVENTS_MIN, N_EVENTS_MAX)) -> list:
    """随机生成当月场次降雨 (mm), 月总量守恒, 同 seed 可复现

    场次数 ~ U(min, max); 每场降水按指数权重分配月降水总量
    (指数分布 → 少数大雨 + 多数小雨, 近似次降雨强度分布)。

    返回:
        list[float]: 每场降水量 (mm), Σ = monthly_precip_mm
    """
    rng = np.random.default_rng(seed + year * 12 + month)
    n = int(rng.integers(n_events_range[0], n_events_range[1] + 1))
    weights = rng.exponential(size=n)
    events = monthly_precip_mm * weights / weights.sum()
    return [float(e) for e in events]


def solve_green_ampt_F(Ks_mm_h: float, psi_f_dtheta_mm: float,
                       t_h: float) -> float:
    """牛顿迭代解 Green-Ampt 累积入渗隐式方程

    F - ψ_f·Δθ·ln(1 + F/(ψ_f·Δθ)) = K_s·t

    参数:
        Ks_mm_h: 饱和导水率 K_s (mm/h)
        psi_f_dtheta_mm: ψ_f·Δθ (mm), 湿润锋吸力 × 含水量差
        t_h: 历时 (h)
    返回:
        float: 累积入渗能力 F (mm)。饱和时 (Δθ→0) 退化为 F = K_s·t。
    """
    A = max(psi_f_dtheta_mm, 1e-6)      # 防除零; 饱和退化由 limit 保证
    rhs = Ks_mm_h * t_h
    F = rhs + 0.5 * A                    # 初始猜测: 无吸力项 + 吸力修正
    for _ in range(GREEN_AMPT_NEWTON_MAX_ITER):
        g = F - A * np.log1p(F / A) - rhs
        gp = F / (A + F)                 # dg/dF = 1 - A/(A+F) = F/(A+F)
        dF = g / gp
        F -= dF
        if abs(dF) < GREEN_AMPT_NEWTON_TOL:
            break
    return max(F, rhs)                   # 物理下界: 至少 K_s·t


def green_ampt_infiltration(precip_mm: float, Ks_cm_day: float,
                            psi_f_mm: float = GREEN_AMPT_PSI_F_MM,
                            theta_s: float = 0.5, theta_i: float = 0.25,
                            hours: float = EVENT_HOURS) -> tuple:
    """Green-Ampt 单场入渗 (mm) → (infiltration_mm, runoff_mm)

    物理: 降雨强度 i = precip/hours; 累积入渗能力 F(t) 由隐式方程解出;
    入渗 = min(场降水, F); 超出部分自然成为地表径流 (Hortonian runoff)。
    彻底移除 Horton 的 surface_coeff 人为系数 (v0.5.2, spec 43)。

    参数:
        precip_mm: 单场降水量 (mm)
        Ks_cm_day: 基质导水率 K_s (cm/day, = ksat_surface)
        psi_f_mm: 湿润锋吸力水头 (mm, Rawls 红壤默认 150)
        theta_s: 饱和含水量 (≈ 孔隙度)
        theta_i: 初始含水量
        hours: 场次历时 (h)
    返回:
        (infiltration_mm, runoff_mm): 单场入渗/超渗径流
    """
    Ks_mm_h = Ks_cm_day * 10.0 / 24.0   # cm/day → mm/h
    dtheta = max(0.0, theta_s - theta_i)
    F = solve_green_ampt_F(Ks_mm_h, psi_f_mm * dtheta, hours)
    infiltration = min(precip_mm, F)
    return infiltration, precip_mm - infiltration


def monthly_hydrology(monthly_precip_mm: float, year: int, month: int,
                      surface_profile, seed: int = DEFAULT_SEED,
                      theta_i: float | None = None):
    """月度入渗-径流分配 (表层 Green-Ampt, v0.5.2)

    逐场 Green-Ampt 入渗: 降雨强度 > 入渗能力 → 超渗产流自然产生
    (彻底移除 Horton 的 surface_coeff 人为系数)。

    参数:
        monthly_precip_mm: 月降水量 (mm)
        year/month: 年/月 (0-indexed, 随机降雨种子派生)
        surface_profile: 表层 SoilProfile (含 ksat_surface/porosity)
        seed: 随机降雨种子
        theta_i: 表层初始体积含水量 (None → 0.5×θ_s, 初始 50% 饱和)
    返回:
        (infiltration_mm, runoff_mm, events): 月入渗/月径流/场次列表
    """
    events = generate_rainfall(monthly_precip_mm, year, month, seed)
    theta_s = surface_profile.porosity
    if theta_i is None:
        theta_i = 0.5 * theta_s
    infiltration = sum(green_ampt_infiltration(
        p, surface_profile.ksat_surface, theta_s=theta_s, theta_i=theta_i)[0]
        for p in events)
    infiltration = min(infiltration, monthly_precip_mm)
    runoff = monthly_precip_mm - infiltration
    return infiltration, runoff, events


class LayerCascade:
    """层间级联渗漏 (v0.5.0): 持水 + Ksat 限制 + 跨月滞水

    每层:
      sat   = φ × depth_cm × 1e5  (L/ha, 饱和持水量)
      space = 0.5 × sat           (50%→100% 饱和增量, 初始溶液体积=50%饱和)
      来水   = 上层排水 + 本层 stored_water
      可排水 = max(0, 来水 − space)
      排水   = min(可排水, Ksat×10000×天数×10)  (Ksat cm/day → L/ha/月)
      滞留   = 来水 − 排水; 超饱和部分 (retained > sat) 溢出计入径流
    最底层排水 = 深层排水流失。
    """

    def __init__(self, profiles: list, n_days: int = 30):
        self.profiles = profiles
        self.n_days = n_days

    def saturation_capacity(self, i: int) -> float:
        """第 i 层饱和持水量 (L/ha) = φ × depth_cm × 1e5"""
        p = self.profiles[i]
        return p.porosity * p.effective_depth * 1e5

    def run(self, inflow_L: float, states: list):
        """执行级联渗漏

        参数:
            inflow_L: 最上层入渗水量 (L/ha)
            states: List[SoilState] (逐层状态, theta 就地更新)
        返回:
            (drains, runoff_extra, deep_drainage)
            - drains: 各层排水量 (L/ha), 长度 = n_layers
            - runoff_extra: 超饱和溢出总量 (L/ha)
            - deep_drainage: 最底层排水 (L/ha)
        """
        drains = []
        runoff_extra = 0.0
        inflow = inflow_L
        for i, state in enumerate(states):
            p = self.profiles[i]
            sat = self.saturation_capacity(i)
            space = 0.5 * sat
            # v0.5.3: stored_water → theta 状态迁移 (Q1/Q7), L/ha 由 vgm 换算
            # (50% 饱和持水语义保留至工单 52 的 LayerCascade 重构)
            stored = theta_to_water_L(state.theta, p.effective_depth)
            avail = inflow + stored
            drainable = max(0.0, avail - space)
            ksat_cap = p.ksat * 10000.0 * self.n_days * 10.0
            drain = min(drainable, ksat_cap)
            retained = avail - drain
            overflow = max(0.0, retained - sat)
            retained = min(retained, sat)
            state.theta = water_L_to_theta(retained, p.effective_depth)
            runoff_extra += overflow
            drains.append(drain)
            inflow = drain
        return drains, runoff_extra, drains[-1]


# ---- v0.5.3 Feddes ET (Q3/Q9, spec 49 §3) ----

def apply_feddes_et(states, pet_mm: float, profiles, root_weights=None):
    """Feddes 根系吸水 ET 扣除 (逐层独立, 无跨层补偿, Q9)

    物理: AET_i = PET × f_root,i × α(ψ_i); ψ 由 VGM 反算 (ψ 版 Feddes)。
    - 逐层独立: 某层需求不足 (α 或水量) 即丢弃, 不向深层再分配 (Q9=A);
    - 亏缺丢弃: 需求超出可提取水量 → AET 截断, 差额计入 et_deficit_mm (Q3b=B1);
    - α=0 钳制: θ ≤ θ(ψ=h4) 永久萎蔫后 AET=0, θ 不取负 (天然钳制)。

    参数:
        states: List[SoilState] (theta 就地更新)
        pet_mm: 本月 PET (mm, 已含月度修正系数)
        profiles: List[SoilProfile] (逐层, 含 porosity/clay_pct/vgm_*)
        root_weights: 根系分布权重 (默认 60/30/10/0, Σ=1)
    返回:
        (aet_mm_list, et_deficit_mm): 各层实际蒸散 (mm) + 亏缺总量 (mm)
    """
    from src.vgm import (calc_psi, feddes_alpha, get_vgm_params,
                         vgm_theta_from_psi)
    if root_weights is None:
        root_weights = ROOT_FRACTION_4LAYER
    aet_list = []
    et_deficit = 0.0
    for i, state in enumerate(states):
        p = profiles[i]
        depth = p.effective_depth
        theta_r, alpha, n = get_vgm_params(p)
        # θ → ψ (VGM 反算) → Feddes α(ψ)
        psi = calc_psi(state.theta, p.porosity, theta_r, alpha, n)
        a_stress = feddes_alpha(psi, FEDDES_H1, FEDDES_H2,
                                FEDDES_H3, FEDDES_H4)
        demand_mm = pet_mm * root_weights[i] * a_stress
        # 可提取水量上限: θ ≥ θ(ψ=h4) (永久萎蔫以下不可提取), mm 水柱
        theta_wp = vgm_theta_from_psi(FEDDES_H4, p.porosity,
                                      theta_r, alpha, n)
        avail_mm = max(0.0, (state.theta - theta_wp) * depth * 10.0)
        aet_mm = min(demand_mm, avail_mm)
        et_deficit += max(0.0, demand_mm - aet_mm)
        # Δθ = AET_mm / (depth_cm × 10) (mm 水柱 → 体积含水量)
        state.theta = max(0.0, state.theta - aet_mm / (depth * 10.0))
        aet_list.append(aet_mm)
    return aet_list, et_deficit
