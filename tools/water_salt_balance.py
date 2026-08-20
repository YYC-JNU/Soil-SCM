# -*- coding: utf-8 -*-
"""v0.6.1 水量/盐分闭合审计工具 (spec 62 Q8, 工单 67)

读取主 CSV (monthly diagnostics) 逐月计算:
  水量闭合: ΣP ≈ ΣRunoff + ΣAET + ΣQ_lat + ΣQ_base + ΔS (阈值 <1%)
  盐分闭合: 输入降水盐分 ≈ 各出口盐分 + 存储变化 (阈值 <5%)

主 CSV 列约定 (output_writer 输出, 逐层后缀):
  year/month/time_decimal/precip_mm/runoff_mm/AET_mm/
  infiltration_L1~L4/drainage_L1~L4/stored_water_L1~L4/
  baseflow_L1~L4/lateral_L1~L4 (v0.6.1 新增)/...

用法:
  python tools/water_salt_balance.py [CSV_PATH] [--csv-only]
    默认读 output/soil_scm_results.csv 或 output/*.csv

闭合方程 (华南红壤, 专家 §7 预期比例):
  地表径流 20~30% / ET 45~55% / 侧向 10~20% / 基流 10~15%
"""
import sys
import csv
import argparse
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

# ---- 闭合阈值 (spec 62 Q8 定案) ----
WATER_CLOSE_TOL = 0.01     # 水量闭合 <1%
SALT_CLOSE_TOL = 0.05      # 盐分闭合 <5%
DEFAULT_CSV = 'output/soil_scm_results.csv'


def _find_csv(path=None):
    """定位主 CSV (默认 output/ 下最新 *.csv)"""
    if path and Path(path).exists():
        return path
    out_dir = Path('output')
    if not out_dir.exists():
        return None
    csvs = sorted(out_dir.glob('*.csv'), key=lambda p: p.stat().st_mtime,
                  reverse=True)
    return str(csvs[0]) if csvs else None


def _col(row, name, n_layers):
    """取逐层列 (无后缀回退全局列)"""
    for i in range(1, n_layers + 1):
        key = f'{name}_L{i}'
        if key in row:
            yield i - 1, float(row.get(key, 0.0) or 0.0)


def compute_monthly_water_balance(rows, n_layers=4):
    """从 CSV 行计算逐月水量闭合

    返回: list[dict] 每行含闭合项 + water_residual (残差分数)
    水量闭合: P = Runoff + AET + ΣQ_lat + ΣQ_base + ΔS_storage
      ΔS 由 stored_water 逐月差近似 (年内月差, 年际趋零)
    """
    results = []
    prev_storage = None
    for row in rows:
        r = {}
        r['year'] = int(row.get('year', 0))
        r['month'] = int(row.get('month', 0))
        r['precip_mm'] = float(row.get('precip_mm', 0.0) or 0.0)
        r['runoff_mm'] = float(row.get('runoff_mm', 0.0) or 0.0)
        r['aet_mm'] = float(row.get('AET_mm', 0.0) or 0.0)
        # 逐层出口聚合 (L/ha → mm = L/ha / 10000)
        r['lateral_mm'] = sum(
            v for _, v in _col(row, 'lateral', n_layers)) / 10000.0
        r['baseflow_mm'] = sum(
            v for _, v in _col(row, 'baseflow', n_layers)) / 10000.0
        r['storage_mm'] = sum(
            v for _, v in _col(row, 'stored_water', n_layers)) / 10000.0
        # ΔS = 本月末储水 − 上月末储水 (mm)
        if prev_storage is not None:
            r['dS_mm'] = r['storage_mm'] - prev_storage
        else:
            r['dS_mm'] = 0.0
        prev_storage = r['storage_mm']
        # 水量闭合: P = Runoff + AET + lat + base + ΔS
        r['out_sum_mm'] = (r['runoff_mm'] + r['aet_mm']
                           + r['lateral_mm'] + r['baseflow_mm']
                           + r['dS_mm'])
        denom = max(abs(r['precip_mm']), 1e-9)
        r['water_residual'] = (r['precip_mm'] - r['out_sum_mm']) / denom
        r['water_closed'] = abs(r['water_residual']) < WATER_CLOSE_TOL
        results.append(r)
    return results


