# -*- coding: utf-8 -*-
"""实验 v0.5.0: 4 层 natural 水文盒子 vs 旧 precip_infiltration 基线对比

   验证水文模式对基线的影响 (科学诚实记录基线漂移):
     - 旧: 各层默认相同 + precip_infiltration=0.05 (年入渗 ~95mm)
     - 新: 4 层内置物理剖面默认 + Horton 入渗(0.75上限) + Ksat/持水/滞水

   输出: 逐年表层 pH / 各层 AlX3 / 月入渗量对比 (stdout)

   用法: python tools/plot_v0_5_hydrology_baseline.py [--years 3]
"""
import sys
import argparse
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
import main as sim_main
from src.input_reader import InputReader
from src.soil_database import SoilDatabase
from src.config_manager import SimulationConfig
from src.phreeqc_engine import PhreeqcEngine
from src.climate_forcing import ClimateForcing
from src.scenario_controller import ScenarioController


def run_old(engine, profile, info, pco2, n_years, n=4):
    """旧路径: 各层默认相同, precip_infiltration 排水"""
    states = [engine.build_initial_state(profile, info, pco2) for _ in range(n)]
    climate = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05, n_years, 'natural')
    ctrl = ScenarioController('natural', {}, {})
    phs, alx3s = [], []
    for y in range(n_years):
        for m in range(12):
            f = climate.get_monthly_forcing(y, m)
            a = ctrl.get_action(y + 1, m + 1)
            states, _ = engine.run_monthly_multi_layer(states, f, a, profile)
        phs.append([s.ph for s in states])
        alx3s.append([s.exchange.get('AlX3', 0) for s in states])
    return phs, alx3s


def run_new(engine, reader, profile, info, pco2, n_years, n=4):
    """v0.5.0 水文路径: 4 层内置默认 + Horton/Ksat/持水/滞水"""
    cfg = SimulationConfig(n_layers=n)
    _, states, pco2s, profiles = sim_main._build_initial_layer_states(
        engine, reader, profile, info, pco2, cfg)
    climate = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05, n_years, 'natural')
    ctrl = ScenarioController('natural', {}, {})
    phs, alx3s, inf_mms = [], [], []
    for y in range(n_years):
        for m in range(12):
            f = climate.get_monthly_forcing(y, m)
            a = ctrl.get_action(y + 1, m + 1)
            h, runoff, extra = sim_main._apply_hydrology_month(
                states, profiles, f, y, m, seed=42)
            inf_mms.append(h['inflows'][0] / 10000.0)
            states, _ = engine.run_monthly_multi_layer(
                states, f, a, profile, layer_pco2s=pco2s, hydrology=h)
        phs.append([s.ph for s in states])
        alx3s.append([s.exchange.get('AlX3', 0) for s in states])
    return phs, alx3s, inf_mms


def main():
    parser = argparse.ArgumentParser(description='v0.5.0 水文基线对比')
    parser.add_argument('--years', type=int, default=3)
    args = parser.parse_args()

    reader = InputReader('data/soil_survey.csv', 'data/exchangeable_ions.csv')
    profile = reader.build_soil_profile()
    db = SoilDatabase(json_path='config/soil_mineral_db.json',
                      tbl_path='config/soil_mineral.tbl')
    info = db.get_soil_info('red_soil')
    pco2 = db.get_pCO2('red_soil')
    engine = PhreeqcEngine(database='phreeqc.dat', mode='phreeqc')

    print(f"=== v0.5.0 水文基线对比 (natural, {args.years} 年, 4 层) ===")
    print("运行旧路径 (precip_infiltration=0.05)...")
    phs_o, alx3_o = run_old(engine, profile, info, pco2, args.years)
    print("运行 v0.5.0 水文路径 (Horton 0.75 + Ksat + 持水)...")
    phs_n, alx3_n, inf_mms = run_new(
        engine, reader, profile, info, pco2, args.years)

    print("\n=== 表层 pH 对比 (逐年) ===")
    print(f"{'年':<4}{'旧基线':<10}{'水文模式':<10}{'Δ'}")
    for y in range(args.years):
        print(f"{y+1:<4}{phs_o[y][0]:<10.3f}{phs_n[y][0]:<10.3f}"
              f"{phs_n[y][0]-phs_o[y][0]:+.3f}")

    print("\n=== 各层 AlX3 (末年末值, mol) ===")
    print(f"{'层':<4}{'旧基线':<14}{'水文模式':<14}")
    for i in range(4):
        print(f"L{i+1:<3}{alx3_o[-1][i]:<14.1f}{alx3_n[-1][i]:<14.1f}")

    print("\n=== 月入渗量 (水文模式, mm) ===")
    print(f"  平均 {sum(inf_mms)/len(inf_mms):.1f} mm/月 "
          f"(旧模式对比: {1893.0*0.05/12:.1f} mm/月, 约 5% 入渗)")
    print(f"  首年累计入渗 {sum(inf_mms[:12]):.0f} mm vs 旧模式 {1893.0*0.05:.0f} mm/年")


if __name__ == '__main__':
    main()
