"""
模块: climate_forcing.py
功能: 生成逐月气候强迫数据 (降水、温度、土壤CO2分压、PET)
      v0.5.3: 新增 Oudin (2005) PET 估算 (D5/Q3)

输入: 基准气候参数、情景类型、模拟年数
输出: 逐月气候强迫数组

参考文献:
  土壤CO2分压: Brook et al. (1983), Davidson & Trumbore (1995)
  南方降水月分配: 中国气象局气候数据
  PET: Oudin et al. (2005) 仅需月均温+纬度; 华南偏差修正见 v0.5.3水分平衡闭合.txt §6.1
"""

import numpy as np
from typing import Tuple
from src.utils import estimate_soil_pCO2
from src.constants import (DAYS_IN_MONTH, DEFAULT_LATITUDE,
                           DEFAULT_DIURNAL_RANGE, K_OM_PCO2, PCO2_MAX)


def apply_om_pco2(pco2_base: float, om_gkg: float,
                  k_om: float = K_OM_PCO2,
                  pco2_max: float = PCO2_MAX) -> float:
    """OM 矿化产 CO₂ 加性调制: pCO₂_eff = pCO₂_base + k_om×OM_i, 钳制 ≤ pCO₂_max

    D7/Q4/Q10: 加性 (非乘性, 防高 OM 失控, 专家 Q4 修订) + 上限钳制;
    温度独立性 (T 响应仅归 base 项, 不 double-count, 专家★3)。

    参数:
        pco2_base: 层内基准 pCO₂ (atm, 温度驱动)
        om_gkg: 有机质含量 (g/kg, 逐层)
        k_om: OM → ΔpCO₂ 系数 (atm per g/kg)
        pco2_max: 层内 pCO₂ 上限钳制 (atm)
    返回:
        float: 层内有效 pCO₂ (atm)
    """
    return min(pco2_base + k_om * om_gkg, pco2_max)


def _calc_extraterrestrial_radiation(latitude_deg: float,
                                     month: int) -> float:
    """大气顶层辐射 R_a (MJ/m²/day) — Oudin 公用 (v0.6.0 提取, Q9)

    日地距离修正 d_r / 太阳赤纬 δ / 日落时角 ω_s:
      d_r  = 1 + 0.033·cos(2πJ/365)
      δ    = 0.4093·sin(2πJ/365 − 1.39)   (rad)
      ω_s  = arccos(−tanφ·tanδ)
      R_a  = (24×60/π)·G_sc·d_r·[ω_s·sinφ·sinδ + cosφ·cosδ·sinω_s]
             (G_sc=0.0820 MJ m⁻² min⁻¹)
    """
    phi = np.radians(latitude_deg)
    J = 15 + 30 * (month - 1)               # 月中日近似
    dr = 1.0 + 0.033 * np.cos(2.0 * np.pi * J / 365.0)
    delta = 0.4093 * np.sin(2.0 * np.pi * J / 365.0 - 1.39)
    cos_ws = np.clip(-np.tan(phi) * np.tan(delta), -1.0, 1.0)
    ws = np.arccos(cos_ws)
    return (24.0 * 60.0 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(delta)
        + np.cos(phi) * np.cos(delta) * np.sin(ws))


def calc_pet_oudin(t_mean_c: float, latitude_deg: float, month: int) -> float:
    """Oudin (2005) 日 PET (mm/day)

    仅需月均温与站点纬度 (v0.5.3 PET 主通道, D5):
      PET = R_a×1000/(λ·ρ_w) × max(0, (T+5)/100)
             (λ=2.45 MJ/kg 汽化潜热, ρ_w=1000 kg/m³ → R_a/2.45 mm/day)

    参数:
        t_mean_c: 月均温 (°C)
        latitude_deg: 站点纬度 (°N, 正值)
        month: 月份 1~12 (月中日 J=15+30×(m−1))
    返回:
        float: 日 PET (mm/day)
    """
    Ra = _calc_extraterrestrial_radiation(latitude_deg, month)
    # R_a (MJ/m²/day) → 蒸散水柱 (mm/day): ×1000/(λ·ρ_w), λ=2.45 MJ/kg,
    # ρ_w=1000 kg/m³ → 0.4082; 温度阈值 (T+5)/100, 冬季休眠自动归零
    return float((Ra * 1000.0 / 2450.0) * max(0.0, (t_mean_c + 5.0) / 100.0))


