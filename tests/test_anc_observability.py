"""测试 工单101 (2026-10-01): P3-ANC **只读列**三组

  组 A 溶液侧 NO₃⁻（与 Cl/S/An 同源同取值点）/ 组 B Q6 `flush` 通道 /
  组 C 降水 ANC 输入（面板口径 = 0 哨兵）

覆盖:
  - 口径契约: `event_accounting._COLUMN_FORMATS` **只追加** 12 列，历史列名/顺序逐位不变
  - 纯函数: A 组构造恒等 / B 组与 `c4_flush_mol` 同式 / C 组"未注入"哨兵 + 与
    `PrecipChemistry.reaction_amounts` 同式（净 ANC = BC + NH₄ − SA − H⁺，≠ 0）
  - 引擎集成: 新列齐备且 A 组恒等成立；面板口径 C 组恒 0；生产口径 L1 C 组 > 0
  - **只读护栏**: 不写回状态 / 不占失败预算 / `DiagnosticOutput` 无新字段
"""

import math

import pytest

from src.event_accounting import (_COLUMN_FORMATS, build_event_row,
                                  flush_leach_columns, rain_anc_columns,
                                  solution_n_columns)
from src.phreeqc_engine import DiagnosticOutput, PhreeqcEngine
from src.precip_chemistry import PrecipChemistry
from src.scenario_controller import MonthlyAction

FORCING = {"temp": 25.0, "pCO2": 0.0175}

# 工单101 之前的完整列顺序 (只追加契约的冻结基线; 2026-10-01 快照)
_HISTORICAL_KEYS = [
    'n_no3_pool', 'leach_no3_mol', 'base_loss_eq', 'base_mode',
    'e_base_anion_eq', 'companion_mode', 'companion_eq', 'inert_eq',
    'acid_eq', 'nh4_exchanged_eq', 'lateral_L', 'baseflow_L', 'flush_L',
    'leach_N_mmol', 'leach_base_mmol', 'ph',
    'site_total_molc', 'site_gap_molc',                    # 工单96
    'leach_cl_mol', 'leach_s_mol', 'leach_an_mol',         # 工单94
    'leach_no3_export_mol', 'leach_no3_transfer_mol',
    'c4_storage_delta_mol', 'c4_inflow_mol',               # 工单95
    'c4_drain_out_mol', 'c4_out_system_mol', 'c4_flush_mol',
    'co2_gas_exchange_mol',
    'leach_cation_eq_molc', 'leach_cation_transfer_molc',  # 工单97
    'leach_cation_export_molc',
    'co2_si', 'co2_aq_mol',                                # 工单100
]

# 工单101 键 → 列名（三组 12 列）
_ANC_COLUMNS = {
    # A 溶液侧 NO₃⁻
    'n_sol_transfer_mol': 'leach_n_sol_transfer_L{}_mol',
    'n_sol_export_mol':   'leach_n_sol_export_L{}_mol',
    'n_sol_flush_mol':    'leach_n_sol_flush_L{}_mol',
    'n_sol_mol':          'leach_n_sol_L{}_mol',
    # B Q6 flush 通道
    'cation_flush_molc':  'leach_cation_flush_L{}_molc',
    'cl_flush_mol':       'leach_cl_flush_L{}_mol',
    's_flush_mol':        'leach_s_flush_L{}_mol',
    'an_flush_mol':       'leach_an_flush_L{}_mol',
    # C 降水 ANC 输入
    'rain_bc_in_eq':      'rain_bc_in_L{}_eq',
    'rain_sa_in_eq':      'rain_sa_in_L{}_eq',
    'rain_nh4_in_eq':     'rain_nh4_in_L{}_eq',
    'rain_anc_in_eq':     'rain_anc_in_L{}_eq',
}


# ---------------------------- 口径契约 ----------------------------

def test_anc_columns_are_appended_with_exact_names():
    fmt = dict(_COLUMN_FORMATS)
    for key, tmpl in _ANC_COLUMNS.items():
        assert fmt[key] == tmpl


def test_anc_columns_keep_historical_prefix_unchanged():
    """**只追加**契约: 历史 34 列（含工单100 两列）逐位不变 + 本工单 12 列紧随其后"""
    keys = [k for k, _ in _COLUMN_FORMATS]
    assert keys[:len(_HISTORICAL_KEYS)] == _HISTORICAL_KEYS
    assert keys[len(_HISTORICAL_KEYS):] == list(_ANC_COLUMNS)


def test_build_event_row_expands_anc_columns_per_layer():
    row = build_event_row(
        {'year': 1, 'month': 1, 'event': 1, 'precip_mm': 0.0},
        [{'n_sol_mol': 1.5, 'rain_anc_in_eq': 220.0},
         {'n_sol_mol': 0.0}])
    assert row['leach_n_sol_L1_mol'] == pytest.approx(1.5)
    assert row['rain_anc_in_L1_eq'] == pytest.approx(220.0)
    assert row['leach_n_sol_L2_mol'] == 0.0          # 缺列 → 0.0 (历史口径)
    assert row['rain_anc_in_L2_eq'] == 0.0
    assert row['co2_si_L1'] == 0.0                    # 工单100 列仍在


