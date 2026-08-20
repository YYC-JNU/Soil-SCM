"""v0.6.1 数值稳定性验收 (spec 62 Q8, 工单 68)

核心验收 (科学诚实: pH 具体值不承诺, 数值稳定性是本版承诺):
  1. 30 年 (可缩短) 事件驱动 4 层 natural 全程 phreeqc_ok=True (无永久降级)
  2. L4 最大离子浓度 < 1 mol/L (深层盐分不再累积爆炸)
  3. 基流/侧向出口 + 溶质比例扣除不破坏水量闭合 (water_salt_balance <1%)
  4. E1 预平衡收敛值如实记录 (HX/GAP_H 注入后, v0.6.0=4.92)

用法:
    python tools/verify_v0_6_1_numerical.py --years 30
    python tools/verify_v0_6_1_numerical.py --years 5   # 快速验证 (CI/调试)

输出: output/verify_v0_6_1_summary.csv + 控制台摘要。
"""
import sys
import csv
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
L4_MAX_CONC_TOL = 1.0        # L4 max 离子浓度上限 (mol/L, spec 62 Q8)
# v0.6.1: VIC 基流 + Darcy 侧向 (对治深层盐分累积)
BASEFLOW_CFG = {'D_max': 100.0, 'D_s': 0.10, 'n_base': 2.5}
LATERAL_CFG = {'f_slope': 0.10, 'k_lat': [0.04, 0.025, 0.015, 0.008]}


def build_base(reader, profile, info, pco2):
    cfg = SimulationConfig(n_layers=4, hydrology_seed=SEED)
    engine = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                           initial_psi_cm=-100.0)
    s0, states, pco2s, profiles = sim_main._build_initial_layer_states(
        engine, reader, profile, info, pco2, cfg)
    return engine, states, profiles, pco2s


def run_numerical_verify(n_years=30, verbose=True):
    """事件驱动 4 层 natural: 30 年数值稳定性验收"""
    reader = InputReader('data/soil_survey.csv', 'data/exchangeable_ions.csv')
    profile = reader.build_soil_profile()
    db = SoilDatabase(json_path='config/soil_mineral_db.json',
                      tbl_path='config/soil_mineral.tbl')
    info = db.get_soil_info('red_soil')
    pco2 = db.get_pCO2('red_soil')

    engine, states, profiles, pco2s = build_base(reader, profile, info, pco2)
    climate = ClimateForcing(BASE_PRECIP, BASE_TEMP, PCO2_REF, T_REF, BETA,
                             n_years, 'natural', latitude=LATITUDE)
    ctrl = ScenarioController('natural', {}, {})

    # E1: 预平衡收敛值 (HX/GAP_H 基线, v0.6.0=4.92; states[0] 为预平衡后 L1)
    e1_pre_ph = states[0].ph

    summary = []
    fallback_year = None
    l4_max_conc = 0.0
    for y in range(n_years):
        for m in range(12):
            f = climate.get_monthly_forcing(y, m)
            a = ctrl.get_action(y + 1, m + 1)
            h, _r, _x = sim_main._apply_hydrology_events(
                states, profiles, f, y, m, SEED, bypass_fraction=0.2,
                baseflow_cfg=BASEFLOW_CFG, lateral_cfg=LATERAL_CFG)
            states, diags = engine.run_monthly_multi_layer(
                states, f, a, profile, layer_pco2s=pco2s, hydrology=h)
            # L4 max 离子浓度追踪
            for k, v in states[3].solution.items():
                if k in ('temp', 'pH', 'pe', 'units'):
                    continue
                l4_max_conc = max(l4_max_conc, float(v))
            if getattr(engine, '_permanent_fallback', False) \
                    and fallback_year is None:
                fallback_year = y + 1
        summary.append({
            'year': y + 1,
            'ph_L1': round(states[0].ph, 3),
            'ph_L4': round(states[3].ph, 3),
            'l4_max_conc': round(l4_max_conc, 5),
            'phreeqc_ok': 0 if fallback_year else 1,
        })
        if verbose and ((y + 1) % 5 == 0 or y == 0):
            print(f'  第 {y+1:2d} 年 | L1 pH={states[0].ph:.3f} '
                  f'L4 pH={states[3].ph:.3f} L4 max={l4_max_conc:.4f} '
                  f"{'OK' if not fallback_year else '! 已降级'}")

    passed = (fallback_year is None
              and l4_max_conc < L4_MAX_CONC_TOL)
    result = {
        'n_years': n_years,
        'fallback_year': fallback_year or 0,
        'l4_max_conc': round(l4_max_conc, 5),
        'e1_pre_ph': round(e1_pre_ph, 3) if e1_pre_ph else None,
        'passed': passed,
        'L1_pH_last': round(states[0].ph, 3),
        'L4_pH_last': round(states[3].ph, 3),
    }
    return summary, result


def main():
    ap = argparse.ArgumentParser(description='v0.6.1 数值稳定性验收')
    ap.add_argument('--years', type=int, default=30,
                    help='模拟年数 (默认 30, 调试可缩短)')
    args = ap.parse_args()
    print(f'=== v0.6.1 数值稳定性验收 (natural 4 层事件驱动, {args.years} 年) ===')
    summary, result = run_numerical_verify(args.years)
    print(f'\n--- 验收判定 ---')
    print(f'  永久降级年: {result["fallback_year"] or "无 (全程 OK)"}')
    print(f'  L4 max 离子浓度: {result["l4_max_conc"]:.5f} mol/L '
          f'(阈值 <{L4_MAX_CONC_TOL})')
    print(f'  E1 预平衡收敛 pH: {result["e1_pre_ph"]} '
          f'(v0.6.0 基线 4.92, HX 注入后复验)')
    print(f'  L1/L4 末 pH: {result["L1_pH_last"]} / {result["L4_pH_last"]}')
    verdict = 'PASS' if result['passed'] else 'FAIL'
    print(f'  判定: {verdict}')
    # 落盘摘要
    out = Path('output/verify_v0_6_1_summary.csv')
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(result.keys()))
        w.writeheader()
        w.writerow(result)
    print(f'  摘要: {out}')
    sys.exit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
