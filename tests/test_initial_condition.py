import math
import pytest
from src.initial_condition import InitialConditionBuilder, MINERAL_SCALE


def _builder(profile, soil_info):
    return InitialConditionBuilder(profile, soil_info, pCO2=0.015)


def test_soil_mass(profile, soil_info):
    b = _builder(profile, soil_info)
    # 1.2 g/cm3 × 0.3m × 10000 m2/ha = 1200 kg/m3 × 3000 m3 = 3.6e6 kg/ha
    assert abs(b.soil_mass_kg - 3.6e6) / 3.6e6 < 0.01


def test_porosity(profile, soil_info):
    b = _builder(profile, soil_info)
    # 1 - 1.2/2.65 ≈ 0.547
    assert 0 < b.porosity < 1
    assert abs(b.porosity - (1 - 1.2 / 2.65)) < 0.001


def test_solution_volume_positive(profile, soil_info):
    b = _builder(profile, soil_info)
    assert b.solution_volume_L > 0


def test_cec_total(profile, soil_info):
    b = _builder(profile, soil_info)
    # 12 cmol/kg = 0.12 mol/kg; 0.12 × 3.6e6 kg = 4.32e5 mol
    assert abs(b.cec_total_mol - 4.32e5) / 4.32e5 < 0.05


def test_exchange_sites_conserved(profile, soil_info):
    b = _builder(profile, soil_info)
    exchange = b.build_exchange()
    total = b._calc_exchange_site_total(exchange)
    assert abs(total - b.cec_total_mol) / b.cec_total_mol < 0.01


def test_build_exchange_weathered_gap_al_dominant(profile, soil_info):
    """工单83: 深层风化层 (低 CEC) 缺口 GAP 分配偏 AlX3

    红壤风化层 (CEC ≤ WEATHERED_GAP_CEC_THRESHOLD) 交换 Al 主导 — 缺口
    主要补 AlX3 (三价) 而非 NaX (盐基), 减少 NaX 虚高盐基饱和度 (BS)。
    """
    from src.input_reader import InputReader
    from src.config_manager import LayerOverrideConfig
    from src.constants import (WEATHERED_GAP_CEC_THRESHOLD, WEATHERED_EXCH_CA,
                               WEATHERED_EXCH_MG, WEATHERED_EXCH_K,
                               WEATHERED_EXCH_NA, WEATHERED_EXCH_AL,
                               WEATHERED_EXCH_H)
    reader = InputReader('data/soil_survey.csv', 'data/exchangeable_ions.csv')
    base = reader.build_soil_profile()
    # 构造风化层 profile (低 CEC + 低盐基 + 高 Al, 深层)
    lo = LayerOverrideConfig(
        cec=WEATHERED_GAP_CEC_THRESHOLD - 1.0,
        exch_ca=WEATHERED_EXCH_CA[3], exch_mg=WEATHERED_EXCH_MG[3],
        exch_k=WEATHERED_EXCH_K[3], exch_na=WEATHERED_EXCH_NA[3],
        exch_al=WEATHERED_EXCH_AL[3], exch_h=WEATHERED_EXCH_H[3])
    weath = reader.apply_layer_override(base, lo, 40.0)
    b = _builder(weath, soil_info)
    ex = b.build_exchange()
    # 交换位点守恒仍成立
    total = b._calc_exchange_site_total(ex)
    assert abs(total - b.cec_total_mol) / b.cec_total_mol < 0.01
    # 风化层: Al 电荷 > Na 电荷 (缺口偏 AlX3, 非 NaX)
    al_charge = ex['AlX3'] * 3.0
    na_charge = ex['NaX']
    assert al_charge > na_charge
    # 非风化层 (高 CEC) 对照: 保持原 GAP — 缺口纯贡献 (exch 全 0) 下
    # NaX 0.4 > AlX3 0.3 (电荷), 即 Na > Al
    lo2 = LayerOverrideConfig(cec=12.0, exch_ca=0, exch_mg=0, exch_k=0,
                              exch_na=0, exch_al=0, exch_h=0)
    top = reader.apply_layer_override(base, lo2, 20.0)
    b2 = _builder(top, soil_info)
    ex2 = b2.build_exchange()
    assert ex2['AlX3'] * 3.0 < ex2['NaX']


