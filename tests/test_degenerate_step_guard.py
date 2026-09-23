"""测试 工单93 选项A 引擎退化步只读护栏 (2026-09-23)

覆盖三层:
  1. 纯函数口径: `has_react_row` / `degenerate_step_flag` (无 `react` 行 =
     该反应步**没有产出平衡解**; 未观测时不判不报);
  2. 引擎接线: `_parse_official_output` 把 `has_react_row` / `sel_row_states` /
     `solve_error` 写入**只读** diag 字段, 并只读计数
     `engine.degenerate_step_count` (首次告警);
  3. **零行为变更护栏**: 检出退化步时引擎仍照旧接受该解 —— 解析行仍是末行、
     不写回旧状态、不占失败预算、不进入降级 (R1 双向证伪 2026-09-17 后的硬约束)。

现场指纹来源: `output/FORENSIC_p4_fx30_dump01_zeroing_L2_y4m3_ev38.txt`
(崩坏场 `nrows=2` / `row_states='i_soln'`; 正常对照场 `nrows=3` /
`row_states='i_soln,react'`, 见 `dev-notes/D45_ROOTCAUSE_E1.md` §3)。
"""
import logging

import pytest

from src.diagnostics import degenerate_step_flag, has_react_row
from src.phreeqc_engine import DiagnosticOutput, PhreeqcEngine, SoilState

# 现场真实错误串 (E1: `GAS_PHASE -fixed_pressure` 约束不可满足)
SOLVE_ERROR_LIVE = ("ERROR: gas moles Total moles in gas phase has not "
                    "converged.\nResidual: 2.250000e-02")


class _FakeOfficial:
    """最小 IPhreeqc SELECTED_OUTPUT 替身 (`state` 列 + 错误串 + 警告计数)"""

    BASE = ['sim', 'state', 'soln', 'dist_x', 'time', 'step', 'pH', 'pe',
            'temp(C)', 'Ca(mol/kgw)', 'mass_H2O']
    SPECIES = ('CaX2', 'MgX2', 'KX', 'NaX', 'AlX3', 'HX')

    def __init__(self, ex_per_kg=None, row_states=('i_soln', 'react'),
                 water_kg=1.0e6, ph=9.2738, solve_error='',
                 warning_count=0, include_state_col=True):
        ex_per_kg = ex_per_kg or {}
        self.HEADERS = list(self.BASE)
        if not include_state_col:
            self.HEADERS.remove('state')
        self.HEADERS += [f'm_{sp}(mol/kgw)' for sp in self.SPECIES]
        vals = {'sim': 1.0, 'state': 'i_soln', 'soln': 1.0, 'dist_x': -99.0,
                'time': -99.0, 'step': -99.0, 'pH': ph, 'pe': 4.0,
                'temp(C)': 25.0, 'Ca(mol/kgw)': 1.0e-3,
                'mass_H2O': water_kg}
        for sp in self.SPECIES:
            vals[f'm_{sp}(mol/kgw)'] = ex_per_kg.get(sp, 0.0)
        self._rows = []
        for st in row_states:
            row = dict(vals)
            row['state'] = st
            self._rows.append([row[h] for h in self.HEADERS])
        self._solve_error = solve_error
        self._warning_count = warning_count

    def GetSelectedOutputRowCount(self):
        return len(self._rows) + 1          # +1 = 列名行

    def GetSelectedOutputColumnCount(self):
        return len(self.HEADERS)

    def GetSelectedOutputValue(self, row, col):
        return self.HEADERS[col] if row == 0 else self._rows[row - 1][col]

    def GetErrorString(self):
        return self._solve_error

    def GetWarningStringLineCount(self):
        return self._warning_count

    def GetWarningStringLine(self, i):
        return ''


@pytest.fixture
def engine():
    return PhreeqcEngine(database='phreeqc.dat', mode='phreeqc')


# ---------------- 1. 纯函数口径 ----------------
def test_has_react_row_normal_and_degenerate():
    """正常场 = i_soln,react; 退化场 = 仅 i_soln; 未观测 (空) = 不判"""
    assert has_react_row(['i_soln', 'react']) is True
    assert has_react_row(['i_soln']) is False
    assert has_react_row([]) is True
    assert has_react_row(None) is True


