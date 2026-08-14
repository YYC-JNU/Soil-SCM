# -*- coding: utf-8 -*-
"""实验3: 多层(n_layers=4)下 SURFACE 有无对比 30年 natural
   子图1: 有无 surface 下 4 层土壤 pH 变化
   子图2: 有无 surface 下 4 层土壤 Al/K/Mg/Na/Ca 离子浓度变化
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

reader = InputReader('data/soil_survey.csv', 'data/exchangeable_ions.csv')
profile = reader.build_soil_profile()
db = SoilDatabase(json_path='config/soil_mineral_db.json',
                  tbl_path='config/soil_mineral.tbl')
info = db.get_soil_info('red_soil')
pco2 = db.get_pCO2('red_soil')

def run_surface_sim(enable_surface):
    """运行 4 层 + surface 开关模拟, 返回 (months, layer_ph, layer_ions)"""
    engine = PhreeqcEngine(database='phreeqc.dat', mode='phreeqc',
                           enable_surface=enable_surface)
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
            states, _ = engine.run_monthly_multi_layer(
                states, forcing, action, profile)
        months.append(y + 1)
        for i, s in enumerate(states):
            layer_ph[i].append(s.ph)
            for k in IONS:
                layer_ions[i][k].append(s.solution.get(k, 0.0))
    return months, layer_ph, layer_ions, engine._permanent_fallback

print("=== 实验3: 多层 + SURFACE 有无对比 ===")
months_off, ph_off, ions_off, fb_off = run_surface_sim(False)
print(f"surface=off 完成 (降级={fb_off})")
months_on, ph_on, ions_on, fb_on = run_surface_sim(True)
print(f"surface=on 完成 (降级={fb_on})")

# ---- 绘图: 上下2子图 ----
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 12))
LAYER_STYLES = ['-', '--', '-.', ':']
layer_names = ['Layer 1', 'Layer 2', 'Layer 3', 'Layer 4']

# 子图1: 4层 pH (实线=off, 虚线=on)
for i in range(4):
    ax1.plot(months_off, ph_off[i], LAYER_STYLES[i], lw=1.8, color='k',
             label=f'{layer_names[i]} surface off')
    ax1.plot(months_on, ph_on[i], LAYER_STYLES[i], lw=1.8, color='r',
             label=f'{layer_names[i]} surface on')
ax1.set_xlabel('Time (years)', fontsize=12)
ax1.set_ylabel('pH', fontsize=12)
ax1.grid(True, alpha=0.3)
ax1.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), fontsize=8, ncol=2)
ax1.set_title(f'Exp3: 4-Layer pH — Surface ON/OFF (natural, {N_YEARS} years)',
              fontsize=13)

# 子图2: 4层离子 (实线=off, 虚线=on)
for k in IONS:
    for i in range(4):
        ax2.plot(months_off, ions_off[i][k], LAYER_STYLES[i], lw=1.2,
                 color=ION_COLORS[k],
                 label=f'{k} L{i+1} off' if i == 0 else None)
        ax2.plot(months_on, ions_on[i][k], LAYER_STYLES[i], lw=1.2,
                 color=ION_COLORS[k], ls='--',
                 label=f'{k} L{i+1} on' if i == 0 else None)
ax2.set_xlabel('Time (years)', fontsize=12)
ax2.set_ylabel('Ion concentration (mol/kgw, log)', fontsize=12)
ax2.set_yscale('log')
ax2.grid(True, alpha=0.3, which='both')
handles, labels = ax2.get_legend_handles_labels()
ax2.legend(handles, labels, loc='upper left', bbox_to_anchor=(1.02, 1.0),
           fontsize=7, ncol=2)
ax2.set_title('4-Layer Ion Concentrations — Surface ON/OFF (log scale)',
              fontsize=13)

plt.tight_layout(rect=[0, 0, 0.85, 1])
out = 'output/exp3_surface_onoff.png'
fig.savefig(out, dpi=150, bbox_inches='tight')
print(f"[PLOT] 已保存: {out}")

# 数据摘要
print("\n=== 末年 4 层 pH 对比 ===")
print(f"{'层':<8}{'off pH':<10}{'on pH':<10}")
for i in range(4):
    print(f"{layer_names[i]:<8}{ph_off[i][-1]:<10.3f}{ph_on[i][-1]:<10.3f}")
print("\n=== 末年 4 层离子对比 (off / on, mol/kgw) ===")
for i in range(4):
    print(f"{layer_names[i]}:")
    for k in IONS:
        print(f"  {k:<4} off={ions_off[i][k][-1]:.2e}  on={ions_on[i][k][-1]:.2e}")
