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
工单97 (2026-09-29): 阳离子出流**荷电当量** (P3-ANC 恒等式闭合的缺列) — 只追加 3 列:
    leach_cation_eq_molc (两通道和) / leach_cation_transfer_molc (drains) /
    leach_cation_export_molc (lateral+baseflow)
  (电荷权重 Ca/Mg ×2、K/Na ×1; 口径源 = `solution` × 通道水量, 取在溶质扣除之前;
   ⚠️ 与旧列 `leach_base_mmol` 的摩尔和口径不同, 不得互相替代)
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
    # 工单95 (2026-09-29): 碳收支 / CO₂ 去气通量 (D8 开体系酸汇显式入账) —
    # 只追加; 五分量 + 闭合残差 (正 = 去气)
    ('c4_storage_delta_mol',   'c4_storage_delta_L{}_mol'),
    ('c4_inflow_mol',          'c4_inflow_L{}_mol'),
    ('c4_drain_out_mol',       'c4_drain_out_L{}_mol'),
    ('c4_out_system_mol',      'c4_out_system_L{}_mol'),
    ('c4_flush_mol',           'c4_flush_L{}_mol'),
    ('co2_gas_exchange_mol',   'co2_gas_exchange_L{}_mol'),
    # 工单97 (2026-09-29): 阳离子出流**荷电当量** (P3-ANC 闭合的缺列; 工单94 §E11.5)
    # — 只追加; 口径源 = `solution` (Ca/Mg/K/Na × 通道水量, 溶质扣除之前)
    #   ⚠️ 与旧列 `leach_base_mmol` (Ca+Mg+K **摩尔和**) 量纲/口径不同, 不得互相替代
    ('leach_cation_eq_molc',       'leach_cation_eq_L{}_molc'),
    ('leach_cation_transfer_molc', 'leach_cation_transfer_L{}_molc'),
    ('leach_cation_export_molc',   'leach_cation_export_L{}_molc'),
    # 工单100 (2026-09-30): 气相自洽性**只读**观测 (零假设判据; 工单99 §6.1.3)
    # — 只追加; 语义见 `src/phreeqc_input.py` 的 SELECTED_OUTPUT/USER_PUNCH 注:
    #   `co2_si`     = `SI(CO2(g))`（**相对 1 atm 纯气**）⇒ 边界被满足 ⇔
    #                  `co2_si == log10(pCO₂_imposed)`（0.0 = 未观测/该步被跳过）
    #   `co2_aq_mol` = 层内 `[CO2]aq` 当量 (mol/ha) = molality × `mass_H2O`
    ('co2_si',     'co2_si_L{}'),
    ('co2_aq_mol', 'co2_aq_L{}_mol'),
    # 工单101 (2026-10-01): P3-ANC 观测面三组只读列 — 只追加; 历史列名/顺序逐位不变
    #   A 溶液侧 NO₃⁻（与 Cl/S/An 同源同取值点; 与"池口径" leach_no3_* 不可相减）
    ('n_sol_transfer_mol',         'leach_n_sol_transfer_L{}_mol'),
    ('n_sol_export_mol',           'leach_n_sol_export_L{}_mol'),
    ('n_sol_flush_mol',            'leach_n_sol_flush_L{}_mol'),
    ('n_sol_mol',                  'leach_n_sol_L{}_mol'),
    #   B Q6 flush 通道（浓度源 = 扣除后/冲洗前; 与 c4_flush_mol 同式）
    ('cation_flush_molc',          'leach_cation_flush_L{}_molc'),
    ('cl_flush_mol',               'leach_cl_flush_L{}_mol'),
    ('s_flush_mol',                'leach_s_flush_L{}_mol'),
    ('an_flush_mol',               'leach_an_flush_L{}_mol'),
    #   C 降水 ANC 输入（eq/ha; 面板口径 precip_chem=None ⇒ 恒 0 = "未注入"哨兵）
    ('rain_bc_in_eq',              'rain_bc_in_L{}_eq'),
    ('rain_sa_in_eq',              'rain_sa_in_L{}_eq'),
    ('rain_nh4_in_eq',             'rain_nh4_in_L{}_eq'),
    ('rain_anc_in_eq',             'rain_anc_in_L{}_eq'),
]

