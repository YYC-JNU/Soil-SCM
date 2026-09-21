"""v0.7.x 工单78: KNOBS 收敛参数化测试 (高离子强度卡顿调优)

/grilling D1~D4 定案 (2026-08-24), 探针驱动的三阶段修复:
  1. 参数化: KNOBS_ITERATIONS/KNOBS_TOLERANCE/KNOBS_TOLERANCE_PRE/
     KNOBS_CONVERGENCE_TOLERANCE 入 constants (消除硬编码)
  2. 双 tolerance: 预平衡 (远起点) 用 KNOBS_TOLERANCE_PRE (1e-12, 宽松假收敛
     稳定; 1e-9 第一步迭代超限返回垃圾解 CaX2=0); 模拟步 (预平衡状态近平衡)
     用 KNOBS_TOLERANCE (1e-9, lime 高 pH 真收敛 10.18, 1e-12 静默假收敛 4.89)
  3. 收敛失败检测 + 宽松重试: 模拟步从远平衡起点 (未预平衡) 1e-9 超限 → 自动
     1e-12 重试 (防垃圾解污染状态链)
SURFACE 启用时 iterations 强制 1000。

工单90 (S4 产品化, 2026-09-20): 迭代预算降本 — 首次 500→100 (KNOBS_ITERATIONS /
_SHALLOW / _DEEP), 重试下限由 _run_official_step 内字面量 500 → KNOBS_RETRY_FLOOR=0
(重试预算 = max(首次 × KNOBS_RETRY_MULTIPLIER, 下限) = 200)。状态中性由 S0/S1
(低 pH 域) + S2 (lime_high 21y 三臂, 状态级 0/84 差异格) 证据支持; 生产闸门 =
natural 30y 逐位一致 + 8 情景迁移面 + 判据 v2。报告 PERF_LOCALIZATION.md §15。
本文件同步更新: 硬编码 500/1000 断言改为常量/预算推导 (`_retry` 助手)。
"""

import pytest

from src.constants import (KNOBS_ITERATIONS, KNOBS_ITERATIONS_SHALLOW,
                           KNOBS_ITERATIONS_DEEP, KNOBS_RETRY_MULTIPLIER,
                           KNOBS_RETRY_FLOOR, KNOBS_TOLERANCE,
                           KNOBS_TOLERANCE_PRE, KNOBS_CONVERGENCE_TOLERANCE)
from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction


def _retry(first, floor=None):
    """工单90: 重试预算推导 = max(首次 × KNOBS_RETRY_MULTIPLIER, 下限)"""
    fl = KNOBS_RETRY_FLOOR if floor is None else floor
    return max(int(first * KNOBS_RETRY_MULTIPLIER), fl)


FORCING = {"precip": 100.0, "temp": 25.0, "pCO2": 0.015}


def _engine(**kw):
    return PhreeqcEngine(database="phreeqc.dat", mode="phreeqc", **kw)


def test_knobs_constants_defined():
    """v0.7.x (工单78): KNOBS 常量存在且为合理值"""
    assert KNOBS_ITERATIONS >= 1
    assert 0.0 < KNOBS_TOLERANCE < 1.0
    assert 0.0 < KNOBS_TOLERANCE_PRE < 1.0
    assert 0.0 < KNOBS_CONVERGENCE_TOLERANCE < 1.0
    # 模拟 tolerance 应宽松于预平衡 (真收敛 vs 假收敛防护)
    assert KNOBS_TOLERANCE > KNOBS_TOLERANCE_PRE
    # 工单90: 迭代预算降本 — 首次 100 (浅/深/全局一致), 重试下限 0
    assert KNOBS_ITERATIONS_SHALLOW == KNOBS_ITERATIONS
    assert KNOBS_ITERATIONS_DEEP == KNOBS_ITERATIONS
    assert KNOBS_RETRY_MULTIPLIER >= 1.0
    assert KNOBS_RETRY_FLOOR >= 0
    # 重试预算须严格大于首次预算 (否则重试无意义)
    assert _retry(KNOBS_ITERATIONS) > KNOBS_ITERATIONS


