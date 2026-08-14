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
