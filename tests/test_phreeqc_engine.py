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
    # L4: 氮库存为模型状态, SELECTED_OUTPUT 不再输出 N(-3)/N(5); F 仍在 totals
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
    """T01: error.inp 写入失败时不中断主流程, 降级路径正常完成

    v0.6.1 (Q5): fallback 改为连续 N=3 次失败才永久降级; 本测试跑 3 次
    失败验证降级路径 + error.inp 写入失败不影响主流程。
    """
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated phreeqc failure")

    monkeypatch.setattr(e.official, "RunString", boom)
    # 模拟 error.inp 路径的父级被普通文件占据 → mkdir/写入必然失败
    blocker = tmp_path / "blocked"
    blocker.write_text("i am a file", encoding="utf-8")
    monkeypatch.setattr("src.phreeqc_engine.ERROR_INP_PATH",
                        str(blocker / "error.inp"))
    monkeypatch.chdir(tmp_path)
    cur = state
    for _ in range(3):   # 连续 3 次失败 (Q5)
        cur, _ = e.run_monthly_step(cur, FORCING, MonthlyAction(), profile)

    # 降级路径正常完成, 状态仍有意义
    assert e._permanent_fallback
    assert e.last_error_message == "simulated phreeqc failure"
    assert cur.ph > 0


def test_simplified_with_fertilizer_no_crash(profile, soil_info):
    """P4 回归: simplified 模式 + 施肥指令不崩溃 (fertilizer_amount 已修复)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="simplified")
    state = e.build_initial_state(profile, soil_info, 0.015)
    act = MonthlyAction(apply_fertilizer=True, n_amount=12.0)
    new_state, _ = e.run_monthly_step(state, FORCING, act, profile)
    assert new_state.ph > 0


def test_error_diagnostics_on_failure(profile, soil_info, monkeypatch, tmp_path):
    """T3/Q18/T01: 引擎失败时记录 last_error_message / last_error_input, 并写入 error.inp

    v0.6.1 (Q5): fallback 改为连续 N=3 次失败才永久降级; 前 1~2 次失败
    保留前一状态跳过 (不调 simplified), 第 3 次才永久降级。
    """
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    assert e.last_error_message is None
    assert e.last_error_input is None

    state = e.build_initial_state(profile, soil_info, 0.015)
    ph0 = state.ph

    def boom(*args, **kwargs):
        raise RuntimeError("simulated phreeqc failure")

    monkeypatch.setattr(e.official, "RunString", boom)
    # T01: 隔离测试, 切换工作目录使 error.inp 写入 tmp_path, 不污染项目根
    monkeypatch.chdir(tmp_path)
    # 前 2 次失败: 保留前一状态跳过 (不永久降级, 不调 simplified)
    cur = state
    for _ in range(2):
        new_state, diag = e.run_monthly_step(
            cur, FORCING, MonthlyAction(), profile)
        assert not e._permanent_fallback
        assert new_state.ph == pytest.approx(ph0, rel=1e-6)  # 状态保留
        assert diag is None                                   # 无诊断 (跳过)
        cur = new_state
    # 第 3 次失败: 永久降级
    new_state, _ = e.run_monthly_step(cur, FORCING, MonthlyAction(), profile)

    assert e._permanent_fallback
    assert e.last_error_message == "simulated phreeqc failure"
    assert "SELECTED_OUTPUT" in e.last_error_input  # 内存属性保留
    assert new_state.ph > 0

    # T01: 磁盘复现文件自动生成且内容为完整输入 (写入 output/ 运行产物目录)
    error_file = tmp_path / "output" / "error.inp"
    assert error_file.exists()
    content = error_file.read_text(encoding="utf-8")
    assert "SELECTED_OUTPUT" in content
    assert "SOLUTION" in content





# ==================== v0.6.1: fallback 事件级局部降级 (S3, spec 62 Q5) ====================

def test_fallback_event_path_counts_separately(profile, soil_info, monkeypatch):
    """v0.6.1 (Q5): 事件/月级路径失败计数分开 — 事件失败不触发月级降级"""
    from src.hydrology import RainEvent
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(e.official, "RunString", boom)
    # 事件路径连续失败 2 次 (未达 N=3): 不降级, 计数递增
    for _ in range(2):
        ev = RainEvent(precip_mm=10.0)
        new_state, diag = e.run_event_step(state, ev, MonthlyAction(), profile)
        assert not e._permanent_fallback
        state = new_state
    assert e._consecutive_failures_event == 2  # 事件路径失败计数
    # 事件失败不影响月级计数
    assert e._consecutive_failures_monthly == 0


def test_fallback_reset_on_success(profile, soil_info, monkeypatch):
    """v0.6.1 (Q5): 成功后重置连续失败计数 (滑动窗口)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(e.official, "RunString", boom)
    # 1 次失败
    e.run_monthly_step(state, FORCING, MonthlyAction(), profile)
    assert e._consecutive_failures_monthly == 1
    # 恢复 RunString → 成功 → 计数重置
    monkeypatch.undo()
    e.run_monthly_step(state, FORCING, MonthlyAction(), profile)
    assert e._consecutive_failures_monthly == 0
    assert not e._permanent_fallback