# 阴离子淋失列 ↔ 观测浓度键 (**单一来源**; 列名即 _COLUMN_FORMATS 左列)
# 'An' = 配对惰性阴离子 (companion/charge-pairing 机制), 不在 `solution` 解析列表内
# ⇒ 由 `DiagnosticOutput.pair_anion_conc` 只读观测提供 (工单94 §2 F6 勘误)。
ANION_LEACH_IONS = (('leach_cl_mol', 'Cl'),
                    ('leach_s_mol', 'S'),
                    ('leach_an_mol', 'An'))

# 工单97 (2026-09-29): 阳离子出流**荷电当量**列 ↔ (溶质名, 电荷数)
# 电荷权重与 `solution_base_eq` (工单80) / `exchange_base_ratios` 同约定:
# Ca/Mg 二价 ×2, K/Na 一价 ×1; Al 不计入 (酸性盐基)。
# 口径源 = `SoilState.solution` (平衡后浓度 × 通道水量) ⇒ 与阴离子列**同源同取值点**。
CATION_LEACH_IONS = (('Ca', 2.0), ('Mg', 2.0), ('K', 1.0), ('Na', 1.0))


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


def cation_charge_columns(conc: dict, drain_L: float, out_system_L: float) -> dict:
    """工单97: 逐层逐场**阳离子出流荷电当量**列 (molc/ha) — 两通道和 + 分离

    口径与排水溶质扣除**同一来源**（`phreeqc_engine` 的 `moved_ions` /
    `q3_out_ions`: 平衡后浓度 × 该通道水量; 取值点在**溶质扣除之前**）⇒
    与工单94 的阴离子列**同源同取值点**, 二者可在同一张 ANC 表内相减。

    电荷权重: `CATION_LEACH_IONS` (Ca/Mg ×2, K/Na ×1; Al 不计入)。

    参数:
        conc: 溶液浓度 dict (mol/L; 只读 Ca/Mg/K/Na 四键, 缺键 → 0.0)
        drain_L: 层间下移水量 (drains → 下一层, L/ha)
        out_system_L: 出系统水量 (lateral + baseflow, L/ha)
    返回:
        {'leach_cation_eq_molc': 两通道和,
         'leach_cation_transfer_molc': drains 层间下移,
         'leach_cation_export_molc': 出系统}
        ⚠️ 恒等式 `eq == transfer + export` **由构造保证** (同一浓度/水量源)。
    """
    conc = conc or {}

    def _eq(water_L):
        return float(sum(z * leach_flux_mol(conc.get(ion, 0.0), water_L)
                         for ion, z in CATION_LEACH_IONS))

    transfer = _eq(drain_L)
    export = _eq(out_system_L)
    return {'leach_cation_eq_molc': transfer + export,
            'leach_cation_transfer_molc': transfer,
            'leach_cation_export_molc': export}


