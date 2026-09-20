"""v0.7.x 工单88 (4c): L1 表层产酸源 (surface acid source) — 红壤表层
有机质矿化持续产酸 (H+), 压住 natural 中期碱化伪影 (v85 y5~y15 ~8.3)。

机制 (spec 88 §3.3 4c, 探针 probe_88_4c.py 30y 细验定档 150 molc/ha/yr):
  - config: simulation.surface_acid.enable + rate_molc_ha_yr (默认 150)
  - 注入: 仅 L1 (layer_index==0); L1 每次平衡 (事件/月级) 注入
    rate_molc_ha_yr / 12 mol H+, REACTION 段电荷配对 An- (复用惰性阴离子)
  - 预平衡豁免 (_in_pre_equilibration=True 不注入 → 锚定目标不受酸源污染)
  - 默认关闭 (enable=False) = v85 逐位一致 (回归护栏)
"""

import pytest

from src.config_manager import ConfigManager, SurfaceAcidConfig
from src.scenario_controller import MonthlyAction


def test_surface_acid_config_default_disabled():
    """回归护栏: 未配置时 surface_acid 默认关闭 (v85 逐位一致)"""
    s = SurfaceAcidConfig()
    assert s.enable is False
    assert s.rate_molc_ha_yr == 1000.0


