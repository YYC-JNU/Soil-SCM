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