def test_has_react_row_tolerates_case_and_whitespace():
    """`state` 列经由 str() 取值, 容错大小写/空白/尾部换行"""
    assert has_react_row([' react ']) is True
    assert has_react_row(['React']) is True
    assert has_react_row(['i_soln', 'react\n']) is True
    assert has_react_row(['i_soln', 'i_gas']) is False


def test_degenerate_step_flag_semantics():
    """None (正常/未观测) vs 'NO_REACT_ROW' (有数据行但无 react 行)"""
    assert degenerate_step_flag(['i_soln', 'react']) is None
    assert degenerate_step_flag(['i_soln']) == 'NO_REACT_ROW'
    assert degenerate_step_flag(['i_soln', 'i_gas']) == 'NO_REACT_ROW'
    # 未观测 (无 `state` 列) ⇒ 不误报
    assert degenerate_step_flag([]) is None
    assert degenerate_step_flag(None) is None


def test_degenerate_step_flag_forensic_fingerprint():
    """现场指纹 (E1 §3): 4/4 崩坏场 = ['i_soln']; 4779/4779 正常场 = 含 react"""
    for _case in ('L2@y4m3', 'L3@y11m3', 'L1@y15m9', 'L4@y18m4'):
        assert degenerate_step_flag(['i_soln']) == 'NO_REACT_ROW'
    assert degenerate_step_flag(['i_soln', 'react']) is None


# ---------------- 2. 引擎接线 (只读字段) ----------------
def test_diag_new_fields_default_unchanged():
    """新字段默认值 — 既有断言零变化 (默认 = 无异常/未观测)"""
    d = DiagnosticOutput()
    assert d.has_react_row is True
    assert d.sel_row_states == ''
    assert d.solve_error == ''
    # 既有字段不受影响
    assert d.exchange_mass_flag == ''
    assert d.exchange_q_in == 0.0


def test_parse_records_react_row_and_error(engine):
    """正常场: sel_row_states='i_soln,react'、无退化标记、两个计数器均不增"""
    ex = {'CaX2': 100.0 / 1.0e6, 'MgX2': 20.0 / 1.0e6,
          'KX': 3.0 / 1.0e6, 'NaX': 2.0 / 1.0e6}
    st = SoilState(exchange={'CaX2': 100.0, 'MgX2': 20.0, 'KX': 3.0,
                             'NaX': 2.0}, volume=1.0e6)
    engine.official = _FakeOfficial(ex, row_states=('i_soln', 'react'))
    new_state, diag = engine._parse_official_output(st)
    assert diag.has_react_row is True
    assert diag.sel_row_states == 'i_soln,react'
    assert diag.solve_error == ''
    assert engine.degenerate_step_count == 0
    assert engine.mass_anomaly_count == 0
    # 解析行仍是末行 (react 行): 交换相被回填
    assert new_state.exchange['CaX2'] == pytest.approx(100.0)
    assert new_state.ph == pytest.approx(9.2738)


def test_parse_flags_degenerate_step_read_only(engine):
    """**零行为变更护栏** — 检出退化步时引擎仍照旧接受该解 (R1 教训)

    现场形态: `nrows=2` / 唯一数据行 = i_soln (交换相六物种显式 0、
    pH = 输入写入值)。本测试锁死正确语义: **只标记, 不改状态、不改降级**。
    """
    q_in = 219520.3743
    st = SoilState(exchange={'CaX2': q_in / 2.0, 'HX': q_in / 2.0},
                   volume=1.0e6)
    engine.official = _FakeOfficial({}, row_states=('i_soln',),
                                     solve_error=SOLVE_ERROR_LIVE)
    new_state, diag = engine._parse_official_output(st)
    # ① 只读字段正确
    assert diag.has_react_row is False
    assert diag.sel_row_states == 'i_soln'
    assert engine.degenerate_step_count == 1
    # ② 退化解的既有语义不变: 末行 (i_soln) 照旧被回填 = 全零交换相
    assert new_state.exchange['CaX2'] == 0.0
    assert new_state.ph == pytest.approx(9.2738)
    # ③ 未进入降级 / 未占失败预算 / 未标记 fallback
    assert engine._permanent_fallback is False
    assert engine._fallback_warned is False
    assert engine._consecutive_failures_event == 0
    assert engine._consecutive_failures_monthly == 0
    # ④ 与 P2 计数器互不污染 (本场同时命中交换相零化)
    assert engine.mass_anomaly_count == 1
    assert diag.exchange_mass_flag == 'ZEROING'