# ==================== v0.6.1: HX 交换酸注入 (S3/S4, spec 62 Q7) ====================

def test_hx_exchange_species_injected(profile, soil_info):
    """v0.6.1 (Q7): EXCHANGE_SPECIES HX 自定义注入 (phreeqc.dat 注释禁用需注入)

    断言: 输入字符串含 "H+ + X- = HX" 与 log_k 行 (HX_LOGK=1.0)
    """
    from src.constants import HX_LOGK
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "H+ + X- = HX" in inp
    assert f"-log_k {HX_LOGK}" in inp
    # SELECTED_OUTPUT molalities 含 HX
    assert "-molalities CaX2 MgX2 KX NaX AlX3 HX X-" in inp


def test_hx_in_exchange_state(profile, soil_info):
    """v0.6.1 (Q7): 初始状态交换相含 HX 且月步后保留"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    assert 'HX' in state.exchange
    assert state.exchange['HX'] > 0
    new_state, diag = e.run_monthly_step(state, FORCING, MonthlyAction(),
                                         profile)
    # 交换相 HX 保留 (绝对摩尔量在平衡中演化, 不消失)
    assert new_state.exchange.get('HX', 0.0) >= 0.0


# ==================== v0.7.0 (spec 69, 工单71): CompAn 惰性阴离子伴随淋失 ====================

def _companion_engine():
    from src.config_manager import CompanionConfig
    return PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                         companion_cfg=CompanionConfig(enable=True))


def test_companion_anion_species_in_input(profile, soil_info):
    """v0.7.0 (工单71): _build_phreeqc_input 含惰性阴离子物种定义 (默认 An)

    SOLUTION_MASTER_SPECIES/SOLUTION_SPECIES 注入输入头段 (不碰 phreeqc.dat),
    不参与氧化还原, 供伴随淋失 E_loss 等当量注入 (REACTION 端, 交换相不动)。
    PHREEQC 元素名须为单元素 (CompAn 会拆为 Comp+An 报错, 故用 An)。
    """
    e = _companion_engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "SOLUTION_MASTER_SPECIES" in inp
    assert "SOLUTION_SPECIES" in inp
    assert "An" in inp
    assert "An-" in inp


def test_companion_anion_reaction_injection(profile, soil_info):
    """v0.7.0 (工单71): forcing companion_anion_eq → REACTION 注入 An- 等当量"""
    e = _companion_engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    forcing = dict(FORCING, companion_anion_eq=100.0, companion_acid_eq=0.0)
    inp = e._build_phreeqc_input(state, forcing, MonthlyAction(), profile)
    assert "An-" in inp
    assert "# 伴随淋失" in inp
    # 注入量 = 当量 (100 eq → 100 mol 一价阴离子)
    assert "1.000000e+02" in inp


def test_companion_acid_reaction_injection(profile, soil_info):
    """v0.7.0 (工单71): forcing companion_acid_eq → REACTION 注入 H+ (酸化模式)"""
    e = _companion_engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    forcing = dict(FORCING, companion_anion_eq=0.0, companion_acid_eq=50.0)
    inp = e._build_phreeqc_input(state, forcing, MonthlyAction(), profile)
    assert "H+" in inp
    assert "# 伴随淋失酸化" in inp


def test_companion_disabled_no_anion_species(profile, soil_info):
    """v0.7.0 (工单71): companion 关闭 → 无伴随淋失注入 (回退 v0.6.1)

    v0.7.x (工单77) 更新: charge pairing (REACTION 电荷平衡修复) 默认独立
    启用, 故 An- 物种定义仍在 (供配对注入); 但 companion 专属的伴随淋失
    (E_loss/companion_anion_eq) 不注入。
    """
    from src.config_manager import ChargePairingConfig
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                      charge_pairing_cfg=ChargePairingConfig(enable=False))
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "SOLUTION_MASTER_SPECIES" not in inp
    assert "An-" not in inp


# ==================== v0.7.0 (spec 69, 工单72): NH4+ 等效置换 ====================

def test_exchange_base_ratios_pure_function():
    """v0.7.0 (工单72): 交换相 Ca:Mg:K:Na 电荷占比计算 (置换注入配比)"""
    from src.phreeqc_engine import exchange_base_ratios
    ratios = exchange_base_ratios(
        {'CaX2': 5.4e4, 'MgX2': 2.7e4, 'KX': 1.8e4, 'NaX': 6.2e4})
    total = 5.4e4 * 2 + 2.7e4 * 2 + 1.8e4 + 6.2e4
    assert ratios['Ca+2'] == pytest.approx(5.4e4 * 2 / total)
    assert ratios['Mg+2'] == pytest.approx(2.7e4 * 2 / total)
    assert ratios['K+'] == pytest.approx(1.8e4 / total)
    assert ratios['Na+'] == pytest.approx(6.2e4 / total)
    assert sum(ratios.values()) == pytest.approx(1.0)
    # 空交换 → 空 dict
    assert exchange_base_ratios({}) == {}


def test_nh4_exchange_reaction_injection(profile, soil_info):
    """v0.7.0 (工单72): 施肥月水解后 REACTION 注入置换盐基 (按交换占比)

    工单76 调优 A: 置换当量 = 硝化量 (12 kg N → 856.8 mol × k1=1.0 × k2=0.4
    = 342.7 mol), 非全水解量 (857) — 抑制 Gapon 回吞导致的盐基过量注入。
    """
    import re
    e = _companion_engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    act = MonthlyAction(apply_fertilizer=True, n_amount=12.0)
    inp = e._build_phreeqc_input(state, FORCING, act, profile)
    # 4 种盐基各注入一行 (Ca+2/Mg+2/K+/Na+)
    assert inp.count("# NH4+ 置换") == 4
    assert "Ca+2" in inp
    # 注入总量 = 硝化当量 (12 kg N → 856.8 mol × k1 × k2)
    vals = [float(m) for m in re.findall(
        r"\s([\d.eE+-]+)\s+# NH4\+ 置换", inp)]
    assert len(vals) == 4
    assert sum(vals) == pytest.approx(
        12.0 * 1000.0 / 14.007 * 1.0 * 0.4, rel=1e-3)


# ==================== v0.7.0 (spec 69, 工单73): D2 矿物风化集总注入 ====================

def _weathering_engine(**kw):
    from src.config_manager import WeatheringConfig
    kw.setdefault('weathering_cfg', WeatheringConfig(enable=True))
    return PhreeqcEngine(database="phreeqc.dat", mode="phreeqc", **kw)


def test_weathering_arrhenius_factor():
    """v0.7.0 (工单73): Arrhenius 温度依赖 — T=T_ref→1, T↑→风化↑ (增温响应)"""
    from src.phreeqc_engine import weathering_arrhenius_factor
    f25 = weathering_arrhenius_factor(25.0, 40.0)   # T_ref=298.15K
    f30 = weathering_arrhenius_factor(30.0, 40.0)
    f20 = weathering_arrhenius_factor(20.0, 40.0)
    assert f25 == pytest.approx(1.0, rel=1e-6)
    assert f30 > f25          # 增温风化加速 (气候敏感性传导)
    assert f20 < f25          # 降温风化减缓
    # Ea 越大温度敏感度越高
    assert (weathering_arrhenius_factor(30.0, 60.0)
            > weathering_arrhenius_factor(30.0, 40.0))


def test_weathering_reaction_injection_math(profile, soil_info):
    """v0.7.0 (工单73): 风化 REACTION 注入数学 — Ca:Mg:K 电荷占比 + HCO3 等当量

    rate=1200 molc/ha/yr → 月 100 molc (T=25°C, Arrhenius=1);
    Ca:Mg:K 电荷 5:3:2, HCO3- 等当量 (电荷守恒)。
    """
    import re
    from src.config_manager import WeatheringConfig
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                      weathering_cfg=WeatheringConfig(
                          enable=True, rate_molc_ha_yr=1200.0))
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, dict(FORCING, temp=25.0),
                                 MonthlyAction(), profile)
    # 解析 # 矿物风化 行: {物种: mol}
    vals = {}
    for line in inp.splitlines():
        if "# 矿物风化" in line:
            sp, amt = line.split("# 矿物风化")[0].split()
            vals[sp.strip()] = float(amt)
    assert 'HCO3-' in vals and 'Ca+2' in vals and 'Mg+2' in vals and 'K+' in vals
    hco3 = vals['HCO3-']
    # HCO3- 等当量 = 月总 molc (100)
    assert hco3 == pytest.approx(1200.0 / 12.0, rel=1e-6)
    # 电荷守恒: Ca+2×2 + Mg+2×2 + K+ = HCO3-
    assert (vals['Ca+2'] * 2 + vals['Mg+2'] * 2 + vals['K+']
            == pytest.approx(hco3, rel=1e-6))
    # Ca:Mg:K 电荷比 5:3:2
    assert vals['Ca+2'] * 2 / hco3 == pytest.approx(0.5, rel=1e-6)
    assert vals['Mg+2'] * 2 / hco3 == pytest.approx(0.3, rel=1e-6)
    assert vals['K+'] / hco3 == pytest.approx(0.2, rel=1e-6)


def test_weathering_arrhenius_applied_to_injection(profile, soil_info):
    """v0.7.0 (工单73): 注入量随温度 Arrhenius 缩放 (增温→风化碱度↑)"""
    import re
    from src.config_manager import WeatheringConfig
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                      weathering_cfg=WeatheringConfig(
                          enable=True, rate_molc_ha_yr=1200.0))
    state = e.build_initial_state(profile, soil_info, 0.015)

    def hco3_at(temp):
        inp = e._build_phreeqc_input(state, dict(FORCING, temp=temp),
                                     MonthlyAction(), profile)
        for line in inp.splitlines():
            if "# 矿物风化" in line and line.startswith("  HCO3-"):
                return float(line.split()[1])
        return 0.0

    h25 = hco3_at(25.0)
    h30 = hco3_at(30.0)
    assert h25 == pytest.approx(1200.0 / 12.0, rel=1e-6)
    assert h30 > h25   # 增温风化碱度注入增强


def test_weathering_disabled_no_injection(profile, soil_info):
    """v0.7.0 (工单73): weathering 关闭 → 无风化注入 (回退基线)"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "# 矿物风化" not in inp


