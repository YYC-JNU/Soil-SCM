"""v0.7.x 工单80: 盐基淋失强化 (base_leaching) 测试

/grilling Q1~Q10 定案 (2026-08-24):
  - Q1=A: E_base 伴随通道泛化 (离开本层全部水的溶液盐基当量 → 下一场平衡前
    注入等当量 An⁻ 拽交换盐基, Gapon 自洽)
  - Q4=A: 水量基准 = drains + lateral + baseflow (与 NO₃⁻ 池同构)
  - Q5=A: BS<bs_low 时 E_base 归零 (zero, 不注酸 — 酸化职责保留给硝化/companion)
  - Q6=A: 复用保守 An⁻
  - Q8=A: 新节点 simulation.base_leaching.{enable, anion, bs_high, bs_low}
"""

import re

import pytest

from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction


FORCING = {"precip": 100.0, "temp": 25.0, "pCO2": 0.015}
EVENT_FORCING = dict(FORCING)


def _engine(**kw):
    return PhreeqcEngine(database="phreeqc.dat", mode="phreeqc", **kw)


def _base_engine(**kw):
    from src.config_manager import BaseLeachingConfig
    kw.setdefault("base_leaching_cfg", BaseLeachingConfig(enable=True))
    return _engine(**kw)


def _anion_injections(inp, comment="# 盐基淋失伴随"):
    """提取指定注释行的 An- 注入总量 (mol)"""
    vals = [float(m) for m in re.findall(
        rf"An-\s+([\d.eE+-]+)\s+{re.escape(comment)}", inp)]
    return sum(vals)


# ==================== 配置 ====================

def test_base_leaching_config_parse(tmp_path):
    """v0.7.x (工单80): YAML simulation.base_leaching 解析"""
    from src.config_manager import ConfigManager
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  base_leaching:\n"
        "    enable: false\n    anion: Z\n    bs_high: 40.0\n"
        "    bs_low: 5.0\n", encoding="utf-8")
    cfg = ConfigManager(str(p)).config.simulation.base_leaching
    assert cfg.enable is False
    assert cfg.anion == "Z"
    assert cfg.bs_high == pytest.approx(40.0)
    assert cfg.bs_low == pytest.approx(5.0)


def test_base_leaching_validation_raises(tmp_path):
    """v0.7.x (工单80): bs 阈值校验 (0 < bs_low < bs_high ≤ 100)"""
    from src.config_manager import ConfigManager
    p = tmp_path / "cfg.yaml"
    p.write_text(
        "simulation:\n  n_years: 2\n  base_leaching:\n"
        "    enable: true\n    bs_high: 5.0\n    bs_low: 10.0\n",
        encoding="utf-8")
    with pytest.raises(ValueError):
        ConfigManager(str(p))


def test_engine_base_leaching_disabled_without_cfg(profile, soil_info):
    """v0.7.x (工单80): 引擎构造不传 → base_leaching 禁用 (回归护栏, 同 companion)"""
    e = _engine()
    assert e.base_leaching_enabled is False


def test_engine_base_leaching_enabled_and_anion(profile, soil_info):
    """v0.7.x (工单80): 传入 cfg → 启用; pair_anion 取 base_leaching.anion"""
    from src.config_manager import BaseLeachingConfig
    e = _engine(base_leaching_cfg=BaseLeachingConfig(enable=True, anion="Z"))
    assert e.base_leaching_enabled is True
    assert e.pair_anion == "Z"


# ==================== 纯函数 ====================

def test_solution_base_eq():
    """溶液盐基当量: 2×Ca + 2×Mg + K + Na (eq, 乘体积)"""
    from src.phreeqc_engine import solution_base_eq
    sol = {"Ca": 0.001, "Mg": 0.0005, "K": 0.0002, "Na": 0.0001,
           "Al": 0.01, "Cl": 0.05}
    assert solution_base_eq(sol, 1000.0) == pytest.approx(
        1000.0 * (2 * 0.001 + 2 * 0.0005 + 0.0002 + 0.0001))
    # 空溶液 → 0
    assert solution_base_eq({}, 1000.0) == 0.0
    # Al 为酸性盐基, 不计入


