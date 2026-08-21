"""v0.7.0 工单75: E2 PET 机制判别 (P-E2-1 非单调 pH 的假设 A/B/C)

PET 900→1200 中间点扫描 (1000/1100) + NaX/CaX2 交换时序 + 单层对比
→ 判别 v0.6.0 复盘文档 §2.3 的成因假设:
  假设 A (水循环→盐基淋洗→缓冲切换) / B (AET θ-限制饱和突变) / C (离子强度-交换选择性)
v0.7.0 稳定基线 (companion 默认启用, weathering 默认关)。

输出: output/pet_discrimination_v070.csv (逐月时序) + 控制台判别摘要。

用法:
    python tools/verify_v0_7_0_pet_discrimination.py [--pet 900 1000 1100 1200] [--years 2]
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

BASE_PRECIP = 1893.0
BASE_TEMP = 25.0
PCO2_REF = 0.015
T_REF = 25.0
BETA = 0.05
LATITUDE = 23.1
SEED = 42


def build_base(reader, profile, info, pco2):
    cfg = SimulationConfig(n_layers=4, hydrology_seed=SEED)
    engine = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                           initial_psi_cm=-100.0)
    s0, states, pco2s, profiles = sim_main._build_initial_layer_states(
        engine, reader, profile, info, pco2, cfg)
    # 无预平衡 (与 verify_v0_6_1_numerical 官方口径一致: E1=5.0 为
    # build_initial_state 初始值; main 正式流程 enable_pre_equilibration 另论)
    return engine, states, profiles, pco2s


def run_pet_scan(reader, profile, info, pco2, pet_values, n_years):
    """逐档 PET 扫描, 逐月记录 pH/交换相 NaX/CaX2 时序 (假设 A/B/C 判别)"""
    rows = []
    for annual_pet in pet_values:
        pet_climate = [annual_pet / 12.0] * 12
        engine, states, profiles, pco2s = build_base(reader, profile, info,
                                                     pco2)
        climate = ClimateForcing(BASE_PRECIP, BASE_TEMP, PCO2_REF, T_REF,
                                 BETA, n_years, 'natural', latitude=LATITUDE,
                                 pet_monthly_climate=pet_climate)
        ctrl = ScenarioController('natural', {}, {})
        soil_profile = profiles[0]
        for y in range(n_years):
            for m in range(12):
                f = climate.get_monthly_forcing(y, m)
                a = ctrl.get_action(y + 1, m + 1)
                hydrology, runoff_mm, runoff_extra = sim_main._apply_hydrology_events(
                    states, profiles, f, y, m, SEED, bypass_fraction=0.2)
                states, diags = engine.run_monthly_multi_layer(
                    states, f, a, soil_profile,
                    layer_pco2s=pco2s, hydrology=hydrology)
                ex = states[0].exchange
                rows.append({
                    'pet_annual_mm': annual_pet,
                    'year': y + 1, 'month': m + 1,
                    'aet_mm': hydrology['aet_mm'],
                    'theta_L1': states[0].theta,
                    'ph_L1': states[0].ph,
                    'NaX_L1': ex.get('NaX', 0.0),
                    'CaX2_L1': ex.get('CaX2', 0.0),
                    'MgX2_L1': ex.get('MgX2', 0.0),
                    'Na_soln_L1': states[0].solution.get('Na', 0.0),
                })
        print(f"  PET={annual_pet}mm 完成 (末月 pH L1={rows[-1]['ph_L1']:.2f}, "
              f"NaX={rows[-1]['NaX_L1']:.2e}, CaX2={rows[-1]['CaX2_L1']:.2e})",
              flush=True)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pet', nargs='+', type=int,
                    default=[900, 1000, 1100, 1200])
    ap.add_argument('--years', type=int, default=2)
    args = ap.parse_args()

    reader = InputReader('data/soil_survey.csv', 'data/exchangeable_ions.csv')
    profile = reader.build_soil_profile()
    db = SoilDatabase()
    info = db.get_soil_info('red_soil')
    pco2 = db.get_pCO2('red_soil')

    print(f"=== v0.7.0 工单75: E2 PET 机制判别 (PET {args.pet}, "
          f"{args.years} 年, 事件驱动 4 层) ===", flush=True)
    df = run_pet_scan(reader, profile, info, pco2, args.pet, args.years)

    out = Path('output')
    out.mkdir(exist_ok=True)
    csv_path = out / 'pet_discrimination_v070.csv'
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')

    # ---- 判别摘要 (假设 A/B/C 证据) ----
    last = df[df.year == args.years].groupby('pet_annual_mm').last()
    print("\n--- 判别摘要 (第 %d 年末) ---" % args.years)
    for pet, r in last.iterrows():
        print(f"  PET={pet:4d} | pH_L1={r['ph_L1']:.2f} | NaX={r['NaX_L1']:.2e} "
              f"| CaX2={r['CaX2_L1']:.2e} | Na_soln={r['Na_soln_L1']:.2e} "
              f"| θ_L1={r['theta_L1']:.3f}")
    print(f"\n结果已保存: {csv_path}")
    print("判别分析见 docs/analysis/V0_7_0_PET_DISCRIMINATION.md")


if __name__ == '__main__':
    main()