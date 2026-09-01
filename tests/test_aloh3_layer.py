"""工单D (2026-08-31): Al(OH)3(a) 分层参数测试 — 深层铝缓冲标定机制

覆盖 (设计树 M1):
  - 默认逐位一致回归: 无 layer_index → fraction=AMORPHOUS_ALOH3_MASS_FRACTION /
    scale=MINERAL_SCALE / logk=数据库值 10.8 不注入 PHASES (v85 基线行为)
  - 分层机制: L4 (layer_index=3) 用 AMORPHOUS_ALOH3_4LAYER_* (monkeypatch 可标定)
  - log_k PHASES 注入: 仅当分层值 != 数据库值 10.8
  - 层数护栏: 越界 / None / n_layers=1 → 全局默认
  - 集中访问器 layer_aloh3_params 单一来源行为
"""

import pytest

from src.phreeqc_engine import PhreeqcEngine
from src.scenario_controller import MonthlyAction
from src.utils import layer_aloh3_params
import src.constants as C


FORCING = {"precip": 0.0, "temp": 25.0, "pCO2": 0.015}


def _engine(**kw):
    return PhreeqcEngine(database="phreeqc.dat", mode="phreeqc", **kw)


def _eq_aloh3_mol(inp):
    """从输入串提取 Al(OH)3(a) EQUILIBRIUM_PHASES 摩尔量 (缩放后)"""
    for ln in inp.splitlines():
        if ln.strip().startswith('Al(OH)3(a)'):
            return float(ln.split()[2])
    raise AssertionError('输入无 Al(OH)3(a) EQUILIBRIUM_PHASES 行')


# ==================== 集中访问器 (单一来源) ====================

def test_aloh3_params_default_none():
    """layer_index=None → 全局默认 (基线)"""
    p = layer_aloh3_params()
    assert p['fraction'] == pytest.approx(C.AMORPHOUS_ALOH3_MASS_FRACTION)
    assert p['logk'] == pytest.approx(C.AMORPHOUS_ALOH3_LOGK_DATABASE)
    assert p['scale'] == pytest.approx(C.MINERAL_SCALE)


def test_aloh3_params_single_layer_guard():
    """n_layers=1 护栏: 即使传 layer_index 也走全局默认"""
    p = layer_aloh3_params(0, 1)
    assert p['fraction'] == pytest.approx(C.AMORPHOUS_ALOH3_MASS_FRACTION)
    p3 = layer_aloh3_params(3, 1)
    assert p3['scale'] == pytest.approx(C.MINERAL_SCALE)


def test_aloh3_params_oob_fallback():
    """索引越界 → 全局默认"""
    p = layer_aloh3_params(5, 4)
    assert p['fraction'] == pytest.approx(C.AMORPHOUS_ALOH3_MASS_FRACTION)


def test_aloh3_params_layer_values(monkeypatch):
    """分层取值 (标定网格可 monkeypatch): L4 用 4LAYER 值, L1 保持基线"""
    monkeypatch.setattr(C, "AMORPHOUS_ALOH3_4LAYER_FRACTIONS",
                        [0.02, 0.02, 0.02, 0.06])
    monkeypatch.setattr(C, "AMORPHOUS_ALOH3_4LAYER_LOGK",
                        [10.8, 10.8, 10.8, 9.3])
    monkeypatch.setattr(C, "AMORPHOUS_ALOH3_4LAYER_SCALE",
                        [C.MINERAL_SCALE] * 3 + [1.0])
    p = layer_aloh3_params(3, 4)
    assert p['fraction'] == pytest.approx(0.06)
    assert p['logk'] == pytest.approx(9.3)
    assert p['scale'] == pytest.approx(1.0)
    p1 = layer_aloh3_params(0, 4)
    assert p1['fraction'] == pytest.approx(0.02)
    assert p1['logk'] == pytest.approx(C.AMORPHOUS_ALOH3_LOGK_DATABASE)


# ==================== 引擎默认逐位一致 (回归锁定) ====================

