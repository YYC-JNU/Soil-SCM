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
                           DEFAULT_4LAYER_F0, DEFAULT_4LAYER_FC,
                           DEFAULT_KSAT_SURFACE)


def _extract_diagnostics(soil_state, diag, variables):
    """从模拟状态提取诊断量 (单层)

    参数:
        soil_state: 模拟后的土壤状态
        diag: 引擎诊断输出
        variables: 配置的输出变量列表 (Q11)
    """
    ex = soil_state.exchange
    base_charge = (ex.get('CaX2', 0) * 2.0 + ex.get('MgX2', 0) * 2.0 +
                   ex.get('KX', 0) + ex.get('NaX', 0))
    total_charge = base_charge + ex.get('AlX3', 0) * 3.0
    base_sat = (base_charge / total_charge * 100.0
                if total_charge > 0 else 0.0)
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
        soil_states = [engine.build_initial_state(
            layer_profiles[i], layer_mineral_infos[i], layer_pco2s[i])
            for i in range(n_layers)]
        return soil_states[0], soil_states, layer_pco2s, layer_profiles

    if n_layers == 4:
        # v0.5.0: n_layers=4 且未配置 layer_overrides → 自动注入内置物理剖面默认
        # (真实红壤剖面: 表层薄/粘粒少/孔隙度大/导水强 → 底层厚/致密/导水弱)
        layer_profiles = []
        layer_mineral_infos = []
        layer_pco2s = []
        for i in range(4):
            lo = LayerOverrideConfig(
                clay_pct=DEFAULT_4LAYER_CLAY_PCT[i],
                porosity=DEFAULT_4LAYER_POROSITY[i],
                ksat=DEFAULT_4LAYER_KSAT[i],
                ksat_surface=DEFAULT_KSAT_SURFACE,
                infiltration_initial=DEFAULT_4LAYER_F0[i],
                infiltration_steady=DEFAULT_4LAYER_FC[i])
            depth = DEFAULT_4LAYER_DEPTHS[i]
            p = reader.apply_layer_override(soil_profile, lo, depth)
            layer_profiles.append(p)
            layer_mineral_infos.append(soil_info)
            layer_pco2s.append(initial_pCO2)
        soil_states = [engine.build_initial_state(
            layer_profiles[i], layer_mineral_infos[i], layer_pco2s[i])
            for i in range(4)]
        return soil_states[0], soil_states, layer_pco2s, layer_profiles

    # 各层默认参数相同 (现状行为, WF2/Q1)
    soil_states = [engine.build_initial_state(
        soil_profile, soil_info, initial_pCO2) for _ in range(n_layers)]
    return soil_states[0], soil_states, None, None


def _apply_hydrology_month(soil_states, layer_profiles, forcing,
                           year, month, seed=42, theta_i=None,
                           bypass_fraction=0.2):
    """v0.5.2: 月度水文 (随机降雨 + Green-Ampt 入渗 + 层间级联)

    就地更新各层 stored_water (跨月滞水); 返回引擎需要的各层入渗/排水量。
    v0.5.2: 入渗用 Green-Ampt (ksat_surface 基质导水率), 移除 surface_coeff;
    大孔隙优先流 bypass_fraction (径流水 β 绕过表层直通 L2)。

    参数:
        theta_i: 表层初始体积含水量 (None → 0.5×θ_s; v0.5.2 由调用方传入,
                 来自 L1 stored_water 换算的简化近似)
        bypass_fraction: 大孔隙优先流比例 (0~1, 超基质 Ks 积水直通 L2)

    返回:
        (hydrology_dict, runoff_mm, runoff_extra_L)
        - hydrology_dict: {'inflows': [L/ha 各层注入水量], 'drains': [L/ha 各层排水],
                           'bypass_water_L': 优先流水量 (L/ha, 注入 L2)}
        - runoff_mm: 超渗径流 (mm, = 月降水 − 月入渗)
        - runoff_extra_L: 超饱和溢出 (L/ha, 积水/侧排)
    """
    from src.hydrology import monthly_hydrology, LayerCascade
    inf_mm, runoff_mm, _ = monthly_hydrology(
        forcing.get('precip', 0.0), year, month, layer_profiles[0], seed,
        theta_i=theta_i)
    inf_L = inf_mm * 10000.0
    cascade = LayerCascade(layer_profiles)
    drains, runoff_extra, _ = cascade.run(inf_L, soil_states)
    inflows = [inf_L] + drains[:-1]  # 层1=入渗, 下层=上层排水
    # v0.5.2: 大孔隙优先流 — 径流水中 β 绕过表层直通 L2 (携带原始降水化学)
    bypass_water_L = runoff_mm * 10000.0 * bypass_fraction
    return {'inflows': inflows, 'drains': drains,
            'bypass_water_L': bypass_water_L}, runoff_mm, runoff_extra


def _extract_diagnostics_with_hydrology(soil_states, hydrology, runoff_mm,
                                        runoff_extra, diag_objs, variables,
                                        layer_profiles):
    """v0.5.0: 提取层诊断并附加水文列 (infiltration/drainage/stored_water/runoff)

    水文列值:
      - infiltration: 该层本月注入水量 (L/ha; 层1=入渗, 下层=上层排水)
      - drainage:     该层排水量 (L/ha, Ksat 限制后)
      - stored_water: 该层跨月滞水 (L/ha, v0.5.3: 由 θ 状态经 vgm 换算, 语义不变)
      - runoff:       表层径流合计 (mm×10000 + 超饱和溢出, L/ha)
      - bypass_drainage: v0.5.2 大孔隙优先流水量 (L/ha, 注入 L2, 可选诊断列)
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
    layer_diags[0]['runoff'] = runoff_mm * 10000.0 + runoff_extra
    # v0.5.2: 大孔隙优先流 (绕过表层直通 L2) 诊断列, 可选输出
    if n > 1 and hydrology.get('bypass_water_L', 0.0) > 0:
        layer_diags[1]['bypass_drainage'] = hydrology['bypass_water_L']
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
                           initial_psi_cm=getattr(cfg.simulation, 'initial_psi_cm', -100.0))

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
                hydrology_enabled = (
                    layer_profiles is not None
                    and getattr(layer_profiles[0], 'infiltration_initial', 0.0) > 0.0)
                if hydrology_enabled:
                    # v0.5.2: 水文模型 (Green-Ampt 入渗 + 级联), 替代
                    # precip_infiltration; 子时间步不适用 (水文为月度盒子)
                    # theta_i: L1 初始含水量近似 (v0.5.2 保留 50% 饱和简化;
                    # v0.5.3 迁移 θ 状态后由 stored_water 精确换算)
                    theta_s = layer_profiles[0].porosity
                    theta_i = 0.5 * theta_s
                    hydrology, runoff_mm, runoff_extra = _apply_hydrology_month(
                        soil_states, layer_profiles, forcing, year, month,
                        cfg.simulation.hydrology_seed, theta_i=theta_i,
                        bypass_fraction=cfg.simulation.bypass_fraction)
                    soil_states, diags = engine.run_monthly_multi_layer(
                        soil_states, forcing, action, soil_profile,
                        layer_pco2s=layer_pco2s, hydrology=hydrology)
                    # WF2/Q6 + v0.5.0: 逐层诊断 + 水文列 + 层后缀输出
                    layer_diagnostics = _extract_diagnostics_with_hydrology(
                        soil_states, hydrology, runoff_mm, runoff_extra,
                        diags, cfg.output.variables, layer_profiles)
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
                    year + 1, month + 1, layer_diagnostics)
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

