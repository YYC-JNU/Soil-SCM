"""测试 工单 97 (2026-09-29): 阳离子出流**荷电当量**只读列 (P3-ANC 闭合的缺列; **只读**)

覆盖:
  - 口径契约: `event_accounting._COLUMN_FORMATS` **只追加** 3 列
    (历史列名/顺序逐位不变; 工单94 的 5 列块与工单95 的 6 列块位置也钉住)
  - 纯函数: `cation_charge_columns` — 电荷权重 (Ca/Mg ×2, K/Na ×1)、
    两通道和、**恒等式** (`total == transfer + export`)、非物理输入护栏
  - 口径区分: 新列 = **荷电当量 molc/ha**; 旧 `leach_base_mmol` = Ca+Mg+K **摩尔和**
    ⇒ 二者不得互相替代 (同量输入下荷电当量 ≥ 摩尔和)
  - 引擎集成: 逐层逐场列存在 + 恒等式成立 + 通道语义 (drains→transfer,
    lateral/baseflow→export) + 零水量 ⇒ 全 0 + 真实通量 ⇒ 正列值
"""

import pytest

from src.event_accounting import (_COLUMN_FORMATS, CATION_LEACH_IONS,
                                  cation_charge_columns, leach_flux_mol)
from src.hydrology import RainEvent
from src.phreeqc_engine import DiagnosticOutput, PhreeqcEngine
from src.scenario_controller import MonthlyAction

FORCING = {"temp": 25.0, "pCO2": 0.015}

# 历史冻结基线 (2026-09-29 快照; 工单94 / 95 之前)
_HISTORICAL_KEYS = [
    'n_no3_pool', 'leach_no3_mol', 'base_loss_eq', 'base_mode',
    'e_base_anion_eq', 'companion_mode', 'companion_eq', 'inert_eq',
    'acid_eq', 'nh4_exchanged_eq', 'lateral_L', 'baseflow_L', 'flush_L',
    'leach_N_mmol', 'leach_base_mmol', 'ph',
    # 工单96 (2026-09-28): 位点往返只读观测
    'site_total_molc', 'site_gap_molc',
]
_W94_KEYS = ['leach_cl_mol', 'leach_s_mol', 'leach_an_mol',
             'leach_no3_export_mol', 'leach_no3_transfer_mol']
_W95_KEYS = ['c4_storage_delta_mol', 'c4_inflow_mol', 'c4_drain_out_mol',
             'c4_out_system_mol', 'c4_flush_mol', 'co2_gas_exchange_mol']
_W97_KEYS = ['leach_cation_eq_molc', 'leach_cation_transfer_molc',
             'leach_cation_export_molc']


# ---------------------------- 口径契约 (S1) ----------------------------

def test_column_formats_appends_cation_charge_columns():
    """口径契约: 3 新列入 `_COLUMN_FORMATS` 且列名格式固定"""
    fmt = dict(_COLUMN_FORMATS)
    assert fmt['leach_cation_eq_molc'] == 'leach_cation_eq_L{}_molc'
    assert fmt['leach_cation_transfer_molc'] == 'leach_cation_transfer_L{}_molc'
    assert fmt['leach_cation_export_molc'] == 'leach_cation_export_L{}_molc'


def test_column_formats_is_append_only_prefix_unchanged():
    """**只追加**契约: 历史前缀 + 94 块 + 95 块位置逐位不变，新 3 列在其后

    ⚠️ 不断言总列数（后续只读票会继续追加）。
    """
    keys = [k for k, _ in _COLUMN_FORMATS]
    n = len(_HISTORICAL_KEYS)
    assert keys[:n] == _HISTORICAL_KEYS
    assert keys[n:n + 5] == _W94_KEYS
    assert keys[n + 5:n + 11] == _W95_KEYS
    assert keys[n + 11:n + 14] == _W97_KEYS


def test_cation_ion_charge_weights():
    """电荷权重唯一来源: Ca/Mg ×2、K/Na ×1（与 `solution_base_eq` 同约定）"""
    assert dict(CATION_LEACH_IONS) == {'Ca': 2.0, 'Mg': 2.0,
                                       'K': 1.0, 'Na': 1.0}


# ---------------------------- 纯函数 (S2) ----------------------------

def test_cation_charge_columns_two_channel_sum_and_identity():
    """两通道和 = transfer + export；且等于 Σ z·c·(drain + out)"""
    conc = {'Ca': 1.0e-4, 'Mg': 5.0e-5, 'K': 2.0e-4, 'Na': 1.0e-4}
    out = cation_charge_columns(conc, drain_L=1.0e5, out_system_L=2.0e5)
    expect = (2.0 * 1.0e-4 + 2.0 * 5.0e-5 + 2.0e-4 + 1.0e-4) * 3.0e5
    assert out['leach_cation_eq_molc'] == pytest.approx(expect, rel=1e-12)
    assert out['leach_cation_eq_molc'] == pytest.approx(
        out['leach_cation_transfer_molc']
        + out['leach_cation_export_molc'], rel=1e-12, abs=1e-12)


def test_cation_charge_is_molc_and_exceeds_molar_sum_for_divalent():
    """**口径区分**: 纯 Ca 输入 ⇒ 荷电当量 = 2 × 摩尔和（不得混用）"""
    conc = {'Ca': 1.0e-3}
    out = cation_charge_columns(conc, 1.0e5, 0.0)
    molar = leach_flux_mol(conc['Ca'], 1.0e5)          # mol/ha (旧口径形状)
    assert out['leach_cation_eq_molc'] == pytest.approx(2.0 * molar,
                                                       rel=1e-12)
    assert out['leach_cation_export_molc'] == 0.0


