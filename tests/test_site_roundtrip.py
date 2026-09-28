"""测试 工单96 (2026-09-28): 交换位点往返只读观测 (偏差 D9)

覆盖:
  - 纯函数: 交换物种后缀电荷启发式 / `m_` 前缀扫描 / 位点总数与丢弃当量 /
    漂移标记阈值与噪声门 (`src/diagnostics.py` 单一公式源)
  - 口径契约: `event_accounting._COLUMN_FORMATS` 新列 + `build_event_row` 展开
  - 引擎集成: `DiagnosticOutput` 新字段默认零变化; 事件明细含位点列;
    **恒等式** `site_total − site_dropped == exchange_charge_sum(exchange)`;
    **只读护栏** (回写仍只有 6 个物种 / 观测不改变状态 / 不占失败预算)
"""

import pytest

from src.constants import (EXCHANGE_SITE_DRIFT_WARN_FRAC,
                           EXCHANGE_SITE_MIN_TOTAL,
                           EXCHANGE_WRITEBACK_SPECIES)
from src.diagnostics import (calc_site_dropped, calc_site_occupied,
                             calc_site_total_observed, exchange_charge_sum,
                             exchange_site_drift_flag, exchange_species_valence,
                             parse_exchange_molalities)
from src.event_accounting import _COLUMN_FORMATS, build_event_row
from src.hydrology import RainEvent
from src.phreeqc_engine import DiagnosticOutput, PhreeqcEngine
from src.scenario_controller import MonthlyAction

FORCING = {"temp": 25.0, "pCO2": 0.015}
MOL = '(mol/kgw)'


def _headers(species):
    return ['sim', 'Ca' + MOL] + [f'm_{sp}{MOL}' for sp in species]


def _engine():
    return PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")


def _events(n_layers=4, n_events=2):
    """事件序列 — 口径抄自 `tests/test_event_chemistry._multilayer_event_list`
    (零水通量 + 显式 theta; 避免不物理的深层排水触发退化步)"""
    return [{'inflows': [0.0] * n_layers, 'drains': [0.0] * n_layers,
             'lateral': [0.0] * n_layers, 'baseflow': [0.0] * n_layers,
             'bypass_water_L': 0.0, 'precip_mm': 10.0,
             'theta': [0.40] * n_layers} for _ in range(n_events)]


# ---------------------------- 纯函数 ----------------------------

def test_exchange_species_valence_suffix_heuristic():
    """后缀启发式: X3→3 / X2→2 / X→1; 自由位点与未识别名 → None"""
    assert exchange_species_valence('CaX2') == 2
    assert exchange_species_valence('AlX3') == 3
    assert exchange_species_valence('HX') == 1
    assert exchange_species_valence('NH4X') == 1
    assert exchange_species_valence('ZnX2') == 2
    assert exchange_species_valence('AlOHX2') == 2
    # 自由位点与未识别名必须返回 None (不得静默按 0 计)
    assert exchange_species_valence('X-') is None
    assert exchange_species_valence('X') is None
    assert exchange_species_valence('Weird') is None
    assert exchange_species_valence('') is None


def test_parse_exchange_molalities_prefix_scan():
    """按 `m_` 前缀扫描: totals 列排除, 自由位点单列, 未识别名入 unknown"""
    hs = _headers(['CaX2', 'HX', 'X-', 'ZnX2', 'Weird'])
    vals = [1, 0.01, 1.5, 0.9, 0.02, 0.5, 0.3]
    r = parse_exchange_molalities(hs, vals)
    assert r['species'] == {'CaX2': 1.5, 'HX': 0.9, 'ZnX2': 0.5}
    assert r['free'] == pytest.approx(0.02)
    assert r['unknown'] == ['Weird']
    assert 'Ca' not in r['species']          # totals 列无 m_ 前缀
    assert 'X-' not in r['species']          # 自由位点单独返回


def test_parse_exchange_molalities_tolerates_missing_and_bad_values():
    """容错: 缺 m_X- 列 → free=None; 非数值/越界取值 → 跳过, 不抛异常"""
    hs = _headers(['CaX2'])
    assert parse_exchange_molalities(hs, [1, 0.01, 2.0])['free'] is None
    hs2 = _headers(['CaX2', 'HX'])
    r = parse_exchange_molalities(hs2, [1, 0.01, 'NaN', None])
    assert r['species'] == {}                # 两者均不可解析
    assert r['free'] is None
    assert r['unknown'] == []


