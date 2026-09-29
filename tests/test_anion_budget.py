"""测试 工单94 (2026-09-28 立票 / **2026-09-29 实施**): 阴离子收支记账 (D8 预算可判读化; **只读**)

覆盖:
  - 口径契约: `event_accounting._COLUMN_FORMATS` **只追加** 5 列
    (历史列名逐位不变) + `build_event_row` 逐层展开
  - 纯函数: `leach_flux_mol` / `anion_leach_columns` (负值/NaN/缺键护栏)
  - 引擎集成: `DiagnosticOutput.pair_anion_conc` 只读观测
    (**配对阴离子 `An` 不入 `solution`** —— 解析列表无 `An`, 故须独立读取);
    事件明细含阴离子列; **恒等式** `export + transfer == 旧 leach_no3_mol`;
    通道语义 (drains = 层间下移 / lateral+baseflow = 出系统); **只读护栏**
    (不写回状态/不占失败预算/不改变 pending_e_loss 口径)
"""

import pytest

from src.event_accounting import (_COLUMN_FORMATS, anion_leach_columns,
                                  build_event_row, leach_flux_mol)
from src.hydrology import RainEvent
from src.phreeqc_engine import DiagnosticOutput, PhreeqcEngine
from src.scenario_controller import MonthlyAction

FORCING = {"temp": 25.0, "pCO2": 0.015}

# 工单94 之前的历史列顺序 (只追加契约的冻结基线; 2026-09-29 快照)
_HISTORICAL_KEYS = [
    'n_no3_pool', 'leach_no3_mol', 'base_loss_eq', 'base_mode',
    'e_base_anion_eq', 'companion_mode', 'companion_eq', 'inert_eq',
    'acid_eq', 'nh4_exchanged_eq', 'lateral_L', 'baseflow_L', 'flush_L',
    'leach_N_mmol', 'leach_base_mmol', 'ph',
    # 工单96 (2026-09-28): 位点往返只读观测
    'site_total_molc', 'site_gap_molc',
]


# ---------------------------- 口径契约 (S1) ----------------------------

def test_column_formats_appends_anion_and_e_loss_split_columns():
    """口径契约: 5 新列入 `_COLUMN_FORMATS` 且列名格式固定"""
    fmt = dict(_COLUMN_FORMATS)
    assert fmt['leach_cl_mol'] == 'leach_cl_L{}_mol'
    assert fmt['leach_s_mol'] == 'leach_s_L{}_mol'
    assert fmt['leach_an_mol'] == 'leach_an_L{}_mol'
    assert fmt['leach_no3_export_mol'] == 'leach_no3_export_L{}_mol'
    assert fmt['leach_no3_transfer_mol'] == 'leach_no3_transfer_L{}_mol'


def test_column_formats_is_append_only_historical_prefix_unchanged():
    """**只追加**契约: 历史列名与顺序逐位不变 (下游 CSV/脚本依赖)"""
    assert [k for k, _ in _COLUMN_FORMATS][:len(_HISTORICAL_KEYS)] \
        == _HISTORICAL_KEYS
    assert len(_COLUMN_FORMATS) == len(_HISTORICAL_KEYS) + 5


def test_build_event_row_expands_anion_columns_per_layer():
    """`build_event_row` 逐层展开新列; 缺列 → 0.0 (历史口径)"""
    row = build_event_row(
        {'year': 1, 'month': 1, 'event': 1, 'precip_mm': 0.0},
        [{'leach_cl_mol': 11.0, 'leach_s_mol': 22.0, 'leach_an_mol': 33.0,
          'leach_no3_export_mol': 44.0, 'leach_no3_transfer_mol': 55.0},
         {'leach_cl_mol': 1.0}])
    assert row['leach_cl_L1_mol'] == 11.0
    assert row['leach_s_L1_mol'] == 22.0
    assert row['leach_an_L1_mol'] == 33.0
    assert row['leach_no3_export_L1_mol'] == 44.0
    assert row['leach_no3_transfer_L1_mol'] == 55.0
    assert row['leach_cl_L2_mol'] == 1.0
    assert row['leach_s_L2_mol'] == 0.0        # 缺列 → 0.0
    assert row['leach_no3_transfer_L2_mol'] == 0.0
    # 历史列仍在 (无回归)
    assert row['leach_no3_L1_mol'] == 0.0
    assert row['ph_L1'] == 0.0


# ---------------------------- 纯函数 (S2) ----------------------------

