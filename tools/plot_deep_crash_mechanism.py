# -*- coding: utf-8 -*-
"""深层崩塌机制链图生成器（2026-09-29）

把"深层（L4）碱度累积 → 浓度冲洗 → 盐基淋失泵放大 → 交换相整体翻转 → pH 崩塌"
画成**机制流程图 + 逐年读数面板**，供 `USERGUIDE.md` 引用。

- **产品版**（中性措辞，**无工单号**）：`docs/images/deep_layer_crash_mechanism.png`（默认输出）
- **开发版**（含 WF19/D7/工单上下文）：加 `--dev`，输出到
  `.scratch/soil-scm-overview/diagrams/wf19_mechanism_dev.png`

**数据驱动**：图内所有数字读自基线包的**附加只读列**（`--extra-observables` 产物），
默认 `output/BASELINE_v97x_LAYERS.csv`；**只读**，不改变模型行为。

⚠️ 该 CSV 需由深层包生成器产出（含 `L*_BS/HX/base_charge/sol_C4` 与 `L*_led_*` 列）：
```
python .scratch/soil-scm-overview/tools/launch_pack_shards.py v97x_ \
       .scratch/soil-scm-overview/tools/make_baseline_pack.py \
       output/sensitivity_pH_30yr_v92.csv extra
```

用法:
  python tools/plot_deep_crash_mechanism.py                      # 仅产品图
  python tools/plot_deep_crash_mechanism.py --dev                # 产品图 + 开发图
  python tools/plot_deep_crash_mechanism.py --csv <csv> --scenario lime_mid
"""
import argparse
import csv
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
os.chdir(_ROOT)

import matplotlib                                   # noqa: E402
matplotlib.use('Agg')
import matplotlib.pyplot as plt                     # noqa: E402

# 中文回退（口径抄仓库既有 tools/plot_92_gates.py）
for _fam in ('Microsoft YaHei', 'SimHei', 'PingFang SC'):
    try:
        plt.rcParams['font.sans-serif'] = [_fam]
        plt.rcParams['axes.unicode_minus'] = False
        break
    except Exception:
        continue

PROD = 'docs/images/deep_layer_crash_mechanism.png'
DEV = '.scratch/soil-scm-overview/diagrams/wf19_mechanism_dev.png'


def load(csv_path, scen, years):
    rows = list(csv.DictReader(open(csv_path, encoding='utf-8')))
    d = {(r['scenario'], int(r['year'])): r for r in rows if r['scenario'] == scen}

    def g(y, c):
        return float(d[(scen, y)].get(c) or 0.0)
    return {y: {'pH': g(y, 'L4_pH_mean'), 'BS': g(y, 'L4_BS'),
                'base': g(y, 'L4_base_charge'), 'HX': g(y, 'L4_HX'),
                'C4': g(y, 'L4_sol_C4'), 'site': g(y, 'L4_ex_q'),
                'ebase': g(y, 'L4_led_base_loss_eq'),
                'cat': g(y, 'L4_led_leach_cation_eq_molc'),
                'flush': g(y, 'L4_led_flush_L')} for y in years}


