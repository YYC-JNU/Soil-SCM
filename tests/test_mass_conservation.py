"""测试 工单91 P2 只读质量守恒检测 (2026-09-22)

覆盖三层:
  1. 纯函数口径: `exchange_charge_sum` 与 BS 分母同构; `exchange_mass_flag`
     判定与阈值语义;
  2. 引擎接线: `_parse_official_output` 把 q_in/q_out/标记写入**只读** diag 字段;
  3. **零行为变更护栏**: 检出 ZEROING 时引擎仍照旧接受该解 —— 不写回旧状态、
     不占失败预算、不进入降级 (R1 双向证伪 2026-09-17 后的硬约束)。

现场指纹来源: `output/MASS_GUARD_d5nat5.csv` 的 `y4 m3 ev38 try1 L2`
(q_in = 219520.8342 molc, q_out = 0.0, pH 9.2734) — natural 与 lime_high 同指纹。
"""
import pytest

from src.diagnostics import (calc_base_saturation, exchange_charge_sum,
                             exchange_mass_flag)
from src.phreeqc_engine import DiagnosticOutput, PhreeqcEngine, SoilState

# y4 L2 崩坏现场真实 q_in (molc)
Q_IN_Y4L2 = 219520.8342


class _FakeOfficial:
    """最小 IPhreeqc SELECTED_OUTPUT 替身 (只喂 `_parse_official_output` 读的列)"""

    HEADERS = (['sim', 'state', 'soln', 'dist_x', 'time', 'step', 'pH', 'pe',
                'temp(C)', 'Ca(mol/kgw)', 'mass_H2O']
               + [f'm_{sp}(mol/kgw)' for sp in ('CaX2', 'MgX2', 'KX', 'NaX',
                                                'AlX3', 'HX')])

    def __init__(self, ex_per_kg, water_kg=1.0e6, ph=9.2734):
        vals = {'sim': 1.0, 'state': 'react', 'soln': 1.0, 'dist_x': 0.0,
                'time': 0.0, 'step': 1.0, 'pH': ph, 'pe': 4.0,
                'temp(C)': 25.0, 'Ca(mol/kgw)': 1.0e-3, 'mass_H2O': water_kg}
        for sp in ('CaX2', 'MgX2', 'KX', 'NaX', 'AlX3', 'HX'):
            vals[f'm_{sp}(mol/kgw)'] = ex_per_kg.get(sp, 0.0)
        self._vals = [vals[h] for h in self.HEADERS]

    def GetSelectedOutputRowCount(self):
        return 2

    def GetSelectedOutputColumnCount(self):
        return len(self.HEADERS)

    def GetSelectedOutputValue(self, row, col):
        return self.HEADERS[col] if row == 0 else self._vals[col]


@pytest.fixture
def engine():
    return PhreeqcEngine(database='phreeqc.dat', mode='phreeqc')


# ---------------- 1. 纯函数口径 ----------------
def test_exchange_charge_sum_matches_bs_denominator():
    """q 与 calc_base_saturation(include_hx=True) 的分母同构 (单一公式源)"""
    ex = {'CaX2': 100.0, 'MgX2': 20.0, 'KX': 3.0, 'NaX': 2.0,
          'AlX3': 10.0, 'HX': 50.0}
    base = 100.0 * 2 + 20.0 * 2 + 3.0 + 2.0
    q = exchange_charge_sum(ex)
    assert abs(calc_base_saturation(ex, include_hx=True)
               - base / q * 100.0) < 1e-9


def test_exchange_charge_sum_empty():
    assert exchange_charge_sum({}) == 0.0
    assert exchange_charge_sum(None) == 0.0


def test_exchange_mass_flag_zeroing_is_hard_fingerprint():
    """q_in>0 而 q_out=0 → 唯一硬指纹 (D4/D5 现场)"""
    assert exchange_mass_flag(Q_IN_Y4L2, 0.0) == 'ZEROING'


def test_exchange_mass_flag_normal_and_collapse():
    """正常场内变化 (<0.4%) 与施石灰上界 (max 1.25) 均不误报"""
    assert exchange_mass_flag(Q_IN_Y4L2, Q_IN_Y4L2 * 0.9968) is None
    assert exchange_mass_flag(Q_IN_Y4L2, Q_IN_Y4L2 * 1.25) is None
    assert exchange_mass_flag(Q_IN_Y4L2, Q_IN_Y4L2 * 0.2) == 'COLLAPSE'
    assert exchange_mass_flag(0.0, 0.0) is None      # 无输入不判


