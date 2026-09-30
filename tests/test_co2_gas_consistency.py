"""测试 工单100 (2026-09-30): 气相自洽性**只读**观测列 (`co2_si` / `co2_aq_mol`)

覆盖:
  - 口径契约: `event_accounting._COLUMN_FORMATS` **只追加** 2 列，历史列名/顺序逐位不变
  - 输入契约: `SELECTED_OUTPUT -saturation_indices CO2(g)` + `USER_PUNCH` 自定列
    （⚠️ **禁止**把 `CO2` 追加到 `-molalities`：`parse_exchange_molalities` 按
     `m_`+`(mol/kgw)` **全收** ⇒ 会污染 `site_total/site_gap` 产品列）
  - 恒等式: `co2_si_L{k} ≈ log10(pCO₂)`（`SI` 相对 **1 atm 纯气**）⇒ `dev ≈ 0`；
    `co2_aq_L{k}_mol > 0`（mol/kgw × mass_H2O）
  - **只读护栏**: 不写回状态 / 不占失败预算 / 不动既有只读计数 / `DiagnosticOutput` 无新字段
"""

import math

import pytest

from src.diagnostics import parse_exchange_molalities
from src.event_accounting import _COLUMN_FORMATS, build_event_row
from src.phreeqc_engine import DiagnosticOutput, PhreeqcEngine
from src.scenario_controller import MonthlyAction

FORCING = {"temp": 25.0, "pCO2": 0.0175}

# 工单100 之前的完整列顺序 (只追加契约的冻结基线; 2026-09-30 快照)
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
]

# 工单100 键 → 列名（口径契约）
_CO2_GAS_COLUMNS = {
    'co2_si':     'co2_si_L{}',
    'co2_aq_mol': 'co2_aq_L{}_mol',
}


# ---------------------------- 口径契约 (S1) ----------------------------

def test_co2_gas_columns_are_appended_with_exact_names():
    fmt = dict(_COLUMN_FORMATS)
    for key, tmpl in _CO2_GAS_COLUMNS.items():
        assert fmt[key] == tmpl


def test_co2_gas_columns_keep_historical_prefix_unchanged():
    """**只追加**契约: 历史 32 列逐位不变 + 本工单 2 列紧随其后"""
    keys = [k for k, _ in _COLUMN_FORMATS]
    assert keys[:len(_HISTORICAL_KEYS)] == _HISTORICAL_KEYS
    assert keys[len(_HISTORICAL_KEYS):] == list(_CO2_GAS_COLUMNS)


def test_build_event_row_expands_co2_gas_columns_per_layer():
    row = build_event_row(
        {'year': 1, 'month': 1, 'event': 1, 'precip_mm': 0.0},
        [{'co2_si': -1.757, 'co2_aq_mol': 719.9},
         {'co2_si': -1.648}])
    assert row['co2_si_L1'] == pytest.approx(-1.757)
    assert row['co2_aq_L1_mol'] == pytest.approx(719.9)
    assert row['co2_si_L2'] == pytest.approx(-1.648)
    assert row['co2_aq_L2_mol'] == 0.0             # 缺列 → 0.0 (历史口径)
    assert row['co2_gas_exchange_L1_mol'] == 0.0   # 工单95 列仍在


# ---------------------------- 输入契约 (S2) ----------------------------

def _input_for(profile, soil_info, pco2=0.0175):
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    s = e.build_initial_state(profile, soil_info, pco2)
    return e._build_phreeqc_input(
        s, {'temp': 25.0, 'pCO2': pco2, 'precip': 50.0,
            'inflow_water_L': 1.0e5},
        MonthlyAction(), profile)


def test_input_has_saturation_index_for_co2_gas(profile, soil_info):
    assert '-saturation_indices CO2(g)' in _input_for(profile, soil_info)


def test_input_has_user_punch_co2_molality(profile, soil_info):
    """`[CO2]aq` 走 USER_PUNCH 自定列名（不做交换位点解析的对象）"""
    inp = _input_for(profile, soil_info)
    assert 'USER_PUNCH 1' in inp
    assert '-headings co2_aq_molal' in inp
    assert 'PUNCH MOL("CO2")' in inp


def test_input_molalities_line_is_unchanged(profile, soil_info):
    """⚠️ **硬约束**: `-molalities` 行**不得**追加 `CO2`（否则污染 site_* 产品列）"""
    inp = _input_for(profile, soil_info)
    mol_lines = [ln for ln in inp.splitlines() if '-molalities' in ln]
    assert len(mol_lines) == 1
    assert 'CO2' not in mol_lines[0].replace('CO2(g)', '').upper()


def test_user_punch_heading_is_not_exchange_species():
    """`co2_aq_molal` 不匹配 `m_`+`(mol/kgw)` ⇒ 交换位点解析忽略它"""
    mols = parse_exchange_molalities(
        ['m_CaX2(mol/kgw)', 'm_X-(mol/kgw)', 'co2_aq_molal'],
        [1.0, 2.0, 3.0])
    assert set(mols['species']) == {'CaX2'}
    assert not any('CO2' in k.upper() for k in mols['species'])


def test_diag_has_no_new_carbon_fields():
    """**只读护栏**: 气相列只走 ledger ⇒ `DiagnosticOutput` 无新字段"""
    assert not any('co2_si' in f or 'co2_aq' in f
                   for f in DiagnosticOutput().__dict__)


# ---------------------------- 引擎集成 (S3) ----------------------------

def _engine():
    return PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")


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


def test_co2_gas_consistency_identity(profile, soil_info):
    """⭐ 恒等式: `co2_si ≈ log10(pCO₂)`（SI 相对 **1 atm 纯气**）⇒ dev ≈ 0"""
    det = _run_event(_engine(), profile, soil_info)
    for i in (1, 2, 3, 4):
        si = det[f'co2_si_L{i}']
        assert math.isfinite(si)
        assert abs(si - math.log10(FORCING['pCO2'])) <= 0.05, \
            f'L{i} dev = {si - math.log10(FORCING["pCO2"]):.4f}'
        assert det[f'co2_aq_L{i}_mol'] > 0.0      # mol/kgw × mass_H2O


def test_co2_gas_column_tracks_boundary_change(profile, soil_info):
    """方向可证伪: pCO₂ 下调 ⇒ SI 同步下调（`SI ≈ log10(pCO₂)`）"""
    si_low = _run_event(_engine(), profile, soil_info,
                        pco2=0.001)['co2_si_L1']
    si_high = _run_event(_engine(), profile, soil_info,
                         pco2=0.060)['co2_si_L1']
    assert si_low < si_high


def test_co2_gas_observer_is_read_only(profile, soil_info):
    """**只读护栏**: 不降级 / 计数不动 / 历史列齐备"""
    e = _engine()
    det = _run_event(e, profile, soil_info)
    assert e._permanent_fallback is False
    assert e.mass_anomaly_count == 0
    assert e.degenerate_step_count == 0
    for col in ('leach_no3_L1_mol', 'site_total_L1_molc',
                'co2_gas_exchange_L1_mol', 'leach_cation_eq_L1_molc'):
        assert col in det