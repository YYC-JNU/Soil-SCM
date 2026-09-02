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