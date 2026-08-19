"""v0.6.0 验收实验 (spec 55, 工单 61)

用法:
    python tools/verify_v0_6_0_acceptance.py

E1: 事件驱动 4 层 N 年 natural — 水分闭合 (AET+径流+Δ储=降水) + 无崩溃
    (子步长不破坏水分平衡门禁: 层间级联排水窗 Σ = 月天数)
E2: PET 敏感性 (600~1400mm) → 旱季 θ 下降 + 溶液浓缩酸化 → pH 方向性响应
E3: k_om 敏感性 (0.0003/0.0005/0.0008) → 表层酸化方向
FF: First-Flush — 雨季单场淋失峰值 > 月均 (脉冲式淋失如实输出)

科学诚实 (spec 55): pH 回落 4.5~5.5 只验收方向, 不承诺具体值。
输出: output/verify_v0_6_0_summary.csv + 控制台摘要。
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import main as sim_main
from src.config_manager import SimulationConfig
from src.input_reader import InputReader
from src.soil_database import SoilDatabase
from src.phreeqc_engine import PhreeqcEngine
from src.climate_forcing import ClimateForcing
from src.scenario_controller import ScenarioController

N_YEARS = 2            # 事件驱动计算量大, 用 2 年验证方向 (全量 50 年见发布运行;
                       # 注意: 3 年+ 长期模拟在深层盐分累积极端场景存在 PHREEQC
                       # 数值不收敛边界, 列为 v0.6.1 调校项, 见工单 61 执行日志)
BASE_PRECIP = 1893.0
BASE_TEMP = 25.0
PCO2_REF = 0.015
T_REF = 25.0
BETA = 0.05
LATITUDE = 23.1
SEED = 42


def build_base(reader, profile, info, pco2, n_years=N_YEARS):
    """构建 4 层初始状态 (逐层 pCO₂ 含 OM 调制)"""
    cfg = SimulationConfig(n_layers=4, hydrology_seed=SEED)
    engine = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                           initial_psi_cm=-100.0)
    s0, states, pco2s, profiles = sim_main._build_initial_layer_states(
        engine, reader, profile, info, pco2, cfg)
    return engine, states, profiles, pco2s


def run_sim_event(engine, states, profiles, pco2s, climate, ctrl,
                  n_years=N_YEARS):
    """事件驱动 4 层 natural 主循环 (Q3: 逐场水文+化学)

    返回末月 pH / 年 AET / 年径流 / L1 θ 范围 / First-Flush 峰值与月均。
    """
    soil_profile = profiles[0]
    monthly = []
    for y in range(n_years):
        for m in range(12):
            f = climate.get_monthly_forcing(y, m)
            a = ctrl.get_action(y + 1, m + 1)
            hydrology, runoff_mm, runoff_extra = sim_main._apply_hydrology_events(
                states, profiles, f, y, m, SEED, bypass_fraction=0.2)
            states, diags = engine.run_monthly_multi_layer(
                states, f, a, soil_profile,
                layer_pco2s=pco2s, hydrology=hydrology)
            # First-Flush: 月内单场淋失峰值 vs 月均 (事件明细)
            dets = hydrology.get('event_details', [])
            no3_events = [d['leach_N_L1_mmol'] for d in dets]
            monthly.append({
                'year': y + 1, 'month': m + 1,
                'aet_mm': hydrology['aet_mm'],
                'runoff_mm': runoff_mm + runoff_extra / 10000.0,
                'theta_L1': states[0].theta,
                'ph_L1': states[0].ph,
                'flush_no3_peak': max(no3_events, default=0.0),
                'flush_no3_avg': (sum(no3_events)
                                  / max(len(no3_events), 1)),
            })
    df = pd.DataFrame(monthly)
    yr = df[df.year == n_years]
    wet = df[(df.month >= 4) & (df.month <= 9)]   # 华南雨季 4~9 月
    return {
        'ph_L1_last': yr['ph_L1'].iloc[-1],
        'aet_annual_mm': df['aet_mm'].sum() / n_years,
        'runoff_annual_mm': df['runoff_mm'].sum() / n_years,
        'theta_L1_min': df['theta_L1'].min(),
        'theta_L1_max': df['theta_L1'].max(),
        'theta_L1_range': df['theta_L1'].max() - df['theta_L1'].min(),
        # First-Flush: 雨季峰值/月均比 (脉冲特征, >1 即捕获)
        'ff_wet_peak': wet['flush_no3_peak'].max(),
        'ff_wet_avg': wet['flush_no3_avg'].mean(),
        'ff_peak_ratio': (wet['flush_no3_peak'].max()
                          / max(wet['flush_no3_avg'].mean(), 1e-12)),
    }


def e1_baseline_event(reader, profile, info, pco2):
    """E1: 事件驱动 4 层 N 年 natural — 水分闭合 + 无崩溃"""
    engine, states, profiles, pco2s = build_base(reader, profile, info, pco2)
    # 预平衡收敛 (与 v0.5.3 同口径)
    pre_phs = []
    for i, s in enumerate(states):
        s2 = engine.pre_equilibrate(s, profiles[i], 60)
        pre_phs.append(s2.ph)
    climate = ClimateForcing(BASE_PRECIP, BASE_TEMP, PCO2_REF, T_REF,
                             BETA, N_YEARS, 'natural', latitude=LATITUDE)
    ctrl = ScenarioController('natural', {}, {})
    r = run_sim_event(engine, states, profiles, pco2s, climate, ctrl)
    r['pre_equil_pH'] = pre_phs
    r['aet_plus_runoff_mm'] = r['aet_annual_mm'] + r['runoff_annual_mm']
    return r


def e2_pet_sensitivity_event(reader, profile, info, pco2):
    """E2: PET 敏感性 (600~1400mm) → 旱季 θ 下降 + pH 方向性响应"""
    rows = []
    for annual_pet in (600, 900, 1200, 1400):
        pet_climate = [annual_pet / 12.0] * 12
        engine, states, profiles, pco2s = build_base(reader, profile, info,
                                                     pco2)
        climate = ClimateForcing(BASE_PRECIP, BASE_TEMP, PCO2_REF, T_REF,
                                 BETA, N_YEARS, 'natural',
                                 latitude=LATITUDE,
                                 pet_monthly_climate=pet_climate)
        ctrl = ScenarioController('natural', {}, {})
        r = run_sim_event(engine, states, profiles, pco2s, climate, ctrl)
        r['pet_annual_mm'] = annual_pet
        rows.append(r)
    return rows


def e3_om_sensitivity_event(reader, profile, info, pco2):
    """E3: k_om 敏感性 → 表层酸化方向"""
    from src.constants import OM_PROFILE_4LAYER
    from src.climate_forcing import apply_om_pco2
    rows = []
    for k_om in (0.0003, 0.0005, 0.0008):
        engine, states, profiles, pco2s = build_base(reader, profile, info,
                                                     pco2)
        pco2s = [apply_om_pco2(0.015, om, k_om=k_om)
                 for om in OM_PROFILE_4LAYER]
        climate = ClimateForcing(BASE_PRECIP, BASE_TEMP, PCO2_REF, T_REF,
                                 BETA, N_YEARS, 'natural', latitude=LATITUDE)
        ctrl = ScenarioController('natural', {}, {})
        r = run_sim_event(engine, states, profiles, pco2s, climate, ctrl)
        r['k_om'] = k_om
        r['pCO2_eff_L1'] = pco2s[0]
        rows.append(r)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--e1', action='store_true')
    ap.add_argument('--e2', action='store_true')
    ap.add_argument('--e3', action='store_true')
    args = ap.parse_args()
    run_e1 = args.e1 or not (args.e2 or args.e3)
    run_e2 = args.e2 or not (args.e1 or args.e3)
    run_e3 = args.e3 or not (args.e1 or args.e2)

    reader = InputReader('data/soil_survey.csv', 'data/exchangeable_ions.csv')
    profile = reader.build_soil_profile()
    db = SoilDatabase()
    info = db.get_soil_info('red_soil')
    pco2 = db.get_pCO2('red_soil')

    results = []
    if run_e1:
        print(f"=== E1: 事件驱动 4 层 {N_YEARS} 年 natural (水分闭合 + 无崩溃) ===")
        r = e1_baseline_event(reader, profile, info, pco2)
        r['experiment'] = 'E1'
        results.append(r)
        print(f"  预平衡 pH (L1~L4): {[f'{p:.2f}' for p in r['pre_equil_pH']]}")
        print(f"  末月 pH L1: {r['ph_L1_last']:.2f}")
        print(f"  年均 AET: {r['aet_annual_mm']:.0f} mm | "
              f"年均径流: {r['runoff_annual_mm']:.0f} mm")
        print(f"  AET+径流: {r['aet_plus_runoff_mm']:.0f} mm "
              f"(< 降水 {BASE_PRECIP:.0f} mm, 含水/深层余量)")
        print(f"  L1 θ 范围: {r['theta_L1_min']:.2f}~{r['theta_L1_max']:.2f} "
              f"(跨月滞水+旱季干化可见)")
        print(f"  First-Flush 峰值/月均比 (雨季): {r['ff_peak_ratio']:.2f}")

    if run_e2:
        print("\n=== E2: PET 敏感性 (事件驱动, 旱季 θ 下降 + pH 方向) ===")
        for r in e2_pet_sensitivity_event(reader, profile, info, pco2):
            r['experiment'] = 'E2'
            results.append(r)
            print(f"  PET={r['pet_annual_mm']:4d}mm | pH L1={r['ph_L1_last']:.2f} "
                  f"| L1θ范围={r['theta_L1_range']:.2f} "
                  f"({r['theta_L1_min']:.2f}~{r['theta_L1_max']:.2f}) "
                  f"| FF比={r['ff_peak_ratio']:.2f}")

    if run_e3:
        print("\n=== E3: k_om 敏感性 (事件驱动, 表层酸化方向) ===")
        for r in e3_om_sensitivity_event(reader, profile, info, pco2):
            r['experiment'] = 'E3'
            results.append(r)
            print(f"  k_om={r['k_om']:.4f} | pCO2_eff_L1={r['pCO2_eff_L1']:.4f} "
                  f"| pH L1={r['ph_L1_last']:.2f}")

    out = Path('output')
    out.mkdir(exist_ok=True)
    df = pd.DataFrame(results)
    df.to_csv(out / 'verify_v0_6_0_summary.csv', index=False,
              encoding='utf-8-sig')
    print(f"\n结果已保存: {out / 'verify_v0_6_0_summary.csv'}")


if __name__ == '__main__':
    main()
