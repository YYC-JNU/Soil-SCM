"""
模块: initial_condition.py
功能: 将土壤普查数据转换为 PHREEQC 可识别的初始状态

输入: SoilProfile 对象、矿物数据库信息、配置参数
输出: PHREEQC 输入字符串、初始状态对象

核心转换逻辑:
  1. 土壤质量计算 (容重 × 厚度 × 面积)
  2. CEC 单位转换 (cmol(+)/kg → mol)
  3. 交换性阳离子 → EXCHANGE 块
  4. 矿物质量分数 → EQUILIBRIUM_PHASES 块
  5. 溶液初始浓度估算 → SOLUTION 块
  6. CO2 分压 → GAS_PHASE 块
  7. 有机质/铁铝氧化物 → SURFACE 块 (可选)

参考文献:
  熊毅, 李庆逵. 中国土壤. 科学出版社, 1987.
  龚子同. 中国土壤地理. 江苏科学技术出版社, 2004.
  Brook G.A. et al. (1983). Earth Surface Processes and Landforms, 8(1), 79-88.
  Davidson E.A. & Trumbore S.E. (1995). Tellus B, 47(5), 550-565.
  Lindsay W.L. Chemical Equilibria in Soils. John Wiley & Sons, 1979.
  Plummer L.N. et al. (1978). American Journal of Science, 278(2), 179-216.
"""

import numpy as np
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from src.logging_config import get_logger
from src.constants import (MINERAL_SCALE, HFO_STRONG_SITE_DENSITY,
                           HFO_WEAK_SITE_DENSITY, HFO_TARGET_SITES,
                           HENRY_CO2 as _HENRY_CO2,
                           KA1_H2CO3 as _KA1_H2CO3,
                           KA2_HCO3 as _KA2_HCO3,
                           KW_WATER as _KW_WATER,
                           CHARGE_BALANCE_CL_RESIDUAL,
                           SOLUTION_TOTAL_CATION_CONC,
                           AMORPHOUS_ALOH3_MASS_FRACTION,
                           AMORPHOUS_ALOH3_MOLAR_MASS,
                           GAP_AL_FRACTION,
                           GAP_H_FRACTION,
                           WEATHERED_GAP_CEC_THRESHOLD,
                           WEATHERED_GAP_AL_FRACTION,
                           WEATHERED_GAP_H_FRACTION,
                           INITIAL_PSI_CM)
from src.utils import cmol_to_mol_per_kg
from src.vgm import vgm_theta_from_psi, get_vgm_params

logger = get_logger("initial_condition")


