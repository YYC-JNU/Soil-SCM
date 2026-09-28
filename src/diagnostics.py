"""
模块: diagnostics.py
功能: 诊断实验领域函数 (L6/T5) — 交换铝缓冲库耗尽年判定与疗效标注

来源: 原 tools/plot_L6_layer_overrides.py (未版本化, 仅剩 __pycache__ 编译产物;
       2026-09-02 经 pyc 反汇编恢复并迁入 src/)。纯函数, 无引擎/绘图依赖,
       供测试与绘图工具共用。阈值见 constants.ALX3_DEPLETION_THRESHOLD_MOL。
"""

import math
from typing import List, Optional

from src.constants import (ALX3_DEPLETION_THRESHOLD_MOL,
                           EXCHANGE_SITE_DRIFT_WARN_FRAC,
                           EXCHANGE_SITE_MIN_TOTAL,
                           EXCHANGE_WRITEBACK_SPECIES)


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


def exchange_charge_sum(exchange: dict) -> float:
    """交换相电荷总和 q (molc) — D4/D5 型"垃圾解"只读检测的单一公式源

    q = CaX2×2 + MgX2×2 + KX + NaX + AlX3×3 + HX
    (与 calc_base_saturation(include_hx=True) 的分母同构)

    工单91 P2 (2026-09-22): 引擎用同层 q_in/q_out 比值识别 PHREEQC 在高 pH /
    临界态静默返回的"质量不守恒解"(交换相六物种全灭, 见 KNOWN_DEVIATIONS
    D4/D5)。**仅诊断观测** — 不参与任何状态判定、不写回状态。
    """
    if not exchange:
        return 0.0
    return (exchange.get('CaX2', 0.0) * 2.0
            + exchange.get('MgX2', 0.0) * 2.0
            + exchange.get('KX', 0.0)
            + exchange.get('NaX', 0.0)
            + exchange.get('AlX3', 0.0) * 3.0
            + exchange.get('HX', 0.0))


def exchange_mass_flag(q_in: float, q_out: float,
                       collapse_thr: float = 0.5,
                       min_q_in: float = 1.0) -> Optional[str]:
    """交换相质量异常标记 (只读诊断; **不得**用于否决解/写回状态)

    返回: None (正常) | 'ZEROING' (q_in>0 而 q_out≤0, 硬指纹)
          | 'COLLAPSE' (q_out/q_in < collapse_thr)

    阈值标定 (工单91 §10.2/§10.2a, 2026-09-22):
      - 正常场内变化 |ratio-1| < 0.004 (natural 1y 380 步实测 0.9962~1.0000);
      - 6 臂 × 5y × 4 层离线扫描下 collapse_thr ≤ 0.9 **零假阳性** (建议 0.5);
      - **噪声门 min_q_in** (2026-09-22 实测新增): 某层一经零化, 其后续各场
        q_in/q_out 落到 1e-6~1e-5 molc 量级 (相对原值 ~1e-11), 此时 ratio 是
        纯噪声 (实测出现 1674× 与 5e-6), 必须与"首次塌陷 (q_in ~2e5)"区分。
        正常交换相量级 ≥ 1e3 molc ⇒ 门限取 1.0 molc (分离度 5 个数量级两侧)。

    历史教训 (R1 首实施, 2026-09-17, 已全部回退): 该标记一旦用于"拦截 +
    写回旧状态"会**双向失败** — 计入失败预算 → 状态链永久降级; 独立计数 →
    同一状态点空转 (610 次)。故本函数只产出标记, 语义由调用方限制为"记录"。
    """
    if q_in < min_q_in:
        return None
    if q_out <= 0.0:
        return 'ZEROING'
    if q_out / q_in < collapse_thr:
        return 'COLLAPSE'
    return None


