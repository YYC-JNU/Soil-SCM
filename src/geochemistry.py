"""
模块: geochemistry.py
功能: 地球化学机制纯函数 (v0.7.0+ 注入通道的离散计算)

2026-09-02 (候选3): 从 src/phreeqc_engine.py 迁出 — 引擎与 PHREEQC 输入构建器
(src/phreeqc_input.py) 共同引用, 消除输入生成对引擎类的循环依赖。
纯函数、无副作用、无引擎状态; 引擎顶部 re-export 保持 phreeqc_engine.<fn> 可见
(monkeypatch 锚点 test_nitrification/test_layer_overrides 零改动)。
"""

import math
from typing import Dict

from src.constants import NITRIFICATION_K1, NITRIFICATION_K2, N_MOL_PER_KG_N


def advance_nitrification(state, action,
                          k1: float = NITRIFICATION_K1,
                          k2: float = NITRIFICATION_K2) -> Dict[str, float]:
    """推进氮形态库存 (尿素 → NH4+ → NO3-, 简化一阶转化) [L4, v0.3.0]

    独立模块级函数 (升级空间): 将来若升级为 PHREEQC KINETICS 动力学块,
    只需替换本函数实现, 调用方 (引擎月度步) 与返回契约不变。

    Q1=A (库存层): 氮形态 (尿素/NH4+/NO3-) 为纯模型状态, 不注入 PHREEQC
    溶液平衡 — phreeqc.dat 的 N 氧化还原平衡会把注入的无机氮全部转为
    N2(g) (实测: pe=0~12 下溶液 N(-3)/N(5) 均≈0)。NH4+ 吸附于交换位点
    不易淋失, 为硝化的驱动源; NO3- 为累计硝化量 (诊断, Q4=A)。

    月度推进顺序:
      1. 施肥: N 以尿素形式入库存 (kg N → mol N)
      2. 尿素水解: n_urea × k1 → NH4+ (k1=1.0 当月全水解)
      3. 硝化: n_nh4 × k2 → NO3- (库存累计)

    返回本月硝化产酸量 (mol H+): {'H+': 2×硝化量}
    (Q3=A: 硝化产酸注入 REACTION, 酸化效应真实进入溶液)
    """
    # 1. 施肥: 尿素入库存 (kg N → mol N)
    if action.apply_fertilizer and getattr(action, 'n_amount', 0.0) > 0:
        state.n_urea += action.n_amount * N_MOL_PER_KG_N

    # 2. 尿素水解: urea → NH4+ (k1)
    hydrolyzed = state.n_urea * k1
    state.n_urea -= hydrolyzed
    state.n_nh4 += hydrolyzed

    # 3. 硝化: NH4+ → NO3- (k2, 库存形态)
    nitrified = state.n_nh4 * k2
    state.n_nh4 -= nitrified
    state.n_no3 += nitrified
    # v0.7.0 (工单70): 硝化量同步进入淋失示踪池 (供逐场 lost_no3 消费)
    state.n_no3_pool += nitrified

    # v0.7.0 (工单70): 返回契约扩展 — nitrified/hydrolyzed 键供 D3 伴随淋失
    # (工单71) 与 NH4+ 等效置换 (工单72) 消费; 'H+' 键契约不变 (向后兼容)
    return {'H+': 2.0 * nitrified,
            'nitrified': nitrified,
            'hydrolyzed': hydrolyzed}


def exchange_base_ratios(exchange: dict) -> Dict[str, float]:
    """v0.7.0 (工单72): 交换相 Ca:Mg:K:Na 电荷占比 (置换注入配比)

    按电荷量占比返回 {离子: 比例}, Σ=1; 空交换相 → 空 dict。
    CaX2/MgX2 为二价 (×2), KX/NaX 为一价。物理依据: NH4+ 置换盐基时
    各盐基按其在交换相中的电荷占比被置换出来 (简化近似, Gapon 加权留 v0.7.x)。
    """
    ca = exchange.get('CaX2', 0.0) * 2.0
    mg = exchange.get('MgX2', 0.0) * 2.0
    k = exchange.get('KX', 0.0)
    na = exchange.get('NaX', 0.0)
    total = ca + mg + k + na
    if total <= 0.0:
        return {}
    return {'Ca+2': ca / total, 'Mg+2': mg / total,
            'K+': k / total, 'Na+': na / total}


def weathering_arrhenius_factor(temp_c: float,
                                activation_energy_kJ: float,
                                t_ref_k: float = 298.15) -> float:
    """v0.7.0 (工单73): 矿物风化 Arrhenius 温度因子 (D2, 气候敏感性传导)

    factor = exp(−Ea/R × (1/T − 1/T_ref)), T 为开尔文
      - T = T_ref (25°C) → 1.0 (基准)
      - Ea=40 kJ/mol 时: 30°C ≈ 1.30 (增温 5°C 风化 +30%);
        20°C ≈ 0.77 (降温风化减缓) → 增温情景产生可观测风化响应 (疑点2)
    """
    r = 8.314
    t_k = temp_c + 273.15
    return math.exp(-activation_energy_kJ * 1000.0 / r
                    * (1.0 / t_k - 1.0 / t_ref_k))