def test_knobs_in_injection_string(profile, soil_info):
    """v0.7.x (工单78): _build_phreeqc_input (模拟步) 含参数化 KNOBS 行"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "KNOBS" in inp
    assert f"-iterations {KNOBS_ITERATIONS}" in inp
    assert f"-tolerance {KNOBS_TOLERANCE:.1e}" in inp
    assert (f"-convergence_tolerance "
            f"{KNOBS_CONVERGENCE_TOLERANCE:.1e}") in inp


def test_knobs_pre_equilibration_tolerance(profile, soil_info):
    """v0.7.x (工单78): 预平衡阶段 _build_phreeqc_input 用 KNOBS_TOLERANCE_PRE"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    e._in_pre_equilibration = True
    try:
        inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    finally:
        e._in_pre_equilibration = False
    assert f"-tolerance {KNOBS_TOLERANCE_PRE:.1e}" in inp
    # 显式 knobs_tolerance 覆盖
    inp2 = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                  knobs_tolerance=1e-6)
    assert "-tolerance 1.0e-06" in inp2


def test_knobs_surface_iterations_1000(profile, soil_info):
    """v0.7.x (工单78): SURFACE 启用时 iterations 强制 1000 (既有行为保持)"""
    e = _engine(enable_surface=True)
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "-iterations 1000" in inp


def test_knobs_no_step_size_line(profile, soil_info):
    """工单82 (数据驱动, 2026-08-25): KNOBS 块不注入 -step_size

    IPhreeqc 3.8.6 对 -step_size 行的**存在本身**敏感: 实测显式
    -step_size 0.2~0.001 全部使预平衡第一步 (远起点大交换相, 真实 red_soil
    数据) 数值发散 (Ca=2000/4000 垃圾解 + 交换相全 0), 仅缺省 (无该行)
    成功。工单78 引入此行且未被 351 测试/探针 13 暴露 (conftest 小交换相
    profile + 探针在预平衡降级后的 simplified 上跑) → v0.7.x 预平衡连续
    3 次失败永久降级 (spec 82 '首月即降级' 的真根因)。
    """
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "-step_size" not in inp


def test_knobs_sim_step_not_use_pre_tolerance(profile, soil_info):
    """工单82 (Q6=A): 模拟步输入不含 1e-12 (KNOBS_TOLERANCE_PRE)

    1e-12 静默假收敛 (lime 高 pH 4.89 错 vs 1e-9 10.18 对) 已由工单78证伪;
    模拟步必须 1e-9 真收敛, 失败走 fallback 计数而非宽松容差兜底。
    KNOBS_TOLERANCE_PRE 仅预平衡 (远起点宽松) 使用。
    """
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert f"-tolerance {KNOBS_TOLERANCE_PRE:.1e}" not in inp
    assert f"-tolerance {KNOBS_TOLERANCE:.1e}" in inp


def test_knobs_monkeypatched_values(profile, soil_info, monkeypatch):
    """v0.7.x (工单78): monkeypatch constants → 注入串跟随 (扫描机制验证)

    工单90 修正锚点: 引擎分层路径读 `pe.KNOBS_ITERATIONS_SHALLOW`, 容差读
    `src.phreeqc_input.KNOBS_TOLERANCE` (按值导入 → pe.* 补丁失效)。
    原测试 patch 的 `pe.KNOBS_ITERATIONS` / `pe.KNOBS_TOLERANCE` 均不生效,
    仅因当时字面量巧合相同而通过。
    """
    import src.phreeqc_engine as pe
    import src.phreeqc_input as pin
    monkeypatch.setattr(pe, "KNOBS_ITERATIONS_SHALLOW", 250)
    monkeypatch.setattr(pin, "KNOBS_TOLERANCE", 1e-8)
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "-iterations 250" in inp
    assert "-tolerance 1.0e-08" in inp


