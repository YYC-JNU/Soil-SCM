"""v0.7.13 (工单99·B2′ / 工单98·W4 改写): **表层物理化 —— 石灰/施肥仅注入 L1**

背景（dev 只读归因, `dev-notes/W4_LAYER_GATING_ROOTCAUSE.md`）：
`_run_multi_layer_events` 把**同一个** `MonthlyAction` 传给每一层的
`run_event_step`，而 `build_phreeqc_input` 对 `apply_lime`/`apply_fertilizer`
**无 layer 门控** ⇒ 石灰/施肥实际注入全部 4 层 = **4× 剂量 + 直施深层**
⇒ 深层溶液 Ca → 0.5 mol/L（盐水态）→ Q6 浓度钳制 → `E_base` 腔回路
→ L4 交换相一年内翻转、pH 崩到 ~2.1（D7）。
对照：`surface_acid_eq`（phreeqc_engine:1064, `i == 0`）与 `skip_nitrification`
（:1060, `i > 0`）**均已有显式层门控** ⇒ 石灰/施肥属**漏加门控**。

修复口径：**表面撒施干预仅作用于表层 L1**（USERGUIDE §4.4）；
`simulation.amendments_surface_only: false` = 旧行为（A/B 单参数对照）。

判据（预登记）：见 `issues/99-*.md §6.1.9` / `issues/98-*.md §6.2`。
"""

import pytest

from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction, surface_scoped

FORCING = {"precip": 100.0, "temp": 25.0, "pCO2": 0.015}


def _amendment_action():
    return MonthlyAction(apply_fertilizer=True, n_amount=12.0, p2o5_amount=4.0,
                         k2o_amount=9.0, mgo_amount=3.0, znso4_amount=1.0,
                         apply_lime=True, lime_amount=45.0)


# ==================== 纯函数 ====================

def test_surface_scoped_returns_copy_with_amendments_cleared():
    """深层 action = 新对象 + 石灰/施肥全关 + 施肥量清零"""
    act = _amendment_action()
    scoped = surface_scoped(act)
    assert scoped is not act
    assert scoped.apply_lime is False
    assert scoped.lime_amount == pytest.approx(0.0)
    assert scoped.apply_fertilizer is False
    for f in ("n_amount", "p2o5_amount", "k2o_amount", "mgo_amount",
              "znso4_amount"):
        assert getattr(scoped, f) == pytest.approx(0.0), f


def test_surface_scoped_does_not_mutate_original():
    """绝不就地改共享 action（否则会污染后续月份/情景）"""
    act = _amendment_action()
    surface_scoped(act)
    assert act.apply_lime is True and act.lime_amount == pytest.approx(45.0)
    assert act.apply_fertilizer is True and act.n_amount == pytest.approx(12.0)


def test_surface_scoped_none_passthrough():
    assert surface_scoped(None) is None


# ==================== 输入串（官方路径）====================

def test_deep_layer_input_has_no_lime_or_fertilizer_lines(profile, soil_info):
    """字符串级: 表层化 action 在任意 layer_index 下都**不**产出注入行"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    st = e.build_initial_state(profile, soil_info, 0.015)
    act = surface_scoped(_amendment_action())
    for li in (0, 1, 2, 3):
        inp = e._build_phreeqc_input(
            st, dict(FORCING, precip=5.0), act, profile,
            layer_index=li, n_layers=4)
        assert "生石灰Ca2+" not in inp, f"layer_index={li} 仍注入石灰"
        assert "钾肥" not in inp and "镁肥" not in inp, f"layer_index={li} 仍注肥"


def test_surface_layer_input_has_lime_and_fertilizer_lines(profile, soil_info):
    """阳性对照: 未表层化 action 在 L1 仍正常注入（口径未被误伤）"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    st = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(
        st, dict(FORCING, precip=5.0), _amendment_action(), profile,
        layer_index=0, n_layers=4)
    assert "生石灰Ca2+" in inp
    assert "钾肥" in inp


# ==================== 引擎多层循环（集成）====================

def _hydrology_events(n=4):
    """最小事件水文 (与 tests/test_event_chemistry 同形)"""
    return {'events': [{
        'inflows': [0.0] * n, 'drains': [0.0] * n,
        'lateral': [0.0] * n, 'baseflow': [0.0] * n,
        'bypass_water_L': 0.0, 'precip_mm': 10.0,
        'theta': [0.40] * n,
    }]}