def has_react_row(row_states: Optional[List[str]]) -> bool:
    """SELECTED_OUTPUT 数据行是否含 `react` 行 (只读诊断)

    参数:
        row_states: SELECTED_OUTPUT `state` 列的数据行取值 (按行序),
                    如正常场 ``['i_soln', 'react']``、退化场 ``['i_soln']``

    返回:
        True (含 `react` 行, 或**未观测** = 空/None 时不判不报)
        False (有数据行但无 `react` 行 = 该场无平衡解)

    工单93 (2026-09-23): PHREEQC 在 `GAS_PHASE -fixed_pressure` 约束不可满足时
    中止反应步、**不写 `react` 行** (SELECTED_OUTPUT 只剩表头 + `i_soln`初始解
    行) ⇒ 解析读到初始解行 (`q_out=0`、`pH_out ≡ pH_in`)。实测 4/4 崩坏场
    `row_states='i_soln'` vs 4779/4779 正常场 `'i_soln,react'` (零例外分离;
    `dev-notes/D45_ROOTCAUSE_E1.md` §3)。
    """
    if not row_states:
        return True
    return any(str(s).strip().lower() == 'react' for s in row_states)


def degenerate_step_flag(row_states: Optional[List[str]]) -> Optional[str]:
    """退化步标记 (只读诊断; **不得**用于否决解/写回状态)

    返回: None (正常 / 未观测) | 'NO_REACT_ROW' (有数据行但无 `react` 行)

    语义: 'NO_REACT_ROW' = 该反应步**没有产出平衡解** (引擎 F2 只要求
    `nrows > 1`, 于是把 `i_soln` 初始解行当有效解读入; F1 的"警告计数差"
    判定又因 `GetWarningStringLineCount()` 是 per-RunString 重置语义而漏判,
    使该步完全静默 —— 工单91 E1)。

    历史教训 (同 `exchange_mass_flag`): 该标记一旦用于"拦截 + 写回旧状态"
    会双向失败 (计入失败预算 → 状态链永久降级; 独立计数 → 同状态点空转
    610 次, 2026-09-17 R1 首实施)。故本函数只产出标记, 调用方语义限制为
    "记录" (工单93 选项 A: 只读标记 + 计数 + 首次告警)。
    """
    if has_react_row(row_states):
        return None
    return 'NO_REACT_ROW'


# ============ 工单96 (2026-09-28): 交换位点往返只读观测 (偏差 D9) ============
# 背景: 交换相**回写** (phreeqc_input 的 EXCHANGE 块) 只覆盖 6 个占用物种
# (constants.EXCHANGE_WRITEBACK_SPECIES), 而 SELECTED_OUTPUT 的 `-molalities`
# 同时输出**自由位点** `m_X-(mol/kgw)` 与全部交换物种 ⇒ **未被回写覆盖的位点
# 每步被静默丢弃** ⇒ 位点总数单调收缩 (实测 5y: L1 −0.09% → L4 −5.0%,
# 两情景近乎相同 ⇒ 结构性)。下列函数为**只读**单一公式源:
# 不参与状态判定、不写回状态、不占失败预算 (与 exchange_mass_flag /
# degenerate_step_flag 同一硬约束 —— 见工单91 P2 / 工单93 双向证伪教训)。

_SITE_FREE_NAMES = ('X-', 'X')
_SITE_SUFFIX_VALENCE = (('X3', 3), ('X2', 2), ('X', 1))
_MOLALITY_SUFFIX = '(mol/kgw)'


def exchange_species_valence(name: str) -> Optional[int]:
    """交换物种名的位点电荷数 — 后缀启发式 (X3→3 / X2→2 / X→1)

    自由位点 ('X-' / 'X') 与**未识别名**一律返回 None — 调用方**必须**把未识别名
    计入 unknown 并报告, **不得**静默按 0 计 (否则未知物种占位会被算丢,
    重复 D9 的"静默性")。
    """
    if not name or name in _SITE_FREE_NAMES:
        return None
    for suffix, z in _SITE_SUFFIX_VALENCE:
        if name.endswith(suffix):
            return z
    return None


