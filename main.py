"""
Soil-SCM: 土壤物理化学数值模式
主程序入口

用法:
    python main.py [--config config/config.yaml]

功能:
    1. 加载配置和数据库
    2. 读取土壤普查数据
    3. 生成气候强迫
    4. 时间积分主循环
    5. 输出诊断量
"""

import sys
import argparse
import json
import logging
import numpy as np
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.config_manager import ConfigManager, LayerOverrideConfig
from src.soil_database import SoilDatabase, apply_mineral_overrides
from src.input_reader import InputReader
from src.climate_forcing import ClimateForcing
from src.scenario_controller import ScenarioController
from src.phreeqc_engine import PhreeqcEngine
from src.output_writer import OutputWriter
from src.initial_condition import InitialConditionBuilder
from src.logging_config import setup_logging
from src.constants import (DEFAULT_4LAYER_DEPTHS, DEFAULT_4LAYER_CLAY_PCT,
                           DEFAULT_4LAYER_POROSITY, DEFAULT_4LAYER_KSAT,
                           DEFAULT_KSAT_SURFACE, OM_PROFILE_4LAYER,
                           WEATHERED_CEC_4LAYER, WEATHERED_EXCH_CA,
                           WEATHERED_EXCH_MG, WEATHERED_EXCH_K,
                           WEATHERED_EXCH_NA, WEATHERED_EXCH_AL,
                           WEATHERED_EXCH_H, DAYS_IN_MONTH)
from src.climate_forcing import apply_om_pco2
from src.utils import layer_pco2_override
from src.diagnostics import calc_base_saturation, calc_cec_occupied


def _extract_diagnostics(soil_state, diag, variables):
    """从模拟状态提取诊断量 (单层)

    参数:
        soil_state: 模拟后的土壤状态
        diag: 引擎诊断输出
        variables: 配置的输出变量列表 (Q11)
    """
    ex = soil_state.exchange
    # 2026-09-02 (候选2): BS% 与 CEC_occupied 委托 src.diagnostics 单一公式,
    # 消除 main 内联重复实现 (历史口径 include_hx=False, 与引擎物理口径区分)
    base_sat = calc_base_saturation(ex)
    total_charge = calc_cec_occupied(ex)
    diagnostics = {
        'pH': soil_state.ph,
        'base_saturation': base_sat,
        'CEC_occupied': total_charge,
        'exchangeable_Ca': ex.get('CaX2', 0),
        'exchangeable_Al': ex.get('AlX3', 0),
    }
    # Q11: 按配置补充可选字段 (dict 以 JSON 序列化)
    if 'mineral_mass' in variables and diag.mineral_masses:
        diagnostics['mineral_mass'] = json.dumps(diag.mineral_masses)
    if 'solution_ions' in variables and diag.solution_ions:
        diagnostics['solution_ions'] = json.dumps(diag.solution_ions)
    return diagnostics