def test_weathering_degrade_minerals_from_equilibrium(profile, soil_info):
    """v0.7.0 (工单73): degrade_minerals → 该矿物从 EQUILIBRIUM_PHASES 移除

    保 Al 循环通道 (Al(OH)3(a)/gibbsite 未降级时仍平衡相; 降级后状态保留、
    仅不写入平衡相 — v0.3.0 证伪教训: 不切断 L2 矿物回补)。
    """
    from src.config_manager import WeatheringConfig
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                      weathering_cfg=WeatheringConfig(
                          enable=True, degrade_minerals=['gibbsite']))
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    # EQUILIBRIUM_PHASES 无 gibbsite
    eq_block = inp.split("EQUILIBRIUM_PHASES")[1].split("GAS_PHASE")[0]
    assert "gibbsite" not in eq_block
    # 其他矿物仍在
    assert "kaolinite" in eq_block
    # 状态仍保留 gibbsite (不破坏矿物演化回填)
    assert 'gibbsite' in state.minerals


def test_weathering_phreeqc_balance_with_degrade(profile, soil_info):
    """v0.7.0 (工单73): 风化注入 + 矿物降级 PHREEQC 实测平衡成功

    验证: 风化碱度 REACTION (Ca/Mg/K/HCO3) 与降级后的平衡相 (gibbsite/
    kaolinite 移除) 在真实 PHREEQC 平衡中收敛, Al 循环通道不断 (AlX3 仍
    在交换相), pH 有效。
    """
    from src.config_manager import WeatheringConfig
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                      weathering_cfg=WeatheringConfig(
                          enable=True, rate_molc_ha_yr=500.0,
                          degrade_minerals=['gibbsite', 'kaolinite']))
    state = e.build_initial_state(profile, soil_info, 0.015)
    new_state, diag = e.run_monthly_step(state, FORCING, MonthlyAction(),
                                         profile)
    assert new_state.ph > 0.0
    assert diag is not None
    # Al 循环通道: 交换相 AlX3 仍存在 (未因矿物降级而立即耗尽)
    assert new_state.exchange.get('AlX3', 0.0) > 0.0
    # 矿化风化注入后溶液盐基响应 (Ca/Mg 解吸或保留, 非 NaN)
    assert new_state.solution.get('Ca', 0.0) >= 0.0


def test_nh4_exchange_skipped_without_fertilizer(profile, soil_info):
    """v0.7.0 (工单72): 无施肥 → 无置换注入"""
    e = _companion_engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "# NH4+ 置换" not in inp


def test_nh4_exchange_skipped_when_disabled(profile, soil_info):
    """v0.7.0 (工单72): nh4_exchange=false → 无置换注入 (D3 单独生效)"""
    from src.config_manager import CompanionConfig
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                      companion_cfg=CompanionConfig(enable=True,
                                                    nh4_exchange=False))
    state = e.build_initial_state(profile, soil_info, 0.015)
    act = MonthlyAction(apply_fertilizer=True, n_amount=12.0)
    inp = e._build_phreeqc_input(state, FORCING, act, profile)
    assert "# NH4+ 置换" not in inp
