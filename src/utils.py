"""
模块: utils.py
功能: 工具函数 (仅保留实际调用的函数, T04 清理死代码)

说明: 原 utils.py 含 8 个函数, 其中 6 个零调用已删除 (T04):
  - mol_per_kg_to_cmol / kg_per_ha_to_mol_per_ha: 无使用场景
  - calc_soil_mass_per_ha / estimate_base_saturation: 已被
    SoilProfile.soil_mass_per_ha / base_saturation 属性取代 (单一事实来源)
  - urea_to_hno3_equivalent / calcite_dissolution_rate: 无使用场景
保留 cmol_to_mol_per_kg / estimate_soil_pCO2 并接入实际调用。
"""

import numpy as np


def cmol_to_mol_per_kg(cmol_per_kg: float) -> float:
    """cmol(+)/kg → mol/kg"""
    return cmol_per_kg / 100.0


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

