"""
模块: climate_forcing.py
功能: 生成逐月气候强迫数据 (降水、温度、土壤CO2分压)

输入: 基准气候参数、情景类型、模拟年数
输出: 逐月气候强迫数组

参考文献:
  土壤CO2分压: Brook et al. (1983), Davidson & Trumbore (1995)
  南方降水月分配: 中国气象局气候数据
"""

import numpy as np
from typing import Tuple
from src.utils import estimate_soil_pCO2


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
                 temp_increase_rate: float = 0.05):
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

        # 生成时间序列
        self.monthly_precip = self._generate_precip()
        self.monthly_temp = self._generate_temp()
        self.monthly_pCO2 = self._generate_pCO2()

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

    def get_monthly_forcing(self, year: int, month: int) -> dict:
        """获取指定年月的强迫数据

        参数:
            year: 年 (0-indexed)
            month: 月 (0-indexed, 0=1月)

        返回:
            dict: 包含 precip, temp, pCO2
        """
        return {
            'precip': self.monthly_precip[year, month],
            'temp': self.monthly_temp[year, month],
            'pCO2': self.monthly_pCO2[year, month],
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