def test_cation_charge_columns_guard_nonphysical_inputs():
    """护栏: 负浓度/零水量/NaN/Inf/缺键/不可解析 ⇒ 0.0（绝不抛异常）

    ⚠️ 只对**非物理**输入归零；正有限浓度照常计入（避免把有效通量误清）。
    """
    zeros = {'leach_cation_eq_molc': 0.0, 'leach_cation_transfer_molc': 0.0,
             'leach_cation_export_molc': 0.0}
    assert cation_charge_columns({'Ca': -1.0}, 1e5, 1e5) == zeros
    assert cation_charge_columns({}, 1e5, 1e5) == zeros
    assert cation_charge_columns({'Ca': 'x'}, 1e5, 1e5) == zeros
    assert cation_charge_columns({'Ca': 1e-4}, 0.0, 0.0) == zeros
    # 非物理混合输入：仅 Na 计入 (1e-4 × 1e5 = 10.0 molc/ha)
    z = cation_charge_columns({'Ca': -1.0, 'Mg': float('nan'),
                               'K': float('inf'), 'Na': 1e-4}, 1e5, 0.0)
    assert z['leach_cation_transfer_molc'] == pytest.approx(10.0, rel=1e-12)
    assert z['leach_cation_export_molc'] == 0.0
    # 全部非物理 ⇒ 0.0
    assert cation_charge_columns({'Ca': -1.0, 'Mg': float('nan'),
                                  'K': float('inf')}, 1e5, 1e5) == zeros


def test_diag_cation_columns_do_not_add_new_fields():
    """只读护栏: 本票**不**给 `DiagnosticOutput` 增字段（口径源即 `solution`）"""
    d = DiagnosticOutput()
    assert not hasattr(d, 'cation_eq') and not hasattr(d, 'base_eq')


# ---------------------------- 引擎集成: 逐层逐场 (S3) ----------------------------

def _engine_companion():
    """companion 启用 ⇒ `An-` 已定义 + 电荷配对注入生效 (口径抄 test_anion_budget)"""
    from src.config_manager import CompanionConfig
    return PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                         companion_cfg=CompanionConfig(enable=True))


def _fert_action():
    return MonthlyAction(apply_fertilizer=True, n_amount=12.0, p2o5_amount=4.0,
                         k2o_amount=9.0, mgo_amount=3.0, znso4_amount=1.0)


def _states(e, profile, soil_info, n_layers=4):
    """生产口径: 先预平衡 (否则远起点步触发 D6 已登记的"无 react 行"退化)"""
    states = [e.build_initial_state(profile, soil_info, 0.015)
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


def _zero_flow_event(n_layers=4):
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


def test_cation_charge_identity_holds_for_every_layer_and_event(profile,
                                                                soil_info):
    """**恒等式** (工单97 §2-3): `eq == transfer + export` 逐层逐场成立"""
    details = _run(_engine_companion(), profile, soil_info,
                   [_flux_event(), _flux_event()])
    assert len(details) == 2
    for det in details:
        for i in (1, 2, 3, 4):
            assert det[f'leach_cation_eq_L{i}_molc'] == pytest.approx(
                det[f'leach_cation_transfer_L{i}_molc']
                + det[f'leach_cation_export_L{i}_molc'],
                rel=1e-12, abs=1e-12)
    # ⭐ 只读护栏: 注入基准不受本列影响 ⇒ 第 2 场伴随当量 == 第 1 场淋失量
    assert details[1]['companion_eq_L1'] == pytest.approx(
        details[0]['leach_no3_L1_mol'], rel=1e-12)


def test_cation_channel_semantics_follow_event_water(profile, soil_info):
    """通道语义 (独立真值 = 事件水量字段)

    L1: drains=1e5, lat+base=0 ⇒ transfer>0 且 export==0
    L4: drains=0, baseflow=1e5 ⇒ export>0 且 transfer==0
    """
    det = _run(_engine_companion(), profile, soil_info, [_flux_event()])[0]
    assert det['leach_cation_transfer_L1_molc'] > 0.0
    assert det['leach_cation_export_L1_molc'] == 0.0
    assert det['leach_cation_transfer_L4_molc'] == 0.0
    assert det['leach_cation_export_L4_molc'] > 0.0


def test_cation_columns_zero_under_zero_water_flux(profile, soil_info):
    """零水量 ⇒ 阳离子列**全 0** (只读记账不凭空造通量)"""
    det = _run(_engine_companion(), profile, soil_info,
               [_zero_flow_event()])[0]
    for i in (1, 2, 3, 4):
        assert det[f'leach_cation_eq_L{i}_molc'] == 0.0
        assert det[f'leach_cation_transfer_L{i}_molc'] == 0.0
        assert det[f'leach_cation_export_L{i}_molc'] == 0.0


def test_cation_columns_track_real_fluxes_and_exceed_molar_column(
        profile, soil_info):
    """接线真实通量 + **口径区分**: 施肥场 Ca 主导 ⇒ 荷电当量 ≥ 旧摩尔和列"""
    det = _run(_engine_companion(), profile, soil_info,
               [_flux_event()], action=_fert_action())[0]
    for i in (1, 2, 3, 4):
        assert det[f'leach_cation_eq_L{i}_molc'] > 0.0
    # 旧列 (Ca+Mg+K **摩尔和**, mmol/ha) 与新列 (molc/ha) 量纲不同:
    # 新列 ≥ 旧列/1000 (每摩尔 Ca/Mg 计 2 当量 ⇒ 恒成立)
    assert det['leach_cation_eq_L1_molc'] >= \
        det['leach_base_L1_mmol'] / 1000.0