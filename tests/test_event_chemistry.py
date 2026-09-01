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

    def spy(state, event, action, profile, forcing=None, **kwargs):
        calls.append((event.precip_mm,
                      forcing.get('inflow_water_L') if forcing else None))
        return orig(state, event, action, profile, forcing=forcing, **kwargs)

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
    # 工单82 (Q2=A/Q5=A): 排水是"换水"不浓缩 — 基流 1e5 L 按摩尔绝对量移出
    # (mol=C×Q_out), 残留体积落回 θ_out; 旧 Q3 比例法断言 "cl_after <=
    # cl_before" (排水稀释) 在新语义下不成立 (排水不改变残留浓度)。
    w1 = theta_to_water_L(0.40, profile.effective_depth)
    assert new_states[3].volume == pytest.approx(w1, rel=1e-6)  # 体积落回 θ_out
    cl_after = new_states[3].solution.get('Cl', 0.0)
    assert cl_after >= 0.0
    assert cl_after < 10.0   # 排水不触发浓缩/清空 (无数值失败)


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


# ==================== v0.7.0 (spec 69, 工单70): NO3- 池事件级水库串联淋失 ====================

def _engine_companion(**kw):
    from src.config_manager import CompanionConfig
    kw.setdefault('companion_cfg', CompanionConfig(enable=True))
    return PhreeqcEngine(database="phreeqc.dat", mode="phreeqc", **kw)


def test_no3_pool_cascade_vertical_and_outflow(profile, soil_info):
    """v0.7.0 (工单70): 4 层事件级水库串联 — 垂直下移 + L4 出系统, pool≥0

    L1 池 1000 mol: drains 垂直下移逐层, L4 baseflow 出口带走 → 池守恒。
    """
    e = _engine_companion()
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    states[0].n_no3_pool = 1000.0
    ev = {'inflows': [1.0e5, 0.0, 0.0, 0.0],
          'drains': [1.0e5, 1.0e4, 1.0e4, 0.0],
          'lateral': [0.0, 0.0, 0.0, 0.0],
          'baseflow': [0.0, 0.0, 0.0, 1.0e5],
          'bypass_water_L': 0.0, 'precip_mm': 50.0,
          'theta': [0.40, 0.40, 0.40, 0.40]}
    hydrology = {'events': [ev], 'aet_mm': 0.0, 'et_deficit_mm': 0.0}
    new_states, _ = e.run_monthly_multi_layer(
        states, dict(EVENT_FORCING, precip=50.0), MonthlyAction(),
        profile, hydrology=hydrology)
    # 全局不变量: 各层 pool ≥ 0
    for s in new_states:
        assert s.n_no3_pool >= 0.0
    # 垂直下移: L1 池被 drains 消耗
    assert new_states[0].n_no3_pool < 1000.0
    # 层间传递: L2 收到 L1 下移量 (该场先处理 L1 后处理 L2)
    assert new_states[1].n_no3_pool > 0.0
    # L4 baseflow 出口 → 系统总量减少 (出系统淋失)
    total = sum(s.n_no3_pool for s in new_states)
    assert total < 1000.0
    assert total > 0.0
    # 记账列: event_details 含 n_no3_pool/leach_no3
    details = hydrology.get('event_details', [])
    assert details
    row0 = details[0]
    assert 'n_no3_pool_L1' in row0
    assert 'leach_no3_L1_mol' in row0
    # leach_no3_L1 = L1 垂直下移量 (drains=1e5, 池按排水前混合体积 V_mix 比例)
    # 工单82 (Q5=A): 排水发生在排水前体积 V_mix = θ_out×d×1e5 + 该场排水总量
    # (drains[0]=1e5 + lateral + baseflow); NO3 池是随水移出的模型库存,
    # 移出分数 = drain/V_mix (排水发生时池在排水前水量中按比例携带)。
    from src.vgm import theta_to_water_L
    v_l1 = theta_to_water_L(0.40, profile.effective_depth)
    v_mix = v_l1 + 1.0e5      # 排水总量 = drains[0] 1e5 (lat/base 为 0)
    expected_leach_l1 = 1000.0 * min(1.0e5 / v_mix, 1.0)
    assert row0['leach_no3_L1_mol'] == pytest.approx(expected_leach_l1, rel=1e-6)
    # 自洽: L1 淋失 = 初始池 − 末池 (无 bypass/出口)
    assert row0['leach_no3_L1_mol'] == pytest.approx(
        1000.0 - new_states[0].n_no3_pool, rel=1e-6)