def _build_initial_layer_states(engine, reader, soil_profile, soil_info,
                                initial_pCO2, simulation_cfg):
    """构建初始状态列表 (L6, v0.4.0: 支持逐层参数覆盖)

    n_layers>1 且配置 layer_overrides 时: 逐层应用覆盖 (部分覆盖回退默认),
    effective_depth 由 layer_depths[i] 派生; 返回逐层 profiles/pCO₂s 供
    月度循环与预平衡使用。否则各层默认参数相同 (ROADMAP 约束, 现状行为)。

    返回:
        (soil_state, soil_states, layer_pco2s, layer_profiles)
        - layer_pco2s/layer_profiles: 有覆盖时逐层列表, 否则 None
    """
    n_layers = getattr(simulation_cfg, 'n_layers', 1)
    layer_depths = getattr(simulation_cfg, 'layer_depths', None)
    layer_overrides = getattr(simulation_cfg, 'layer_overrides', None) or []

    if n_layers > 1 and layer_overrides:
        if layer_depths is None:
            # L6: 有逐层覆盖但未配置 layer_depths → 每层厚度用默认 profile,
            # 输出后缀将走等分兜底 (物理厚度与列名仍可能错位), 提示用户
            logging.getLogger("main").warning(
                "已配置 layer_overrides 但未配置 layer_depths: 各层 "
                "effective_depth 将用默认剖面厚度, 输出列后缀走等分兜底; "
                "建议配置 simulation.layer_depths 使列名与物理厚度一致")
        # L6: 逐层 profile/矿物/pCO2 构建 (密集列表长度已由 config 校验)
        layer_profiles = []
        layer_mineral_infos = []
        layer_pco2s = []
        for i in range(n_layers):
            lo = layer_overrides[i]
            depth = (layer_depths[i] if layer_depths
                     else soil_profile.effective_depth)
            p = reader.apply_layer_override(soil_profile, lo, depth)
            layer_profiles.append(p)
            m = (apply_mineral_overrides(soil_info, lo.minerals)
                 if lo.minerals else soil_info)
            layer_mineral_infos.append(m)
            pco2 = lo.pCO2 if lo.pCO2 is not None else initial_pCO2
            layer_pco2s.append(pco2)
        # v0.5.3 (Q4/Q10): OM 矿化加性调制 pCO₂_eff = base + k_om×OM_i
        # (层内有机质, 表层富集强化表层酸性; 温度独立, 专家★3)
        layer_pco2s = [apply_om_pco2(p, layer_profiles[i].organic_matter)
                       for i, p in enumerate(layer_pco2s)]
        # 工单D (C1, 2026-08-31): 分层 pCO₂ 覆盖 — 深层碳酸缓冲标定
        # (默认 PCO2_4LAYER_OVERRIDE 全 None = 不覆盖 v85 基线; 仅 L4 定案值非默认)
        layer_pco2s = [layer_pco2_override(i, n_layers) or p
                       for i, p in enumerate(layer_pco2s)]
        soil_states = [engine.build_initial_state(
            layer_profiles[i], layer_mineral_infos[i], layer_pco2s[i],
            layer_index=i)
            for i in range(n_layers)]
        return soil_states[0], soil_states, layer_pco2s, layer_profiles

    if n_layers == 4:
        # v0.5.0: n_layers=4 且未配置 layer_overrides → 自动注入内置物理剖面默认
        # (真实红壤剖面: 表层薄/粘粒少/孔隙度大/导水强 → 底层厚/致密/导水弱)
        layer_profiles = []
        layer_mineral_infos = []
        layer_pco2s = []
        for i in range(4):
            # v0.5.0: 内置物理剖面默认 (水文)
            lo_kwargs = dict(
                clay_pct=DEFAULT_4LAYER_CLAY_PCT[i],
                porosity=DEFAULT_4LAYER_POROSITY[i],
                ksat=DEFAULT_4LAYER_KSAT[i],
                ksat_surface=DEFAULT_KSAT_SURFACE,
                organic_matter=OM_PROFILE_4LAYER[i])   # v0.5.3: OM 垂直剖面
            # 工单83 (2026-08-25): 深层风化剖面 CEC/BS 物理化 —
            # L2~L4 CEC 深度衰减 + 盐基淋洗 + 交换 Al 主导 (修复深层交换盐基库
            # 单点外推×层厚放大的物理失真); L1 (i=0) 保持观测 (表层耕层)。
            if i > 0:
                lo_kwargs.update(
                    cec=WEATHERED_CEC_4LAYER[i],
                    exch_ca=WEATHERED_EXCH_CA[i],
                    exch_mg=WEATHERED_EXCH_MG[i],
                    exch_k=WEATHERED_EXCH_K[i],
                    exch_na=WEATHERED_EXCH_NA[i],
                    exch_al=WEATHERED_EXCH_AL[i],
                    exch_h=WEATHERED_EXCH_H[i])
            lo = LayerOverrideConfig(**lo_kwargs)
            depth = DEFAULT_4LAYER_DEPTHS[i]
            p = reader.apply_layer_override(soil_profile, lo, depth)
            layer_profiles.append(p)
            layer_mineral_infos.append(soil_info)
            layer_pco2s.append(initial_pCO2)
        # v0.5.3 (Q4/Q10): OM 矿化加性调制 (表层富集 → pCO₂_eff 梯度)
        layer_pco2s = [apply_om_pco2(p, layer_profiles[i].organic_matter)
                       for i, p in enumerate(layer_pco2s)]
        # 工单D (C1, 2026-08-31): 分层 pCO₂ 覆盖 — 深层碳酸缓冲标定
        # (默认 PCO2_4LAYER_OVERRIDE 全 None = 不覆盖 v85 基线; 仅 L4 定案值非默认)
        layer_pco2s = [layer_pco2_override(i, 4) or p
                       for i, p in enumerate(layer_pco2s)]
        soil_states = [engine.build_initial_state(
            layer_profiles[i], layer_mineral_infos[i], layer_pco2s[i],
            layer_index=i)
            for i in range(4)]
        return soil_states[0], soil_states, layer_pco2s, layer_profiles

    # 各层默认参数相同 (现状行为, WF2/Q1)
    soil_states = [engine.build_initial_state(
        soil_profile, soil_info, initial_pCO2) for _ in range(n_layers)]
    return soil_states[0], soil_states, None, None


def _baseflow_dict(baseflow_cfg):
    """v0.6.1: BaseflowConfig → LayerCascade dict (None=禁用)"""
    if baseflow_cfg is None:
        return None
    return {k: v for k, v in {
        'D_max': baseflow_cfg.D_max,
        'D_s': baseflow_cfg.D_s,
        'n_base': baseflow_cfg.n_base,
    }.items() if v is not None}