def _spy_layer_actions(engine, states, action, profile, hydrology, method):
    """记录每层收到的 (layer_index, lime, fert, lime_amount)"""
    seen = []
    orig = getattr(engine, method)

    def spy(state, second, act, *args, **kw):
        seen.append((kw.get("layer_index"),
                     bool(getattr(act, "apply_lime", False)),
                     bool(getattr(act, "apply_fertilizer", False)),
                     float(getattr(act, "lime_amount", 0.0) or 0.0)))
        return orig(state, second, act, *args, **kw)

    setattr(engine, method, spy)
    try:
        engine.run_monthly_multi_layer(states, FORCING, action, profile,
                                       hydrology=hydrology)
    finally:
        setattr(engine, method, orig)
    return seen


def _assert_surface_only(seen):
    """事件路径: 前 4 条 = 第 1 场事件 的 L1~L4"""
    assert len(seen) >= 4
    first = seen[:4]
    assert [s[0] for s in first] == [0, 1, 2, 3]
    assert first[0][1] is True and first[0][2] is True
    assert first[0][3] == pytest.approx(45.0)
    for li, lime, fert, amount in first[1:]:
        assert lime is False and fert is False, li
        assert amount == pytest.approx(0.0), li


def _assert_all_layers_injected(seen):
    for li, lime, fert, amount in seen[:4]:
        assert lime is True and fert is True, li
        assert amount == pytest.approx(45.0), li


def test_multilayer_event_path_amendments_only_reach_surface(profile,
                                                             soil_info):
    """默认 (amendments_surface_only=True) · 事件路径: 仅 L1 收到石灰/施肥"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="simplified")
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    seen = _spy_layer_actions(e, states, _amendment_action(), profile,
                              _hydrology_events(), "run_event_step")
    _assert_surface_only(seen)


def test_multilayer_event_path_legacy_mode_injects_all_layers(profile,
                                                             soil_info):
    """A/B 单参数 · 事件路径: amendments_surface_only=False → 旧「逐层注入」"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="simplified",
                      amendments_surface_only=False)
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    seen = _spy_layer_actions(e, states, _amendment_action(), profile,
                              _hydrology_events(), "run_event_step")
    _assert_all_layers_injected(seen)


def test_multilayer_month_path_amendments_only_reach_surface(profile,
                                                            soil_info):
    """默认 · 月级路径 (无 events): 仅 L1 收到石灰/施肥"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="simplified")
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    seen = _spy_layer_actions(e, states, _amendment_action(), profile,
                              None, "run_monthly_step")
    _assert_surface_only(seen)


def test_multilayer_month_path_legacy_mode_injects_all_layers(profile,
                                                             soil_info):
    """A/B 单参数 · 月级路径: amendments_surface_only=False → 旧「逐层注入」"""
    e = PhreeqcEngine(database="phreeqc.dat", mode="simplified",
                      amendments_surface_only=False)
    states = [e.build_initial_state(profile, soil_info, 0.015) for _ in range(4)]
    seen = _spy_layer_actions(e, states, _amendment_action(), profile,
                              None, "run_monthly_step")
    _assert_all_layers_injected(seen)


# ==================== 配置 ====================

def test_amendments_surface_only_config_default_true(tmp_path):
    """YAML 缺省 → True（修复后口径 = 表层化）"""
    from src.config_manager import ConfigManager
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n", encoding="utf-8")
    cfg = ConfigManager(str(p)).config.simulation
    assert cfg.amendments_surface_only is True


def test_amendments_surface_only_config_parse(tmp_path):
    """YAML 显式 false → 旧行为（A/B 对照）"""
    from src.config_manager import ConfigManager
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n"
                 "  amendments_surface_only: false\n", encoding="utf-8")
    cfg = ConfigManager(str(p)).config.simulation
    assert cfg.amendments_surface_only is False


def test_amendments_surface_only_validation_raises(tmp_path):
    """非布尔值 → 配置校验报错"""
    from src.config_manager import ConfigManager
    p = tmp_path / "cfg.yaml"
    p.write_text("simulation:\n  n_years: 2\n"
                 "  amendments_surface_only: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="amendments_surface_only"):
        ConfigManager(str(p))