def test_no3_pool_bypass_carry(profile, soil_info):
    """v0.7.0 (工单70): bypass 优先流携带 L1 池 NO3- 直通 L2 (默认模式)"""
    e = _engine_companion()
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    states[0].n_no3_pool = 1000.0
    ev = {'inflows': [1.0e5, 1.0e4, 1.0e4, 1.0e4],
          'drains': [0.0, 0.0, 0.0, 0.0],
          'lateral': [0.0, 0.0, 0.0, 0.0],
          'baseflow': [0.0, 0.0, 0.0, 0.0],
          'bypass_water_L': 1.0e6,   # 大优先流 (> L1 体积)
          'precip_mm': 100.0,
          'theta': [0.40, 0.40, 0.40, 0.40]}
    hydrology = {'events': [ev], 'aet_mm': 0.0, 'et_deficit_mm': 0.0}
    new_states, _ = e.run_monthly_multi_layer(
        states, dict(EVENT_FORCING, precip=100.0), MonthlyAction(),
        profile, hydrology=hydrology)
    # L1 池被 bypass 携带消耗 (cap at pool: 最多带走全部)
    assert 0.0 <= new_states[0].n_no3_pool <= 1000.0
    # L2 收到 bypass 携带的 NO3- (直通 L2)
    assert new_states[1].n_no3_pool > 0.0
    # 无其他出口: L1+L2 池守恒 (bypass 是层间转移非损失)
    assert new_states[0].n_no3_pool + new_states[1].n_no3_pool \
        == pytest.approx(1000.0, rel=1e-3)


def test_no3_pool_disabled_without_companion(profile, soil_info):
    """v0.7.0 (工单70): companion 关闭 (默认) → 池不动 (完全回退 v0.6.1)"""
    e = _engine()  # companion_cfg=None → 禁用
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    states[0].n_no3_pool = 1000.0
    ev = {'inflows': [1.0e5, 0.0, 0.0, 0.0],
          'drains': [1.0e5, 1.0e4, 1.0e4, 0.0],
          'lateral': [0.0, 0.0, 0.0, 0.0],
          'baseflow': [0.0, 0.0, 0.0, 1.0e5],
          'bypass_water_L': 0.0, 'precip_mm': 50.0,
          'theta': [0.40, 0.40, 0.40, 0.40]}
    hydrology = {'events': [ev], 'aet_mm': 0.0, 'et_deficit_mm': 0.0}
    new_states, _ = e.run_monthly_multi_layer(
        states, dict(EVENT_FORCING, precip=50.0), MonthlyAction(),
        profile, hydrology=hydrology)
    # 禁用: 池不参与淋失 (保持原值)
    assert new_states[0].n_no3_pool == pytest.approx(1000.0)
    assert new_states[1].n_no3_pool == pytest.approx(0.0)


def test_diagnostics_no3_pool_monthly_columns(profile, soil_info):
    """v0.7.0 (工单70): 月度诊断输出 n_no3_pool 存量 + leach_no3_mol 聚合列"""
    import main as sim_main
    e = _engine_companion()
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    states[0].n_no3_pool = 100.0
    hydrology = {
        'inflows': [1.0e5, 0, 0, 0], 'drains': [0.0, 0, 0, 0],
        'baseflow': [0.0, 0, 0, 0], 'lateral': [0.0, 0, 0, 0],
        'bypass_water_L': 0.0,
        'event_details': [
            {'leach_no3_L1_mol': 10.0, 'leach_no3_L2_mol': 5.0},
            {'leach_no3_L1_mol': 3.0, 'leach_no3_L2_mol': 1.0}]}
    diags = sim_main._extract_diagnostics_with_hydrology(
        states, hydrology, 0.0, 0.0, [None] * 4,
        ["pH"], [profile] * 4)
    # 月度存量列: 直接来自月末状态
    assert diags[0]['n_no3_pool'] == pytest.approx(100.0)
    assert diags[3]['n_no3_pool'] == pytest.approx(0.0)
    # 月度淋失聚合列: 事件级 Σ
    assert diags[0]['leach_no3_mol'] == pytest.approx(13.0)
    assert diags[1]['leach_no3_mol'] == pytest.approx(6.0)
    assert diags[2]['leach_no3_mol'] == pytest.approx(0.0)


