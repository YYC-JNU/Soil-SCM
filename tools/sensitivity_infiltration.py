# -*- coding: utf-8 -*-
"""敏感性实验 (v0.5.2): Green-Ampt 基质导水率 ksat_surface (1~15 cm/day)
对 4 层土壤最终 pH 的影响

   情景 natural, 15 年, n_layers=4 (内置水文默认剖面), 随机降雨 seed=42 固定,
   唯一变量 = 表层基质导水率 (profiles[0].ksat_surface, Green-Ampt 入渗 K_s)。

   结果: output/sensitivity_infiltration.csv (断点续跑, 已存在 ksat 跳过)
   散点图: output/sensitivity_infiltration_scatter.png
         横=ksat_surface(cm/day), 纵=4 层土层, 颜色=第 15 年各层 pH 均值 (RdYlBu_r, 3.0~7.0)

   用法:
     python tools/sensitivity_infiltration.py --ksat 3.0   # 单点
     python tools/sensitivity_infiltration.py --all        # 循环全部点 (断点续跑)
     python tools/sensitivity_infiltration.py --all --max 7  # 分批 (前 7 点)
     python tools/sensitivity_infiltration.py --plot       # 读 CSV 生成散点图
"""
import sys
import os
import csv
import argparse
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
import numpy as np
import main as sim_main
from src.input_reader import InputReader
from src.soil_database import SoilDatabase
from src.config_manager import SimulationConfig
from src.phreeqc_engine import PhreeqcEngine
from src.climate_forcing import ClimateForcing
from src.scenario_controller import ScenarioController

N_YEARS = 15
CSV_PATH = 'output/sensitivity_infiltration.csv'
PLOT_PATH = 'output/sensitivity_infiltration_scatter.png'
SEED = 42
# v0.5.2: 扫描变量 = Green-Ampt 基质导水率 ksat_surface (cm/day), 1~15, 1 间隔
KSAT_RANGE = [round(1.0 + i * 1.0, 1) for i in range(15)]
FIELDS = ['ksat_surface', 'L1_pH_mean', 'L2_pH_mean', 'L3_pH_mean', 'L4_pH_mean',
          'surface_pH_mean']


def run_point(engine, reader, profile, info, pco2, ksat_surface,
              n_years=N_YEARS):
    """运行 4 层内置默认 + ksat_surface 覆盖, 返回第 n_years 年各层 pH 均值

    返回:
        list[float]: [L1, L2, L3, L4] 第 15 年 12 个月 pH 均值
    """
    cfg = SimulationConfig(n_layers=4)
    _, states, pco2s, profiles = sim_main._build_initial_layer_states(
        engine, reader, profile, info, pco2, cfg)
    profiles[0].ksat_surface = ksat_surface  # 扫描变量: Green-Ampt 入渗 K_s
    climate = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05,
                             n_years, 'natural')
    ctrl = ScenarioController('natural', {}, {})
    last_year_ph = [[] for _ in range(4)]
    for y in range(n_years):
        for m in range(12):
            f = climate.get_monthly_forcing(y, m)
            a = ctrl.get_action(y + 1, m + 1)
            h, _runoff, _extra = sim_main._apply_hydrology_month(
                states, profiles, f, y, m, SEED)
            states, _ = engine.run_monthly_multi_layer(
                states, f, a, profile, layer_pco2s=pco2s, hydrology=h)
            if y == n_years - 1:
                for i, s in enumerate(states):
                    last_year_ph[i].append(s.ph)
    return [float(np.mean(last_year_ph[i])) for i in range(4)]


def load_existing(path=CSV_PATH):
    """读取已存在结果: {ksat_surface: row dict}"""
    if os.path.exists(path):
        with open(path, 'r', newline='', encoding='utf-8') as f:
            return {float(r['ksat_surface']): r for r in csv.DictReader(f)}
    return {}


