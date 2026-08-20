"""测试 v0.5.0 pre_equilibrate 预平衡 (初始状态自洽化, L9 落地)

  - 无干预多步平衡: 初始构建后连续空步 (无降水/施肥/石灰, 固定 pCO2)
  - 让溶液/交换/矿物纯内部重新分配至稳态, 作为长期模拟初始态
  - config 默认开启 (enable_pre_equilibration=True), max_steps 默认 60
  - simplified 引擎跳过 (无化学平衡概念)
"""

import pytest

from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction


FORCING = {"precip": 0.0, "temp": 25.0, "pCO2": 0.015}


def test_config_defaults():
    """config: enable_pre_equilibration 默认 true, max_steps 默认 60"""
    from src.config_manager import SimulationConfig
    s = SimulationConfig()
    assert s.enable_pre_equilibration is True
    assert s.pre_equilibration_max_steps == 60


def test_pre_equilibrate_returns_state(profile, soil_info):
    """pre_equilibrate 返回平衡后状态 (ph/exchange 有效)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    eq_state = e.pre_equilibrate(state, profile)
    assert eq_state is not None
    assert eq_state.ph > 0
    assert len(eq_state.exchange) > 0


def test_pre_equilibrate_converges(profile, soil_info):
    """预平衡后状态收敛 (盐基离子锚定保持 <10%, v0.5.0 支柱②)

    v0.6.1 (spec 62 Q7): HX 酸库 (log_k=3.0) 引入后 AlX3 被排挤 (-86%,
    物理真实), 不再锚定 AlX3/HX; 盐基 Ca/Mg/K/Na 仍锚定 <10%。
    """
    from src.initial_condition import InitialConditionBuilder
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    eq_state = e.pre_equilibrate(state, profile)
    # 再跑一步 (无注入), 盐基交换离子锚定应保持 (v0.5.0: pH 不锚定, 仅离子)
    b = InitialConditionBuilder(profile, None, pCO2=0.015)
    targets = b.build_exchange()
    s1, _ = e.run_monthly_step(eq_state, FORCING, MonthlyAction(), profile)
    for ion in ('CaX2', 'MgX2', 'KX', 'NaX'):
        target = targets.get(ion, 0.0)
        if target == 0.0:
            continue
        rel = abs(s1.exchange.get(ion, 0.0) - target) / target
        assert rel < 0.10, f"{ion}: 锚定失效 (偏差={rel:.1%})"


def test_pre_equilibrate_max_steps_cap(profile, soil_info):
    """max_steps 上限: 不收敛时在 max_steps 终止不报错"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    eq_state = e.pre_equilibrate(state, profile, max_steps=3)
    assert eq_state is not None
    assert eq_state.ph > 0


def test_simplified_skips_pre_equilibrate(profile, soil_info):
    """simplified 引擎跳过预平衡 (返回原状态, 无化学平衡概念)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="simplified")
    state = e.build_initial_state(profile, soil_info, 0.015)
    state.ph = 6.0
    eq_state = e.pre_equilibrate(state, profile)
    assert eq_state.ph == 6.0


def test_pre_equilibrate_records_diagnostics(profile, soil_info):
    """工单 17: 预平衡后记录偏离度诊断 (pH + 全部交换性离子)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    e.pre_equilibrate(state, profile)
    diag = getattr(e, 'last_pre_equilibration_diagnostics', None)
    assert diag is not None
    assert 'pH' in diag
    assert isinstance(diag['pH'], tuple) and len(diag['pH']) == 2
    # config 输入的交换性离子观测值全部纳入 (Q5=A)
    for ion in ('CaX2', 'MgX2', 'KX', 'NaX', 'AlX3'):
        assert ion in diag, ion
        init_val, eq_val = diag[ion]
        assert isinstance(init_val, float)
        assert isinstance(eq_val, float)


def test_pre_equilibrate_diagnostics_match_snapshot(profile, soil_info):
    """工单 17: 诊断初始值 = 预平衡前快照 (初始 vs 稳态对比正确)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    init_ph = state.ph
    init_exch = dict(state.exchange)
    e.pre_equilibrate(state, profile)
    diag = e.last_pre_equilibration_diagnostics
    assert abs(diag['pH'][0] - init_ph) < 1e-9
    for ion in ('CaX2', 'MgX2', 'KX', 'NaX', 'AlX3'):
        assert abs(diag[ion][0] - init_exch.get(ion, 0.0)) < 1e-9, ion


def test_pre_equilibrate_diagnostics_loggable(profile, soil_info):
    """工单 17: 偏离度诊断数据完整可输出 (日志经模块 logger, 控制台可见)"""
    import logging
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    e.pre_equilibrate(state, profile)
    assert hasattr(e, '_log_pre_equilibration_diagnostics')
    diag = e.last_pre_equilibration_diagnostics
    # 诊断含 pH 与全部交换离子, 初始/稳态值可计算相对变化
    for ion in ('pH', 'CaX2', 'MgX2', 'KX', 'NaX', 'AlX3'):
        init_v, eq_v = diag[ion]
        assert isinstance(init_v, float) and isinstance(eq_v, float)
    # 模块 logger 可用 (日志经 soil_scm.phreeqc_engine 输出)
    logger = logging.getLogger('soil_scm.phreeqc_engine')
    assert logger is not None


def test_pre_equilibrate_anchors_ph(profile, soil_info):
    """观测锚定 (grilling Q5=A): 预平衡后 pH 接近观测 (Δ<0.3)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    eq_state = e.pre_equilibrate(state, profile, max_steps=100)
    assert abs(eq_state.ph - profile.ph) < 0.3, \
        f"pH 未锚定: 观测={profile.ph}, 稳态={eq_state.ph:.3f}"


def test_pre_equilibrate_anchors_exchange(profile, soil_info):
    """观测锚定 (grilling Q5=A): 预平衡后盐基交换性离子接近观测 (相对偏差<10%)

    config 输入的盐基交换离子观测值 (Ca/Mg/K/Na) 均应纳入判断。
    v0.6.1 (spec 62 Q7): AlX3 因 HX 酸库占位排挤不再锚定 (物理真实, 记录于诊断)。
    """
    from src.initial_condition import InitialConditionBuilder
    b = InitialConditionBuilder(profile, None, pCO2=0.015)
    targets = b.build_exchange()   # 观测交换离子 → mol (与 build_exchange 换算一致)

    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    eq_state = e.pre_equilibrate(state, profile, max_steps=100)
    for ion in ('CaX2', 'MgX2', 'KX', 'NaX'):
        target = targets.get(ion, 0.0)
        if target == 0.0:
            continue
        rel = abs(eq_state.exchange.get(ion, 0.0) - target) / target
        assert rel < 0.10, f"{ion}: 未锚定 (观测={target:.0f}, 稳态={eq_state.exchange.get(ion,0):.0f}, 偏差={rel:.1%})"


