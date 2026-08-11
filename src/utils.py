"""
模块: utils.py
功能: 工具函数
"""

import numpy as np
from typing import Tuple


def cmol_to_mol_per_kg(cmol_per_kg: float) -> float:
    """cmol(+)/kg → mol/kg"""
    return cmol_per_kg / 100.0


def mol_per_kg_to_cmol(mol_per_kg: float) -> float:
    """mol/kg → cmol(+)/kg"""
    return mol_per_kg * 100.0


def kg_per_ha_to_mol_per_ha(kg_per_ha: float, molar_mass: float) -> float:
    """kg/ha → mol/ha"""
    return kg_per_ha * 1000.0 / molar_mass


def calc_soil_mass_per_ha(bulk_density: float, depth_cm: float) -> float:
    """计算单位面积土壤质量 (kg/ha)

    参数:
        bulk_density: 容重 (g/cm³)
        depth_cm: 土层厚度 (cm)

    返回:
        土壤质量 (kg/ha)
    """
    depth_m = depth_cm / 100.0
    volume_m3 = depth_m * 10000.0  # m³/ha
    mass_kg = bulk_density * 1000.0 * volume_m3
    return mass_kg


def estimate_base_saturation(exch_ca: float, exch_mg: float,
                              exch_k: float, exch_na: float,
                              cec: float) -> float:
    """估算盐基饱和度 (%)

    参数:
        exch_ca, exch_mg, exch_k, exch_na: 交换性盐基离子 (cmol(+)/kg)
        cec: 阳离子交换量 (cmol(+)/kg)

    返回:
        盐基饱和度 (%)
    """
    total_base = exch_ca + exch_mg + exch_k + exch_na
    if cec > 0:
        return total_base / cec * 100.0
    return 0.0


def urea_to_hno3_equivalent(urea_kg_ha: float) -> float:
    """尿素转化为等效硝酸产酸量

    尿素 CO(NH2)2 水解后硝化:
      CO(NH2)2 + H2O → 2NH4+ + CO32-
      2NH4+ + 4O2 → 2NO3- + 4H+ + 2H2O

    每摩尔尿素产生 2 摩尔 H+
    尿素分子量: 60.06 g/mol

    参考文献:
      Lindsay W.L. Chemical Equilibria in Soils. John Wiley & Sons, 1979.
      Parton W.J. et al. (1987). SSSAJ, 51(5), 1173-1179.

    参数:
        urea_kg_ha: 尿素施用量 (kg/ha)

    返回:
        等效 H+ 摩尔量 (mol/ha)
    """
    urea_mol = urea_kg_ha * 1000.0 / 60.06  # mol/ha
    h_plus_mol = urea_mol * 2.0              # 2 mol H+ / mol urea
    return h_plus_mol


def calcite_dissolution_rate(ph: float, temperature: float) -> float:
    """方解石溶解速率 (mol/m²/s)

    参考文献:
      Plummer L.N., Wigley T.M.L., Parkhurst D.L. (1978). The kinetics of
      calcite dissolution in CO2-water systems at 5° to 60°C and 0.0 to
      1.0 atm CO2. American Journal of Science, 278(2), 179-216.

      Pokrovsky O.S. et al. (2009). Chemical Geology, 265(1-2), 1-17.

    参数:
        ph: 溶液 pH
        temperature: 温度 (°C)

    返回:
        溶解速率 (mol/m²/s)
    """
    # 简化速率方程 (Plummer et al., 1978)
    # 速率与 H+ 浓度成正比
    h_plus = 10.0 ** (-ph)

    # 温度修正 (Arrhenius)
    T_K = temperature + 273.15
    Ea = 50000.0  # J/mol (活化能)
    R = 8.314     # J/(mol·K)
    temp_factor = np.exp(-Ea / R * (1.0 / T_K - 1.0 / 298.15))

    # 基础速率常数
    k_base = 1e-7  # mol/m²/s (参考 Plummer et al., 1978)

    rate = k_base * h_plus * temp_factor
    return rate


def estimate_soil_pCO2(temp: float, pCO2_ref: float = 0.015,
                        T_ref: float = 25.0, beta: float = 0.05) -> float:
    """估算土壤CO2分压

    公式: pCO2(T) = pCO2_ref × exp[β × (T - T_ref)]

    参考文献:
      Brook G.A., Folkoff M.E., Box E.O. (1983). A world model of soil
      carbon dioxide. Earth Surface Processes and Landforms, 8(1), 79-88.

      Davidson E.A., Trumbore S.E. (1995). Gas diffusivity and production
      of CO2 in deep soils of the eastern Amazon. Tellus B, 47(5), 550-565.

    参数:
        temp: 当前温度 (°C)
        pCO2_ref: 参考CO2分压 (atm)
        T_ref: 参考温度 (°C)
        beta: 温度响应系数 (1/°C)

    返回:
        土壤CO2分压 (atm)
    """
    return pCO2_ref * np.exp(beta * (temp - T_ref))

