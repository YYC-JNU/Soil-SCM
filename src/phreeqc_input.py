"""
模块: phreeqc_input.py
功能: PHREEQC 输入字符串构建器 — 从引擎状态与配置生成完整 PHREEQC 输入

2026-09-02 (候选3): 从 src/phreeqc_engine.PhreeqcEngine._build_phreeqc_input
迁出为独立深层模块。接口 = 土壤化学状态 + forcing + 操作 + 剖面 + 配置
(PhreeqcInputConfig) → 完整输入字符串; 纯函数、零引擎依赖、零副作用。
引擎 (adapter) 经薄委托复用。注入通道规则各归其段, 可毫秒级字符串断言测试。

配置契约: PhreeqcInputConfig 承载构建所需的全部引擎参数 (原 self.* 依赖面),
由引擎 __init__ 构建一次, 每步构建输入时以快照传入 (局部可变字段如
in_pre_equilibration 由调用方按需更新)。
"""

from dataclasses import dataclass
from typing import Any, List, Optional

from src.constants import (KNOBS_ITERATIONS, KNOBS_ITERATIONS_DEEP,
                           KNOBS_DEEP_START_LAYER,
                           KNOBS_TOLERANCE, KNOBS_TOLERANCE_PRE,
                           KNOBS_CONVERGENCE_TOLERANCE,
                           ALX3_SELECTIVITY_LOGK, ALX3_DEFAULT_LOGK,
                           HX_LOGK,
                           AMORPHOUS_ALOH3_LOGK_DATABASE,
                           HFO_SPECIFIC_AREA, HFO_STRONG_SITE_DENSITY,
                           HFO_WEAK_SITE_DENSITY)
from src.utils import layer_aloh3_params
from src.geochemistry import (advance_nitrification,
                              exchange_base_ratios,
                              weathering_arrhenius_factor)


@dataclass
class PhreeqcInputConfig:
    """PHREEQC 输入构建器配置 (原 _build_phreeqc_input 的 self.* 依赖面)

    纯数据快照 — 构建输入时由调用方 (引擎) 从 self 填充后传入。
    """
    # ---- 惰性阴离子/电荷配对 ----
    anion_defined: bool = False
    pair_anion: str = "An"
    charge_pairing_enabled: bool = False
    # ---- 伴随淋失 (companion) ----
    companion_enabled: bool = False
    companion_cfg: Optional[Any] = None
    # ---- 盐基淋失强化 (E_base) ----
    base_leaching_enabled: bool = False
    # ---- 矿物风化注入 ----
    weathering_enabled: bool = False
    weathering_cfg: Optional[Any] = None
    # ---- 硝化 ----
    nitrification_k1: float = 1.0
    nitrification_k2: float = 0.4
    # ---- 水文注入 ----
    precip_infiltration: float = 0.05
    precip_chem: Optional[Any] = None
    # ---- 矿物缩放 / SURFACE ----
    mineral_scale: float = 0.001
    enable_surface: bool = False
    # ---- 收敛容差 (KNOBS) ----
    in_pre_equilibration: bool = False
    surface_iterations: int = 1000


def _pick_knobs_iterations(cfg: PhreeqcInputConfig,
                           layer_index=None, n_layers=None) -> int:
    """工单86 (2026-08-31): 分层 KNOBS 迭代选择 (纯逻辑)

    优先级: SURFACE 强制 1000 (既有行为, test_knobs_surface_iterations_1000)
    > 深层 (L3/L4, KNOBS_ITERATIONS_DEEP) > 浅层/缺省 (KNOBS_ITERATIONS)。
    与引擎原 _pick_knobs_iterations 语义一致 (纯函数化迁移)。
    """
    if cfg.enable_surface:
        return cfg.surface_iterations
    if (layer_index is not None and n_layers is not None
            and n_layers >= 2
            and layer_index + 1 >= KNOBS_DEEP_START_LAYER):
        return KNOBS_ITERATIONS_DEEP
    return KNOBS_ITERATIONS