def test_charge_balance_within_tolerance(profile, soil_info):
    b = _builder(profile, soil_info)
    solution = b.build_solution()
    imbalance = b._check_charge_balance(solution)
    assert abs(imbalance) < 1e-3


def test_minerals_no_anatase(profile, soil_info):
    b = _builder(profile, soil_info)
    minerals = b.build_minerals()
    assert "anatase" not in minerals
    assert len(minerals) > 0


def test_amorphous_aloh3_in_minerals(profile, soil_info):
    """L9: 非晶质 Al(OH)3(a) 缓冲相加入矿物相 (红壤真实组分, v0.4.0)"""
    b = _builder(profile, soil_info)
    minerals = b.build_minerals()
    assert "Al(OH)3(a)" in minerals
    assert minerals["Al(OH)3(a)"] > 0


def test_minerals_all_positive(profile, soil_info):
    b = _builder(profile, soil_info)
    minerals = b.build_minerals()
    for name, moles in minerals.items():
        assert moles > 0, name


def test_mineral_scale_constant():
    assert MINERAL_SCALE == 0.001


def test_gas_phase_uses_pco2(profile, soil_info):
    b = _builder(profile, soil_info)
    inp = b.build_phreeqc_input(include_surface=False)
    assert f"-pressure     {b.pCO2:.6f}" in inp


def test_validate_passes(profile, soil_info):
    b = _builder(profile, soil_info)
    assert b.validate() is True


def test_theta_init_field_capacity(profile, soil_info):
    """v0.5.3/Q8: 初始 θ 由 VGM 从 initial_psi_cm=-100 (田间持水量) 正算

    θ_r<θ_init<θ_s (含水合理区间); 默认 profile: clay=25, porosity≈0.547
    → θ_init≈0.41 (实测约 0.75θ_s, 非"50% 饱和"的过湿假设)。
    """
    b = _builder(profile, soil_info)
    assert b.theta_init > 0
    assert b.theta_init < b.porosity
    # L1 clay 25% 回归: θ_r=0.06 → θ_init 显著高于 θ_r
    assert b.theta_init > 0.30


def test_solution_volume_theta_coupled(profile, soil_info):
    """v0.5.3/Q8: 化学初始溶液体积 = θ_init×depth×1e5 (与水文 θ 联动)"""
    b = _builder(profile, soil_info)
    assert b.solution_volume_L == pytest.approx(
        b.theta_init * profile.effective_depth * 1e5)



# ==================== v0.6.1: HX 交换酸注入 + GAP_H 缺口重分配 (S4, spec 62 Q7) ====================

def test_exch_h_maps_to_hx_not_na(profile, soil_info):
    """v0.6.1 (Q7): exch_h 直接映射 HX 交换物种, 不再并入 NaX

    数学断言: NaX = exch_na/100×mass + 缺口×GAP_NA (余量盐基通道, 不含 exch_h);
              HX  = exch_h/100×mass + 缺口×GAP_H (交换性酸)
    """
    from src.constants import GAP_H_FRACTION, GAP_AL_FRACTION
    b = _builder(profile, soil_info)
    exchange = b.build_exchange()
    assert 'HX' in exchange
    assert exchange['HX'] > 0
    # HX 来源 = exch_h (从 Na 剥离) + 缺口×GAP_H
    gap_na_frac = 1.0 - GAP_H_FRACTION - GAP_AL_FRACTION
    # NaX = exch_na 部分 (不再含 exch_h) + 缺口×GAP_NA
    # 验证: NaX ≥ exch_na 部分 (exch_h 剥离后 NaX 不含 H)
    na_from_exch = profile.exch_na / 100.0 * b.soil_mass_kg
    assert exchange['NaX'] >= na_from_exch
    # 交换性 H 全部进入 HX (exch_h 不并入 NaX)
    h_from_exch = profile.exch_h / 100.0 * b.soil_mass_kg
    assert exchange['HX'] >= h_from_exch


def test_gap_three_channel_redistribution(profile, soil_info):
    """v0.6.1 (Q7): CEC 缺口按 GAP_H/GAP_AL/NaX 三通道重分配"""
    from src.constants import GAP_H_FRACTION, GAP_AL_FRACTION
    b = _builder(profile, soil_info)
    exchange = b.build_exchange()
    # CEC 总量守恒 (关键不变量)
    total = b._calc_exchange_site_total(exchange)
    assert abs(total - b.cec_total_mol) / b.cec_total_mol < 0.01
    # HX > 0 (缺口有 HX 通道 + exch_h)
    assert exchange['HX'] > 0
    # GAP_H_FRACTION 生效: HX 电荷占比应显著 (exch_h + 缺口×GAP_H)
    hx_charge_frac = exchange['HX'] / b.cec_total_mol
    assert hx_charge_frac >= GAP_H_FRACTION * 0.5