def draw(dat, years, dev=False, out=PROD):
    ys = list(years)
    cr = max(ys) - 1              # 崩塌年（末年前一年：ΔL4_pH ≤ −2）
    for y in ys:
        if y > ys[0] and (dat[y]['pH'] - dat[y - 1]['pH'] <= -2.0
                          or dat[y]['pH'] <= 3.0):
            cr = y
            break
    pre, post = dat[cr - 1], dat[cr]
    fig = plt.figure(figsize=(13.2, 7.0), dpi=150)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.32, 1.0], wspace=0.06)
    ax = fig.add_subplot(gs[0, 0]); ax.axis('off')
    ax.set_xlim(0, 10); ax.set_ylim(0, 11.3)

    stages = [
        ('①  深层 DIC / 碱度累积', '液相 C(4) 顶到冲洗阈值平台\n'
         f'C(4) → CONC_WARN = 0.5 mol/L（实测 {pre["C4"]:.3f} / 0.500）', '#e8f1fb'),
        ('②  Q6 浓度冲洗启动（出水量放大）', '阈值触发基流/侧向激增（flush）\n'
         f'flush {pre["flush"]:.2e} → {post["flush"]:.2e} L/ha/yr', '#fdf3e3'),
        ('③  E_base 盐基淋失泵"可抽池"放大', '可抽池 ∝ 出水量\n'
         f'认领 {dat[ys[0]]["ebase"]:,.0f} → {pre["ebase"]:,.0f} → '
         f'{post["ebase"]:,.0f} molc/ha/yr（{post["ebase"] / dat[ys[0]]["ebase"]:.0f}×）',
         '#fdeaea'),
        ('④  交换相整体翻转', f'盐基 {pre["base"]:,.0f} → {post["base"]:,.0f}'
         f'（{post["base"] / pre["base"] * 100 - 100:.0f}%）\n'
         f'HX {pre["HX"]:.0f} → {post["HX"]:,.0f}；'
         f'位点总数 {post["site"]:,.0f}（不变）', '#eef7ec'),
        ('⑤  深层 pH 崩塌（L4）', f'pH {pre["pH"]:.2f} → {post["pH"]:.2f} → '
         f'{dat[ys[-1]]["pH"]:.2f}（y{ys[-1]}）', '#f3eafb'),
    ]
    y0, dy, bh = 10.05, 1.72, 1.32
    for i, (title, sub, fc) in enumerate(stages):
        ytop = y0 - i * dy
        ax.add_patch(plt.Rectangle((0.35, ytop - bh), 8.0, bh, fc=fc,
                                   ec='#5b6b7b', lw=1.3, zorder=2,
                                   joinstyle='round'))
        ax.text(0.75, ytop - 0.40, title, fontsize=12.5, weight='bold',
                va='center', zorder=3)
        ax.text(0.75, ytop - 0.96, sub, fontsize=10, color='#2b3a4a',
                va='center', zorder=3)
        if i < len(stages) - 1:
            ax.annotate('', xy=(4.35, ytop - bh - 0.30),
                        xytext=(4.35, ytop - bh),
                        arrowprops=dict(arrowstyle='-|>', lw=2.0,
                                        color='#5b6b7b'), zorder=3)
    ax.text(0.35, 10.72, ('深层崩塌机制链（诊断示意 + 实测读数）'
                          + ('  —  WF19 §E7 / D7 / W19-B / 工单 99' if dev else '')),
            fontsize=14, weight='bold')
    note = ('触发量 = 深层碳/碱度缺出口；执行机构 = E_base × Q6 冲洗耦合\n'
            '现象 = 交换相翻转；位点总数不变 → 非"位点零化"\n'
            '边界：崩塌期 NO3- 池淋失 / 伴随注入 / An- / H+ 注酸 全为 0')
    if dev:
        note += '\n（开发版：本图含 D7 上下文，**不入产品仓库**；产品版见 docs/images/）'
    ax.text(0.35, 1.06, note, fontsize=9, color='#37474f', va='center',
            linespacing=1.5)
    ax.text(0.35, 0.20, '数据源：8 情景 30y 深层包（附加只读列）；情景 = '
            f'{SCEN_LABEL} L4。只读观测，不改变模型行为。',
            fontsize=8.5, color='#78909c')

    ax2 = fig.add_subplot(gs[0, 1])
    eb = [dat[y]['ebase'] for y in ys]
    ph = [dat[y]['pH'] for y in ys]
    ax2.bar([f'y{y}' for y in ys], eb, color='#e57373', alpha=0.85,
            label='E_base 认领 (molc/ha/yr)')
    ax2.set_ylabel('E_base 认领 (molc/ha/yr)', color='#c62828')
    ax2.tick_params(axis='y', labelcolor='#c62828')
    ax2.set_title(f'L4 逐年读数（{SCEN_LABEL}）', fontsize=12)
    ax3 = ax2.twinx()
    ax3.plot([f'y{y}' for y in ys], ph, 'o-', color='#1565c0', lw=2.2,
             label='L4 pH（年末）')
    ax3.set_ylabel('L4 pH', color='#1565c0')
    ax3.tick_params(axis='y', labelcolor='#1565c0')
    ax2.set_xlabel('C(4) mol/L（y%d→y%d）：' % (ys[0], ys[-1])
                   + ' / '.join(f'{dat[y]["C4"]:.3f}' for y in ys),
                   fontsize=9.5)
    ax2.axvline(ys.index(cr), color='#c62828', ls='--', lw=1.3, alpha=0.75)
    ax2.text(ys.index(cr) + 0.09, max(eb) * 0.99,
             f'崩塌年 y{cr}（ΔL4_pH ≤ −2）', color='#c62828', fontsize=9,
             va='top')
    h1, l1 = ax2.get_legend_handles_labels()
    h2, l2 = ax3.get_legend_handles_labels()
    ax2.legend(h1 + h2, l1 + l2, loc='upper left', fontsize=8.5,
               framealpha=0.92)
    ax2.grid(alpha=0.25, axis='y')

    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, bbox_inches='tight')
    plt.close(fig)
    print(f'[图] {out}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default='output/BASELINE_v97x_LAYERS.csv',
                    help='深层包 CSV（需含附加只读列）')
    ap.add_argument('--scenario', default='lime_mid')
    ap.add_argument('--years', type=int, nargs=4, default=[27, 28, 29, 30])
    ap.add_argument('--dev', action='store_true', help='同时出开发版（含票号）')
    ap.add_argument('--out-prod', default=PROD)
    ap.add_argument('--out-dev', default=DEV)
    args = ap.parse_args()

    global SCEN_LABEL
    SCEN_LABEL = args.scenario
    if not os.path.exists(args.csv):
        raise SystemExit(f'缺少 {args.csv}（需先产出含 --extra-observables 的深层包；'
                         '见本文件头部说明）')
    data = load(args.csv, args.scenario, tuple(args.years))
    draw(data, tuple(args.years), dev=False, out=args.out_prod)
    if args.dev:
        draw(data, tuple(args.years), dev=True, out=args.out_dev)


SCEN_LABEL = 'lime_mid'


if __name__ == '__main__':
    main()