def _lateral_dict(lateral_cfg):
    """v0.6.1: LateralConfig → LayerCascade dict (None=禁用)"""
    if lateral_cfg is None:
        return None
    return {k: v for k, v in {
        'f_slope': lateral_cfg.f_slope,
        'k_lat': lateral_cfg.k_lat,
    }.items() if v is not None}


def _apply_hydrology_month(soil_states, layer_profiles, forcing,
                           year, month, seed=42,
                           bypass_fraction=0.2,
                           baseflow_cfg=None, lateral_cfg=None):
    """v0.5.3: 月度水文 (ET → 入渗 → 级联, 时序 v0.5.3水分平衡闭合.txt §4.3)

    就地更新各层 theta (跨月滞水); 返回引擎需要的各层入渗/排水量。
    v0.5.3 (spec 49):
      ① ET 扣除最前端 (Feddes, 逐层独立, 亏缺丢弃计 et_deficit_mm, Q3/Q9)
      ② Green-Ampt 入渗 (θ_i = L1 当前 θ, 已含 ET 扣除; 删除 50% 饱和魔法数)
      ③ 层间级联 (θ_FC 可排水量 + K(θ) 界面通量, D3/Q2/Q11)
    v0.5.2: 大孔隙优先流 bypass_fraction (径流水 β 绕过表层直通 L2)。

    参数:
        bypass_fraction: 大孔隙优先流比例 (0~1, 超基质 Ks 积水直通 L2)

    返回:
        (hydrology_dict, runoff_mm, runoff_extra_L)
        - hydrology_dict: {'inflows': [L/ha 各层注入水量], 'drains': [L/ha 各层排水],
                           'bypass_water_L': 优先流水量 (L/ha, 注入 L2),
                           'aet_mm': 本月实际蒸散总量 (mm),
                           'et_deficit_mm': ET 亏缺总量 (mm)}
        - runoff_mm: 超渗径流 (mm, = 月降水 − 月入渗)
        - runoff_extra_L: 超饱和溢出 (L/ha, 积水/侧排)
    """
    from src.hydrology import (monthly_hydrology, LayerCascade,
                               apply_feddes_et)
    # ① ET 扣除 (最前端, 腾出孔隙空间; α=0 钳制 θ 不取负)
    pet_mm = forcing.get('pet', 0.0)
    aet_mm_list, et_deficit_mm = apply_feddes_et(
        soil_states, pet_mm, layer_profiles)
    # ② Green-Ampt 入渗 (θ_i = L1 当前 θ, v0.5.3 精确换算, 删除 50% 魔法数)
    inf_mm, runoff_mm, _ = monthly_hydrology(
        forcing.get('precip', 0.0), year, month, layer_profiles[0], seed,
        theta_i=soil_states[0].theta)
    inf_L = inf_mm * 10000.0
    # ③ 层间级联 (θ_FC 可排水量 + K(θ) 界面通量, D3/Q2/Q11)
    # v0.6.1: 基流/侧向出口 (spec 62 Q1/Q2/Q4), 配置为 None 时行为与旧版一致
    cascade = LayerCascade(layer_profiles, baseflow_cfg=baseflow_cfg,
                           lateral_cfg=lateral_cfg)
    drains, runoff_extra, baseflow, lateral, theta_out = \
        cascade.run_extended(inf_L, soil_states)
    inflows = [inf_L] + drains[:-1]  # 层1=入渗, 下层=上层排水
    # v0.5.2: 大孔隙优先流 — 径流水中 β 绕过表层直通 L2 (携带原始降水化学)
    bypass_water_L = runoff_mm * 10000.0 * bypass_fraction
    return {'inflows': inflows, 'drains': drains,
            'baseflow': baseflow, 'lateral': lateral,
            'bypass_water_L': bypass_water_L,
            'aet_mm': sum(aet_mm_list),
            'et_deficit_mm': et_deficit_mm}, runoff_mm, runoff_extra


