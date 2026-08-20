"""测试 v0.6.1 water_salt_balance 闭合审计工具 (S7, spec 62 Q8, 工单 67)

  - 构造已知收支样例验证水量闭合公式 (P = Runoff + AET + lat + base + ΔS)
  - 阈值告警逻辑 (<1% 水量闭合)
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.water_salt_balance import (compute_monthly_water_balance,
                                      summarize_annual, WATER_CLOSE_TOL)


def _row(year=1, month=1, precip=158.0, runoff=20.0, aet=90.0,
         lat_mm=15.0, base_mm=25.0, storage=400.0):
    """构造主 CSV 行 (逐层列, L/ha 值 = mm×10000; storage = 本月末储水 mm)"""
    row = {
        'year': str(year), 'month': str(month),
        'precip_mm': str(precip), 'runoff_mm': str(runoff),
        'AET_mm': str(aet),
        'stored_water_L1': str(storage * 10000.0),
        'lateral_L1': str(lat_mm * 10000.0),
        'baseflow_L1': str(base_mm * 10000.0),
    }
    return row


def test_water_balance_perfect_closure():
    """S7: 构造完美闭合样例 (P = 各出口 + ΔS) → 残差 ≈ 0"""
    # 上月: storage=400; 本月: P=158, out=20+90+15+25=150, storage=408
    # → ΔS=8 → P = 150+8 = 158 → 闭合
    rows = [_row(year=0, month=12, storage=400.0),
            _row(year=1, month=1, storage=408.0)]
    monthly = compute_monthly_water_balance(rows, n_layers=1)
    r = monthly[1]   # 第二行有 ΔS
    assert r['dS_mm'] == pytest.approx(8.0)
    assert r['out_sum_mm'] == pytest.approx(20 + 90 + 15 + 25 + 8)
    assert r['water_residual'] == pytest.approx(0.0, abs=1e-9)
    assert r['water_closed'] is True


def test_water_balance_exact_known_values():
    """S7: 已知数值逐项核对 (公式精确)"""
    rows = [_row(year=2, month=5, storage=410.0),
            _row(year=2, month=6, precip=200.0, runoff=40.0, aet=100.0,
                 lat_mm=20.0, base_mm=30.0, storage=420.0)]
    monthly = compute_monthly_water_balance(rows, n_layers=1)
    r = monthly[1]
    assert r['precip_mm'] == pytest.approx(200.0)
    assert r['runoff_mm'] == pytest.approx(40.0)
    assert r['aet_mm'] == pytest.approx(100.0)
    assert r['lateral_mm'] == pytest.approx(20.0)
    assert r['baseflow_mm'] == pytest.approx(30.0)
    assert r['dS_mm'] == pytest.approx(10.0)
    # 200 = 40+100+20+30+10 → 完全闭合
    assert r['water_residual'] == pytest.approx(0.0, abs=1e-9)


def test_water_balance_residual_flag():
    """S7: 不闭合样例 → 残差超阈值 → water_closed=False"""
    # 上月 storage=400; 本月 storage=400 (ΔS=0), P=158, out=150 → 残差 8/158
    rows = [_row(year=0, month=12, storage=400.0),
            _row(year=1, month=1, storage=400.0)]
    monthly = compute_monthly_water_balance(rows, n_layers=1)
    r = monthly[1]
    assert abs(r['water_residual']) > WATER_CLOSE_TOL
    assert r['water_closed'] is False


def test_annual_summary_closure():
    """S7: 年度聚合 (年际 ΔS 趋零) 闭合"""
    # 前月 (year0) + 3 个月完美闭合: 每月 ΔS=8, storage 递增
    rows = [_row(year=0, month=12, storage=400.0)]
    storage = 400.0
    for m in range(0, 3):
        storage += 8.0
        rows.append(_row(year=1, month=m + 1, storage=storage))
    monthly = compute_monthly_water_balance(rows, n_layers=1)
    annual = summarize_annual(monthly)
    assert len(annual) == 1
    a = annual[0]
    # 年 ΣP = 3×158 = 474, Σout = 3×150 = 450, 年 ΔS = 24 (400→424)
    # → 474 = 450 + 24 → 闭合
    assert a['ds'] == pytest.approx(24.0)
    assert a['water_closed'] is True
    assert abs(a['water_residual']) < WATER_CLOSE_TOL