def test_calc_site_total_and_dropped_values():
    """位点总数 = (自由 + 占用) × kgw; 丢弃 = 自由 + 非回写物种

    ⚠️ 口径要点 (实现中发现): `calc_site_occupied` 认识**全部**交换物种
    (后缀启发式, 含 ZnX2 等), 而 `exchange_charge_sum` **只覆盖 6 个回写物种**
    ⇒ 两者仅在**回写子集**上恒等; 差值 = "回写未覆盖的占用" —— 正是本票要测的量。
    """
    species = {'CaX2': 1.5, 'HX': 0.9, 'ZnX2': 0.5}
    kw = 1000.0
    # 占用 = (2×1.5 + 1×0.9 + 2×0.5) × 1000 = 4.9 × 1000
    assert calc_site_occupied(species, kw) == pytest.approx(4900.0)
    # 回写子集上与 exchange_charge_sum 恒等
    wb = {k: v for k, v in species.items() if k in EXCHANGE_WRITEBACK_SPECIES}
    assert calc_site_occupied(wb, kw) == pytest.approx(
        exchange_charge_sum({k: v * kw for k, v in wb.items()}))
    # 非回写物种 (ZnX2 = 2×0.5×1000) 计入占用但**不计入** exchange_charge_sum
    assert exchange_charge_sum({k: v * kw for k, v in species.items()}) \
        == pytest.approx(3900.0)
    # 总数 = 4900 + 0.02×1000
    assert calc_site_total_observed(species, 0.02, kw) == pytest.approx(4920.0)
    # 丢弃 = 自由 20 + ZnX2 1000 = 1020
    assert calc_site_dropped(species, 0.02, kw) == pytest.approx(1020.0)
    # free=None 时总数退化为占用
    assert calc_site_total_observed(species, None, kw) == pytest.approx(4900.0)


def test_site_dropped_zero_means_mechanism_falsified():
    """⭐ 证伪面: 自由位点≈0 且仅有回写物种 ⇒ 丢弃 = 0 (机制不成立)"""
    species = {sp: 1.0 for sp in EXCHANGE_WRITEBACK_SPECIES}
    assert calc_site_dropped(species, 0.0, 1000.0) == 0.0
    assert calc_site_dropped(species, None, 1000.0) == 0.0


def test_exchange_site_drift_flag_thresholds_and_noise_gate():
    """漂移标记: 阈值内 None / 超阈值 SITE_DRIFT / 归零 SITE_ZEROING / 噪声门"""
    s = 100000.0
    assert exchange_site_drift_flag(s, s * 0.999) is None
    assert exchange_site_drift_flag(
        s, s * (1 - 2 * EXCHANGE_SITE_DRIFT_WARN_FRAC)) == 'SITE_DRIFT'
    assert exchange_site_drift_flag(s, 0.0) == 'SITE_ZEROING'
    # 噪声门: 位点总数 ≤ EXCHANGE_SITE_MIN_TOTAL 一律不判
    assert exchange_site_drift_flag(0.5, 0.0) is None
    assert exchange_site_drift_flag(EXCHANGE_SITE_MIN_TOTAL, 0.0) is None


def test_diag_site_fields_default_to_zero():
    """DiagnosticOutput 新字段默认 0/'' ⇒ 既有断言与行为零变化"""
    d = DiagnosticOutput()
    assert d.site_total_molc == 0.0
    assert d.site_dropped_molc == 0.0
    assert d.site_free_molc == 0.0
    assert d.site_unlisted == ''
    assert d.site_drift_flag == ''


def test_column_formats_contract_and_row_expansion():
    """口径契约: 新列入 `_COLUMN_FORMATS` 且 `build_event_row` 逐层展开"""
    fmt = dict(_COLUMN_FORMATS)
    assert fmt['site_total_molc'] == 'site_total_L{}_molc'
    assert fmt['site_gap_molc'] == 'site_gap_L{}_molc'
    row = build_event_row({'year': 1, 'month': 1, 'event': 1, 'precip_mm': 0.0},
                          [{'site_total_molc': 11.0, 'site_gap_molc': 0.5},
                           {'site_total_molc': 22.0}])
    assert row['site_total_L1_molc'] == 11.0
    assert row['site_gap_L1_molc'] == 0.5
    assert row['site_total_L2_molc'] == 22.0
    assert row['site_gap_L2_molc'] == 0.0     # 缺列 → 0.0 (历史口径)


