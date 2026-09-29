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

工单94 (2026-09-28): **阴离子收支记账** (D8 预算可判读化) — 只追加下列列
(历史列名与顺序逐位不变):
    leach_cl_mol / leach_s_mol / leach_an_mol (阴离子随水移出量, mol/ha)
    leach_no3_export_mol (出系统: lateral+baseflow)
    leach_no3_transfer_mol (层间下移: drains + bypass 携带)
  ⚠️ `leach_no3_export_mol + leach_no3_transfer_mol == leach_no3_mol` 仅在
  **浮点级**成立 (三项各自独立累加以保持 `leach_no3_mol` 逐位不变 ⇒
  `pending_e_loss` 注入基准零变化, 见工单94 §5 硬约束)。
"""

import math
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
    # 工单96 (2026-09-28): 交换位点往返只读观测 (D9) — 位点总数 / 回写丢弃当量
    ('site_total_molc',  'site_total_L{}_molc'),
    ('site_gap_molc',    'site_gap_L{}_molc'),
    # 工单94 (2026-09-28): 阴离子收支记账 (D8) — 只追加, 历史列名/顺序逐位不变
    # (阴离子三列 + E_loss 出口/层间下移分离两列)
    ('leach_cl_mol',           'leach_cl_L{}_mol'),
    ('leach_s_mol',            'leach_s_L{}_mol'),
    ('leach_an_mol',           'leach_an_L{}_mol'),
    ('leach_no3_export_mol',   'leach_no3_export_L{}_mol'),
    ('leach_no3_transfer_mol', 'leach_no3_transfer_L{}_mol'),
]

# 阴离子淋失列 ↔ 观测浓度键 (**单一来源**; 列名即 _COLUMN_FORMATS 左列)
# 'An' = 配对惰性阴离子 (companion/charge-pairing 机制), 不在 `solution` 解析列表内
# ⇒ 由 `DiagnosticOutput.pair_anion_conc` 只读观测提供 (工单94 §2 F6 勘误)。
ANION_LEACH_IONS = (('leach_cl_mol', 'Cl'),
                    ('leach_s_mol', 'S'),
                    ('leach_an_mol', 'An'))


def leach_flux_mol(conc_mol_L, water_L) -> float:
    """工单94: 溶质随水移出量 (mol/ha) = 浓度 (mol/L) × 水量 (L/ha)

    **只读观测护栏** (与工单91 P2 / 工单93 / 工单96 同一硬约束):
    负浓度/零水量/NaN/Inf/不可解析 一律返回 0.0 —— 观测本身**绝不**中断模拟,
    也不得把非物理数带进记账表 (`float('NaN')` 不抛异常 ⇒ 须 `isfinite` 显式剔除)。
    """
    try:
        c = float(conc_mol_L)
        w = float(water_L)
    except (TypeError, ValueError):
        return 0.0
    if not (math.isfinite(c) and math.isfinite(w)):
        return 0.0
    if c <= 0.0 or w <= 0.0:
        return 0.0
    return c * w


def anion_leach_columns(conc: dict, drain_L: float, out_system_L: float) -> dict:
    """工单94: 逐层逐场阴离子淋失列 (mol/ha) — 两通道之和

    口径与排水溶质扣除**同一来源** (`phreeqc_engine` 的 `moved_ions` /
    `q3_out_ions`: 平衡后浓度 × 该通道水量):
      - drain_L: 层间下移 (drains → 下一层)
      - out_system_L: 出系统 (lateral + baseflow)
    两者之和 = 本层本场随水移出的阴离子总量 ⇒ 可与 NO₃⁻ 淋失在同表对账。

    参数:
        conc: {'Cl': .., 'S': .., 'An': ..} (mol/L; 缺键 → 0.0, 历史口径)
        drain_L / out_system_L: 该场该层两通道水量 (L/ha)
    返回:
        {'leach_cl_mol': float, 'leach_s_mol': float, 'leach_an_mol': float}
    """
    conc = conc or {}
    return {key: (leach_flux_mol(conc.get(ion, 0.0), drain_L)
                  + leach_flux_mol(conc.get(ion, 0.0), out_system_L))
            for key, ion in ANION_LEACH_IONS}


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