def _apply_hydrology_events(soil_states, layer_profiles, forcing, year, month,
                            seed=42, bypass_fraction=0.2,
                            baseflow_cfg=None, lateral_cfg=None):
    """v0.6.0 事件级水文编排 (Q3/Q15, spec 55 §4)

    月首 ET 一次 (Feddes, 与月级一致) → 逐场:
      ① Green-Ampt 单场入渗 (θ_i = L1 当前 θ, 逐场更新)
      ② 层间级联 (LayerCascade, 排水窗 = 月天数/场次数)
      ③ bypass = 该场径流×β (逐场注入 L2)
    返回:
        (hydrology_dict, runoff_mm, runoff_extra_L)
        - hydrology_dict: 含 'events' 键 (每场 inflows/drains/bypass_water_L/
          precip_mm) + 月聚合键 (inflows/drains/bypass_water_L/aet_mm/
          et_deficit_mm, 供诊断列)
        - runoff_mm: 月超渗径流 (mm = 月降水 − Σ 单场入渗)
        - runoff_extra_L: 月超饱和溢出总量 (L/ha)

    LayerCascade 排水窗: 月级 n_days=30 (整月排水能力); 事件级每场
    n_days=月天数/场次数 → Σ排水窗 = 月天数 → 月排水总量与月级一致
    (子步长不改变水分平衡, E1 复验门禁)。
    """
    from src.hydrology import (generate_events, green_ampt_infiltration,
                               LayerCascade, apply_feddes_et)
    # ① ET 扣除 (月首一次, 与月级 _apply_hydrology_month 一致)
    pet_mm = forcing.get('pet', 0.0)
    aet_mm_list, et_deficit_mm = apply_feddes_et(
        soil_states, pet_mm, layer_profiles)
    # ② 逐场: Green-Ampt → 级联 → bypass
    events = generate_events(forcing.get('precip', 0.0), year, month, seed)
    n_ev = max(len(events), 1)
    interval_days = DAYS_IN_MONTH[month] / n_ev
    cascade = LayerCascade(layer_profiles, n_days=interval_days,
                           baseflow_cfg=baseflow_cfg, lateral_cfg=lateral_cfg)
    n = len(layer_profiles)
    ev_entries = []
    month_inflows = [0.0] * n
    month_drains = [0.0] * n
    month_baseflow = [0.0] * n
    month_lateral = [0.0] * n
    month_bypass = 0.0
    total_inf_mm = 0.0
    total_runoff_extra = 0.0
    for ev in events:
        inf_mm, runoff_mm = green_ampt_infiltration(
            ev.precip_mm, layer_profiles[0].ksat_surface,
            theta_s=layer_profiles[0].porosity,
            theta_i=soil_states[0].theta)
        inf_L = inf_mm * 10000.0
        drains, runoff_extra, baseflow, lateral, theta_out = \
            cascade.run_extended(inf_L, soil_states)
        inflows = [inf_L] + drains[:-1]
        bypass_water_L = runoff_mm * 10000.0 * bypass_fraction
        # v0.6.0: 记录每场事件后各层 θ (引擎逐场 rescale 用, 避免用月末 θ
        # 一次性浓缩 — 事件化水文/化学精确耦合)
        # v0.6.1: 逐场记录 baseflow/lateral 出口 (Q2: 事件粒度水量出口)
        ev_entries.append({'inflows': inflows, 'drains': drains,
                           'baseflow': baseflow, 'lateral': lateral,
                           'bypass_water_L': bypass_water_L,
                           'precip_mm': ev.precip_mm,
                           'theta': theta_out})
        total_inf_mm += inf_mm
        total_runoff_extra += runoff_extra
        for i in range(n):
            month_inflows[i] += inflows[i]
            month_drains[i] += drains[i]
            month_baseflow[i] += baseflow[i]
            month_lateral[i] += lateral[i]
        month_bypass += bypass_water_L
    runoff_mm = forcing.get('precip', 0.0) - total_inf_mm
    hydrology = {'events': ev_entries,
                 'inflows': month_inflows, 'drains': month_drains,
                 'baseflow': month_baseflow, 'lateral': month_lateral,
                 'bypass_water_L': month_bypass,
                 'aet_mm': sum(aet_mm_list),
                 'et_deficit_mm': et_deficit_mm}
    return hydrology, runoff_mm, total_runoff_extra