# ---------------------------- 引擎集成 ----------------------------

def test_event_details_contains_site_columns(profile, soil_info):
    """事件明细含位点列 (工单96 §3.4): `site_total_L*_molc` / `site_gap_L*_molc`

    状态须**先预平衡** (生产口径) —— 否则远起点步会出现 D6 已登记的
    "无 `react` 行" 退化, 位点观测读到 0。
    """
    e = _engine()
    states = [e.build_initial_state(profile, soil_info, 0.015)
              for _ in range(4)]
    states = [e.pre_equilibrate(s, profile, 10, layer_index=i)
              for i, s in enumerate(states)]
    hyd = {'events': _events()}
    e.run_monthly_multi_layer(states, dict(FORCING, precip=10.0),
                              MonthlyAction(), profile, hydrology=hyd)
    det = hyd['event_details'][0]
    assert 'site_total_L1_molc' in det and 'site_gap_L1_molc' in det
    assert det['site_total_L1_molc'] > 0.0
    assert det['site_gap_L1_molc'] >= 0.0


def test_site_observables_identity_with_exchange_charge_sum(profile, soil_info):
    """**恒等式**: `site_total − site_dropped == exchange_charge_sum(exchange)`

    两侧同源 (molality × kgw) ⇒ 必须一致到浮点级 ⇒ 证明新观测量**未引入新口径**。
    """
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    f = dict(FORCING, precip=20.0, inflow_water_L=200000.0)
    new_state, diag = e.run_event_step(state, RainEvent(precip_mm=20.0),
                                       MonthlyAction(), profile, forcing=f)
    q = exchange_charge_sum(new_state.exchange)
    assert diag.site_total_molc - diag.site_dropped_molc == pytest.approx(
        q, rel=1e-9)


def test_site_observer_is_read_only(profile, soil_info):
    """**只读护栏**: 回写仍只有 6 个物种 (不把自由位点/未列物种写回状态)"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    f = dict(FORCING, precip=20.0, inflow_water_L=200000.0)
    new_state, diag = e.run_event_step(state, RainEvent(precip_mm=20.0),
                                       MonthlyAction(), profile, forcing=f)
    assert set(new_state.exchange) <= set(EXCHANGE_WRITEBACK_SPECIES)
    assert 'X-' not in new_state.exchange
    assert diag.site_drift_flag in ('', 'SITE_DRIFT', 'SITE_ZEROING')
    # 观测不占失败预算 / 不触发降级
    assert e._permanent_fallback is False


def test_site_drift_accumulator_flags_once_without_state_change(profile,
                                                                soil_info):
    """累计计数 + 首次告警 (**口径 = Δq = q_in−q_out**): 仅动计数, 不动状态/不重复告警

    口径修正依据 (2026-09-28 量级归因): `ΣΔq` 与观测漂移比值 −0.90~−0.95
    (⇒ Δq 即真损失量), 而 `Σsite_gap/ΣΔq` 无规律 ⇒ 自由位点通道被证伪。
    """
    e = _engine()
    st = DiagnosticOutput(exchange_q_in=1000.0, exchange_q_out=500.0)
    e._observe_site_roundtrip(0, st)
    assert e.site_drift_count == 1              # Δq/ref = 50% ≫ 0.5% ⇒ 首次告警
    e._observe_site_roundtrip(0, st)
    assert e.site_drift_count == 1              # 不重复
    assert e._site_drift_cum[0] == pytest.approx(1000.0)   # 2 × Δq(500)
    # 噪声门内的层不进入告警集合 (q_in ≤ 门限)
    e._observe_site_roundtrip(1, DiagnosticOutput(exchange_q_in=0.5,
                                                  exchange_q_out=0.5))
    assert 1 not in e._site_drift_warned
    assert e.site_drift_count == 1
    # None diag 安全 (失败路径传入 None)
    e._observe_site_roundtrip(2, None)
    assert 2 not in e._site_ref