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
"""

import pytest

from src.constants import (KNOBS_ITERATIONS, KNOBS_TOLERANCE,
                           KNOBS_TOLERANCE_PRE, KNOBS_CONVERGENCE_TOLERANCE)
from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction


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


def test_knobs_monkeypatched_values(profile, soil_info, monkeypatch):
    """v0.7.x (工单78): monkeypatch constants → 注入串跟随 (扫描机制验证)"""
    import src.phreeqc_engine as pe
    monkeypatch.setattr(pe, "KNOBS_ITERATIONS", 500)
    monkeypatch.setattr(pe, "KNOBS_TOLERANCE", 1e-9)
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "-iterations 500" in inp
    assert "-tolerance 1.0e-09" in inp


def test_knobs_convergence_warning_helpers(profile, soil_info):
    """v0.7.x (工单78): 收敛失败 warning 检测 (超限关键词, 无异常)"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    _ = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert e._warning_count() >= 0
    # 无新增警告时返回 False (count 未变)
    before = e._warning_count()
    assert e._has_new_convergence_warning(before) is False

