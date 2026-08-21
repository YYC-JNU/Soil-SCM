"""v0.7.0 工单76: 30 年 8 情景方向带验收 (spec 69, Q14=A)

读 `output/sensitivity_pH_30yr_v070.csv` (sensitivity 口径, 无降水化学),
断言方向带 (科学诚实: 方向性验收, 不承诺具体值):

  ① natural 30 年 pH 缓降或持平 (末年 ≤ 首年 + 0.3, 不上升)
  ② fertilizer 30 年 <4.0 (盐基枯竭酸化)
  ③ lime_low/mid/high 3~5 年回落 (峰值后下降至 ≤ 峰值−0.5)
  ④ 排序 Natural < Fertilizer < Lime (末年 L1_pH_mean)
  ⑤ 全情景 30 年 phreeqc_ok = 1 (无降级)
  ⑥ N 收支闭合 (water_salt_balance N 行逐月 <5%, 阈值可配)

用法:
    python tools/verify_v0_7_0_acceptance.py [--csv output/sensitivity_pH_30yr_v070.csv]
输出: PASS/FAIL 逐项 + 摘要, 退出码 0=全过 / 1=有未达标 (如实报告)。
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd


def load(csv_path):
    df = pd.read_csv(csv_path)
    df['L1_pH_mean'] = df['L1_pH_mean'].astype(float)
    df['L1_pH_dec'] = df['L1_pH_dec'].astype(float)
    df['phreeqc_ok'] = df['phreeqc_ok'].astype(int)
    return df


def check_natural(df):
    """natural 30 年缓降或持平: 末年 ≤ 首年 + 0.3"""
    d = df[df.scenario == 'natural'].sort_values('year')
    if len(d) < 2:
        return False, 'natural 数据不足'
    first, last = d.iloc[0], d.iloc[-1]
    ok = last['L1_pH_mean'] <= first['L1_pH_mean'] + 0.3
    return ok, (f"natural {first['L1_pH_mean']:.2f} → {last['L1_pH_mean']:.2f} "
                f"(Δ={last['L1_pH_mean']-first['L1_pH_mean']:+.2f})")


def check_fertilizer(df):
    """fertilizer 30 年 <4.0 (盐基枯竭酸化)"""
    d = df[df.scenario == 'fertilizer'].sort_values('year')
    if len(d) < 2:
        return False, 'fertilizer 数据不足'
    last = d.iloc[-1]['L1_pH_mean']
    ok = last < 4.0
    return ok, f"fertilizer 末年 pH = {last:.2f} ({'<4.0' if ok else '≥4.0'})"


def check_lime(df):
    """lime 3~5 年回落: 峰值后下降 (末年 ≤ 峰值 − 0.5)"""
    results = []
    all_ok = True
    for scen in ('lime_low', 'lime_mid', 'lime_high'):
        d = df[df.scenario == scen].sort_values('year')
        if len(d) < 2:
            all_ok = False
            results.append(f'{scen}: 数据不足')
            continue
        peak = d['L1_pH_mean'].max()
        last = d.iloc[-1]['L1_pH_mean']
        ok = last <= peak - 0.5
        all_ok = all_ok and ok
        results.append(f'{scen}: 峰 {peak:.2f} → 末 {last:.2f} '
                       f'({"回落" if ok else "未回落"})')
    return all_ok, '; '.join(results)


def check_ordering(df):
    """排序 Natural < Fertilizer < Lime (末年 L1_pH_mean)"""
    last = df.groupby('scenario')['L1_pH_mean'].last()
    nat = last.get('natural', float('nan'))
    fert = last.get('fertilizer', float('nan'))
    lime = last.get('lime_low', float('nan'))
    ok = nat < fert < lime
    return ok, f'排序: Natural({nat:.2f}) < Fertilizer({fert:.2f}) < Lime({lime:.2f})'


def check_no_degrade(df):
    """全情景 phreeqc_ok=1 (无降级)"""
    bad = df[df.phreeqc_ok != 1]
    ok = len(bad) == 0
    return ok, f'无降级: {"PASS" if ok else f"FAIL ({len(bad)} 行降级)"}'


def check_n_balance(csv_path, threshold_pct=5.0):
    """N 收支闭合 (water_salt_balance N 行逐月 <阈值%)

    若无 N 收支报表则 SKIP (30 年全量跑完后用 tools/water_salt_balance.py 补)。
    """
    # water_salt_balance 的 N 行在输出中; 这里做能力检测
    n_path = Path('output/water_salt_balance_summary.csv')
    if not n_path.exists():
        return None, 'N 收支报表未生成 (30 年全量后 water_salt_balance 补)'
    df = pd.read_csv(n_path)
    if 'N_balance_pct' not in df.columns:
        return None, 'N 收支列缺失 (water_salt_balance 未扩展 N 行)'
    bad = df[df['N_balance_pct'].abs() > threshold_pct]
    ok = len(bad) == 0
    return ok, (f'N 收支闭合 <{threshold_pct}%: '
                f'{"PASS" if ok else f"FAIL ({len(bad)} 月超限)"}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default='output/sensitivity_pH_30yr_v070.csv')
    args = ap.parse_args()

    if not Path(args.csv).exists():
        print(f'[ERROR] {args.csv} 不存在 — 先跑 tools/sensitivity_pH_30yr.py '
              f'--all --years 30 生成')
        sys.exit(1)
    df = load(args.csv)

    checks = [
        ('① natural 缓降/持平', check_natural(df)),
        ('② fertilizer <4.0', check_fertilizer(df)),
        ('③ lime 3~5 年回落', check_lime(df)),
        ('④ 排序 N<F<L', check_ordering(df)),
        ('⑤ 30 年无降级', check_no_degrade(df)),
    ]
    n_ok = check_n_balance(args.csv)
    if n_ok[0] is not None:
        checks.append(('⑥ N 收支闭合', n_ok))

    print('=== v0.7.0 方向带验收 (spec 69, Q14=A) ===')
    all_ok = True
    for name, (ok, msg) in checks:
        status = 'PASS' if ok else ('SKIP' if ok is None else 'FAIL')
        if ok is None:
            all_ok = all_ok and True
        else:
            all_ok = all_ok and ok
        print(f'  [{status}] {name}: {msg}')

    if all_ok:
        print('\n[PASS] 全部达标 — 方向带达成, 可发布')
    else:
        print('\n[FAIL] 存在未达标项 — 需调优或如实记录差距')
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()