def parse_exchange_molalities(headers, values) -> dict:
    """按 `m_` 前缀扫描 SELECTED_OUTPUT 的交换相 molality 列

    列名约定形如 `m_CaX2(mol/kgw)` / `m_X-(mol/kgw)`(自由位点);
    `-totals` 列 (`Ca(mol/kgw)` 等) **无 `m_` 前缀**, 天然排除。

    参数:
        headers: 列名序列;  values: 与之等长的取值序列

    返回:
        {'species': {name: molality},   # 占用物种 (自由位点除外)
         'free': float|None,            # 自由位点 molality (缺列 → None)
         'unknown': [name, ...]}        # 后缀未识别 (须报告)
    """
    species, unknown = {}, []
    free = None
    for c, h in enumerate(headers):
        name = str(h)
        if not name.startswith('m_') or not name.endswith(_MOLALITY_SUFFIX):
            continue
        sp = name[2:-len(_MOLALITY_SUFFIX)]
        try:
            val = float(values[c])
        except (TypeError, ValueError, IndexError):
            continue
        if not math.isfinite(val):
            continue        # NaN/Inf 一律跳过 (防污染位点统计)
        if sp in _SITE_FREE_NAMES:
            free = val
            continue
        if exchange_species_valence(sp) is None:
            unknown.append(sp)
            continue
        species[sp] = val
    return {'species': species, 'free': free, 'unknown': unknown}


def calc_site_occupied(species: dict, water_mass: float) -> float:
    """占用位点电荷 (molc/ha) = Σ z·m_sp × 水质量(kg)

    与 `exchange_charge_sum(state.exchange)` **在值上恒等**(同一换算) ⇒
    两者之差只反映"**回写覆盖范围**", 不引入新的数值口径。
    """
    return sum(exchange_species_valence(sp) * float(m)
               for sp, m in species.items()) * float(water_mass)


def calc_site_total_observed(species: dict, free: Optional[float],
                             water_mass: float) -> float:
    """本场**观测**位点总数 (molc/ha) = 自由位点 + 全部占用物种

    与 `calc_site_occupied` 之差 = 自由位点当量 ⇒ 是 D9 往返丢弃的**上界**。
    """
    occ = calc_site_occupied(species, water_mass)
    if free is None:
        return occ
    return occ + max(0.0, float(free)) * float(water_mass)


def calc_site_dropped(species: dict, free: Optional[float],
                      water_mass: float,
                      writeback=EXCHANGE_WRITEBACK_SPECIES) -> float:
    """本场**回写丢弃**的位点当量 (molc/ha) = 自由位点 + 未列物种占用

    判读 (工单96 ⭐ 判据, 2026-09-28):
      > 0 且可归因于自由位点或未列物种 ⇒ **往返丢弃确证** (D9 机制成立);
      ≈ 0 (自由位点≈0 且无未列物种) ⇒ 机制**证伪**, 须另找因。
    """
    dropped = 0.0
    if free is not None:
        dropped += max(0.0, float(free)) * float(water_mass)
    for sp, m in species.items():
        if sp in writeback:
            continue
        z = exchange_species_valence(sp)
        if z is None:
            continue
        dropped += max(0.0, z * float(m)) * float(water_mass)
    return dropped


def exchange_site_drift_flag(site_in: float, site_out: float,
                             warn_frac: float = EXCHANGE_SITE_DRIFT_WARN_FRAC,
                             min_site_in: float = EXCHANGE_SITE_MIN_TOTAL
                             ) -> Optional[str]:
    """位点总数漂移标记 (**只读**; 不得用于否决解 / 写回状态)

    返回: None (正常) | 'SITE_ZEROING' (site_out ≤ 0 且 site_in > 噪声门)
          | 'SITE_DRIFT' (|site_out − site_in| / site_in > warn_frac)

    阈值标定 (工单96, 2026-09-28): 现有护栏 `exchange_mass_flag` 只查**步内**
    `q_out/q_in < 0.5` 的崩塌 ⇒ **检不到 ~1%/yr 的慢漂移**; 本函数补该盲区,
    阈值取 **0.5%/场** (远高于正常场噪声, 远低于崩塌量级)。
    """
    if site_in <= min_site_in:
        return None
    if site_out <= 0.0:
        return 'SITE_ZEROING'
    if abs(site_out - site_in) / site_in > warn_frac:
        return 'SITE_DRIFT'
    return None
