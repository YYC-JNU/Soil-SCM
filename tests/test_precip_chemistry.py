import pytest
from src.precip_chemistry import PrecipChemistry


def test_reaction_amounts(precip_chem):
    conc = precip_chem.ion_mol_per_l()
    amounts = precip_chem.reaction_amounts(1000.0)  # 1000 L 入渗水
    for sp in ("Cl-", "SO4-2", "NO3-", "F-", "Ca+2", "NH4+", "Na+", "Mg+2", "K+", "H+"):
        assert sp in amounts, sp
        assert amounts[sp] > 0, sp
    # 自洽性: 摩尔量 = 浓度 × 水量
    assert abs(amounts["Cl-"] - conc["Cl"] * 1000.0) < 1e-8
    assert abs(amounts["SO4-2"] - conc["SO4"] * 1000.0) < 1e-8


# ==================== v0.2.3: config 内联 data 直接使用 ====================

INLINE_DATA = {
    "pH": 5.5,
    "ions": {
        "Cl": 20.0, "SO4": 12.0, "NO3": 11.0, "F": 2.0,
        "Ca": 21.0, "NH4": 15.0, "Na": 11.0, "Mg": 5.0,
        "K": 2.0, "H": 1.0,
    },
}


def test_inline_data_ph():
    """config 内联 data: pH 正确读取"""
    pc = PrecipChemistry(data=INLINE_DATA)
    assert pc.ph == 5.5
    assert pc.ions["Ca"] == 21.0


def test_inline_data_reaction_amounts():
    """config 内联 data: 浓度换算与 REACTION 量正确"""
    pc = PrecipChemistry(data=INLINE_DATA)
    conc = pc.ion_mol_per_l()
    amounts = pc.reaction_amounts(1000.0)
    assert abs(amounts["Cl-"] - conc["Cl"] * 1000.0) < 1e-8
    # 自洽性: 总当量浓度 = 10^(-pH) / (H_frac/100)
    total_eq = pc.total_eq_concentration()
    assert abs(total_eq - 10.0 ** (-5.5) / 0.01) < 1e-12


def test_inline_data_differs_from_default():
    """内联数据与默认 JSON 不同: 验证确实使用内联"""
    pc = PrecipChemistry(data=INLINE_DATA)
    assert pc.ph != 5.75          # 默认 JSON pH=5.75
    assert pc.ions["Cl"] != 18.4  # 默认 JSON Cl=18.4
