import pytest
from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction


FORCING = {"precip": 100.0, "temp": 25.0, "pCO2": 0.015}


def test_backend_official_default():
    e = PhreeqcEngine(database="phreeqc.dat", mode="auto")
    assert e.backend == "official"


def test_backend_legacy_forced_to_official(caplog):
    e = PhreeqcEngine(database="phreeqc.dat", mode="auto",
                      backend="phreeqpython")
    assert e.backend == "official"
    # Q15 改造: 警告走 logging, 由 pytest caplog 捕获
    assert any("已废弃" in rec.message for rec in caplog.records)


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


def test_error_write_failure_does_not_break_flow(profile, soil_info, monkeypatch, tmp_path):
    """T01: error.inp 写入失败时不中断主流程, 降级路径正常完成"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated phreeqc failure")

    monkeypatch.setattr(e.official, "RunString", boom)
    # 模拟 error.inp 路径为非法目录 → 写入必然失败
    monkeypatch.setattr("src.phreeqc_engine.ERROR_INP_PATH",
                        str(tmp_path / "no_such_dir" / "error.inp"))
    monkeypatch.chdir(tmp_path)
    new_state, _ = e.run_monthly_step(state, FORCING, MonthlyAction(), profile)

    # 降级路径正常完成, 状态仍有意义
    assert e._permanent_fallback
    assert e.last_error_message == "simulated phreeqc failure"
    assert new_state.ph > 0


def test_simplified_with_fertilizer_no_crash(profile, soil_info):
    """P4 回归: simplified 模式 + 施肥指令不崩溃 (fertilizer_amount 已修复)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="simplified")
    state = e.build_initial_state(profile, soil_info, 0.015)
    act = MonthlyAction(apply_fertilizer=True, n_amount=12.0)
    new_state, _ = e.run_monthly_step(state, FORCING, act, profile)
    assert new_state.ph > 0


def test_error_diagnostics_on_failure(profile, soil_info, monkeypatch, tmp_path):
    """T3/Q18/T01: 引擎失败时记录 last_error_message / last_error_input, 并写入 error.inp"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    assert e.last_error_message is None
    assert e.last_error_input is None

    state = e.build_initial_state(profile, soil_info, 0.015)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated phreeqc failure")

    monkeypatch.setattr(e.official, "RunString", boom)
    # T01: 隔离测试, 切换工作目录使 error.inp 写入 tmp_path, 不污染项目根
    monkeypatch.chdir(tmp_path)
    new_state, _ = e.run_monthly_step(state, FORCING, MonthlyAction(), profile)

    assert e._permanent_fallback
    assert e.last_error_message == "simulated phreeqc failure"
    assert "SELECTED_OUTPUT" in e.last_error_input  # 内存属性保留

    # T01: 磁盘复现文件自动生成且内容为完整输入
    error_file = tmp_path / "error.inp"
    assert error_file.exists()
    content = error_file.read_text(encoding="utf-8")
    assert "SELECTED_OUTPUT" in content
    assert "SOLUTION" in content
