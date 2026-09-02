"""
模块: event_accounting.py
功能: 事件级记账纯函数 — 事件明细行构造 + First-Flush 峰值计算

2026-09-02 (候选4): 从 src/phreeqc_engine._run_multi_layer_events 迁出。
领域循环只推进状态, 记账规则 (列名/mmol-eq 换算/峰值聚合) 集中于此模块,
可脱离 IPhreeqc 做纯 dict/字符串断言测试。零引擎依赖、零副作用。

明细行契约 (每场一行 dict, 列名与既存 hydrology['event_details'] 逐位一致):
  year/month/event/precip_mm + 逐层 {column}_L{layer} 展开列 (见 _COLUMN_FORMATS):
    n_no3_pool / leach_no3_mol / base_loss_eq / base_mode /
    e_base_anion_eq / companion_mode / companion_eq / inert_eq / acid_eq /
    nh4_exchanged_eq / lateral_L / baseflow_L / flush_L /
    leach_N_mmol / leach_base_mmol / ph
"""

from typing import Dict, List, Optional

# 列名生成映射: (ledger 无后缀键, 层后缀模板)
# 统一入口保证列名的历史格式 (lateral_L1_L / leach_N_L1_mmol / ph_L1) 逐位不变
_COLUMN_FORMATS = [
    ('n_no3_pool',       'n_no3_pool_L{}'),
    ('leach_no3_mol',    'leach_no3_L{}_mol'),
    ('base_loss_eq',     'base_loss_eq_L{}'),
    ('base_mode',        'base_mode_L{}'),
    ('e_base_anion_eq',  'e_base_anion_eq_L{}'),
    ('companion_mode',   'companion_mode_L{}'),
    ('companion_eq',     'companion_eq_L{}'),
    ('inert_eq',         'inert_eq_L{}'),
    ('acid_eq',          'acid_eq_L{}'),
    ('nh4_exchanged_eq', 'nh4_exchanged_eq_L{}'),
    ('lateral_L',        'lateral_L{}_L'),
    ('baseflow_L',       'baseflow_L{}_L'),
    ('flush_L',          'flush_L{}_L'),
    ('leach_N_mmol',     'leach_N_L{}_mmol'),
    ('leach_base_mmol',  'leach_base_L{}_mmol'),
    ('ph',               'ph_L{}'),
]


def build_event_row(ev_meta: dict, layer_rows: List[dict]) -> dict:
    """构造一场事件的明细行 (merged dict)

    参数:
        ev_meta: 事件头 {'year', 'month', 'event', 'precip_mm'}
        layer_rows: 逐层记账 dict 列表 (长度 = n_layers), 键为无后缀 ledger 名
            (见 _COLUMN_FORMATS 左列, 如 'leach_no3_mol'); 本函数按层格式展开。

    返回:
        单行 dict — 事件头 + 逐层 {column}_L{layer} 展开列
    """
    row = dict(ev_meta)
    for i, lr in enumerate(layer_rows):
        layer = i + 1
        for ledger_key, fmt in _COLUMN_FORMATS:
            row[fmt.format(layer)] = lr.get(ledger_key, 0.0)
    return row


def first_flush_peaks(layer0_rows: List[dict]) -> Dict[str, float]:
    """L1 (i=0) First-Flush 峰值: 当月最大单场淋失 (mmol/ha)

    参数:
        layer0_rows: 事件明细中 L1 的记账 dict 列表 (每场一条)

    返回:
        {'flush_no3_peak_mmol': float, 'flush_base_peak_mmol': float}
    """
    no3_peak = max((r.get('leach_N_mmol', 0.0) for r in layer0_rows),
                   default=0.0)
    base_peak = max((r.get('leach_base_mmol', 0.0) for r in layer0_rows),
                    default=0.0)
    return {'flush_no3_peak_mmol': no3_peak,
            'flush_base_peak_mmol': base_peak}