def test_knobs_convergence_warning_helpers(profile, soil_info):
    """v0.7.x (工单78): 收敛失败 warning 检测 (超限关键词, 无异常)"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    _ = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert e._warning_count() >= 0
    # 无新增警告时返回 False (count 未变)
    before = e._warning_count()
    assert e._has_new_convergence_warning(before) is False


def test_knobs_layer_iterations_deep(profile, soil_info, monkeypatch):
    """工单86 (2026-08-31): 深层 (L3/L4) KNOBS 迭代 = KNOBS_ITERATIONS_DEEP

    分层迭代机制 (layer_index 透传 → 深层用 DEEP 常量)。工单90 降本后
    深层=浅层=100; 机制验证: 上调 DEEP → 深层注入跟随, 浅层不受影响。
    """
    from src.constants import KNOBS_ITERATIONS_DEEP
    import src.phreeqc_engine as pe
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    for li in (2, 3):   # L3/L4 (索引 2/3)
        inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                     layer_index=li, n_layers=4)
        assert f"-iterations {KNOBS_ITERATIONS_DEEP}" in inp
    # 机制验证: DEEP 上调 → 深层注入跟随, 浅层保持
    monkeypatch.setattr(pe, "KNOBS_ITERATIONS_DEEP", 1000)
    inp2 = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                  layer_index=3, n_layers=4)
    assert "-iterations 1000" in inp2
    inp3 = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                  layer_index=0, n_layers=4)
    assert f"-iterations {KNOBS_ITERATIONS_SHALLOW}" in inp3


def test_knobs_layer_iterations_shallow(profile, soil_info):
    """工单86/90: 浅层 (L1/L2) KNOBS 迭代 = KNOBS_ITERATIONS_SHALLOW
    (工单90 降本后 = 100)"""
    from src.constants import KNOBS_ITERATIONS_SHALLOW
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    for li in (0, 1):   # L1/L2 (索引 0/1)
        inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                     layer_index=li, n_layers=4)
        assert f"-iterations {KNOBS_ITERATIONS_SHALLOW}" in inp


def test_knobs_layer_none_default_unchanged(profile, soil_info):
    """工单86/90: 不传层 (单层/直接调用/预平衡) 走浅层默认

    引擎分层路径的"默认"即 KNOBS_ITERATIONS_SHALLOW (工单90 前该值与全局
    KNOBS_ITERATIONS 同为 500, 现同为 100 — 一致性由 constants 测试守卫)。
    """
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert f"-iterations {KNOBS_ITERATIONS_SHALLOW}" in inp
    # 单层 (n_layers=1) 护栏: 即使传 layer_index 也走默认, 不切深层
    inp1 = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                  layer_index=0, n_layers=1)
    assert f"-iterations {KNOBS_ITERATIONS_SHALLOW}" in inp1


def test_knobs_surface_still_1000_with_layer(profile, soil_info):
    """工单86 (2026-08-31): SURFACE 启用时 iterations 强制 1000 优先于分层"""
    e = _engine(enable_surface=True)
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                 layer_index=3, n_layers=4)
    assert "-iterations 1000" in inp


def test_knobs_retry_follows_layer_iterations(profile, soil_info, monkeypatch):
    """工单86/90: 重试迭代跟随分层首次迭代 × 倍数 (+ 下限)

    工单90 后 深层=浅层=100 → 重试 200 (原 500→1000); 机制验证:
    DEEP 上调 → 深层重试跟随翻倍。
    """
    import src.phreeqc_engine as pe
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    calls = []
    monkeypatch.setattr(e.official, "RunString", lambda s: calls.append(s))
    # 首次 RunString 后判定超限 (len==1 → True), 重试后收敛 (len==2 → False)
    monkeypatch.setattr(e, "_has_new_convergence_warning",
                        lambda before: len(calls) == 1)
    monkeypatch.setattr(e, "_parse_official_output",
                        lambda state, **kw: (state, None))
    # 深层: 首次 = DEEP, 重试 = _retry(DEEP)
    e._run_official_step(state, dict(FORCING), MonthlyAction(), profile,
                         layer_index=3, n_layers=4)
    assert len(calls) == 2
    assert f"-iterations {KNOBS_ITERATIONS_DEEP}" in calls[0]
    assert f"-iterations {_retry(KNOBS_ITERATIONS_DEEP)}" in calls[1]
    # 机制验证: DEEP=800 → 深层首次 800, 重试 1600
    monkeypatch.setattr(pe, "KNOBS_ITERATIONS_DEEP", 800)
    calls.clear()
    e._run_official_step(state, dict(FORCING), MonthlyAction(), profile,
                         layer_index=3, n_layers=4)
    assert len(calls) == 2
    assert "-iterations 800" in calls[0]
    assert "-iterations 1600" in calls[1]
    # 浅层: 首次 = SHALLOW, 重试 = _retry(SHALLOW) (不受 DEEP 影响)
    calls.clear()
    e._run_official_step(state, dict(FORCING), MonthlyAction(), profile,
                         layer_index=0, n_layers=4)
    assert len(calls) == 2
    assert f"-iterations {KNOBS_ITERATIONS_SHALLOW}" in calls[0]
    assert f"-iterations {_retry(KNOBS_ITERATIONS_SHALLOW)}" in calls[1]


def test_knobs_retry_floor_dominates(profile, soil_info, monkeypatch):
    """工单90: 重试下限语义 (原硬编码字面量 500 → KNOBS_RETRY_FLOOR)

    默认 FLOOR=0 ⇒ 重试预算完全由倍数决定 (100→200, 即 S2 验证口径);
    下限高于倍数预算时以下限为准 (如 FLOOR=500 → 重试 500)。
    """
    import src.phreeqc_engine as pe
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    calls = []
    monkeypatch.setattr(e.official, "RunString", lambda s: calls.append(s))
    monkeypatch.setattr(e, "_has_new_convergence_warning",
                        lambda before: len(calls) == 1)
    monkeypatch.setattr(e, "_parse_official_output",
                        lambda state, **kw: (state, None))
    # 默认: 重试 = 2 × 100 = 200 (< 旧字面量 500)
    e._run_official_step(state, dict(FORCING), MonthlyAction(), profile,
                         layer_index=0, n_layers=4)
    assert len(calls) == 2
    assert f"-iterations {_retry(KNOBS_ITERATIONS_SHALLOW)}" in calls[1]
    assert _retry(KNOBS_ITERATIONS_SHALLOW) == 200
    assert KNOBS_RETRY_FLOOR == 0
    # 下限抬高到 500 → 重试预算跟随下限
    monkeypatch.setattr(pe, "KNOBS_RETRY_FLOOR", 500)
    calls.clear()
    e._run_official_step(state, dict(FORCING), MonthlyAction(), profile,
                         layer_index=0, n_layers=4)
    assert len(calls) == 2
    assert "-iterations 500" in calls[1]


def test_knobs_multi_layer_passes_layer_index(profile, soil_info, monkeypatch):
    """工单86 (2026-08-31): run_monthly_multi_layer 透传层索引 → 深层注入 1000

    月级循环每层传 layer_index=i, n_layers=n; 深层 (L3/L4) 由 _build_phreeqc_input
    用 KNOBS_ITERATIONS_DEEP 注入 (deep/shallow 注入串已由上面两个测试验证)。
    """
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    states = [state, state, state, state]
    seen = []
    monkeypatch.setattr(
        e, "run_monthly_step",
        lambda st, forcing, action, prof, **kw:
            (seen.append((kw.get('layer_index'), kw.get('n_layers'))) or (st, None)))
    e.run_monthly_multi_layer(states, dict(FORCING), MonthlyAction(), profile)
    assert [li for li, _ in seen] == [0, 1, 2, 3]
    assert all(nl == 4 for _, nl in seen)


def test_knobs_high_ph_state_boosts_retry_budget(profile, soil_info,
                                                 monkeypatch):
    """工单88 D4 (2026-09-09): 高 pH 状态 (ph≥9) 重试迭代预算提高到 2000

    v88s lime_high y18 后 ph≈10.8 强碱态 PHREEQC 迭代超限 → 单场跳过 →
    状态冻结 (y19~y30 锁死 10.848, D4 伪影)。修复: 高 pH 状态重试迭代预算
    抬高至 KNOBS_HIGH_PH_RETRY_ITERATIONS = 2000, 提高 1e-9 真收敛成功率。
    正常 pH (ph<9) 状态走倍数预算 (工单90 降本后 = 200)。
    """
    from src.constants import (KNOBS_HIGH_PH_RETRY_THRESHOLD,
                               KNOBS_HIGH_PH_RETRY_ITERATIONS)
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    calls = []
    monkeypatch.setattr(e.official, "RunString", lambda s: calls.append(s))
    # 首次 RunString 后判定超限 (len==1 → True), 重试后收敛 (len==2 → False)
    monkeypatch.setattr(e, "_has_new_convergence_warning",
                        lambda before: len(calls) == 1)
    monkeypatch.setattr(e, "_parse_official_output",
                        lambda state, **kw: (state, None))
    # 高 pH 状态: 重试迭代应为 2000 (提高预算)
    state.ph = KNOBS_HIGH_PH_RETRY_THRESHOLD + 1.0   # 10.0 ≥ 9.0
    e._run_official_step(state, dict(FORCING), MonthlyAction(), profile,
                         layer_index=0, n_layers=4)
    assert len(calls) == 2
    assert f"-iterations {KNOBS_ITERATIONS_SHALLOW}" in calls[0]
    # 高 pH: 重试预算被 2000 抬高 (max(_retry(100)=200, 2000) = 2000)
    assert f"-iterations {KNOBS_HIGH_PH_RETRY_ITERATIONS}" in calls[1]
    # 正常 pH 状态: 重试按倍数预算 (工单90 后 200, 不受 D4 影响)
    calls.clear()
    state.ph = 7.0
    e._run_official_step(state, dict(FORCING), MonthlyAction(), profile,
                         layer_index=0, n_layers=4)
    assert len(calls) == 2
    assert f"-iterations {_retry(KNOBS_ITERATIONS_SHALLOW)}" in calls[1]

