"""v0.7.x 工单77: REACTION 电荷平衡修复 (charge pairing) 测试

科学发现 (2026-08-21 探针实测):
  - PHREEQC REACTION 注入裸阳离子 (NH4+ 置换 Ca+2/钾肥 K+/镁肥 Mg+2)
    → 电荷平衡迫使产生 OH- → 伪碱化 (Ca+2 343 → pH 9.28, 复现 v0.7.0
    fertilizer 8~11)
  - 裸 H+ 注入 (硝化产酸/companion acid) → 不酸化 (H 以非 H+ 形态存在)
  - 电荷配对注入 (H+ + An- / Ca+2 + 2An-) → pH 正常响应
  修复: 所有净电荷注入按等当量伴随保守惰性阴离子 An- (复用 companion
  inert_anion 机制; SOLUTION_MASTER_SPECIES 自定义, 不碰 phreeqc.dat;
  随排水淋失不积累)。
"""

import re

import pytest

from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction


FORCING = {"precip": 100.0, "temp": 25.0, "pCO2": 0.015}


def _engine(**kw):
    return PhreeqcEngine(database="phreeqc.dat", mode="phreeqc", **kw)


def _pair_engine(**kw):
    from src.config_manager import ChargePairingConfig
    kw.setdefault("charge_pairing_cfg", ChargePairingConfig(enable=True))
    return _engine(**kw)


def _pair_anion_amounts(inp):
    """提取 # 电荷配对 行的 An- 注入总量 (mol)"""
    vals = [float(m) for m in re.findall(
        r"An-\s+([\d.eE+-]+)\s+# 电荷配对", inp)]
    return sum(vals)


# ==================== 配置 ====================

def test_charge_pairing_default_enabled():
    """v0.7.x (工单77): 引擎默认启用 charge pairing (None → 默认配置)"""
    e = _engine()
    assert e.charge_pairing_enabled is True
    assert e.pair_anion == "An"


def test_charge_pairing_config_parse(tmp_path):
    """v0.7.x (工单77): YAML simulation.charge_pairing 解析"""
    from src.config_manager import ConfigManager
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  charge_pairing:\n"
        "    enable: false\n    anion: Cp\n", encoding="utf-8")
    cfg = ConfigManager(str(p)).config.simulation.charge_pairing
    assert cfg.enable is False
    assert cfg.anion == "Cp"


def test_charge_pairing_anion_species_defined_without_companion(
        profile, soil_info):
    """companion 关闭 + pairing 启用 → An- 物种定义仍在 (解耦)"""
    e = _pair_engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "SOLUTION_MASTER_SPECIES" in inp
    assert "An-" in inp


def test_nh4_exchange_salts_paired_by_charge(profile, soil_info):
    """NH4+ 置换盐基: An- 注入量 = Σ(价×mol) (Ca+2×2 + Mg+2×2 + K+×1 + Na+×1)"""
    from src.config_manager import CompanionConfig, ChargePairingConfig
    e = _engine(companion_cfg=CompanionConfig(enable=True),
                charge_pairing_cfg=ChargePairingConfig(enable=True))
    state = e.build_initial_state(profile, soil_info, 0.015)
    act = MonthlyAction(apply_fertilizer=True, n_amount=12.0)
    inp = e._build_phreeqc_input(state, FORCING, act, profile)
    assert inp.count("# NH4+ 置换") == 4
    # 提取各盐基摩尔量 (Ca+2/Mg+2 二价, K+/Na+ 一价)
    salt_mol = {}
    for sp, charge in (("Ca+2", 2), ("Mg+2", 2), ("K+", 1), ("Na+", 1)):
        m = re.findall(rf"\s{re.escape(sp)}\s+([\d.eE+-]+)\s+# NH4\+ 置换",
                       inp)
        assert len(m) == 1, sp
        salt_mol[sp] = float(m[0])
    expected_charge = sum(salt_mol[sp] * charge
                          for sp, charge in (("Ca+2", 2), ("Mg+2", 2),
                                             ("K+", 1), ("Na+", 1)))
    # NH4+ 置换块起点的 # 电荷配对 行 (排除硝化产酸等前序配对口)
    after = inp[inp.find("# NH4+ 置换"):]
    paired = [float(m) for m in re.findall(
        r"An-\s+([\d.eE+-]+)", after)]
    assert sum(paired) == pytest.approx(expected_charge, rel=1e-3)