# ---------------------------- 纯函数 (A 组) ----------------------------

def test_solution_n_columns_channels_and_identity():
    """⭐ 三通道 + **构造恒等** `total = transfer + export + flush`"""
    c = solution_n_columns({'N': 2.0e-4}, drain_L=1.0e4,
                           out_system_L=2.0e3, flush_L=5.0e3)
    assert c['n_sol_transfer_mol'] == pytest.approx(2.0)
    assert c['n_sol_export_mol'] == pytest.approx(0.4)
    assert c['n_sol_flush_mol'] == pytest.approx(1.0)
    assert c['n_sol_mol'] == pytest.approx(
        c['n_sol_transfer_mol'] + c['n_sol_export_mol'] + c['n_sol_flush_mol'])


def test_solution_n_columns_zero_when_no_water_and_guarded():
    c = solution_n_columns({'N': 1.0e-3}, 0.0, 0.0, 0.0)
    assert c['n_sol_mol'] == 0.0
    c2 = solution_n_columns({}, -5.0, -1.0, -1.0)      # 缺键/负水量 ⇒ 0
    assert c2['n_sol_mol'] == 0.0


# ---------------------------- 纯函数 (B 组) ----------------------------

def test_flush_leach_columns_linear_in_flush_water():
    """与 `c4_flush_mol` **同式**（浓度 × 冲洗水量）；线性可证伪"""
    conc = {'Cl': 1.0e-3, 'S': 2.0e-4, 'Ca': 5.0e-4, 'Mg': 1.0e-4,
            'K': 2.0e-5, 'Na': 3.0e-5}
    a = flush_leach_columns(conc, 1.0e-3, 1.0e4)
    b = flush_leach_columns(conc, 1.0e-3, 2.0e4)
    assert a['cl_flush_mol'] == pytest.approx(10.0)
    assert a['s_flush_mol'] == pytest.approx(2.0)
    assert a['an_flush_mol'] == pytest.approx(10.0)     # An 走 pair_anion_conc
    assert a['cation_flush_molc'] == pytest.approx(
        (2 * 5.0e-4 + 2 * 1.0e-4 + 2.0e-5 + 3.0e-5) * 1.0e4)
    assert b['cl_flush_mol'] == pytest.approx(2 * a['cl_flush_mol'])
    assert b['cation_flush_molc'] == pytest.approx(2 * a['cation_flush_molc'])


def test_flush_leach_columns_zero_when_no_flush():
    conc = {'Cl': 1.0e-3, 'S': 1.0e-3, 'Ca': 1.0e-3, 'Na': 1.0e-3}
    out = flush_leach_columns(conc, 5.0e-3, 0.0)
    assert out == {'cation_flush_molc': 0.0, 'cl_flush_mol': 0.0,
                   's_flush_mol': 0.0, 'an_flush_mol': 0.0}


# ---------------------------- 纯函数 (C 组) ----------------------------

def test_rain_anc_columns_panel_caliber_sentinel_is_zero():
    """⭐ 面板口径（`precip_chem=None`）⇒ **"未注入"哨兵 0.0**（引用须标口径）"""
    out = rain_anc_columns(None, 1.0e6)
    assert set(out) == {'rain_bc_in_eq', 'rain_sa_in_eq', 'rain_nh4_in_eq',
                        'rain_anc_in_eq'}
    assert all(v == 0.0 for v in out.values())


def test_rain_anc_columns_matches_reaction_amounts_and_is_nonzero():
    """与 `reaction_amounts` **同式**；默认降水化学**电荷不平衡** ⇒ 净 ANC ≠ 0"""
    pc = PrecipChemistry()
    w = 1.0e6
    out = rain_anc_columns(pc, w)
    amt = pc.reaction_amounts(w)
    bc = 2 * amt['Ca+2'] + 2 * amt['Mg+2'] + amt['K+'] + amt['Na+']
    sa = amt['Cl-'] + 2 * amt['SO4-2'] + amt['NO3-'] + amt['F-']
    assert out['rain_bc_in_eq'] == pytest.approx(bc)
    assert out['rain_sa_in_eq'] == pytest.approx(sa)
    assert out['rain_nh4_in_eq'] == pytest.approx(amt['NH4+'])
    assert out['rain_anc_in_eq'] == pytest.approx(
        bc + amt['NH4+'] - sa - amt['H+'])
    assert out['rain_anc_in_eq'] > 0.0        # 阳离子过量（12.4%）⇒ ANC > 0


