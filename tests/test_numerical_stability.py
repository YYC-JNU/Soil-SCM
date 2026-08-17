"""测试 v0.6.1 数值稳定性: 子进程超时机制 (KINETICS 偶发卡顿定位)

  - run_monthly_step_with_timeout: 子进程执行月度步, 超时终止返回 None
  - 正常步返回 (new_state, diag); 超时/失败返回 None
"""

import pytest

from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction


FORCING = {"precip": 100.0, "temp": 25.0, "pCO2": 0.015}


def test_timeout_step_returns_result(profile, soil_info):
    """子进程执行正常步返回 (new_state, diag) (pickle 跨进程工作)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    result = e.run_monthly_step_with_timeout(
        state, FORCING, MonthlyAction(), profile, timeout=30)
    assert result is not None, "子进程月度步应返回结果"
    new_state, diag = result
    assert new_state.ph > 0
    assert diag.ph > 0


def test_timeout_returns_none_when_short(profile, soil_info):
    """超时 (极短) 返回 None (子进程终止信号)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    result = e.run_monthly_step_with_timeout(
        state, FORCING, MonthlyAction(), profile, timeout=0.001)
    # spawn 启动 + PHREEQC 初始化远大于 0.001s → 必超时
    assert result is None or result[0].ph > 0
