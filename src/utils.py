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


def layer_pco2_override(layer_index=None, n_layers=None):
    """工单D (C1, 2026-08-31): 分层 pCO₂ 覆盖访问器 (深层碳酸缓冲标定)

    返回该层目标 pCO₂ (atm) 或 None (不覆盖=基线)。默认全 None (v85 基线);
    仅 L4 定案值非默认 (PCO2_4LAYER_OVERRIDE)。单一来源 + 层数护栏 + 调用期
    读取 (monkeypatch 可扫描), 同 layer_aloh3_params 口径。

    返回:
        float 或 None (None = 不覆盖, 用 apply_om_pco2 基线值)
    """
    import src.constants as C
    n = len(C.PCO2_4LAYER_OVERRIDE)
    if (layer_index is None or layer_index < 0 or layer_index >= n
            or n_layers == 1):
        return None
    return C.PCO2_4LAYER_OVERRIDE[layer_index]


def layer_aloh3_params(layer_index=None, n_layers=None) -> dict:
    """工单D (2026-08-31): Al(OH)3(a) 分层参数集中访问器 (单一来源)

    builder (build_minerals) / engine (_build_phreeqc_input) 共用 — 值+逻辑单一来源:
      值: src.constants (AMORPHOUS_ALOH3_4LAYER_*; SCALE 从 MINERAL_SCALE 派生防双轨)
      逻辑: 本函数唯一实现分层选择 (索引护栏 / 显式单层护栏)
      调用期读取模块属性 → monkeypatch 可扫描标定 (不改代码换网格, D 工单方法论)

    返回 dict(fraction, logk, scale):
      - layer_index None / 索引越界 / n_layers==1 (显式单层护栏) → 全局默认
        (AMORPHOUS_ALOH3_MASS_FRACTION / 数据库 log_k / MINERAL_SCALE) = 基线行为
      - 否则取 AMORPHOUS_ALOH3_4LAYER_*[layer_index]
        (logk 默认 = 数据库值 10.8, 引擎据此判定不注入 PHASES, 逐位基线)
    注: n_layers 仅用于显式单层护栏 (==1); None/≥2 不拦截 (多层传 layer_index 即可)。
    """
    import src.constants as C
    n = len(C.AMORPHOUS_ALOH3_4LAYER_FRACTIONS)
    if (layer_index is None or layer_index < 0 or layer_index >= n
            or n_layers == 1):
        return {
            'fraction': C.AMORPHOUS_ALOH3_MASS_FRACTION,
            'logk': C.AMORPHOUS_ALOH3_LOGK_DATABASE,
            'scale': C.MINERAL_SCALE,
        }
    return {
        'fraction': C.AMORPHOUS_ALOH3_4LAYER_FRACTIONS[layer_index],
        'logk': C.AMORPHOUS_ALOH3_4LAYER_LOGK[layer_index],
        'scale': C.AMORPHOUS_ALOH3_4LAYER_SCALE[layer_index],
    }