def _finite_or_zero(v) -> float:
    """工单95: 只读观测取数护栏 — 不可解析/NaN/Inf → 0.0 (绝不中断模拟)"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return f if math.isfinite(f) else 0.0


def _leach_mol(conc, water_L) -> float:
    """只读取数护栏: 浓度(mol/L) × 水量(L); 负水量/缺失/NaN ⇒ 0.0"""
    w = _finite_or_zero(water_L)
    if w <= 0.0:
        return 0.0
    return _finite_or_zero(conc) * w


# 工单101 (2026-10-01): P3-ANC 观测面三组只读列的离子集合
N_SOL_SPECIES = 'N'
FLUSH_CATIONS = (('Ca', 2.0), ('Mg', 2.0), ('K', 1.0), ('Na', 1.0))
RAIN_SPECIES = ('Ca+2', 'Mg+2', 'K+', 'Na+', 'NH4+', 'H+',
                'Cl-', 'SO4-2', 'NO3-', 'F-')


def solution_n_columns(conc: dict, drain_L: float, out_system_L: float,
                       flush_L: float = 0.0) -> dict:
    """工单101 A 组: **溶液侧 NO₃⁻** 三通道出流 (mol/ha) + 恒等列

    口径与工单94 `anion_leach_columns` / 工单97 `cation_charge_columns`
    **同源同取值点**（平衡后 `SELECTED_OUTPUT` totals，溶质扣除**之前**）⇒
    可在同一张 ANC 表内与 Cl/S/An 对账。

    ⚠️ 与账本 `leach_no3_mol`（**虚拟池**跟踪）**不可相减**：工单98 §6.1 实测
    fertilizer L1 池 76,959 vs 溶液侧 **1.54**（比值 2×10⁻⁵）⇒ 池的 NO₃⁻ 质量
    **未进入溶液**（其电荷效应经 `inert_eq`/`acid_eq` 替代注入）。

    参数:
        conc: 溶液浓度 dict (mol/L; 只读 'N' 键, 缺键 → 0.0)
        drain_L / out_system_L / flush_L: 三通道水量 (L/ha)
    返回:
        {'n_sol_transfer_mol': drains, 'n_sol_export_mol': lateral+baseflow,
         'n_sol_flush_mol': 冲洗通道, 'n_sol_mol': 三者之和}
        ⚠️ 恒等式 `n_sol_mol == transfer + export + flush` **由构造保证**。
    """
    conc = conc or {}
    tr = _leach_mol(conc.get(N_SOL_SPECIES, 0.0), drain_L)
    ex = _leach_mol(conc.get(N_SOL_SPECIES, 0.0), out_system_L)
    fl = _leach_mol(conc.get(N_SOL_SPECIES, 0.0), flush_L)
    return {'n_sol_transfer_mol': tr, 'n_sol_export_mol': ex,
            'n_sol_flush_mol': fl, 'n_sol_mol': tr + ex + fl}


def flush_leach_columns(conc: dict, pair_anion_conc: float,
                        flush_L: float) -> dict:
    """工单101 B 组: **Q6 浓度冲洗通道**只读记账 (mol/ha / molc/ha)

    与既有 `c4_flush_mol` (**同式**): 冲洗带出量 = 浓度 × `flush_L`
    （`flush_L = water_after_L × (max_c − CONC_WARN)/max_c`，引擎 Q6）。
    ⚠️ 该通道浓度源 = **溶质扣除后 / 冲洗前**（`flush_L` 本身定义于该浓度面）
    —— 与 A 组/工单94 的"扣除前"口径**不同**（票面 §2 已写明）。

    参数:
        conc: 冲洗前溶液浓度 dict (mol/L); `pair_anion_conc` = `An` 标量
              (`DiagnosticOutput.pair_anion_conc`; `An` 不入 `solution`)
        flush_L: 冲洗水量 (L/ha)
    返回:
        {'cation_flush_molc': (2Ca+2Mg+K+Na)×flush_L (荷电当量),
         'cl_flush_mol' / 's_flush_mol' / 'an_flush_mol': 摩尔}
        ⇒ `ANC_flush = cation − (cl + 2·s + an)`（供 P3-ANC 表使用）。
    """
    conc = conc or {}
    cat = sum(z * _leach_mol(conc.get(ion, 0.0), flush_L)
              for ion, z in FLUSH_CATIONS)
    return {'cation_flush_molc': cat,
            'cl_flush_mol': _leach_mol(conc.get('Cl', 0.0), flush_L),
            's_flush_mol': _leach_mol(conc.get('S', 0.0), flush_L),
            'an_flush_mol': _leach_mol(pair_anion_conc, flush_L)}


def rain_anc_columns(precip_chem, water_L: float,
                     bypass_L: float = 0.0) -> dict:
    """工单101 C 组: **降水化学注入的 ANC/电荷分量** (eq/ha) — 只读复算

    与 `src/phreeqc_input._collect_reaction_lines` **逐行同式**:
    `amounts = precip_chem.reaction_amounts(water_L)`（+ 优先流 `bypass_L`）。

    ⚠️ **口径（必须标注）**: `precip_chem is None`（**权威面板 / 基线包 / 全部探针**）
    ⇒ 引擎**未注入**降水化学 ⇒ 本组**恒 0.0**（"未注入"哨兵，非"未入账"）。
    只有产品端到端 `main.py` 传 `PrecipChemistry` ⇒ 本组才有值。

    ⚠️ **默认降水化学配置电荷不平衡**（`config/precip_chemistry_default.json`
    当量占比：阳离子 55.2 + H⁺ 1.0 vs 阴离子 43.8 ⇒ **阳离子过量 12.4%**）
    ⇒ `rain_anc_in_eq > 0`；**不得**按 gross BC 入账（须按**净 ANC**）。

    返回:
        {'rain_bc_in_eq': 2Ca+2Mg+K+Na, 'rain_sa_in_eq': Cl+2SO4+NO3+F,
         'rain_nh4_in_eq': NH4+, 'rain_anc_in_eq': BC+NH4−SA−H+}
    """
    out = {'rain_bc_in_eq': 0.0, 'rain_sa_in_eq': 0.0,
           'rain_nh4_in_eq': 0.0, 'rain_anc_in_eq': 0.0}
    if precip_chem is None:
        return out
    tot = {sp: 0.0 for sp in RAIN_SPECIES}
    for w in (water_L, bypass_L):
        if _finite_or_zero(w) <= 0.0:
            continue
        amt = precip_chem.reaction_amounts(w)
        for sp in RAIN_SPECIES:
            tot[sp] += _finite_or_zero(amt.get(sp, 0.0))
    bc = 2.0 * tot['Ca+2'] + 2.0 * tot['Mg+2'] + tot['K+'] + tot['Na+']
    sa = tot['Cl-'] + 2.0 * tot['SO4-2'] + tot['NO3-'] + tot['F-']
    out.update({'rain_bc_in_eq': bc, 'rain_sa_in_eq': sa,
                'rain_nh4_in_eq': tot['NH4+'],
                'rain_anc_in_eq': bc + tot['NH4+'] - sa - tot['H+']})
    return out


def co2_gas_exchange_mol(storage_delta_mol, inflow_mol, outflow_mol,
                         flush_mol) -> float:
    """工单95: 碳收支闭合残差 (= CO₂ 气相交换量, mol/ha; **正 = 去气/释放**)

    闭合式: `gas = 入流 − 存量增量 − 随水流出 − 冲洗带出`
    （等价于"水相 C(4) 的收支缺项"）。

    物理依据 (工单95 §2/§3): 本模型**无碳酸盐矿物相、无碳 KINETICS** ⇒ 水相 C(4)
    的变化只能来自 ① 水/溶质输运 ② **气相交换**（+ 未入账的数值残差）
    ⇒ 残差即 CO₂ 通量估计。去气 (`H⁺ + HCO₃⁻ → CO₂↑`) 不留态量痕迹，
    故必须由**恒等式闭合**反解（WF18 §E8 ③）。

    参数:
        storage_delta_mol: 本层本场**层内** C(4) 存量变化 (后 − 前; 含体积效应)
        inflow_mol: 层间入流 C(4) (上层 drains 携带; L1 = 0)
        outflow_mol: 随水流出 (drains 下移 + lateral/baseflow 出系统)
        flush_mol: 浓度冲洗 (CONC_WARN) 带出的 C(4)
    返回:
        float (mol/ha) — 不可解析/非有限输入按 0.0 计 (与 `leach_flux_mol` 同约束)
    """
    return (_finite_or_zero(inflow_mol)
            - _finite_or_zero(storage_delta_mol)
            - _finite_or_zero(outflow_mol)
            - _finite_or_zero(flush_mol))


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