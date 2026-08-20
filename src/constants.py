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
# 折中方案说明见 docs/analysis/Q1_plus_ANALYSIS.md:
# 物理值(1e6-1e7 mol)会导致碱性突变(pH~9.9), 需取较小值保留区分度
MINERAL_SCALE = 0.001

# ---- PHREEQC 失败输入复现文件路径 (Q18 落盘, T01 修复) ----
# 官方引擎计算失败时, 完整输入字符串写入此文件供复现与调试 (README 承诺)
# 落盘位置固定为 output/ 运行产物目录 (与 CSV/PNG/日志同处, gitignore 已忽略),
# 引擎写入前自动创建父目录 (v0.3.0 整理: 原根目录 error.inp 移入 output/)
ERROR_INP_PATH = "output/error.inp"

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
#     红壤酸性条件硝化受抑, 取保守量级 (可配置, 见 docs/reports/V0_3_0_FINAL_REPORT.md)
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
# 2e-3 (维持 v0.2.6 基线行为, 详见 docs/reports/V0_3_0_FINAL_REPORT.md 第三节)。
SOLUTION_TOTAL_CATION_CONC = 2e-3

# ---- 非晶质氢氧化铝缓冲相 (L9, v0.4.0) ----
# phreeqc.dat 定义 Al(OH)3(a) (非晶质, log_k 小于结晶态 gibbsite, 更可溶):
# 提供额外 Al 缓冲来源, 解决 fertilizer 单层长期 AlX3 耗尽→pH 突升
# (Q12* 残留 + Q1+ 矿物压缩; v0.4.0 扫描证实单纯增大 MINERAL_SCALE 无效,
# 见 docs/reports/V0_3_0_FINAL_REPORT.md)。质量分数 2% (红壤非晶质铝氧化物典型量级)
AMORPHOUS_ALOH3_MASS_FRACTION = 0.02
# Al(OH)3 摩尔质量 (g/mol)
AMORPHOUS_ALOH3_MOLAR_MASS = 78.0

# ---- 观测锚定预平衡参数 (v0.5.0, grilling Q5=A) ----
# 预平衡通过迭代反馈 (比例-阻尼) 使初始状态在观测 (pH + 交换离子) 约束下
# 自洽: 每步注入修正 (pH→H+/OH-, 交换离子→对应阳离子), 直到观测偏差收敛。
# 收敛判据 (Q5=A): ΔpH < 0.3 且各交换离子相对偏差 < 10%
PRE_EQUIL_PH_TOL = 0.3      # pH 收敛阈值 (观测 vs 稳态)
PRE_EQUIL_ION_TOL = 0.10    # 交换离子相对偏差阈值
PRE_EQUIL_PH_GAIN = 3000.0  # pH 修正增益 (mol H/每 pH 单位, 比例控制, 实测标定 08-14)
PRE_EQUIL_ION_GAIN = 0.5    # 交换离子修正增益 (偏差比例 → 注入比例)

# ---- CEC 缺口补齐参数 (v0.5.0, B 诊断落地) ----
# build_exchange 中 CEC 缺口 (= CEC - Σ观测交换离子) 的填充分配:
# 缺口 × GAP_AL_FRACTION → AlX3 (三价), 缺口 × (1-GAP_AL_FRACTION) → NaX (一价)。
# B 诊断 (2026-08-14): 缺口全 Al (比例=1.0) 使自然平衡 pH 4.36 偏离观测 5.0;
# 全 Na (比例=0.0) 使 pH 5.1 自洽但盐基饱和度偏高。参数化在"pH 自洽"与
# "盐基物理"间取平衡, 扫描确定默认值 (见 docs/reports/V0_3_0_FINAL_REPORT.md)。
GAP_AL_FRACTION = 0.3       # 缺口中 Al 占比 (扫描确定 2026-08-14: 0.3→首平衡 pH 4.92, Δ=0.08 最接近观测 5.0)

# ---- AlX3 交换选择性校准参数 (v0.5.0, L9) ----
# 引擎层 EXCHANGE_SPECIES 覆盖 Al+3 + 3X- = AlX3 的 log_k (默认 0.41=数据库值)。
# 校准方向: 增大 log_k → 增强 Al 对交换位点亲和力, 抑制盐基置换交换 Al。
# 历史教训 (ROADMAP): 0.41→5.0 曾在 natural 场景无效, fertilizer 场景需扫描。
ALX3_DEFAULT_LOGK = 0.41    # phreeqc.dat 数据库原值
ALX3_SELECTIVITY_LOGK = 0.41   # 校准值 (默认=数据库值, 仅覆盖非默认时输出 EXCHANGE_SPECIES)

# ---- Al 动力学 (v0.6.0) 已回退 (v0.6.1) ----
# KINETICS 方案被证据否定: 冻结 gibbsite 切断 L2 矿物回补, 反而加速 AlX3 耗尽
# (y1 m7 vs 平衡相 y3); AlX3 耗尽主因是单层排水淋失 (结构性), 非矿物化。
# 完整证据链见 docs/reports/V0_3_0_FINAL_REPORT.md。AL_KINETIC_* 常量已删除。

