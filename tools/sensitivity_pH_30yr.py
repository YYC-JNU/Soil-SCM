# -*- coding: utf-8 -*-
"""敏感性实验 (v0.5.2): 不同情景下表层土壤 pH 未来 30 年演变对比

8 情景 (管理措施敏感性 + 气候敏感性):
  natural          仅降水 (基线, 无干预)
  fertilizer       常规化肥 (3/6/9 月 N-P-K-Mg-Zn, 农业农村部 2021 推荐量)
  lime_low         低量石灰 22.5 kg CaO/ha/次
  lime_mid         标准石灰 45 kg CaO/ha/次 (原 lime_only)
  lime_high        高量石灰 90 kg CaO/ha/次
  fertilizer_lime  化肥 + 标准石灰
  precip_increase  降水 +2%/年 (30 年累计 +80%, 气候强迫)
  temp_increase    增温 +0.05°C/年 (30 年 +1.5°C, 气候强迫)

模型: n_layers=4 (内置红壤物理剖面) + Green-Ampt 水文 (seed 固定, 各情景
降雨分配一致, 差异纯来自干预/气候) + 初始状态预平衡 (与 main.py 默认一致)。
输出: output/sensitivity_pH_30yr.csv (断点续跑) + output/sensitivity_pH_30yr.png

用法:
  python tools/sensitivity_pH_30yr.py --all               # 全部情景 (断点续跑)
  python tools/sensitivity_pH_30yr.py --scenario natural  # 单个情景
  python tools/sensitivity_pH_30yr.py --plot              # 读 CSV 绘图
  python tools/sensitivity_pH_30yr.py --all --years 10    # 缩短年数 (调试)
"""
import sys
import os
import csv
import copy
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
from src.scenario_controller import MonthlyAction

# ---- 实验常量 (与 config/config.yaml 默认值一致) ----
CSV_PATH = 'output/sensitivity_pH_30yr.csv'
PLOT_PATH = 'output/sensitivity_pH_30yr.png'
SEED = 42                      # 随机降雨种子 (各情景一致, 公平对比)
BASE_PRECIP = 1893.0           # 基准年降水 (mm)
BASE_TEMP = 25.0               # 基准年均温 (°C)
PCO2_REF = 0.015
T_REF = 25.0
BETA = 0.05
PRECIP_INC_RATE = 0.02         # 降水年增加比例 (precip_increase)
TEMP_INC_RATE = 0.05           # 温度年增加 (°C, temp_increase)
FERT_MONTHS = (3, 6, 9)        # 施肥/施石灰月份 (与 config 一致)
FERT_N = 12.0                  # kg N/ha/次
FERT_P2O5 = 4.0
FERT_K2O = 9.0
FERT_MGO = 3.0
FERT_ZN = 1.0

# 情景表: (key, 中文标签, 石灰量 kg CaO/ha/次, 是否施肥, ClimateForcing 情景)
SCENARIOS = [
    ('natural',          '自然状态 (仅降水)',        0.0,  False, 'natural'),
    ('fertilizer',       '常规施肥',                 0.0,  True,  'natural'),
    ('lime_low',         '低量石灰 22.5',            22.5, False, 'natural'),
    ('lime_mid',         '标准石灰 45',              45.0, False, 'natural'),
    ('lime_high',        '高量石灰 90',              90.0, False, 'natural'),
    ('fertilizer_lime',  '施肥+标准石灰',            45.0, True,  'natural'),
    ('precip_increase',  '降水+2%/年',               0.0,  False, 'precip_increase'),
    ('temp_increase',    '增温+0.05°C/年',           0.0,  False, 'temp_increase'),
]
COLORS = ['#333333', '#d62728', '#2ca02c', '#1f77b4', '#ff7f0e',
          '#9467bd', '#17becf', '#8c564b']
LSTYLES = ['-', '--', '-.', ':', '-', '--', '-.', ':']
CSV_FIELDS = ['scenario', 'label', 'year', 'L1_pH_mean', 'L1_pH_dec']


def make_action(key, month, lime_amount):
    """构造月度干预指令 (month 为 1-12; 施肥/石灰 3/6/9 月各一次)"""
    action = MonthlyAction()
    if month in FERT_MONTHS:
        if key in ('fertilizer', 'fertilizer_lime'):
            action.apply_fertilizer = True
            action.n_amount = FERT_N
            action.p2o5_amount = FERT_P2O5
            action.k2o_amount = FERT_K2O
            action.mgo_amount = FERT_MGO
            action.znso4_amount = FERT_ZN
        if lime_amount > 0:
            action.apply_lime = True
            action.lime_amount = lime_amount
    return action


