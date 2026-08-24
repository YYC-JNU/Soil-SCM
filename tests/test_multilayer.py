"""
测试 WF2 多分层模型实现 (基于 WF1 架构决策):
  Q1: List[SoilState] 分层表示
  Q2: 一维平流层间迁移
  Q3: 级联下渗排水分配
  Q4: run_monthly_step 单层接口不变 + 新增 run_monthly_multi_layer 编排层
  Q7: SELECTED_OUTPUT totals × 排水水量 守恒核算
"""

import pytest
from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction


FORCING = {"precip": 100.0, "temp": 25.0, "pCO2": 0.015}
ACTION = MonthlyAction()
LAYER_DEPTHS = [10.0, 10.0, 20.0, 20.0]  # 4 层: 0-10/10-20/20-40/40-60cm


def _make_layers(profile, soil_info, n=4):
    """构建 n 层初始状态列表 (各层默认参数相同, ROADMAP 设计约束)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    states = []
    for _ in range(n):
        states.append(e.build_initial_state(profile, soil_info, 0.015))
    return e, states


def test_multi_layer_runs(profile, soil_info):
    """WF2: n_layers=4 完整月度步可运行, 返回相同数量状态"""
    e, states = _make_layers(profile, soil_info, 4)
    new_states, diags = e.run_monthly_multi_layer(
        states, FORCING, ACTION, profile)
    assert len(new_states) == 4
    assert len(diags) == 4
    for s, d in zip(new_states, diags):
        assert s.ph > 0
        assert d.ph > 0


def test_multi_layer_returns_new_state_objects(profile, soil_info):
    """WF2: 编排层返回新状态对象, 不就地修改输入"""
    e, states = _make_layers(profile, soil_info, 2)
    new_states, _ = e.run_monthly_multi_layer(states, FORCING, ACTION, profile)
    assert new_states[0] is not states[0]


def test_multi_layer_equivalent_to_single_when_n1(profile, soil_info):
    """WF2: 单层 (n=1) 走 run_monthly_multi_layer 与 run_monthly_step 数值一致 (回归护栏)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    new_single, diag_single = e.run_monthly_step(state, FORCING, ACTION, profile)

    states = [state]
    new_multi, diag_multi = e.run_monthly_multi_layer(
        states, FORCING, ACTION, profile)
    assert new_multi[0].ph == pytest.approx(new_single.ph)
    assert diag_multi[0].ph == pytest.approx(diag_single.ph)


def test_multi_layer_leaching_moves_solute_down(profile, soil_info):
    """WF2/Q7: 上层排水溶质应向下层传递 (级联下渗); 下层溶液离子总量不低于单层独立模拟"""
    e, states = _make_layers(profile, soil_info, 2)
    # v0.7.x (工单78): 先预平衡 (真实流程; 模拟步 1e-9 需近平衡起点)
    states = [e.pre_equilibrate(s, profile, max_steps=30) for s in states]
    # 运行两层多层模拟
    new_states, _ = e.run_monthly_multi_layer(states, FORCING, ACTION, profile)
    # 运行单层独立模拟 (两层分别跑 run_monthly_step, 无层间交换)
    e2 = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    s1 = e2.build_initial_state(profile, soil_info, 0.015)
    s2 = e2.build_initial_state(profile, soil_info, 0.015)
    s1 = e2.pre_equilibrate(s1, profile, max_steps=30)
    s2 = e2.pre_equilibrate(s2, profile, max_steps=30)
    ns1, _ = e2.run_monthly_step(s1, FORCING, ACTION, profile)
    ns2, _ = e2.run_monthly_step(s2, FORCING, ACTION, profile)

    # 多层模型下层溶液离子总量 ≥ 独立模拟下层 (因接收上层排水溶质)
    for ion in ("Ca", "Mg", "K"):
        multi_lower = new_states[1].solution.get(ion, 0.0)
        single_lower = ns2.solution.get(ion, 0.0)
        assert multi_lower > single_lower, f"{ion}: 下层离子未增加, 平流未生效"