def test_rain_anc_columns_linear_in_water_and_includes_bypass():
    pc = PrecipChemistry()
    a = rain_anc_columns(pc, 1.0e6)
    b = rain_anc_columns(pc, 2.0e6)
    assert b['rain_anc_in_eq'] == pytest.approx(2 * a['rain_anc_in_eq'])
    c = rain_anc_columns(pc, 1.0e6, bypass_L=1.0e6)
    assert c['rain_anc_in_eq'] == pytest.approx(2 * a['rain_anc_in_eq'])


def test_rain_anc_columns_zero_water_is_zero():
    pc = PrecipChemistry()
    assert all(v == 0.0 for v in rain_anc_columns(pc, 0.0).values())


# ---------------------------- 引擎集成 ----------------------------

def _engine(precip_chem=None):
    return PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                         precip_chem=precip_chem)


def _run_event(e, profile, soil_info, pco2=None):
    p = FORCING['pCO2'] if pco2 is None else pco2
    states = [e.build_initial_state(profile, soil_info, p) for _ in range(4)]
    states = [e.pre_equilibrate(s, profile, 10, layer_index=i)
              for i, s in enumerate(states)]
    ev = {'inflows': [1.0e5, 0.0, 0.0, 0.0],
          'drains': [1.0e5, 1.0e4, 1.0e4, 0.0],
          'lateral': [0.0] * 4, 'baseflow': [0.0, 0.0, 0.0, 1.0e5],
          'bypass_water_L': 0.0, 'precip_mm': 50.0, 'theta': [0.40] * 4}
    hyd = {'events': [ev], 'aet_mm': 0.0, 'et_deficit_mm': 0.0}
    e.run_monthly_multi_layer(states, dict(FORCING, precip=50.0),
                              MonthlyAction(), profile,
                              layer_pco2s=[p] * 4, hydrology=hyd)
    return hyd['event_details'][0]


def test_new_columns_present_and_n_identity_holds(profile, soil_info):
    det = _run_event(_engine(), profile, soil_info)
    for i in (1, 2, 3, 4):
        for tmpl in ('leach_n_sol_transfer_L{}_mol',
                     'leach_n_sol_export_L{}_mol',
                     'leach_n_sol_flush_L{}_mol', 'leach_n_sol_L{}_mol',
                     'leach_cation_flush_L{}_molc', 'leach_cl_flush_L{}_mol',
                     'leach_s_flush_L{}_mol', 'leach_an_flush_L{}_mol',
                     'rain_bc_in_L{}_eq', 'rain_sa_in_L{}_eq',
                     'rain_nh4_in_L{}_eq', 'rain_anc_in_L{}_eq'):
            assert tmpl.format(i) in det, tmpl.format(i)
        assert det[f'leach_n_sol_L{i}_mol'] == pytest.approx(
            det[f'leach_n_sol_transfer_L{i}_mol']
            + det[f'leach_n_sol_export_L{i}_mol']
            + det[f'leach_n_sol_flush_L{i}_mol'])


def test_panel_caliber_rain_columns_are_zero(profile, soil_info):
    """面板口径（不注入降水化学）⇒ C 组恒 0（未注入哨兵）"""
    det = _run_event(_engine(), profile, soil_info)
    for i in (1, 2, 3, 4):
        assert det[f'rain_bc_in_L{i}_eq'] == 0.0
        assert det[f'rain_sa_in_L{i}_eq'] == 0.0
        assert det[f'rain_anc_in_L{i}_eq'] == 0.0


def test_production_caliber_rain_columns_are_nonzero(profile, soil_info):
    """生产口径（`precip_chem=PrecipChemistry()`）⇒ L1 BC/ANC > 0 且按层递减"""
    det = _run_event(_engine(PrecipChemistry()), profile, soil_info)
    assert det['rain_bc_in_L1_eq'] > 0.0
    assert det['rain_anc_in_L1_eq'] > 0.0
    assert det['rain_bc_in_L1_eq'] > det['rain_bc_in_L3_eq']


def test_anc_observer_is_read_only(profile, soil_info):
    """**只读护栏**: 不降级 / 计数不动 / 历史列齐备 / `DiagnosticOutput` 无新字段"""
    e = _engine(PrecipChemistry())
    det = _run_event(e, profile, soil_info)
    assert e._permanent_fallback is False
    assert e.mass_anomaly_count == 0
    assert e.degenerate_step_count == 0
    for col in ('leach_no3_L1_mol', 'leach_cl_L1_mol',
                'leach_cation_eq_L1_molc', 'co2_si_L1', 'leach_n_sol_L1_mol'):
        assert col in det
    assert not any('n_sol' in f or 'flush_mol' in f or 'rain_' in f
                   for f in DiagnosticOutput().__dict__)
    assert math.isfinite(det['leach_n_sol_L1_mol'])