def build_phreeqc_input(state, forcing, action, profile, cfg: PhreeqcInputConfig,
                        n_reaction=None, solution_water_L=None,
                        inject_water=True, knobs_tolerance=None,
                        knobs_iterations=None, layer_index=None,
                        n_layers=None) -> str:
    """构建完整 PHREEQC 输入字符串 (纯函数, 2026-09-02 由引擎方法迁出)

    参数:
        state: 土壤化学状态 (SoilState)
        forcing: 当月气候/事件 forcing dict
        action: 操作指令 (MonthlyAction 或 equivalent)
        profile: 土壤剖面数据
        cfg: 构建器配置快照 (PhreeqcInputConfig)
        n_reaction: 本月氮反应量 {'NH4+','NO3-','H+','nitrified','hydrolyzed'}
            (mol); None 时内部调用 advance_nitrification 计算。
        solution_water_L / inject_water: 体积-θ 耦合参数 (v0.6.0)
        knobs_tolerance / knobs_iterations: 覆盖 KNOBS 收敛参数 (None=默认策略)
        layer_index / n_layers: 分层参数透传 (工单86)

    返回:
        str: 完整 PHREEQC 输入
    """
    lines = []

    # 工单D: 分层 Al(OH)3(a) log_k 覆盖 (仅分层 logk != 数据库值时注入)
    aloh3 = layer_aloh3_params(layer_index, n_layers)
    if aloh3['logk'] != AMORPHOUS_ALOH3_LOGK_DATABASE:
        lines.append("PHASES")
        lines.append("  Al(OH)3(a)")
        lines.append("    Al(OH)3 + 3 H+ = Al+3 + 3 H2O")
        lines.append(f"    -log_k {aloh3['logk']}")
        lines.append("")

    # 惰性阴离子物种定义 (工单71/77: companion 或 charge pairing 或 E_base 启用)
    if cfg.anion_defined:
        an_name = cfg.pair_anion
        an_species = f"{an_name}-"
        lines.append("SOLUTION_MASTER_SPECIES")
        lines.append(f"    {an_name}    {an_species}    0.0    {an_name}    35.453")
        lines.append("")
        lines.append("SOLUTION_SPECIES")
        lines.append(f"    {an_species} = {an_species}")
        lines.append("    -log_k    0.0")
        lines.append("")

    # KNOBS (工单78/82/86; 不注入 -step_size 见工单82 数据驱动教训)
    iterations = knobs_iterations if knobs_iterations is not None \
        else _pick_knobs_iterations(cfg, layer_index, n_layers)
    tolerance = knobs_tolerance
    if tolerance is None:
        tolerance = (KNOBS_TOLERANCE_PRE if cfg.in_pre_equilibration
                     else KNOBS_TOLERANCE)
    lines.append("KNOBS")
    lines.append(f"  -iterations {iterations}")
    lines.append(f"  -tolerance {tolerance:.1e}")
    lines.append(f"  -convergence_tolerance {KNOBS_CONVERGENCE_TOLERANCE:.1e}")
    lines.append("")