def calc_pet(t_mean_c: float, latitude_deg: float, month: int,
             method: str = 'oudin',
             diurnal_range_deg: float = DEFAULT_DIURNAL_RANGE) -> float:
    """PET 单入口分派 (v0.6.0, Q8/Q9, Oudin 精度增强模式)

    三种方法共享同一入口, 输出均为日 PET (mm/day), 下游 ET 扣除
    (LayerCascade) 无需知道方法来源:

      - "oudin" (默认): Oudin (2005), 仅需月均温+纬度 (calc_pet_oudin)
      - "hargreaves": Hargreaves-Samani (1985),
          PET = 0.0023 × R_a × (T_mean+17.8) × √(T_max−T_min)
          T_max = T_mean + range/2, T_min = T_mean − range/2 (config 日较差)
          R_a 复用 Oudin 日地/赤纬/时角计算 (_calc_extraterrestrial_radiation)
      - "hargreaves_enhanced": v0.6.0 只预留枚举 + 显式报错
          (12 值日较差 + 外部气候文件内插数据管线留 v0.7.0)

    参数:
        t_mean_c: 月均温 (°C)
        latitude_deg: 站点纬度 (°N, 正值)
        month: 月份 1~12
        method: pet 方法 ('oudin' | 'hargreaves' | 'hargreaves_enhanced')
        diurnal_range_deg: 日较差 T_max−T_min (°C, hargreaves 用, 默认 8.0)
    返回:
        float: 日 PET (mm/day)
    """
    if method == 'oudin':
        return calc_pet_oudin(t_mean_c, latitude_deg, month)
    if method == 'hargreaves':
        # Hargreaves-Samani (1985): 经验系数 0.0023 (含单位换算), PET 单位 mm/day
        Ra = _calc_extraterrestrial_radiation(latitude_deg, month)
        t_max = t_mean_c + diurnal_range_deg / 2.0
        t_min = t_mean_c - diurnal_range_deg / 2.0
        return float(0.0023 * Ra * (t_mean_c + 17.8)
                     * (t_max - t_min) ** 0.5)
    if method == 'hargreaves_enhanced':
        raise NotImplementedError(
            "pet_method='hargreaves_enhanced' 为 v0.7.0 预留 "
            "(12 值日较差 + 外部气候文件内插数据管线); v0.6.0 仅枚举+报错")
    raise ValueError(f"未知 pet_method: {method}")