def test_calc_base_leaching_invariant():
    """E_base 淋失不变量: 0 ≤ lost ≤ pool (同 calc_no3_leaching 哲学)"""
    from src.phreeqc_engine import calc_base_leaching
    # 无出水 → 0
    assert calc_base_leaching(100.0, 0.0, 1000.0) == 0.0
    # 比例淋失
    assert calc_base_leaching(100.0, 500.0, 1000.0) == pytest.approx(50.0)
    # Q ≫ V → 最多带走全部 (pool ≥ 0)
    assert calc_base_leaching(100.0, 1.0e6, 1000.0) == pytest.approx(100.0)
    # pool ≤ 0 → 0
    assert calc_base_leaching(0.0, 1000.0, 1000.0) == 0.0
    assert calc_base_leaching(-5.0, 1000.0, 1000.0) == 0.0


def test_grade_base_leaching_three_states(profile, soil_info):
    """BS 分级三态: inert 全量 / hybrid 线性衰减 / zero 归零 (不注酸!)"""
    from src.config_manager import BaseLeachingConfig
    e = _engine(base_leaching_cfg=BaseLeachingConfig(
        enable=True, bs_high=30.0, bs_low=10.0))
    # BS ≥ bs_high → inert 全量
    anion, mode = e._grade_base_leaching(100.0, 30.0)
    assert mode == 'inert' and anion == pytest.approx(100.0)
    anion, mode = e._grade_base_leaching(100.0, 55.0)
    assert mode == 'inert' and anion == pytest.approx(100.0)
    # bs_low ≤ BS < bs_high → hybrid 线性衰减
    anion, mode = e._grade_base_leaching(100.0, 20.0)
    assert mode == 'hybrid'
    assert anion == pytest.approx(100.0 * (20.0 - 10.0) / (30.0 - 10.0))
    # BS < bs_low → zero 归零, 且绝不注入 H+ (酸化职责不在本通道)
    anion, mode = e._grade_base_leaching(100.0, 9.9)
    assert mode == 'zero' and anion == 0.0
    anion, mode = e._grade_base_leaching(50.0, 0.0)
    assert mode == 'zero' and anion == 0.0


# ==================== An- 定义解耦 ====================

def test_anion_defined_with_only_base_leaching(profile, soil_info):
    """companion off + charge_pairing off + base_leaching on → An- 物种定义仍在"""
    e = _base_engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "SOLUTION_MASTER_SPECIES" in inp
    assert "An-" in inp
    # SELECTED_OUTPUT totals 含 An
    assert "-totals Ca Mg K Na Al P Zn Cl C S N Si F An" in inp


def test_base_anion_eq_injection_in_input(profile, soil_info):
    """forcing base_anion_eq → REACTION 注入 `An- x  # 盐基淋失伴随`"""
    e = _base_engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    forcing = dict(FORCING, base_anion_eq=123.0)
    inp = e._build_phreeqc_input(state, forcing, MonthlyAction(), profile)
    assert "# 盐基淋失伴随" in inp
    assert _anion_injections(inp) == pytest.approx(123.0)
    # 无 base_anion_eq → 不注入 (既有注释不混入)
    inp2 = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert _anion_injections(inp2) == 0.0


# ==================== 事件循环记账 + PHREEQC 实测 ====================

