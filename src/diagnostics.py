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