def _extract_diagnostics_with_hydrology(soil_states, hydrology, runoff_mm,
                                        runoff_extra, diag_objs, variables,
                                        layer_profiles, layer_pco2s=None):
    """v0.5.0: 提取层诊断并附加水文列 (infiltration/drainage/stored_water/runoff)

    水文列值:
      - infiltration: 该层本月注入水量 (L/ha; 层1=入渗, 下层=上层排水)
      - drainage:     该层排水量 (L/ha, Ksat 限制后)
      - stored_water: 该层跨月滞水 (L/ha, v0.5.3: 由 θ 状态经 vgm 换算, 语义不变)
      - runoff:       表层径流合计 (mm×10000 + 超饱和溢出, L/ha)
      - bypass_drainage: v0.5.2 大孔隙优先流水量 (L/ha, 注入 L2, 可选诊断列)
      - soil_moisture: v0.5.3 本层体积含水量 θ (m³/m³, 逐层)
      - pCO2_eff:     v0.5.3 本层有效 pCO₂ (atm, 含 OM 加性调制, Q4)
    AET_mm / et_deficit_mm 为月度全局列 (由主循环经 global_diagnostics 输出)。
    """
    from src.vgm import theta_to_water_L
    layer_diags = [_extract_diagnostics(s, d, variables)
                   for s, d in zip(soil_states, diag_objs)]
    n = len(soil_states)
    for i in range(n):
        inflow = (hydrology['inflows'][i] if i == 0
                  else hydrology['drains'][i - 1])
        layer_diags[i]['infiltration'] = inflow
        layer_diags[i]['drainage'] = hydrology['drains'][i]
        # v0.5.3: stored_water 列向后兼容 (L/ha, 由 θ×depth×1e5 换算, 专家★5)
        layer_diags[i]['stored_water'] = theta_to_water_L(
            soil_states[i].theta, layer_profiles[i].effective_depth)
        # v0.5.3: 逐层土壤含水量 + 有效 pCO₂ (含 OM 加性调制)
        layer_diags[i]['soil_moisture'] = soil_states[i].theta
        if layer_pco2s is not None:
            layer_diags[i]['pCO2_eff'] = layer_pco2s[i]
        else:
            layer_diags[i]['pCO2_eff'] = soil_states[i].gas_phase.get(
                'CO2(g)', 0.0)
    layer_diags[0]['runoff'] = runoff_mm * 10000.0 + runoff_extra
    # v0.5.2: 大孔隙优先流 (绕过表层直通 L2) 诊断列, 可选输出
    if n > 1 and hydrology.get('bypass_water_L', 0.0) > 0:
        layer_diags[1]['bypass_drainage'] = hydrology['bypass_water_L']
    # v0.6.1 (spec 62 Q3/Q6): 基流/侧向出口诊断列 (逐层, L/ha; 非事件/未配置
    # 时恒 0, 列保持存在) — 侧向/基流溶质移出系统 (质量守恒记账)
    for i in range(n):
        layer_diags[i]['baseflow'] = hydrology.get('baseflow', [0.0] * n)[i]
        layer_diags[i]['lateral'] = hydrology.get('lateral', [0.0] * n)[i]
        # v0.7.0 (工单70): NO3- 示踪池月度存量 (mol, 月末状态)
        layer_diags[i]['n_no3_pool'] = soil_states[i].n_no3_pool
        # v0.7.0 (工单72): NH4+ 假设占用的交换位点 (eq, NH4X_virtual 记账,
        # 不进 EXCHANGE 总量 — CEC 守恒审计不破, 预平衡锚定不受扰)
        layer_diags[i]['NH4X_virtual'] = soil_states[i].n_nh4
    # v0.7.0 (工单70): NO3- 淋失月度聚合 (mol; 事件级 Σ, 非事件路径恒 0 保列)
    ev_details = (hydrology or {}).get('event_details', [])
    for i in range(n):
        layer_diags[i]['leach_no3_mol'] = sum(
            row.get(f'leach_no3_L{i+1}_mol', 0.0) for row in ev_details)
    # v0.7.x (工单80): 盐基淋失月度聚合 (eq; 事件级 Σ, 非事件路径恒 0 保列)
    for i in range(n):
        layer_diags[i]['base_loss_eq'] = sum(
            row.get(f'base_loss_eq_L{i+1}', 0.0) for row in ev_details)
        layer_diags[i]['e_base_anion_eq'] = sum(
            row.get(f'e_base_anion_eq_L{i+1}', 0.0) for row in ev_details)
    # v0.6.0 (Q14): First-Flush 峰值列 (L1 当月最大单场淋失, mmol/ha;
    # 非事件驱动路径恒 0, 列保持存在)
    if diag_objs and diag_objs[0] is not None:
        layer_diags[0]['flush_NO3_peak_mmol'] = \
            diag_objs[0].flush_no3_peak_mmol
        layer_diags[0]['flush_base_peak_mmol'] = \
            diag_objs[0].flush_base_peak_mmol
    return layer_diags


