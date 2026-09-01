"""
模块: phreeqc_engine.py
功能: PHREEQC 引擎封装 (通过官方 phreeqc / IPhreeqc 调用)

输入: 土壤状态、当月强迫条件
输出: 更新后的土壤状态、诊断量

核心原理:
  - 离子交换 (Gapon/Vanselow 方程)
  - 表面络合 (有机质/铁铝氧化物)
  - 矿物溶解-沉淀平衡
  - 溶质运移/淋溶
"""

import math
import numpy as np
from pathlib import Path
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from src.constants import (MINERAL_SCALE, PRECIP_INFILTRATION_DEFAULT,
                           SIMPLIFIED_K_PRECIP, SIMPLIFIED_K_FERT,
                           SIMPLIFIED_K_LIME, PH_LOWER, PH_UPPER,
                           ERROR_INP_PATH,
                           HFO_SPECIFIC_AREA, HFO_STRONG_SITE_DENSITY,
                           HFO_WEAK_SITE_DENSITY,
                           NITRIFICATION_K1, NITRIFICATION_K2,
                           N_MOL_PER_KG_N,
                           PRE_EQUIL_PH_TOL, PRE_EQUIL_ION_TOL,
                           PRE_EQUIL_PH_GAIN, PRE_EQUIL_ION_GAIN,
                           ALX3_DEFAULT_LOGK, ALX3_SELECTIVITY_LOGK,
                           HX_LOGK,
                           INITIAL_PSI_CM, GREEN_AMPT_PSI_F_MM,
                           DEFAULT_KSAT_SURFACE, MAX_CONCENTRATION_RATIO,
                           FALLBACK_MAX_CONSECUTIVE,
                           C_MIN, CONC_WARN,
                           KNOBS_ITERATIONS, KNOBS_TOLERANCE,
                           KNOBS_TOLERANCE_PRE,
                           KNOBS_CONVERGENCE_TOLERANCE,
                           KNOBS_STEP_SIZE,
                           KNOBS_ITERATIONS_SHALLOW,
                           KNOBS_ITERATIONS_DEEP,
                           KNOBS_DEEP_START_LAYER,
                           KNOBS_RETRY_MULTIPLIER)
from src.vgm import theta_to_water_L
from src.logging_config import get_logger
from src.scenario_controller import MonthlyAction

logger = get_logger("phreeqc_engine")

try:
    from phreeqc import Phreeqc as OfficialPhreeqc
    OFFICIAL_PHREEQC_AVAILABLE = True
except ImportError:
    OFFICIAL_PHREEQC_AVAILABLE = False
    logger.warning("官方 phreeqc (IPhreeqc) 未安装")


@dataclass
class SoilState:
    """土壤化学状态 (PHREEQC 内部状态)"""
    solution: dict = field(default_factory=dict)
    exchange: dict = field(default_factory=dict)
    minerals: dict = field(default_factory=dict)
    gas_phase: dict = field(default_factory=dict)
    surface: dict = field(default_factory=dict)   # WF4: Hfo_s/Hfo_w 表面位点
    volume: float = 1.0          # 土壤溶液体积 (L)
    temperature: float = 25.0
    ph: float = 7.0
    pe: float = 4.0
    # L4: 氮形态库存 (mol N) — 简化两步硝化 (尿素→NH4+→NO3-)
    n_urea: float = 0.0          # 尿素形态氮 (mol N), 水解前库存
    n_nh4: float = 0.0           # 铵态氮 (mol N), 由 SELECTED_OUTPUT N(-3) 回填
    n_no3: float = 0.0           # 硝态氮 (mol N), 由 SELECTED_OUTPUT N(5) 回填
    # v0.7.0 (工单70): 硝态氮淋失示踪池 (mol N) — 由 advance_nitrification 同步
    # 推进; 逐场 lost_no3 水库串联消费; n_no3 保持为累计诊断器 (向后兼容)
    n_no3_pool: float = 0.0
    theta: float = 0.0           # v0.5.3: 本层体积含水量 θ (m³/m³), 跨月累积
                                 # (规范状态, Q1/Q7; L/ha 由 vgm.theta_to_water_L 派生)


def advance_nitrification(state: SoilState, action,
                          k1: float = NITRIFICATION_K1,
                          k2: float = NITRIFICATION_K2) -> Dict[str, float]:
    """推进氮形态库存 (尿素 → NH4+ → NO3-, 简化一阶转化) [L4, v0.3.0]

    独立模块级函数 (升级空间): 将来若升级为 PHREEQC KINETICS 动力学块,
    只需替换本函数实现, 调用方 (引擎月度步) 与返回契约不变。

    Q1=A (库存层): 氮形态 (尿素/NH4+/NO3-) 为纯模型状态, 不注入 PHREEQC
    溶液平衡 — phreeqc.dat 的 N 氧化还原平衡会把注入的无机氮全部转为
    N2(g) (实测: pe=0~12 下溶液 N(-3)/N(5) 均≈0)。NH4+ 吸附于交换位点
    不易淋失, 为硝化的驱动源; NO3- 为累计硝化量 (诊断, Q4=A)。

    月度推进顺序:
      1. 施肥: N 以尿素形式入库存 (kg N → mol N)
      2. 尿素水解: n_urea × k1 → NH4+ (k1=1.0 当月全水解)
      3. 硝化: n_nh4 × k2 → NO3- (库存累计)

    返回本月硝化产酸量 (mol H+): {'H+': 2×硝化量}
    (Q3=A: 硝化产酸注入 REACTION, 酸化效应真实进入溶液)
    """
    # 1. 施肥: 尿素入库存 (kg N → mol N)
    if action.apply_fertilizer and getattr(action, 'n_amount', 0.0) > 0:
        state.n_urea += action.n_amount * N_MOL_PER_KG_N

    # 2. 尿素水解: urea → NH4+ (k1)
    hydrolyzed = state.n_urea * k1
    state.n_urea -= hydrolyzed
    state.n_nh4 += hydrolyzed

    # 3. 硝化: NH4+ → NO3- (k2, 库存形态)
    nitrified = state.n_nh4 * k2
    state.n_nh4 -= nitrified
    state.n_no3 += nitrified
    # v0.7.0 (工单70): 硝化量同步进入淋失示踪池 (供逐场 lost_no3 消费)
    state.n_no3_pool += nitrified

    # v0.7.0 (工单70): 返回契约扩展 — nitrified/hydrolyzed 键供 D3 伴随淋失
    # (工单71) 与 NH4+ 等效置换 (工单72) 消费; 'H+' 键契约不变 (向后兼容)
    return {'H+': 2.0 * nitrified,
            'nitrified': nitrified,
            'hydrolyzed': hydrolyzed}


def calc_no3_leaching(pool_mol: float, water_out_L: float,
                      v_pool_L: float) -> float:
    """v0.7.0 (工单70): NO₃⁻ 随水移出量 (mol) — 水库串联淋失 + 全局不变量

    lost = min(pool × water_out/V_pool, pool)  (池不变量: pool ≥ 0)
      - water_out_L: 该出口通道排水量 (L, 垂直/侧向/基流/bypass)
      - v_pool_L: 池溶液体积 (L), ≤0 按 1.0 保护
      - 返回移出摩尔量 (0 ≤ lost ≤ pool): 与 v0.6.1 "防抽干" 同哲学 —
        bypass/排水量再大也只能带走池中实际存在的 NO₃⁻ (Q19 审查通过)
    """
    if pool_mol <= 0.0 or water_out_L <= 0.0:
        return 0.0
    v = max(v_pool_L, 1.0)
    return min(pool_mol * (water_out_L / v), pool_mol)


def solution_base_eq(solution: dict, volume: float) -> float:
    """v0.7.x (工单80): 溶液盐基当量总量 (eq)

    eq = (2×Ca + 2×Mg + K + Na) × volume
      - Ca/Mg 二价 ×2, K/Na 一价 ×1 (与 exchange_base_ratios 同价态约定)
      - Al 为酸性盐基 (Al³⁺), 不计入
      - volume ≤ 0 → 0 (防负当量)
    """
    if volume <= 0.0:
        return 0.0
    return ((solution.get('Ca', 0.0) * 2.0
             + solution.get('Mg', 0.0) * 2.0
             + solution.get('K', 0.0)
             + solution.get('Na', 0.0)) * volume)


def calc_base_leaching(base_eq: float, water_out_L: float,
                       v_pool_L: float, eq_floor: float = 0.0) -> float:
    """v0.7.x (工单80): 盐基随水移出当量 (eq) — E_base, 与 NO₃⁻ 池同构

    E_base = min(溶液盐基eq × water_out/V_pool, 溶液盐基eq)  (0 ≤ lost ≤ pool)
      - water_out_L: 离开本层的全部水 (drains + lateral + baseflow)
      - 复用 calc_no3_leaching 同构不变量 (全局 pool≥0, Q19 哲学延续)

    工单87 (P0-A): eq_floor>0 时施加"溶液盐基保底"——低于保底当量时不认领
    淋失 (E_base 返回 0, 下一场不再注入 An- 拽盐基), 可抽池 = base_eq - eq_floor。
    护栏语义: 出系统水流仍可自然带走盐基 (Q3 溶质扣除在 run_event_step 内),
    但 E_base 泵不再把溶液盐基逼到物理下限之下 (H1 归因落地)。
    """
    if base_eq <= eq_floor or water_out_L <= 0.0:
        return 0.0
    v = max(v_pool_L, 1.0)
    pool = base_eq - eq_floor
    return min(pool * (water_out_L / v), pool)


def calc_base_saturation(exchange: dict, include_hx: bool = False) -> float:
    """v0.7.0 (工单71): 盐基饱和度 BS% — 与 main._extract_diagnostics 同公式

    BS = (CaX2×2 + MgX2×2 + KX + NaX) / (盐基 + AlX3×3) × 100
    (与既有 base_saturation 诊断列数值一致, 分级注入与输出可对照)

    工单87 (P0-C): include_hx=True 时分母追加 HX (X- 位点上的 H, 一价电荷当量
    = mol) ——修复"AlX3 耗尽后 BS→100% 度量伪影" (H0 归因: 伪影经 E_base/
    companion 分级注入反馈放大泵)。引擎分级注入传 include_hx=True (物理口径),
    输出诊断列保持 include_hx=False (历史口径兼容)。
    """
    base_charge = (exchange.get('CaX2', 0.0) * 2.0
                   + exchange.get('MgX2', 0.0) * 2.0
                   + exchange.get('KX', 0.0)
                   + exchange.get('NaX', 0.0))
    acid_charge = exchange.get('AlX3', 0.0) * 3.0
    if include_hx:
        acid_charge += exchange.get('HX', 0.0)
    total = base_charge + acid_charge
    return base_charge / total * 100.0 if total > 0 else 0.0


def exchange_base_ratios(exchange: dict) -> Dict[str, float]:
    """v0.7.0 (工单72): 交换相 Ca:Mg:K:Na 电荷占比 (置换注入配比)

    按电荷量占比返回 {离子: 比例}, Σ=1; 空交换相 → 空 dict。
    CaX2/MgX2 为二价 (×2), KX/NaX 为一价。物理依据: NH4+ 置换盐基时
    各盐基按其在交换相中的电荷占比被置换出来 (简化近似, Gapon 加权留 v0.7.x)。
    """
    ca = exchange.get('CaX2', 0.0) * 2.0
    mg = exchange.get('MgX2', 0.0) * 2.0
    k = exchange.get('KX', 0.0)
    na = exchange.get('NaX', 0.0)
    total = ca + mg + k + na
    if total <= 0.0:
        return {}
    return {'Ca+2': ca / total, 'Mg+2': mg / total,
            'K+': k / total, 'Na+': na / total}


def weathering_arrhenius_factor(temp_c: float,
                                activation_energy_kJ: float,
                                t_ref_k: float = 298.15) -> float:
    """v0.7.0 (工单73): 矿物风化 Arrhenius 温度因子 (D2, 气候敏感性传导)

    factor = exp(−Ea/R × (1/T − 1/T_ref)), T 为开尔文
      - T = T_ref (25°C) → 1.0 (基准)
      - Ea=40 kJ/mol 时: 30°C ≈ 1.30 (增温 5°C 风化 +30%);
        20°C ≈ 0.77 (降温风化减缓) → 增温情景产生可观测风化响应 (疑点2)
    """
    r = 8.314
    t_k = temp_c + 273.15
    return math.exp(-activation_energy_kJ * 1000.0 / r
                    * (1.0 / t_k - 1.0 / t_ref_k))


@dataclass
class DiagnosticOutput:
    """诊断输出"""
    ph: float = 0.0
    pe: float = 0.0
    base_saturation: float = 0.0
    cec_occupied: float = 0.0
    exchangeable_ca: float = 0.0
    exchangeable_al: float = 0.0
    mineral_masses: dict = field(default_factory=dict)
    solution_ions: dict = field(default_factory=dict)
    # v0.6.0 (Q14): First-Flush 峰值列 (当月 L1 最大单场淋失, mmol/ha)
    flush_no3_peak_mmol: float = 0.0
    flush_base_peak_mmol: float = 0.0


def _monthly_step_worker(q, database, mode, enable_surface, precip_infiltration,
                         precip_chem, nitrification_k1, nitrification_k2,
                         state, forcing, action, soil_profile):
    """子进程月度步 worker (数值稳定性, v0.6.1): 重建引擎执行, 结果入队列"""
    try:
        from src.phreeqc_engine import PhreeqcEngine
        e = PhreeqcEngine(database=database, mode=mode,
                          enable_surface=enable_surface,
                          precip_infiltration=precip_infiltration,
                          precip_chem=precip_chem,
                          nitrification_k1=nitrification_k1,
                          nitrification_k2=nitrification_k2)
        ns, diag = e.run_monthly_step(state, forcing, action, soil_profile)
        q.put((ns, diag))
    except Exception as ex:
        q.put(('error', str(ex)))


