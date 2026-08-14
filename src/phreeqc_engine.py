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
                           N_MOL_PER_KG_N)
from src.logging_config import get_logger

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


class PhreeqcEngine:
    """PHREEQC 引擎封装类"""

    def __init__(self, database: str = 'phreeqc.dat',
                 mode: str = 'auto', backend: str = 'official',
                 precip_chem=None,
                 precip_infiltration: float = PRECIP_INFILTRATION_DEFAULT,
                 enable_surface: bool = False):
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
        self._fallback_warned = False
        self._permanent_fallback = False
        self.last_error_message = None    # Q18: 最近一次引擎失败信息
        self.last_error_input = None     # Q18: 最近一次失败输入字符串
        # 降水入渗系数 (0~1): 实际进入土壤溶液的比例, 其余径流/排水 (T3 参数化)
        self.precip_infiltration = precip_infiltration
        # 矿物量缩放系数: EQUILIBRIUM_PHASES 矿物量 = 物理摩尔量 × 此系数
        # (折中方案, 见 docs/Q1_plus_ANALYSIS.md):
        # 物理值(1e6-1e7 mol)会导致碱性突变(pH~9.9), 需取较小值保留区分度
        # F2 修复: 与 initial_condition.MINERAL_SCALE 统一 (双路径一致)
        self.mineral_scale = MINERAL_SCALE

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

        builder = InitialConditionBuilder(soil_profile, mineral_db_info, pCO2)

        state = SoilState()
        state.temperature = 25.0
        state.ph = soil_profile.ph

        # 溶液、交换位点、矿物相、气相全部由 InitialConditionBuilder 生成
        state.solution = builder.build_solution()
        state.exchange = builder.build_exchange()
        state.minerals = builder.build_minerals()
        state.gas_phase = builder.build_gas_phase()
        state.volume = builder.solution_volume_L
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

    def run_monthly_multi_layer(self, states: list,
                                monthly_forcing: dict,
                                action,
                                soil_profile) -> Tuple[list, list]:
        """执行多分层月度计算步 (WF2, 基于 WF1 架构决策)

        架构 (WF1 Q1-Q4, Q7):
          - Q1: List[SoilState] — 每层独立完整状态
          - Q3: 级联下渗 — 最上层接受 precip×infiltration, 每层平衡后
               超出持水水量(含溶质)逐层下渗, 最底层流失
          - Q2/Q7: 一维平流 — 上层排水量 × 平衡后溶液浓度(SELECTED_OUTPUT
               totals) = 移出摩尔量, 作为下层 REACTION 输入 (守恒)
          - Q4: run_monthly_step 单层接口不变 (深模块), 此处是高层编排层

        参数:
            states: List[SoilState] — 各层当前状态 (长度 = n_layers)
            monthly_forcing: 当月气候强迫
            action: 当月操作指令
            soil_profile: 土壤剖面数据 (各层默认参数相同, ROADMAP 约束)

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
            if inflow_ions:
                # 下层: 接收上层排水溶质 (Q2/Q7 平流守恒)
                layer_forcing['inflow_ions'] = inflow_ions
            new_state, diag = self.run_monthly_step(
                states[i], layer_forcing, action, soil_profile)
            new_states.append(new_state)
            diags.append(diag)

            # 计算本层排水携带的溶质 → 作为下一层输入 (Q7 守恒核算)
            if i < n - 1:
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

    def _run_official_step(self, state, forcing, action, profile):
        """使用官方 phreeqc (IPhreeqc 3.8.6) 引擎执行单月计算"""
        # L4: 推进氮形态库存 (尿素→NH4+→NO3-, 简化两步), 返回本月氮反应量
        # 独立函数 + 返回契约 → 将来可替换为 KINETICS 实现 (升级空间)
        n_reaction = advance_nitrification(state, action)
        # 构建 PHREEQC 输入字符串 (含 SELECTED_OUTPUT 查询块)
        input_string = self._build_phreeqc_input(
            state, forcing, action, profile, n_reaction=n_reaction)

        try:
            self.official.RunString(input_string)
            new_state, diag = self._parse_official_output(state)
            return new_state, diag
        except Exception as e:
            # Q18 修复: 记录完整诊断 (错误详情 + 输入字符串落盘可复现)
            self.last_error_message = str(e)
            self.last_error_input = input_string
            # T01 修复: 失败输入写入磁盘复现文件 (README 承诺的 error.inp)
            # 写入失败不影响主流程 (降级继续), 仅记录日志
            try:
                Path(ERROR_INP_PATH).write_text(input_string, encoding='utf-8')
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

    def _parse_official_output(self, old_state):
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
        new_state.volume = old_state.volume
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
                             n_reaction=None) -> str:
        """构建 PHREEQC 输入字符串

        参数:
            n_reaction (L4, v0.3.0): 本月氮反应量 {'NH4+','NO3-','H+'} (mol),
                由 advance_nitrification 计算。None 时内部计算 (直接调用场景,
                如测试), 此时会就地推进 state 的氮库存。
        """
        lines = []

        # KNOBS: 提高收敛鲁棒性 (物理矿物量较大时数值更难收敛)
        # 迭代数取 100 平衡速度与收敛 (500 会使长模拟显著变慢)
        # WF4/WF5: SURFACE 增加非线性, 需更高迭代数收敛 (1000, 实测验证)
        iterations = 1000 if self.enable_surface else 100
        lines.append("KNOBS")
        lines.append(f"  -iterations {iterations}")
        lines.append("  -tolerance 1e-12")
        lines.append("")

        # SOLUTION 块
        # -water 指定土柱溶液体积 (L), 使溶液与交换/矿物摩尔量量级匹配
        lines.append("SOLUTION 1")
        lines.append(f"  -water      {state.volume:.6e}")
        lines.append(f"  temp      {forcing['temp']}")
        lines.append(f"  pH        {state.ph}")
        lines.append(f"  pe        4.0")
        lines.append(f"  units     mol/L")
        for ion, conc in state.solution.items():
            if ion not in ['temp', 'pH', 'pe', 'units']:
                lines.append(f"  {ion:<8} {conc:.6e}")
        lines.append("")

        # EXCHANGE 块
        lines.append("EXCHANGE 1")
        for species, amount in state.exchange.items():
            lines.append(f"  {species:<8} {amount:.6e}")
        lines.append("")

        # EQUILIBRIUM_PHASES 块
        # 矿物量 = 物理摩尔量 × 缩放系数 (折中方案, 见 docs/Q1_plus_ANALYSIS.md):
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
        #      必须用元素名或具体物种名 (见 docs/Q1_ANALYSIS.md);
        #   3) 降水: mm → L → mol (1 L H2O ≈ 55.5 mol), 乘以入渗系数
        precip_mm = forcing['precip']
        reaction_lines = []

        if precip_mm > 0:
            water_mol = (precip_mm * 10000.0 * 55.5
                         * self.precip_infiltration)
            reaction_lines.append(f"  H2O    {water_mol:.6e}  # 降水入渗")
            # Q7: 降水化学离子 (酸雨组分) 随入渗水进入溶液
            # 入渗水量(L) = 降水(mm) × 10000(m2/ha) × 入渗系数 (1mm=1L/m2)
            if self.precip_chem is not None:
                water_L = precip_mm * 10000.0 * self.precip_infiltration
                amounts = self.precip_chem.reaction_amounts(water_L)
                for sp, mol in amounts.items():
                    if mol > 0:
                        reaction_lines.append(
                            f"  {sp:<8} {mol:.6e}  # 降水{sp}")

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
            n_reaction = advance_nitrification(state, action)
        h_mol = n_reaction.get('H+', 0.0)
        if h_mol > 0:
            reaction_lines.append(f"  H+     {h_mol:.6e}  # 硝化产酸")

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



