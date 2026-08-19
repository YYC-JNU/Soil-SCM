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


# ==================== v0.6.0 run_monthly_step 聚合包装 (S1, Q10) ====================

def test_run_monthly_step_event_driven_loops_events(profile, soil_info,
                                                    monkeypatch):
    """Q10: event_driven 事件化包装 — 逐场循环, Σ事件降水 = 月降水"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    calls = []
    orig = e.run_event_step

    def spy(state, event, action, profile, forcing=None):
        calls.append((event.precip_mm,
                      forcing.get('inflow_water_L') if forcing else None))
        return orig(state, event, action, profile, forcing=forcing)

    monkeypatch.setattr(e, 'run_event_step', spy)
    forcing = dict(EVENT_FORCING, precip=100.0, event_driven=True,
                   seed=42, year=0, month=3)
    new_state, diag = e.run_monthly_step(state, forcing, MonthlyAction(),
                                         profile)
    assert len(calls) >= 4
    assert sum(c for c, _ in calls) == pytest.approx(100.0, rel=1e-6)
    assert new_state.ph > 0


def test_run_monthly_step_default_legacy_behavior(profile, soil_info,
                                                  monkeypatch):
    """Q10: 无 event_driven 标记 → 旧单次平衡路径 (expand 兼容门禁)"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    calls = []
    orig = e.run_event_step

    def spy(state, event, action, profile, forcing=None):
        calls.append(event.precip_mm)
        return orig(state, event, action, profile, forcing=forcing)

    monkeypatch.setattr(e, 'run_event_step', spy)
    forcing = dict(EVENT_FORCING, precip=100.0)
    new_state, diag = e.run_monthly_step(state, forcing, MonthlyAction(),
                                         profile)
    assert calls == []           # 未走事件路径
    assert new_state.ph > 0


# ==================== v0.6.0 多层 events 路径 (S5, Q4/Q10) ====================

def test_run_monthly_multi_layer_events_path(profile, soil_info):
    """Q4: hydrology['events'] → 逐场逐层级联 (层间溶质事件粒度)"""
    e = _engine()
    states = [e.build_initial_state(profile, soil_info, 0.015)
              for _ in range(2)]
    ev1 = {'inflows': [100000.0, 10000.0], 'drains': [10000.0, 1000.0],
           'bypass_water_L': 0.0, 'precip_mm': 15.0}
    ev2 = {'inflows': [200000.0, 20000.0], 'drains': [20000.0, 2000.0],
           'bypass_water_L': 0.0, 'precip_mm': 15.0}
    hydrology = {'events': [ev1, ev2], 'aet_mm': 0.0, 'et_deficit_mm': 0.0}
    forcing = dict(EVENT_FORCING, precip=30.0)
    new_states, diags = e.run_monthly_multi_layer(
        states, forcing, MonthlyAction(), profile, hydrology=hydrology)
    assert len(new_states) == 2
    assert all(s.ph > 0 for s in new_states)
    assert len(diags) == 2


def test_run_monthly_multi_layer_fallback_without_events(profile, soil_info):
    """Q10: 无 events 键 → 旧月级路径 (向后兼容护栏)"""
    e = _engine()
    states = [e.build_initial_state(profile, soil_info, 0.015)
              for _ in range(2)]
    hydrology = {'inflows': [100000.0, 10000.0], 'drains': [10000.0, 1000.0],
                 'bypass_water_L': 0.0, 'aet_mm': 0.0, 'et_deficit_mm': 0.0}
    forcing = dict(EVENT_FORCING, precip=100.0)
    new_states, diags = e.run_monthly_multi_layer(
        states, forcing, MonthlyAction(), profile, hydrology=hydrology)
    assert len(new_states) == 2
    assert all(s.ph > 0 for s in new_states)
    assert len(diags) == 2


def test_run_monthly_multi_layer_events_flush_peak(profile, soil_info):
    """Q14: events 路径 → L1 诊断携带 First-Flush 峰值 (月内最大单场)"""
    e = _engine()
    states = [e.build_initial_state(profile, soil_info, 0.015)
              for _ in range(2)]
    ev1 = {'inflows': [100000.0, 10000.0], 'drains': [10000.0, 1000.0],
           'bypass_water_L': 0.0, 'precip_mm': 15.0}
    ev2 = {'inflows': [200000.0, 20000.0], 'drains': [20000.0, 2000.0],
           'bypass_water_L': 0.0, 'precip_mm': 15.0}
    hydrology = {'events': [ev1, ev2], 'aet_mm': 0.0, 'et_deficit_mm': 0.0}
    forcing = dict(EVENT_FORCING, precip=30.0)
    new_states, diags = e.run_monthly_multi_layer(
        states, forcing, MonthlyAction(), profile, hydrology=hydrology)
    assert diags[0].flush_no3_peak_mmol > 0
    assert diags[0].flush_base_peak_mmol > 0
    # event_details 回填: 每场每层淋失 + pH (事件明细 CSV 用)
    assert len(hydrology['event_details']) == 2
    det = hydrology['event_details'][0]
    assert 'leach_N_L1_mmol' in det
    assert 'leach_base_L2_mmol' in det
    assert 'ph_L1' in det
    # 峰值 = 月内 L1 各场 max
    assert diags[0].flush_no3_peak_mmol == pytest.approx(
        max(det['leach_N_L1_mmol']
            for det in hydrology['event_details']), rel=1e-9)
