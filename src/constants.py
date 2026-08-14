"""
模块: constants.py
功能: 全局常量集中管理 (Q19 修复, v0.2.2)

说明: 简化模式系数/pH 界限/入渗系数/矿物量缩放等魔法数字统一在此定义,
      避免散落于各模块 (涉及 src/phreeqc_engine.py, src/initial_condition.py,
      src/config_manager.py)。
"""

# ---- 简化模式经验系数 (S4 物理量级校准, v0.2.1) ----
# 说明: official natural 前 7 年升碱是单层 Al 淋洗局限, 故采用物理量级校准
SIMPLIFIED_K_PRECIP = 1.5e-5   # 降水淋溶: ~0.03 pH/年 (30 年 ~0.9)
SIMPLIFIED_K_FERT = 0.0007     # 施肥产酸: ~0.02 pH/次
SIMPLIFIED_K_LIME = 0.002      # 石灰提碱: ~0.09 pH/次

# ---- pH 物理界限 (Q5 修复, v0.2.1: 移除硬编码 3.5/9.0) ----
PH_LOWER = 2.0
PH_UPPER = 12.0

# ---- 降水入渗系数 (T3 参数化, v0.2.2) ----
PRECIP_INFILTRATION_DEFAULT = 0.05

# ---- 矿物量缩放系数 (F2 统一, v0.1.4) ----
# 折中方案说明见 docs/Q1_plus_ANALYSIS.md:
# 物理值(1e6-1e7 mol)会导致碱性突变(pH~9.9), 需取较小值保留区分度
MINERAL_SCALE = 0.001

# ---- PHREEQC 失败输入复现文件路径 (Q18 落盘, T01 修复) ----
# 官方引擎计算失败时, 完整输入字符串写入此文件供复现与调试 (README 承诺)
ERROR_INP_PATH = "error.inp"

# ---- Hfo 表面位点参数 (WF4: SURFACE 表面络合, Dzombak & Morel 1990) ----
# 铁氧化物比表面积 (m2/g): HFO 典型值 (Dzombak & Morel), 仅用于质量推导
HFO_SPECIFIC_AREA = 600.0
# 强位点 (Hfo_s) 位点密度 (mol/m2): D&M 标准 0.005 mol/mol Fe 折算
HFO_STRONG_SITE_DENSITY = 8.35e-4
# 弱位点 (Hfo_w) 位点密度 (mol/m2): D&M 标准 0.2 mol/mol Fe 折算
HFO_WEAK_SITE_DENSITY = 1.67e-2
# 目标表面位点总量 (mol): D&M 模型适用浓度范围 (~1e-4 mol/L), 超出会数值失稳
# (WF5 实测: 表面位点 >~100 mol 时 Al/Ca 不收敛, 交换位点被误判为抽干)
HFO_TARGET_SITES = 50.0

# ---- 硝化两步动力学参数 (L4, v0.3.0) ----
# 简化一阶转化: 尿素 → NH4+ (水解 k1) → NO3- + 2H+ (硝化 k2)
# 决策依据 (2026-08-14 grilling Q3/Q10):
#   - 简化两步一阶 (非 Monod KINETICS), 但架构留有升级空间
#     (advance_nitrification 独立函数, 可整体替换为 PHREEQC KINETICS 实现)
#   - k1=1.0: 尿素水解 (urease 催化) 在田间数天内完成, 远快于月步长 → 当月全水解
#   - k2=0.4: 硝化速率 0.4/month, 约 2-3 个月完成大部分硝化;
#     红壤酸性条件硝化受抑, 取保守量级 (可配置, 见 docs/V0_3_0_REPORT.md)
NITRIFICATION_K1 = 1.0      # 尿素水解速率 (/month)
NITRIFICATION_K2 = 0.4      # 硝化速率 (/month)
# kg N → mol N 换算 (N 原子量 14.007): 施肥量 (kg N/ha) → 摩尔量 (mol N)
N_MOL_PER_KG_N = 1000.0 / 14.007

# ---- 溶液电荷平衡参数 (L5, v0.3.0) ----
# CO2 亨利常数 (mol/(L·atm), 25°C): 计算初始 HCO3- 浓度 (与 GAS_PHASE pCO2 联动)
HENRY_CO2 = 3.4e-2
# 碳酸第一级解离常数 (25°C): H2CO3 ⇌ H+ + HCO3-
KA1_H2CO3 = 4.3e-7
# 碳酸第二级解离常数 (25°C): HCO3- ⇌ H+ + CO3-2
KA2_HCO3 = 4.7e-11
# 水的离子积 (25°C)
KW_WATER = 1.0e-14
# 保留微量 Cl- (mol/L): 电荷平衡盈余大时由 Cl- 兜底 (pH<6 HCO3- 承载有限),
# 背景值避免与降水化学 Cl- 输入完全归零导致数值边缘
CHARGE_BALANCE_CL_RESIDUAL = 1e-6
# 初始溶液总阳离子浓度 (mol/L) — 土壤溶液量级 (与交换相自洽)
# 修正记录 (v0.3.0 实测): 曾尝试淋溶液量级 5e-5 (电荷物理化), 但土壤溶液
# 体积为田间持水 (8.2e5 L/ha), 5e-5 与交换相 NaX (43200 mol) 失衡, 平衡时
# NaX 释放 Na+ 触发 pH 碱化漂移 (fertilizer 5 年 pH 反转至 10.4), 故保留
# 2e-3 (维持 v0.2.6 基线行为, 详见 docs/V0_3_0_REPORT.md 第三节)。
SOLUTION_TOTAL_CATION_CONC = 2e-3

# ---- 非晶质氢氧化铝缓冲相 (L9, v0.4.0) ----
# phreeqc.dat 定义 Al(OH)3(a) (非晶质, log_k 小于结晶态 gibbsite, 更可溶):
# 提供额外 Al 缓冲来源, 解决 fertilizer 单层长期 AlX3 耗尽→pH 突升
# (Q12* 残留 + Q1+ 矿物压缩; v0.4.0 扫描证实单纯增大 MINERAL_SCALE 无效,
# 见 docs/V0_4_0_L9_SCAN.md)。质量分数 2% (红壤非晶质铝氧化物典型量级)
AMORPHOUS_ALOH3_MASS_FRACTION = 0.02
# Al(OH)3 摩尔质量 (g/mol)
AMORPHOUS_ALOH3_MOLAR_MASS = 78.0