class PhreeqcEngine:
    """PHREEQC 引擎封装类"""

    def __init__(self, database: str = 'phreeqc.dat',
                 mode: str = 'auto', backend: str = 'official',
                 precip_chem=None,
                 precip_infiltration: float = PRECIP_INFILTRATION_DEFAULT,
                 enable_surface: bool = False,
                 nitrification_k1: float = NITRIFICATION_K1,
                 nitrification_k2: float = NITRIFICATION_K2,
                 initial_psi_cm: float = INITIAL_PSI_CM,
                 companion_cfg=None,
                 weathering_cfg=None,
                 charge_pairing_cfg=None,
                 base_leaching_cfg=None):
        """
        参数:
            database: PHREEQC 热力学数据库
            mode: 引擎模式
                - auto      : PHREEQC 可用则用 PHREEQC, 否则简化模式 (默认)
                - simplified: 始终使用简化动力学模式
                - phreeqc   : 始终使用 PHREEQC (失败时降级简化模式)
            backend: PHREEQC 后端 (v0.1.3 起仅支持官方引擎)
                - official    : 官方 phreeqc 包 (IPhreeqc 3.8.6), 默认
                - 其他取值    : 已废弃 (phreeqpython 等), 自动视为 official
            precip_chem: 降水化学对象 (PrecipChemistry) 或 None (Q7)
            precip_infiltration: 降水入渗系数 0~1 (T3 参数化, 默认 0.05)
            enable_surface: 是否启用 SURFACE 表面络合 (WF4, 默认关闭)
                - True : 生成 Hfo_s/Hfo_w 铁氧化物表面, P/Zn 吸附生效
                - False: 不生成 SURFACE 块 (回归护栏)
            nitrification_k1: 尿素水解速率 /月 (L4, 默认 1.0=当月全水解)
            nitrification_k2: 硝化速率 /月 (L4, 默认 0.4; config 可配置)
            initial_psi_cm: v0.5.3: 初始基质势 (cm, 负值, 默认 −100 田间持水量),
                经 VGM 正算 state.theta 初始值 (D8/Q8)
        """
        self.database = database
        self.mode = mode
        # phreeqpython 后端已废弃 (v0.1.3): 统一使用官方引擎
        if backend != 'official':
            logger.warning("backend '%s' 已废弃, 强制使用官方引擎", backend)
        self.backend = 'official'
        self.official = None    # 官方 phreeqc 后端实例
        self.precip_chem = precip_chem  # 降水化学 (Q7)
        self.enable_surface = enable_surface  # WF4: SURFACE 表面络合开关
        # L4 硝化速率 (v0.4.0: config 可配置, 默认=constants)
        self.nitrification_k1 = nitrification_k1  # 尿素水解速率 /月
        self.nitrification_k2 = nitrification_k2  # 硝化速率 /月
        self._fallback_warned = False
        self._permanent_fallback = False
        # v0.6.1 (spec 62 Q5): 事件级局部降级 — 连续失败计数 (事件/月级分开)
        self._consecutive_failures_event = 0
        self._consecutive_failures_monthly = 0
        self.last_error_message = None    # Q18: 最近一次引擎失败信息
        self.last_error_input = None     # Q18: 最近一次失败输入字符串
        # 降水入渗系数 (0~1): 实际进入土壤溶液的比例, 其余径流/排水 (T3 参数化)
        self.precip_infiltration = precip_infiltration
        # 矿物量缩放系数: EQUILIBRIUM_PHASES 矿物量 = 物理摩尔量 × 此系数
        # (折中方案, 见 docs/analysis/Q1_plus_ANALYSIS.md):
        # 物理值(1e6-1e7 mol)会导致碱性突变(pH~9.9), 需取较小值保留区分度
        # F2 修复: 与 initial_condition.MINERAL_SCALE 统一 (双路径一致)
        self.mineral_scale = MINERAL_SCALE
        # v0.5.3: 初始基质势 (cm, 负值) — 经 VGM 正算 state.theta (D8/Q8)
        self.initial_psi_cm = initial_psi_cm
        # v0.7.0 (spec 69, 工单70): NO3- 伴随淋失配置 (None=禁用, 回退 v0.6.1)
        # companion 为 v0.7.0 主线 (config 默认启用); 既有测试构造引擎不传 → 禁用
        self.companion_cfg = companion_cfg
        self.companion_enabled = bool(companion_cfg is not None
                                      and companion_cfg.enable)
        self.companion_bypass_no3_carry = bool(
            companion_cfg is not None and companion_cfg.bypass_no3_carry)
        # v0.7.0 (spec 69, 工单73): 矿物风化集总注入配置 (None=禁用, 回退基线)
        self.weathering_cfg = weathering_cfg
        self.weathering_enabled = bool(weathering_cfg is not None
                                       and weathering_cfg.enable)
        # v0.7.x (工单77): REACTION 电荷平衡修复 — 裸阳离子/酸注入在 PHREEQC
        # 中因电荷平衡产生伪碱化/不酸化 (2026-08-21 探针实测, Ca+2 343 →
        # pH 9.28 复现 v0.7.0 fertilizer 8~11)。默认启用 (None → 默认配置);
        # 显式 enable=False 回退裸注入 (对照)。
        self.charge_pairing_cfg = charge_pairing_cfg
        self.charge_pairing_enabled = bool(
            charge_pairing_cfg is None or charge_pairing_cfg.enable)
        # v0.7.x (工单80): 盐基淋失强化 — None=禁用 (回归护栏, 同 companion);
        # main/sensitivity 从 config 传入 (config.yaml 默认启用)。enable:false
        # = 工单 80 前基线 (A/B 对照, natural 30y 轨迹叠加对比)。
        self.base_leaching_cfg = base_leaching_cfg
        self.base_leaching_enabled = bool(base_leaching_cfg is not None
                                          and base_leaching_cfg.enable)
        # 配对阴离子名: companion 启用时与其 inert_anion 共享 (单一定义);
        # 否则用 charge_pairing.anion (默认 An); 否则 base_leaching.anion
        if companion_cfg is not None and companion_cfg.enable:
            self.pair_anion = companion_cfg.inert_anion
        elif charge_pairing_cfg is not None:
            self.pair_anion = charge_pairing_cfg.anion
        elif base_leaching_cfg is not None:
            self.pair_anion = base_leaching_cfg.anion
        else:
            self.pair_anion = "An"
        # An- 物种定义条件: companion 或 charge pairing 或 base leaching 任一启用
        self.anion_defined = bool(self.companion_enabled
                                  or self.charge_pairing_enabled
                                  or self.base_leaching_enabled)
        # v0.7.x (工单78): 预平衡/模拟双 tolerance — 预平衡从远平衡起点需 1e-12
        # (宽松假收敛稳定, 1e-9 会第一步迭代超限返回垃圾解 CaX2=0); 模拟步从
        # 预平衡状态 (接近平衡) 用 1e-9 (lime 高 pH 真收敛 10.18, 1e-12 静默假
        # 收敛 4.89)。_build_phreeqc_input 据此选 -tolerance。
        self._in_pre_equilibration = False

        # ---- 初始化后端 (v0.1.3: 仅官方引擎, phreeqpython 已废弃) ----
        if OFFICIAL_PHREEQC_AVAILABLE:
            self.official = OfficialPhreeqc()
            self.official.LoadBuiltInDatabase(database)
            ver = self.official.GetVersionString()
            logger.info("官方 PHREEQC 引擎已初始化 (IPhreeqc %s)", ver)
        else:
            self.backend = 'simplified'
            logger.warning("无可用 PHREEQC 引擎，使用简化模式")

    def build_initial_state(self, soil_profile, mineral_db_info,
                            pCO2: float) -> SoilState:
        """构建初始土壤状态

        使用 InitialConditionBuilder 生成与 phreeqc.dat 兼容的
        正确化学状态 (交换物种 CaX2/MgX2/KX/NaX/AlX3、矿物相不含
        phreeqc.dat 不支持的 anatase 等)。

        参数:
            soil_profile: SoilProfile 对象
            mineral_db_info: 矿物数据库信息
            pCO2: 初始CO2分压 (atm)

        返回:
            SoilState 对象
        """
        from src.initial_condition import InitialConditionBuilder

        builder = InitialConditionBuilder(soil_profile, mineral_db_info, pCO2,
                                          initial_psi_cm=self.initial_psi_cm)

        state = SoilState()
        state.temperature = 25.0
        state.ph = soil_profile.ph

        # 溶液、交换位点、矿物相、气相全部由 InitialConditionBuilder 生成
        state.solution = builder.build_solution()
        state.exchange = builder.build_exchange()
        state.minerals = builder.build_minerals()
        state.gas_phase = builder.build_gas_phase()
        state.volume = builder.solution_volume_L
        # v0.5.3: 初始 θ 由 VGM 从初始水势 (田间持水量) 正算 (D8/Q8),
        # 与化学初始溶液体积严格联动 (同一 θ_init 驱动)
        state.theta = builder.theta_init
        # WF4: SURFACE 表面络合 (Hfo_s/Hfo_w), 默认关闭
        if self.enable_surface:
            state.surface = builder.build_surface() or {}

        return state

    def run_monthly_step(self, state: SoilState,
                         monthly_forcing: dict,
                         action,
                         soil_profile,
                         layer_index=None,
                         n_layers=None) -> Tuple[SoilState, DiagnosticOutput]:
        """执行单月计算步

        参数:
            state: 当前土壤状态
            monthly_forcing: 当月气候强迫
            action: 当月操作指令
            soil_profile: 土壤剖面数据
            layer_index / n_layers (工单86): 分层 KNOBS 迭代透传 (深层可用
                KNOBS_ITERATIONS_DEEP, 当前=500 与工单85 逐位一致; 探针证伪
                1000 负收益, 见 V0_7_x_L4_CONVERGENCE_PERF.md)

        返回:
            (新状态, 诊断输出)
        """
        # 根据模式与后端决定计算路径
        # - simplified 模式: 强制简化
        # - phreeqc 模式: 强制 PHREEQC (失败降级)
        # - auto: PHREEQC 可用则用
        phreeqc_ready = (self.backend == 'official' and self.official is not None
                         and not getattr(self, '_permanent_fallback', False))

        use_phreeqc = phreeqc_ready
        if self.mode == 'simplified':
            use_phreeqc = False
        elif self.mode == 'phreeqc' and not phreeqc_ready:
            use_phreeqc = False

        if use_phreeqc:
            # v0.6.0 (Q10): 事件驱动模式 (main 传 event_driven=True) —
            # 月内逐场闭环 (generate_events → 逐场水文+化学 → 月末浓缩平衡);
            # 缺省旧单次平衡 (预平衡/测试/向后兼容, expand 兼容门禁)
            if monthly_forcing.get('event_driven'):
                return self._run_monthly_step_events(state, monthly_forcing,
                                                     action, soil_profile,
                                                     layer_index=layer_index,
                                                     n_layers=n_layers)
            return self._run_official_step(state, monthly_forcing,
                                           action, soil_profile,
                                           layer_index=layer_index,
                                           n_layers=n_layers)
        else:
            return self._run_simplified_step(state, monthly_forcing,
                                             action, soil_profile)

    def _run_monthly_step_events(self, state: SoilState,
                                 monthly_forcing: dict, action,
                                 soil_profile, layer_index=None,
                                 n_layers=None) -> Tuple[SoilState, DiagnosticOutput]:
        """run_monthly_step 的事件化内部 (v0.6.0, Q3/Q10)

        月内逐场闭环: generate_events(月降水) → 逐场:
          1. 事件级水文步: Green-Ampt 单场入渗 → θ 增量 (入渗水进入含水)
          2. 化学步: run_event_step (体积-θ 耦合, 事件后 θ 驱动 -water)
        → 月末浓缩平衡 (Q12, θ 月内下降才触发, 零额外计算)。

        施肥/石灰 (action) 在第一场事件注入, 其余场次空操作 (月内一次性干预)。
        """
        from src.hydrology import generate_events, green_ampt_infiltration
        seed = monthly_forcing.get('seed', 42)
        year = monthly_forcing.get('year', 0)
        month = monthly_forcing.get('month', 0)
        precip = monthly_forcing.get('precip', 0.0)
        events = generate_events(precip, year, month, seed)
        depth = soil_profile.effective_depth
        theta_s = getattr(soil_profile, 'porosity', 0.5)
        ksat_surface = getattr(soil_profile, 'ksat_surface',
                               DEFAULT_KSAT_SURFACE)
        theta_start = state.theta
        cur_state = state
        last_diag = None
        for idx, ev in enumerate(events):
            # 事件级水文步: Green-Ampt 单场入渗 (θ_i = 事件前 θ)
            inf_mm, _ = green_ampt_infiltration(
                ev.precip_mm, ksat_surface, theta_s=theta_s,
                theta_i=cur_state.theta)
            inf_L = inf_mm * 10000.0
            # 入渗水 → θ 增量 (Δθ = L / (depth_cm × 1e5))
            cur_state.theta += inf_L / (depth * 1e5)
            # 化学步 (第一场注入施肥/石灰, 其余空操作)
            event_action = action if idx == 0 else MonthlyAction()
            eff = {'inflow_water_L': inf_L,
                   'temp': monthly_forcing.get('temp', 25.0),
                   'pCO2': monthly_forcing.get('pCO2', 0.015)}
            cur_state, last_diag = self.run_event_step(
                cur_state, ev, event_action, soil_profile, forcing=eff,
                layer_index=layer_index, n_layers=n_layers)
        # 月末浓缩平衡 (Q12): θ 月内下降 → 浓缩 (无降水事件期干化效应)
        if cur_state.theta < theta_start - 1e-9:
            cur_state, diag2 = self.apply_concentration_equilibrium(
                cur_state, cur_state.theta, soil_profile, monthly_forcing,
                layer_index=layer_index, n_layers=n_layers)
            if diag2 is not None:
                last_diag = diag2
        return cur_state, last_diag

    def run_event_step(self, state: SoilState, event, action,
                       soil_profile, forcing: dict = None,
                       theta_after: float = None,
                       event_out_water_L: float = None,
                       layer_index=None,
                       n_layers=None) -> Tuple[SoilState, DiagnosticOutput]:
        """执行单场降雨事件的化学步 (v0.6.0, Q1/Q3/Q5/Q6)

        事件驱动化学核心: 每场事件一次全量 PHREEQC 平衡。

        - 事件级 forcing: precip = event.precip_mm; inflow_water_L /
          bypass_water_L / inflow_ions 由事件级水文编排注入
          (层间溶质逐场传递, Q4)
        - 体积-θ 耦合 (Q5): SOLUTION -water = θ_事件后×depth×1e5
          (theta_to_water_L), 替换恒定 state.volume; 浓度按质量守恒换算
          (C_new = C_old×V_old/V_new), 干燥→体积小→浓缩酸化自然产生
        - theta_after (v0.6.0): 该场事件后的 θ (事件化水文在 main 预跑时
          传 ev['theta'], 否则用 state.theta); 避免"月末 θ 一次性浓缩"错误
        - 交换相/矿物相绝对摩尔量不变 (Q6): EXCHANGE/EQUILIBRIUM_PHASES mol
          为绝对量, 仅溶液体积随 θ 重建, PHREEQC 自动重平衡浓度
        - 水量效应全部由 -water 体现, REACTION 只注入化学物质
          (inject_water=False)

        参数:
            state: 当前土壤状态 (含上一场事件后的溶液/交换/矿物/体积)
            event: RainEvent (precip_mm/duration_h/precip_chem)
            action: 当月操作指令 (施肥/石灰)
            soil_profile: 土壤剖面数据
            forcing: 事件级补充 forcing dict (可选, 覆盖事件默认)
            theta_after: 该场事件后的 θ (m³/m³); None → state.theta

        返回:
            (新状态, 诊断输出)
        """
        eff = dict(forcing or {})
        eff.setdefault('precip', event.precip_mm)
        eff.setdefault('temp', 25.0)
        eff.setdefault('pCO2', 0.015)

        # 体积-θ 耦合 (Q5): 事件后溶液体积由 θ 决定, 浓度按绝对量守恒换算
        theta_ev = (theta_after if theta_after is not None
                    else state.theta)
        water_target_L = theta_to_water_L(theta_ev,
                                          soil_profile.effective_depth)
        # 工单82 (Q5=A): 平衡体积 = 排水前混合体积 (排水后 θ 体积 + 该场排水)
        # 雨水事件是"换水"(入渗+排水同时) 非蒸发浓缩; 排水溶质由调用方
        # (_run_multi_layer_events) 按摩尔绝对量扣除并回落体积至 θ_out。
        mix_water_L = water_target_L
        if event_out_water_L is not None:
            mix_water_L = water_target_L + max(event_out_water_L, 0.0)
        self._rescale_solution_for_volume(state, mix_water_L,
                                          soil_profile)

        # 模式分派 (与 run_monthly_step 一致)
        phreeqc_ready = (self.backend == 'official' and self.official is not None
                         and not getattr(self, '_permanent_fallback', False))
        use_phreeqc = phreeqc_ready
        if self.mode == 'simplified':
            use_phreeqc = False
        elif self.mode == 'phreeqc' and not phreeqc_ready:
            use_phreeqc = False

        if use_phreeqc:
            return self._run_official_step(state, eff, action, soil_profile,
                                           solution_water_L=mix_water_L,
                                           inject_water=False, path='event',
                                           layer_index=layer_index,
                                           n_layers=n_layers)
        return self._run_simplified_step(state, eff, action, soil_profile)

    def apply_concentration_equilibrium(self, state: SoilState, theta: float,
                                        soil_profile, forcing: dict,
                                        action=None, layer_index=None,
                                        n_layers=None):
        """月末浓缩平衡 (v0.6.0, Q7/Q12)

        旱季无降水事件后: θ 下降 → 仅重设 SOLUTION -water = θ×depth×1e5
        (无 REACTION/降水化学) 做一次浓缩平衡, 浓度按绝对量守恒换算
        → 干燥浓缩酸化进入状态 (对治"月尾 θ 回充掩盖旱季干化"根因)。
        θ 未下降 (月尾回充至 θ_FC) → 跳过, 返回原状态 (零额外计算)。

        返回:
            (new_state, diag) 或 (state, None) (跳过)
        """
        depth = soil_profile.effective_depth
        water_target_L = theta_to_water_L(theta, depth)
        if water_target_L >= state.volume - 1e-9:
            return state, None

        phreeqc_ready = (self.backend == 'official' and self.official is not None
                         and not getattr(self, '_permanent_fallback', False))
        if self.mode == 'simplified' or not phreeqc_ready:
            return state, None   # 简化模式不建模浓缩效应

        # 浓度按绝对量守恒换算 (浓缩), 然后仅重设 -water 平衡
        self._rescale_solution_for_volume(state, water_target_L,
                                          soil_profile)
        eff = dict(forcing)
        eff['precip'] = 0.0
        eff['inflow_water_L'] = None
        eff['bypass_water_L'] = 0.0
        eff['inflow_ions'] = None
        eff['skip_nitrification'] = True
        return self._run_official_step(state, eff, action or MonthlyAction(),
                                       soil_profile,
                                       solution_water_L=water_target_L,
                                       inject_water=False,
                                       layer_index=layer_index,
                                       n_layers=n_layers)

    def _rescale_solution_for_volume(self, state: SoilState,
                                     new_water_L: float, profile=None):
        """体积-θ 耦合的浓度换算 (Q5/Q7 内部): 保持溶质绝对量守恒

        溶液浓度 C (mol/L) × 体积 V (L) = 溶质绝对量 (mol)。-water 从 V_old
        变到 V_new 时, 浓度调整为 C_new = C_old × V_old/V_new, 使总溶质不变
        (干燥浓缩 / 湿润稀释的数学表达)。就地更新 state.solution/volume。

        v0.6.0 数值保护 (E2 实测修复):
          - 体积物理下限: new_water_L ≥ θ_r×depth×1e5 (蒸发浓缩不越过残余含水,
            防浓缩失控 → PHREEQC 不收敛)
          - 单步浓缩比上限: ratio ≤ MAX_CONCENTRATION_RATIO (防单步极端浓缩)
        """
        old_water_L = state.volume
        if old_water_L <= 0 or new_water_L <= 0:
            return
        # 物理下限 (θ ≥ θ_r, VGM 残余含水量)
        if profile is not None:
            from src.vgm import get_vgm_params
            theta_r, _, _ = get_vgm_params(profile)
            min_water_L = theta_r * profile.effective_depth * 1e5
            new_water_L = max(new_water_L, min_water_L)
        ratio = min(old_water_L / new_water_L, MAX_CONCENTRATION_RATIO)
        new_solution = {}
        for k, v in state.solution.items():
            if k in ('temp', 'pH', 'pe', 'units'):
                new_solution[k] = v
            else:
                new_solution[k] = float(v) * ratio
        state.solution = new_solution
        state.volume = new_water_L

    def run_monthly_step_with_timeout(self, state: SoilState,
                                      forcing: dict, action,
                                      soil_profile,
                                      timeout: float = 10.0):
        """子进程执行月度步 + 超时终止 (数值稳定性, v0.6.1)

        KINETICS 偶发 PHREEQC 卡顿 (RunString 不返回, 非确定)——主进程无法
        中断同步调用。此方法用 multiprocessing 子进程执行, 超时强制终止,
        返回 None 表示超时 (调用方应降级)。默认路径 (run_monthly_step) 不变,
        本方法用于定位脚本与超时降级兜底。

        返回:
            (new_state, diag) 或 None (超时/失败)
        """
        import multiprocessing
        ctx = multiprocessing.get_context('spawn')
        q = ctx.Queue()
        p = ctx.Process(
            target=_monthly_step_worker,
            args=(q, self.database, self.mode, self.enable_surface,
                  self.precip_infiltration, self.precip_chem,
                  self.nitrification_k1, self.nitrification_k2,
                  state, forcing, action, soil_profile))
        p.start()
        p.join(timeout)
        if p.is_alive():
            p.terminate()
            p.join()
            logger.error("月度步超时 (%.1fs) — PHREEQC 未返回, 建议降级", timeout)
            return None
        try:
            result = q.get(timeout=2)
        except Exception:
            return None
        if isinstance(result, tuple) and result and result[0] == 'error':
            logger.error("月度步子进程失败: %s", result[1])
            return None
        return result

    def pre_equilibrate(self, state: SoilState, soil_profile,
                        max_steps: int = 100) -> SoilState:
        """前处理预平衡: 观测锚定迭代, 使初始状态在观测约束下自洽 [v0.5.0]

        背景: 初始状态由溶液/交换/矿物三相独立估算拼合, 首次 PHREEQC 平衡
        剧烈重分配 (pH 漂移、交换 Al 被矿物相吸收, L9 根因)。自由预平衡
        实测让 pH 漂移至 2.88 (偏离观测 5.0)——故改为**观测锚定**:
        把 config/CSV 输入的观测 (pH + 全部交换性离子) 作为硬约束,
        通过迭代反馈 (比例-阻尼控制) 修正溶液, 使稳态接近观测。

        实现 (grilling Q1=B/Q2=A/Q3=(a)/Q5=A/Q6):
          - 每步 run_monthly_step 后计算观测偏差 (ΔpH/Δ各交换离子)
          - REACTION 注入修正: pH→H+/OH-, 交换离子→对应阳离子 (顺序迭代)
          - 收敛: ΔpH < 0.3 且各交换离子相对偏差 < 10%, 或 max_steps 截断
          - 锚定仅预平衡期; 长期模拟交换 Al 自由演化 (可耗尽)
          - simplified 引擎跳过

        参数:
            state: 初始构建的状态
            soil_profile: 土壤剖面 (观测 pH/交换离子来源)
            max_steps: 最大迭代步数 (默认 100, Q5=A)

        返回:
            观测锚定后的状态
        """
        if self.mode == 'simplified' or self.backend != 'official':
            return state

        # v0.7.x (工单78): 预平衡阶段用宽松 tolerance (1e-12) — 从远平衡起点稳定;
        # 模拟步用 1e-9 (真收敛, lime 高 pH 不假收敛)。_build_phreeqc_input 读此标志。
        self._in_pre_equilibration = True
        try:
            return self._pre_equilibrate_inner(state, soil_profile, max_steps)
        finally:
            self._in_pre_equilibration = False

    def _pre_equilibrate_inner(self, state: SoilState, soil_profile,
                               max_steps: int = 100) -> SoilState:
        """预平衡主体 (观测锚定迭代, 在 _in_pre_equilibration 标志下执行)"""

        from src.initial_condition import InitialConditionBuilder
        from src.scenario_controller import MonthlyAction
        # 观测目标: 交换离子 (cmol/kg → mol, 与 build_exchange 换算一致)
        builder = InitialConditionBuilder(
            soil_profile, None,
            pCO2=state.gas_phase.get('CO2(g)', 0.015))
        targets = builder.build_exchange()
        target_ph = soil_profile.ph

        # 工单 17: 偏离度诊断快照 (初始 vs 稳态)
        init_snapshot = {'pH': state.ph}
        for ion in ('CaX2', 'MgX2', 'KX', 'NaX', 'AlX3', 'HX'):
            init_snapshot[ion] = state.exchange.get(ion, 0.0)

        action = MonthlyAction()
        current = state
        # 先平衡一步 (暴露首次平衡的观测漂移)
        forcing = {'precip': 0.0, 'temp': current.temperature,
                   'pCO2': current.gas_phase.get('CO2(g)', 0.015)}
        current, _ = self.run_monthly_step(current, forcing, action,
                                           soil_profile)
        # 迭代修正: 计算观测偏差 → 注入拉回 → 再平衡, 直到收敛
        for _ in range(max_steps - 1):
            injection = self._compute_anchor_injection(
                current, targets, target_ph)
            if not injection:
                break   # 观测偏差全部收敛
            forcing = {'precip': 0.0, 'temp': current.temperature,
                       'pCO2': current.gas_phase.get('CO2(g)', 0.015),
                       'injection': injection}
            current, _ = self.run_monthly_step(current, forcing, action,
                                               soil_profile)

        # 工单 17: 偏离度诊断 (初始 vs 稳态)
        self.last_pre_equilibration_diagnostics = {
            'pH': (init_snapshot['pH'], current.ph),
        }
        for ion in ('CaX2', 'MgX2', 'KX', 'NaX', 'AlX3', 'HX'):
            self.last_pre_equilibration_diagnostics[ion] = (
                init_snapshot[ion], current.exchange.get(ion, 0.0))
        self._log_pre_equilibration_diagnostics()
        return current

    def _compute_anchor_injection(self, state, targets: dict,
                                  target_ph: float) -> dict:
        """计算交换离子锚定修正注入 (比例-阻尼控制, v0.5.0 支柱②)

        v0.5.0: **移除 pH 锚定** — GAS_PHASE 固定分压 CO2 会缓冲吸收碱
        (实测注入 H -3000/-10000/-30000 结果完全相同 pH 3.612), 锚定 pH
        无效。pH 自然平衡并记录于偏离度诊断 (支柱① 缺口修正后自然接近观测)。

        返回空 dict 表示全部交换离子观测偏差已收敛 (<10%)。
        """
        injection = {}
        # v0.6.1 (spec 62 Q7): HX 为标定酸库 (log_k=HX_LOGK 扫描标定, 平衡量由
        # 热力学决定, 非观测锚定输入) — 不纳入观测锚定; 盐基阳离子
        # (Ca/Mg/K/Na/Al) 为观测交换离子, 锚定保持 <10% 偏差。
        # v0.6.1 防冲垮: 偏差 >50% 的离子跳过锚定 — 明显非物理偏差 (如 HX
        # 酸库占位排挤 AlX3 至 -86%) 强行拉回会使注入量级过大冲垮交换相
        # (实测注入 -1.6e4 Al 后交换相全归零), 温和校正 + 诊断记录更稳。
        sp_map = {'CaX2': 'Ca+2', 'MgX2': 'Mg+2', 'KX': 'K+',
                  'NaX': 'Na+', 'AlX3': 'Al+3'}
        for ion, target in targets.items():
            if target <= 0 or ion not in sp_map:
                continue
            cur = state.exchange.get(ion, 0.0)
            dev = (cur - target) / target
            if abs(dev) > PRE_EQUIL_ION_TOL and abs(dev) <= 0.5:
                injection[sp_map[ion]] = (
                    injection.get(sp_map[ion], 0.0)
                    + dev * target * PRE_EQUIL_ION_GAIN)
        return injection

    def _log_pre_equilibration_diagnostics(self):
        """日志输出预平衡偏离度诊断 + 阈值警示 (工单 17, Q5=A)

        科学判据 (初值, 实测后校准): ΔpH < 0.5 且各交换性离子相对变化 < 20%
        视为"输入参数物理合理" (稳态接近观测); 超出则警示。
        """
        if not getattr(self, 'last_pre_equilibration_diagnostics', None):
            return
        diag = self.last_pre_equilibration_diagnostics
        d_ph = abs(diag['pH'][1] - diag['pH'][0])
        lines = ['初始状态预平衡完成:']
        lines.append('  pH: %.3f -> %.3f (Δ=%.3f)' % (
            diag['pH'][0], diag['pH'][1], d_ph))
        warn = d_ph > 0.5
        for ion in ('CaX2', 'MgX2', 'KX', 'NaX', 'AlX3', 'HX'):
            init_v, eq_v = diag[ion]
            rel = (abs(eq_v - init_v) / max(abs(init_v), 1e-6)) * 100.0
            lines.append('  %s: %.3e -> %.3e (相对变化 %.1f%%)' % (
                ion, init_v, eq_v, rel))
            if rel > 20.0:
                warn = True
        if warn:
            logger.warning('预平衡偏离度超阈值 (ΔpH>0.5 或交换离子变化>20%%): '
                           '输入参数可能不物理, 请检查观测值', extra=None)
            logger.warning('  ' + '\n  '.join(lines[1:]))
        else:
            logger.info('  ' + '\n  '.join(lines[1:]))

    def run_monthly_multi_layer(self, states: list,
                                monthly_forcing: dict,
                                action,
                                soil_profile,
                                layer_pco2s=None,
                                hydrology=None) -> Tuple[list, list]:
        """执行多分层月度计算步 (WF2, 基于 WF1 架构决策)

        架构 (WF1 Q1-Q4, Q7):
          - Q1: List[SoilState] — 每层独立完整状态
          - Q3: 级联下渗 — 最上层接受 precip×infiltration, 每层平衡后
               超出持水水量(含溶质)逐层下渗, 最底层流失
          - Q2/Q7: 一维平流 — 上层排水量 × 平衡后溶液浓度(SELECTED_OUTPUT
               totals) = 移出摩尔量, 作为下层 REACTION 输入 (守恒)
          - Q4: run_monthly_step 单层接口不变 (深模块), 此处是高层编排层

        L6 (v0.4.0): 可选逐层 pCO₂ — 各层月度 GAS_PHASE 固定分压按层注入
          (真实剖面表层低/底层高的 pCO₂ 梯度全程保持), 缺省回退全局 forcing。

        v0.5.0 水文模式: hydrology = {'inflows': List[L/ha], 'drains': List[L/ha]}
          - inflows[i]: 第 i 层本月注入水量 (层1=入渗, 下层=上层排水), 替代
            precip×infiltration 计算; 进入 REACTION H2O 与降水化学离子
          - drains[i]: 第 i 层排水量 (Ksat 限制后), 用于层间溶质传递

        v0.6.0 事件级水文模式 (Q4/Q10): hydrology 含可选 'events' 键
          - events = List[dict], 每场含 inflows/drains/bypass_water_L/precip_mm
          - 逐场逐层级联: for event: for layer: run_event_step (层间溶质
            事件粒度传递, First-Flush 本质)
          - 无 events 键 → 旧月级路径 (向后兼容护栏)

        参数:
            states: List[SoilState] — 各层当前状态 (长度 = n_layers)
            monthly_forcing: 当月气候强迫
            action: 当月操作指令
            soil_profile: 土壤剖面数据 (各层默认参数相同, ROADMAP 约束)
            layer_pco2s: List[float] 或 None — 各层 pCO₂ 覆盖值 (长度=n_layers)
            hydrology: dict 或 None — 水文模式各层入渗/排水量

        返回:
            (List[SoilState], List[DiagnosticOutput]) — 更新后各层状态与诊断
        """
        n = len(states)
        if n == 1:
            # 回归护栏: 单层走原接口 (WF1 Q4)
            new_state, diag = self.run_monthly_step(
                states[0], monthly_forcing, action, soil_profile)
            return [new_state], [diag]

        # v0.6.0 (Q4): 事件级水文模式 — hydrology['events'] 逐场逐层级联
        event_list = (hydrology or {}).get('events')
        if event_list:
            return self._run_multi_layer_events(
                states, monthly_forcing, action, soil_profile,
                layer_pco2s, event_list, hydrology)

        new_states = []
        diags = []
        # 级联下渗: 上一层排出的溶质 (mol) 注入下一层
        inflow_ions = {}  # 初始为 None: 最上层无层间输入
        for i in range(n):
            layer_forcing = dict(monthly_forcing)
            # L6: 逐层 pCO₂ 注入 (缺省回退全局 forcing['pCO2'])
            if layer_pco2s is not None:
                layer_forcing['pCO2'] = layer_pco2s[i]
            # v0.5.2: 硝化产酸仅 L1 (表层酸化源强化); 深层跳过氮过程
            if i > 0:
                layer_forcing['skip_nitrification'] = True
            # v0.5.0: 水文模式各层注入水量 (替代 precip×infiltration)
            if hydrology:
                layer_forcing['inflow_water_L'] = hydrology['inflows'][i]
                # v0.5.2: 大孔隙优先流 — 绕过表层积水直通 L2 (犁底层),
                # 携带原始降水化学 (在 _build_phreeqc_input 中按水量注入)
                if i == 1 and hydrology.get('bypass_water_L', 0.0) > 0:
                    layer_forcing['bypass_water_L'] = hydrology['bypass_water_L']
            if inflow_ions:
                # 下层: 接收上层排水溶质 (Q2/Q7 平流守恒)
                layer_forcing['inflow_ions'] = inflow_ions
            # 工单86 (2026-08-31): 分层 KNOBS 迭代透传 (深层 L3/L4 用
            # KNOBS_ITERATIONS_DEEP, 当前=500; 探针证伪 1000 负收益)
            new_state, diag = self.run_monthly_step(
                states[i], layer_forcing, action, soil_profile,
                layer_index=i, n_layers=n)
            new_states.append(new_state)
            diags.append(diag)

            # 计算本层排水携带的溶质 → 作为下一层输入 (Q7 守恒核算)
            if i < n - 1:
                if hydrology:
                    # v0.5.0: 排水量由水文级联 (Ksat 限制) 决定
                    drain_water_L = hydrology['drains'][i]
                else:
                    # 排水量 = 入渗水量 (L), 由 precip_infiltration 决定
                    # 1 mm 降水 × 10000 m2/ha × 入渗系数 = L/ha (与引擎内一致)
                    drain_water_L = (monthly_forcing.get('precip', 0.0)
                                     * 10000.0 * self.precip_infiltration)
                inflow_ions = {}
                for ion, conc in new_state.solution.items():
                    if ion in ('temp', 'pH', 'pe', 'units'):
                        continue
                    # totals (mol/kgw ≈ mol/L) × 排水水量(L) = 移出摩尔量
                    if conc > 0:
                        inflow_ions[ion] = conc * drain_water_L

        return new_states, diags

    def _grade_companion_injection(self, e_loss_eq: float, bs: float):
        """v0.7.0 (工单71, spec 69): 伴随淋失分级注入 (Q18=A)

        按层盐基饱和度 BS 动态选择注入策略 (专家方案 D):
          - BS ≥ bs_high: 全量注入 CompAn- (交换相盐基充足, Gapon 正常驱动解吸)
          - bs_low ≤ BS < bs_high: CompAn- × 线性衰减 (BS−bs_low)/(bs_high−bs_low)
          - BS < bs_low: 切换酸化注入 H+ = E_loss 当量 (交换相盐基枯竭,
            继续 InertAnion 会拽 Al/H 异常压 pH; H+ 主导酸化更物理)

        返回: (anion_eq, acid_eq, mode) — mode ∈ inert/hybrid/acid
        """
        bs_high = self.companion_cfg.bs_high
        bs_low = self.companion_cfg.bs_low
        if bs >= bs_high:
            return e_loss_eq, 0.0, 'inert'
        if bs >= bs_low:
            frac = (bs - bs_low) / (bs_high - bs_low)
            return e_loss_eq * frac, 0.0, 'hybrid'
        return 0.0, e_loss_eq, 'acid'

    def _grade_base_leaching(self, e_base_eq: float, bs: float):
        """v0.7.x (工单80): 盐基淋失 E_base 分级降权 (Q5=A)

        按层盐基饱和度 BS 动态降权 (Q3=C: 全情景含 natural 自然保护):
          - BS ≥ bs_high: 全量注入 An- (交换相盐基充足, Gapon 正常驱动解吸)
          - bs_low ≤ BS < bs_high: An- × 线性衰减 (BS−bs_low)/(bs_high−bs_low)
          - BS < bs_low: 归零 (zero, 不注酸) — E_base 角色是"盐基淋失"而非
            "酸化注入"; 酸化由硝化产酸/companion acid 负责; 防 natural 长期
            BS 下降后被本通道额外注酸拉出 4.5~5.0 带

        返回: (anion_eq, mode) — mode ∈ inert/hybrid/zero
        """
        bs_high = self.base_leaching_cfg.bs_high
        bs_low = self.base_leaching_cfg.bs_low
        if bs >= bs_high:
            return e_base_eq, 'inert'
        if bs >= bs_low:
            frac = (bs - bs_low) / (bs_high - bs_low)
            return e_base_eq * frac, 'hybrid'
        return 0.0, 'zero'

    def _run_multi_layer_events(self, states: list, monthly_forcing: dict,
                                action, soil_profile, layer_pco2s,
                                event_list: list, hydrology: dict = None):
        """v0.6.0 (Q4): 逐场逐层级联 (层间溶质事件粒度传递, First-Flush 本质)

        hydrology['events'] 驱动: 每场事件按层顺序执行 run_event_step,
        该场上层排水携带溶质 (conc×drain) 作为下层当场 inflow_ions。
        施肥/石灰 (action) 仅第一场事件注入 (月内一次性干预)。
        Q14: 每场每层淋失明细回填 hydrology['event_details'] (事件 CSV 用)。

        返回:
            (List[SoilState], List[DiagnosticOutput]) — 最后一场事件后各层状态
        """
        from src.hydrology import RainEvent
        n = len(states)
        new_states = list(states)
        last_diags = [None] * n
        # v0.6.0 (Q14): First-Flush 峰值 (当月 L1 最大单场淋失, mmol/ha)
        flush_no3_peak = 0.0
        flush_base_peak = 0.0
        event_details = []
        # v0.7.0 (工单71): 各层"上一场淋失产生的伴随当量"待下场平衡前注入
        # (跨场保留: 本场淋失 → 下一场注入, 逐场滚动)
        pending_e_loss = [0.0] * n
        # v0.7.x (工单80): 盐基淋失 E_base 跨场滚动 (本场淋失 → 下场注入 An-)
        pending_e_base = [0.0] * n
        for ev_idx, ev in enumerate(event_list):
            layer_states = []
            inflow_ions = {}
            # v0.7.0 (工单70): 本场层间 NO3- 池下移/bypass 携带的传递量 (mol)
            pool_carry = 0.0
            event_action = action if ev_idx == 0 else MonthlyAction()
            row = {'year': monthly_forcing.get('year', 0),
                   'month': monthly_forcing.get('month', 0),
                   'event': ev_idx + 1,
                   'precip_mm': ev.get('precip_mm', 0.0)}
            for i in range(n):
                # v0.7.0 (工单70): 吸收上层 drains 下移/bypass 携带的 NO3- 池
                # (水库串联: 上层排出的池质量逐层下移, 先处理上层后下层)
                if i > 0 and pool_carry > 0:
                    new_states[i].n_no3_pool += pool_carry
                    pool_carry = 0.0
                layer_forcing = dict(monthly_forcing)
                # L6: 逐层 pCO₂ 注入 (缺省回退全局 forcing['pCO2'])
                if layer_pco2s is not None:
                    layer_forcing['pCO2'] = layer_pco2s[i]
                # v0.5.2: 硝化产酸仅 L1; 深层跳过氮过程
                if i > 0:
                    layer_forcing['skip_nitrification'] = True
                # 事件级水量: 该场入渗/排水/优先流
                layer_forcing['inflow_water_L'] = ev['inflows'][i]
                if i == 1 and ev.get('bypass_water_L', 0.0) > 0:
                    layer_forcing['bypass_water_L'] = ev['bypass_water_L']
                if inflow_ions:
                    layer_forcing['inflow_ions'] = inflow_ions
                # v0.7.0 (工单71, spec 69): 伴随淋失分级注入 — 上一场淋失的
                # 盐基当量 (E_loss) 在本场平衡前经 REACTION 注入 (CompAn-/H+),
                # 交换相由平衡自洽解吸 (Gapon 哲学, Q11=E 方案)
                companion_anion_eq = 0.0
                companion_acid_eq = 0.0
                companion_mode = 'none'
                if self.companion_enabled and pending_e_loss[i] > 0:
                    bs = calc_base_saturation(new_states[i].exchange,
                                              include_hx=True)
                    companion_anion_eq, companion_acid_eq, companion_mode = \
                        self._grade_companion_injection(pending_e_loss[i], bs)
                    if companion_mode == 'acid':
                        logger.warning(
                            "v0.7.0 伴随淋失: 层 %d 盐基枯竭 (BS=%.1f%% < %.0f%%), "
                            "切换酸化注入 H+ = %.2f eq",
                            i + 1, bs, self.companion_cfg.bs_low,
                            companion_acid_eq)
                layer_forcing['companion_anion_eq'] = companion_anion_eq
                layer_forcing['companion_acid_eq'] = companion_acid_eq
                # v0.7.x (工单80): 盐基淋失伴随注入 — 上一场 E_base 在本场平衡前
                # 经 REACTION 注入 An- (Q4=A: 离开本层全部水携带的盐基当量);
                # BS 分级降权 (Q5=A: <bs_low 归零不注酸), 交换相由 Gapon 自洽
                base_anion_eq = 0.0
                base_mode = 'none'
                if self.base_leaching_enabled and pending_e_base[i] > 0:
                    bs = calc_base_saturation(new_states[i].exchange,
                                              include_hx=True)
                    base_anion_eq, base_mode = self._grade_base_leaching(
                        pending_e_base[i], bs)
                    if base_mode == 'zero':
                        logger.debug(
                            "v0.7.x 盐基淋失: 层 %d BS=%.1f%% < %.0f%%, "
                            "E_base 归零 (不注酸)", i + 1, bs,
                            self.base_leaching_cfg.bs_low)
                layer_forcing['base_anion_eq'] = base_anion_eq
                rain_ev = RainEvent(precip_mm=ev.get('precip_mm', 0.0),
                                    duration_h=2.0)
                # 该场事件后的 θ (事件化水文已逐场更新, ev['theta'] 记录)
                theta_ev = (ev.get('theta') or [None] * n)[i]
                # 工单82 (Q5=A): 该场该层排水总量 (drains+lateral+baseflow),
                # 传给 run_event_step 作为平衡体积 (V_mix = θ_out×d×1e5 + out)
                out_ev_L = ((ev.get('drains') or [0.0] * n)[i]
                            + (ev.get('lateral') or [0.0] * n)[i]
                            + (ev.get('baseflow') or [0.0] * n)[i])
                new_state, diag = self.run_event_step(
                    new_states[i], rain_ev, event_action, soil_profile,
                    forcing=layer_forcing, theta_after=theta_ev,
                    event_out_water_L=out_ev_L,
                    layer_index=i, n_layers=n)
                layer_states.append(new_state)
                last_diags[i] = diag
                # ---- v0.7.0 (工单70, spec 69): NO3- 示踪池水库串联淋失 ----
                # 池随水移出 (垂直下移/侧向/基流/bypass), 全局不变量 pool≥0
                # (calc_no3_leaching 内部 min(公式, pool) 防抽干, Q19)
                leach_no3_i = 0.0
                if self.companion_enabled:
                    v_pool = max(new_state.volume, 1.0)
                    drain_i = ev['drains'][i]
                    lat_out_L = (ev.get('lateral') or [0.0] * n)[i]
                    base_out_L = (ev.get('baseflow') or [0.0] * n)[i]
                    # ① 垂直下移: drains 携带池 → 下一层 (水库串联)
                    mass_down = calc_no3_leaching(
                        new_state.n_no3_pool, drain_i, v_pool)
                    new_state.n_no3_pool -= mass_down
                    leach_no3_i += mass_down
                    if i < n - 1:
                        pool_carry += mass_down
                    # ② 出系统: lateral + baseflow 带走池余额
                    lost_out = calc_no3_leaching(
                        new_state.n_no3_pool, lat_out_L + base_out_L, v_pool)
                    new_state.n_no3_pool -= lost_out
                    leach_no3_i += lost_out
                    # ③ bypass 携带: L1 池 NO3- 直通 L2 (默认模式, 深度分布留 v0.7.x)
                    if i == 0:
                        bypass_water = ev.get('bypass_water_L', 0.0)
                        if bypass_water > 0 and self.companion_bypass_no3_carry:
                            m_bypass = calc_no3_leaching(
                                new_state.n_no3_pool, bypass_water, v_pool)
                            new_state.n_no3_pool -= m_bypass
                            leach_no3_i += m_bypass
                            pool_carry += m_bypass
                # 记账列 (v0.7.0): 池存量 + 该场淋失量
                row[f'n_no3_pool_L{i+1}'] = new_state.n_no3_pool
                row[f'leach_no3_L{i+1}_mol'] = leach_no3_i
                # v0.7.x (工单80): 盐基淋失 E_base — 仅对模型实际带走的盐基通道配对
                # (lateral+baseflow 出系统, Q3 同通道; 排除 drains — 事件路径不搬
                # 溶质, drains 项会形成"纯 An- 泵"正反馈: 注入拽盐基→盐基滞留→
                # E_base 又涨→交换相耗尽→Al³⁺ 水解酸化崩盘, 2026-08-24 探针证伪
                # Q4 全水道草案; 修正为出系统出口, 自限无正反馈)
                base_loss_eq_i = 0.0
                if self.base_leaching_enabled:
                    q_out_system = ((ev.get('lateral') or [0.0] * n)[i]
                                    + (ev.get('baseflow') or [0.0] * n)[i])
                    v_pool = max(new_state.volume, 1.0)
                    base_total_eq = solution_base_eq(
                        new_state.solution, new_state.volume)
                    base_loss_eq_i = calc_base_leaching(
                        base_total_eq, q_out_system, v_pool,
                        eq_floor=(self.base_leaching_cfg.c_floor_mmol_L
                                  * 1e-3 * v_pool))
                    pending_e_base[i] = base_loss_eq_i
                row[f'base_loss_eq_L{i+1}'] = base_loss_eq_i
                row[f'base_mode_L{i+1}'] = base_mode
                row[f'e_base_anion_eq_L{i+1}'] = base_anion_eq
                # 记账列 (v0.7.0, 工单71): 伴随淋失分级注入记录
                # (本场注入 = 上一场淋失当量的分级结果; 本场淋失 → 下一场注入)
                row[f'companion_mode_L{i+1}'] = companion_mode
                row[f'companion_eq_L{i+1}'] = pending_e_loss[i]
                row[f'inert_eq_L{i+1}'] = companion_anion_eq
                row[f'acid_eq_L{i+1}'] = companion_acid_eq
                pending_e_loss[i] = leach_no3_i
                # 记账列 (v0.7.0, 工单72): NH4+ 置换当量 (施肥月 L1 硝化量×k2;
                # 工单76 调优 A: 从水解量改为硝化量, 抑制盐基过量注入)
                nh4_exchanged_i = 0.0
                if (self.companion_enabled
                        and self.companion_cfg.nh4_exchange
                        and ev_idx == 0 and i == 0
                        and getattr(action, 'apply_fertilizer', False)):
                    nh4_exchanged_i = (
                        getattr(action, 'n_amount', 0.0) * N_MOL_PER_KG_N
                        * self.nitrification_k1 * self.nitrification_k2)
                row[f'nh4_exchanged_eq_L{i+1}'] = nh4_exchanged_i
                # ---- 工单82 (Q5=A/Q2=A): 排水溶质摩尔绝对量扣除 + 体积落回 θ_out ----
                # 事件平衡已在 V_mix = θ_out×depth×1e5 + 排水总量 (排水前混合体积)
                # 上完成 (run_event_step 的 event_out_water_L)。雨水事件是"换水"
                # (入渗+排水同时), 排水不浓缩残留水 — 摩尔绝对量守恒:
                #   - drains 通道: mol_out = C×drain (i<n-1 进下层 inflow_ions;
                #     L4 无下层 = 深层出系统)
                #   - lateral+baseflow 通道: mol_out = C×(lat+base) (出系统)
                #   - 残留溶质 = C×V_mix − Σmol_out; 残留体积 = θ_out×d×1e5
                #   - 残留浓度 = 残留mol/残留体积 (≈ C, 物理"换水不浓缩")
                # 修复旧 Q3 比例法 frac=min(Q_out/V,1) 在 q_out>V (L4 基流
                # 99.6万L vs 48万L) 时钳到 1 → 溶质全清 C_MIN 的物理失真。
                # 交换相不动靠后续平衡 Gapon 补偿 (spec 62 Q3 决策不变)。
                drain_water_L = ev['drains'][i]
                lat_out_L = (ev.get('lateral') or [0.0] * n)[i]
                base_out_L = (ev.get('baseflow') or [0.0] * n)[i]
                q_out_system_L = lat_out_L + base_out_L
                vol_mix = max(new_state.volume, 1.0)      # 平衡后体积 = V_mix
                theta_eff = theta_ev if theta_ev is not None else new_state.theta
                water_after_L = max(
                    theta_to_water_L(theta_eff,
                                     soil_profile.effective_depth), 1e-6)
                moved_ions = {}
                q3_out_ions = {}
                if drain_water_L > 0:
                    for ion, conc in new_state.solution.items():
                        if ion in ('temp', 'pH', 'pe', 'units'):
                            continue
                        if conc > 0:
                            moved_ions[ion] = conc * drain_water_L
                if q_out_system_L > 0:
                    for ion, conc in new_state.solution.items():
                        if ion in ('temp', 'pH', 'pe', 'units'):
                            continue
                        if conc > 0:
                            q3_out_ions[ion] = conc * q_out_system_L
                for ion, conc in list(new_state.solution.items()):
                    if ion in ('temp', 'pH', 'pe', 'units'):
                        continue
                    n_rem = (conc * vol_mix - moved_ions.get(ion, 0.0)
                             - q3_out_ions.get(ion, 0.0))
                    new_state.solution[ion] = max(
                        n_rem / water_after_L, C_MIN)
                new_state.volume = water_after_L
                total_lateral_i = lat_out_L
                total_base_i = base_out_L
                flush_L = 0.0
                # 浓度冲洗 (Q6: C_warn 超限 → 折算额外水量出口 + 同比例扣溶质)
                sol_conc = {k: v for k, v in new_state.solution.items()
                            if k not in ('temp', 'pH', 'pe', 'units')}
                max_c = max(sol_conc.values()) if sol_conc else 0.0
                if max_c > CONC_WARN:
                    excess = max_c - CONC_WARN
                    flush_L = water_after_L * (excess / max_c)
                    if flush_L > 0:
                        frac_flush = min(flush_L / water_after_L, 1.0)
                        for ion, conc in list(new_state.solution.items()):
                            if ion in ('temp', 'pH', 'pe', 'units'):
                                continue
                            new_state.solution[ion] = max(
                                conc * (1.0 - frac_flush), C_MIN)
                # 出口记账 → event_details + 月度诊断列
                row[f'lateral_L{i+1}_L'] = total_lateral_i
                row[f'baseflow_L{i+1}_L'] = total_base_i
                row[f'flush_L{i+1}_L'] = flush_L
                # 该场该层淋失明细 (Q14, mmol/ha = conc(mol/L)×drain(L)×1000)
                drain_i = ev['drains'][i]
                row[f'leach_N_L{i+1}_mmol'] = \
                    new_state.solution.get('N', 0.0) * drain_i * 1000.0
                row[f'leach_base_L{i+1}_mmol'] = (
                    new_state.solution.get('Ca', 0.0)
                    + new_state.solution.get('Mg', 0.0)
                    + new_state.solution.get('K', 0.0)) * drain_i * 1000.0
                row[f'ph_L{i+1}'] = new_state.ph
                # First-Flush 记录: L1 该场淋失 (mmol/ha)
                if i == 0:
                    no3_mmol = new_state.solution.get('N', 0.0) \
                        * ev['drains'][0] * 1000.0
                    base_mmol = (new_state.solution.get('Ca', 0.0)
                                 + new_state.solution.get('Mg', 0.0)
                                 + new_state.solution.get('K', 0.0)) \
                        * ev['drains'][0] * 1000.0
                    flush_no3_peak = max(flush_no3_peak, no3_mmol)
                    flush_base_peak = max(flush_base_peak, base_mmol)
                # 该场排水携带溶质 → 下层当场输入 (Q4 事件粒度, 工单82 Q2=A:
                # 用平衡后 V_mix 浓度×drain 的摩尔绝对量 moved_ions, 与扣除同源)
                if i < n - 1 and drain_water_L > 0:
                    inflow_ions = moved_ions
            new_states = layer_states
            event_details.append(row)
        # Q14: 事件明细回填 (main 经 hydrology['event_details'] 写事件 CSV)
        if hydrology is not None:
            hydrology['event_details'] = event_details
        # First-Flush 峰值附加到 L1 诊断 (Q14, main 经 diag_objs 提取)
        diags_out = list(last_diags)
        if diags_out[0] is not None:
            diags_out[0].flush_no3_peak_mmol = flush_no3_peak
            diags_out[0].flush_base_peak_mmol = flush_base_peak
        return new_states, diags_out

    def _warning_count(self) -> int:
        """PHREEQC 当前警告行数 (本次 RunString 后增量判断用)"""
        try:
            return self.official.GetWarningStringLineCount()
        except Exception:
            return 0

    def _has_new_convergence_warning(self, before: int) -> bool:
        """本次 RunString 新增警告含收敛失败关键词 (超限/数值方法失败)

        PHREEQC 在 KNOBS 迭代超限时不抛异常、返回垃圾解 (交换相全 0/溶液
        不变), 需检测防污染状态链 (工单78, 2026-08-24 探针)。
        """
        try:
            n = self.official.GetWarningStringLineCount()
        except Exception:
            return False
        if n <= before:
            return False
        for i in range(before, n):
            try:
                line = self.official.GetWarningStringLine(i) or ''
            except Exception:
                continue
            if ('Maximum iterations' in line
                    or 'Numerical method failed' in line):
                return True
        return False

    def _run_official_step(self, state, forcing, action, profile,
                           solution_water_L=None, inject_water=True,
                           path='monthly', layer_index=None,
                           n_layers=None):
        """使用官方 phreeqc (IPhreeqc 3.8.6) 引擎执行计算步

        参数:
            solution_water_L (v0.6.0): 目标溶液体积 (L), 体积-θ 耦合用
                (run_event_step 传 θ×depth×1e5); None=用 state.volume (月级现状)
            inject_water (v0.6.0): 是否注入入渗水 H2O (体积耦合时 False,
                水量已由 -water 体现, REACTION 只注入化学物质)
        """
        # L4: 推进氮形态库存 (尿素→NH4+→NO3-, 简化两步), 返回本月氮反应量
        # 独立函数 + 返回契约 → 将来可替换为 KINETICS 实现 (升级空间)
        # v0.4.0: 硝化速率由引擎配置 (config.simulation.nitrification_k1/k2)
        # v0.5.2: 硝化产酸仅 L1 (表层酸化源强化); 深层 (skip_nitrification)
        # 跳过全部氮过程 (氮不随层间传递, 完整氮运移留待 v0.6.0 子步长)
        if forcing.get('skip_nitrification'):
            n_reaction = {}
        else:
            n_reaction = advance_nitrification(
                state, action,
                k1=self.nitrification_k1, k2=self.nitrification_k2)
        # 构建 PHREEQC 输入字符串 (含 SELECTED_OUTPUT 查询块)
        input_string = self._build_phreeqc_input(
            state, forcing, action, profile, n_reaction=n_reaction,
            solution_water_L=solution_water_L, inject_water=inject_water,
            layer_index=layer_index, n_layers=n_layers)

        try:
            warn_before = self._warning_count()
            self.official.RunString(input_string)
            # v0.7.x (工单78): 收敛失败检测 — 模拟步 1e-9 迭代超限时自动重试。
            # 工单82 (Q6=A, 2026-08-25): 废弃 1e-12 宽松兜底 — 1e-12 静默假收敛
            # (lime 高 pH 4.89 错 vs 1e-9 10.18 对) 已证伪; 提高迭代 (1e-9 真收敛)
            # 仍失败 → 直接判定收敛失败走 fallback 计数 (连续 N=3 才永久降级),
            # 绝不回落 1e-12 把假收敛写回状态链。
            # 工单86 (2026-08-31): 重试迭代跟随实际分层首次迭代数 × 倍数
            # (当前深层=浅层=500 → 重试 1000, 与工单78~85 一致; 探针证伪
            # 深层 1000 负收益, D 工单后若启用分层再动态跟随)
            if (self._has_new_convergence_warning(warn_before)
                    and not self._in_pre_equilibration):
                logger.warning(
                    "PHREEQC 模拟步收敛失败 (迭代超限), 提高迭代重试")
                retry_iters = max(
                    int(self._pick_knobs_iterations(layer_index, n_layers)
                        * KNOBS_RETRY_MULTIPLIER),
                    500)
                retry_string = self._build_phreeqc_input(
                    state, forcing, action, profile, n_reaction=n_reaction,
                    solution_water_L=solution_water_L, inject_water=inject_water,
                    knobs_iterations=retry_iters,
                    layer_index=layer_index, n_layers=n_layers)
                warn_before = self._warning_count()
                self.official.RunString(retry_string)
                if self._has_new_convergence_warning(warn_before):
                    logger.warning(
                        "PHREEQC 模拟步提高迭代仍不收敛 (1e-9), 判定收敛失败 → "
                        "fallback (不回落 1e-12 假收敛)")
                    raise RuntimeError(
                        "PHREEQC 未收敛 (Maximum iterations exceeded)")
                input_string = retry_string
            new_state, diag = self._parse_official_output(
                state, solution_water_L=solution_water_L)
            # v0.6.1 (Q5): 单次成功重置对应路径的连续失败计数 (滑动窗口)
            if path == 'event':
                self._consecutive_failures_event = 0
            else:
                self._consecutive_failures_monthly = 0
            return new_state, diag
        except Exception as e:
            # Q18 修复: 记录完整诊断 (错误详情 + 输入字符串落盘可复现)
            self.last_error_message = str(e)
            self.last_error_input = input_string
            # T01 修复: 失败输入写入磁盘复现文件 (README 承诺的 error.inp)
            # 路径固定为 output/ 运行产物目录 (gitignore 已忽略), 写入前确保目录存在;
            # 写入失败不影响主流程 (降级继续), 仅记录日志
            try:
                err_path = Path(ERROR_INP_PATH)
                err_path.parent.mkdir(parents=True, exist_ok=True)
                err_path.write_text(input_string, encoding='utf-8')
            except Exception as write_err:
                logger.warning("无法写入 PHREEQC 失败输入复现文件 %s: %s",
                               ERROR_INP_PATH, write_err)
            # v0.6.1 (spec 62 Q5): 事件级局部降级 — 连续 N 次失败才永久降级
            # 失败场保留前一正常状态跳过 (不调 simplified, 化学连续性最好);
            # 事件/月级路径分开计数 (Q5 决策)
            if path == 'event':
                self._consecutive_failures_event += 1
                n_fails = self._consecutive_failures_event
            else:
                self._consecutive_failures_monthly += 1
                n_fails = self._consecutive_failures_monthly
            if n_fails >= FALLBACK_MAX_CONSECUTIVE:
                if not getattr(self, '_fallback_warned', False):
                    logger.error("PHREEQC 连续 %d 次计算失败: %s",
                                 n_fails, e, exc_info=True)
                    logger.debug("失败输入:\n%s", input_string)
                    logger.warning("已永久降级到简化模式继续模拟")
                    self._fallback_warned = True
                self._permanent_fallback = True
                return self._run_simplified_step(state, forcing, action,
                                                 profile)
            # 未达阈值: 保留前一正常状态跳过该场 (事件级局部降级, Q5)
            if not getattr(self, '_fallback_warned', False):
                logger.warning("PHREEQC 单场计算失败 (%s): %s — 保留前状态跳过, "
                               "连续失败 %d/%d 后永久降级", path, e, n_fails,
                               FALLBACK_MAX_CONSECUTIVE)
                self._fallback_warned = True
            return state, None

    def _parse_official_output(self, old_state, solution_water_L=None):
        """从官方 PHREEQC SELECTED_OUTPUT 提取平衡状态并回填 (Q1 核心)

        SELECTED_OUTPUT 列: 0=sim 1=state 2=soln 3=dist_x 4=time 5=step
                            6=pH 7=pe 8=temp(C) 9..18=totals(元素)
                            19..24=molalities(交换物种)
        """
        p = self.official
        nrows = p.GetSelectedOutputRowCount()
        ncols = p.GetSelectedOutputColumnCount()
        if nrows <= 1:
            raise RuntimeError("SELECTED_OUTPUT 无数据行")

        # 列名映射 (第一行为列名)
        headers = [str(p.GetSelectedOutputValue(0, c)) for c in range(ncols)]
        idx = {h: c for c, h in enumerate(headers)}
        last = nrows - 1

        def get(col):
            return float(p.GetSelectedOutputValue(last, idx[col]))

        new_state = SoilState()
        # 排水模型: 降水入渗+平衡后, 多余水分排水, 溶液体积恢复初始值
        # (淋溶损失由浓度稀释体现: 下月用恢复体积×稀释后浓度)
        # v0.6.0 (Q5): 体积-θ 耦合时 volume = 目标溶液体积 (θ×depth×1e5)
        new_state.volume = (solution_water_L if solution_water_L is not None
                            else old_state.volume)
        # v0.5.3 (Q1/Q7): θ 为跨月规范状态, 化学步必须保留 (水文状态连续)
        new_state.theta = old_state.theta
        new_state.ph = get('pH')
        new_state.pe = get('pe')
        new_state.temperature = get('temp(C)')

        # 溶液组成 (mol/kgw ≈ mol/L, 直接保存)
        solution = {'temp': new_state.temperature,
                    'pH': new_state.ph,
                    'pe': new_state.pe,
                    'units': 'mol/L'}
        for el in ['Ca', 'Mg', 'K', 'Na', 'Al', 'P', 'Zn',
                   'Cl', 'C', 'S', 'N', 'Si', 'F']:
            col = f"{el}(mol/kgw)"
            if col in idx:
                solution[el] = get(col)
        # v0.6.0 数值防护 (E2/E3 实测): 离子浓度物理上限检查 —
        # PHREEQC 高离子强度/碱性平衡失败时 SELECTED_OUTPUT 可能输出异常值
        # (实测 Cl=44 mol/L), 若进入状态链会经层间 inflow_ions 级联放大。
        # 判定为数值失败 (抛异常 → 走简化 fallback 保留前一正常状态)。
        for _el, _c in solution.items():
            if _el in ('temp', 'pH', 'pe', 'units'):
                continue
            if abs(float(_c)) > 10.0:
                raise RuntimeError(
                    f"离子浓度异常 ({_el}={_c:.2f} mol/L > 10), 判定数值失败")
        new_state.solution = solution

        # 交换组成: SELECTED_OUTPUT molality (mol/kgw) × 实际水质量(kg)
        # 必须用实际水质量(含降水 mass_H2O)而非初始体积, 否则交换相
        # 会被错误稀释耗尽 (见 Q1_ANALYSIS.md 诊断)
        water_mass = get('mass_H2O') if 'mass_H2O' in idx \
            else new_state.volume
        exchange = {}
        for sp in ['CaX2', 'MgX2', 'KX', 'NaX', 'AlX3', 'HX']:
            col = f"m_{sp}(mol/kgw)"
            if col in idx:
                exchange[sp] = get(col) * water_mass
        new_state.exchange = exchange

        # 矿物相: L2 修复 — 从 SELECTED_OUTPUT 读取矿物摩尔量演化
        # (原 Q1 占位实现冻结为旧值, 导致矿物单向吸收 Al 不回补 → Al 耗尽)
        # -equilibrium_phases 输出两列: <name> (当前摩尔量), d_<name> (变化量)
        # (v0.6.1: KINETICS 双路径已回退, 恢复单路径)
        minerals = {}
        for mname, moles in old_state.minerals.items():
            col = mname
            if col in idx:
                minerals[mname] = max(0.0, get(col))
            else:
                minerals[mname] = moles  # 未输出时保持旧值 (兜底)
        new_state.minerals = minerals
        new_state.gas_phase = old_state.gas_phase
        # WF4: 表面位点摩尔量在月步间保持 (吸附位点不因平衡而消失)
        new_state.surface = old_state.surface

        # L4 (Q4=A): 氮形态库存由 advance_nitrification 推进 (纯模型状态),
        # 不被溶液输出覆盖 — 施肥氮不注入溶液 (N2 平衡), 溶液 N 不代表库存。
        # n_urea/n_nh4 为水解/硝化的驱动库存, n_no3 为累计硝化量 (诊断)。
        # (advance 已在 _run_official_step 中就地推进传入的 state, 此处延续)
        new_state.n_urea = old_state.n_urea
        new_state.n_nh4 = old_state.n_nh4
        new_state.n_no3 = old_state.n_no3
        # v0.7.0 (工单70): 淋失示踪池随状态延续 (advance 已就地推进, 此处复制)
        new_state.n_no3_pool = old_state.n_no3_pool

        diag = DiagnosticOutput(ph=new_state.ph, pe=new_state.pe)
        return new_state, diag

    def _pick_knobs_iterations(self, layer_index=None,
                               n_layers=None) -> int:
        """工单86 (2026-08-31): 分层 KNOBS 迭代选择 (L4 收敛性能优化)

        优先级: SURFACE 强制 1000 (既有行为, test_knobs_surface_iterations_1000)
        > 深层 (L3/L4, KNOBS_ITERATIONS_DEEP) > 浅层/缺省 (500)。

        数据依据 (工单84 探针 B): 难步 82% 集中 L3+L4 (L4 单层 71%), 重试步占
        84% 模拟时间。⚠️ 探针证伪 (probe_86_layer_iters.py, natural 1y):
        深层 500→1000 实测 +56.5% 更慢且重试不减少 — PHREEQC 对首次迭代预算
        非预期敏感 (首次 1000 的 L4 难步仍超限需重试 2000), 故当前
        KNOBS_ITERATIONS_DEEP=500 与工单85 权威基线逐位一致; 分层架构保留,
        D 工单 (铝缓冲标定) 改变 L4 条件数后可再启用。

        layer_index / n_layers 为 None 时 (单层路径/直接调用/测试) 返回默认,
        行为不变。n_layers=1 时即使传 layer_index 也走默认 (单层回归护栏)。
        """
        if self.enable_surface:
            return 1000
        if (layer_index is not None and n_layers is not None
                and n_layers >= 2
                and layer_index + 1 >= KNOBS_DEEP_START_LAYER):
            return KNOBS_ITERATIONS_DEEP
        return KNOBS_ITERATIONS_SHALLOW

    def _build_phreeqc_input(self, state, forcing, action, profile,
                             n_reaction=None, solution_water_L=None,
                             inject_water=True, knobs_tolerance=None,
                             knobs_iterations=None, layer_index=None,
                             n_layers=None) -> str:
        """构建 PHREEQC 输入字符串

        参数:
            n_reaction (L4, v0.3.0): 本月氮反应量 {'NH4+','NO3-','H+'} (mol),
                由 advance_nitrification 计算。None 时内部计算 (直接调用场景,
                如测试), 此时会就地推进 state 的氮库存。
            solution_water_L (v0.6.0): 目标溶液体积 (L), 体积-θ 耦合用;
                None=用 state.volume (月级现状)。
            inject_water (v0.6.0): 是否注入入渗水 H2O (体积耦合时 False,
                水量由 -water 体现; 降水化学/优先流化学仍注入)。
            layer_index / n_layers (工单86, 2026-08-31): 分层 KNOBS 迭代 —
                深层 (L3/L4) 用 KNOBS_ITERATIONS_DEEP (当前=500, 与工单85
                逐位一致; 探针证伪 1000 负收益), 浅层/缺省保持 500。
                None/None (单层或直接调用) 行为不变。
        """
        lines = []

        # v0.7.0 (工单71, spec 69): 自定义保守惰性阴离子物种定义
        # (不碰 phreeqc.dat; 不参与氧化还原; 供伴随淋失 E_loss 等当量注入,
        #  进平衡前 REACTION 注入 → 电荷平衡驱动交换相盐基解吸, Gapon 自洽)
        # 元素名 = companion.inert_anion (PHREEQC 要求单元素名, 默认 An),
        # 物种 = 元素名 + '-'; gfW 取 Cl 原子量 (保守示踪)
        # v0.7.x (工单77): 条件从 companion_enabled 解耦 — charge pairing
        # (电荷平衡修复) 独立启用时同样需要该保守阴离子定义
        if self.anion_defined:
            an_name = self.pair_anion
            an_species = f"{an_name}-"
            lines.append("SOLUTION_MASTER_SPECIES")
            lines.append(
                f"    {an_name}    {an_species}    0.0    {an_name}    35.453")
            lines.append("")
            lines.append("SOLUTION_SPECIES")
            lines.append(f"    {an_species} = {an_species}")
            lines.append("    -log_k    0.0")
            lines.append("")

        # KNOBS: 提高收敛鲁棒性 (物理矿物量较大时数值更难收敛)
        # 迭代数取 100 平衡速度与收敛 (500 会使长模拟显著变慢)
        # WF4/WF5: SURFACE 增加非线性, 需更高迭代数收敛 (1000, 实测验证)
        # v0.7.x (工单78): 迭代/容差参数化 (constants.KNOBS_*)。预平衡 (远平衡
        # 起点) 用 KNOBS_TOLERANCE_PRE (1e-12, 宽松假收敛稳定; 1e-9 第一步迭代
        # 超限返回垃圾解 CaX2=0); 模拟步 (预平衡状态近平衡) 用 KNOBS_TOLERANCE
        # (1e-9, lime 高 pH 真收敛 10.18, 1e-12 静默假收敛 4.89)。见
        # docs/analysis/KNOBS_CONVERGENCE.md。
        # 工单82 (2026-08-25, 数据驱动): 不注入 -step_size — IPhreeqc 3.8.6
        # 对 -step_size 行的存在本身敏感 (实测 0.2~0.001 均使预平衡第一步
        # 远起点大交换相平衡数值发散 Ca=2000/4000 垃圾解, 缺省 OK); 工单78
        # 引入此行是 v0.7.x 预平衡连续失败→永久降级 (spec82 '首月即降级')
        # 的真根因。PHREEQC 默认牛顿步长保持。
        # 工单86 (2026-08-31): 分层 KNOBS 迭代 — 深层 (L3/L4) 用
        # KNOBS_ITERATIONS_DEEP (当前=500, 探针证伪 1000 负收益);
        # 浅层/单层/直接调用保持 KNOBS_ITERATIONS (500) 逐位一致
        iterations = self._pick_knobs_iterations(layer_index, n_layers)
        if knobs_iterations is not None:
            iterations = knobs_iterations
        tolerance = knobs_tolerance
        if tolerance is None:
            tolerance = (KNOBS_TOLERANCE_PRE if self._in_pre_equilibration
                         else KNOBS_TOLERANCE)
        lines.append("KNOBS")
        lines.append(f"  -iterations {iterations}")
        lines.append(f"  -tolerance {tolerance:.1e}")
        lines.append(f"  -convergence_tolerance {KNOBS_CONVERGENCE_TOLERANCE:.1e}")
        lines.append("")

        # v0.5.0 L9: 覆盖 AlX3 交换选择性 log_k (抑制盐基置换交换 Al)
        # 仅在校准值 != 数据库默认值时输出 (默认不改变行为)
        if ALX3_SELECTIVITY_LOGK != ALX3_DEFAULT_LOGK:
            lines.append("EXCHANGE_SPECIES")
            lines.append("Al+3 + 3 X- = AlX3")
            lines.append(f"    -log_k {ALX3_SELECTIVITY_LOGK}")
            lines.append("")

        # v0.6.1 (spec 62 Q7): 注入 HX 交换物种 — phreeqc.dat 的
        # "H+ + X- = HX" 被注释禁用 (第 1362 行), 必须自定义注入使模型可识别
        # 交换性 H 酸库 (exch_h→HX, initial_condition.build_exchange)。
        # log_k=HX_LOGK (v0.6.1 扫描标定 3.0 → v0.7.0 工单76 调优 B 改 2.8, 可标定)
        lines.append("EXCHANGE_SPECIES")
        lines.append("H+ + X- = HX")
        lines.append(f"    -log_k {HX_LOGK}")
        lines.append("")

        # SOLUTION 块
        # -water 指定土柱溶液体积 (L), 使溶液与交换/矿物摩尔量量级匹配
        # v0.6.0 (Q5): 体积-θ 耦合时用目标溶液体积 (θ×depth×1e5)
        lines.append("SOLUTION 1")
        water_volume = solution_water_L if solution_water_L is not None \
            else state.volume
        lines.append(f"  -water      {water_volume:.6e}")
        lines.append(f"  temp      {forcing['temp']}")
        lines.append(f"  pH        {state.ph}")
        lines.append(f"  pe        4.0")
        lines.append(f"  units     mol/L")
        for ion, conc in state.solution.items():
            if ion not in ['temp', 'pH', 'pe', 'units']:
                # v0.6.0: 离子浓度下限 1e-10 mol/L (事件级小水量数值稳定性,
                # 防止浓度趋零触发 PHREEQC negative activity)
                lines.append(f"  {ion:<8} {max(float(conc), 1e-10):.6e}")
        lines.append("")

        # EXCHANGE 块
        lines.append("EXCHANGE 1")
        for species, amount in state.exchange.items():
            lines.append(f"  {species:<8} {amount:.6e}")
        lines.append("")

        # EQUILIBRIUM_PHASES 块 (v0.6.1: 恢复全矿物平衡相, KINETICS 已回退)
        # 矿物量 = 物理摩尔量 × 缩放系数 (折中方案, 见 docs/analysis/Q1_plus_ANALYSIS.md):
        # 物理值会导致碱性突变(pH~9.9), 10% 提供真实缓冲且 pH 合理(4.4-4.5)
        # v0.7.0 (工单73): weathering.degrade_minerals 指定的矿物从平衡相降级
        # (不写入本块 → 消除"矿物闪蒸"无限供碱, 疑点1 机制A); 状态仍保留
        # (SELECTED_OUTPUT 矿物演化回填不破坏 — v0.3.0 证伪教训: 不切断回补)
        lines.append("EQUILIBRIUM_PHASES 1")
        degrade_set = set(self.weathering_cfg.degrade_minerals
                          if self.weathering_enabled else [])
        for mineral, moles in state.minerals.items():
            if mineral in degrade_set:
                continue
            if moles > 0:
                scaled = moles * self.mineral_scale
                lines.append(f"  {mineral:<15} 0.0  {scaled:.6e}")
        lines.append("")

        # GAS_PHASE 块 (CO2 分压来自气候强迫, F1 修复: 不再硬编码 0.015)
        # 写法: 总压=CO2分压 + 纯CO2 (验证有效)
        pco2 = forcing.get('pCO2', 0.015)
        lines.append("GAS_PHASE 1")
        lines.append("  -fixed_pressure")
        lines.append(f"  -pressure     {pco2:.6f}")
        lines.append("  CO2(g)        1.0")
        lines.append("")

        # SURFACE 块 (WF4: Hfo_s/Hfo_w 铁氧化物表面络合, 默认关闭)
        # PHREEQC 语法: {name} {表面积m2} {比表面m2/g} {位点密度mol/m2}
        #   -equilibrate with solution 1 (与溶液平衡)
        # 位点量 = 面积 × 位点密度; 面积由 build_surface 按 HFO_TARGET_SITES 反算
        if self.enable_surface and state.surface:
            surface_area = state.surface.get('area_m2', 0.0)
            if surface_area > 0:
                lines.append("SURFACE 1")
                lines.append(f"  Hfo_s  {surface_area:.6e}  "
                             f"{HFO_SPECIFIC_AREA:.1f}  "
                             f"{HFO_STRONG_SITE_DENSITY:.6e}")
                lines.append("  -equilibrate with solution 1")
                lines.append(f"  Hfo_w  {surface_area:.6e}  "
                             f"{HFO_SPECIFIC_AREA:.1f}  "
                             f"{HFO_WEAK_SITE_DENSITY:.6e}")
                lines.append("  -equilibrate with solution 1")
                lines.append("")

        # 单一 REACTION 块: 降水入渗 + 施肥(尿素硝化) + 石灰(CaO水化)
        # 注意:
        #   1) PHREEQC 多 REACTION 块共存时仅第一个生效 (phreeqc 包行为),
        #      故所有干预合并到同一 REACTION 块;
        #   2) REACTION 物质名不支持括号价态写法(N(5)/H(1) 会 Parsing error),
        #      必须用元素名或具体物种名 (见 docs/analysis/Q1_ANALYSIS.md);
        #   3) 降水: mm → L → mol (1 L H2O ≈ 55.5 mol), 乘以入渗系数
        precip_mm = forcing['precip']
        reaction_lines = []

        if precip_mm > 0 or forcing.get('inflow_water_L'):
            # v0.5.0: 水文模式用该层注入水量 (inflow_water_L, L/ha), 否则用
            # 降水×入渗系数; 水量为 0 时不注入
            inflow_water_L = forcing.get('inflow_water_L')
            if inflow_water_L is not None:
                water_L = inflow_water_L
            else:
                water_L = precip_mm * 10000.0 * self.precip_infiltration
            water_mol = water_L * 55.5  # 1 L H2O ≈ 55.5 mol
            # v0.6.0 (Q5): 体积-θ 耦合 (inject_water=False) 时不注入 H2O,
            # 水量由 SOLUTION -water 体现
            if inject_water and water_mol > 0:
                reaction_lines.append(f"  H2O    {water_mol:.6e}  # 降水入渗")
            # Q7: 降水化学离子 (酸雨组分) 随入渗水进入溶液
            if self.precip_chem is not None and water_L > 0:
                amounts = self.precip_chem.reaction_amounts(water_L)
                for sp, mol in amounts.items():
                    if mol > 0:
                        reaction_lines.append(
                            f"  {sp:<8} {mol:.6e}  # 降水{sp}")

            # v0.5.2: 大孔隙优先流 — 绕过表层积水 (未与表层平衡) 携带原始
            # 降水化学注入深层; H2O 独立追加, 降水化学按 precip_chem 有无
            bypass_water_L = forcing.get('bypass_water_L', 0.0)
            if bypass_water_L > 0:
                if inject_water:
                    bypass_mol = bypass_water_L * 55.5
                    reaction_lines.append(
                        f"  H2O    {bypass_mol:.6e}  # 优先流")
                if self.precip_chem is not None:
                    b_amounts = self.precip_chem.reaction_amounts(bypass_water_L)
                    for sp, mol in b_amounts.items():
                        if mol > 0:
                            reaction_lines.append(
                                f"  {sp:<8} {mol:.6e}  # 优先流{sp}")

        # WF2/Q2+Q7: 层间平流输入 — 上层排水溶质 (mol) 注入本层
        # 由 run_monthly_multi_layer 计算上层 SELECTED_OUTPUT totals × 排水量
        inflow_ions = forcing.get('inflow_ions')
        if inflow_ions:
            for ion, mol in inflow_ions.items():
                if mol > 0:
                    reaction_lines.append(
                        f"  {ion:<8} {mol:.6e}  # 上层排水")

        # L4 (v0.3.0): 氮形态两步 — 尿素水解 → NH4+ → NO3- (库存层, Q1=A)
        # NH4+/NO3- 不注入 PHREEQC 溶液: phreeqc.dat 的 N 氧化还原平衡会将其
        # 全部转为 N2(g) (实测 pe=0~12 下 N(-3)/N(5)≈0)。只注入硝化产酸
        # H+ = 2×硝化量 (Q3=A: 酸化效应真实进入溶液, 与旧"一步产酸"守恒)
        if n_reaction is None:
            # v0.4.0: 兜底路径也使用引擎配置的硝化速率
            n_reaction = advance_nitrification(
                state, action,
                k1=self.nitrification_k1, k2=self.nitrification_k2)
        h_mol = n_reaction.get('H+', 0.0)
        if h_mol > 0:
            reaction_lines.append(f"  H+     {h_mol:.6e}  # 硝化产酸")
            # v0.7.x (工单77): 电荷配对 — 裸 H+ 注入在 PHREEQC 中因电荷
            # 平衡不酸化 (2026-08-21 实测); 伴随等当量保守惰性阴离子后
            # 真实酸化 (模拟 HNO3 的伴随阴离子, N 不进溶液故用 An- 替代)
            if self.charge_pairing_enabled:
                reaction_lines.append(
                    f"  {self.pair_anion}- {h_mol:.6e}  # 电荷配对")

        # v0.7.0 (工单72, spec 69): NH4+ 等效置换 — 施肥月尿素水解后, NH4+
        # 假想占据交换位点并置换等当量盐基到溶液 (按交换相电荷占比注入),
        # 模拟农业"NH4+ 置换盐基→盐基淋失"酸化通道 (不触碰 L4 Q3=A:
        # NH4+/NO3- 不进溶液; 与硝化 H+ 同场平衡, 净效应 H+ 主导酸化)。
        # 再吸附由平衡自然回吸 (Q20 决策), NH4X_virtual 记账列观测净效率。
        # 工单76 调优 A (2026-08-21): 置换当量从水解量 (857 eq/次) 改为
        # 硝化量 (343 eq/次) — 实测 857 使肥料盐基流净 +180 eq/次 (置换注入
        # 的盐基被 Gapon 回吞 > 产酸), 施肥仍碱化; 仅对实际参与硝化的 N
        # 置换, 物理更准且抑制盐基过量注入。
        if (self.companion_enabled and self.companion_cfg.nh4_exchange
                and not forcing.get('skip_nitrification')
                and n_reaction and n_reaction.get('nitrified', 0.0) > 0):
            nh4_eq = n_reaction['nitrified']
            ratios = exchange_base_ratios(state.exchange)
            if ratios:
                for ion, frac in ratios.items():
                    eq = nh4_eq * frac
                    reaction_lines.append(
                        f"  {ion} {eq:.6e}  # NH4+ 置换")
                    # v0.7.x (工单77): 电荷配对 — 裸阳离子注入在 PHREEQC 中
                    # 因电荷平衡产生 OH- 伪碱化 (Ca+2 343 → pH 9.28, 复现
                    # v0.7.0 fertilizer 碱化); 伴随等当量 An- 使置换盐基以
                    # 电中性盐形式进入 (盐基效应由化学平衡/淋失决定)
                    if self.charge_pairing_enabled:
                        charge = 2 if ion in ('Ca+2', 'Mg+2') else 1
                        reaction_lines.append(
                            f"  {self.pair_anion}- {charge * eq:.6e}  # 电荷配对")

        # v0.7.0 (工单71, spec 69): 伴随淋失注入 — 随 NO3- 移出的盐基当量
        # E_loss (工单70 事件循环计算, 经 forcing 传入; 进平衡前注)
        #   - companion_anion_eq>0: 注入惰性阴离子 CompAn- (电荷平衡驱动交换相解吸)
        #   - companion_acid_eq>0: 酸化注入 H+ (BS<low 盐基枯竭模式)
        companion_anion_eq = forcing.get('companion_anion_eq', 0.0)
        companion_acid_eq = forcing.get('companion_acid_eq', 0.0)
        if companion_anion_eq > 0 and self.companion_enabled:
            an_species = f"{self.companion_cfg.inert_anion}-"
            reaction_lines.append(
                f"  {an_species} {companion_anion_eq:.6e}  # 伴随淋失")
        if companion_acid_eq > 0:
            reaction_lines.append(
                f"  H+     {companion_acid_eq:.6e}  # 伴随淋失酸化")
            # v0.7.x (工单77): 电荷配对 (同硝化产酸)
            if self.charge_pairing_enabled:
                reaction_lines.append(
                    f"  {self.pair_anion}- {companion_acid_eq:.6e}  # 电荷配对")

        # v0.7.x (工单80): 盐基淋失伴随注入 — 上一场 E_base (离开本层全部水的
        # 溶液盐基当量, Q4=A) 分级后 (Q5=A) 注入等当量 An- → 平衡自洽拽出交换
        # 相盐基 (Gapon); 独立于 charge_pairing (保守阴离子伴随, 不依赖配对开关)
        base_anion_eq = forcing.get('base_anion_eq', 0.0)
        if base_anion_eq > 0 and self.base_leaching_enabled:
            reaction_lines.append(
                f"  {self.pair_anion}- {base_anion_eq:.6e}  # 盐基淋失伴随")

        # v0.7.0 (工单73, spec 69): 矿物风化集总碱度注入 (D2, 不用 KINETICS)
        # 逐月注入风化碱度: Ca:Mg:K 按电荷占比 (默认 5:3:2) + HCO3- 等当量;
        # Arrhenius 温度依赖 (rate(T) = rate_ref×exp(−Ea/R×(1/T−1/T_ref)))
        # 替代瞬时平衡相的"无限供碱" (矿物闪蒸, 疑点1 机制A); 增温情景
        # 风化↑ → 气候敏感性传导恢复 (疑点2)
        if self.weathering_enabled:
            wth = self.weathering_cfg
            temp_c = forcing.get('temp', 25.0)
            arrhenius = weathering_arrhenius_factor(
                temp_c, wth.activation_energy_kJ)
            monthly_molc = wth.rate_molc_ha_yr / 12.0 * arrhenius
            # 各盐基注入摩尔量 (电荷占比 → mol, 二价 ×2)
            ca_mol = monthly_molc * wth.ca_frac / 2.0
            mg_mol = monthly_molc * wth.mg_frac / 2.0
            k_mol = monthly_molc * wth.k_frac
            if ca_mol > 0:
                reaction_lines.append(f"  Ca+2   {ca_mol:.6e}  # 矿物风化")
            if mg_mol > 0:
                reaction_lines.append(f"  Mg+2   {mg_mol:.6e}  # 矿物风化")
            if k_mol > 0:
                reaction_lines.append(f"  K+     {k_mol:.6e}  # 矿物风化")
            if monthly_molc > 0:
                reaction_lines.append(
                    f"  HCO3-  {monthly_molc:.6e}  # 矿物风化")

        # v0.5.0: 预平衡观测锚定注入 (pH/交换离子修正, 见 pre_equilibrate)
        injection = forcing.get('injection')
        if injection:
            for sp, mol in injection.items():
                if abs(mol) > 1e-12:
                    reaction_lines.append(
                        f"  {sp:<8} {mol:.6e}  # 预平衡锚定")
                    # v0.7.x (工单77): 电荷配对 — 锚定注入为阳离子 (Ca/Mg/K/
                    # Na/Al), 裸注入会使预平衡 pH 伪碱化; 正注入伴随等当量 An-
                    if (self.charge_pairing_enabled and mol > 0.0):
                        charge = 3 if sp == 'Al+3' else (
                            2 if sp in ('Ca+2', 'Mg+2') else 1)
                        reaction_lines.append(
                            f"  {self.pair_anion}- {charge * mol:.6e}  # 电荷配对")

        if action.apply_fertilizer:
            # 磷肥 (P2O5 → 2 H2PO4-)
            p_mol = action.p2o5_amount * 1000.0 / 141.94 * 2.0
            if p_mol > 0:
                reaction_lines.append(f"  H2PO4- {p_mol:.6e}  # 磷肥")
            # 钾肥 (K2O → 2 K+)
            k_mol = action.k2o_amount * 1000.0 / 94.20 * 2.0
            if k_mol > 0:
                reaction_lines.append(f"  K+     {k_mol:.6e}  # 钾肥")
                # v0.7.x (工单77): 电荷配对 (裸 K+ 轻度碱化, K+191 → pH 6.03)
                if self.charge_pairing_enabled:
                    reaction_lines.append(
                        f"  {self.pair_anion}- {k_mol:.6e}  # 电荷配对")
            # 镁肥 (MgO → Mg+2)
            mg_mol = action.mgo_amount * 1000.0 / 40.30
            if mg_mol > 0:
                reaction_lines.append(f"  Mg+2   {mg_mol:.6e}  # 镁肥")
                # v0.7.x (工单77): 电荷配对 (裸 Mg+2 轻度碱化)
                if self.charge_pairing_enabled:
                    reaction_lines.append(
                        f"  {self.pair_anion}- {2.0 * mg_mol:.6e}  # 电荷配对")
            # 硫酸锌 (ZnSO4 → Zn+2 + SO4-2)
            zn_mol = action.znso4_amount * 1000.0 / 161.47
            if zn_mol > 0:
                reaction_lines.append(f"  Zn+2   {zn_mol:.6e}  # 硫酸锌")
                reaction_lines.append(f"  SO4-2  {zn_mol:.6e}  # 硫酸锌")

        if action.apply_lime:
            # 生石灰 CaO: 水化产 Ca2+ + 2OH- (移除 2H)
            lime_mol = action.lime_amount * 1000.0 / 56.08
            if lime_mol > 0:
                reaction_lines.append(f"  Ca     {lime_mol:.6e}  # 生石灰Ca2+")
                reaction_lines.append(f"  H      {-2*lime_mol:.6e}  # 水化OH-")

        if reaction_lines:
            lines.append("REACTION 1")
            lines.extend(reaction_lines)
            lines.append("  1.0")
            lines.append("")

        # SELECTED_OUTPUT 块: 输出平衡后状态供解析回填
        lines.append("SELECTED_OUTPUT 1")
        lines.append("  -ph true")
        lines.append("  -pe true")
        lines.append("  -temp true")
        lines.append("  -water true")
        # L4 (Q1=A): 氮库存为模型状态 (不注入溶液), 无需 N(-3)/N(5) 回填;
        # 总 N 保留供层间平流 (inflow_ions)
        # v0.7.0 (工单71): companion 启用时 totals 追加惰性阴离子元素 (审计)
        # v0.7.x (工单77): 条件扩展 — charge pairing 启用时同样需要 (配对
        # 注入的 An- 进入溶液成分/淋失循环, 需在 totals 输出供回填审计)
        totals_line = "  -totals Ca Mg K Na Al P Zn Cl C S N Si F"
        if self.anion_defined:
            totals_line += f" {self.pair_anion}"
        lines.append(totals_line)
        lines.append("  -molalities CaX2 MgX2 KX NaX AlX3 HX X-")
        # L2: 输出矿物相摩尔量 (供矿物演化回填, 修复 Al 耗尽根因)
        # 只列出非零矿物; 矿物名须与 phreeqc.dat PHASES 段一致
        # L2: 输出矿物相摩尔量 (供矿物演化回填, 修复 Al 耗尽根因)
        # 只列出非零矿物; 矿物名须与 phreeqc.dat PHASES 段一致
        mineral_names = [m for m, v in state.minerals.items() if v > 0]
        if mineral_names:
            lines.append("  -equilibrium_phases " + " ".join(mineral_names))
        lines.append("END")

        return "\n".join(lines)

    def _run_simplified_step(self, state, forcing, action, profile):
        """简化模式 (无 PHREEQC 时的 fallback)

        仅更新 pH, 保留溶液/交换/矿物等化学状态 (Q6 缓解):
        简化模式不应清空化学组成, 保证状态链连续。
        """
        new_state = SoilState()
        # 保留化学状态
        new_state.solution = state.solution
        new_state.exchange = state.exchange
        new_state.minerals = state.minerals
        new_state.gas_phase = state.gas_phase
        new_state.surface = state.surface   # WF4: 保留表面位点
        new_state.volume = state.volume
        # v0.5.3 (Q1/Q7): θ 为跨月规范状态, 简化模式同样保留 (状态连续)
        new_state.theta = state.theta
        new_state.temperature = state.temperature
        new_state.pe = state.pe
        new_state.ph = state.ph
        # L4 (Q9=A): simplified 引擎不参与硝化逻辑, 氮库存占位保留
        # (降级边界: 简化模式退化为经验产酸, 氮形态不演化, 见 V0_3_0_REPORT)
        new_state.n_urea = state.n_urea
        new_state.n_nh4 = state.n_nh4
        new_state.n_no3 = state.n_no3

        # 简化: 降水淋溶 → pH 缓降 (S4 物理量级校准 v0.2.1)
        #   k_precip=1.5e-5 → 年降 ~0.03 (30 年 ~0.9, 保持淋溶酸化物理方向;
        #   官方引擎 natural 前 7 年升碱是单层 Al 淋洗局限, 不作为匹配目标)
        precip_effect = forcing['precip'] * SIMPLIFIED_K_PRECIP
        new_state.ph = state.ph - precip_effect

        # 简化: 施肥产酸 (P4 修复: fertilizer_amount 字段不存在, 改用各肥料量之和)
        if action.apply_fertilizer:
            fert_total = (action.n_amount + action.p2o5_amount +
                          action.k2o_amount + action.mgo_amount +
                          action.znso4_amount)
            fert_acid = fert_total * SIMPLIFIED_K_FERT    # ~0.02 pH/次施肥
            new_state.ph = new_state.ph - fert_acid

        # 简化: 石灰提碱
        if action.apply_lime:
            lime_alk = action.lime_amount * SIMPLIFIED_K_LIME   # ~0.09 pH/次石灰
            new_state.ph = new_state.ph + lime_alk

        # Q5 修复 (v0.2.1): 移除硬编码 3.5/9.0 界限, 放宽至物理合理范围
        new_state.ph = min(PH_UPPER, max(PH_LOWER, new_state.ph))

        diag = DiagnosticOutput(ph=new_state.ph)
        return new_state, diag