class InitialConditionBuilder:
    """初始条件构建器

    将土壤普查数据（pH、CEC、交换性阳离子、有机质、矿物组成等）
    转换为 PHREEQC 可识别的初始状态。

    类比大气模式: 类似于 WRF 的 real.exe，将观测/再分析数据
    转换为模式可识别的初始场。
    """

    # ============================================================
    # 热力学常数 (25°C) — Q19 收敛: 数值来自 src/constants.py (单一事实来源)
    # ============================================================
    KH_CO2 = _HENRY_CO2     # CO2 Henry's law constant, mol/(L·atm)
    KA1_H2CO3 = _KA1_H2CO3  # H2CO3 第一级解离常数
    KA2_HCO3 = _KA2_HCO3    # HCO3- 第二级解离常数
    KW = _KW_WATER          # 水的离子积
    KSP_AL_OH3 = 3.0e-34   # Al(OH)3 溶度积
    KSP_FE_OH3 = 2.8e-39   # Fe(OH)3 溶度积

    # 铁氧化物表面位点密度 (mol/kg 铁氧化物) — WF4 已移入 constants.py
    # FE_OXIDE_SITE_DENSITY 由 HFO_SITE_DENSITY 取代; OM_SITE_DENSITY 因
    # phreeqc.dat 无有机质表面物种而废弃 (见 WF3/WF4)。

    def __init__(self, soil_profile, mineral_db_info, pCO2: float,
                 initial_psi_cm: float = INITIAL_PSI_CM):
        """
        参数:
            soil_profile: SoilProfile 对象 (来自 input_reader.py)
            mineral_db_info: SoilTypeInfo 对象 (来自 soil_database.py)
            pCO2: 初始 CO2 分压 (atm)
            initial_psi_cm: v0.5.3: 初始基质势 (cm, 负值, 默认 −100 田间持水量,
                经 VGM 正算 θ_init 驱动初始溶液体积, D8/Q8)
        """
        self.profile = soil_profile
        self.mineral_info = mineral_db_info
        self.pCO2 = pCO2
        self.initial_psi_cm = initial_psi_cm

        # 计算衍生量 (复用 SoilProfile 已有属性, 消除重复实现, T04)
        # 注意: porosity 必须先于 solution_volume 计算
        # ( _calc_solution_volume 内部引用 self.porosity )
        self.soil_mass_kg = self.profile.soil_mass_per_ha
        self.porosity = self.profile.porosity
        # v0.5.3: 初始 θ 由 VGM 从初始水势 (田间持水量) 正算 (D8, 废弃 50% 饱和)
        theta_r, alpha, n = get_vgm_params(self.profile)
        self.theta_init = vgm_theta_from_psi(
            self.initial_psi_cm, self.porosity, theta_r, alpha, n)
        self.solution_volume_L = self._calc_solution_volume()
        self.cec_total_mol = self._calc_cec_total()

    # ============================================================
    # 基础物理量计算
    # ============================================================

    def _calc_solution_volume(self) -> float:
        """估算土壤溶液体积 (L/ha) — v0.5.3: θ_init×depth×1e5 (D8/Q8)

        化学初始溶液体积与水文初始 θ (VGM 田间持水量正算) 严格联动,
        废弃"50% 饱和度"假设 (同一层不再出现化学 50% 饱和 vs 水文
        VGM 田间持水的矛盾态; 决策 D8, spec 49 Q8)。

        返回:
            溶液体积 (L/ha)
        """
        return self.theta_init * self.profile.effective_depth * 1e5

    def _calc_cec_total(self) -> float:
        """将 CEC 从 cmol(+)/kg 转换为 mol (对于整个土柱)

        公式: CEC_total(mol) = CEC(cmol(+)/kg) / 100 × soil_mass(kg)
        换算复用 utils.cmol_to_mol_per_kg (单一事实来源, T04)

        返回:
            CEC 总量 (mol)
        """
        cec_mol_per_kg = cmol_to_mol_per_kg(self.profile.cec)  # cmol(+)/kg → mol/kg
        cec_total_mol = cec_mol_per_kg * self.soil_mass_kg
        return cec_total_mol

    # ============================================================
    # SOLUTION 块: 溶液初始浓度估算
    # ============================================================

    def build_solution(self) -> Dict[str, float]:
        """估算溶液初始离子浓度 (mol/L)

        方法:
          1. 基于 pH 计算 H⁺, OH⁻
          2. 基于 pH 和 pCO2 计算碳酸平衡 (H2CO3, HCO3-, CO3^2-)
          3. 基于交换性阳离子比例估算溶液阳离子浓度
          4. 基于 Al(OH)3 溶度积估算 Al³⁺ 浓度
          5. 假设典型阴离子浓度 (SO4^2-, NO3-, Cl-)
          6. 电荷平衡校验

        参考文献:
          Lindsay W.L. Chemical Equilibria in Soils. John Wiley & Sons, 1979.

        返回:
            dict: 离子名称 → 浓度 (mol/L)
        """
        ph = self.profile.ph
        h_plus = 10.0 ** (-ph)
        oh_minus = self.KW / h_plus

        # ---- 碳酸平衡 ----
        # CO2(g) + H2O ⇌ H2CO3 ⇌ H+ + HCO3- ⇌ 2H+ + CO3^2-
        h2co3 = self.KH_CO2 * self.pCO2
        hco3 = self.KA1_H2CO3 * h2co3 / h_plus
        co3 = self.KA2_HCO3 * hco3 / h_plus
        total_inorganic_carbon = h2co3 + hco3 + co3

        # ---- Al³⁺ 浓度 (基于 Al(OH)3 溶度积) ----
        # Al(OH)3(s) ⇌ Al³⁺ + 3OH⁻
        # Ksp = [Al³⁺][OH⁻]³
        # [Al³⁺] = Ksp × [H⁺]³ / Kw³
        al3plus = self.KSP_AL_OH3 * h_plus**3 / self.KW**3
        # 限制 Al³⁺ 浓度上限 (避免极端值)
        al3plus = min(al3plus, 1e-3)

        # ---- 阳离子浓度估算 ----
        # 基于交换性阳离子比例分配典型总阳离子浓度
        total_base = (self.profile.exch_ca + self.profile.exch_mg +
                      self.profile.exch_k + self.profile.exch_na)

        if total_base > 0:
            ca_frac = self.profile.exch_ca / total_base
            mg_frac = self.profile.exch_mg / total_base
            k_frac = self.profile.exch_k / total_base
            na_frac = self.profile.exch_na / total_base
        else:
            ca_frac = mg_frac = k_frac = na_frac = 0.25

        # 红壤典型总阳离子浓度 (mol/L) — 土壤溶液浓度 (田间持水)
        # 参考: 熊毅, 李庆逵. 中国土壤. 科学出版社, 1987.
        # 注意: 溶液体积为田间持水 (8.2e5 L/ha), 浓度应为土壤溶液量级
        # (与交换相自洽); 曾尝试淋溶液量级 5e-5 触发 NaX 失衡碱化 (见常量注释)
        total_cation_conc = SOLUTION_TOTAL_CATION_CONC  # mol/L

        ca_conc = ca_frac * total_cation_conc
        mg_conc = mg_frac * total_cation_conc
        k_conc = k_frac * total_cation_conc
        na_conc = na_frac * total_cation_conc

        # ---- 阴离子浓度 (典型值) ----
        # 参考: 张远辉等. 中国酸雨研究进展. 环境科学, 2003.
        so4_conc = 5e-5    # SO4^2- (mol/L)
        no3_conc = 1e-5    # NO3^- (mol/L)
        # Cl^-: 背景微量 (L5 修正: 电荷盈余由 Cl- 兜底, 大盈余下数值由盈余
        # 决定; 保留背景值避免降水化学 Cl- 输入与初始完全归零的数值边缘)
        cl_conc = CHARGE_BALANCE_CL_RESIDUAL

        # ---- 电荷平衡修正 (L5, v0.3.0 修正) ----
        # 背景: 初始溶液阳离子电荷高于阴离子, 若不修正, PHREEQC 平衡时只能靠
        # OH- 补足电中性, 平衡 pH 大幅偏离。
        # L5 修正要点 (经实测校准):
        #   - HCO3- 浓度由 pCO2 决定 (亨利定律, 与 GAS_PHASE 开放体系自洽)
        #   - _check_charge_balance 用碳酸体系真实电荷 (替代旧 C(4) 一价简化)
        #   - 电荷盈余由强酸阴离子 Cl- 兜底 (Q13): pH<6 时 HCO3- 承载能力
        #     有限 (pH=5 时仅 ~2e-5 mol/L), 强制 HCO3 补足会使 C(4) 暴涨至
        #     0.09 mol/L (物理不可能, PHREEQC 数值失稳, 实测)。Cl- 是土壤
        #     溶液主要强酸阴离子, 由其承担盈余是物理必要的。
        #   - Cl- 保留"微量"仅在盈余小 (接近平衡) 时成立; 大盈余下 Cl- 为
        #     平衡所需, 数值由盈余决定。
        cation_charge = (2.0 * ca_conc + 2.0 * mg_conc + k_conc +
                         na_conc + 3.0 * al3plus + h_plus)
        anion_charge_without_cl = (2.0 * so4_conc + no3_conc +
                                   hco3 + 2.0 * co3 + oh_minus)
        charge_imbalance = cation_charge - anion_charge_without_cl
        if charge_imbalance > 0:
            cl_conc += charge_imbalance  # Cl- 一价兜底 (Q13/L5 修正)

        # ---- 组装溶液 ----
        solution = {
            'temp': 25.0,
            'pH': ph,
            'pe': 4.0,          # 氧化还原电位 (典型红壤值)
            'units': 'mol/L',
            'Ca': ca_conc,
            'Mg': mg_conc,
            'K': k_conc,
            'Na': na_conc,
            'Al': al3plus,
            'S(6)': so4_conc,   # SO4^2-
            'N(5)': no3_conc,   # NO3^-
            'Cl': cl_conc,
            'C(4)': total_inorganic_carbon,  # 无机碳
        }

        return solution

    def _check_charge_balance(self, solution: Dict[str, float]) -> float:
        """检查溶液电荷平衡

        公式:
          阳离子电荷总和 = 阴离子电荷总和
          2[Ca²⁺] + 2[Mg²⁺] + [K⁺] + [Na⁺] + 3[Al³⁺] + [H⁺]
          = 2[SO₄²⁻] + [NO₃⁻] + [Cl⁻] + [HCO₃⁻] + 2[CO₃²⁻] + [OH⁻]

        碳酸体系 (L5, v0.3.0): 从 C(4) 总量按解离平衡拆分 HCO3-/CO3-2,
        用真实电荷 (HCO3- 一价 + CO3-2 二价), 替代旧一价简化。

        返回:
            电荷不平衡度 (mol/L)
        """
        h_plus = 10.0 ** (-solution['pH'])
        oh_minus = self.KW / h_plus

        cation_charge = (
            2.0 * solution.get('Ca', 0) +
            2.0 * solution.get('Mg', 0) +
            solution.get('K', 0) +
            solution.get('Na', 0) +
            3.0 * solution.get('Al', 0) +
            h_plus
        )

        # 碳酸体系拆分 (L5): C(4) = H2CO3 + HCO3- + CO3-2
        c4 = solution.get('C(4)', 0.0)
        h2co3 = c4 / (1.0 + self.KA1_H2CO3 / h_plus +
                      self.KA1_H2CO3 * self.KA2_HCO3 / h_plus ** 2)
        hco3 = h2co3 * self.KA1_H2CO3 / h_plus
        co3 = hco3 * self.KA2_HCO3 / h_plus

        anion_charge = (
            2.0 * solution.get('S(6)', 0) +
            solution.get('N(5)', 0) +
            solution.get('Cl', 0) +
            hco3 + 2.0 * co3 +   # L5: 碳酸体系真实电荷 (替代 C(4) 一价)
            oh_minus
        )

        imbalance = cation_charge - anion_charge
        return imbalance

    # ============================================================
    # EXCHANGE 块: 交换位点
    # ============================================================

    def build_exchange(self) -> Dict[str, float]:
        """构建交换位点数据

        将交换性阳离子从 cmol(+)/kg 转换为 mol (对于整个土柱)

        注意: cmol(+)/kg 是电荷摩尔数，需要除以离子电荷数
        才能得到离子摩尔数。

        PHREEQC EXCHANGE 写法:
          CaX2: 每个 CaX2 包含 1 个 Ca²⁺ 和 2 个 X⁻
          MgX2: 每个 MgX2 包含 1 个 Mg²⁺ 和 2 个 X⁻
          KX:   每个 KX 包含 1 个 K⁺ 和 1 个 X⁻
          NaX:  每个 NaX 包含 1 个 Na⁺ 和 1 个 X⁻
          AlX3: 每个 AlX3 包含 1 个 Al³⁺ 和 3 个 X⁻
          HX:   每个 HX 包含 1 个 H⁺ 和 1 个 X⁻

        参考文献:
          Lindsay W.L. Chemical Equilibria in Soils. John Wiley & Sons, 1979.

        返回:
            dict: 交换复合物名称 → 摩尔量 (mol)
        """
        # 交换性阳离子 (cmol(+)/kg → 离子摩尔数 mol/kg)
        # 注意: cmol(+)/kg 是电荷摩尔数，需要除以离子电荷数
        ca_ion_mol_per_kg = self.profile.exch_ca / 2.0 / 100.0  # Ca²⁺
        mg_ion_mol_per_kg = self.profile.exch_mg / 2.0 / 100.0  # Mg²⁺
        k_ion_mol_per_kg = self.profile.exch_k / 1.0 / 100.0    # K⁺
        na_ion_mol_per_kg = self.profile.exch_na / 1.0 / 100.0  # Na⁺
        al_ion_mol_per_kg = self.profile.exch_al / 3.0 / 100.0  # Al³⁺
        # v0.6.1 (spec 62 Q7): 交换性 H 直接映射 HX 交换物种 (不再并入 Na)。
        # phreeqc.dat 的 "H+ + X- = HX" 被注释禁用, 由引擎层 EXCHANGE_SPECIES
        # 自定义注入 (log_k=HX_LOGK, phreeqc_engine._build_phreeqc_input)。
        h_ion_mol_per_kg = self.profile.exch_h / 1.0 / 100.0    # H⁺

        # 转换为整个土柱的摩尔数
        ca_mol = ca_ion_mol_per_kg * self.soil_mass_kg
        mg_mol = mg_ion_mol_per_kg * self.soil_mass_kg
        k_mol = k_ion_mol_per_kg * self.soil_mass_kg
        na_mol = na_ion_mol_per_kg * self.soil_mass_kg
        al_mol = al_ion_mol_per_kg * self.soil_mass_kg
        h_mol = h_ion_mol_per_kg * self.soil_mass_kg

        # 用 HX/AlX3/NaX 三通道按比例补齐 CEC 未覆盖的位点 (v0.6.1 Q7)
        # 历史: v0.5.0 B 诊断用 GAP_AL_FRACTION 折中 (全 Al pH 偏低 4.36 /
        # 全 Na 盐基偏高); v0.6.1 引入 GAP_H_FRACTION 提供交换性酸真实缓冲:
        #   缺口 × GAP_H_FRACTION → HX (一价酸), 缺口 × GAP_AL_FRACTION → AlX3 (三价),
        #   缺口 × (1−GAP_H−GAP_AL) → NaX (一价盐基)
        covered_charge_cmol = (
            self.profile.exch_ca + self.profile.exch_mg +
            self.profile.exch_k + self.profile.exch_na +
            self.profile.exch_al + self.profile.exch_h
        )
        gap_cmol = max(0.0, self.profile.cec - covered_charge_cmol)
        # 工单83 (2026-08-25): 深层风化层 (低 CEC) 缺口 GAP 偏 AlX3 —
        # 红壤风化层交换 Al 主导, 缺口主要补 AlX3 (三价) 而非 NaX (盐基),
        # 减少 NaX 虚高盐基饱和度 (BS); 非风化层保持原三通道 (0.3/0.3/0.4)。
        if self.profile.cec <= WEATHERED_GAP_CEC_THRESHOLD:
            gap_h_cmol = gap_cmol * WEATHERED_GAP_H_FRACTION
            gap_al_cmol = gap_cmol * WEATHERED_GAP_AL_FRACTION
            gap_na_cmol = gap_cmol * (
                1.0 - WEATHERED_GAP_H_FRACTION - WEATHERED_GAP_AL_FRACTION)
        else:
            gap_h_cmol = gap_cmol * GAP_H_FRACTION
            gap_al_cmol = gap_cmol * GAP_AL_FRACTION
            gap_na_cmol = gap_cmol * (1.0 - GAP_H_FRACTION - GAP_AL_FRACTION)
        h_mol += gap_h_cmol / 1.0 / 100.0 * self.soil_mass_kg
        al_mol += gap_al_cmol / 3.0 / 100.0 * self.soil_mass_kg
        na_mol += gap_na_cmol / 1.0 / 100.0 * self.soil_mass_kg

        # PHREEQC EXCHANGE 写法 (HX 由引擎 EXCHANGE_SPECIES 注入定义)
        exchange = {
            'CaX2': ca_mol,
            'MgX2': mg_mol,
            'KX': k_mol,
            'NaX': na_mol,
            'AlX3': al_mol,
            'HX': h_mol,
        }

        return exchange

    def _calc_exchange_site_total(self, exchange: Dict[str, float]) -> float:
        """计算交换位点总量 (mol)

        公式:
          总位点 = CaX2×2 + MgX2×2 + KX×1 + NaX×1 + AlX3×3 + HX×1

        返回:
            总交换位点 (mol)
        """
        total = (
            exchange.get('CaX2', 0) * 2.0 +
            exchange.get('MgX2', 0) * 2.0 +
            exchange.get('KX', 0) * 1.0 +
            exchange.get('NaX', 0) * 1.0 +
            exchange.get('AlX3', 0) * 3.0 +
            exchange.get('HX', 0) * 1.0
        )
        return total

    # ============================================================
    # EQUILIBRIUM_PHASES 块: 矿物相
    # ============================================================

    def build_minerals(self) -> Dict[str, float]:
        """构建矿物相数据

        将矿物质量分数转换为摩尔量 (mol)

        公式:
          mineral_mass(kg) = soil_mass(kg) × mass_fraction
          moles(mol) = mineral_mass(g) / molar_mass(g/mol)

        注意:
          phreeqc.dat 数据库 PHASES 段未定义以下矿物相,
          若直接写入 EQUILIBRIUM_PHASES 块会导致 "Phase not found" 错误,
          因此在生成输入时自动排除。

        返回:
            dict: 矿物名称 → 摩尔量 (mol)
        """
        # phreeqc.dat 不支持的矿物相 (需扩展数据库后启用)
        unsupported = ('anatase',)

        minerals = {}
        for mname, minfo in self.mineral_info.minerals.items():
            if mname in unsupported:
                continue
            if minfo.mass_fraction > 0:
                # 矿物质量 (kg)
                mineral_mass_kg = self.soil_mass_kg * minfo.mass_fraction
                # 摩尔量 (mol)
                moles = mineral_mass_kg * 1000.0 / minfo.molar_mass
                minerals[mname] = moles

        # L9 (v0.4.0): 非晶质氢氧化铝缓冲相 — 解决 fertilizer 单层长期
        # AlX3 耗尽→pH 突升 (Q12* 残留 + Q1+ 矿物压缩)。phreeqc.dat 定义
        # Al(OH)3(a) (非晶质, 更可溶), 交换 Al 被淋失时溶解补充 Al3+,
        # 配合 L2 矿物回填维持 Al 循环。v0.4.0 扫描证实单纯增大
        # MINERAL_SCALE 无效 (矿物化加速 Al 耗尽, 见 docs/reports/V0_3_0_FINAL_REPORT.md)。
        minerals['Al(OH)3(a)'] = (self.soil_mass_kg
                                  * AMORPHOUS_ALOH3_MASS_FRACTION
                                  * 1000.0 / AMORPHOUS_ALOH3_MOLAR_MASS)

        return minerals

    # ============================================================
    # GAS_PHASE 块: 气相
    # ============================================================

    def build_gas_phase(self) -> Dict[str, float]:
        """构建气相数据

        参考文献:
          Brook G.A. et al. (1983). Earth Surface Processes and Landforms.
          Davidson E.A. & Trumbore S.E. (1995). Tellus B, 47(5), 550-565.

        返回:
            dict: 气相参数
        """
        return {
            'pressure': 1.0,       # atm
            'CO2(g)': self.pCO2,   # CO2 分压 (atm)
        }

    # ============================================================
    # SURFACE 块: 表面络合位点 (可选)
    # ============================================================

    def build_surface(self) -> Optional[Dict[str, float]]:
        """构建表面络合数据 (可选, WF4: Hfo_s/Hfo_w 铁氧化物表面)

        返回铁氧化物表面积 (m2), 供引擎生成 SURFACE 块。
        面积按 HFO_TARGET_SITES 目标位点总量反算, 约束在 D&M 模型适用
        浓度范围 (~1e-4 mol/L, 对应表面位点 ~50 mol), 避免数值失稳
        (WF5 实测: 位点 >~100 mol 时 Al/Ca 不收敛)。
        有机质表面 (Som) 不启用: phreeqc.dat 无对应 SURFACE_MASTER_SPECIES。

        参考文献:
          Dzombak & Morel (1990). Surface Complexation Modeling: HFO.
          龚子同. 中国土壤地理. 江苏科学技术出版社, 2004.

        返回:
            dict: {'area_m2': 铁氧化物表面积}, 或 None (无铁氧化物时)
        """
        # ---- 检查是否有铁氧化物 (针铁矿 + 赤铁矿) ----
        fe_oxides = ['goethite', 'hematite']
        fe_mass_kg = 0.0
        for mname in fe_oxides:
            if mname in self.mineral_info.minerals:
                minfo = self.mineral_info.minerals[mname]
                fe_mass_kg += self.soil_mass_kg * minfo.mass_fraction

        if fe_mass_kg <= 0:
            return None

        # 面积 = 目标位点总量 / 总位点密度 (强+弱)
        total_density = (HFO_STRONG_SITE_DENSITY + HFO_WEAK_SITE_DENSITY)
        surface_area_m2 = HFO_TARGET_SITES / total_density
        return {'area_m2': surface_area_m2}

    # ============================================================
    # 生成 PHREEQC 输入字符串
    # ============================================================

    def build_phreeqc_input(self, include_surface: bool = False) -> str:
        """生成完整的 PHREEQC 输入字符串

        参数:
            include_surface: 是否包含表面络合位点

        返回:
            str: PHREEQC 输入字符串
        """
        lines = []

        # ---- SOLUTION 块 ----
        solution = self.build_solution()
        lines.append("SOLUTION 1")
        lines.append(f"  -water      {self.solution_volume_L:.6e}")
        lines.append(f"  temp      {solution['temp']}")
        lines.append(f"  pH        {solution['pH']}")
        lines.append(f"  pe        {solution['pe']}")
        lines.append(f"  units     {solution['units']}")
        for ion, conc in solution.items():
            if ion not in ['temp', 'pH', 'pe', 'units']:
                lines.append(f"  {ion:<8} {conc:.6e}")
        lines.append("")

        # ---- EXCHANGE 块 ----
        exchange = self.build_exchange()
        lines.append("EXCHANGE 1")
        for species, moles in exchange.items():
            lines.append(f"  {species:<8} {moles:.6e}")
        lines.append("")

        # ---- EQUILIBRIUM_PHASES 块 ----
        # 矿物量 = 物理摩尔量 × 缩放系数 (折中方案, 见 docs/analysis/Q1_plus_ANALYSIS.md)
        minerals = self.build_minerals()
        lines.append("EQUILIBRIUM_PHASES 1")
        for mineral, moles in minerals.items():
            if moles > 0:
                scaled = moles * MINERAL_SCALE
                lines.append(f"  {mineral:<15} 0.0  {scaled:.6e}")
        lines.append("")

        # ---- GAS_PHASE 块 (CO2 分压 = 初始 pCO2, F1 修复: 不再硬编码) ----
        lines.append("GAS_PHASE 1")
        lines.append("  -fixed_pressure")
        lines.append(f"  -pressure     {self.pCO2:.6f}")
        lines.append("  CO2(g)        1.0")
        lines.append("")

        # ---- SURFACE 块 (可选) ----
        if include_surface:
            surface = self.build_surface()
            if surface:
                lines.append("SURFACE 1")
                for stype, sites in surface.items():
                    lines.append(f"  {stype:<8} {sites:.6e}")
                    lines.append(f"  -sites  {sites:.6e}")
                    lines.append(f"  -equilibrate solution")
                lines.append("")

        return "\n".join(lines)

    # ============================================================
    # 诊断与打印
    # ============================================================

    def print_summary(self):
        """打印初始条件摘要"""
        print("\n" + "=" * 60)
        print("初始条件摘要")
        print("=" * 60)
        print(f"  土壤质量: {self.soil_mass_kg:.2e} kg/ha")
        print(f"  溶液体积: {self.solution_volume_L:.2e} L/ha")
        print(f"  孔隙度: {self.porosity:.3f}")
        print(f"  CEC 总量: {self.cec_total_mol:.2e} mol")
        print(f"  初始 pH: {self.profile.ph}")
        print(f"  pCO2: {self.pCO2} atm")

        # 交换位点
        exchange = self.build_exchange()
        total_sites = self._calc_exchange_site_total(exchange)
        print(f"\n  交换位点:")
        print(f"    总位点: {total_sites:.4e} mol")
        print(f"    CEC 总量: {self.cec_total_mol:.4e} mol")
        print(f"    差异: {abs(total_sites - self.cec_total_mol):.4e} mol")
        for species, moles in exchange.items():
            print(f"    {species}: {moles:.4e} mol")

        # 溶液浓度
        solution = self.build_solution()
        print(f"\n  溶液初始浓度 (mol/L):")
        for ion, conc in solution.items():
            if ion not in ['temp', 'pH', 'pe', 'units']:
                print(f"    {ion}: {conc:.4e}")

        # 电荷平衡检查
        imbalance = self._check_charge_balance(solution)
        print(f"\n  电荷不平衡度: {imbalance:.4e} mol/L")

        # 矿物相
        minerals = self.build_minerals()
        print(f"\n  矿物相数量: {len(minerals)}")
        for mname, moles in minerals.items():
            print(f"    {mname}: {moles:.4e} mol")

        # 表面位点
        surface = self.build_surface()
        if surface:
            print(f"\n  表面络合位点:")
            for stype, sites in surface.items():
                print(f"    {stype}: {sites:.4e} mol")

        print("=" * 60)

    def validate(self) -> bool:
        """验证初始条件的合理性

        检查:
          1. CEC 与交换性阳离子总和是否一致
          2. 溶液电荷平衡是否在可接受范围内
          3. pH 是否在合理范围内

        返回:
            bool: 是否通过验证
        """
        # 检查 CEC 一致性
        exchange = self.build_exchange()
        total_sites = self._calc_exchange_site_total(exchange)
        cec_diff = abs(total_sites - self.cec_total_mol)
        if cec_diff > 0.01 * self.cec_total_mol:
            logger.warning("CEC 不一致: 交换位点总量=%.4e, CEC=%.4e", total_sites, self.cec_total_mol)

        # 检查溶液电荷平衡
        solution = self.build_solution()
        imbalance = self._check_charge_balance(solution)
        if abs(imbalance) > 1e-4:
            logger.warning("溶液电荷不平衡: %.4e mol/L", imbalance)

        # 检查 pH 范围
        if self.profile.ph < 3.0 or self.profile.ph > 10.0:
            logger.warning("pH 超出合理范围: %s", self.profile.ph)

        return True




