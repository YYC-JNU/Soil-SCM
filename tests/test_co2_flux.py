"""测试 工单95 (2026-09-29): CO₂ 去气通量观测 (开体系酸汇显式入账; **只读**)

覆盖:
  - 口径契约: `event_accounting._COLUMN_FORMATS` **只追加** 6 列（碳收支五分量 +
    气相交换残差），历史列名逐位不变
  - 纯函数: `co2_gas_exchange_mol` 符号约定（**正 = 去气**）与非物理输入护栏
  - 引擎集成: `hydrology['event_details']` 碳账**与状态轨迹自洽**（层内存量变化
    由**独立来源**（事件前后 state）复算）；**方向可证伪**（pCO₂ 上调 ⇒ 吸收 /
    下调 ⇒ 去气）；零水量 ⇒ 输运项全 0；**只读护栏**（不写回状态 / 不占失败预算）
"""

import pytest

from src.event_accounting import (_COLUMN_FORMATS, build_event_row,
                                  co2_gas_exchange_mol)
from src.phreeqc_engine import DiagnosticOutput, PhreeqcEngine
from src.scenario_controller import MonthlyAction

FORCING = {"temp": 25.0, "pCO2": 0.015}

# 工单95 之前的历史列顺序 (只追加契约的冻结基线; 2026-09-29 快照)
_HISTORICAL_KEYS = [
    'n_no3_pool', 'leach_no3_mol', 'base_loss_eq', 'base_mode',
    'e_base_anion_eq', 'companion_mode', 'companion_eq', 'inert_eq',
    'acid_eq', 'nh4_exchanged_eq', 'lateral_L', 'baseflow_L', 'flush_L',
    'leach_N_mmol', 'leach_base_mmol', 'ph',
    'site_total_molc', 'site_gap_molc',                      # 工单96
    'leach_cl_mol', 'leach_s_mol', 'leach_an_mol',           # 工单94
    'leach_no3_export_mol', 'leach_no3_transfer_mol',
]

# 工单95 碳收支键 → 列名（口径契约）
_CO2_COLUMNS = {
    'c4_storage_delta_mol': 'c4_storage_delta_L{}_mol',
    'c4_inflow_mol':        'c4_inflow_L{}_mol',
    'c4_drain_out_mol':     'c4_drain_out_L{}_mol',
    'c4_out_system_mol':    'c4_out_system_L{}_mol',
    'c4_flush_mol':         'c4_flush_L{}_mol',
    'co2_gas_exchange_mol': 'co2_gas_exchange_L{}_mol',
}


# ---------------------------- 口径契约 (S1) ----------------------------

def test_co2_flux_columns_are_appended_with_exact_names():
    """6 新列入 `_COLUMN_FORMATS` 且列名格式固定"""
    fmt = dict(_COLUMN_FORMATS)
    for key, tmpl in _CO2_COLUMNS.items():
        assert fmt[key] == tmpl


def test_co2_flux_columns_keep_historical_prefix_unchanged():
    """**只追加**契约: 历史列名与顺序逐位不变 + 工单95 的 6 列**紧随其后**"""
    keys = [k for k, _ in _COLUMN_FORMATS]
    assert keys[:len(_HISTORICAL_KEYS)] == _HISTORICAL_KEYS
    assert keys[len(_HISTORICAL_KEYS):len(_HISTORICAL_KEYS) + 6] == list(
        _CO2_COLUMNS)


def test_build_event_row_expands_carbont_columns_per_layer():
    """`build_event_row` 逐层展开碳账列; 缺列 → 0.0 (历史口径)"""
    row = build_event_row(
        {'year': 1, 'month': 1, 'event': 1, 'precip_mm': 0.0},
        [{'c4_storage_delta_mol': -100.0, 'c4_inflow_mol': 5.0,
          'c4_drain_out_mol': 1.0, 'c4_out_system_mol': 2.0,
          'c4_flush_mol': 0.5, 'co2_gas_exchange_mol': 106.5},
         {'c4_inflow_mol': 7.0}])
    assert row['c4_storage_delta_L1_mol'] == -100.0
    assert row['co2_gas_exchange_L1_mol'] == 106.5
    assert row['c4_out_system_L1_mol'] == 2.0
    assert row['c4_inflow_L2_mol'] == 7.0
    assert row['c4_flush_L2_mol'] == 0.0          # 缺列 → 0.0
    assert row['leach_no3_L1_mol'] == 0.0         # 历史列仍在 (无回归)


# ---------------------------- 纯函数 (S2) ----------------------------

