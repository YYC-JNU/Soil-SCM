"""测试 L5 溶液电荷平衡 HCO₃⁻ 缓冲 (v0.3.0):

  - 电荷平衡从保守 Cl⁻ 补足 (Q13) 改为 HCO₃⁻ 补足
  - 初始 HCO₃⁻ 由亨利定律 + 碳酸一级解离从 pCO₂ 计算 (与 GAS_PHASE 联动)
  - 保留微量 Cl⁻ (CHARGE_BALANCE_CL_RESIDUAL), 避免数值边缘 (Q11)
  - _check_charge_balance 用碳酸体系真实电荷 (HCO3- 1价 + CO3-2 2价)
"""

import pytest

from src.initial_condition import InitialConditionBuilder
from src.constants import CHARGE_BALANCE_CL_RESIDUAL


def _builder(profile, soil_info):
    return InitialConditionBuilder(profile, soil_info, pCO2=0.015)


def test_hco3_from_pco2_henry(profile, soil_info):
    """初始 HCO₃⁻ 与 pCO₂ 自洽 (亨利定律 + 碳酸一级解离)"""
    b = _builder(profile, soil_info)
    sol = b.build_solution()
    h_plus = 10.0 ** (-sol['pH'])
    hco3_theory = b.KA1_H2CO3 * b.KH_CO2 * b.pCO2 / h_plus
    # 从 C(4) 拆分还原 hco3, 应 ≥ 理论值 (阳离子盈余以 HCO3- 补足)
    c4 = sol['C(4)']
    h2co3 = c4 / (1.0 + b.KA1_H2CO3 / h_plus +
                  b.KA1_H2CO3 * b.KA2_HCO3 / h_plus ** 2)
    hco3 = h2co3 * b.KA1_H2CO3 / h_plus
    assert hco3 >= hco3_theory - 1e-12


def test_cl_balances_surplus_hco3_by_pco2(profile, soil_info):
    """L5 修正 (实测校准): pH<6 下 HCO3- 承载能力有限, Cl- 兜底电荷盈余

    HCO3- 由 pCO2 决定 (亨利定律, 碳酸自洽); C(4) 保持 pCO2 平衡量级
    (无旧 HCO3 强制补足的 0.09 mol/L 暴涨——PHREEQC 数值失稳根因);
    电荷盈余由 Cl- 承担 (土壤溶液主要强酸阴离子, Q13 物理必要)。
    """
    b = _builder(profile, soil_info)
    sol = b.build_solution()
    # C(4) 接近 pCO2 平衡量级 (无 HCO3 强制补足暴涨)
    h2co3_sat = b.KH_CO2 * b.pCO2
    assert sol['C(4)'] < 10 * h2co3_sat
    # Cl- 承担盈余 (远大于微量背景 1e-6), 由阳离子-阴离子差额决定
    assert sol['Cl'] > 1e-4


def test_charge_balance_precise_carbonates(profile, soil_info):
    """_check_charge_balance 用碳酸体系真实电荷, 补足后不平衡度近零"""
    b = _builder(profile, soil_info)
    sol = b.build_solution()
    imbalance = b._check_charge_balance(sol)
    assert abs(imbalance) < 1e-3


def test_c4_above_pure_h2co3_saturation(profile, soil_info):
    """C(4) ≥ 纯 H2CO3 溶解量 (含 HCO3-/CO3-, 与 GAS_PHASE pCO2 一致)"""
    b = _builder(profile, soil_info)
    sol = b.build_solution()
    h2co3_sat = b.KH_CO2 * b.pCO2
    assert sol['C(4)'] > h2co3_sat * 0.9


def test_solution_consistent_with_gas_phase(profile, soil_info):
    """SOLUTION 的 C(4) 与 GAS_PHASE pCO2 写在一起 (开放体系自洽)"""
    b = _builder(profile, soil_info)
    inp = b.build_phreeqc_input(include_surface=False)
    sol = b.build_solution()
    assert "C(4)" in inp
    assert f"-pressure     {b.pCO2:.6f}" in inp
    assert sol['C(4)'] > 0