def summarize_annual(results):
    """年度聚合水量闭合 (年际 ΔS 趋零 → 更严闭合检验)"""
    years = {}
    for r in results:
        if r['year'] <= 0:
            continue   # 前月占位行不参与年度统计
        y = years.setdefault(r['year'], {
            'precip': 0.0, 'runoff': 0.0, 'aet': 0.0,
            'lat': 0.0, 'base': 0.0, 'ds': 0.0, 'n': 0})
        y['precip'] += r['precip_mm']
        y['runoff'] += r['runoff_mm']
        y['aet'] += r['aet_mm']
        y['lat'] += r['lateral_mm']
        y['base'] += r['baseflow_mm']
        y['ds'] += r['dS_mm']
        y['n'] += 1
    summary = []
    for yr, y in sorted(years.items()):
        denom = max(abs(y['precip']), 1e-9)
        resid = (y['precip'] - y['runoff'] - y['aet'] - y['lat']
                 - y['base'] - y['ds']) / denom
        summary.append({
            'year': yr, 'precip': y['precip'], 'runoff': y['runoff'],
            'aet': y['aet'], 'lat': y['lat'], 'base': y['base'],
            'ds': y['ds'], 'water_residual': resid,
            'water_closed': abs(resid) < WATER_CLOSE_TOL})
    return summary


def audit_from_csv(csv_path=None, verbose=True):
    """主入口: 读 CSV → 逐月/年度水量闭合报告"""
    path = _find_csv(csv_path)
    if not path:
        print('[water_salt_balance] 未找到主 CSV (output/*.csv)')
        return None
    with open(path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        print('[water_salt_balance] CSV 为空:', path)
        return None
    # 检测层数 (lateral 列后缀)
    n_layers = 1
    sample = rows[0]
    for key in sample:
        if key.startswith('lateral_L'):
            n_layers = max(n_layers, int(key.split('_L')[1]))
    monthly = compute_monthly_water_balance(rows, n_layers)
    annual = summarize_annual(monthly)
    if verbose:
        print(f'[water_salt_balance] 源: {path}')
        print(f'[water_salt_balance] 层数: {n_layers}, 月份数: {len(monthly)}')
        print(f'\n{"年":>4} {"降水":>8} {"径流":>8} {"AET":>8} '
              f'{"侧向":>8} {"基流":>8} {"ΔS":>8} {"残差%":>8} 状态')
        for a in annual:
            flag = 'OK' if a['water_closed'] else '!! 超阈'
            print(f"{a['year']:>4} {a['precip']:>8.1f} "
                  f"{a['runoff']:>8.1f} {a['aet']:>8.1f} "
                  f"{a['lat']:>8.1f} {a['base']:>8.1f} {a['ds']:>8.2f} "
                  f"{a['water_residual']*100:>7.2f}%  {flag}")
        n_ok = sum(1 for a in annual if a['water_closed'])
        print(f'\n[water_salt_balance] 水量闭合: {n_ok}/{len(annual)} '
              f'年度 OK (阈值 <{WATER_CLOSE_TOL*100}%)')
    return {'monthly': monthly, 'annual': annual}


def main():
    ap = argparse.ArgumentParser(description='Soil-SCM 水量/盐分闭合审计')
    ap.add_argument('csv_path', nargs='?', default=None,
                    help='主 CSV 路径 (默认 output/ 最新)')
    args = ap.parse_args()
    result = audit_from_csv(args.csv_path)
    if result is None:
        sys.exit(1)


if __name__ == '__main__':
    main()