def test_co2_gas_exchange_sign_convention():
    """符号约定: **正 = 去气/释放**（存量下降或注入未留住），负 = 吸收

    闭合式: `gas = 入流 − 存量增量 − 随水流出 − 冲洗带出`
    """
    # 存量下降 100 且无任何流通 ⇒ 100 mol C 离开水相 ⇒ 去气 +100
    assert co2_gas_exchange_mol(-100.0, 0.0, 0.0, 0.0) == pytest.approx(100.0)
    # 存量上升 50 且无入流 ⇒ 从气相吸收 ⇒ −50
    assert co2_gas_exchange_mol(50.0, 0.0, 0.0, 0.0) == pytest.approx(-50.0)
    # 入流 30 全部消失（存量/流出均 0）⇒ 去气 +30
    assert co2_gas_exchange_mol(0.0, 30.0, 0.0, 0.0) == pytest.approx(30.0)
    # 随水流出 20 + 冲洗 5，存量正好减少 25 ⇒ 闭合成 0 (无需气相项)
    assert co2_gas_exchange_mol(-25.0, 0.0, 20.0, 5.0) == pytest.approx(0.0)
    # 全零 ⇒ 0 (无驱动)
    assert co2_gas_exchange_mol(0.0, 0.0, 0.0, 0.0) == 0.0


def test_co2_gas_exchange_guards_nonphysical_inputs():
    """护栏: NaN/Inf/None/不可解析贡献 0.0（观测绝不抛异常、不污染记账表）"""
    assert co2_gas_exchange_mol(float('nan'), 0.0, 0.0, 0.0) == 0.0
    assert co2_gas_exchange_mol(0.0, float('inf'), 0.0, 0.0) == 0.0
    assert co2_gas_exchange_mol(None, None, None, None) == 0.0
    assert co2_gas_exchange_mol('bad', 1.0, 2.0, 3.0) == pytest.approx(-4.0)


def test_diag_has_no_new_carbon_fields():
    """**只读护栏**: 碳账只走 ledger ⇒ `DiagnosticOutput` 无新字段（既有断言零变化）"""
    assert not any('c4' in f or 'co2' in f for f in DiagnosticOutput().__dict__)


# ---------------------------- 引擎集成 (S3) ----------------------------

def _engine():
    return PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")


def _states(e, profile, soil_info, n_layers=4):
    """生产口径: 先预平衡 (否则远起点步触发 D6 已登记的"无 react 行"退化)"""
    states = [e.build_initial_state(profile, soil_info, FORCING['pCO2'])
              for _ in range(n_layers)]
    return [e.pre_equilibrate(s, profile, 10, layer_index=i)
            for i, s in enumerate(states)]


def _flux_event(n_layers=4):
    """有水量事件: L1 drains 下移 / L4 baseflow 出系统"""
    return {'inflows': [1.0e5] + [0.0] * (n_layers - 1),
            'drains': [1.0e5, 1.0e4, 1.0e4, 0.0],
            'lateral': [0.0] * n_layers,
            'baseflow': [0.0] * (n_layers - 1) + [1.0e5],
            'bypass_water_L': 0.0, 'precip_mm': 50.0,
            'theta': [0.40] * n_layers}


def _run_carbon(e, profile, soil_info, pco2=None, events=None, monkeypatch=None):
    """跑一个月单场事件, 返回 (event_details[0], 返回态列表, 步前 C 存量快照)

    步前快照经 `run_event_step` **入口 spy** 读取 (独立来源) —
    注意必须**在 orig 调用前**取值: `_rescale_solution_for_volume` 会就地改
    state.volume/浓度 (质量守恒换算, 极端浓缩下有 MAX_CONCENTRATION_RATIO 截断)。
    """
    states = _states(e, profile, soil_info)
    pre = []
    if monkeypatch is not None:
        orig = PhreeqcEngine.run_event_step

        def spy(self, state, *a, **k):
            pre.append((float(state.solution.get('C', 0.0) or 0.0),
                        float(state.volume or 0.0)))
            return orig(self, state, *a, **k)

        monkeypatch.setattr(PhreeqcEngine, 'run_event_step', spy)
    p = FORCING['pCO2'] if pco2 is None else pco2
    hyd = {'events': events or [_flux_event()], 'aet_mm': 0.0,
           'et_deficit_mm': 0.0}
    out_states = e.run_monthly_multi_layer(
        states, dict(FORCING, precip=50.0), MonthlyAction(), profile,
        layer_pco2s=[p] * len(states), hydrology=hyd)
    return hyd['event_details'][0], out_states[0], pre