def run_simulation(config_path: str = "config/config.yaml"):
    """运行模拟主函数"""

    # ============================================================
    # 阶段 1: 配置加载
    # ============================================================
    print("\n" + "=" * 60)
    print("Soil-SCM: 土壤物理化学数值模式")
    print("=" * 60)

    cfg_mgr = ConfigManager(config_path)
    cfg = cfg_mgr.config
    # Q15: 初始化日志 (console + output/soil_scm.log)
    setup_logging(cfg.output.directory)
    cfg_mgr.print_summary()

    # ============================================================
    # 阶段 2: 加载矿物数据库
    # ============================================================
    soil_db = SoilDatabase(
        json_path="config/soil_mineral_db.json",
        tbl_path="config/soil_mineral.tbl"
    )
    soil_type = cfg.soil_data.soil_type
    soil_info = soil_db.get_soil_info(soil_type)
    soil_db.print_soil_info(soil_type)

    # ============================================================
    # 阶段 3: 读取土壤普查数据
    # ============================================================
    reader = InputReader(
        soil_file=cfg.soil_data.input_file,
        exchangeable_file=cfg.soil_data.exchangeable_ions_file
    )
    # v0.2.3: 传递 config 内联字段 (全 -1 时自动回退 CSV)
    soil_profile = reader.build_soil_profile(
        survey_config=vars(cfg.soil_data.survey),
        exchangeable_config=vars(cfg.soil_data.exchangeable_ions)
    )

    print(f"\n土壤剖面数据:")
    print(f"  pH: {soil_profile.ph}")
    print(f"  CEC: {soil_profile.cec} cmol(+)/kg")
    print(f"  盐基饱和度: {soil_profile.base_saturation:.1f}%")
    print(f"  有机质: {soil_profile.organic_matter} g/kg")
    print(f"  土层厚度: {soil_profile.effective_depth} cm")

    # ============================================================
    # 阶段 4: 构建初始条件 (InitialConditionBuilder)
    # ============================================================
    initial_pCO2 = soil_db.get_pCO2(soil_type)
    ic_builder = InitialConditionBuilder(
        soil_profile=soil_profile,
        mineral_db_info=soil_info,
        pCO2=initial_pCO2
    )
    ic_builder.print_summary()
    ic_builder.validate()

    # T5-Q8 修复: 不再单独生成/打印初始输入串 (仅打印不用, 与引擎路径割裂)。
    # 引擎实际初始状态由阶段 7 build_initial_state() 复用 InitialConditionBuilder 生成。
    # SURFACE 默认关闭: phreeqc.dat 仅定义 Hfo_s/Hfo_w 表面物种, 文档代码生成的
    # Som/Hfo 位点与该数据库不兼容 (见 docs/analysis/OPTIMIZATION_PLAN.md P3)。

    # ============================================================
    # 阶段 5: 生成气候强迫
    # ============================================================
    climate = ClimateForcing(
        base_annual_precip=cfg.climate.base_annual_precip,
        base_annual_temp=cfg.climate.base_annual_temp,
        pCO2_ref=cfg.soil_co2.pCO2_ref,
        T_ref=cfg.soil_co2.T_ref,
        beta=cfg.soil_co2.beta,
        n_years=cfg.simulation.n_years,
        scenario=cfg.simulation.scenario,
        precip_increase_rate=cfg.climate.precip_increase_rate,
        temp_increase_rate=cfg.climate.temp_increase_rate,
        # v0.5.3: PET 通道 (D5) — Oudin 为主 + fixed 气候态兜底
        latitude=getattr(cfg.climate, 'latitude', 23.1),
        pet_method=getattr(cfg.climate, 'pet_method', 'oudin'),
        pet_monthly_climate=getattr(cfg.climate, 'pet_monthly_climate', None),
        pet_correction_factor=getattr(cfg.climate, 'pet_correction_factor',
                                      None),
    )
    climate.print_summary()

    # ============================================================
    # 阶段 6: 初始化情景控制器
    # ============================================================
    scenario_ctrl = ScenarioController(
        scenario=cfg.simulation.scenario,
        fertilizer_config={
            'n': cfg.fertilizer.n,
            'p2o5': cfg.fertilizer.p2o5,
            'k2o': cfg.fertilizer.k2o,
            'mgo': cfg.fertilizer.mgo,
            'znso4': cfg.fertilizer.znso4,
            'apply_months': cfg.fertilizer.apply_months,
        },
        lime_config={
            'amount_per_apply': cfg.lime.amount_per_apply,
            'apply_months': cfg.lime.apply_months,
        }
    )
    scenario_ctrl.print_scenario_info()

    # ============================================================
    # 阶段 7: 初始化 PHREEQC 引擎
    # ============================================================
    # Q7: 加载降水化学 (默认华南数据, 见 config/precip_chemistry_default.json)
    from src.precip_chemistry import PrecipChemistry
    precip_chem = (PrecipChemistry(data=cfg.precip_chemistry.data)
                   if cfg.precip_chemistry.data else None)
    if precip_chem is not None:
        precip_chem.print_summary()

    engine = PhreeqcEngine(database='phreeqc.dat',
                           mode=cfg.simulation.engine_mode,
                           precip_chem=precip_chem,
                           precip_infiltration=cfg.simulation.precip_infiltration,
                           enable_surface=getattr(cfg.simulation, 'enable_surface', False),
                           nitrification_k1=getattr(cfg.simulation, 'nitrification_k1', 1.0),
                           nitrification_k2=getattr(cfg.simulation, 'nitrification_k2', 0.4),
                           initial_psi_cm=getattr(cfg.simulation, 'initial_psi_cm', -100.0),
                           companion_cfg=getattr(cfg.simulation, 'companion', None),
                           weathering_cfg=getattr(cfg.simulation, 'weathering', None),
                           charge_pairing_cfg=getattr(cfg.simulation,
                                                      'charge_pairing', None),
                           base_leaching_cfg=getattr(cfg.simulation,
                                                     'base_leaching', None))

    # 构建初始状态 (initial_pCO2 已在阶段 4 中计算)
    # WF2/Q1: 多分层时构建 List[SoilState]; L6 (v0.4.0): 支持逐层参数覆盖
    n_layers = getattr(cfg.simulation, 'n_layers', 1)
    layer_depths = getattr(cfg.simulation, 'layer_depths', None)
    layer_overrides = getattr(cfg.simulation, 'layer_overrides', None) or []
    soil_state, soil_states, layer_pco2s, layer_profiles = \
        _build_initial_layer_states(
            engine, reader, soil_profile, soil_info, initial_pCO2,
            cfg.simulation)

    # v0.5.0: 初始状态预平衡 (热力学自洽, 默认开启, L9 落地)
    # 无干预多步平衡让溶液/交换/矿物三相重新分配至稳态, 避免首次平衡
    # 剧烈重分配 (矿物量大时交换 Al 被矿物相吸收 → fertilizer 长期耗尽)
    # L6 (v0.4.0): 逐层覆盖时每层独立预平衡 (各层 profile 作观测锚定)
    if getattr(cfg.simulation, 'enable_pre_equilibration', True):
        pre_steps = getattr(cfg.simulation, 'pre_equilibration_max_steps', 60)
        if layer_profiles is not None:
            soil_state = engine.pre_equilibrate(
                soil_state, layer_profiles[0], pre_steps)
            soil_states = [engine.pre_equilibrate(
                s, layer_profiles[i], pre_steps)
                for i, s in enumerate(soil_states)]
        else:
            soil_state = engine.pre_equilibrate(
                soil_state, soil_profile, pre_steps)
            soil_states = [engine.pre_equilibrate(s, soil_profile, pre_steps)
                           for s in soil_states]

    print(f"\n初始状态:")
    if n_layers > 1:
        print(f"  分层数: {n_layers} (各层默认参数相同)")
        print(f"  顶层 pH: {soil_states[0].ph}")
    else:
        print(f"  pH: {soil_state.ph}")
    print(f"  pCO2: {initial_pCO2} atm")
    print(f"  矿物相数量: {len(soil_state.minerals)}")

    # ============================================================
    # 阶段 8: 时间积分主循环
    # ============================================================
    print(f"\n{'='*60}")
    print(f"开始时间积分: {cfg.simulation.n_years} 年 × 12 月")
    print(f"{'='*60}")

    # 初始化输出器
    # WF2/Q6: 多分层时列名加层深度后缀 (单层列名不变)
    layer_depths = getattr(cfg.simulation, 'layer_depths', None)
    output_writer = OutputWriter(
        output_dir=cfg.output.directory,
        output_format=cfg.output.format,
        scenario=cfg.simulation.scenario,
        variables=cfg.output.variables,  # Q11: 按配置输出变量
        n_layers=n_layers,
        layer_depths=layer_depths
    )

    n_years = cfg.simulation.n_years
    sub_steps = cfg.simulation.sub_time_step_days

    for year in range(n_years):
        for month in range(12):
            # 获取当月气候强迫
            forcing = climate.get_monthly_forcing(year, month)

            # 获取当月操作指令
            action = scenario_ctrl.get_action(year + 1, month + 1)

            # 执行化学计算
            if n_layers > 1:
                # v0.5.0: 水文模式 (4 层内置默认或 layer_overrides 含水文)
                # v0.5.3: f0/fc 已移除, 水文字段触发 = ksat>0 (层间排水物理)
                hydrology_enabled = (
                    layer_profiles is not None
                    and getattr(layer_profiles[0], 'ksat', 0.0) > 0.0)
                global_diag = None
                if hydrology_enabled:
                    # v0.5.2: 水文模型 (Green-Ampt 入渗 + 级联), 替代
                    # precip_infiltration; 子时间步不适用 (水文为月度盒子)
                    # v0.5.3: theta_i = L1 当前 θ (由 _apply_hydrology_month 内部
                    # 从 states[0].theta 精确读取, 删除 50% 饱和简化)
                    # v0.6.0: event_driven 用事件级水文编排 (逐场 Green-Ampt+
                    # 级联+bypass, Q3/Q15), 否则月级编排 (护栏)
                    if cfg.simulation.event_driven:
                        hydrology, runoff_mm, runoff_extra = _apply_hydrology_events(
                            soil_states, layer_profiles, forcing, year, month,
                            cfg.simulation.hydrology_seed,
                            bypass_fraction=cfg.simulation.bypass_fraction,
                            baseflow_cfg=_baseflow_dict(cfg.simulation.baseflow),
                            lateral_cfg=_lateral_dict(cfg.simulation.lateral))
                    else:
                        hydrology, runoff_mm, runoff_extra = _apply_hydrology_month(
                            soil_states, layer_profiles, forcing, year, month,
                            cfg.simulation.hydrology_seed,
                            bypass_fraction=cfg.simulation.bypass_fraction,
                            baseflow_cfg=_baseflow_dict(cfg.simulation.baseflow),
                            lateral_cfg=_lateral_dict(cfg.simulation.lateral))
                    soil_states, diags = engine.run_monthly_multi_layer(
                        soil_states, forcing, action, soil_profile,
                        layer_pco2s=layer_pco2s, hydrology=hydrology)
                    # WF2/Q6 + v0.5.0: 逐层诊断 + 水文列 + 层后缀输出
                    layer_diagnostics = _extract_diagnostics_with_hydrology(
                        soil_states, hydrology, runoff_mm, runoff_extra,
                        diags, cfg.output.variables, layer_profiles,
                        layer_pco2s=layer_pco2s)
                    # v0.5.3: 月度全局聚合列 (ET 收支, 无层后缀; 列名与 config
                    # output.variables 一致)
                    global_diag = {'AET_mm': hydrology['aet_mm'],
                                   'et_deficit_mm': hydrology['et_deficit_mm']}
                    # v0.6.0 (Q14): 逐场事件明细 CSV (event_output=true 时)
                    if cfg.output.event_output and hydrology.get('event_details'):
                        for det in hydrology['event_details']:
                            det_out = dict(det)
                            det_out['year'] = det_out.get('year', 0) + 1
                            det_out['month'] = det_out.get('month', 0) + 1
                            output_writer.record_event(det_out)
                else:
                    # WF2/Q4: 多分层 — 高层编排层 (层循环 + 级联平流)
                    if sub_steps > 0:
                        n_sub = int(30 / sub_steps)
                        for sub in range(n_sub):
                            sub_forcing = forcing.copy()
                            sub_forcing['precip'] = forcing['precip'] / n_sub
                            soil_states, diags = engine.run_monthly_multi_layer(
                                soil_states, sub_forcing, action, soil_profile,
                                layer_pco2s=layer_pco2s)
                    else:
                        soil_states, diags = engine.run_monthly_multi_layer(
                            soil_states, forcing, action, soil_profile,
                            layer_pco2s=layer_pco2s)
                    # WF2/Q6: 逐层诊断 + 层后缀输出
                    layer_diagnostics = [
                        _extract_diagnostics(s, d, cfg.output.variables)
                        for s, d in zip(soil_states, diags)]
                output_writer.record_multi_step(
                    year + 1, month + 1, layer_diagnostics,
                    global_diagnostics=global_diag)
            else:
                # 单层路径 (回归护栏: 走原接口)
                if sub_steps > 0:
                    # 子时间步模式
                    n_sub = int(30 / sub_steps)
                    for sub in range(n_sub):
                        sub_forcing = forcing.copy()
                        sub_forcing['precip'] = forcing['precip'] / n_sub
                        soil_state, diag = engine.run_monthly_step(
                            soil_state, sub_forcing, action, soil_profile)
                else:
                    # 月步长模式
                    if cfg.simulation.event_driven:
                        # v0.6.0: 单层事件驱动 (run_monthly_step 内部事件化)
                        ev_forcing = dict(forcing, event_driven=True,
                                          year=year, month=month,
                                          seed=cfg.simulation.hydrology_seed)
                        soil_state, diag = engine.run_monthly_step(
                            soil_state, ev_forcing, action, soil_profile)
                    else:
                        soil_state, diag = engine.run_monthly_step(
                            soil_state, forcing, action, soil_profile)

                # 记录诊断量 (从模拟状态提取, 反映化学演化)
                diagnostics = _extract_diagnostics(
                    soil_state, diag, cfg.output.variables)
                output_writer.record_step(year + 1, month + 1, diagnostics)

        # 每年打印进度
        if (year + 1) % 10 == 0 or year == 0:
            if n_layers > 1:
                print(f"  第 {year+1:3d} 年完成 | 顶层 pH = {soil_states[0].ph:.3f}")
            else:
                print(f"  第 {year+1:3d} 年完成 | pH = {soil_state.ph:.3f}")

    # ============================================================
    # 阶段 9: 输出结果
    # ============================================================
    print(f"\n{'='*60}")
    print("模拟完成，正在保存结果...")
    print(f"{'='*60}")

    output_writer.save()
    output_writer.plot_results()

    print("\n[SUCCESS] Soil-SCM 模拟完成!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Soil-SCM 土壤物理化学数值模式')
    parser.add_argument('--config', type=str, default='config/config.yaml',
                        help='配置文件路径')
    args = parser.parse_args()

    run_simulation(args.config)

