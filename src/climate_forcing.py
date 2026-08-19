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
from src.constants import (DAYS_IN_MONTH, DEFAULT_LATITUDE)


def calc_pet_oudin(t_mean_c: float, latitude_deg: float, month: int) -> float:
    """Oudin (2005) 日 PET (mm/day)

    仅需月均温与站点纬度 (v0.5.3 PET 主通道, D5):
      d_r  = 1 + 0.033·cos(2πJ/365)                      (日地距离修正)
      δ    = 0.4093·sin(2πJ/365 − 1.39)                  (太阳赤纬, rad)
      ω_s  = arccos(−tanφ·tanδ)                          (日落时角)
      R_a  = (24×60/π)·G_sc·d_r·[ω_s·sinφ·sinδ + cosφ·cosδ·sinω_s]
             (G_sc=0.0820 MJ m⁻² min⁻¹, 大气顶层辐射 MJ m⁻² day⁻¹)
      PET  = R_a×1000/(λ·ρ_w) × max(0, (T+5)/100)
             (λ=2.45 MJ/kg 汽化潜热, ρ_w=1000 kg/m³ → R_a/2.45 mm/day)

    参数:
        t_mean_c: 月均温 (°C)
        latitude_deg: 站点纬度 (°N, 正值)
        month: 月份 1~12 (月中日 J=15+30×(m−1))
    返回:
        float: 日 PET (mm/day)
    """
    phi = np.radians(latitude_deg)
    J = 15 + 30 * (month - 1)               # 月中日近似
    dr = 1.0 + 0.033 * np.cos(2.0 * np.pi * J / 365.0)
    delta = 0.4093 * np.sin(2.0 * np.pi * J / 365.0 - 1.39)
    cos_ws = np.clip(-np.tan(phi) * np.tan(delta), -1.0, 1.0)
    ws = np.arccos(cos_ws)
    Ra = (24.0 * 60.0 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(delta)
        + np.cos(phi) * np.cos(delta) * np.sin(ws))
    # R_a (MJ/m²/day) → 蒸散水柱 (mm/day): ×1000/(λ·ρ_w), λ=2.45 MJ/kg,
    # ρ_w=1000 kg/m³ → 0.4082; 温度阈值 (T+5)/100, 冬季休眠自动归零
    return float((Ra * 1000.0 / 2450.0) * max(0.0, (t_mean_c + 5.0) / 100.0))


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
                 pet_correction_factor=None):
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
            pet_monthly_climate: v0.5.3: 12 值固定气候态月 PET (mm/month, 提供时优先)
            pet_correction_factor: v0.5.3: 12 值月度修正系数 (华南夏低冬高偏差, 默认恒等)
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

        Oudin 主通道: PET = calc_pet_oudin(T, lat, month) × 当月天数 × 修正系数;
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
                    daily = calc_pet_oudin(T, self.latitude, month + 1)
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