def test_aloh3_default_no_phases_injection(profile, soil_info):
    """默认 logk=10.8 (=数据库值) → 不注入 PHASES 覆盖块 (v85 基线)"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    lines = [ln.strip() for ln in inp.splitlines()]
    assert "PHASES" not in lines          # 无独立 PHASES 覆盖块
    assert any(ln.startswith("EQUILIBRIUM_PHASES") for ln in lines)  # 平衡相块仍在


def test_aloh3_default_scale_is_mineral_scale(profile, soil_info):
    """默认 scale = MINERAL_SCALE (所有层含 L4, v85 基线逐位一致)"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    base_mol = state.minerals['Al(OH)3(a)']
    for li in (0, 3):
        inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                     layer_index=li, n_layers=4)
        assert _eq_aloh3_mol(inp) == pytest.approx(base_mol * C.MINERAL_SCALE)


# ==================== 分层机制 ====================

def test_aloh3_layer_fraction(profile, soil_info, monkeypatch):
    """L4 分层质量分数 → build_initial_state.minerals['Al(OH)3(a)'] 跟随"""
    monkeypatch.setattr(C, "AMORPHOUS_ALOH3_4LAYER_FRACTIONS",
                        [0.02, 0.02, 0.02, 0.06])
    e = _engine()
    s1 = e.build_initial_state(profile, soil_info, 0.015, layer_index=0)
    s4 = e.build_initial_state(profile, soil_info, 0.015, layer_index=3)
    mass = profile.soil_mass_per_ha
    assert s1.minerals['Al(OH)3(a)'] == pytest.approx(
        mass * C.AMORPHOUS_ALOH3_MASS_FRACTION * 1000.0
        / C.AMORPHOUS_ALOH3_MOLAR_MASS)
    assert s4.minerals['Al(OH)3(a)'] == pytest.approx(
        mass * 0.06 * 1000.0 / C.AMORPHOUS_ALOH3_MOLAR_MASS)


def test_aloh3_layer_scale_injection(profile, soil_info, monkeypatch):
    """L4 分层 scale (解开千斤顶) → EQUILIBRIUM_PHASES 摩尔量 = 物理量;
    L1 保持 MINERAL_SCALE 缩水 (逐位基线)"""
    monkeypatch.setattr(C, "AMORPHOUS_ALOH3_4LAYER_SCALE",
                        [C.MINERAL_SCALE] * 3 + [1.0])
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    base_mol = state.minerals['Al(OH)3(a)']
    inp4 = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                  layer_index=3, n_layers=4)
    inp1 = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                  layer_index=0, n_layers=4)
    assert _eq_aloh3_mol(inp4) == pytest.approx(base_mol * 1.0)
    assert _eq_aloh3_mol(inp1) == pytest.approx(base_mol * C.MINERAL_SCALE)


def test_aloh3_layer_logk_injection(profile, soil_info, monkeypatch):
    """L4 分层 log_k ≠ 数据库值 → 注入 PHASES 覆盖; L1 默认 10.8 不注入"""
    monkeypatch.setattr(C, "AMORPHOUS_ALOH3_4LAYER_LOGK",
                        [10.8, 10.8, 10.8, 9.3])
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp4 = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                  layer_index=3, n_layers=4)
    lines4 = [ln.strip() for ln in inp4.splitlines()]
    assert "PHASES" in lines4
    assert "-log_k 9.3" in inp4
    inp1 = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                  layer_index=0, n_layers=4)
    lines1 = [ln.strip() for ln in inp1.splitlines()]
    assert "PHASES" not in lines1
    assert "-log_k 9.3" not in inp1


def test_aloh3_layer_guard_default(profile, soil_info, monkeypatch):
    """层数护栏: 越界 layer_index → 全局默认 (不注入 log_k, scale=MINERAL_SCALE)"""
    monkeypatch.setattr(C, "AMORPHOUS_ALOH3_4LAYER_LOGK",
                        [10.8, 10.8, 10.8, 9.3])
    monkeypatch.setattr(C, "AMORPHOUS_ALOH3_4LAYER_SCALE",
                        [C.MINERAL_SCALE] * 3 + [1.0])
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile,
                                 layer_index=9, n_layers=4)
    lines = [ln.strip() for ln in inp.splitlines()]
    assert "PHASES" not in lines
    assert _eq_aloh3_mol(inp) == pytest.approx(
        state.minerals['Al(OH)3(a)'] * C.MINERAL_SCALE)