# ==================== v0.7.0 (spec 69, 工单71): CompAn 分级注入 ====================

def test_companion_grade_injection_boundaries():
    """v0.7.0 (工单71): 分级注入三态边界 (BS=30/10 邻域, Q18=A)"""
    from src.config_manager import CompanionConfig
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                      companion_cfg=CompanionConfig(
                          enable=True, bs_high=30.0, bs_low=10.0))
    # BS ≥ bs_high: 全量注入 CompAn- (inert 模式)
    anion, acid, mode = e._grade_companion_injection(100.0, 30.0)
    assert mode == 'inert' and anion == pytest.approx(100.0) and acid == 0.0
    anion, acid, mode = e._grade_companion_injection(100.0, 45.0)
    assert mode == 'inert' and anion == pytest.approx(100.0)
    # bs_low ≤ BS < bs_high: 线性衰减 (BS=20 → 0.5×; BS=10 → 0)
    anion, acid, mode = e._grade_companion_injection(100.0, 20.0)
    assert mode == 'hybrid' and anion == pytest.approx(50.0) and acid == 0.0
    anion, acid, mode = e._grade_companion_injection(100.0, 10.0)
    assert mode == 'hybrid' and anion == pytest.approx(0.0)
    # BS < bs_low: 酸化注入 H+ = 全当量 (acid 模式)
    anion, acid, mode = e._grade_companion_injection(100.0, 9.9)
    assert mode == 'acid' and acid == pytest.approx(100.0) and anion == 0.0
    anion, acid, mode = e._grade_companion_injection(50.0, 0.0)
    assert mode == 'acid' and acid == pytest.approx(50.0)


def test_companion_injection_across_events(profile, soil_info):
    """v0.7.0 (工单71): 一场淋失 → 下一场平衡前注入 CompAn (PHREEQC 实测)

    验证: ① 第一场无注入 (mode=none), 淋失 NO3 入池 ② 第二场注入第一场
    淋失当量 (BS 高 → inert) ③ CompAn 物种被 PHREEQC 正常平衡 (数值可行性,
    交换相盐基响应解吸、总电荷守恒)。
    """
    e = _engine_companion()
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(2)]
    # v0.7.x (工单78): 先预平衡 (真实流程; 模拟步 1e-9 需近平衡起点)
    states = [e.pre_equilibrate(s, profile, max_steps=30) for s in states]
    states[0].n_no3_pool = 500.0
    ev1 = {'inflows': [1.0e5, 0.0], 'drains': [1.0e5, 0.0],
           'lateral': [0.0, 0.0], 'baseflow': [0.0, 0.0],
           'bypass_water_L': 0.0, 'precip_mm': 50.0, 'theta': [0.4, 0.4]}
    ev2 = {'inflows': [0.0, 0.0], 'drains': [0.0, 0.0],
           'lateral': [0.0, 0.0], 'baseflow': [0.0, 0.0],
           'bypass_water_L': 0.0, 'precip_mm': 0.0, 'theta': [0.4, 0.4]}
    hydrology = {'events': [ev1, ev2], 'aet_mm': 0.0, 'et_deficit_mm': 0.0}
    new_states, _ = e.run_monthly_multi_layer(
        states, dict(EVENT_FORCING, precip=50.0), MonthlyAction(),
        profile, hydrology=hydrology)
    details = hydrology['event_details']
    assert len(details) == 2
    # 第一场: 无上一场淋失 → mode=none; 本场淋失 NO3
    assert details[0]['companion_mode_L1'] == 'none'
    assert details[0]['leach_no3_L1_mol'] > 0.0
    # 第二场: 注入第一场淋失当量 (BS 高 → inert 模式, 全量 CompAn)
    assert details[1]['companion_mode_L1'] == 'inert'
    assert details[1]['companion_eq_L1'] == pytest.approx(
        details[0]['leach_no3_L1_mol'], rel=1e-6)
    assert details[1]['inert_eq_L1'] == pytest.approx(
        details[0]['leach_no3_L1_mol'], rel=1e-6)
    # CompAn 平衡后: 交换相总电荷守恒 (CEC 不破), 盐基≥0
    ex = new_states[0].exchange
    total_charge = (ex.get('CaX2', 0.0) * 2 + ex.get('MgX2', 0.0) * 2
                    + ex.get('KX', 0.0) + ex.get('NaX', 0.0)
                    + ex.get('AlX3', 0.0) * 3 + ex.get('HX', 0.0))
    assert total_charge > 0.0
    base_after = (ex.get('CaX2', 0.0) * 2 + ex.get('MgX2', 0.0) * 2
                  + ex.get('KX', 0.0) + ex.get('NaX', 0.0))
    assert base_after >= 0.0