# EXCHANGE_SPECIES 覆盖 (L9 AlX3 选择性 + HX 酸库, 工单76 B 调优 2.8)
    if ALX3_SELECTIVITY_LOGK != ALX3_DEFAULT_LOGK:
        lines.append("EXCHANGE_SPECIES")
        lines.append("Al+3 + 3 X- = AlX3")
        lines.append(f"    -log_k {ALX3_SELECTIVITY_LOGK}")
        lines.append("")
    lines.append("EXCHANGE_SPECIES")
    lines.append("H+ + X- = HX")
    lines.append(f"    -log_k {HX_LOGK}")
    lines.append("")

    # SOLUTION 块 (体积-θ 耦合: solution_water_L 覆盖 state.volume)
    lines.append("SOLUTION 1")
    water_volume = solution_water_L if solution_water_L is not None \
        else state.volume
    lines.append(f"  -water      {water_volume:.6e}")
    lines.append(f"  temp      {forcing['temp']}")
    lines.append(f"  pH        {state.ph}")
    lines.append("  pe        4.0")
    lines.append("  units     mol/L")
    for ion, conc in state.solution.items():
        if ion not in ['temp', 'pH', 'pe', 'units']:
            # v0.6.0: 离子浓度下限 1e-10 mol/L (事件级小水量数值稳定性)
            lines.append(f"  {ion:<8} {max(float(conc), 1e-10):.6e}")
    lines.append("")

    # EXCHANGE 块 (绝对摩尔量, 平衡重分配)
    lines.append("EXCHANGE 1")
    for species, amount in state.exchange.items():
        lines.append(f"  {species:<8} {amount:.6e}")
    lines.append("")

    # EQUILIBRIUM_PHASES 块 (工单73: degrade_minerals 从平衡相降级; 矿物量×缩放)
    lines.append("EQUILIBRIUM_PHASES 1")
    degrade_set = set(cfg.weathering_cfg.degrade_minerals
                      if cfg.weathering_enabled else [])
    for mineral, moles in state.minerals.items():
        if mineral in degrade_set:
            continue
        if moles > 0:
            if mineral == 'Al(OH)3(a)':
                scaled = moles * layer_aloh3_params(
                    layer_index, n_layers)['scale']
            else:
                scaled = moles * cfg.mineral_scale
            lines.append(f"  {mineral:<15} 0.0  {scaled:.6e}")
    lines.append("")

    # GAS_PHASE 块 (CO2 分压来自气候强迫, F1 修复: 不再硬编码 0.015)
    pco2 = forcing.get('pCO2', 0.015)
    lines.append("GAS_PHASE 1")
    lines.append("  -fixed_pressure")
    lines.append(f"  -pressure     {pco2:.6f}")
    lines.append("  CO2(g)        1.0")
    lines.append("")

    return _build_tail(lines, state, forcing, action, cfg, n_reaction,
                       inject_water)


def _build_tail(lines, state, forcing, action, cfg, n_reaction, inject_water):
    """构建尾部: SURFACE → REACTION → SELECTED_OUTPUT (2026-09-02 拆分)

    承接 build_phreeqc_input 的 GAS_PHASE 之后; REACTION 注入通道规则集中在
    _collect_reaction_lines, 便于逐通道独立测试。
    """
    # SURFACE 块 (WF4: Hfo_s/Hfo_w 铁氧化物表面络合, 默认关闭)
    # PHREEQC 语法: {name} {表面积m2} {比表面m2/g} {位点密度mol/m2}
    if cfg.enable_surface and state.surface:
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

    # 单一 REACTION 块: 降水入渗 + 施肥 + 石灰等全部注入通道合并
    # (PHREEQC 多 REACTION 块共存时仅第一个生效, 故合并为一块)
    reaction_lines = _collect_reaction_lines(
        state, forcing, action, cfg, n_reaction, inject_water)
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
    totals_line = "  -totals Ca Mg K Na Al P Zn Cl C S N Si F"
    if cfg.anion_defined:
        totals_line += f" {cfg.pair_anion}"
    lines.append(totals_line)
    lines.append("  -molalities CaX2 MgX2 KX NaX AlX3 HX X-")
    mineral_names = [m for m, v in state.minerals.items() if v > 0]
    if mineral_names:
        lines.append("  -equilibrium_phases " + " ".join(mineral_names))
    lines.append("END")

    return "\n".join(lines)