def test_exchange_mass_flag_noise_gate():
    """**小分母噪声门** (2026-09-22 实测, tole_12 臂 y5 起): 零化后 q_in/q_out
    落到 1e-6~1e-5 molc 量级, ratio 无物理意义 (实测 1674× / 5e-6) — 不得误报"""
    # 首次塌陷 (q_in 有物理量级) → 报
    assert exchange_mass_flag(219520.3772, 0.0) == 'ZEROING'
    # 零化后的噪声级样本 → 一律不报 (无论 ratio 看起来多极端)
    assert exchange_mass_flag(1.0e-5, 0.0) is None
    assert exchange_mass_flag(1.0e-6, 1.0e-6 * 5e-6) is None
    assert exchange_mass_flag(1.0e-5, 1.0e-5 * 1674.0) is None
    # 门限可配 (极小的 min_q_in 会恢复旧行为, 仅用于诊断对照)
    assert exchange_mass_flag(1.0e-5, 0.0, min_q_in=0.0) == 'ZEROING'


def test_exchange_mass_flag_threshold_semantics():
    """阈值可配: 0.99 会捕获 2% 漂移, 默认 0.5 不捕获 (标定建议值)"""
    q = Q_IN_Y4L2
    assert exchange_mass_flag(q, q * 0.98, collapse_thr=0.99) == 'COLLAPSE'
    assert exchange_mass_flag(q, q * 0.98, collapse_thr=0.5) is None
    assert exchange_mass_flag(q, q * 0.995, collapse_thr=0.5) is None


# ---------------- 2. 引擎接线 (只读 diag 字段) ----------------
def test_diag_new_fields_default_unchanged():
    """新字段默认值 — 既有行为与断言零变化"""
    d = DiagnosticOutput()
    assert d.exchange_q_in == 0.0
    assert d.exchange_q_out == 0.0
    assert d.exchange_mass_flag == ''


def test_parse_official_output_records_normal_ratio(engine):
    """正常态: q_out ≈ q_in、无标记、计数不增"""
    ex = {'CaX2': 100.0, 'MgX2': 20.0, 'KX': 3.0, 'NaX': 2.0}
    st = SoilState(exchange=dict(ex), volume=1.0e6)
    engine.official = _FakeOfficial(
        {'CaX2': 100.0 / 1.0e6, 'MgX2': 20.0 / 1.0e6,
         'KX': 3.0 / 1.0e6, 'NaX': 2.0 / 1.0e6})
    _, diag = engine._parse_official_output(st)
    assert diag.exchange_q_in == pytest.approx(exchange_charge_sum(ex))
    assert diag.exchange_q_out == pytest.approx(diag.exchange_q_in)
    assert diag.exchange_mass_flag == ''
    assert engine.mass_anomaly_count == 0


def test_zeroing_is_flagged_but_solution_still_accepted(engine):
    """**零行为变更护栏** — 检出 ZEROING 时引擎仍照旧接受该解 (R1 教训)

    R1 首实施 (2026-09-17) 的两种语义 (拦截占失败预算 / 拦截独立计数)
    均已双向证伪; 本测试锁死正确语义: **只标记, 不改状态、不改降级**。
    """
    st = SoilState(exchange={'CaX2': Q_IN_Y4L2 / 2.0, 'HX': Q_IN_Y4L2 / 2.0},
                   volume=1.0e6)
    engine.official = _FakeOfficial({})          # m_* 全 0 → 交换相全灭
    new_state, diag = engine._parse_official_output(st)
    # 检出正确
    assert diag.exchange_mass_flag == 'ZEROING'
    assert diag.exchange_q_in > 0.0
    assert diag.exchange_q_out == 0.0
    assert engine.mass_anomaly_count == 1
    # ① 状态未被替换/写回 (引擎照旧接受该解 ⇒ 与权威基线逐位一致的前提)
    assert new_state.exchange['CaX2'] == 0.0
    # ② 未进入降级/失败预算
    assert engine._permanent_fallback is False
    assert engine._fallback_warned is False
    assert engine._consecutive_failures_event == 0
    assert engine._consecutive_failures_monthly == 0


def test_flag_counts_every_occurrence(engine):
    """只读累计计数 (每次异常都计数; 告警限流由 `== 1` 条件保证)"""
    st = SoilState(exchange={'CaX2': Q_IN_Y4L2 / 2.0, 'HX': Q_IN_Y4L2 / 2.0},
                   volume=1.0e6)
    engine.official = _FakeOfficial({})
    for _ in range(3):
        engine._parse_official_output(st)
    assert engine.mass_anomaly_count == 3
    assert engine._permanent_fallback is False