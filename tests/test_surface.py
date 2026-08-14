"""
测试 WF4 SURFACE 表面络合启用 (阶段一: Hfo_s/Hfo_w 铁氧化物表面)

决策 (WF3 调研 + /grilling):
  - Q2 调整: Al 表面络合推迟 (四源查证无标准数据), 阶段一仅启用 Hfo_s/Hfo_w
  - Hfo_s/Hfo_w 按 Dzombak & Morel 强:弱 = 10%:90% 拆分
  - 有机质表面 (Som) 不启用 (phreeqc.dat 无对应物种)
"""

import pytest
from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction
from src.initial_condition import InitialConditionBuilder

FORCING = {"precip": 100.0, "temp": 25.0, "pCO2": 0.015}
ACTION = MonthlyAction()


def _builder(profile, soil_info):
    return InitialConditionBuilder(profile, soil_info, pCO2=0.015)


def test_build_surface_hfo_area(profile, soil_info):
    """WF4: build_surface() 返回铁氧化物表面积 (供 SURFACE 块)"""
    b = _builder(profile, soil_info)
    surface = b.build_surface()
    assert surface is not None
    assert "area_m2" in surface
    assert surface["area_m2"] > 0


def test_build_surface_positive(profile, soil_info):
    """WF4: 红壤含针铁矿/赤铁矿, 表面积应为正"""
    b = _builder(profile, soil_info)
    surface = b.build_surface()
    assert surface["area_m2"] > 0


def test_engine_input_contains_surface_when_enabled(profile, soil_info):
    """WF4: 引擎 _build_phreeqc_input 在 enable_surface=True 时含 SURFACE 块"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                      enable_surface=True)
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, ACTION, profile)
    assert "SURFACE 1" in inp
    assert "Hfo_s" in inp
    assert "Hfo_w" in inp
    assert "-equilibrate with solution 1" in inp


def test_engine_input_no_surface_when_disabled(profile, soil_info):
    """WF4: 默认 (enable_surface=False) 时输入无 SURFACE 块 (回归护栏)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, ACTION, profile)
    assert "SURFACE 1" not in inp


def test_initial_state_has_surface_field(profile, soil_info):
    """WF4: SoilState 含 surface 字段 (启用时填充 area_m2)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                      enable_surface=True)
    state = e.build_initial_state(profile, soil_info, 0.015)
    assert hasattr(state, "surface")
    assert "area_m2" in state.surface
    assert state.surface["area_m2"] > 0


def test_surface_enabled_runs_and_converges(profile, soil_info):
    """WF4: 启用 SURFACE 后月度步可运行且收敛 (无永久降级)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                      enable_surface=True)
    state = e.build_initial_state(profile, soil_info, 0.015)
    new_state, diag = e.run_monthly_step(state, FORCING, ACTION, profile)
    assert new_state.ph > 0
    assert not e._permanent_fallback   # 无降级
    # 表面面积保留在新状态中
    assert "area_m2" in new_state.surface


def test_surface_adsorbs_p_zn(profile, soil_info):
    """WF4: 启用 SURFACE 后, 施肥带入的 P/Zn 被铁氧化物吸附 (浓度显著降低)

    红壤磷固定现象: Hfo 对磷酸盐 (log_k 31.29) 与 Zn (log_k 0.99) 强吸附。
    """
    fertilize = MonthlyAction(apply_fertilizer=True, n_amount=12.0,
                              p2o5_amount=4.0, k2o_amount=9.0,
                              mgo_amount=3.0, znso4_amount=1.0)
    # 开启 SURFACE
    e_on = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                         enable_surface=True)
    s_on = e_on.build_initial_state(profile, soil_info, 0.015)
    s_on, _ = e_on.run_monthly_step(s_on, FORCING, fertilize, profile)
    # 关闭 SURFACE
    e_off = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    s_off = e_off.build_initial_state(profile, soil_info, 0.015)
    s_off, _ = e_off.run_monthly_step(s_off, FORCING, fertilize, profile)

    for ion in ("P", "Zn"):
        on_v = s_on.solution.get(ion, 0.0)
        off_v = s_off.solution.get(ion, 0.0)
        assert on_v < off_v, f"{ion}: SURFACE 开启后浓度未降低 (on={on_v}, off={off_v})"