def test_hx_in_phreeqc_input(profile, soil_info):
    """v0.6.1 (Q7): 初始条件 PHREEQC 输入含 EXCHANGE 块 HX 行"""
    b = _builder(profile, soil_info)
    inp = b.build_phreeqc_input(include_surface=False)
    assert 'HX' in inp


def test_hx_logk_constant():
    """v0.6.1 (Q7): HX_LOGK 常量 (v0.7.0 工单76 调优 B: 3.0→2.8 减弱锁酸)"""
    from src.constants import HX_LOGK
    assert HX_LOGK == 2.8


def test_calc_exchange_site_total_includes_hx(profile, soil_info):
    """v0.6.1 (Q7): _calc_exchange_site_total 计入 HX 一价位点"""
    b = _builder(profile, soil_info)
    exchange = b.build_exchange()
    total_with_hx = b._calc_exchange_site_total(exchange)
    total_without = total_with_hx - exchange.get('HX', 0.0)
    assert total_with_hx > total_without


# ==================== 工单88 (2026-09-03): L1 初始盐基物理化 ====================

# 理论值计算 (L1 观测数据 data/soil_survey.csv + exchangeable_ions.csv):
#   CEC=12, 六离子 3.0+1.5+0.5+0.2+2.0+1.0 = 8.2 → 缺口 gap = 3.8 cmol/kg。
#   旧三通道 (0.3/0.3/0.4): NaX 缺口 1.52 cmol/kg (盐基虚高伪影燃料)。
#   物理化口径要求 NaX 余量 ≤ 0.2 且 H+Al ≥ 0.8 (spec 88 §3.2 网格约束)。


def test_surface_gap_hplus_al_constraints():
    """工单88 (4a): L1 表层物理化口径满足物理约束 — NaX 余量 ≤0.2, H+Al ≥0.8

    避免 L1 缺口被高盐基 Na 填充 (v85 natural 中期碱化伪影燃料)。
    """
    from src.constants import (GAP_H_FRACTION, GAP_AL_FRACTION,
                               SURFACE_GAP_H_FRACTION, SURFACE_GAP_AL_FRACTION)
    # 旧全局口径: NaX 余量 0.4 (>0.2, 伪影来源)
    assert 1.0 - GAP_H_FRACTION - GAP_AL_FRACTION > 0.20
    # 新表层物理化口径 (9c 扫描网格约束): NaX ≤ 0.2 且 H+Al ≥ 0.8
    na_frac = 1.0 - SURFACE_GAP_H_FRACTION - SURFACE_GAP_AL_FRACTION
    assert 0.0 <= na_frac <= 0.20
    assert SURFACE_GAP_H_FRACTION + SURFACE_GAP_AL_FRACTION >= 0.80


def test_surface_gap_applies_to_layer0(profile, soil_info):
    """工单88 (4a): layer_index=0 (L1 表层) 缺口分配用物理化口径 — NaX 虚高消除

    L1 = 耕层表层 (CEC=12), 缺口 3.8 cmol/kg; 物理化后缺口 NaX ≤ 0.2×gap
    (旧 0.4×gap=1.52 cmol/kg NaX 盐基伪影燃料), 偏 AlX3/HX 酸缓冲。
    """
    from src.constants import SURFACE_GAP_H_FRACTION, SURFACE_GAP_AL_FRACTION
    b = InitialConditionBuilder(profile, soil_info, pCO2=0.015, layer_index=0)
    exchange = b.build_exchange()
    # CEC 总量守恒 (关键不变量)
    total = b._calc_exchange_site_total(exchange)
    assert abs(total - b.cec_total_mol) / b.cec_total_mol < 0.01
    # 缺口 NaX 余量 ≤ 0.2 (旧 0.4): 用电荷当量计算
    na_gap_charge_cmol = (exchange['NaX'] * 1.0 * 100.0 / b.soil_mass_kg
                          - profile.exch_na)
    gap_cmol = b.profile.cec - (profile.exch_ca + profile.exch_mg +
                                profile.exch_k + profile.exch_na +
                                profile.exch_al + profile.exch_h)
    assert gap_cmol > 0
    assert na_gap_charge_cmol / gap_cmol <= 0.20 + 1e-9
    # H/Al 缺口通道显著 (H+Al ≥ 0.8)
    al_gap_charge_cmol = (exchange['AlX3'] * 3.0 * 100.0 / b.soil_mass_kg
                          - profile.exch_al)
    h_gap_charge_cmol = (exchange['HX'] * 1.0 * 100.0 / b.soil_mass_kg
                         - profile.exch_h)
    assert (h_gap_charge_cmol + al_gap_charge_cmol) / gap_cmol >= 0.80 - 1e-9
    # 常量生效一致性 (spec 88 §3.2 网格取值落在扫描范围)
    assert SURFACE_GAP_H_FRACTION in (0.3, 0.4, 0.5)
    assert SURFACE_GAP_AL_FRACTION in (0.3, 0.4, 0.5, 0.6)


