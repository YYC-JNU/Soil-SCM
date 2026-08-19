"""测试 v0.6.0 事件驱动化学 (src/phreeqc_engine.py run_event_step):

  - run_event_step: 事件级化学步, 体积-θ 耦合 (Q5), 交换相/矿物相绝对量 (Q6)
  - apply_concentration_equilibrium: 月末浓缩平衡 (Q7/Q12)
  - 溶液浓度下限 1e-10 mol/L (数值稳定性)
"""

import pytest
from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction
from src.hydrology import RainEvent
from src.vgm import theta_to_water_L, water_L_to_theta


EVENT_FORCING = {"temp": 25.0, "pCO2": 0.015}


def _engine(mode="phreeqc"):
    return PhreeqcEngine(database="phreeqc.dat", mode=mode)


def test_run_event_step_volume_theta_coupled(profile, soil_info):
    """Q5: 事件后 new_state.volume = θ×depth×1e5 (体积-θ 耦合)"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    state.theta = 0.30
    ev = RainEvent(precip_mm=20.0)
    forcing = dict(EVENT_FORCING, inflow_water_L=200000.0)
    new_state, diag = e.run_event_step(state, ev, MonthlyAction(), profile,
                                       forcing=forcing)
    assert new_state.volume == pytest.approx(
        theta_to_water_L(0.30, profile.effective_depth), rel=1e-6)
    assert new_state.ph > 0


def test_run_event_step_no_h2o_injection(profile, soil_info):
    """体积耦合时 REACTION 不注入 H2O (水量由 -water 体现)"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    water_target = theta_to_water_L(0.30, profile.effective_depth)
    inp = e._build_phreeqc_input(
        state, dict(EVENT_FORCING, precip=20.0, inflow_water_L=200000.0),
        MonthlyAction(), profile, solution_water_L=water_target,
        inject_water=False)
    assert f"-water      {water_target:.6e}" in inp
    assert "H2O" not in inp


def test_run_event_step_volume_shrink_concentrates(profile, soil_info):
    """Q5: 体积缩小时浓度换算保持溶质绝对量守恒 (C_new = C_old×V_old/V_new)"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    vol_old = state.volume
    theta_new = water_L_to_theta(vol_old * 0.5, profile.effective_depth)
    state.theta = theta_new
    ev = RainEvent(precip_mm=0.0)
    new_state, _ = e.run_event_step(state, ev, MonthlyAction(), profile,
                                    forcing=dict(EVENT_FORCING,
                                                 inflow_water_L=0.0))
    # 无降水/无 inflow: 纯浓缩, 体积减半
    assert new_state.volume == pytest.approx(vol_old * 0.5, rel=1e-6)


def test_apply_concentration_equilibrium_triggers_on_shrink(profile, soil_info):
    """Q12: θ 下降 → 浓缩平衡, volume 缩小"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    vol_before = state.volume
    theta_shrunk = water_L_to_theta(vol_before * 0.6, profile.effective_depth)
    ns, diag = e.apply_concentration_equilibrium(state, theta_shrunk, profile,
                                                 dict(EVENT_FORCING))
    assert ns.volume == pytest.approx(
        theta_to_water_L(theta_shrunk, profile.effective_depth), rel=1e-6)
    assert ns.volume < vol_before


def test_apply_concentration_equilibrium_skips_when_not_shrunk(profile, soil_info):
    """Q12: θ 未下降 → 跳过, 零额外计算"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    theta_same = water_L_to_theta(state.volume, profile.effective_depth)
    ns, diag = e.apply_concentration_equilibrium(state, theta_same, profile,
                                                 dict(EVENT_FORCING))
    assert ns is state
    assert diag is None


def test_ion_concentration_floor(profile, soil_info):
    """数值稳定性: 溶液离子浓度下限 1e-10 mol/L (防 negative activity)"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    state.solution['Ca'] = 1e-14
    inp = e._build_phreeqc_input(
        state, dict(EVENT_FORCING, precip=0.0), MonthlyAction(), profile)
    ca_line = [l for l in inp.splitlines() if l.strip().startswith('Ca ')]
    assert ca_line and '1.000000e-10' in ca_line[0]


def test_run_event_step_exchange_evolves(profile, soil_info):
    """Q6: 事件级化学步后交换相按 PHREEQC 平衡演化 (非按体积缩放)"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    state.theta = 0.30
    ev = RainEvent(precip_mm=20.0)
    forcing = dict(EVENT_FORCING, inflow_water_L=200000.0)
    new_state, _ = e.run_event_step(state, ev, MonthlyAction(), profile,
                                    forcing=forcing)
    assert new_state.exchange != {}
    assert new_state.minerals != {}
