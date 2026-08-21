# -*- coding: utf-8 -*-
"""敏感性实验 (v0.6.0): 不同情景下表层土壤 pH 未来 30 年演变对比 (事件驱动)

8 情景 (管理措施敏感性 + 气候敏感性):
  natural          仅降水 (基线, 无干预)
  fertilizer       常规化肥 (3/6/9 月 N-P-K-Mg-Zn, 农业农村部 2021 推荐量)
  lime_low         低量石灰 22.5 kg CaO/ha/次
  lime_mid         标准石灰 45 kg CaO/ha/次 (原 lime_only)
  lime_high        高量石灰 90 kg CaO/ha/次
  fertilizer_lime  化肥 + 标准石灰
  precip_increase  降水 +2%/年 (30 年累计 +80%, 气候强迫)
  temp_increase    增温 +0.05°C/年 (30 年 +1.5°C, 气候强迫)

模型 (v0.6.0): n_layers=4 (内置红壤物理剖面 + OM 调制 pCO₂) + 事件驱动化学
(_apply_hydrology_events: 逐场 Green-Ampt + 级联 + Feddes ET, seed 固定各情景
一致) + 体积-θ 耦合 (SOLUTION -water = θ×depth×1e5, 浓缩酸化自然产生)
+ 初始状态预平衡 (initial_psi_cm=-100 田间持水量)。对比 v0.5.2 月度路径:
v0.6.0 修正了表层 pH 恒 6.9 的平台化, 酸化方向 (末月 L1≈3.9) 更接近红壤。

输出: output/sensitivity_pH_30yr_v060.csv (断点续跑)
     + output/sensitivity_pH_30yr_v060.png

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
CSV_PATH = 'output/sensitivity_pH_30yr_v060.csv'
PLOT_PATH = 'output/sensitivity_pH_30yr_v060.png'
SEED = 42                      # 随机降雨种子 (各情景一致, 公平对比)
# v0.6.1 (spec 62 Q1/Q10): 基流/侧向出口 (VIC/Darcy), 默认启用
# (对治 30 年深层盐分累积 → PHREEQC 数值边界)
BASEFLOW_CFG = {'D_max': 100.0, 'D_s': 0.10, 'n_base': 2.5}
LATERAL_CFG = {'f_slope': 0.10,
               'k_lat': [0.04, 0.025, 0.015, 0.008]}
BASE_PRECIP = 1893.0           # 基准年降水 (mm)
BASE_TEMP = 25.0               # 基准年均温 (°C)
PCO2_REF = 0.015
T_REF = 25.0
BETA = 0.05
LATITUDE = 23.1                # 站点纬度 (广东, Oudin PET)
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
CSV_FIELDS = ['scenario', 'label', 'year', 'L1_pH_mean', 'L1_pH_dec',
              'phreeqc_ok']


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
    cfg = SimulationConfig(n_layers=4, hydrology_seed=SEED)
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
    """运行单个情景, 返回 (years, mean_ph, dec_ph) 三个列表

    v0.6.0: 事件驱动化学 — _apply_hydrology_events 逐场水文 + run_monthly_
    multi_layer 内部逐场 run_event_step (体积-θ 耦合)。L1 pH = 每月最后
    一场事件后的表层状态。
    """
    states = copy.deepcopy(states0)
    climate = ClimateForcing(BASE_PRECIP, BASE_TEMP, PCO2_REF, T_REF,
                             BETA, n_years, climate_scenario,
                             precip_increase_rate=PRECIP_INC_RATE,
                             temp_increase_rate=TEMP_INC_RATE,
                             latitude=LATITUDE)
    years, mean_ph, dec_ph, phreeqc_ok = [], [], [], []
    fallback = False
    for y in range(n_years):
        yearly = []
        for m in range(12):
            f = climate.get_monthly_forcing(y, m)
            a = make_action(key, m + 1, lime_amount)
            h, _runoff, _extra = sim_main._apply_hydrology_events(
                states, profiles, f, y, m, seed, bypass_fraction=0.2,
                baseflow_cfg=BASEFLOW_CFG, lateral_cfg=LATERAL_CFG)
            states, _ = engine.run_monthly_multi_layer(
                states, f, a, profile, layer_pco2s=pco2s, hydrology=h)
            # v0.6.0 数值边界: PHREEQC 失败后引擎永久降级简化模式 (pH 钳制)
            if getattr(engine, '_permanent_fallback', False):
                fallback = True
            yearly.append(states[0].ph)   # L1 = 表层 (0-20cm)
        years.append(y + 1)
        mean_ph.append(float(np.mean(yearly)))
        dec_ph.append(yearly[-1])
        phreeqc_ok.append(0 if fallback else 1)
        if verbose and ((y + 1) % 5 == 0 or y == 0):
            print(f"    {key:<18} 第 {y+1:2d} 年 | L1 pH 年均 = {mean_ph[-1]:.3f}"
                  f"{'' if not fallback else '  [已降级简化]'}")
    if fallback:
        fb_year = next(i + 1 for i, ok in enumerate(phreeqc_ok) if not ok)
        print(f"    [!] 第 {fb_year} 年起 PHREEQC 永久降级简化模式 "
              f"(深层盐分累积数值边界, v0.6.1 调校项), 其后 pH 为钳制伪影")
    return years, mean_ph, dec_ph, phreeqc_ok


def _run_scenario_worker(q, engine_cfg, reader_paths, profile, states0, pco2s,
                         profiles, key, label, lime_amount, fertilize,
                         climate_scenario, n_years, seed):
    """子进程 worker: 独立引擎执行 run_scenario (超时隔离, v0.6.1)

    PHREEQC 偶发卡顿 (RunString 不返回, 非确定) 时主进程无法中断同步调用;
    本 worker 在子进程执行, 超时由主进程 terminate 兜底 (v0.6.1 修复建议)。
    """
    try:
        from src.input_reader import InputReader
        from src.phreeqc_engine import PhreeqcEngine
        reader = InputReader(*reader_paths)
        engine = PhreeqcEngine(**engine_cfg)
        years, means, decs, p_ok = run_scenario(
            engine, reader, profile, states0, pco2s, profiles,
            key, label, lime_amount, fertilize, climate_scenario,
            n_years, seed=seed, verbose=False)
        q.put(('ok', years, means, decs, p_ok))
    except Exception as e:
        q.put(('error', str(e)))


def run_scenario_with_timeout(reader_paths, engine_cfg, profile, states0,
                              pco2s, profiles, key, label, lime_amount,
                              fertilize, climate_scenario, n_years, seed,
                              timeout=120.0):
    """子进程超时运行单情景 (v0.6.1: 卡顿终止不挂死)

    返回:
        (years, means, decs, p_ok) 或 None (超时/失败, 记录并跳过)
    """
    import multiprocessing
    ctx = multiprocessing.get_context('spawn')
    q = ctx.Queue()
    p = ctx.Process(target=_run_scenario_worker,
                    args=(q, engine_cfg, reader_paths, profile, states0,
                          pco2s, profiles, key, label, lime_amount, fertilize,
                          climate_scenario, n_years, seed))
    p.start()
    p.join(timeout)
    if p.is_alive():
        p.terminate()
        p.join()
        print(f'  [!] 情景 {key} 超时 (>{timeout:.0f}s), PHREEQC 卡顿 — '
              f'已终止, 断点续跑可重试', flush=True)
        return None
    try:
        result = q.get(timeout=2)
    except Exception:
        return None
    if isinstance(result, tuple) and result and result[0] == 'error':
        print(f'  [!] 情景 {key} 子进程失败: {result[1]}', flush=True)
        return None
    return result[1:] if result else None

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
    min_fb_year = None
    for i, (key, label, *_rest) in enumerate(SCENARIOS):
        rows = data.get(key)
        if not rows:
            continue
        years = [int(r['year']) for r in rows]
        phs = [float(r['L1_pH_mean']) for r in rows]
        p_ok = [int(r.get('phreeqc_ok', 1)) for r in rows]
        dph = phs[-1] - phs[0]
        if len(rows) >= n_years:
            complete += 1
        ok_count = sum(p_ok)
        if ok_count == len(p_ok):
            # PHREEQC 全程正常: 实线
            ax.plot(years, phs, color=COLORS[i], linestyle=LSTYLES[i],
                    lw=2.2, marker='o', ms=4,
                    label=f'{label}   (ΔpH={dph:+.2f})')
        else:
            # 降级点之后: 虚线淡化 (简化模式 pH 钳制伪影)
            fb_year = years[ok_count]
            min_fb_year = (fb_year if min_fb_year is None
                           else min(min_fb_year, fb_year))
            ax.plot(years[:ok_count + 1], phs[:ok_count + 1],
                    color=COLORS[i], linestyle=LSTYLES[i], lw=2.2,
                    marker='o', ms=4,
                    label=f'{label}   (ΔpH={dph:+.2f})')
            ax.plot(years[ok_count:], phs[ok_count:], color=COLORS[i],
                    linestyle=':', lw=1.5, alpha=0.55, marker='o', ms=3)
            ax.axvline(x=fb_year, color=COLORS[i], lw=0.9, ls=':', alpha=0.5)

    if min_fb_year is not None:
        ax.axvspan(min_fb_year - 0.5, n_years + 0.5, color='red', alpha=0.06,
                   label=f'简化模式区域 (PHREEQC 数值边界, ≥y{min_fb_year})')

    ax.set_xlabel('年份 (Year)', fontsize=12)
    ax.set_ylabel('表层土壤 pH (L1, 年均值)', fontsize=12)
    ax.set_title(f'不同情景下表层土壤 pH 未来 {n_years} 年演变对比 '
                 f'(敏感性实验 v0.6.0, 4 层事件驱动, seed={SEED})', fontsize=13)
    ax.legend(loc='best', fontsize=9, framealpha=0.9)
    ax.grid(True, alpha=0.3)
    all_ph = [float(r['L1_pH_mean']) for rows in data.values() for r in rows]
    ax.set_ylim(bottom=min(all_ph) - 0.5)
    ax.set_xlim(0.5, n_years + 0.5)
    ax.annotate(
        'v0.6.0 事件驱动 + 体积-θ 耦合: 表层 pH 呈酸化方向 (修正 v0.5.x\n'
        '恒 ~6.9 平台); 长期深层盐分累积极端触发 PHREEQC 数值边界, 引擎\n'
        '自动降级简化模式 (pH 钳制 2.0~12.0, 红色阴影区为伪影, v0.6.1 调校项)。\n'
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
    parser.add_argument('--tag', type=str, default='v070',
                        help='输出文件名标签 (并行分情景运行用, 默认 v070)')
    parser.add_argument('--timeout', type=float, default=1800.0,
                        help='单情景子进程超时秒数 (v0.6.1: PHREEQC 卡顿防护, '
                             '默认 1800s=30min/情景; natural 30y 约 65s, '
                             'lime 高 Ca/OH 平衡慢实测 >10min)')
    parser.add_argument('--weather-rate', type=float, default=0.0,
                        help='v0.7.0 工单76: 风化注入速率 molc/ha/yr/层 '
                             '(0=关闭, 500=默认; 方向带调优扫描)')
    parser.add_argument('--degrade', nargs='+', default=[],
                        help='v0.7.0 工单76: 从平衡相降级的矿物 '
                             '(如 gibbsite kaolinite; 空=不降级)')
    args = parser.parse_args()

    csv_path = f'output/sensitivity_pH_30yr_{args.tag}.csv'
    png_path = f'output/sensitivity_pH_30yr_{args.tag}.png'

    if args.plot:
        plot(csv_path, png_path)
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

    existing = load_existing(csv_path)
    # v0.6.1: 每个情景独立引擎 (避免降级污染) + 子进程超时护栏
    # v0.7.0 工单76: 接入 companion (D3 伴随淋失, 默认启用) + weathering
    # (D2 风化注入, --weather-rate>0 才启用, 方向带调优)
    from src.config_manager import CompanionConfig, WeatheringConfig
    wth_cfg = None
    if args.weather_rate > 0:
        wth_cfg = WeatheringConfig(enable=True,
                                   rate_molc_ha_yr=args.weather_rate,
                                   degrade_minerals=list(args.degrade))
    engine_cfg = dict(database='phreeqc.dat', mode='phreeqc',
                      initial_psi_cm=-100.0,
                      companion_cfg=CompanionConfig(enable=True),
                      weathering_cfg=wth_cfg)
    reader_paths = ('data/soil_survey.csv', 'data/exchangeable_ions.csv')
    for key in targets:
        rows = existing.get(key, [])
        if len(rows) >= args.years:
            print(f'{key}: 已有完整 {len(rows)} 年数据, 跳过')
            continue
        meta = next(s for s in SCENARIOS if s[0] == key)
        # 每个情景独立引擎 + 独立初始状态/预平衡: 避免 PHREEQC 永久降级
        # (_permanent_fallback 为引擎实例级) 污染后续情景
        engine = PhreeqcEngine(**engine_cfg)
        states0, pco2s, profiles = build_base_states(
            engine, reader, profile, info, pco2, args.pre_steps,
            args.skip_pre)
        print(f'\n=== 运行情景 {key} ({meta[1]}, {args.years} 年, 4 层) ===')
        result = run_scenario_with_timeout(
            reader_paths, engine_cfg, profile, states0, pco2s, profiles,
            key, meta[1], meta[2], meta[3], meta[4],
            args.years, seed=args.seed, timeout=args.timeout)
        if result is None:
            print(f'  {key}: 超时/失败, 跳过 (断点续跑可重试)')
            continue
        years, means, decs, p_ok = result
        new_rows = [{'scenario': key, 'label': meta[1], 'year': y,
                     'L1_pH_mean': f'{mp:.3f}', 'L1_pH_dec': f'{dp:.3f}',
                     'phreeqc_ok': str(ok)}
                    for y, mp, dp, ok in zip(years, means, decs, p_ok)]
        append_rows(csv_path, new_rows)
        existing[key] = rows + new_rows
        print(f'  {key}: L1 pH {means[0]:.3f} -> {means[-1]:.3f} '
              f'(Δ = {means[-1]-means[0]:+.3f})')

    print(f'\n[DONE] 全部目标情景完成, 结果: {csv_path} '
          f'(累计 {sum(len(v) for v in existing.values())} 行)')


if __name__ == '__main__':
    main()

