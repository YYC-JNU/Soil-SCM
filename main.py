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
import numpy as np
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.config_manager import ConfigManager
from src.soil_database import SoilDatabase
from src.input_reader import InputReader
from src.climate_forcing import ClimateForcing
from src.scenario_controller import ScenarioController
from src.phreeqc_engine import PhreeqcEngine
from src.output_writer import OutputWriter
from src.initial_condition import InitialConditionBuilder
from src.logging_config import setup_logging


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
    soil_profile = reader.build_soil_profile()

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

    # 生成 PHREEQC 初始输入字符串
    # 注意: 默认关闭 SURFACE 块(include_surface=False)——
    # phreeqc.dat 仅定义 Hfo_s/Hfo_w 表面物种, 文档代码生成的
    # Som/Hfo 位点与该数据库不兼容 (见 docs/OPTIMIZATION_PLAN.md P3)
    phreeqc_initial_input = ic_builder.build_phreeqc_input(
        include_surface=False
    )
    print("\nPHREEQC 初始输入:")
    print(phreeqc_initial_input)

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
                           precip_chem=precip_chem)

    # 构建初始状态 (initial_pCO2 已在阶段 4 中计算)
    soil_state = engine.build_initial_state(
        soil_profile, soil_info, initial_pCO2)

    print(f"\n初始状态:")
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
    output_writer = OutputWriter(
        output_dir=cfg.output.directory,
        output_format=cfg.output.format,
        scenario=cfg.simulation.scenario
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
            output_writer.record_step(year + 1, month + 1, diagnostics)

        # 每年打印进度
        if (year + 1) % 10 == 0 or year == 0:
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