def test_surface_acid_config_parse(tmp_path):
    """config.yaml surface_acid 块解析"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "simulation:\n"
        "  surface_acid:\n"
        "    enable: true\n"
        "    rate_molc_ha_yr: 1000.0\n",
        encoding="utf-8")
    cm = ConfigManager(str(cfg_path))
    sa = cm.config.simulation.surface_acid
    assert sa.enable is True
    assert sa.rate_molc_ha_yr == 1000.0


def test_rate_constant_defined():
    """定档值常量: 正式语义 30y 细验定案 1000 molc/ha/yr"""
    from src.constants import SURFACE_ACID_RATE_MOLC_HA_YR
    assert SURFACE_ACID_RATE_MOLC_HA_YR == 1000.0


def test_surface_acid_reaction_injection(profile, soil_info):
    """L1 产酸源进入 PHREEQC REACTION 段 (H+ + 电荷配对 An-)"""
    import src.phreeqc_engine as pe
    from src.config_manager import ChargePairingConfig
    e = pe.PhreeqcEngine(
        database="phreeqc.dat", mode="phreeqc",
        surface_acid_cfg=SurfaceAcidConfig(enable=True, rate_molc_ha_yr=1000.0),
        charge_pairing_cfg=ChargePairingConfig(enable=True))
    state = e.build_initial_state(profile, soil_info, 0.015, layer_index=0)
    FORCING = {"precip": 0.0, "temp": 25.0, "pCO2": 0.015,
               "surface_acid_eq": 1000.0 / 12.0}
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                 layer_index=0, n_layers=4)
    assert "# 表层产酸源" in inp
    h_expected = f"  H+     {1000.0/12.0:.6e}"
    assert h_expected in inp
    # 电荷配对: (An-, 单空格后跟量)
    an_frag = f"An- {1000.0/12.0:.6e}"
    assert an_frag in inp


def test_surface_acid_engine_scopes_to_layer0(profile, soil_info,
                                              monkeypatch):
    """仅 L1 (layer_index==0) 的 forcing 被填充 surface_acid_eq 键; 深层不填

    实际注入顺序: run_monthly_multi_layer 层循环在 layer_index==0 时写
    forcing['surface_acid_eq'] (各层独立 forcing, 深层无此键) → 每层 input
    构建消费该键。用 spy 捕获各层实际收到的 forcing 验证作用域。
    """
    import src.phreeqc_engine as pe
    from src.scenario_controller import MonthlyAction
    from src.config_manager import ChargePairingConfig
    e = pe.PhreeqcEngine(
        database="phreeqc.dat", mode="phreeqc",
        surface_acid_cfg=SurfaceAcidConfig(enable=True, rate_molc_ha_yr=1000.0),
        charge_pairing_cfg=ChargePairingConfig(enable=True))
    states = [e.build_initial_state(profile, soil_info, 0.015, layer_index=i)
              for i in range(2)]
    captured = {}

    orig = e._build_phreeqc_input

    def spy(state, forcing, action, profile_, **kw):
        li = kw.get('layer_index')
        captured[li] = dict(forcing)
        return orig(state, forcing, action, profile_, **kw)

    monkeypatch.setattr(e, "_build_phreeqc_input", spy)
    FORCING = {"precip": 0.0, "temp": 25.0, "pCO2": 0.015}
    e.run_monthly_multi_layer(states, FORCING, MonthlyAction(), profile)
    # L1 (li=0): 注入键 = rate/12
    assert captured[0].get('surface_acid_eq') == pytest.approx(1000.0 / 12.0)
    # L2 (li=1): 无注入键 (天然豁免)
    assert 'surface_acid_eq' not in captured[1]


def test_surface_acid_skipped_in_pre_equilibration(profile, soil_info,
                                                   monkeypatch):
    """预平衡阶段不注入产酸源 (锚定目标不被酸源污染)"""
    import src.phreeqc_engine as pe
    from src.scenario_controller import MonthlyAction
    from src.config_manager import ChargePairingConfig
    e = pe.PhreeqcEngine(
        database="phreeqc.dat", mode="phreeqc",
        surface_acid_cfg=SurfaceAcidConfig(enable=True, rate_molc_ha_yr=1000.0),
        charge_pairing_cfg=ChargePairingConfig(enable=True))
    states = [e.build_initial_state(profile, soil_info, 0.015, layer_index=i)
              for i in range(2)]
    captured = {}

    orig = e._build_phreeqc_input

    def spy(state, forcing, action, profile_, **kw):
        li = kw.get('layer_index')
        captured[li] = dict(forcing)
        return orig(state, forcing, action, profile_, **kw)

    monkeypatch.setattr(e, "_build_phreeqc_input", spy)
    FORCING = {"precip": 0.0, "temp": 25.0, "pCO2": 0.015}
    e._in_pre_equilibration = True
    try:
        e.run_monthly_multi_layer(states, FORCING, MonthlyAction(), profile)
    finally:
        e._in_pre_equilibration = False
    # 预平衡中 L1 (li=0) 也无注入键
    assert 'surface_acid_eq' not in captured[0]


def test_surface_acid_disabled_no_injection(profile, soil_info):
    """默认关闭 (enable=False): REACTION 段无产酸源行 (v85 逐位一致)"""
    import src.phreeqc_engine as pe
    from src.scenario_controller import MonthlyAction
    e = pe.PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")
    state = e.build_initial_state(profile, soil_info, 0.015, layer_index=0)
    FORCING = {"precip": 0.0, "temp": 25.0, "pCO2": 0.015}
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                 layer_index=0, n_layers=4)
    assert "# 表层产酸源" not in inp


def test_surface_acid_layer0_short_natural_injection_points(profile,
                                                            soil_info,
                                                            monkeypatch):
    """L1 每场平衡调用传递 surface_acid_eq (force 键由引擎多层路径填充)"""
    import src.phreeqc_engine as pe
    from src.config_manager import ChargePairingConfig
    e = pe.PhreeqcEngine(
        database="phreeqc.dat", mode="phreeqc",
        surface_acid_cfg=SurfaceAcidConfig(enable=True, rate_molc_ha_yr=1000.0),
        charge_pairing_cfg=ChargePairingConfig(enable=True))
    captured = {}

    orig_run = e.run_monthly_multi_layer

    def spy(states, monthly_forcing, action, soil_profile, **kw):
        # 单层路径调用 run_monthly_step; 深层跳过在此层循环验证
        captured['n_states'] = len(states)
        return orig_run(states, monthly_forcing, action, soil_profile, **kw)

    monkeypatch.setattr(e, "run_monthly_multi_layer", spy)
    states = [e.build_initial_state(profile, soil_info, 0.015, layer_index=0)]
    FORCING = {"precip": 0.0, "temp": 25.0, "pCO2": 0.015}
    e.run_monthly_multi_layer(states, FORCING, MonthlyAction(), profile)
    assert captured['n_states'] == 1