def test_companion_acid_paired(profile, soil_info):
    """companion_acid_eq: H+ x + An- x 配对"""
    e = _pair_engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    forcing = dict(FORCING, companion_anion_eq=0.0, companion_acid_eq=50.0)
    inp = e._build_phreeqc_input(state, forcing, MonthlyAction(), profile)
    assert "# 伴随淋失酸化" in inp
    h_mol = [float(m) for m in re.findall(
        r"\sH\+\s+([\d.eE+-]+)\s+# 伴随淋失酸化", inp)]
    assert len(h_mol) == 1
    assert _pair_anion_amounts(inp) == pytest.approx(h_mol[0], rel=1e-3)


def test_fertilizer_k_mg_paired(profile, soil_info):
    """钾肥 K+ x + An- x; 镁肥 Mg+2 x + An- 2x (电中性盐)"""
    e = _pair_engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    act = MonthlyAction(apply_fertilizer=True, n_amount=0.0,
                        k2o_amount=9.0, mgo_amount=3.0)
    inp = e._build_phreeqc_input(state, FORCING, act, profile)
    # 钾肥: 9 kg K2O → 2×1000/94.2 mol K+; 镁肥: 3 kg MgO → 1000/40.3 mol Mg+2
    k_mol = 9.0 * 1000.0 / 94.20 * 2.0
    mg_mol = 3.0 * 1000.0 / 40.30
    expected = k_mol + 2.0 * mg_mol
    assert _pair_anion_amounts(inp) == pytest.approx(expected, rel=1e-3)


def test_pairing_disabled_fallback_bare_injection(profile, soil_info):
    """charge_pairing 关闭 → 回退裸注入 (对照/兼容模式)"""
    from src.config_manager import ChargePairingConfig
    e = _engine(charge_pairing_cfg=ChargePairingConfig(enable=False))
    state = e.build_initial_state(profile, soil_info, 0.015)
    act = MonthlyAction(apply_fertilizer=True, n_amount=12.0)
    inp = e._build_phreeqc_input(state, FORCING, act, profile)
    assert "# 硝化产酸" in inp
    assert _pair_anion_amounts(inp) == 0.0


# ==================== PHREEQC 实测 (电荷平衡物理) ====================

def test_phreeqc_paired_acid_actually_acidifies(profile, soil_info):
    """PHREEQC 实测: 配对抗酸 (H+ + An-) pH 下降; 裸 H+ 不酸化"""
    from src.config_manager import ChargePairingConfig
    # 配对: companion_acid_eq 500 → H+ + An- → pH 显著低于 5.0
    # v0.7.x (工单78): 先预平衡 (真实流程; 模拟步 tolerance=1e-9 需近平衡起点)
    e = _pair_engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    state = e.pre_equilibrate(state, profile, max_steps=30)
    forcing = dict(FORCING, precip=0.0,
                   companion_anion_eq=0.0, companion_acid_eq=500.0)
    ns, _ = e.run_monthly_step(state, forcing, MonthlyAction(), profile)
    assert ns.ph < 5.0
    # 对照: 关闭 pairing 的裸 H+ (companion acid 裸注入) → 不酸化/酸化弱
    e_bare = _engine(charge_pairing_cfg=ChargePairingConfig(enable=False))
    state_b = e_bare.build_initial_state(profile, soil_info, 0.015)
    state_b = e_bare.pre_equilibrate(state_b, profile, max_steps=30)
    ns_b, _ = e_bare.run_monthly_step(state_b, forcing,
                                      MonthlyAction(), profile)
    assert ns_b.ph >= ns.ph  # 裸注入 pH 不低 (酸化弱于配对或持平)


def test_phreeqc_paired_salt_does_not_alkalinize(profile, soil_info):
    """PHREEQC 实测: 配对施肥月 (含盐基+An-) 不伪碱化到 8+"""
    e = _pair_engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    act = MonthlyAction(apply_fertilizer=True, n_amount=12.0)
    ns, _ = e.run_monthly_step(state, FORCING, act, profile)
    assert ns.ph < 8.0, f"配对注入不应碱化, 实测 pH={ns.ph}"

