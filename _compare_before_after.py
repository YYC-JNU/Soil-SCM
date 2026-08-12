# -*- coding: utf-8 -*-
"""Q1 前后对比实验: phreeqpython(修改前) vs 官方phreeqc(修改后)"""
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


def run_sim(backend, n_years=N_YEARS):
    engine = PhreeqcEngine(database='phreeqc.dat', mode='phreeqc',
                           backend=backend)
    state = engine.build_initial_state(profile, info, pco2)
    climate = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05,
                             n_years, 'fertilizer_lime')
    ctrl = ScenarioController(
        'fertilizer_lime',
        {'type': 'urea', 'annual_amount': 300.0, 'apply_months': [3, 6, 9]},
        {'annual_amount': 1000.0, 'apply_month': 1})
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


# 正式 50 年对比
print(f"=== 对比实验 ({N_YEARS}年 fertilizer_lime) ===")
before = run_sim('phreeqpython')
after = run_sim('official')
print(f"  修改前(phreeqpython): 降级={before['falls']}年, "
      f"pH {before['ph'][0]:.3f} -> {before['ph'][-1]:.3f}")
print(f"  修改后(official):     降级={after['falls']}年, "
      f"pH {after['ph'][0]:.3f} -> {after['ph'][-1]:.3f}")

# ---- 绘图 (英文标签避免中文字体问题) ----
fig, axes = plt.subplots(2, 2, figsize=(12, 9))
fig.suptitle('Soil-SCM Q1 Fix: Before vs After (fertilizer_lime, 50 yr)',
             fontsize=14)

axes[0, 0].plot(before['year'], before['ph'], 'r--', lw=1.5,
                label='Before (phreeqpython)')
axes[0, 0].plot(after['year'], after['ph'], 'b-', lw=2,
                label='After (official phreeqc)')
axes[0, 0].set_xlabel('Year'); axes[0, 0].set_ylabel('Soil pH')
axes[0, 0].set_title('Soil pH Evolution')
axes[0, 0].legend(); axes[0, 0].grid(True, alpha=0.3)

axes[0, 1].plot(before['year'], before['bs'], 'r--', lw=1.5,
                label='Before')
axes[0, 1].plot(after['year'], after['bs'], 'b-', lw=2, label='After')
axes[0, 1].set_xlabel('Year')
axes[0, 1].set_ylabel('Base saturation (%)')
axes[0, 1].set_title('Base Saturation Evolution')
axes[0, 1].legend(); axes[0, 1].grid(True, alpha=0.3)

axes[1, 0].plot(before['year'], [x / 1000 for x in before['al']],
                'r--', lw=1.5, label='Before')
axes[1, 0].plot(after['year'], [x / 1000 for x in after['al']],
                'b-', lw=2, label='After')
axes[1, 0].set_xlabel('Year')
axes[1, 0].set_ylabel('Exch. Al (10^3 mol)')
axes[1, 0].set_title('Exchangeable Al Evolution')
axes[1, 0].legend(); axes[1, 0].grid(True, alpha=0.3)

axes[1, 1].plot(before['year'], [x / 1000 for x in before['ca']],
                'r--', lw=1.5, label='Before')
axes[1, 1].plot(after['year'], [x / 1000 for x in after['ca']],
                'b-', lw=2, label='After')
axes[1, 1].set_xlabel('Year')
axes[1, 1].set_ylabel('Exch. Ca (10^3 mol)')
axes[1, 1].set_title('Exchangeable Ca Evolution')
axes[1, 1].legend(); axes[1, 1].grid(True, alpha=0.3)

plt.tight_layout()
fig.savefig('output/Q1_before_after_comparison.png', dpi=150,
            bbox_inches='tight')
print("\n[PLOT] 已保存: output/Q1_before_after_comparison.png")

# 数据对比表
print("\n=== 指标对比 (首年 -> 末年) ===")
print(f"{'指标':<18}{'修改前':<22}{'修改后':<22}")
for name, key, scale in [
        ('pH', 'ph', 1),
        ('盐基饱和度(%)', 'bs', 1),
        ('交换性Al(10^3mol)', 'al', 1000),
        ('交换性Ca(10^3mol)', 'ca', 1000)]:
    b = f"{before[key][0]/scale:.3f} -> {before[key][-1]/scale:.3f}"
    a = f"{after[key][0]/scale:.3f} -> {after[key][-1]/scale:.3f}"
    print(f"{name:<18}{b:<22}{a:<22}")

