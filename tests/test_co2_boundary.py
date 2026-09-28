"""工单92 (2026-09-24): CO₂ 气相边界实现治理单测 — 判据 1「意图一致性」

WF17 D2 裁定 P3-a = C1: 生产输入由
  `GAS_PHASE 1 / -fixed_pressure / -pressure <pCO₂> / CO2(g) 1.0`  (有限气相库)
改为
  `EQUILIBRIUM_PHASES 1 / CO2(g) <log10 pCO₂> <相摩尔 ≥1e6>`  (固定逸度 ≈ 无限库)

依据: PHREEQC 手册 GAS_PHASE 页 "A GAS_PHASE data block is not needed if
fixed partial pressures of gas components are desired; use EQUILIBRIUM_PHASES
instead." ⇒ 旧写法在临界态 (碳酸盐需求 ≫ 1 mol) 约束不可满足 ⇒ 该场无平衡解
(D4/D5 机制)。`USERGUIDE.md` 的生产意图即「固定分压」。

覆盖:
  1. 写入点 1 `src/phreeqc_input.build_phreeqc_input` (引擎月度/事件步);
  2. 写入点 2 `src/initial_condition.InitialConditionBuilder.build_phreeqc_input`
     (初始条件构建器的输入串副本);
  3. 两处口径一致 (共用 `co2_boundary_lines`)、相摩尔 ≥1e6、矿物相不被覆盖;
  4. `state.gas_phase` 状态字典语义保留 (pCO₂ 报告 + 预平衡目标);
  5. 真实 PHREEQC 实测: 新边界下月度步写出 `react` 行 (无退化步)。
"""

import math
import re

import pytest

from src.constants import CO2_BOUNDARY_PHASE_MOLES
from src.initial_condition import InitialConditionBuilder
from src.phreeqc_engine import PhreeqcEngine
from src.phreeqc_input import co2_boundary_lines
from src.scenario_controller import MonthlyAction


PCO2 = 0.030
FORCING = {"precip": 100.0, "temp": 25.0, "pCO2": PCO2}


def _engine():
    return PhreeqcEngine(database="phreeqc.dat", mode="phreeqc")


def _eq_block(inp: str) -> str:
    """提取 EQUILIBRIUM_PHASES 块体 (至后继块头为止)"""
    body = inp.split("EQUILIBRIUM_PHASES")[1]
    for sentinel in ("SURFACE 1", "REACTION 1", "SELECTED_OUTPUT"):
        if sentinel in body:
            body = body.split(sentinel)[0]
    return body


def _co2_phase(block: str):
    """解析 CO2(g) 相行 → (log10 pCO₂, 相摩尔)"""
    m = re.search(r"^\s*CO2\(g\)\s+(-?[\d.]+)\s+([\d.eE+-]+)\s*$", block, re.M)
    assert m, "EQUILIBRIUM_PHASES 块内无 CO2(g) 相行"
    return float(m.group(1)), float(m.group(2))


# ==================== 判据 1: 意图一致性 (两处写入点) ====================

def test_engine_input_co2_boundary_is_equilibrium_phase(profile, soil_info):
    """写入点 1 (月度/事件步): 平衡相 CO2(g) 携带 log10(pCO₂) 与相摩尔 ≥1e6"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    assert "GAS_PHASE" not in inp
    log_p, moles = _co2_phase(_eq_block(inp))
    assert log_p == pytest.approx(math.log10(PCO2), abs=5e-5)
    assert moles == pytest.approx(CO2_BOUNDARY_PHASE_MOLES)
    assert moles >= 1e6


def test_initial_condition_input_co2_boundary_is_equilibrium_phase(
        profile, soil_info):
    """写入点 2 (初始条件构建器输入串): 同一口径, 无 GAS_PHASE"""
    b = InitialConditionBuilder(profile, soil_info, pCO2=PCO2)
    inp = b.build_phreeqc_input(include_surface=False)
    assert "GAS_PHASE" not in inp
    log_p, moles = _co2_phase(_eq_block(inp))
    assert log_p == pytest.approx(math.log10(PCO2), abs=5e-5)
    assert moles == pytest.approx(CO2_BOUNDARY_PHASE_MOLES)


def test_two_write_points_share_single_source(profile, soil_info):
    """两处写入点共用 co2_boundary_lines ⇒ 行内容逐字一致 (口径不分叉)"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp_engine = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    b = InitialConditionBuilder(profile, soil_info, pCO2=PCO2)
    inp_init = b.build_phreeqc_input(include_surface=False)
    line = co2_boundary_lines(PCO2)[0]
    assert line in inp_engine
    assert line in inp_init