def test_base_leaching_event_accounting(profile, soil_info):
    """事件级: 一场排水携带盐基 → base_loss/base_mode/e_base 记账列存在且合理

    PHREEQC 实测: base_leaching on 时 2 场事件序列 (第一场 drains 带走盐基 →
    第二场注入 An⁻), 平衡正常完成、交换相盐基 ≥0。
    """
    e = _base_engine()
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(2)]
    ev1 = {'inflows': [1.0e5, 0.0], 'drains': [1.0e5, 0.0],
           'lateral': [1.0e4, 0.0], 'baseflow': [0.0, 0.0],
           'bypass_water_L': 0.0, 'precip_mm': 50.0, 'theta': [0.40, 0.40]}
    ev2 = {'inflows': [0.0, 0.0], 'drains': [0.0, 0.0],
           'lateral': [0.0, 0.0], 'baseflow': [0.0, 0.0],
           'bypass_water_L': 0.0, 'precip_mm': 0.0, 'theta': [0.40, 0.40]}
    hydrology = {'events': [ev1, ev2], 'aet_mm': 0.0, 'et_deficit_mm': 0.0}
    new_states, _ = e.run_monthly_multi_layer(
        states, dict(EVENT_FORCING, precip=50.0), MonthlyAction(),
        profile, hydrology=hydrology)
    details = hydrology['event_details']
    assert len(details) == 2
    # 记账列存在
    for key in ('base_loss_eq_L1', 'base_mode_L1', 'e_base_anion_eq_L1',
                'base_loss_eq_L2', 'base_mode_L2', 'e_base_anion_eq_L2'):
        assert key in details[0], key
    # 第一场无上一场注入 → e_base=0, mode=none (本场淋失 base_loss>0)
    assert details[0]['e_base_anion_eq_L1'] == 0.0
    assert details[0]['base_mode_L1'] == 'none'
    assert details[0]['base_loss_eq_L1'] >= 0.0
    # 第二场注入第一场 E_base (BS 高 → inert 或 hybrid; 不为 zero 除非 BS<low)
    assert details[1]['e_base_anion_eq_L1'] >= 0.0
    assert details[1]['base_mode_L1'] in ('inert', 'hybrid', 'zero')
    if details[1]['base_mode_L1'] == 'inert':
        assert details[1]['e_base_anion_eq_L1'] == pytest.approx(
            details[0]['base_loss_eq_L1'], rel=1e-6)
    # 交换相盐基 ≥0 (不变量); 平衡正常
    ex = new_states[0].exchange
    base_after = (ex.get('CaX2', 0.0) * 2 + ex.get('MgX2', 0.0) * 2
                  + ex.get('KX', 0.0) + ex.get('NaX', 0.0))
    assert base_after >= 0.0
    assert new_states[0].ph > 0.0


def test_base_leaching_reduces_solution_base(profile, soil_info):
    """PHREEQC 实测: base_leaching on 的溶液盐基当量随排水减少 (对照 off)"""
    from src.config_manager import BaseLeachingConfig
    from src.phreeqc_engine import solution_base_eq

    def run(engine_cfg):
        e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                          **engine_cfg)
        states = [e.build_initial_state(profile, soil_info, 0.015)
                  for _ in range(2)]
        ev = {'inflows': [1.0e5, 0.0], 'drains': [1.0e5, 0.0],
              'lateral': [1.0e4, 0.0], 'baseflow': [0.0, 0.0],
              'bypass_water_L': 0.0, 'precip_mm': 50.0, 'theta': [0.40, 0.40]}
        hydrology = {'events': [ev], 'aet_mm': 0.0, 'et_deficit_mm': 0.0}
        new_states, _ = e.run_monthly_multi_layer(
            states, dict(EVENT_FORCING, precip=50.0), MonthlyAction(),
            profile, hydrology=hydrology)
        return new_states[0]

    off = run({})                       # base_leaching 禁用
    on = run({'base_leaching_cfg': BaseLeachingConfig(enable=True)})
    # 同初始状态 → on 的溶液盐基当量应 ≤ off (An- 拽走更多盐基进排水/交换补偿)
    eq_on = solution_base_eq(on.solution, on.volume)
    eq_off = solution_base_eq(off.solution, off.volume)
    assert eq_on <= eq_off + 1e-9


def test_base_leaching_disabled_fallback(profile, soil_info):
    """base_leaching 关闭 → 事件记账列恒 0 (完全回退 v0.7.0 行为)"""
    e = _engine()  # 不传 cfg → 禁用
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(2)]
    ev = {'inflows': [1.0e5, 0.0], 'drains': [1.0e5, 0.0],
          'lateral': [1.0e4, 0.0], 'baseflow': [0.0, 0.0],
          'bypass_water_L': 0.0, 'precip_mm': 50.0, 'theta': [0.40, 0.40]}
    hydrology = {'events': [ev], 'aet_mm': 0.0, 'et_deficit_mm': 0.0}
    new_states, _ = e.run_monthly_multi_layer(
        states, dict(EVENT_FORCING, precip=50.0), MonthlyAction(),
        profile, hydrology=hydrology)
    row0 = hydrology['event_details'][0]
    assert row0['base_loss_eq_L1'] == 0.0
    assert row0['base_mode_L1'] == 'none'
    assert row0['e_base_anion_eq_L1'] == 0.0
