"""
模块: diagnostics.py
功能: 诊断实验领域函数 (L6/T5) — 交换铝缓冲库耗尽年判定与疗效标注

来源: 原 tools/plot_L6_layer_overrides.py (未版本化, 仅剩 __pycache__ 编译产物;
       2026-09-02 经 pyc 反汇编恢复并迁入 src/)。纯函数, 无引擎/绘图依赖,
       供测试与绘图工具共用。阈值见 constants.ALX3_DEPLETION_THRESHOLD_MOL。
"""

from typing import List, Optional

from src.constants import ALX3_DEPLETION_THRESHOLD_MOL


def depletion_year(alx3_series: List[float],
                   threshold: float = ALX3_DEPLETION_THRESHOLD_MOL) -> Optional[int]:
    """AlX3 首次低于阈值的一年 (1-based), 未耗尽则返回 None。

    参数:
        alx3_series: 某层逐年的交换性铝缓冲库 (AlX3, mol) 序列
        threshold: 耗尽判定阈值 (mol)

    返回:
        int (1-based 年份) 或 None (从未低于阈值)
    """
    for i, v in enumerate(alx3_series):
        if v < threshold:
            return i + 1
    return None


def impact_tag(base_alx3: List[float], real_alx3: List[float],
               threshold: float = ALX3_DEPLETION_THRESHOLD_MOL) -> str:
    """L6/T5 (2026-09-02 恢复): 真实剖面 vs 等参基线的 AlX3 耗尽疗效标注。

    判据:
      - 'good': 真实剖面耗尽推迟 / 未耗尽而基线耗尽 (缓冲增强)
      - 'bad':  真实剖面更早耗尽 / 耗尽而基线未耗尽 (缓冲脆弱)
      - 'neutral': 两者耗尽情况一致

    参数:
        base_alx3: 等参基线逐年的 AlX3 (mol) 序列
        real_alx3: 真实剖面逐年的 AlX3 (mol) 序列
        threshold: 耗尽判定阈值 (mol)

    返回:
        'good' | 'bad' | 'neutral'
    """
    base_dep = depletion_year(base_alx3, threshold)
    real_dep = depletion_year(real_alx3, threshold)

    # 真实未耗尽而基线耗尽 → 改善
    if real_dep is None and base_dep is not None:
        return 'good'
    # 真实耗尽而基线未耗尽 → 恶化
    if real_dep is not None and base_dep is None:
        return 'bad'
    # 两者都耗尽: 比较耗尽年份
    if real_dep is not None and base_dep is not None:
        if real_dep > base_dep:
            return 'good'
        if real_dep < base_dep:
            return 'bad'
    return 'neutral'


def calc_cec_occupied(exchange: dict) -> float:
    """CEC 占用电荷总量 (eq) — 输出诊断列 CEC_occupied 的单一公式源

    total = 盐基电荷 (CaX2×2 + MgX2×2 + KX + NaX) + AlX3×3，不含 HX
    (历史口径; 与 calc_base_saturation include_hx=False 的分母一致)。
    """
    base_charge = (exchange.get('CaX2', 0.0) * 2.0
                   + exchange.get('MgX2', 0.0) * 2.0
                   + exchange.get('KX', 0.0)
                   + exchange.get('NaX', 0.0))
    return base_charge + exchange.get('AlX3', 0.0) * 3.0


def calc_base_saturation(exchange: dict, include_hx: bool = False) -> float:
    """盐基饱和度 BS% — 输出诊断列与引擎分级注入的单一公式 (工单71)

    BS = (CaX2×2 + MgX2×2 + KX + NaX) / (盐基 + AlX3×3) × 100
    (与 main._extract_diagnostics 历史诊断列数值一致; 分母含 AlX3×3)。

    工单87 (P0-C): include_hx=True 时分母追加 HX (X- 位点上的 H, 一价电荷
    当量 = mol) —— 修复"AlX3 耗尽后 BS→100% 度量伪影" (H0 归因: 伪影经
    E_base/companion 分级注入反馈放大泵)。引擎分级注入传 include_hx=True
    (物理口径), 输出诊断列保持 include_hx=False (历史口径兼容)。

    参数:
        exchange: 交换相组成 dict (CaX2/MgX2/KX/NaX/AlX3/HX, mol)
        include_hx: 分母是否追加 HX (一价当量)

    返回:
        BS% (0~100, 总电荷 ≤ 0 时返回 0.0)
    """
    base_charge = (exchange.get('CaX2', 0.0) * 2.0
                   + exchange.get('MgX2', 0.0) * 2.0
                   + exchange.get('KX', 0.0)
                   + exchange.get('NaX', 0.0))
    acid_charge = exchange.get('AlX3', 0.0) * 3.0
    if include_hx:
        acid_charge += exchange.get('HX', 0.0)
    total = base_charge + acid_charge
    if total <= 0.0:
        return 0.0
    return base_charge / total * 100.0