"""
模块: hydrology.py
功能: 逐层土壤水文盒子模型 (v0.5.0)

将模型从"全局入渗系数"升级为物理水文过程:
  1. 随机日降雨生成: 每月场次 U(4,12), 每场降水指数分布拆分 (月总量守恒),
     单场历时 2h, 种子可复现 (默认 42, config 可配)
  2. Horton 入渗: 单场入渗能力 A = fc×T + (f0−fc)/k·(1−e^(−kT)) (k=5/h),
     入渗 = min(场降水×表层入渗系数 0.75, A); 降水耗尽则全入渗
  3. 层间级联: 每层持水 (50%→100% 饱和增量), Ksat 限制渗漏,
     stored_water 跨月累积, 超饱和溢出计入径流

参考: Horton (1940) 入渗曲线; 经典土壤水文盒子近似。
"""

import numpy as np
from src.logging_config import get_logger
from src.constants import DEFAULT_SURFACE_INFILTRATION_COEFF

logger = get_logger("hydrology")

# ---- 水文默认常量 (Q19 收敛) ----
HORTON_DECAY_K_PER_H = 5.0          # Horton 衰减系数 (/h)
EVENT_HOURS = 2.0                   # 单场降雨历时 (h)
N_EVENTS_MIN = 4                    # 每月最少场次
N_EVENTS_MAX = 12                   # 每月最多场次
PARTICLE_DENSITY = 2.65             # 土壤颗粒密度 (g/cm³), 孔隙度反推容重
DEFAULT_SEED = 42                   # 随机降雨默认种子
# 表层入渗上限系数默认来自 constants (v0.5.1 起 config 驱动: simulation.surface_infiltration_coeff)


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


def horton_event_infiltration(precip_mm: float, f0_mm_min: float,
                              fc_mm_min: float,
                              k_per_h: float = HORTON_DECAY_K_PER_H,
                              hours: float = EVENT_HOURS,
                              surface_coeff: float = DEFAULT_SURFACE_INFILTRATION_COEFF) -> float:
    """Horton 单场入渗量 (mm)

    A = fc×T + (f0−fc)/k·(1−e^(−kT))  (k: /h, T: h)
    入渗 = min(场降水×surface_coeff, A); 场降水×coeff ≤ A → 全入渗 (降水耗尽)。

    参数:
        precip_mm: 单场降水量 (mm)
        f0_mm_min: 初渗率 (mm/min)
        fc_mm_min: 稳渗率 (mm/min)
        surface_coeff: 表层入渗上限系数 (v0.5.1 config 驱动, 默认 0.75)
    返回:
        float: 单场入渗量 (mm)
    """
    k_min = k_per_h / 60.0
    t_min = hours * 60.0
    capacity = (fc_mm_min * t_min
                + (f0_mm_min - fc_mm_min) / k_min
                * (1.0 - np.exp(-k_min * t_min)))
    available = precip_mm * surface_coeff
    return min(available, capacity)


def monthly_hydrology(monthly_precip_mm: float, year: int, month: int,
                      surface_profile, seed: int = DEFAULT_SEED,
                      surface_coeff: float = DEFAULT_SURFACE_INFILTRATION_COEFF):
    """月度入渗-径流分配 (表层 Horton)

    参数:
        surface_profile: 表层 SoilProfile (含 infiltration_initial/steady)
        seed: 随机降雨种子
        surface_coeff: 表层入渗上限系数 (v0.5.1 config 驱动)
    返回:
        (infiltration_mm, runoff_mm, events): 月入渗/月径流/场次列表
    """
    events = generate_rainfall(monthly_precip_mm, year, month, seed)
    f0 = surface_profile.infiltration_initial
    fc = surface_profile.infiltration_steady
    infiltration = sum(horton_event_infiltration(
        p, f0, fc, surface_coeff=surface_coeff) for p in events)
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
            states: List[SoilState] (逐层状态, stored_water 就地更新)
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
            avail = inflow + state.stored_water
            drainable = max(0.0, avail - space)
            ksat_cap = p.ksat * 10000.0 * self.n_days * 10.0
            drain = min(drainable, ksat_cap)
            retained = avail - drain
            overflow = max(0.0, retained - sat)
            retained = min(retained, sat)
            state.stored_water = retained
            runoff_extra += overflow
            drains.append(drain)
            inflow = drain
        return drains, runoff_extra, drains[-1]
