# -*- coding: utf-8 -*-
"""官方 phreeqc 引擎 50 年 fertilizer_lime 化学演化监控
   (原 Q1 before/after 对比脚本已随 phreeqpython 废弃而简化,
    仅保留 official 单引擎路径)
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.input_reader import InputReader
from src.soil_database import SoilDatabase
from src.phreeqc_engine import PhreeqcEngine
from src.climate_forcing import ClimateForcing
from src.scenario_controller import ScenarioController

reader = InputReader('data/soil_survey.csv', 'data/exchangeable_ions.csv')
profile = reader.build_soil_profile()
db = SoilDatabase(json_path='config/soil_mineral_db.json',
                  tbl_path='config/soil_mineral.tbl')
info = db.get_soil_info('red_soil')
pco2 = db.get_pCO2('red_soil')

N_YEARS = 50


def run_sim(n_years=N_YEARS):
    """官方引擎运行 fertilizer_lime 情景"""
    engine = PhreeqcEngine(database='phreeqc.dat', mode='phreeqc')
    state = engine.build_initial_state(profile, info, pco2)
    climate = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05,
                             n_years, 'fertilizer_lime')
    ctrl = ScenarioController(
        'fertilizer_lime',
        {'n': 12.0, 'p2o5': 4.0, 'k2o': 9.0, 'mgo': 3.0, 'znso4': 1.0,
         'apply_months': [3, 6, 9]},
        {'amount_per_apply': 45.0, 'apply_months': [3, 6, 9]})
    rec = {'year': [], 'ph': [], 'bs': [], 'al': [], 'ca': [],
           'falls': 0}
    for y in range(n_years):
        for m in range(12):
            f = climate.get_monthly_forcing(y, m)
            a = ctrl.get_action(y + 1, m + 1)
            state, diag = engine.run_monthly_step(state, f, a, profile)
        ex = state.exchange
        base = (ex.get('CaX2', 0) * 2 + ex.get('MgX2', 0) * 2 +
                ex.get('KX', 0) + ex.get('NaX', 0))
        tot = base + ex.get('AlX3', 0) * 3
        bs = base / tot * 100 if tot > 0 else 0.0
        rec['year'].append(y + 1)
        rec['ph'].append(state.ph)
        rec['bs'].append(bs)
        rec['al'].append(ex.get('AlX3', 0))
        rec['ca'].append(ex.get('CaX2', 0))
        if getattr(engine, '_permanent_fallback', False):
            rec['falls'] += 1
    return rec


print(f"=== 官方引擎模拟 ({N_YEARS}年 fertilizer_lime) ===")
after = run_sim()
print(f"  降级={after['falls']}年, pH {after['ph'][0]:.3f} -> {after['ph'][-1]:.3f}")

# ---- 绘图 (英文标签避免中文字体问题) ----
fig, axes = plt.subplots(2, 2, figsize=(12, 9))
fig.suptitle('Soil-SCM Official Engine: fertilizer_lime, 50 yr',
             fontsize=14)

axes[0, 0].plot(after['year'], after['ph'], 'b-', lw=2)
axes[0, 0].set_xlabel('Year'); axes[0, 0].set_ylabel('Soil pH')
axes[0, 0].set_title('Soil pH Evolution')
axes[0, 0].grid(True, alpha=0.3)

axes[0, 1].plot(after['year'], after['bs'], 'b-', lw=2)
axes[0, 1].set_xlabel('Year')
axes[0, 1].set_ylabel('Base saturation (%)')
axes[0, 1].set_title('Base Saturation Evolution')
axes[0, 1].grid(True, alpha=0.3)

axes[1, 0].plot(after['year'], [x / 1000 for x in after['al']], 'b-', lw=2)
axes[1, 0].set_xlabel('Year')
axes[1, 0].set_ylabel('Exch. Al (10^3 mol)')
axes[1, 0].set_title('Exchangeable Al Evolution')
axes[1, 0].grid(True, alpha=0.3)

axes[1, 1].plot(after['year'], [x / 1000 for x in after['ca']], 'b-', lw=2)
axes[1, 1].set_xlabel('Year')
axes[1, 1].set_ylabel('Exch. Ca (10^3 mol)')
axes[1, 1].set_title('Exchangeable Ca Evolution')
axes[1, 1].grid(True, alpha=0.3)

plt.tight_layout()
fig.savefig('output/official_engine_50yr_evolution.png', dpi=150,
            bbox_inches='tight')
print("\n[PLOT] 已保存: output/official_engine_50yr_evolution.png")

print("\n=== 指标 (首年 -> 末年) ===")
print(f"pH           {after['ph'][0]:.3f} -> {after['ph'][-1]:.3f}")
print(f"盐基饱和度%  {after['bs'][0]:.3f} -> {after['bs'][-1]:.3f}")
print(f"交换性Al(10^3mol) {after['al'][0]/1000:.3f} -> {after['al'][-1]/1000:.3f}")
print(f"交换性Ca(10^3mol) {after['ca'][0]/1000:.3f} -> {after['ca'][-1]/1000:.3f}")