def test_carbon_ledger_matches_state_trajectory(profile, soil_info,
                                               monkeypatch):
    """碳账**与状态轨迹自洽**: 层内存量变化由事件前后 state 独立复算

    真值来源 = spy 记下的步前 (conc×volume) 与引擎返回的步后 state
    ⇒ 不是"用同一公式复算同一公式"，可抓到记账点/体积口径写错。
    """
    e = _engine()
    det, states, pre = _run_carbon(e, profile, soil_info,
                                   monkeypatch=monkeypatch)
    assert pre, 'spy 未捕获步前状态'
    assert len(pre) == 4                       # 逐层一次
    for i in range(4):
        c4_before = pre[i][0] * pre[i][1]
        c4_after = (float(states[i].solution.get('C', 0.0) or 0.0)
                    * float(states[i].volume or 0.0))
        assert det[f'c4_storage_delta_L{i+1}_mol'] == pytest.approx(
            c4_after - c4_before, rel=1e-9, abs=1e-9)
    # 恒等式（定义式）: 入流 − 流出(两通道) − 冲洗 − 存量增量 == 气相交换
    for i in range(1, 5):
        assert det[f'co2_gas_exchange_L{i}_mol'] == pytest.approx(
            det[f'c4_inflow_L{i}_mol'] - det[f'c4_drain_out_L{i}_mol']
            - det[f'c4_out_system_L{i}_mol'] - det[f'c4_flush_L{i}_mol']
            - det[f'c4_storage_delta_L{i}_mol'], rel=1e-12, abs=1e-12)
    # L1 无层间入流 (降水化学不含 C) ⇒ 入流列恒 0
    assert det['c4_inflow_L1_mol'] == 0.0
    # 有水量 ⇒ 有 C 随水移出 (drains 通道)
    assert det['c4_drain_out_L1_mol'] > 0.0


def test_co2_flux_direction_is_falsifiable(profile, soil_info):
    """⭐ **方向可证伪**: pCO₂ 下调 ⇒ **去气**（正）；上调 ⇒ **吸收**（负）

    与 WF18 §E8 ③ 的物理必然一致（`H⁺ + HCO₃⁻ → CO₂↑`）；若记账/边界写错，
    符号会反或两项同号 ⇒ 本测试失败。
    """
    e1, e2 = _engine(), _engine()
    low, _, _ = _run_carbon(e1, profile, soil_info, pco2=0.0003)
    high, _, _ = _run_carbon(e2, profile, soil_info, pco2=0.0600)
    g_low = low['co2_gas_exchange_L1_mol']
    g_high = high['co2_gas_exchange_L1_mol']
    assert g_low > 0.0, f'低 pCO₂ 应去气, 实测 {g_low}'
    assert g_high < 0.0, f'高 pCO₂ 应吸收, 实测 {g_high}'
    assert g_low > g_high                      # 单调：逸度差驱动


def test_carbon_ledger_zero_water_has_no_transport(profile, soil_info):
    """零水量 ⇒ 输运/冲洗项恒 0（气相项只由边界驱动，不再凭空造通量）"""
    e = _engine()
    ev = {'inflows': [0.0] * 4, 'drains': [0.0] * 4, 'lateral': [0.0] * 4,
          'baseflow': [0.0] * 4, 'bypass_water_L': 0.0, 'precip_mm': 10.0,
          'theta': [0.40] * 4}
    det, _, _ = _run_carbon(e, profile, soil_info, events=[ev])
    for i in range(1, 5):
        assert det[f'c4_inflow_L{i}_mol'] == 0.0
        assert det[f'c4_drain_out_L{i}_mol'] == 0.0
        assert det[f'c4_out_system_L{i}_mol'] == 0.0
        assert det[f'c4_flush_L{i}_mol'] == 0.0


def test_carbon_observer_is_read_only(profile, soil_info):
    """**只读护栏**: 不写回状态 / 不占失败预算 / 不动既有只读计数"""
    e = _engine()
    det, _, _ = _run_carbon(e, profile, soil_info)
    assert e._permanent_fallback is False
    assert e.mass_anomaly_count == 0
    assert e.degenerate_step_count == 0
    # 历史列仍在 (无回归)
    assert 'leach_no3_L1_mol' in det and 'site_total_L1_molc' in det
    # 碳账列齐备 (逐层)
    for key, tmpl in _CO2_COLUMNS.items():
        assert tmpl.format(1) in det