def test_co2_line_uses_log10_of_pco2():
    """相行格式 = log10(pCO₂) (气相目标饱和指数) + 相摩尔常量"""
    line = co2_boundary_lines(0.015)[0]
    assert "-1.8239" in line                      # log10(0.015)
    assert "1.000000e+06" in line


def test_pco2_zero_is_guarded():
    """pCO₂ ≤ 0 时取 log10 下限护栏 (不产生 -inf/-nan 行)"""
    line = co2_boundary_lines(0.0)[0]
    assert "-12.0000" in line
    assert "nan" not in line.lower()


# ==================== 块内共存、状态语义与回退面 ====================

def test_mineral_phases_preserved_in_same_block(profile, soil_info):
    """CO2(g) 为追加行 — 既有矿物相不被覆盖 (Al(OH)3(a)/kaolinite 仍在同块)"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, FORCING, MonthlyAction(), profile)
    blk = _eq_block(inp)
    assert "CO2(g)" in blk
    assert "Al(OH)3(a)" in blk
    assert "kaolinite" in blk


def test_gas_phase_state_dict_semantics_retained(profile, soil_info):
    """state.gas_phase 字典语义保留 (pCO₂ 报告/预平衡目标), 不随输入串改动"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, PCO2)
    assert state.gas_phase["CO2(g)"] == pytest.approx(PCO2)
    assert state.gas_phase["pressure"] == pytest.approx(1.0)
    b = InitialConditionBuilder(profile, soil_info, pCO2=PCO2)
    assert b.build_gas_phase()["CO2(g)"] == pytest.approx(PCO2)


def test_pco2_fallback_default(profile, soil_info):
    """forcing 缺 pCO2 → 回退 0.015 (与原 GAS_PHASE 口径一致)"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, {"precip": 100.0, "temp": 25.0},
                                 MonthlyAction(), profile)
    log_p, _ = _co2_phase(_eq_block(inp))
    assert log_p == pytest.approx(math.log10(0.015), abs=5e-5)


def test_layer_pco2_flows_into_boundary(profile, soil_info):
    """逐层 pCO₂ (L6) 经 forcing 流入边界相 — L4 覆盖 0.04 时目标指数跟随"""
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    inp = e._build_phreeqc_input(state, dict(FORCING, pCO2=0.04),
                                 MonthlyAction(), profile)
    log_p, _ = _co2_phase(_eq_block(inp))
    assert log_p == pytest.approx(math.log10(0.04), abs=5e-5)


def test_phase_moles_constant_at_least_1e6():
    """相摩尔下限锁定: <1e6 会退化为'无 CO₂ 交换'假解 (S3-c: 1e3 在 L1/L3 不足)"""
    assert CO2_BOUNDARY_PHASE_MOLES >= 1e6


# ==================== PHREEQC 实测: 该场不再"无平衡解" ====================

def test_phreeqc_monthly_step_has_react_row(profile, soil_info):
    """真实 PHREEQC: 新边界下月度步写出 react 行, 退化步计数为 0

    (工单93 只读护栏: 无 react 行 = 该场无平衡解 ⇒ 解析读到 i_soln 回声)
    """
    e = _engine()
    state = e.build_initial_state(profile, soil_info, 0.015)
    state = e.pre_equilibrate(state, profile, max_steps=10)
    new_state, diag = e.run_monthly_step(state, FORCING, MonthlyAction(),
                                        profile)
    assert new_state.ph > 0
    assert diag.has_react_row is True
    assert "react" in diag.sel_row_states
    assert e.degenerate_step_count == 0