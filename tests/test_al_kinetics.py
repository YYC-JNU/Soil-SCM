"""测试 v0.6.0 Al 动力学 (KINETICS, 阻断矿物化单向 Al 汇)

  - gibbsite/Al(OH)3(a) 从 EQUILIBRIUM_PHASES 切到 KINETICS (RATES 速率控制)
  - SELECTED_OUTPUT -kinetics 输出动力学相摩尔量 (L2 回填双路径)
  - 其余矿物保持平衡路径 (EQUILIBRIUM_PHASES)
"""

import pytest

from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction
from src.constants import AL_KINETIC_RATE, AL_KINETIC_PHASES


FORCING = {"precip": 0.0, "temp": 25.0, "pCO2": 0.015}


def test_kinetics_constants_defined():
    """AL_KINETIC_RATE 初值与动力学相定义 (与 state.minerals 键一致)"""
    assert AL_KINETIC_RATE > 0
    assert 'gibbsite' in AL_KINETIC_PHASES
    assert 'Al(OH)3(a)' in AL_KINETIC_PHASES


def test_input_has_rates_and_kinetics(profile, soil_info):
    """输入含 RATES + KINETICS 块, Al 相不在 EQUILIBRIUM_PHASES"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "RATES" in inp
    assert "KINETICS" in inp
    # Al 动力学相在 KINETICS 块 (不在 EQUILIBRIUM_PHASES)
    kin_section = inp.split("KINETICS")[1].split("SELECTED_OUTPUT")[0]
    for ph in ('Gibbsite', 'Al(OH)3(a)'):
        assert ph in kin_section, ph
    # EQUILIBRIUM_PHASES 段不含 Al 动力学相
    eq_section = inp.split("EQUILIBRIUM_PHASES")[1].split("RATES")[0]
    assert "gibbsite" not in eq_section
    assert "Al(OH)3(a)" not in eq_section


def test_input_select_output_has_kinetics(profile, soil_info):
    """SELECTED_OUTPUT 含 -kinetics (L2 回填双路径)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "-kinetics" in inp


def test_kinetics_runs_and_backfills(profile, soil_info):
    """月度步可运行, 动力学相摩尔量回填 (L2 双路径)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    new_state, _ = e.run_monthly_step(state, FORCING, MonthlyAction(), profile)
    # 动力学相在 minerals 中 (回填后)
    assert 'gibbsite' in new_state.minerals
    assert 'Al(OH)3(a)' in new_state.minerals
    # 平衡相 (kaolinite) 不受影响
    assert 'kaolinite' in new_state.minerals
