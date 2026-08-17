# -*- coding: utf-8 -*-
"""实验1: 完整模式 (n_layers=4) 30年 natural 模拟
   子图1: 4层土壤pH变化
   子图2: 4层土壤 Al/K/Mg/Na/Ca 离子浓度变化
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
LAYER_STYLES = ['-', '--', '-.', ':']

reader = InputReader('data/soil_survey.csv', 'data/exchangeable_ions.csv')
profile = reader.build_soil_profile()
db = SoilDatabase(json_path='config/soil_mineral_db.json',
                  tbl_path='config/soil_mineral.tbl')
info = db.get_soil_info('red_soil')
pco2 = db.get_pCO2('red_soil')

print(f"=== 实验1: 4层30年 natural (n_layers=4, surface=off) ===")
engine = PhreeqcEngine(database='phreeqc.dat', mode='phreeqc')
states = [engine.build_initial_state(profile, info, pco2) for _ in range(4)]
climate = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05, N_YEARS, 'natural')
ctrl = ScenarioController('natural', {}, {})

months = []
layer_ph = {i: [] for i in range(4)}
layer_ions = {i: {k: [] for k in IONS} for i in range(4)}

for y in range(N_YEARS):
    for m in range(12):
        forcing = climate.get_monthly_forcing(y, m)
        action = ctrl.get_action(y + 1, m + 1)
        states, _ = engine.run_monthly_multi_layer(states, forcing, action, profile)
    months.append(y + 1)
    for i, s in enumerate(states):
        layer_ph[i].append(s.ph)
        for k in IONS:
            layer_ions[i][k].append(s.solution.get(k, 0.0))

print(f"模拟完成: {N_YEARS} 年, 降级={engine._permanent_fallback}")

# ---- 绘图: 上下2子图 ----
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 12))

# 子图1: 4层 pH
for i in range(4):
    ax1.plot(months, layer_ph[i], LAYER_STYLES[i], lw=2,
             color='k', label=f'Layer {i+1}')
ax1.set_xlabel('Time (years)', fontsize=12)
ax1.set_ylabel('pH', fontsize=12)
ax1.grid(True, alpha=0.3)
ax1.legend(loc='best', fontsize=9)
ax1.set_title(f'Exp1: 4-Layer Soil pH (natural, {N_YEARS} years)', fontsize=13)

# 子图2: 4层 5离子 (对数)
for k in IONS:
    for i in range(4):
        ax2.plot(months, layer_ions[i][k], LAYER_STYLES[i],
                 lw=1.3, color=ION_COLORS[k],
                 label=f'{k} L{i+1}' if i == 0 else None)
ax2.set_xlabel('Time (years)', fontsize=12)
ax2.set_ylabel('Ion concentration (mol/kgw, log)', fontsize=12)
ax2.set_yscale('log')
ax2.grid(True, alpha=0.3, which='both')
handles, labels = ax2.get_legend_handles_labels()
ax2.legend(handles, labels, loc='upper left', bbox_to_anchor=(1.02, 1.0),
           fontsize=8, ncol=2)
ax2.set_title(f'4-Layer Ion Concentrations (Al/K/Mg/Na/Ca, log scale)',
              fontsize=13)

plt.tight_layout(rect=[0, 0, 0.85, 1])
out = 'output/exp1_4layer_30yr.png'
fig.savefig(out, dpi=150, bbox_inches='tight')
print(f"[PLOT] 已保存: {out}")

# 数据摘要
print("\n=== 末年各层 pH / 离子浓度 (mol/kgw) ===")
print(f"{'层':<4}{'pH':<8}" + ''.join(f'{k:<10}' for k in IONS))
for i in range(4):
    row = f"L{i+1:<3}{layer_ph[i][-1]:<8.3f}"
    for k in IONS:
        row += f"{layer_ions[i][k][-1]:<10.2e}"
    print(row)
