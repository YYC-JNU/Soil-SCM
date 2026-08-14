"""测试 L4 硝化两步动力学 (简化一阶, v0.3.0):

  尿素 → NH₄⁺ (k1 水解) → NO₃⁻ (k2 硝化, 库存层)

  - 氮形态 (尿素/NH4+/NO3-) 为模型库存, 不注入 PHREEQC 溶液平衡 (Q1=A:
    phreeqc.dat 的 N 氧化还原平衡会把注入的无机氮全部转为 N2)
  - 硝化产酸 2H+/mol N 注入 REACTION (Q3=A: 酸化效应真实进入溶液)
  - advance_nitrification 为模块级独立函数 (升级空间: 可替换为 KINETICS)
  - simplified 引擎保持现状 (Q9=A), 仅占位传递氮库存
"""

import inspect

import pytest

from src import phreeqc_engine
from src.phreeqc_engine import (PhreeqcEngine, SoilState,
                                advance_nitrification)
from src.scenario_controller import MonthlyAction
from src.constants import (NITRIFICATION_K1, NITRIFICATION_K2,
                           N_MOL_PER_KG_N)


FORCING = {"precip": 0.0, "temp": 25.0, "pCO2": 0.015}


def test_soil_state_has_n_fields():
    """SoilState 含氮形态字段 (尿素/NH4+/NO3- 库存, mol N)"""
    s = SoilState()
    assert hasattr(s, 'n_urea')
    assert hasattr(s, 'n_nh4')
    assert hasattr(s, 'n_no3')


def test_n_constants_defined():
    """k1/k2 默认值进 constants.py (Q10: 可配置参数文档化)"""
    assert NITRIFICATION_K1 == 1.0
    assert NITRIFICATION_K2 == 0.4
    # kg N → mol N (N 原子量 14.007)
    assert abs(N_MOL_PER_KG_N - 1000.0 / 14.007) < 1e-6


def test_urea_hydrolysis_full_with_k1_one():
    """k1=1.0: 尿素当月全水解为 NH4+ (库存); k2=0 无硝化无产酸"""
    s = SoilState(n_urea=100.0, n_nh4=0.0, n_no3=0.0)
    r = advance_nitrification(s, MonthlyAction(), k1=1.0, k2=0.0)
    assert s.n_urea == pytest.approx(0.0)
    assert s.n_nh4 == pytest.approx(100.0)
    assert r == {'H+': 0.0}


def test_nitrification_k2_ratio():
    """k2=0.4: 40% NH4+ 硝化, 60% 库存保留; 产酸 H+ = 2×硝化量"""
    s = SoilState(n_urea=0.0, n_nh4=100.0, n_no3=0.0)
    r = advance_nitrification(s, MonthlyAction(), k1=1.0, k2=0.4)
    assert r['H+'] == pytest.approx(80.0)   # 40 mol 硝化 × 2
    assert s.n_nh4 == pytest.approx(60.0)
    assert s.n_no3 == pytest.approx(40.0)


def test_nitrification_produces_two_protons_per_n():
    """硝化产酸守恒: H+ = 2 × 硝化量"""
    s = SoilState(n_urea=0.0, n_nh4=50.0, n_no3=0.0)
    r = advance_nitrification(s, MonthlyAction(), k1=1.0, k2=0.4)
    assert r['H+'] == pytest.approx(2.0 * 50.0 * 0.4)


def test_fertilizer_adds_urea_to_inventory():
    """施肥: N 以尿素形式入库存, 当月水解+硝化 (k1=1, k2=0.4)"""
    s = SoilState()
    act = MonthlyAction(apply_fertilizer=True, n_amount=14.007)  # 1000 mol N
    r = advance_nitrification(s, act, k1=1.0, k2=0.4)
    assert r['H+'] == pytest.approx(800.0)  # 400 mol 硝化 × 2
    assert s.n_nh4 == pytest.approx(600.0)
    assert s.n_no3 == pytest.approx(400.0)


def test_no_fertilizer_no_n_reaction(profile, soil_info):
    """无施肥且无库存: REACTION 无氮反应行"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "NH4+" not in inp
    assert "# 硝化产酸" not in inp


def test_fertilizer_month_input_acid_only(profile, soil_info):
    """施肥月: REACTION 只注入硝化产酸 H+ (Q1=A: 无 NH4+/NO3- 注入)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    act = MonthlyAction(apply_fertilizer=True, n_amount=12.0)
    inp = e._build_phreeqc_input(state, FORCING, act, profile)
    assert "# 硝化产酸" in inp      # 产酸进入 REACTION
    assert "NH4+" not in inp        # NH4+ 不注入 (避免被 N2 平衡吞没)
    assert "NO3-" not in inp        # NO3- 不注入


def test_select_output_no_n_species(profile, soil_info):
    """SELECTED_OUTPUT 无 N(-3)/N(5) (库存为模型状态, 无需溶液回填)

    注意: SOLUTION 块含 N(5) 是初始溶液 NO3- 浓度 (既有行为), 本断言
    针对 SELECTED_OUTPUT 的 -totals 行。
    """
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    # SELECTED_OUTPUT 的 totals 行无 N(-3)/N(5) (L4: 氮库存为模型状态)
    assert "-totals Ca Mg K Na Al P Zn Cl C S N Si F" in inp


def test_advance_nitrification_is_module_level():
    """升级空间: advance_nitrification 为模块级函数 (可替换为 KINETICS)"""
    assert inspect.isfunction(phreeqc_engine.advance_nitrification)


def test_n_state_preserved_across_steps(profile, soil_info):
    """月度步间氮库存由模型推进 (不被溶液输出覆盖, Q4=A)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    act = MonthlyAction(apply_fertilizer=True, n_amount=12.0)
    s1, _ = e.run_monthly_step(state, FORCING, act, profile)
    # 施肥月: 尿素水解 857 mol + 40% 硝化 → NH4 保留, NO3 累计
    assert s1.n_nh4 > 0.0
    assert s1.n_no3 > 0.0
    assert s1.n_nh4 == s1.n_nh4 and s1.n_no3 == s1.n_no3  # 非 NaN
    # 第二个月无施肥: NH4 继续硝化递减, NO3 累计 (Q4=A)
    s2, _ = e.run_monthly_step(s1, FORCING, MonthlyAction(), profile)
    assert s2.n_nh4 <= s1.n_nh4
    assert s2.n_no3 >= s1.n_no3


def test_simplified_preserves_n_state(profile, soil_info):
    """simplified 模式: 氮库存占位保留 (不参与硝化逻辑, Q9=A)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="simplified")
    state = e.build_initial_state(profile, soil_info, 0.015)
    state.n_nh4 = 42.0
    new_state, _ = e.run_monthly_step(state, FORCING,
                                      MonthlyAction(), profile)
    assert new_state.n_nh4 == 42.0
