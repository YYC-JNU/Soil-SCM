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
    """v0.6.1 (Q7): HX_LOGK 常量 = 3.0 (2026-08-20 扫描标定: 平衡 pH 4.99 收敛观测)"""
    from src.constants import HX_LOGK
    assert HX_LOGK == 3.0


def test_calc_exchange_site_total_includes_hx(profile, soil_info):
    """v0.6.1 (Q7): _calc_exchange_site_total 计入 HX 一价位点"""
    b = _builder(profile, soil_info)
    exchange = b.build_exchange()
    total_with_hx = b._calc_exchange_site_total(exchange)
    total_without = total_with_hx - exchange.get('HX', 0.0)
    assert total_with_hx > total_without