def test_leach_flux_mol_guards_nonphysical_inputs():
    """纯函数护栏: 浓度 × 水量; 负值/零/NaN/不可解析/负水量 → 0.0"""
    assert leach_flux_mol(1e-3, 1.0e5) == pytest.approx(100.0)
    assert leach_flux_mol(0.0, 1.0e5) == 0.0
    assert leach_flux_mol(-1e-3, 1.0e5) == 0.0        # 负浓度非物理
    assert leach_flux_mol(1e-3, 0.0) == 0.0
    assert leach_flux_mol(1e-3, -1.0) == 0.0          # 负水量非物理
    assert leach_flux_mol(float('nan'), 1.0e5) == 0.0
    assert leach_flux_mol(float('inf'), 1.0e5) == 0.0
    assert leach_flux_mol(None, 1.0e5) == 0.0
    assert leach_flux_mol('bad', 1.0e5) == 0.0


def test_anion_leach_columns_are_two_channel_sums():
    """阴离子列 = 层间下移 (drains) + 出系统 (lateral+baseflow) 两通道之和

    口径与 `phreeqc_engine` 排水溶质扣除 (`moved_ions` / `q3_out_ions`) **同一来源**
    ⇒ 阴离子账可与 NO₃⁻ 淋失账在同一份观测表内对账 (工单94 §1)。
    """
    conc = {'Cl': 1.0e-3, 'S': 2.0e-3, 'An': 5.0e-4}
    out = anion_leach_columns(conc, drain_L=1.0e4, out_system_L=3.0e4)
    assert out['leach_cl_mol'] == pytest.approx(1.0e-3 * 4.0e4)
    assert out['leach_s_mol'] == pytest.approx(2.0e-3 * 4.0e4)
    assert out['leach_an_mol'] == pytest.approx(5.0e-4 * 4.0e4)
    # 单通道为零 ⇒ 只剩另一通道
    only_drain = anion_leach_columns(conc, 1.0e4, 0.0)
    assert only_drain['leach_cl_mol'] == pytest.approx(10.0)
    only_out = anion_leach_columns(conc, 0.0, 1.0e4)
    assert only_out['leach_cl_mol'] == pytest.approx(10.0)
    # 缺键/空浓度 → 全 0.0 (历史口径, 不得抛异常)
    assert anion_leach_columns({}, 1.0e4, 1.0e4) == {
        'leach_cl_mol': 0.0, 'leach_s_mol': 0.0, 'leach_an_mol': 0.0}


# ---------------------------- 引擎集成 (S3/S4) ----------------------------

def test_diag_pair_anion_field_defaults_to_zero():
    """`DiagnosticOutput.pair_anion_conc` 默认 0.0 ⇒ 既有断言零变化"""
    assert DiagnosticOutput().pair_anion_conc == 0.0


def _engine_companion():
    """companion 启用 ⇒ `An-` 已定义 + 电荷配对注入生效 (口径抄 test_event_chemistry)"""
    from src.config_manager import CompanionConfig
    return PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                         companion_cfg=CompanionConfig(enable=True))


def _fert_action():
    return MonthlyAction(apply_fertilizer=True, n_amount=12.0, p2o5_amount=4.0,
                        k2o_amount=9.0, mgo_amount=3.0, znso4_amount=1.0)


def test_pair_anion_observed_without_entering_solution(profile, soil_info):
    """**只读护栏**: `An` 可观测 (`pair_anion_conc > 0`) 但**不入** `solution`

    `An` 若进 `solution`, 会随层间 `inflow_ions = moved_ions` 被注入下一层
    ⇒ **物理行为改变** (工单94 §5 明令禁止)。本测试把该边界钉死。
    """
    e = _engine_companion()
    state = e.build_initial_state(profile, soil_info, 0.015)
    f = dict(FORCING, precip=20.0, inflow_water_L=200000.0)
    new_state, diag = e.run_event_step(
        state, RainEvent(precip_mm=20.0), _fert_action(), profile, forcing=f)
    assert 'An' not in new_state.solution          # 未进入状态 (不改变层间输入)
    assert diag.pair_anion_conc > 0.0              # 但已可观测 (只读)
    assert e._permanent_fallback is False          # 观测不占失败预算/不触发降级


# ---------------------------- 引擎集成: 逐层逐场记账 (S4) ----------------------------

def _states(e, profile, soil_info, n_layers=4):
    """生产口径: 先预平衡 (否则远起点步触发 D6 已登记的\"无 react 行\"退化)"""
    states = [e.build_initial_state(profile, soil_info, 0.015)
              for _ in range(n_layers)]
    return [e.pre_equilibrate(s, profile, 10, layer_index=i)
            for i, s in enumerate(states)]


def _flux_event(n_layers=4):
    """有水量事件: L1 drains 下移 / L4 baseflow 出系统 (口径抄 test_event_chemistry)"""
    return {'inflows': [1.0e5] + [0.0] * (n_layers - 1),
            'drains': [1.0e5, 1.0e4, 1.0e4, 0.0],
            'lateral': [0.0] * n_layers,
            'baseflow': [0.0] * (n_layers - 1) + [1.0e5],
            'bypass_water_L': 0.0, 'precip_mm': 50.0,
            'theta': [0.40] * n_layers}


