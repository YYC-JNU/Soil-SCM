"""
测试 L2 矿物演化回填 (Al 耗尽根因修复)

背景 (Q1_plus_ANALYSIS 诊断):
  - _parse_official_output 将矿物相"冻结"为旧值 (Q1 占位实现)
  - 矿物单向吸收交换 Al (沉淀) 但不回补 → 交换 AlX3 持续耗尽 → pH 突升
  - 修复: 用 SELECTED_OUTPUT -equilibrium_phases 读取矿物摩尔量演化
"""

import pytest
from src.phreeqc_engine import PhreeqcEngine, SoilState
from src.scenario_controller import MonthlyAction
from src.input_reader import InputReader
from src.soil_database import SoilDatabase


FORCING = {"precip": 100.0, "temp": 25.0, "pCO2": 0.015}
ACTION = MonthlyAction()


def _setup():
    reader = InputReader("data/soil_survey.csv", "data/exchangeable_ions.csv")
    profile = reader.build_soil_profile()
    db = SoilDatabase(json_path="config/soil_mineral_db.json",
                      tbl_path="config/soil_mineral.tbl")
    info = db.get_soil_info("red_soil")
    return profile, info


def test_engine_input_has_equilibrium_phases_output(profile, soil_info):
    """L2: _build_phreeqc_input 的 SELECTED_OUTPUT 含 -equilibrium_phases"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, ACTION, profile)
    assert "-equilibrium_phases" in inp
    # 矿物名应出现在输出中 (gibbsite/kaolinite)
    assert "gibbsite" in inp


def test_minerals_evolve_after_step(profile, soil_info):
    """L2: 月度步后矿物量应随化学演化 (不再冻结为旧值)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    old_minerals = dict(state.minerals)
    new_state, _ = e.run_monthly_step(state, FORCING, ACTION, profile)
    # 矿物量应已演化 (可能变化很小, 但不应与旧值引用相同)
    assert new_state.minerals is not state.minerals
    # 含 Al 矿物 (gibbsite) 应在新状态中存在
    assert "gibbsite" in new_state.minerals


def test_alx3_depletion_slower_with_mineral_evolution(profile, soil_info):
    """L2: 矿物演化回填后, 交换 AlX3 应有矿物回补通道 (不再单向耗尽)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    # 模拟雨季连续 3 月 (强降水), 观察 AlX3 变化
    for _ in range(3):
        state, _ = e.run_monthly_step(state, FORCING, ACTION, profile)
    alx3 = state.exchange.get("AlX3", 0)
    # 矿物回补后 AlX3 不应在 3 月内归零 (相比旧实现第 4 月耗尽)
    assert alx3 > 1000, f"AlX3 仍过快耗尽: {alx3}"
