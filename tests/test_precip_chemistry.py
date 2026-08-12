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
