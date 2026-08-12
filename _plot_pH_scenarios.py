# -*- coding: utf-8 -*-
"""4 情景土壤 pH 演化对比图 (官方 phreeqc 引擎, 50 年)
  情景1: 仅降水(natural)
  情景2: 降水+尿素(fertilizer)
  情景3: 降水+生石灰(lime_only)
  情景4: 降水+尿素+生石灰(fertilizer_lime)
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
from src.scenario_controller import MonthlyAction

reader = InputReader('data/soil_survey.csv', 'data/exchangeable_ions.csv')
profile = reader.build_soil_profile()
db = SoilDatabase(json_path='config/soil_mineral_db.json',
                  tbl_path='config/soil_mineral.tbl')
info = db.get_soil_info('red_soil')
pco2 = db.get_pCO2('red_soil')

N_YEARS = 5


def make_action(scenario, month):
    """构造月度干预指令 (month 为 1-12)"""
    action = MonthlyAction()
    # 氮磷钾镁锌肥: 3/6/9 月各一次 (农业农村部2021指导意见, 每次量 kg/ha)
    if scenario in ('fertilizer', 'fertilizer_lime') and month in (3, 6, 9):
        action.apply_fertilizer = True
        action.n_amount = 12.0
        action.p2o5_amount = 4.0
        action.k2o_amount = 9.0
        action.mgo_amount = 3.0
        action.znso4_amount = 1.0
    # 生石灰 (CaO): 3/6/9 月各一次, 45 kg/ha/次
    if scenario in ('lime_only', 'fertilizer_lime') and month in (3, 6, 9):
        action.apply_lime = True
        action.lime_amount = 45.0
    return action


def run_pH(scenario):
    """运行指定情景, 返回 (年份列表, 逐年pH列表)"""
    engine = PhreeqcEngine(database='phreeqc.dat', mode='phreeqc',
                           backend='official')
    state = engine.build_initial_state(profile, info, pco2)
    # 气候固定为基准 (降水1893mm/年, 均温25C), 差异仅来自干预
    climate = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05,
                             N_YEARS, 'natural')
    phs = []
    for y in range(N_YEARS):
        for m in range(12):
            forcing = climate.get_monthly_forcing(y, m)
            action = make_action(scenario, m + 1)
            state, diag = engine.run_monthly_step(state, forcing, action,
                                                  profile)
        phs.append(state.ph)
    print(f"  {scenario}: pH {phs[0]:.3f} -> {phs[-1]:.3f}")
    return list(range(1, N_YEARS + 1)), phs


SCENARIOS = [
    ('natural', 'Scenario 1: Rainfall only', '#1f77b4', '-'),
    ('fertilizer', 'Scenario 2: Rainfall + Urea', '#d62728', '--'),
    ('lime_only', 'Scenario 3: Rainfall + Quicklime', '#2ca02c', '-.'),
    ('fertilizer_lime', 'Scenario 4: Rainfall + Urea + Quicklime', '#9467bd', ':'),
]

print(f"=== 4 情景 pH 模拟 ({N_YEARS} 年, 官方 phreeqc 引擎) ===")
results = {}
for key, label, color, ls in SCENARIOS:
    years, phs = run_pH(key)
    results[key] = (years, phs)

# ---- 绘图 ----
fig, ax = plt.subplots(figsize=(11, 8))
for key, label, color, ls in SCENARIOS:
    years, phs = results[key]
    ax.plot(years, phs, color=color, linestyle=ls, lw=2,
            label=label)

ax.set_xlabel('Year', fontsize=12)
ax.set_ylabel('Soil pH', fontsize=12)
ax.set_title(f'Soil pH Evolution under 4 Scenarios ({N_YEARS} years)',
             fontsize=14)
ax.legend(loc='best', fontsize=10)
ax.grid(True, alpha=0.3)
ax.set_ylim(bottom=2.5)

# 模型局限说明 (natural 的 Al 淋洗脱酸现象)
ax.annotate(
    'Model limitation note:\n'
    'Scenario 1 (rainfall only) rises to alkaline pH because exchangeable\n'
    'Al is leached/mineralized in the single-layer model (no vertical\n'
    'Al accumulation). Real red-soil leaching should acidify (base loss).',
    xy=(0.5, 0.02), xycoords='axes fraction', ha='center',
    fontsize=9, color='dimgray',
    bbox=dict(boxstyle='round,pad=0.4', facecolor='lightyellow',
              alpha=0.8))

plt.tight_layout()
out = 'output/pH_4scenarios.png'
fig.savefig(out, dpi=150, bbox_inches='tight')
print(f"\n[PLOT] 已保存: {out}")

print("\n=== 各情景关键年份 pH ===")
print(f"{'情景':<32}{'第1年':<8}{'中期':<8}{'末年':<8}")
for key, label, *_ in SCENARIOS:
    years, phs = results[key]
    n = len(phs)
    idx = sorted(set([0, n // 2, n - 1]))
    vals = ' '.join(f"{phs[i]:<8.3f}" for i in idx)
    print(f"{label:<32}{vals}")