def load_existing(path=CSV_PATH):
    """读取已存在结果: {scenario: [row_dict, ...]} (按年份升序)"""
    if not os.path.exists(path):
        return {}
    data = {}
    with open(path, 'r', newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            data.setdefault(row['scenario'], []).append(row)
    for rows in data.values():
        rows.sort(key=lambda r: int(r['year']))
    return data


def append_rows(path, rows):
    write_header = not os.path.exists(path)
    with open(path, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(rows)


def build_base_states(engine, reader, profile, info, pco2, pre_steps,
                      skip_pre=False):
    """构建 4 层初始状态并预平衡 (一次性, 各情景 deepcopy 复用)"""
    cfg = SimulationConfig(n_layers=4)
    _, states, pco2s, profiles = sim_main._build_initial_layer_states(
        engine, reader, profile, info, pco2, cfg)
    if not skip_pre:
        for i, s in enumerate(states):
            states[i] = engine.pre_equilibrate(s, profiles[i], pre_steps)
    print(f"[INIT] 4 层初始状态构建完成 (预平衡={'跳过' if skip_pre else pre_steps} 步)")
    print(f"[INIT] 表层(L1)初始 pH = {states[0].ph:.3f}")
    return states, pco2s, profiles


def run_scenario(engine, reader, profile, states0, pco2s, profiles,
                 key, label, lime_amount, fertilize, climate_scenario,
                 n_years, seed=SEED, verbose=True):
    """运行单个情景, 返回 (years, mean_ph, dec_ph) 三个列表"""
    states = copy.deepcopy(states0)
    climate = ClimateForcing(BASE_PRECIP, BASE_TEMP, PCO2_REF, T_REF,
                             BETA, n_years, climate_scenario,
                             precip_increase_rate=PRECIP_INC_RATE,
                             temp_increase_rate=TEMP_INC_RATE)
    theta_s = profiles[0].porosity
    theta_i = 0.5 * theta_s   # L1 初始含水量 50% 饱和 (与 main.py 一致)
    years, mean_ph, dec_ph = [], [], []
    for y in range(n_years):
        yearly = []
        for m in range(12):
            f = climate.get_monthly_forcing(y, m)
            a = make_action(key, m + 1, lime_amount)
            h, _runoff, _extra = sim_main._apply_hydrology_month(
                states, profiles, f, y, m, seed, theta_i=theta_i)
            states, _ = engine.run_monthly_multi_layer(
                states, f, a, profile, layer_pco2s=pco2s, hydrology=h)
            yearly.append(states[0].ph)   # L1 = 表层 (0-20cm)
        years.append(y + 1)
        mean_ph.append(float(np.mean(yearly)))
        dec_ph.append(yearly[-1])
        if verbose and ((y + 1) % 5 == 0 or y == 0):
            print(f"    {key:<18} 第 {y+1:2d} 年 | L1 pH 年均 = {mean_ph[-1]:.3f}")
    return years, mean_ph, dec_ph

def plot(path=CSV_PATH, out=PLOT_PATH):
    """读 CSV 生成 30 年表层 pH 对比图 (全部情景同图)"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    # 中文字体 (Windows: 微软雅黑; 缺失时回退默认)
    for font in ('Microsoft YaHei', 'SimHei', 'PingFang SC',
                 'Noto Sans CJK SC'):
        try:
            matplotlib.font_manager.findfont(font,
                                             fallback_to_default=False)
            matplotlib.rcParams['font.sans-serif'] = [font, 'DejaVu Sans']
            break
        except Exception:
            continue
    matplotlib.rcParams['axes.unicode_minus'] = False

    data = load_existing(path)
    if not data:
        print('[PLOT] CSV 为空, 无图可绘')
        return
    n_years = max(int(r['year']) for rows in data.values() for r in rows)

    fig, ax = plt.subplots(figsize=(12.5, 8))
    complete = 0
    for i, (key, label, *_rest) in enumerate(SCENARIOS):
        rows = data.get(key)
        if not rows:
            continue
        years = [int(r['year']) for r in rows]
        phs = [float(r['L1_pH_mean']) for r in rows]
        dph = phs[-1] - phs[0]
        if len(rows) >= n_years:
            complete += 1
        ax.plot(years, phs, color=COLORS[i], linestyle=LSTYLES[i],
                lw=2.2, marker='o', ms=4,
                label=f'{label}   (ΔpH={dph:+.2f})')

    ax.set_xlabel('年份 (Year)', fontsize=12)
    ax.set_ylabel('表层土壤 pH (L1, 年均值)', fontsize=12)
    ax.set_title(f'不同情景下表层土壤 pH 未来 {n_years} 年演变对比 '
                 f'(敏感性实验, 4 层模型, seed={SEED})', fontsize=13)
    ax.legend(loc='best', fontsize=10, framealpha=0.9)
    ax.grid(True, alpha=0.3)
    all_ph = [float(r['L1_pH_mean']) for rows in data.values() for r in rows]
    ax.set_ylim(bottom=min(all_ph) - 0.5)
    ax.set_xlim(0.5, n_years + 0.5)
    ax.annotate(
        '模型局限 (v0.5.2): 单层 Al 淋洗脱酸使 natural 情景 pH 上行;\n'
        '多层模型含垂直 Al 累积, 结果更接近红壤酸化物理认知。\n'
        f'已完成情景: {complete}/{len(SCENARIOS)}',
        xy=(0.02, 0.02), xycoords='axes fraction', ha='left', va='bottom',
        fontsize=8.5, color='dimgray',
        bbox=dict(boxstyle='round,pad=0.4', facecolor='lightyellow',
                  alpha=0.8))

    plt.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches='tight')
    print(f'[PLOT] 已保存: {out} ({complete}/{len(SCENARIOS)} 情景完整)')



def main():
    parser = argparse.ArgumentParser(
        description='表层土壤 pH 30 年情景敏感性实验')
    parser.add_argument('--all', action='store_true',
                        help='运行全部情景 (断点续跑)')
    parser.add_argument('--scenario', type=str,
                        help='运行单个情景 key (natural/fertilizer/lime_low/'
                             'lime_mid/lime_high/fertilizer_lime/'
                             'precip_increase/temp_increase)')
    parser.add_argument('--plot', action='store_true', help='只读 CSV 绘图')
    parser.add_argument('--years', type=int, default=30, help='模拟年数 (默认 30)')
    parser.add_argument('--seed', type=int, default=SEED, help='随机降雨种子')
    parser.add_argument('--pre-steps', type=int, default=60,
                        help='预平衡最大步数 (默认 60)')
    parser.add_argument('--skip-pre', action='store_true',
                        help='跳过预平衡 (调试)')
    args = parser.parse_args()

    if args.plot:
        plot()
        return

    valid_keys = [s[0] for s in SCENARIOS]
    if args.scenario and args.scenario not in valid_keys:
        parser.error(f'未知情景: {args.scenario}, 可选: {valid_keys}')
    if args.scenario:
        targets = [args.scenario]
    elif args.all:
        targets = [s[0] for s in SCENARIOS]
    else:
        parser.error('需指定 --all 或 --scenario')

    reader = InputReader('data/soil_survey.csv', 'data/exchangeable_ions.csv')
    profile = reader.build_soil_profile()
    db = SoilDatabase(json_path='config/soil_mineral_db.json',
                      tbl_path='config/soil_mineral.tbl')
    info = db.get_soil_info('red_soil')
    pco2 = db.get_pCO2('red_soil')
    engine = PhreeqcEngine(database='phreeqc.dat', mode='phreeqc')
    states0, pco2s, profiles = build_base_states(
        engine, reader, profile, info, pco2, args.pre_steps, args.skip_pre)

    existing = load_existing()
    for key in targets:
        rows = existing.get(key, [])
        if len(rows) >= args.years:
            print(f'{key}: 已有完整 {len(rows)} 年数据, 跳过')
            continue
        meta = next(s for s in SCENARIOS if s[0] == key)
        print(f'\n=== 运行情景 {key} ({meta[1]}, {args.years} 年, 4 层) ===')
        years, means, decs = run_scenario(
            engine, reader, profile, states0, pco2s, profiles,
            key, meta[1], meta[2], meta[3], meta[4],
            args.years, seed=args.seed)
        new_rows = [{'scenario': key, 'label': meta[1], 'year': y,
                     'L1_pH_mean': f'{mp:.3f}', 'L1_pH_dec': f'{dp:.3f}'}
                    for y, mp, dp in zip(years, means, decs)]
        append_rows(CSV_PATH, new_rows)
        existing[key] = rows + new_rows
        print(f'  {key}: L1 pH {means[0]:.3f} -> {means[-1]:.3f} '
              f'(Δ = {means[-1]-means[0]:+.3f})')

    print(f'\n[DONE] 全部目标情景完成, 结果: {CSV_PATH} '
          f'(累计 {sum(len(v) for v in existing.values())} 行)')


if __name__ == '__main__':
    main()