class ClimateForcing:
    """气候强迫生成器"""

    # 南方红壤区降水月分配比例 (参考中国南方气候特征)
    # 4-9月为雨季(占~75%), 10-3月为旱季(占~25%)
    MONTHLY_PRECIP_FRACTION = np.array([
        0.03, 0.04, 0.06, 0.10, 0.14, 0.15,
        0.13, 0.12, 0.08, 0.06, 0.05, 0.04
    ])  # 总计 ≈ 1.0

    # 月平均温度偏差 (相对于年均温)
    # 南方亚热带气候: 冬暖夏热
    MONTHLY_TEMP_ANOMALY = np.array([
        -5.0, -3.0, 0.0, 3.0, 5.0, 6.0,
        6.5, 6.0, 4.0, 1.0, -2.0, -4.0
    ])  # °C

    def __init__(self, base_annual_precip: float, base_annual_temp: float,
                 pCO2_ref: float, T_ref: float, beta: float,
                 n_years: int, scenario: str = 'natural',
                 precip_increase_rate: float = 0.02,
                 temp_increase_rate: float = 0.05,
                 latitude: float = DEFAULT_LATITUDE,
                 pet_method: str = 'oudin',
                 pet_monthly_climate=None,
                 pet_correction_factor=None,
                 diurnal_range_deg: float = DEFAULT_DIURNAL_RANGE):
        """
        参数:
            base_annual_precip: 基准年降水量 (mm)
            base_annual_temp: 基准年平均温度 (°C)
            pCO2_ref: 参考CO2分压 (atm)
            T_ref: 参考温度 (°C)
            beta: CO2温度响应系数 (1/°C)
            n_years: 模拟年数
            scenario: 情景类型
            precip_increase_rate: 降水年增加比例
            temp_increase_rate: 温度年增加量 (°C)
            latitude: v0.5.3: 站点纬度 (°N, Oudin PET 必需, D5)
            pet_method: v0.5.3: "oudin" (主) | "fixed" (pet_monthly_climate 兜底)
                       v0.6.0: "hargreaves" | "hargreaves_enhanced" (预留报错)
            pet_monthly_climate: v0.5.3: 12 值固定气候态月 PET (mm/month, 提供时优先)
            pet_correction_factor: v0.5.3: 12 值月度修正系数 (华南夏低冬高偏差, 默认恒等)
            diurnal_range_deg: v0.6.0: 日较差 T_max−T_min (°C, hargreaves 用,
                默认 8.0, config 可配)
        """
        self.base_annual_precip = base_annual_precip
        self.base_annual_temp = base_annual_temp
        self.pCO2_ref = pCO2_ref
        self.T_ref = T_ref
        self.beta = beta
        self.n_years = n_years
        self.scenario = scenario
        self.precip_increase_rate = precip_increase_rate
        self.temp_increase_rate = temp_increase_rate
        self.latitude = latitude
        self.pet_method = pet_method
        self.pet_monthly_climate = pet_monthly_climate
        self.pet_correction_factor = pet_correction_factor
        self.diurnal_range_deg = diurnal_range_deg

        # 生成时间序列
        self.monthly_precip = self._generate_precip()
        self.monthly_temp = self._generate_temp()
        self.monthly_pCO2 = self._generate_pCO2()
        # v0.5.3: 逐月 PET (n_years×12, Oudin 正算或固定气候态)
        self.monthly_pet = self._generate_pet()

    def _generate_precip(self) -> np.ndarray:
        """生成逐月降水序列 (n_years × 12)"""
        precip = np.zeros((self.n_years, 12))

        for year in range(self.n_years):
            # 降水年增加 (情景3)
            if self.scenario == 'precip_increase':
                annual_factor = (1.0 + self.precip_increase_rate) ** year
            else:
                annual_factor = 1.0

            annual_precip = self.base_annual_precip * annual_factor

            for month in range(12):
                precip[year, month] = annual_precip * \
                    self.MONTHLY_PRECIP_FRACTION[month]

        return precip

    def _generate_temp(self) -> np.ndarray:
        """生成逐月温度序列 (n_years × 12)"""
        temp = np.zeros((self.n_years, 12))

        for year in range(self.n_years):
            # 温度年增加 (情景4)
            if self.scenario == 'temp_increase':
                temp_offset = self.temp_increase_rate * year
            else:
                temp_offset = 0.0

            for month in range(12):
                temp[year, month] = self.base_annual_temp + \
                    self.MONTHLY_TEMP_ANOMALY[month] + temp_offset

        return temp

    def _generate_pCO2(self) -> np.ndarray:
        """生成逐月土壤CO2分压序列

        公式: pCO2(T) = pCO2_ref × exp[β × (T - T_ref)]
        计算复用 utils.estimate_soil_pCO2 (单一事实来源, T04)
        参考文献:
          Brook G.A. et al. (1983). Earth Surface Processes and Landforms.
          Davidson E.A. & Trumbore S.E. (1995). Tellus B, 47(5), 550-565.
        """
        pCO2 = np.zeros((self.n_years, 12))

        for year in range(self.n_years):
            for month in range(12):
                T = self.monthly_temp[year, month]
                pCO2[year, month] = estimate_soil_pCO2(
                    T, self.pCO2_ref, self.T_ref, self.beta)

        return pCO2

    def _generate_pet(self) -> np.ndarray:
        """生成逐月 PET 序列 (n_years × 12, v0.5.3, D5)

        v0.6.0 (Q9): 单入口 calc_pet 分派 (pet_method 决定);
        Oudin 主通道: PET = calc_pet_oudin(T, lat, month) × 当月天数 × 修正系数;
        Hargreaves: PET = calc_pet(..., method='hargreaves') (日较差驱动);
        固定气候态兜底: pet_monthly_climate (12 值) 提供时优先 (仍乘月度修正)。
        """
        pet = np.zeros((self.n_years, 12))
        cf = (self.pet_correction_factor if self.pet_correction_factor
              else [1.0] * 12)
        for year in range(self.n_years):
            for month in range(12):
                if self.pet_monthly_climate is not None:
                    pet[year, month] = self.pet_monthly_climate[month] * cf[month]
                else:
                    T = self.monthly_temp[year, month]
                    daily = calc_pet(T, self.latitude, month + 1,
                                     method=self.pet_method,
                                     diurnal_range_deg=self.diurnal_range_deg)
                    pet[year, month] = daily * DAYS_IN_MONTH[month] * cf[month]
        return pet

    def get_monthly_forcing(self, year: int, month: int) -> dict:
        """获取指定年月的强迫数据

        参数:
            year: 年 (0-indexed)
            month: 月 (0-indexed, 0=1月)

        返回:
            dict: 包含 precip, temp, pCO2, pet (v0.5.3)
        """
        return {
            'precip': self.monthly_precip[year, month],
            'temp': self.monthly_temp[year, month],
            'pCO2': self.monthly_pCO2[year, month],
            'pet': self.monthly_pet[year, month],
        }

    def print_summary(self):
        """打印气候强迫摘要"""
        print("\n气候强迫摘要:")
        print(f"  模拟年数: {self.n_years}")
        print(f"  基准年降水: {self.base_annual_precip} mm")
        print(f"  基准年均温: {self.base_annual_temp} °C")
        print(f"  情景: {self.scenario}")
        print(f"  第1年年总降水: {self.monthly_precip[0].sum():.1f} mm")
        print(f"  最后一年总降水: {self.monthly_precip[-1].sum():.1f} mm")
        print(f"  第1年年均温: {self.monthly_temp[0].mean():.1f} °C")
        print(f"  最后一年均温: {self.monthly_temp[-1].mean():.1f} °C")
        print(f"  pCO2范围: [{self.monthly_pCO2.min():.4f}, "
              f"{self.monthly_pCO2.max():.4f}] atm")