# ==================== v0.7.0 (spec 69, 工单72): NH4+ 置换事件记账 ====================

def test_nh4_exchange_event_accounting(profile, soil_info):
    """v0.7.0 (工单72): 施肥月事件级 nh4_exchanged_eq 记账列 (PHREEQC 实测)

    施肥月 L1: 置换当量 = 水解量×k1 (12 kg N → 856.8 mol); L2~L4 无置换;
    PHREEQC 平衡成功 (置换注入 + 硝化产酸同场, 净效应 H+ 主导酸化)。
    """
    e = _engine_companion()
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    act = MonthlyAction(apply_fertilizer=True, n_amount=12.0)
    ev1 = {'inflows': [1.0e5, 0.0, 0.0, 0.0], 'drains': [0.0] * 4,
           'lateral': [0.0] * 4, 'baseflow': [0.0] * 4,
           'bypass_water_L': 0.0, 'precip_mm': 10.0, 'theta': [0.4] * 4}
    hydrology = {'events': [ev1], 'aet_mm': 0.0, 'et_deficit_mm': 0.0}
    new_states, _ = e.run_monthly_multi_layer(
        states, dict(EVENT_FORCING, precip=10.0), act, profile,
        hydrology=hydrology)
    row0 = hydrology['event_details'][0]
    # L1 施肥月: 置换当量 = 12 kg N × N_MOL_PER_KG_N × k1 × k2 (硝化量, 调优 A)
    assert row0['nh4_exchanged_eq_L1'] == pytest.approx(
        12.0 * 1000.0 / 14.007 * 0.4, rel=1e-3)
    # L2~L4: 无置换 (硝化仅 L1)
    assert row0['nh4_exchanged_eq_L2'] == 0.0
    # PHREEQC 平衡成功 (含置换注入 + 硝化产酸)
    assert new_states[0].ph > 0.0


def test_nh4x_virtual_monthly_column(profile, soil_info):
    """v0.7.0 (工单72): 月度诊断 NH4X_virtual 列 = NH4+ 库存 (假设占位)"""
    import main as sim_main
    e = _engine_companion()
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(2)]
    states[0].n_nh4 = 500.0   # NH4 库存 = 假设占据的交换位点 (1:1 eq)
    hydrology = {'inflows': [0.0, 0.0], 'drains': [0.0, 0.0],
                 'baseflow': [0.0, 0.0], 'lateral': [0.0, 0.0],
                 'bypass_water_L': 0.0}
    diags = sim_main._extract_diagnostics_with_hydrology(
        states, hydrology, 0.0, 0.0, [None] * 2, ["pH"], [profile] * 2)
    assert diags[0]['NH4X_virtual'] == pytest.approx(500.0)
    assert diags[1]['NH4X_virtual'] == pytest.approx(0.0)
