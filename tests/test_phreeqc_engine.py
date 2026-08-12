import pytest
from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction


FORCING = {"precip": 100.0, "temp": 25.0, "pCO2": 0.015}


def test_backend_official_default():
    e = PhreeqcEngine(database="phreeqc.dat", mode="auto")
    assert e.backend == "official"


def test_backend_legacy_forced_to_official(capsys):
    e = PhreeqcEngine(database="phreeqc.dat", mode="auto",
                      backend="phreeqpython")
    out = capsys.readouterr().out
    assert e.backend == "official"
    assert "已废弃" in out


def test_build_initial_state(profile, soil_info):
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    assert state.ph > 0
    assert len(state.exchange) > 0
    assert len(state.minerals) > 0
    assert state.volume > 0


def test_input_uses_forcing_pco2(profile, soil_info):
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    forcing = dict(FORCING, pCO2=0.020)
    inp = e._build_phreeqc_input(state, forcing, MonthlyAction(), profile)
    assert "-pressure     0.020000" in inp


def test_input_contains_precip_ions(profile, soil_info, precip_chem):
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                      precip_chem=precip_chem)
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    for sp in ("Cl-", "SO4-2", "NO3-", "F-", "NH4+"):
        assert sp in inp, sp


def test_input_select_output_has_f(profile, soil_info):
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "-totals Ca Mg K Na Al P Zn Cl C S N Si F" in inp


def test_simplified_state_preserved(profile, soil_info):
    e = PhreeqcEngine(database="phreeqc.dat", mode="simplified")
    state = e.build_initial_state(profile, soil_info, 0.015)
    old_exchange = dict(state.exchange)
    new_state, _ = e.run_monthly_step(state, FORCING, MonthlyAction(),
                                      profile)
    assert new_state.exchange == old_exchange


def test_monthly_step_no_fallback(profile, soil_info):
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    new_state, diag = e.run_monthly_step(state, FORCING, MonthlyAction(),
                                         profile)
    assert new_state.ph > 0
    assert not e._permanent_fallback


def test_mineral_scale_consistent(profile, soil_info):
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    assert e.mineral_scale == 0.001
