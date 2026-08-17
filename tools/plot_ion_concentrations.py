# -*- coding: utf-8 -*-
"""模拟过程中 PHREEQC 输出的所有离子浓度与 pH 变化曲线
  情景: fertilizer_lime (降水+尿素+生石灰), 5 年
  数据: 每月 run 后从 state.solution 读取 pH + 10 种离子浓度 (mol/kgw)
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

N_YEARS = 30
# 注: Zn 浓度过低(红壤强固定, ~1e-20)不再绘制
IONS = ['Ca', 'Mg', 'K', 'Na', 'Al', 'P', 'Cl', 'C', 'S', 'N', 'Si']
COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
          '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
          '#aec7e8']

print(f"=== 离子浓度与 pH 模拟 ({N_YEARS} 年, fertilizer_lime) ===")
engine = PhreeqcEngine(database='phreeqc.dat', mode='phreeqc',
                       backend='official')
state = engine.build_initial_state(profile, info, pco2)
climate = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05,
                         N_YEARS, 'natural')
ctrl = ScenarioController(
    'fertilizer_lime',
    {'n': 12.0, 'p2o5': 4.0, 'k2o': 9.0, 'mgo': 3.0, 'znso4': 1.0,
     'apply_months': [3, 6, 9]},
    {'amount_per_apply': 45.0, 'apply_months': [3, 6, 9]})

months = []
ph_list = []
ion_data = {k: [] for k in IONS}

for y in range(N_YEARS):
    for m in range(12):
        forcing = climate.get_monthly_forcing(y, m)
        action = ctrl.get_action(y + 1, m + 1)
        state, diag = engine.run_monthly_step(state, forcing, action,
                                              profile)
        months.append(y + 1 + (m + 1) / 12.0)
        ph_list.append(state.ph)
        sol = state.solution
        for k in IONS:
            ion_data[k].append(sol.get(k, 0.0))

# ---- 绘图: 单图双轴 ----
fig, ax1 = plt.subplots(figsize=(13, 7))

# 左轴: pH
ax1.plot(months, ph_list, 'k-', lw=2.5, label='pH')
ax1.set_xlabel('Time (years)', fontsize=12)
ax1.set_ylabel('pH', fontsize=12, color='k')
ax1.tick_params(axis='y', labelcolor='k')
ax1.grid(True, alpha=0.3)

# 右轴: 离子浓度 (对数)
ax2 = ax1.twinx()
for k, c in zip(IONS, COLORS):
    ax2.plot(months, ion_data[k], '--', lw=1.5, color=c,
             label=f'{k} (mol/kgw)')
ax2.set_ylabel('Ion concentration (mol/kgw, log scale)', fontsize=12)
ax2.set_yscale('log')
ax2.tick_params(axis='y')

# 图例放在图外右侧 (bbox_to_anchor), 不遮挡曲线
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2,
           loc='upper left', bbox_to_anchor=(1.02, 1.0),
           fontsize=8, ncol=2, framealpha=0.9)

ax1.set_title('PHREEQC Output: pH and Ion Concentrations '
              '(fertilizer_lime, 30 years)', fontsize=13)

# 预留右侧空间给图例
plt.tight_layout(rect=[0, 0, 0.82, 1])
out = 'output/pH_ions.png'
fig.savefig(out, dpi=150, bbox_inches='tight')
print(f"[PLOT] 已保存: {out}")

# 输出首/末年关键数据
print("\n=== 首/末年离子浓度 (mol/kgw) ===")
print(f"{'离子':<6}{'第1月':<14}{'末月':<14}{'变化趋势'}")
for k in IONS:
    a, b = ion_data[k][0], ion_data[k][-1]
    trend = '↑' if b > a * 1.1 else ('↓' if b < a * 0.9 else '→')
    print(f"{k:<6}{a:<14.3e}{b:<14.3e}{trend}")
print(f"pH     {ph_list[0]:<14.3f}{ph_list[-1]:<14.3f}")
