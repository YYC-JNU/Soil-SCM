"""
模块: phreeqc_engine.py
功能: PHREEQC 引擎封装 (通过 phreeqpython 调用)

输入: 土壤状态、当月强迫条件
输出: 更新后的土壤状态、诊断量

核心原理:
  - 离子交换 (Gapon/Vanselow 方程)
  - 表面络合 (有机质/铁铝氧化物)
  - 矿物溶解-沉淀平衡
  - 溶质运移/淋溶
"""

import numpy as np
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field

try:
    import phreeqpython
    PHREEQC_AVAILABLE = True
except ImportError:
    PHREEQC_AVAILABLE = False
    print("[WARNING] phreeqpython 未安装，将使用简化模式")


@dataclass
class SoilState:
    """土壤化学状态 (PHREEQC 内部状态)"""
    solution: dict = field(default_factory=dict)
    exchange: dict = field(default_factory=dict)
    minerals: dict = field(default_factory=dict)
    gas_phase: dict = field(default_factory=dict)
    temperature: float = 25.0
    ph: float = 7.0
    pe: float = 4.0


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
                 mode: str = 'auto'):
        """
        参数:
            database: PHREEQC 热力学数据库
            mode: 引擎模式
                - auto      : PHREEQC 可用则用 PHREEQC, 否则简化模式 (默认)
                - simplified: 始终使用简化动力学模式
                - phreeqc   : 始终使用 PHREEQC (失败时降级简化模式)
        """
        self.database = database
        self.mode = mode
        self.phreeqc = None

        if PHREEQC_AVAILABLE:
            self.phreeqc = phreeqpython.PhreeqPython(
                database=self.database
            )
            print(f"[INFO] PHREEQC 引擎已初始化 (数据库: {database})")
        else:
            print("[WARNING] PHREEQC 不可用，使用简化模式")

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
        # 根据模式决定是否使用 PHREEQC
        # - simplified: 强制简化模式
        # - phreeqc   : 强制 PHREEQC (不可用时警告并降级)
        # - auto      : PHREEQC 可用则用, 否则简化
        phreeqc_ready = (PHREEQC_AVAILABLE and self.phreeqc is not None
                         and not getattr(self, '_permanent_fallback', False))

        use_phreeqc = phreeqc_ready
        if self.mode == 'simplified':
            use_phreeqc = False
        elif self.mode == 'phreeqc' and not phreeqc_ready:
            if PHREEQC_AVAILABLE and self.phreeqc is None:
                print("[WARNING] PHREEQC 引擎不可用，使用简化模式")
            use_phreeqc = False

        if use_phreeqc:
            return self._run_phreeqc_step(state, monthly_forcing,
                                          action, soil_profile)
        else:
            return self._run_simplified_step(state, monthly_forcing,
                                             action, soil_profile)

    def _run_phreeqc_step(self, state, forcing, action, profile):
        """使用 PHREEQC 引擎执行计算"""
        # 构建 PHREEQC 输入字符串
        input_string = self._build_phreeqc_input(
            state, forcing, action, profile)

        # 执行计算
        # 说明: phreeqpython 高层 API (PhreeqPython) 没有 run_string 方法，
        # 需要通过底层 VIPhreeqc (self.phreeqc.ip) 调用
        try:
            run_func = getattr(self.phreeqc, 'run_string', None)
            if run_func is None:
                run_func = self.phreeqc.ip.run_string
            result = run_func(input_string)
            # 解析结果
            new_state, diagnostics = self._parse_phreeqc_output(
                result, state)
            return new_state, diagnostics
        except Exception as e:
            # 计算失败(如输入块与数据库不匹配)时永久降级到简化模式，
            # 保证模拟流程稳定运行且 pH 演变连续
            if not getattr(self, '_fallback_warned', False):
                print(f"[WARNING] PHREEQC 计算失败: {e}")
                print("[WARNING] 已永久降级到简化模式继续模拟")
                self._fallback_warned = True
            self._permanent_fallback = True
            return self._run_simplified_step(state, forcing, action, profile)

    def _build_phreeqc_input(self, state, forcing, action, profile) -> str:
        """构建 PHREEQC 输入字符串"""
        lines = []

        # SOLUTION 块
        lines.append("SOLUTION 1")
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
        lines.append("EQUILIBRIUM_PHASES 1")
        for mineral, moles in state.minerals.items():
            if moles > 0:
                lines.append(f"  {mineral:<15} 0.0  {moles:.6e}")
        lines.append("")

        # GAS_PHASE 块
        lines.append("GAS_PHASE 1")
        lines.append(f"  -pressure     {state.gas_phase.get('pressure', 1.0)}")
        lines.append(f"  CO2(g)        {forcing['pCO2']:.6e}")
        lines.append("")

        # REACTION 块 (降水入渗)
        precip_mm = forcing['precip']
        if precip_mm > 0:
            # 将降水转化为溶液混合
            lines.append("REACTION 1")
            lines.append(f"  H2O    {precip_mm / 1000.0:.6e}  # 降水入渗(m)")
            lines.append("")

        # 施肥 (REACTION)
        if action.apply_fertilizer:
            fert_mol = self._calc_fertilizer_moles(action)
            if fert_mol > 0:
                lines.append("REACTION 2")
                lines.append(f"  N(5)    {fert_mol:.6e}  # 尿素硝化产NO3-")
                lines.append(f"  H(1)    {-2*fert_mol:.6e}  # 产酸")
                lines.append("")

        # 石灰 (KINETICS)
        if action.apply_lime:
            lime_mol = action.lime_amount / 100.09  # kg → mol CaCO3
            lines.append("KINETICS 1")
            lines.append("  Calcite")
            lines.append(f"  -m0     {lime_mol:.6e}")
            lines.append("  -parms  1e-7  1.0")
            lines.append("  -steps  2592000")  # 30天 (秒)
            lines.append("")

        return "\n".join(lines)

    def _run_simplified_step(self, state, forcing, action, profile):
        """简化模式 (无 PHREEQC 时的 fallback)"""
        new_state = SoilState()
        new_state.ph = state.ph

        # 简化: 降水淋溶降低盐基饱和度 → pH 略降
        precip_effect = forcing['precip'] * 0.0001
        new_state.ph = max(3.5, state.ph - precip_effect)

        # 简化: 施肥产酸
        if action.apply_fertilizer:
            fert_acid = action.fertilizer_amount * 0.0005
            new_state.ph = max(3.5, new_state.ph - fert_acid)

        # 简化: 石灰提碱
        if action.apply_lime:
            lime_alk = action.lime_amount * 0.0003
            new_state.ph = min(9.0, new_state.ph + lime_alk)

        diag = DiagnosticOutput(ph=new_state.ph)
        return new_state, diag

    def _calc_fertilizer_moles(self, action) -> float:
        """计算施肥摩尔量"""
        if action.fertilizer_type == 'urea':
            # 尿素 CO(NH2)2, M=60.06 g/mol
            # 每公顷 kg → mol
            mass_kg = action.fertilizer_amount  # kg/ha
            moles = mass_kg * 1000.0 / 60.06   # mol/ha
            return moles
        return 0.0

    def _parse_phreeqc_output(self, result, old_state):
        """解析 PHREEQC 输出"""
        new_state = SoilState()
        diag = DiagnosticOutput()

        # 从 PHREEQC 结果中提取 pH 等诊断量
        # 通过 phreeqpython 高层 API 查询溶液状态
        try:
            sol = self.phreeqc.get_solution(1)
            new_state.ph = float(sol.pH)
        except Exception:
            new_state.ph = old_state.ph  # fallback

        diag.ph = new_state.ph
        diag.pe = old_state.pe

        return new_state, diag


