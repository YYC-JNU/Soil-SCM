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
                           INITIAL_PSI_CM)
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

    return {'H+': 2.0 * nitrified}


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
                 initial_psi_cm: float = INITIAL_PSI_CM):
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
                         soil_profile) -> Tuple[SoilState, DiagnosticOutput]:
        """执行单月计算步

        参数:
            state: 当前土壤状态
            monthly_forcing: 当月气候强迫
            action: 当月操作指令
            soil_profile: 土壤剖面数据

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
            return self._run_official_step(state, monthly_forcing,
                                           action, soil_profile)
        else:
            return self._run_simplified_step(state, monthly_forcing,
                                             action, soil_profile)

    def run_event_step(self, state: SoilState, event, action,
                       soil_profile, forcing: dict = None
                       ) -> Tuple[SoilState, DiagnosticOutput]:
        """执行单场降雨事件的化学步 (v0.6.0, Q1/Q3/Q5/Q6)

        事件驱动化学核心: 每场事件一次全量 PHREEQC 平衡。

        - 事件级 forcing: precip = event.precip_mm; inflow_water_L /
          bypass_water_L / inflow_ions 由事件级水文编排注入
          (层间溶质逐场传递, Q4)
        - 体积-θ 耦合 (Q5): SOLUTION -water = θ_事件后×depth×1e5
          (theta_to_water_L), 替换恒定 state.volume; 浓度按质量守恒换算
          (C_new = C_old×V_old/V_new), 干燥→体积小→浓缩酸化自然产生
        - 交换相/矿物相绝对摩尔量不变 (Q6): EXCHANGE/EQUILIBRIUM_PHASES mol
          为绝对量, 仅溶液体积随 θ 重建, PHREEQC 自动重平衡浓度
        - 水量效应全部由 -water 体现, REACTION 只注入化学物质
          (inject_water=False)

        参数:
            state: 当前土壤状态 (事件级水文步已就地更新 state.theta)
            event: RainEvent (precip_mm/duration_h/precip_chem)
            action: 当月操作指令 (施肥/石灰)
            soil_profile: 土壤剖面数据
            forcing: 事件级补充 forcing dict (可选, 覆盖事件默认)

        返回:
            (新状态, 诊断输出)
        """
        eff = dict(forcing or {})
        eff.setdefault('precip', event.precip_mm)
        eff.setdefault('temp', 25.0)
        eff.setdefault('pCO2', 0.015)

        # 体积-θ 耦合 (Q5): 事件后溶液体积由 θ 决定, 浓度按绝对量守恒换算
        water_target_L = theta_to_water_L(state.theta,
                                          soil_profile.effective_depth)
        self._rescale_solution_for_volume(state, water_target_L)

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
                                           solution_water_L=water_target_L,
                                           inject_water=False)
        return self._run_simplified_step(state, eff, action, soil_profile)

    def apply_concentration_equilibrium(self, state: SoilState, theta: float,
                                        soil_profile, forcing: dict,
                                        action=None):
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
        self._rescale_solution_for_volume(state, water_target_L)
        eff = dict(forcing)
        eff['precip'] = 0.0
        eff['inflow_water_L'] = None
        eff['bypass_water_L'] = 0.0
        eff['inflow_ions'] = None
        eff['skip_nitrification'] = True
        return self._run_official_step(state, eff, action or MonthlyAction(),
                                       soil_profile,
                                       solution_water_L=water_target_L,
                                       inject_water=False)

    def _rescale_solution_for_volume(self, state: SoilState,
                                     new_water_L: float):
        """体积-θ 耦合的浓度换算 (Q5/Q7 内部): 保持溶质绝对量守恒

        溶液浓度 C (mol/L) × 体积 V (L) = 溶质绝对量 (mol)。-water 从 V_old
        变到 V_new 时, 浓度调整为 C_new = C_old × V_old/V_new, 使总溶质不变
        (干燥浓缩 / 湿润稀释的数学表达)。就地更新 state.solution/volume。
        """
        old_water_L = state.volume
        if old_water_L <= 0 or new_water_L <= 0:
            return
        ratio = old_water_L / new_water_L
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
        for ion in ('CaX2', 'MgX2', 'KX', 'NaX', 'AlX3'):
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
        for ion in ('CaX2', 'MgX2', 'KX', 'NaX', 'AlX3'):
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
        sp_map = {'CaX2': 'Ca+2', 'MgX2': 'Mg+2', 'KX': 'K+',
                  'NaX': 'Na+', 'AlX3': 'Al+3'}
        for ion, target in targets.items():
            if target <= 0 or ion not in sp_map:
                continue
            cur = state.exchange.get(ion, 0.0)
            dev = (cur - target) / target
            if abs(dev) > PRE_EQUIL_ION_TOL:
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
        for ion in ('CaX2', 'MgX2', 'KX', 'NaX', 'AlX3'):
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
            new_state, diag = self.run_monthly_step(
                states[i], layer_forcing, action, soil_profile)
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

    def _run_official_step(self, state, forcing, action, profile,
                           solution_water_L=None, inject_water=True):
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
            solution_water_L=solution_water_L, inject_water=inject_water)

        try:
            self.official.RunString(input_string)
            new_state, diag = self._parse_official_output(
                state, solution_water_L=solution_water_L)
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
            if not getattr(self, '_fallback_warned', False):
                logger.error("PHREEQC 计算失败: %s", e, exc_info=True)
                logger.debug("失败输入:\n%s", input_string)
                logger.warning("已永久降级到简化模式继续模拟")
                self._fallback_warned = True
            self._permanent_fallback = True
            return self._run_simplified_step(state, forcing, action, profile)

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
        new_state.solution = solution

        # 交换组成: SELECTED_OUTPUT molality (mol/kgw) × 实际水质量(kg)
        # 必须用实际水质量(含降水 mass_H2O)而非初始体积, 否则交换相
        # 会被错误稀释耗尽 (见 Q1_ANALYSIS.md 诊断)
        water_mass = get('mass_H2O') if 'mass_H2O' in idx \
            else new_state.volume
        exchange = {}
        for sp in ['CaX2', 'MgX2', 'KX', 'NaX', 'AlX3']:
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

        diag = DiagnosticOutput(ph=new_state.ph, pe=new_state.pe)
        return new_state, diag

    def _build_phreeqc_input(self, state, forcing, action, profile,
                             n_reaction=None, solution_water_L=None,
                             inject_water=True) -> str:
        """构建 PHREEQC 输入字符串

        参数:
            n_reaction (L4, v0.3.0): 本月氮反应量 {'NH4+','NO3-','H+'} (mol),
                由 advance_nitrification 计算。None 时内部计算 (直接调用场景,
                如测试), 此时会就地推进 state 的氮库存。
            solution_water_L (v0.6.0): 目标溶液体积 (L), 体积-θ 耦合用;
                None=用 state.volume (月级现状)。
            inject_water (v0.6.0): 是否注入入渗水 H2O (体积耦合时 False,
                水量由 -water 体现; 降水化学/优先流化学仍注入)。
        """
        lines = []

        # KNOBS: 提高收敛鲁棒性 (物理矿物量较大时数值更难收敛)
        # 迭代数取 100 平衡速度与收敛 (500 会使长模拟显著变慢)
        # WF4/WF5: SURFACE 增加非线性, 需更高迭代数收敛 (1000, 实测验证)
        # v0.6.0: KINETICS 动力学积分增加数值难度, 同样提至 1000
        # KNOBS: 提高收敛鲁棒性 (物理矿物量较大时数值更难收敛)
        # 迭代数取 100 平衡速度与收敛 (500 会使长模拟显著变慢)
        # WF4/WF5: SURFACE 增加非线性, 需更高迭代数收敛 (1000, 实测验证)
        iterations = 1000 if self.enable_surface else 100
        lines.append("KNOBS")
        lines.append(f"  -iterations {iterations}")
        lines.append("  -tolerance 1e-12")
        lines.append("")

        # v0.5.0 L9: 覆盖 AlX3 交换选择性 log_k (抑制盐基置换交换 Al)
        # 仅在校准值 != 数据库默认值时输出 (默认不改变行为)
        if ALX3_SELECTIVITY_LOGK != ALX3_DEFAULT_LOGK:
            lines.append("EXCHANGE_SPECIES")
            lines.append("Al+3 + 3 X- = AlX3")
            lines.append(f"    -log_k {ALX3_SELECTIVITY_LOGK}")
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
        lines.append("EQUILIBRIUM_PHASES 1")
        for mineral, moles in state.minerals.items():
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

        # v0.5.0: 预平衡观测锚定注入 (pH/交换离子修正, 见 pre_equilibrate)
        injection = forcing.get('injection')
        if injection:
            for sp, mol in injection.items():
                if abs(mol) > 1e-12:
                    reaction_lines.append(
                        f"  {sp:<8} {mol:.6e}  # 预平衡锚定")

        if action.apply_fertilizer:
            # 磷肥 (P2O5 → 2 H2PO4-)
            p_mol = action.p2o5_amount * 1000.0 / 141.94 * 2.0
            if p_mol > 0:
                reaction_lines.append(f"  H2PO4- {p_mol:.6e}  # 磷肥")
            # 钾肥 (K2O → 2 K+)
            k_mol = action.k2o_amount * 1000.0 / 94.20 * 2.0
            if k_mol > 0:
                reaction_lines.append(f"  K+     {k_mol:.6e}  # 钾肥")
            # 镁肥 (MgO → Mg+2)
            mg_mol = action.mgo_amount * 1000.0 / 40.30
            if mg_mol > 0:
                reaction_lines.append(f"  Mg+2   {mg_mol:.6e}  # 镁肥")
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
        lines.append("  -totals Ca Mg K Na Al P Zn Cl C S N Si F")
        lines.append("  -molalities CaX2 MgX2 KX NaX AlX3 X-")
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