def test_degenerate_step_counts_every_occurrence_warns_once(engine, caplog):
    """只读累计计数 (每次都计数) + **首次告警** (限流)"""
    st = SoilState(exchange={'CaX2': 100.0}, volume=1.0e6)
    engine.official = _FakeOfficial({}, row_states=('i_soln',))
    with caplog.at_level(logging.WARNING,
                         logger='soil_scm.phreeqc_engine'):
        for _ in range(2):
            engine._parse_official_output(st)
    assert engine.degenerate_step_count == 2
    warns = [r for r in caplog.records if '退化步' in r.getMessage()]
    assert len(warns) == 1
    assert 'NO_REACT_ROW' in warns[0].getMessage()


def test_missing_state_column_is_not_flagged(engine):
    """无 `state` 列 (未观测) ⇒ 不判不报 (零误报护栏)"""
    st = SoilState(exchange={'CaX2': 100.0}, volume=1.0e6)
    engine.official = _FakeOfficial({'CaX2': 100.0 / 1.0e6},
                                    row_states=('x',),
                                    include_state_col=False)
    _, diag = engine._parse_official_output(st)
    assert diag.sel_row_states == ''
    assert diag.has_react_row is True
    assert engine.degenerate_step_count == 0


# ---------------- 3. F1 盲区与只读可观测性 ----------------
def test_row_state_read_failure_is_not_flagged(engine):
    """`state` 列读取抛异常 ⇒ 放弃观测 (不假报退化步)"""
    class _Broken(_FakeOfficial):
        def GetSelectedOutputValue(self, row, col):
            if row > 0 and self.HEADERS[col] == 'state':
                raise RuntimeError('IPhreeqc API 异常')
            return super().GetSelectedOutputValue(row, col)

    st = SoilState(exchange={'CaX2': 100.0}, volume=1.0e6)
    engine.official = _Broken({'CaX2': 100.0 / 1.0e6},
                              row_states=('i_soln', 'react'))
    _, diag = engine._parse_official_output(st)
    assert diag.sel_row_states == ''
    assert engine.degenerate_step_count == 0


def test_solve_error_recorded_read_only(engine):
    """`solve_error` 只读记录 (`GetErrorString()`, 折叠单行) — 不触发退化标记"""
    st = SoilState(exchange={'CaX2': 100.0}, volume=1.0e6)
    engine.official = _FakeOfficial({'CaX2': 100.0 / 1.0e6},
                                    row_states=('i_soln', 'react'),
                                    solve_error='WARNING: foo\nWARNING: bar')
    _, diag = engine._parse_official_output(st)
    assert diag.solve_error == 'WARNING: foo | WARNING: bar'
    assert engine.degenerate_step_count == 0     # react 行在 ⇒ 非退化步
    assert engine._permanent_fallback is False


def test_f1_blind_spot_is_observable(engine):
    """F1 漏判 (警告计数 per-RunString 重置 ⇒ 判不出"重试仍失败") 的步,
    必被只读观测检出 (本票不修改 F1 判定本身, 只补观测面)"""
    # F1 现场: 同输入连跑三次计数恒 85 ⇒ `_has_new_convergence_warning`
    # 因 `n <= before` 立即返回 False (既有行为, 本票不动)
    engine.official = _FakeOfficial({}, row_states=('i_soln',),
                                     warning_count=85,
                                     solve_error=SOLVE_ERROR_LIVE)
    assert engine._has_new_convergence_warning(85) is False
    st = SoilState(exchange={'CaX2': 100.0}, volume=1.0e6)
    new_state, diag = engine._parse_official_output(st)
    # 观测面覆盖 F1 盲区: 退化步 + 真实错误串 均可见
    assert diag.has_react_row is False
    assert diag.sel_row_states == 'i_soln'
    assert 'has not converged' in diag.solve_error
    assert engine.degenerate_step_count == 1
    # 且未改变任何既有行为
    assert new_state.ph == pytest.approx(9.2738)
    assert engine._consecutive_failures_monthly == 0