def test_surface_gap_keeps_deeper_layers_unchanged(profile, soil_info,
                                                   monkeypatch):
    """工单88 (判据甲): layer_index>0 (L2~L4) 缺口分配与 v85 逐位一致

    L2 CEC=9 (非风化, 走旧三通道) 与 L3/L4 CEC≤7 (风化口径) 均不得因 L1
    物理化波及 — 表层物理化仅对 layer_index=0 生效。
    """
    from src.input_reader import InputReader
    from src.config_manager import LayerOverrideConfig
    from src.constants import (WEATHERED_CEC_4LAYER, WEATHERED_EXCH_CA,
                               WEATHERED_EXCH_MG, WEATHERED_EXCH_K,
                               WEATHERED_EXCH_NA, WEATHERED_EXCH_AL,
                               WEATHERED_EXCH_H)
    reader = InputReader('data/soil_survey.csv', 'data/exchangeable_ions.csv')
    base = reader.build_soil_profile()
    # 构造 L2 profile (CEC=9) 与 L4 profile (CEC=4)
    profiles = []
    for idx in (1, 3):
        lo = LayerOverrideConfig(
            cec=WEATHERED_CEC_4LAYER[idx],
            exch_ca=WEATHERED_EXCH_CA[idx], exch_mg=WEATHERED_EXCH_MG[idx],
            exch_k=WEATHERED_EXCH_K[idx], exch_na=WEATHERED_EXCH_NA[idx],
            exch_al=WEATHERED_EXCH_AL[idx], exch_h=WEATHERED_EXCH_H[idx])
        profiles.append(reader.apply_layer_override(base, lo, 20.0))
    for p, li in zip(profiles, (1, 3)):
        b_surface = InitialConditionBuilder(p, soil_info, pCO2=0.015,
                                            layer_index=li)
        b_baseline = InitialConditionBuilder(p, soil_info, pCO2=0.015,
                                             layer_index=None)
        ex_surface = b_surface.build_exchange()
        ex_baseline = b_baseline.build_exchange()
        for ion in ('CaX2', 'MgX2', 'KX', 'NaX', 'AlX3', 'HX'):
            assert ex_surface[ion] == ex_baseline[ion], (
                f"layer_index={li} {ion}: 表层物理化不应波及深层")


def test_surface_gap_params_monkeypatchable(profile, soil_info, monkeypatch):
    """工单88 (9c 扫描): 表层 GAP 参数可 monkeypatch 扫描 (探针无侵入)"""
    import src.initial_condition as ic
    monkeypatch.setattr(ic, "SURFACE_GAP_H_FRACTION", 0.4)
    monkeypatch.setattr(ic, "SURFACE_GAP_AL_FRACTION", 0.6)
    b = InitialConditionBuilder(profile, soil_info, pCO2=0.015, layer_index=0)
    exchange = b.build_exchange()
    total = b._calc_exchange_site_total(exchange)
    assert abs(total - b.cec_total_mol) / b.cec_total_mol < 0.01
    # NaX 余量 = 1 - 0.4 - 0.6 = 0
    na_gap_charge_cmol = (exchange['NaX'] * 100.0 / b.soil_mass_kg
                          - profile.exch_na)
    assert na_gap_charge_cmol <= 1e-9