# ---- v0.5.2 Green-Ampt 表层入渗 (物理边界, 替代 Horton + surface_coeff) ----
# 湿润锋吸力水头 ψ_f (mm): Rawls et al. (1983) 红壤 (粘土/粘壤土) 典型值
# -10 ~ -20 cm (绝对值 100~200 mm), 取中值 150
GREEN_AMPT_PSI_F_MM = 150.0
# 基质导水率 (cm/day): 仅用于 Green-Ampt 地表入渗 (K_s), 专家方案 D3 定案
# 华南红壤 L1 基质导水率 (暴雨 >15mm/h 自然触发超渗产流)
DEFAULT_KSAT_SURFACE = 7.2
# Green-Ampt 牛顿迭代收敛容差与最大迭代数
GREEN_AMPT_NEWTON_TOL = 1e-9
GREEN_AMPT_NEWTON_MAX_ITER = 50


# ---- v0.5.0 水文: 4 层内置物理剖面默认 (n_layers=4 且未配置 layer_overrides 时自动启用) ----
# 真实红壤剖面: 表层薄/粘粒少/孔隙度大/导水强, 底层厚/粘粒多/致密/导水弱
# 孔隙度覆盖时反推容重 ρ=2.65(1−φ) (input_reader.apply_layer_override)
DEFAULT_4LAYER_DEPTHS = [20.0, 20.0, 20.0, 40.0]    # 每层厚度 (cm)
DEFAULT_4LAYER_CLAY_PCT = [25.0, 35.0, 45.0, 50.0]  # 粘粒含量 (%)
DEFAULT_4LAYER_POROSITY = [0.55, 0.47, 0.45, 0.43]  # 孔隙度
DEFAULT_4LAYER_KSAT = [12.0, 1.9, 0.48, 0.05]  # 层间排水上限 (cm/day, v0.5.2 起仅 LayerCascade 用)

# ---- v0.5.3 VGM 水分特征 (D8, VGM参数化方案.txt) ----
# 三级参数优先级: ①layer_overrides 显式 vgm_* ②clay_pct 连续回归
# (Saxton & Rawls 2006 + 红壤修正) ③华南红壤兜底; l=0.5 固定 (Mualem);
# θ_s≡porosity (数学自洽, 状态转换无质量误差)
INITIAL_PSI_CM = -100.0                 # 初始水势 (cm, 田间持水量, config 可配)
VGM_CLAY_THETA_R_A = 0.01               # θ_r 回归: A + B×clay_pct
VGM_CLAY_THETA_R_B = 0.002
VGM_CLAY_ALPHA_A = 0.04                 # α (1/cm) 回归: A + B×clay_pct
VGM_CLAY_ALPHA_B = -0.0006
VGM_CLAY_N_A = 1.5                      # n 回归: A + B×clay_pct
VGM_CLAY_N_B = -0.008
VGM_FALLBACK_THETA_R = 0.08             # 华南红壤兜底 θ_r
VGM_FALLBACK_ALPHA = 0.015              # 华南红壤兜底 α (1/cm)
VGM_FALLBACK_N = 1.25                   # 华南红壤兜底 n
VGM_MUALEM_L = 0.5                      # Mualem 曲折度参数 (固定)

# ---- v0.5.3 Feddes 根系吸水 (Q3/Q9, ψ 版 α) ----
# 四阈值 (cm, 标准 Feddes 红壤旱地中值): α 分段如下
#   ψ≥h1 厌氧/积水 → 0; h1→h2 线性升 0→1; h2→h3 平台 1;
#   h3→h4 线性降 1→0; ψ≤h4 永久萎蔫 → 0
FEDDES_H1 = -25.0                       # 厌氧点 (积水/缺氧)
FEDDES_H2 = -100.0                      # 最适区间上界 (≈田间持水量)
FEDDES_H3 = -800.0                      # 最适区间下界 (中度胁迫)
FEDDES_H4 = -15000.0                    # 永久萎蔫点
# 4 层根系分布权重 (D5, Σ=1.0)
ROOT_FRACTION_4LAYER = [0.60, 0.30, 0.10, 0.00]
# 每月天数 (Oudin PET 月累积, 平年)
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
DEFAULT_LATITUDE = 23.1                 # 站点纬度默认 (广州, 华南红壤典型)

# ---- v0.6.0 Hargreaves PET (Q8/Q9, Oudin 精度增强模式) ----
# 默认日较差 (T_max − T_min): 华南典型 6~10°C 中值 (config 可配, 非硬编码)
DEFAULT_DIURNAL_RANGE = 8.0

# ---- v0.6.0 体积-θ 耦合数值保护 (Q5 修复) ----
# 单步浓缩/稀释比上限: 物理约束 = 田间持水→萎蔫点的水量比 (θ_FC/θ_wp ≈
# 0.41/0.143 ≈ 3), 超出按 3× 钳制 (防蒸发浓缩单步失控; 绝对量守恒略破但
# 数值稳定优先; 彻底解决需 v0.6.1+ 盐分淋失路径调校)
MAX_CONCENTRATION_RATIO = 3.0