def _zero_flow_event(n_layers=4):
    """零水量事件 (全部出口为 0)"""
    return {'inflows': [0.0] * n_layers, 'drains': [0.0] * n_layers,
            'lateral': [0.0] * n_layers, 'baseflow': [0.0] * n_layers,
            'bypass_water_L': 0.0, 'precip_mm': 10.0,
            'theta': [0.40] * n_layers}


def _run(e, profile, soil_info, events, action=None):
    states = _states(e, profile, soil_info)
    states[0].n_no3_pool = 1000.0
    hyd = {'events': events, 'aet_mm': 0.0, 'et_deficit_mm': 0.0}
    e.run_monthly_multi_layer(states, dict(FORCING, precip=50.0),
                              action or MonthlyAction(), profile,
                              hydrology=hyd)
    return hyd['event_details']


def test_e_loss_split_identity_holds_for_every_layer_and_event(profile,
                                                               soil_info):
    """**恒等式** (工单94 §4 判据): `export + transfer == 旧 leach_no3_mol`

    逐层逐场成立 ⇒ 分离记账**未改口径** (总量仍取自同一 NO₃⁻ 池跟踪)。
    """
    details = _run(_engine_companion(), profile, soil_info,
                   [_flux_event(), _flux_event()])
    assert len(details) == 2
    for det in details:
        for i in (1, 2, 3, 4):
            assert det[f'leach_no3_export_L{i}_mol'] \
                + det[f'leach_no3_transfer_L{i}_mol'] == pytest.approx(
                    det[f'leach_no3_L{i}_mol'], rel=1e-12, abs=1e-12)
    # ⭐ 只读护栏: 注入基准不受分离记账影响 ⇒ 第 2 场伴随当量 == 第 1 场淋失量
    #    (`pending_e_loss` 语义逐位不变; 工单94 §5 硬约束)
    assert details[1]['companion_eq_L1'] == pytest.approx(
        details[0]['leach_no3_L1_mol'], rel=1e-12)


def test_e_loss_split_channel_semantics_follow_event_water(profile, soil_info):
    """通道语义 (独立真值 = 事件水量字段): drains→transfer; lateral/baseflow→export

    L1: drains=1e5 (下移), lat+base=0  ⇒ transfer>0 且 export==0
    L4: drains=0, baseflow=1e5 (出系统) ⇒ export>0 且 transfer==0
    """
    det = _run(_engine_companion(), profile, soil_info, [_flux_event()])[0]
    assert det['leach_no3_transfer_L1_mol'] > 0.0
    assert det['leach_no3_export_L1_mol'] == 0.0
    assert det['leach_no3_transfer_L4_mol'] == 0.0
    assert det['leach_no3_export_L4_mol'] > 0.0


def test_anion_columns_zero_under_zero_water_flux(profile, soil_info):
    """零水量 ⇒ 阴离子列与 E_loss 分离列**全 0** (只读记账不凭空造通量)"""
    det = _run(_engine_companion(), profile, soil_info,
               [_zero_flow_event()])[0]
    for i in (1, 2, 3, 4):
        assert det[f'leach_cl_L{i}_mol'] == 0.0
        assert det[f'leach_s_L{i}_mol'] == 0.0
        assert det[f'leach_an_L{i}_mol'] == 0.0
        assert det[f'leach_no3_L{i}_mol'] == 0.0
        assert det[f'leach_no3_export_L{i}_mol'] == 0.0
        assert det[f'leach_no3_transfer_L{i}_mol'] == 0.0


def test_anion_columns_track_real_fluxes_and_pair_anion(profile, soil_info):
    """阴离子列接线真实通量: 有水量 + 有阴离子 ⇒ 正列值; `An` 由只读观测驱动

    `leach_an_mol` 的口径源 = `DiagnosticOutput.pair_anion_conc` (An 不入 state)
    ⇒ 施肥场 (电荷配对注入 An⁻) 应给出 `leach_an_L1_mol > 0`。
    """
    det = _run(_engine_companion(), profile, soil_info,
               [_flux_event()], action=_fert_action())[0]
    assert det['leach_cl_L1_mol'] > 0.0        # 降水化学携带 Cl⁻
    assert det['leach_s_L1_mol'] > 0.0         # 降水化学 + ZnSO₄ 携带 SO₄²⁻
    assert det['leach_an_L1_mol'] > 0.0        # 电荷配对注入 An⁻ (只读观测口径)
    # L1 lat+base=0 ⇒ 全部阴离子通量只走 drains 通道 (与通道语义一致)
    assert det['leach_cl_L1_mol'] > det['leach_cl_L2_mol'] > 0.0