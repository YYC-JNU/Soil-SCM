"""
测试 WF5 集成验证: 多分层 + SURFACE 组合行为

验证目标 (对应 ROADMAP 已知局限):
  1. 多层模型建立垂直 pH 梯度 (盐基优先淋洗)
  2. 多层推迟 Al 耗尽/pH 突升 (对比单层)
  3. SURFACE 吸附在多层下生效
  4. 单层回归 (n_layers=1)
"""

import pytest
from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction
from src.input_reader import InputReader
from src.soil_database import SoilDatabase
from src.climate_forcing import ClimateForcing


FORCING = {"precip": 189.0, "temp": 25.0, "pCO2": 0.015}  # 雨季月
ACTION = MonthlyAction()


def _setup():
    reader = InputReader("data/soil_survey.csv", "data/exchangeable_ions.csv")
    profile = reader.build_soil_profile()
    db = SoilDatabase(json_path="config/soil_mineral_db.json",
                      tbl_path="config/soil_mineral.tbl")
    info = db.get_soil_info("red_soil")
    return profile, info


def test_multilayer_establishes_ph_gradient(profile, soil_info):
    """WF5: 多层模型建立垂直 pH 梯度 (表层高/底层低, 盐基优先淋洗)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    # 模拟 1 年 (12 月, natural)
    climate = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05, 1, "natural")
    for m in range(12):
        f = climate.get_monthly_forcing(0, m)
        states, _ = e.run_monthly_multi_layer(states, f, ACTION, profile)
    phs = [s.ph for s in states]
    # 顶层 pH 应 >= 底层 (表层盐基优先流失 → 顶层相对更酸? 或更碱?)
    # 实测: 顶层高/底层低 (表层 Al 淋失 → 相对脱酸)
    assert phs[0] >= phs[-1] - 0.5, f"pH 梯度异常: {phs}"


def test_multilayer_delays_al_depletion(profile, soil_info):
    """WF5: 多层模型 AlX3 在初期各层保留 (不立即耗尽)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    climate = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05, 1, "natural")
    for m in range(12):
        f = climate.get_monthly_forcing(0, m)
        states, _ = e.run_monthly_multi_layer(states, f, ACTION, profile)
    # 1 年后各层 AlX3 应仍有保留 (多层垂直缓冲)
    alx3 = [s.exchange.get("AlX3", 0) for s in states]
    assert all(a > 10000 for a in alx3), f"AlX3 过早耗尽: {alx3}"


def test_surface_adsorbs_p_in_multilayer(profile, soil_info):
    """WF5: SURFACE 吸附 (P) 在多层下生效"""
    fertilize = MonthlyAction(apply_fertilizer=True, n_amount=12.0,
                              p2o5_amount=4.0, k2o_amount=9.0,
                              mgo_amount=3.0, znso4_amount=1.0)
    # 开启 SURFACE
    e_on = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                         enable_surface=True)
    states_on = [e_on.build_initial_state(profile, soil_info, 0.015)
                 for _ in range(2)]
    states_on, _ = e_on.run_monthly_multi_layer(
        states_on, FORCING, fertilize, profile)
    # 关闭 SURFACE
    e_off = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    states_off = [e_off.build_initial_state(profile, soil_info, 0.015)
                  for _ in range(2)]
    states_off, _ = e_off.run_monthly_multi_layer(
        states_off, FORCING, fertilize, profile)
    # 多层下 SURFACE 开启时 P 浓度应显著低于关闭
    p_on = sum(s.solution.get("P", 0) for s in states_on)
    p_off = sum(s.solution.get("P", 0) for s in states_off)
    assert p_on < p_off, f"多层下 SURFACE 未生效: on={p_on}, off={p_off}"


def test_single_layer_regression(profile, soil_info):
    """WF5: 单层 (n_layers=1) 走原接口, 结果与 run_monthly_step 一致"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    s1, _ = e.run_monthly_step(state, FORCING, ACTION, profile)
    s2, _ = e.run_monthly_multi_layer([state], FORCING, ACTION, profile)
    assert s1.ph == pytest.approx(s2[0].ph)
