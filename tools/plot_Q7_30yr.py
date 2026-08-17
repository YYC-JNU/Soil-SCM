# -*- coding: utf-8 -*-
"""Q7 降水化学集成 + F1 pCO2 传递后 30 年模拟: pH 与全部离子浓度曲线
   情景: natural (仅降水), 官方 phreeqc 引擎
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from src.input_reader import InputReader
from src.soil_database import SoilDatabase
from src.phreeqc_engine import PhreeqcEngine
from src.climate_forcing import ClimateForcing
from src.scenario_controller import ScenarioController
from src.precip_chemistry import PrecipChemistry

reader = InputReader("data/soil_survey.csv", "data/exchangeable_ions.csv")
profile = reader.build_soil_profile()
db = SoilDatabase(json_path="config/soil_mineral_db.json",
                  tbl_path="config/soil_mineral.tbl")
info = db.get_soil_info("red_soil")
pco2 = db.get_pCO2("red_soil")

N_YEARS = 30
IONS = ["Ca", "Mg", "K", "Na", "Al", "P", "Zn", "Cl", "C", "S", "N", "Si", "F"]
COLORS = plt.cm.tab20(np.linspace(0, 1, len(IONS)))

precip_chem = PrecipChemistry()
precip_chem.print_summary()

engine = PhreeqcEngine(database="phreeqc.dat", mode="phreeqc",
                       precip_chem=precip_chem)
state = engine.build_initial_state(profile, info, pco2)
climate = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05, N_YEARS, "natural")
ctrl = ScenarioController("natural", {}, {})

months, ph_list, pco2_list = [], [], []
ion_data = {k: [] for k in IONS}

for y in range(N_YEARS):
    for m in range(12):
        forcing = climate.get_monthly_forcing(y, m)
        action = ctrl.get_action(y + 1, m + 1)
        state, diag = engine.run_monthly_step(state, forcing, action, profile)
        months.append(y + 1 + (m + 1) / 12.0)
        ph_list.append(state.ph)
        pco2_list.append(forcing["pCO2"])
        sol = state.solution
        for k in IONS:
            ion_data[k].append(sol.get(k, 0.0))

print(f"模拟完成: {N_YEARS} 年, 降级={engine._permanent_fallback}")

# ---- 绘图: 单图双轴 ----
fig, ax1 = plt.subplots(figsize=(13, 7.5))
ax1.plot(months, ph_list, "k-", lw=2.5, label="pH")
ax1.set_xlabel("Time (years)", fontsize=12)
ax1.set_ylabel("pH", fontsize=12, color="k")
ax1.tick_params(axis="y", labelcolor="k")
ax1.grid(True, alpha=0.3)

ax2 = ax1.twinx()
for k, c in zip(IONS, COLORS):
    ax2.plot(months, ion_data[k], "--", lw=1.3, color=c,
             label=f"{k} (mol/kgw)")
ax2.set_ylabel("Ion concentration (mol/kgw, log scale)", fontsize=12)
ax2.set_yscale("log")
ax2.tick_params(axis="y")

lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2,
           loc="upper left", bbox_to_anchor=(1.02, 1.0),
           fontsize=8, ncol=2, framealpha=0.9)

ax1.set_title("Q7+F1: pH and Ion Concentrations with Precip Chemistry "
              f"(natural, {N_YEARS} years)", fontsize=13)

# 已知局限标注
ax1.annotate(
    "Known limitation: exchangeable Al depletion (~yr 8) causes pH jump\n"
    "in single-layer model (no vertical Al accumulation).",
    xy=(0.5, 0.02), xycoords="axes fraction", ha="center",
    fontsize=8, color="dimgray",
    bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow", alpha=0.8))

plt.tight_layout(rect=[0, 0, 0.82, 1])
out = "output/pH_ions_30yr_Q7.png"
fig.savefig(out, dpi=150, bbox_inches="tight")
print(f"[PLOT] 已保存: {out}")

# 输出首/末年关键数据
print("\n=== 首/末年离子浓度 (mol/kgw) ===")
print(f"{'离子':<6}{'第1月':<14}{'末月':<14}{'变化趋势'}")
for k in IONS:
    a, b = ion_data[k][0], ion_data[k][-1]
    trend = "↑" if b > a * 1.1 else ("↓" if b < a * 0.9 else "→")
    print(f"{k:<6}{a:<14.3e}{b:<14.3e}{trend}")
print(f"pH     {ph_list[0]:<14.3f}{ph_list[-1]:<14.3f}")
print(f"pCO2   {pco2_list[0]:<14.5f}{pco2_list[-1]:<14.5f}")
