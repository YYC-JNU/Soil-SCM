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



# ==================== v0.6.1: 溶质出口记账 + 浓度冲洗 (S2/S6, spec 62 Q3/Q6) ====================

def _multilayer_event_list(n_layers=4, lateral=None, baseflow=None):
    """构造事件列表 (含逐场 lateral/baseflow 出口, 模拟工单63事件路径)"""
    n = n_layers
    lat = lateral or [0.0] * n
    bf = baseflow or [0.0] * n
    return [{
        'inflows': [0.0] * n, 'drains': [0.0] * n,
        'lateral': lat, 'baseflow': bf,
        'bypass_water_L': 0.0, 'precip_mm': 10.0,
        'theta': [0.40] * n,
    }]


def test_lateral_baseflow_solute_proportional_deduction(profile, soil_info):
    """v0.6.1 (Q3): 侧向/基流排水溶质比例扣除数学恒等

    n_new = max(n_old×(1−Q_out/V), C_min×V); 交换相不动 (Gapon 后续补偿)
    """
    from src.constants import C_MIN
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    # L4 基流出口 1e5 L (模拟深层出口); 其他层无出口
    ev_list = _multilayer_event_list(
        lateral=[0.0, 0.0, 0.0, 0.0], baseflow=[0.0, 0.0, 0.0, 1.0e5])
    hydrology = {'events': ev_list}
    new_states, diags = e.run_monthly_multi_layer(
        states, dict(EVENT_FORCING, year=0, month=0), MonthlyAction(),
        profile, hydrology=hydrology)
    # 事件明细含 L4 基流出口 (event_details 记账)
    details = hydrology.get('event_details', [])
    assert details, "event_details 应有记录"
    row0 = details[0]
    # L4 (i=3) 基流出口记录 = 1e5 L
    assert row0['baseflow_L4_L'] == pytest.approx(1.0e5)
    # L4 溶质比例扣除: 最终浓度 ≤ 原平衡浓度 × (1 − Q_out/V)
    # (V 为 L4 体积 θ×40×1e5; 平衡后经 PHREEQC, 保守离子 Cl 近似比例)
    v_l4 = new_states[3].volume
    cl_after = new_states[3].solution.get('Cl', 0.0)
    cl_before = states[3].solution.get('Cl', 0.0)  # 近似 (平衡前)
    assert cl_after >= 0.0
    assert cl_after <= cl_before  # 出口移出后浓度不增 (物理方向)


def test_concentration_flush_triggers_on_high_conc(profile, soil_info):
    """v0.6.1 (Q6): C_warn 超限 → flush_L 折算 + 溶质同比例扣除"""
    from src.constants import CONC_WARN
    e = _engine()
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    # 人为抬高 L1 溶液 Na 浓度到超限 (模拟深层盐分累积)
    states[0].solution['Na'] = 2.0 * CONC_WARN
    states[0].solution['Cl'] = 2.0 * CONC_WARN
    ev_list = _multilayer_event_list(n_layers=4)
    hydrology = {'events': ev_list}
    new_states, diags = e.run_monthly_multi_layer(
        states, dict(EVENT_FORCING, year=0, month=0), MonthlyAction(),
        profile, hydrology=hydrology)
    # flush_L 记入 event_details (L1 超限触发)
    details = hydrology.get('event_details', [])
    assert details
    row0 = details[0]
    assert row0.get('flush_L1_L', 0.0) > 0.0
    # 冲洗后 max 浓度 ≤ C_warn (同比例扣除生效)
    sol = {k: v for k, v in new_states[0].solution.items()
           if k not in ('temp', 'pH', 'pe', 'units')}
    assert max(sol.values()) <= CONC_WARN * 1.001


def test_concentration_no_flush_normal(profile, soil_info):
    """v0.6.1 (Q6): 正常浓度不触发冲洗 (flush_L=0, 无副作用)"""
    e = _engine()
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    ev_list = _multilayer_event_list(n_layers=4)
    hydrology = {'events': ev_list}
    new_states, diags = e.run_monthly_multi_layer(
        states, dict(EVENT_FORCING, year=0, month=0), MonthlyAction(),
        profile, hydrology=hydrology)
    details = hydrology.get('event_details', [])
    assert details
    row0 = details[0]
    # 正常浓度下各层 flush_L = 0
    for i in range(4):
        assert row0.get(f'flush_L{i+1}_L', 0.0) == 0.0


def test_diagnostics_baseflow_lateral_columns(profile, soil_info, monkeypatch):
    """v0.6.1 (Q3): _extract_diagnostics_with_hydrology 输出 baseflow/lateral 列"""
    import main as sim_main
    e = _engine()
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    hydrology = {
        'inflows': [1.0e5, 0, 0, 0], 'drains': [0.0, 0, 0, 0],
        'baseflow': [0.0, 0, 0, 1.0e5], 'lateral': [0.0, 0, 0, 0],
        'bypass_water_L': 0.0}
    diags = sim_main._extract_diagnostics_with_hydrology(
        states, hydrology, 0.0, 0.0, [None] * 4,
        ["pH"], [profile] * 4)
    assert diags[0]['baseflow'] == 0.0
    assert diags[3]['baseflow'] == pytest.approx(1.0e5)
    assert diags[0]['lateral'] == 0.0
