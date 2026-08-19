"""测试 v0.5.3 PET 通道 (src/climate_forcing.py) — S3 seam (spec 49):

  - calc_pet_oudin 手算验证 (广州 23.1°N: 1月 2.05 / 7月 5.93 mm/day)
  - ClimateForcing.monthly_pet 逐月数组 (n_years×12, Oudin 正算, 温变响应)
  - pet_correction_factor 月度修正生效
  - pet_monthly_climate 固定气候态兜底 (提供时优先, 专家★4)
  - get_monthly_forcing 输出 'pet' 键
"""

import pytest
from src.climate_forcing import calc_pet_oudin, ClimateForcing


def test_calc_pet_oudin_handcalc_guangzhou():
    """Oudin 手算 (广州 φ=23.1°N, J=月中): 1月 T=15°C → 2.046 mm/day

    独立计算 (非代码自证): Ra=25.058 MJ/m²/day;
    PET = 25.058×1000/2450 × (15+5)/100 = 2.046 mm/day。
    """
    pet = calc_pet_oudin(15.0, 23.1, 1)
    assert pet == pytest.approx(2.046, abs=0.005)


def test_calc_pet_oudin_summer_higher():
    """夏季 (7月, T=31.5°C) PET 高于冬季 (1月) — 华南 PET 峰值在盛夏"""
    pet_winter = calc_pet_oudin(15.0, 23.1, 1)
    pet_summer = calc_pet_oudin(31.5, 23.1, 7)
    assert pet_summer > pet_winter
    assert pet_summer == pytest.approx(5.93, abs=0.02)


def test_calc_pet_oudin_cold_threshold():
    """温度阈值: (T+5)/100 < 0 → PET=0 (冬季休眠)"""
    assert calc_pet_oudin(-5.0, 23.1, 1) == 0.0


def test_calc_pet_oudin_latitude_effect():
    """同月同温: 纬度越高 (鹰潭 28.2°N) PET 越低 (冬季日照短)"""
    pet_gz = calc_pet_oudin(13.0, 23.1, 1)
    pet_yt = calc_pet_oudin(13.0, 28.2, 1)
    assert pet_yt < pet_gz
    assert pet_yt == pytest.approx(1.626, abs=0.005)


def test_monthly_pet_array_shape_and_positive():
    """monthly_pet 数组 (n_years×12), 夏季>冬季, 年际温变响应"""
    cf = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05, 3, "natural")
    assert cf.monthly_pet.shape == (3, 12)
    assert (cf.monthly_pet > 0).all()
    # 华南: 夏季 PET > 冬季 PET
    assert cf.monthly_pet[0, 6] > cf.monthly_pet[0, 0]
    # 年际温变 (temp_increase): 后期 PET 更高
    cf_inc = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05, 5,
                            "temp_increase")
    assert cf_inc.monthly_pet[-1].sum() > cf_inc.monthly_pet[0].sum()


def test_pet_correction_factor_applied():
    """月度修正系数生效: 全月 ×2 → PET 数组翻倍"""
    cf0 = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05, 1, "natural")
    cf2 = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05, 1, "natural",
                         pet_correction_factor=[2.0] * 12)
    assert cf2.monthly_pet[0, 5] == pytest.approx(cf0.monthly_pet[0, 5] * 2.0)


def test_pet_monthly_climate_priority():
    """固定气候态兜底: pet_monthly_climate 提供时优先 (专家★4)"""
    clim = [45.0, 50.0, 65.0, 85.0, 105.0, 115.0,
            130.0, 125.0, 110.0, 85.0, 60.0, 45.0]
    cf = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05, 2, "natural",
                        pet_monthly_climate=clim)
    assert cf.monthly_pet[0, 0] == pytest.approx(45.0)
    assert cf.monthly_pet[1, 6] == pytest.approx(130.0)


def test_get_monthly_forcing_has_pet():
    """get_monthly_forcing 输出 'pet' 键 (v0.5.3)"""
    cf = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05, 1, "natural")
    f = cf.get_monthly_forcing(0, 0)
    assert "pet" in f
    assert f["pet"] == pytest.approx(cf.monthly_pet[0, 0])