def _collect_reaction_lines(state, forcing, action, cfg: PhreeqcInputConfig,
                            n_reaction, inject_water) -> List[str]:
    """收集 REACTION 块的行 (2026-09-02 由引擎方法迁出, 注入通道规则集中地)"""
    reaction_lines = []
    precip_mm = forcing['precip']

    # ---- 水文注入: 降水入渗 + 优先流 + 层间平流 ----
    if precip_mm > 0 or forcing.get('inflow_water_L'):
        inflow_water_L = forcing.get('inflow_water_L')
        if inflow_water_L is not None:
            water_L = inflow_water_L
        else:
            water_L = precip_mm * 10000.0 * cfg.precip_infiltration
        water_mol = water_L * 55.5  # 1 L H2O ≈ 55.5 mol
        # v0.6.0 (Q5): 体积-θ 耦合 (inject_water=False) 时不注入 H2O
        if inject_water and water_mol > 0:
            reaction_lines.append(f"  H2O    {water_mol:.6e}  # 降水入渗")
        # Q7: 降水化学离子随入渗水进入溶液
        if cfg.precip_chem is not None and water_L > 0:
            amounts = cfg.precip_chem.reaction_amounts(water_L)
            for sp, mol in amounts.items():
                if mol > 0:
                    reaction_lines.append(f"  {sp:<8} {mol:.6e}  # 降水{sp}")

        # v0.5.2: 大孔隙优先流 (绕过表层直通 L2, 携带原始降水化学)
        bypass_water_L = forcing.get('bypass_water_L', 0.0)
        if bypass_water_L > 0:
            if inject_water:
                bypass_mol = bypass_water_L * 55.5
                reaction_lines.append(f"  H2O    {bypass_mol:.6e}  # 优先流")
            if cfg.precip_chem is not None:
                b_amounts = cfg.precip_chem.reaction_amounts(bypass_water_L)
                for sp, mol in b_amounts.items():
                    if mol > 0:
                        reaction_lines.append(
                            f"  {sp:<8} {mol:.6e}  # 优先流{sp}")

    # WF2/Q2+Q7: 层间平流输入 — 上层排水溶质 (mol) 注入本层
    inflow_ions = forcing.get('inflow_ions')
    if inflow_ions:
        for ion, mol in inflow_ions.items():
            if mol > 0:
                reaction_lines.append(f"  {ion:<8} {mol:.6e}  # 上层排水")

    # ---- 氮过程: 硝化产酸 (L4 Q3=A: 只注 H+ 不注 N) + 电荷配对 ----
    if n_reaction is None:
        n_reaction = advance_nitrification(
            state, action,
            k1=cfg.nitrification_k1, k2=cfg.nitrification_k2)
    h_mol = n_reaction.get('H+', 0.0)
    if h_mol > 0:
        reaction_lines.append(f"  H+     {h_mol:.6e}  # 硝化产酸")
        if cfg.charge_pairing_enabled:
            reaction_lines.append(
                f"  {cfg.pair_anion}- {h_mol:.6e}  # 电荷配对")

    # ---- NH4+ 等效置换 (工单72): 按交换相电荷占比注入盐基 ----
    if (cfg.companion_enabled and cfg.companion_cfg
            and cfg.companion_cfg.nh4_exchange
            and not forcing.get('skip_nitrification')
            and n_reaction.get('nitrified', 0.0) > 0):
        nh4_eq = n_reaction['nitrified']
        ratios = exchange_base_ratios(state.exchange)
        if ratios:
            for ion, frac in ratios.items():
                eq = nh4_eq * frac
                reaction_lines.append(f"  {ion} {eq:.6e}  # NH4+ 置换")
                if cfg.charge_pairing_enabled:
                    charge = 2 if ion in ('Ca+2', 'Mg+2') else 1
                    reaction_lines.append(
                        f"  {cfg.pair_anion}- {charge * eq:.6e}  # 电荷配对")

    # ---- 伴随淋失 (工单71): E_loss 分级注入 (惰性阴离子 / H+ / 配对) ----
    companion_anion_eq = forcing.get('companion_anion_eq', 0.0)
    companion_acid_eq = forcing.get('companion_acid_eq', 0.0)
    if companion_anion_eq > 0 and cfg.companion_enabled:
        an_species = f"{cfg.companion_cfg.inert_anion}-"
        reaction_lines.append(f"  {an_species} {companion_anion_eq:.6e}  # 伴随淋失")
    if companion_acid_eq > 0:
        reaction_lines.append(f"  H+     {companion_acid_eq:.6e}  # 伴随淋失酸化")
        if cfg.charge_pairing_enabled:
            reaction_lines.append(
                f"  {cfg.pair_anion}- {companion_acid_eq:.6e}  # 电荷配对")

    # ---- 盐基淋失强化 (工单80): E_base 分级注入 An- ----
    base_anion_eq = forcing.get('base_anion_eq', 0.0)
    if base_anion_eq > 0 and cfg.base_leaching_enabled:
        reaction_lines.append(
            f"  {cfg.pair_anion}- {base_anion_eq:.6e}  # 盐基淋失伴随")

    # ---- 矿物风化 (工单73): Arrhenius 温度依赖的集总碱度注入 ----
    if cfg.weathering_enabled:
        wth = cfg.weathering_cfg
        temp_c = forcing.get('temp', 25.0)
        arrhenius = weathering_arrhenius_factor(
            temp_c, wth.activation_energy_kJ)
        monthly_molc = wth.rate_molc_ha_yr / 12.0 * arrhenius
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

    # ---- 预平衡观测锚定注入 (见 pre_equilibrate) ----
    injection = forcing.get('injection')
    if injection:
        for sp, mol in injection.items():
            if abs(mol) > 1e-12:
                reaction_lines.append(
                    f"  {sp:<8} {mol:.6e}  # 预平衡锚定")
                if (cfg.charge_pairing_enabled and mol > 0.0):
                    charge = 3 if sp == 'Al+3' else (
                        2 if sp in ('Ca+2', 'Mg+2') else 1)
                    reaction_lines.append(
                        f"  {cfg.pair_anion}- {charge * mol:.6e}  # 电荷配对")

    # ---- 施肥 (磷/钾/镁/锌 + 电荷配对) ----
    if action.apply_fertilizer:
        p_mol = action.p2o5_amount * 1000.0 / 141.94 * 2.0
        if p_mol > 0:
            reaction_lines.append(f"  H2PO4- {p_mol:.6e}  # 磷肥")
        k_mol = action.k2o_amount * 1000.0 / 94.20 * 2.0
        if k_mol > 0:
            reaction_lines.append(f"  K+     {k_mol:.6e}  # 钾肥")
            if cfg.charge_pairing_enabled:
                reaction_lines.append(
                    f"  {cfg.pair_anion}- {k_mol:.6e}  # 电荷配对")
        mg_mol = action.mgo_amount * 1000.0 / 40.30
        if mg_mol > 0:
            reaction_lines.append(f"  Mg+2   {mg_mol:.6e}  # 镁肥")
            if cfg.charge_pairing_enabled:
                reaction_lines.append(
                    f"  {cfg.pair_anion}- {2.0 * mg_mol:.6e}  # 电荷配对")
        zn_mol = action.znso4_amount * 1000.0 / 161.47
        if zn_mol > 0:
            reaction_lines.append(f"  Zn+2   {zn_mol:.6e}  # 硫酸锌")
            reaction_lines.append(f"  SO4-2  {zn_mol:.6e}  # 硫酸锌")

    # ---- 石灰 (CaO 水化产碱: Ca2+ + 2OH-) ----
    if action.apply_lime:
        lime_mol = action.lime_amount * 1000.0 / 56.08
        if lime_mol > 0:
            reaction_lines.append(f"  Ca     {lime_mol:.6e}  # 生石灰Ca2+")
            reaction_lines.append(f"  H      {-2*lime_mol:.6e}  # 水化OH-")

    return reaction_lines