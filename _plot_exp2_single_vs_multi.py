# -*- coding: utf-8 -*-
"""实验2: 单层 vs 多层 (表层对比) 30年 natural 模拟
   子图1: 表层土壤 pH 对比 (单层 vs 多层第1层)
   子图2: 表层土壤 Al/K/Mg/Na/Ca 离子浓度对比
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

N_YEARS = 30
IONS = ['Al', 'K', 'Mg', 'Na', 'Ca']
ION_COLORS = {'Al': '#9467bd', 'K': '#2ca02c', 'Mg': '#1f77b4',
              'Na': '#ff7f0e', 'Ca': '#d62728'}
STYLES = {'single': '-', 'multi': '--'}

reader = InputReader('data/soil_survey.csv', 'data/exchangeable_ions.csv')
profile = reader.build_soil_profile()
db = SoilDatabase(json_path='config/soil_mineral_db.json',
                  tbl_path='config/soil_mineral.tbl')
info = db.get_soil_info('red_soil')
pco2 = db.get_pCO2('red_soil')

def run_simulation(n_layers):
    """运行 n_layers 层模拟, 返回 (months, surface_ph, surface_ions)"""
    engine = PhreeqcEngine(database='phreeqc.dat', mode='phreeqc')
    if n_layers == 1:
        state = engine.build_initial_state(profile, info, pco2)
    else:
        states = [engine.build_initial_state(profile, info, pco2)
                  for _ in range(n_layers)]
    climate = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05, N_YEARS, 'natural')
    ctrl = ScenarioController('natural', {}, {})
    months, ph, ions = [], [], {k: [] for k in IONS}
    for y in range(N_YEARS):
        for m in range(12):
            forcing = climate.get_monthly_forcing(y, m)
            action = ctrl.get_action(y + 1, m + 1)
            if n_layers == 1:
                state, _ = engine.run_monthly_step(state, forcing, action, profile)
                surf_state = state
            else:
                states, _ = engine.run_monthly_multi_layer(
                    states, forcing, action, profile)
                surf_state = states[0]  # 表层 = 第1层
        months.append(y + 1)
        ph.append(surf_state.ph)
        for k in IONS:
            ions[k].append(surf_state.solution.get(k, 0.0))
    return months, ph, ions

print("=== 实验2: 单层 vs 多层 表层对比 ===")
months_s, ph_s, ions_s = run_simulation(1)
print("单层完成")
months_m, ph_m, ions_m = run_simulation(4)
print("多层完成")

# ---- 绘图: 上下2子图 ----
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 12))

# 子图1: 表层 pH 对比
ax1.plot(months_s, ph_s, STYLES['single'], lw=2.2, color='k',
         label='Single-layer (surface)')
ax1.plot(months_m, ph_m, STYLES['multi'], lw=2.2, color='b',
         label='Multi-layer (layer 1)')
ax1.set_xlabel('Time (years)', fontsize=12)
ax1.set_ylabel('pH', fontsize=12)
ax1.grid(True, alpha=0.3)
ax1.legend(loc='best', fontsize=10)
ax1.set_title(f'Exp2: Surface pH — Single vs Multi Layer (natural, {N_YEARS} years)',
              fontsize=13)

# 子图2: 表层离子对比 (实线=单层, 虚线=多层)
for k in IONS:
    ax2.plot(months_s, ions_s[k], STYLES['single'], lw=1.4,
             color=ION_COLORS[k], label=f'{k} single')
    ax2.plot(months_m, ions_m[k], STYLES['multi'], lw=1.4,
             color=ION_COLORS[k], label=f'{k} multi')
ax2.set_xlabel('Time (years)', fontsize=12)
ax2.set_ylabel('Ion concentration (mol/kgw, log)', fontsize=12)
ax2.set_yscale('log')
ax2.grid(True, alpha=0.3, which='both')
handles, labels = ax2.get_legend_handles_labels()
ax2.legend(handles, labels, loc='upper left', bbox_to_anchor=(1.02, 1.0),
           fontsize=8, ncol=2)
ax2.set_title('Surface Ion Concentrations (Al/K/Mg/Na/Ca, log scale)',
              fontsize=13)

plt.tight_layout(rect=[0, 0, 0.85, 1])
out = 'output/exp2_single_vs_multi.png'
fig.savefig(out, dpi=150, bbox_inches='tight')
print(f"[PLOT] 已保存: {out}")

# 数据摘要
print("\n=== 表层末年 pH / 离子对比 ===")
print(f"{'模式':<8}{'pH':<8}" + ''.join(f'{k:<10}' for k in IONS))
print(f"{'single':<8}{ph_s[-1]:<8.3f}" +
      ''.join(f"{ions_s[k][-1]:<10.2e}" for k in IONS))
print(f"{'multi':<8}{ph_m[-1]:<8.3f}" +
      ''.join(f"{ions_m[k][-1]:<10.2e}" for k in IONS))
print(f"\npH 差异: 单层={ph_s[-1]:.2f}, 多层={ph_m[-1]:.2f}")