# ==================== v0.5.3 OM 矿化产 CO₂ (Q4/Q10, 专家★3) ====================

def test_apply_om_pco2_additive():
    """加性: pCO₂_eff = base + k_om×OM (L1 30g/kg → +0.015 atm)"""
    from src.climate_forcing import apply_om_pco2
    assert apply_om_pco2(0.015, 30.0) == pytest.approx(0.030)
    assert apply_om_pco2(0.015, 0.0) == pytest.approx(0.015)


def test_apply_om_pco2_clamped():
    """钳制: 高 OM 下 pCO₂_eff ≤ pCO₂_max (不失控, Q4 专家修订)"""
    from src.climate_forcing import apply_om_pco2
    assert apply_om_pco2(0.04, 30.0) == pytest.approx(0.05)    # 0.055 → 钳制
    assert apply_om_pco2(0.049, 100.0) == pytest.approx(0.05)  # 极高 OM 也钳制


def test_apply_om_pco2_temperature_independent():
    """温度独立性 (专家★3): ΔpCO₂ 与 T/base 无关 (增量恒定, T 响应仅归 base)"""
    from src.climate_forcing import apply_om_pco2
    d_low = apply_om_pco2(0.010, 30.0) - 0.010
    d_high = apply_om_pco2(0.030, 30.0) - 0.030
    assert d_low == pytest.approx(d_high)   # 同 OM 异 base → 增量相同


def test_apply_om_pco2_vertical_gradient():
    """垂直梯度 (专家★3): OM [30,15,8,5] → pCO₂_eff 单调不增且表层增量最大"""
    from src.climate_forcing import apply_om_pco2
    base = 0.015
    effs = [apply_om_pco2(base, om) for om in (30.0, 15.0, 8.0, 5.0)]
    assert all(e1 >= e2 for e1, e2 in zip(effs, effs[1:]))
    assert effs[0] - base > effs[3] - base   # 表层增量最大


# ==================== v0.6.0 Hargreaves PET (S4, Q8/Q9) ====================

def test_calc_pet_oudin_dispatch_equals_legacy():
    """Q9: calc_pet('oudin') 与 calc_pet_oudin 数值等价 (回归门禁)"""
    from src.climate_forcing import calc_pet
    for m in range(1, 13):
        assert calc_pet(25.0, 23.1, m, method='oudin') == \
            pytest.approx(calc_pet_oudin(25.0, 23.1, m))


def test_calc_pet_hargreaves_formula_and_diurnal_sensitivity():
    """Q8/Q9: Hargreaves — 日较差↑ → PET↑, 且 ∝ √range (公式端点)"""
    from src.climate_forcing import calc_pet
    pet8 = calc_pet(25.0, 23.1, 6, method='hargreaves', diurnal_range_deg=8.0)
    pet16 = calc_pet(25.0, 23.1, 6, method='hargreaves', diurnal_range_deg=16.0)
    assert pet16 > pet8
    assert pet16 == pytest.approx(pet8 * (16.0 / 8.0) ** 0.5, rel=1e-9)


def test_calc_pet_hargreaves_sensible_magnitude():
    """Hargreaves 量级合理: 与 Oudin 同量级 (0~15 mm/day, 月内各月)"""
    from src.climate_forcing import calc_pet
    for m in range(1, 13):
        pet = calc_pet(25.0, 23.1, m, method='hargreaves',
                       diurnal_range_deg=8.0)
        assert 0 <= pet <= 15.0


def test_calc_pet_hargreaves_enhanced_raises():
    """Q9: hargreaves_enhanced 显式报错 (v0.6.0 预留, 数据管线留 v0.7.0)"""
    from src.climate_forcing import calc_pet
    with pytest.raises(NotImplementedError):
        calc_pet(25.0, 23.1, 6, method='hargreaves_enhanced')


def test_generate_pet_hargreaves_method():
    """Q9: pet_method='hargreaves' 走 calc_pet 分派 (n_years×12 数组)"""
    cf = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05, 1, "natural",
                        pet_method="hargreaves", diurnal_range_deg=8.0)
    assert cf.monthly_pet.shape == (1, 12)
    assert (cf.monthly_pet > 0).all()