def append_row(path, row):
    write_header = not os.path.exists(path)
    with open(path, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            w.writeheader()
        w.writerow(row)


def plot(path=CSV_PATH, out=PLOT_PATH):
    """读 CSV 生成散点图: 横=ksat_surface cm/day, 纵=4 层, 色=第 15 年年均 pH"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows = load_existing(path)
    if not rows:
        print('CSV 为空, 无图可绘'); return
    ksats = sorted(rows)
    xs, ys, cs = [], [], []
    for ksat in ksats:
        for li in range(4):
            xs.append(ksat)
            ys.append(li + 1)
            cs.append(float(rows[ksat][f'L{li+1}_pH_mean']))
    fig, ax = plt.subplots(figsize=(12, 5.5))
    sc = ax.scatter(xs, ys, c=cs, cmap='RdYlBu_r', vmin=3.0, vmax=7.0,
                    s=180, edgecolors='k', linewidths=0.5)
    ax.set_yticks([1, 2, 3, 4])
    ax.set_yticklabels(['L1 (0-20cm)', 'L2 (20-40cm)', 'L3 (40-60cm)',
                        'L4 (60-100cm)'])
    ax.set_xlabel('Green-Ampt K_s (cm/day)', fontsize=12)
    ax.set_ylabel('Soil layer', fontsize=12)
    ax.set_title(f'Green-Ampt K_s sensitivity: final pH by layer '
                 f'(natural {N_YEARS}y, seed={SEED}, year-{N_YEARS} mean)',
                 fontsize=13)
    ax.invert_yaxis()
    ax.grid(True, alpha=0.3)
    cbar = fig.colorbar(sc, ax=ax, label='Final pH (year-15 mean)')
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches='tight')
    print(f'[PLOT] 已保存: {out}')


def main():
    parser = argparse.ArgumentParser(description='Green-Ampt K_s 敏感性实验')
    parser.add_argument('--ksat', type=float,
                        help='单点基质导水率 ksat_surface (cm/day, 1~15)')
    parser.add_argument('--all', action='store_true', help='循环全部点 (断点续跑)')
    parser.add_argument('--max', type=int, default=15,
                        help='--all 时最多跑前 N 点 (分批用)')
    parser.add_argument('--plot', action='store_true', help='生成散点图')
    args = parser.parse_args()

    if args.plot:
        plot()
        return

    reader = InputReader('data/soil_survey.csv', 'data/exchangeable_ions.csv')
    profile = reader.build_soil_profile()
    db = SoilDatabase(json_path='config/soil_mineral_db.json',
                      tbl_path='config/soil_mineral.tbl')
    info = db.get_soil_info('red_soil')
    pco2 = db.get_pCO2('red_soil')
    engine = PhreeqcEngine(database='phreeqc.dat', mode='phreeqc')

    if args.ksat is not None:
        targets = [args.ksat]
    elif args.all:
        targets = KSAT_RANGE[:args.max]
    else:
        parser.error('需指定 --ksat 或 --all')

    existing = load_existing()
    done = 0
    for ksat in targets:
        if ksat in existing:
            print(f'ksat_surface={ksat:.1f} 已存在, 跳过')
            continue
        print(f'运行 ksat_surface={ksat:.1f} ({N_YEARS} 年, 4 层, natural)...')
        means = run_point(engine, reader, profile, info, pco2, ksat)
        row = {'ksat_surface': f'{ksat:.1f}',
               'L1_pH_mean': f'{means[0]:.3f}',
               'L2_pH_mean': f'{means[1]:.3f}',
               'L3_pH_mean': f'{means[2]:.3f}',
               'L4_pH_mean': f'{means[3]:.3f}',
               'surface_pH_mean': f'{means[0]:.3f}'}
        append_row(CSV_PATH, row)
        print(f'  L1={means[0]:.3f} L2={means[1]:.3f} '
              f'L3={means[2]:.3f} L4={means[3]:.3f}')
        existing[ksat] = row
        done += 1
    print(f'完成 {done} 点 (累计 {len(existing)} 点), 结果: {CSV_PATH}')


if __name__ == '__main__':
    main()