# ---- v0.5.3 OM 矿化产 CO₂ (D7/Q4/Q10) ----
# 加性调制 GAS_PHASE pCO₂: pCO₂_eff = base(T) + k_om×OM_i, 钳制 ≤ pCO₂_max
# (加性防高 OM 失控, 专家 Q4 修订; 温度独立性: T 响应仅归 base 项, 专家★3)
K_OM_PCO2 = 0.0005          # OM → ΔpCO₂ 系数 (atm per g/kg): L1 30g/kg → +0.015 atm
PCO2_MAX = 0.05             # 层内 pCO₂ 上限钳制 (atm)
OM_PROFILE_4LAYER = [30.0, 15.0, 8.0, 5.0]   # 4 层内置默认有机质 (g/kg, 表层富集)

# ============================================================
# v0.6.1 数值稳定性根治 (spec 62, /grilling Q1~Q10 定案, 2026-08-20)
# ============================================================

# ---- VIC 深层基流 (Q1/Q2/Q4, L4 底部替换 min(drainable, ksat_cap)) ----
# Q_base = D_max·[D_s·S + (1−D_s)·Sⁿ], S=(θ−θ_r)/(θ_s−θ_r)
#   - θ_c = θ_r (残余含水量): 旱季 θ_r<θ<θ_FC 有 D_s 线性项裂隙基流基线 (专家参数表)
#   - D_max 对应完全饱和态: 华南红壤年深层渗漏 500~800 mm/yr ×35% ≈ 665/12 ≈ 55;
#     考虑 D_max 为饱和上限取 100 mm/month (裂隙/风化壳基流工程出口, 可扫描标定)
#   - 防抽干: Q_base = min(公式, (θ−θ_r)·d·10), 不抽到 θ_r 以下
BASE_D_MAX = 100.0          # 最大基流速率 (mm/month)
BASE_DS = 0.10              # 线性排水比例 (裂隙流基线, 低含水量小流量)
BASE_N = 2.5                # 非线性指数 (红壤粘重排水非线性较强)
BASE_THETA_C_MODE = "theta_r"   # 基流启动阈值来源: "theta_r" (专家参数表)

# ---- Darcy 侧向排水 (Q1/Q2/Q4, 各层) ----
# Q_lat = k_lat·f_slope·max(0, θ−θ_FC)·d·10 (mm/month)
#   - 严格 FC 闸门: θ≤θ_FC 零侧向 (毛管力束缚, 华南红壤"垂直有裂隙、侧向需饱和")
#   - f_slope = tan(β): β≈6° 华南红壤农田典型坡度 (3°~15°)
#   - k_lat 反映各层水平导水率/裂隙/根系通道: 表层快、母质层慢
#   - 防抽干: Q_lat = min(公式, (θ−θ_FC)·d·10)
LAT_F_SLOPE = 0.10          # 地形坡度因子 (tan 6°, 无单位)
LAT_K = [0.04, 0.025, 0.015, 0.008]   # 各层侧向排水系数 (1/day): L1~L4

# ---- fallback 事件级局部降级 (Q5, P-NUM-3) ----
# 单场失败保留前一正常状态跳过; 连续 N 次失败才永久降级 (事件/月级路径分开计数)
FALLBACK_MAX_CONSECUTIVE = 3

# ---- 浓度硬上限冲洗 (Q6) ----
# 事件后某层 max 离子浓度 > C_warn → 触发基流/侧向激增 Q_flush (物理式加速出口)
CONC_WARN = 0.5             # 离子浓度预警阈值 (mol/L)
C_MIN = 1e-10               # 溶质比例扣除的下限保护 (mol/L, 防 PHREEQC negative activity)

# ---- HX 交换酸注入 (Q7, P-E2-1 A 类) ----
# phreeqc.dat 的 "H+ + X- = HX" 被注释禁用 (第 1362 行), 需引擎层 EXCHANGE_SPECIES 自定义注入
#   - log_k=3.0: 扫描标定 (2026-08-20 实测): log_k=1.0 → 平衡 pH 3.74 (酸解离过强,
#     预平衡无法锚定观测 5.0); log_k=3.0 → 平衡 pH 4.99 (自然收敛观测, HX 保留为
#     真实酸库); log_k≥5.0 → pH 过高 (≥6.9) 且 HX 膨胀超 CEC。见 spec 62 风险注记。
#   - GAP_H_FRACTION: CEC 缺口三通道重分配 (HX/AlX3/NaX), 与 GAP_AL_FRACTION 并列
HX_LOGK = 3.0               # HX 交换物种 log_k (扫描标定值, 2026-08-20)
GAP_H_FRACTION = 0.3        # 缺口 → HX 比例 (与 GAP_AL_FRACTION 并列, 余量 NaX)



