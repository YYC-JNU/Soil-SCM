"""
模块: config_validation.py
功能: 配置合法性校验规则 (2026-09-02 候选5 自 config_manager.py 迁出)

配置校验是"独立可移动的复杂度" — 纯函数规则族, 零 IO (除 texture_code.json
读取), 零 ConfigManager 状态。ConfigManager._validate_config 降为薄委托,
60 项既有测试经构造触发校验, 零改动; 本模块可脱离 yaml 加载直接断言规则。

依赖方向唯一: config_manager → config_validation (cfg 鸭子类型, 不 import
Config 避免循环依赖)。报错消息与历史逐字一致 (测试断言消息片段)。
"""

import json
import os
from pathlib import Path
from typing import Any, Dict

from src.constants import PRECIP_ION_KEYS
from src.logging_config import get_logger

logger = get_logger("config_validation")


def validate_config(cfg) -> None:
    """验证配置参数合法性 (纯函数, 零副作用; 不创建输出目录)

    参数:
        cfg: Config 实例 (鸭子类型, 访问 .simulation/.output/.climate 等)
    """
    assert cfg.simulation.n_years > 0, "模拟年数必须大于0"
    assert cfg.simulation.sub_time_step_days >= 0, "子时间步长不能为负"
    if cfg.simulation.sub_time_step_days > 7:
        raise ValueError("子时间步长不能超过7天")

    valid_scenarios = ['natural', 'fertilizer', 'fertilizer_lime',
                       'precip_increase', 'temp_increase']
    assert cfg.simulation.scenario in valid_scenarios, \
        f"情景 {cfg.simulation.scenario} 无效"

    valid_modes = ['simplified', 'phreeqc', 'auto']
    assert cfg.simulation.engine_mode in valid_modes, \
        f"引擎模式 {cfg.simulation.engine_mode} 无效, " \
        f"可选: {valid_modes}"

    assert cfg.output.format in ['csv', 'netcdf'], \
        "输出格式仅支持 csv 或 netcdf"

    # ---- soil_data 子块校验 (v0.2.3) ----
    # 每个子块 (survey / exchangeable_ions):
    #   全部字段 = -1 → 回退 CSV (合法)
    #   全部字段为有效值 → 覆盖 CSV (合法)
    #   混合 (部分 -1 部分有效值) → 报错
    _validate_soil_block("survey", vars(cfg.soil_data.survey))
    _validate_soil_block("exchangeable_ions",
                         vars(cfg.soil_data.exchangeable_ions))

    # survey 特有校验: 全部有效值时检查砂粉黏之和与质地编码
    survey_vals = vars(cfg.soil_data.survey)
    if all(v != -1 for v in survey_vals.values()):
        total = survey_vals['sand_pct'] + survey_vals['silt_pct'] + \
            survey_vals['clay_pct']
        if abs(total - 100.0) > 1e-6:
            raise ValueError(
                "['sand_pct/silt_pct/clay_pct' 参数存在问题: 三者之和必须等于 100, "
                f"当前为 {total:.2f}, 请确认后再输入]")
        _validate_texture_code(survey_vals['texture'])

    # ---- precipitation_chemistry 校验 (v0.2.3) ----
    _validate_precip_chemistry(cfg)

    # ---- L6: layer_overrides / layer_depths 校验 (v0.4.0) ----
    _validate_layer_overrides(cfg)

    # ---- L4: 硝化速率校验 (v0.4.0 config 显式化, 0~1 比例) ----
    for name in ('nitrification_k1', 'nitrification_k2'):
        k = getattr(cfg.simulation, name)
        if not (0.0 <= k <= 1.0):
            raise ValueError(
                f"['simulation.{name}' 参数存在问题: 速率 {k} 超出范围 (0~1), "
                f"请确认后再输入]")

    # ---- v0.5.2: 大孔隙优先流比例校验 (0~1) ----
    bypass = cfg.simulation.bypass_fraction
    if not (0.0 <= bypass <= 1.0):
        raise ValueError(
            f"['simulation.bypass_fraction' 参数存在问题: "
            f"比例 {bypass} 超出范围 (0~1), 请确认后再输入]")

    # ---- v0.6.1: VIC 深层基流校验 (spec 62 Q1/Q10) ----
    _validate_baseflow(cfg)
    # ---- v0.6.1: Darcy 侧向排水校验 (spec 62 Q1/Q10) ----
    _validate_lateral(cfg)
    # ---- v0.7.0 (spec 69, 工单70): NO3- 伴随淋失配置校验 ----
    _validate_companion(cfg)
    # ---- v0.7.0 (spec 69, 工单73): 矿物风化注入配置校验 ----
    _validate_weathering(cfg)
    # ---- v0.7.x (工单80): 盐基淋失强化配置校验 ----
    _validate_base_leaching(cfg)

    # ---- v0.5.3: 初始基质势校验 (负值吸力) ----
    psi = cfg.simulation.initial_psi_cm
    if psi >= 0:
        raise ValueError(
            f"['simulation.initial_psi_cm' 参数存在问题: "
            f"初始水势 {psi} 必须为负 (吸力水头 cm, 田间持水量≈-100), "
            f"请确认后再输入]")

    # ---- v0.5.3: PET 通道校验 (D5) ----
    _validate_climate(cfg)
def _validate_baseflow(cfg) -> None:
    """v0.6.1: VIC 深层基流校验 (spec 62 Q1/Q10)"""
    bf = cfg.simulation.baseflow
    if bf is not None:
        if bf.theta_c != 'auto':
            raise ValueError(
                "['simulation.baseflow.theta_c' 参数存在问题: "
                "仅支持 \"auto\" (自动取 VGM 残余含水量 θ_r), "
                f"当前为 {bf.theta_c}, 请确认后再输入]")
        if bf.D_max is not None and bf.D_max <= 0:
            raise ValueError(
                f"['simulation.baseflow.D_max' 参数存在问题: "
                f"最大基流速率 {bf.D_max} 必须 >0, 请确认后再输入]")
        if bf.D_s is not None and not (0.0 < bf.D_s <= 1.0):
            raise ValueError(
                f"['simulation.baseflow.D_s' 参数存在问题: "
                f"线性比例 {bf.D_s} 超出范围 (0,1], 请确认后再输入]")
        if bf.n_base is not None and bf.n_base <= 1.0:
            raise ValueError(
                f"['simulation.baseflow.n_base' 参数存在问题: "
                f"非线性指数 {bf.n_base} 必须 >1, 请确认后再输入]")


def _validate_lateral(cfg) -> None:
    """v0.6.1: Darcy 侧向排水校验 (spec 62 Q1/Q10)"""
    lat = cfg.simulation.lateral
    if lat is not None:
        if lat.f_slope is not None and not (0.0 < lat.f_slope < 1.0):
            raise ValueError(
                f"['simulation.lateral.f_slope' 参数存在问题: "
                f"坡度因子 {lat.f_slope} 超出范围 (0,1), 请确认后再输入]")
        if lat.k_lat is not None:
            if isinstance(lat.k_lat, list):
                if not all(k > 0 for k in lat.k_lat):
                    raise ValueError(
                        "['simulation.lateral.k_lat' 参数存在问题: "
                        "各层侧向系数必须 >0, 请确认后再输入]")
                n = cfg.simulation.n_layers
                if len(lat.k_lat) != n:
                    raise ValueError(
                        f"['simulation.lateral.k_lat' 参数存在问题: "
                        f"长度 {len(lat.k_lat)} != n_layers({n}), "
                        f"请确认后再输入]")
            elif lat.k_lat <= 0:
                raise ValueError(
                    f"['simulation.lateral.k_lat' 参数存在问题: "
                    f"系数 {lat.k_lat} 必须 >0, 请确认后再输入]")


def _validate_companion(cfg) -> None:
    """v0.7.0 (spec 69, 工单70): NO3- 伴随淋失配置校验"""
    comp = cfg.simulation.companion
    if comp is not None:
        if not isinstance(comp.enable, bool):
            raise ValueError(
                "['simulation.companion.enable' 参数存在问题: "
                "必须为布尔 (true/false), 请确认后再输入]")
        if not isinstance(comp.bypass_no3_carry, bool):
            raise ValueError(
                "['simulation.companion.bypass_no3_carry' 参数存在问题: "
                "必须为布尔 (true/false), 请确认后再输入]")
        if not isinstance(comp.nh4_exchange, bool):
            raise ValueError(
                "['simulation.companion.nh4_exchange' 参数存在问题: "
                "必须为布尔 (true/false), 请确认后再输入]")
        if not (0.0 < comp.bs_low < comp.bs_high <= 100.0):
            raise ValueError(
                "['simulation.companion.bs_high/bs_low' 参数存在问题: "
                f"阈值需满足 0 < bs_low({comp.bs_low}) < "
                f"bs_high({comp.bs_high}) ≤ 100, 请确认后再输入]")


def _validate_weathering(cfg) -> None:
    """v0.7.0 (spec 69, 工单73): 矿物风化注入配置校验"""
    wth = cfg.simulation.weathering
    if wth is not None:
        if not isinstance(wth.enable, bool):
            raise ValueError(
                "['simulation.weathering.enable' 参数存在问题: "
                "必须为布尔 (true/false), 请确认后再输入]")
        if wth.rate_molc_ha_yr <= 0:
            raise ValueError(
                "['simulation.weathering.rate_molc_ha_yr' 参数存在问题: "
                f"风化速率 {wth.rate_molc_ha_yr} 必须 >0, 请确认后再输入]")
        frac_sum = wth.ca_frac + wth.mg_frac + wth.k_frac
        if not (0.0 < wth.ca_frac < 1.0 and 0.0 < wth.mg_frac < 1.0
                and 0.0 < wth.k_frac < 1.0) or abs(frac_sum - 1.0) > 1e-6:
            raise ValueError(
                "['simulation.weathering.ca/mg/k_frac' 参数存在问题: "
                f"盐基电荷占比须 0<各<1 且和=1 (当前 {wth.ca_frac}/"
                f"{wth.mg_frac}/{wth.k_frac} Σ={frac_sum:.4f}), 请确认后再输入]")
        if wth.activation_energy_kJ <= 0:
            raise ValueError(
                "['simulation.weathering.activation_energy_kJ' 参数存在问题: "
                "活化能必须 >0, 请确认后再输入]")


def _validate_base_leaching(cfg) -> None:
    """v0.7.x (工单80): 盐基淋失强化配置校验"""
    bl = cfg.simulation.base_leaching
    if bl is not None:
        if not isinstance(bl.enable, bool):
            raise ValueError(
                "['simulation.base_leaching.enable' 参数存在问题: "
                "必须为布尔 (true/false), 请确认后再输入]")
        if not (0.0 < bl.bs_low < bl.bs_high <= 100.0):
            raise ValueError(
                "['simulation.base_leaching.bs_high/bs_low' 参数存在问题: "
                f"阈值需满足 0 < bs_low({bl.bs_low}) < "
                f"bs_high({bl.bs_high}) ≤ 100, 请确认后再输入]")
        if not bl.anion or not bl.anion.strip():
            raise ValueError(
                "['simulation.base_leaching.anion' 参数存在问题: "
                "保守惰性阴离子元素名不能为空 (默认 An), 请确认后再输入]")
def _validate_climate(cfg) -> None:
    """v0.5.3: PET 通道校验 (D5)"""
    clim = cfg.climate
    if not (-60.0 < clim.latitude < 60.0):
        raise ValueError(
            f"['climate.latitude' 参数存在问题: 纬度 {clim.latitude} "
            f"超出范围 (-60,60), 请确认后再输入]")
    if clim.pet_method == "hargreaves_enhanced":
        raise ValueError(
            "['climate.pet_method' 参数存在问题: 'hargreaves_enhanced' 为 "
            "v0.7.0 预留 (12 值日较差 + 外部气候文件内插), v0.6.0 仅支持 "
            "'oudin'/'fixed'/'hargreaves', 请确认后再输入]")
    if clim.pet_method not in ("oudin", "fixed", "hargreaves"):
        raise ValueError(
            f"['climate.pet_method' 参数存在问题: 方法 {clim.pet_method} "
            f"无效, 可选: 'oudin'/'fixed'/'hargreaves', 请确认后再输入]")
    # v0.6.0 (Q8): 日较差校验 (>0, Hargreaves 必需)
    if clim.diurnal_range_deg <= 0:
        raise ValueError(
            f"['climate.diurnal_range_deg' 参数存在问题: 日较差 "
            f"{clim.diurnal_range_deg} 必须为正 (>0, Hargreaves 用), "
            f"请确认后再输入]")
    if clim.pet_monthly_climate is not None \
            and len(clim.pet_monthly_climate) != 12:
        raise ValueError(
            "['climate.pet_monthly_climate' 参数存在问题: 必须为 12 值 "
            "(逐月气候态 PET), 请确认后再输入]")
    if len(clim.pet_correction_factor) != 12:
        raise ValueError(
            "['climate.pet_correction_factor' 参数存在问题: 必须为 12 值 "
            "(逐月修正系数), 请确认后再输入]")
    if clim.pet_method == "fixed" and clim.pet_monthly_climate is None:
        raise ValueError(
            "['climate.pet_method' 参数存在问题: 'fixed' 方法必须提供 "
            "'pet_monthly_climate' (12 值), 请确认后再输入]")


def _validate_layer_overrides(cfg) -> None:
    """校验逐层参数覆盖 (L6, v0.4.0)

    规则:
        1. n_layers=1 且 layer_overrides/layer_depths 非空 → 警告 + 忽略 (单层回归护栏)
        2. n_layers>1: 密集列表长度必须 = n_layers (否则报错)
        3. 覆盖字段值域校验 (ph∈(3,10), cec/bulk_density/pCO2>0, exch_*≥0, 质量分数∈(0,1))
        4. minerals 质量分数总和≠1 → 警告 (增量替换, 不归一化)
    """
    sim = cfg.simulation
    n = sim.n_layers
    overrides = sim.layer_overrides
    depths = sim.layer_depths

    if n == 1:
        if overrides or depths:
            logger.warning(
                "n_layers=1 时 layer_overrides/layer_depths 将被忽略 "
                "(单层回归护栏), 请仅在 n_layers>1 时配置")
        return

    if overrides and len(overrides) != n:
        raise ValueError(
            f"['layer_overrides' 参数存在问题: 密集列表长度 {len(overrides)} "
            f"必须等于 n_layers {n}, 请确认后再输入]")
    if depths is not None and len(depths) != n:
        raise ValueError(
            f"['layer_depths' 参数存在问题: 列表长度 {len(depths)} "
            f"必须等于 n_layers {n}, 请确认后再输入]")

    for i, lo in enumerate(overrides):
        if lo.ph is not None and not (3.0 <= lo.ph <= 10.0):
            raise ValueError(
                f"[layer_overrides[{i}]/ph 参数存在问题: {lo.ph} 超出物理范围 (3~10), "
                f"请确认后再输入]")
        if lo.cec is not None and lo.cec <= 0:
            raise ValueError(
                f"[layer_overrides[{i}]/cec 参数存在问题: 必须大于 0, "
                f"请确认后再输入]")
        if lo.bulk_density is not None and lo.bulk_density <= 0:
            raise ValueError(
                f"[layer_overrides[{i}]/bulk_density 参数存在问题: 必须大于 0, "
                f"请确认后再输入]")
        if lo.pCO2 is not None and lo.pCO2 <= 0:
            raise ValueError(
                f"[layer_overrides[{i}]/pCO2 参数存在问题: 必须大于 0, "
                f"请确认后再输入]")
        for fld in ('exch_ca', 'exch_mg', 'exch_k', 'exch_na',
                    'exch_al', 'exch_h'):
            v = getattr(lo, fld)
            if v is not None and v < 0:
                raise ValueError(
                    f"[layer_overrides[{i}]/{fld} 参数存在问题: 不能为负, "
                    f"请确认后再输入]")
        if lo.minerals:
            for mname, frac in lo.minerals.items():
                if not (0.0 < frac < 1.0):
                    raise ValueError(
                        f"[layer_overrides[{i}]/minerals.{mname} 参数存在问题: "
                        f"质量分数 {frac} 超出范围 (0,1), 请确认后再输入]")
            total = sum(lo.minerals.values())
            if abs(total - 1.0) > 1e-6:
                logger.warning(
                    "layer_overrides[%d] 矿物质量分数总和 %.3f != 1 "
                    "(增量替换语义, 不归一化), 请确认剖面数据", i, total)
# v0.5.0 水文值域校验
        if lo.porosity is not None and not (0.0 < lo.porosity < 1.0):
            raise ValueError(
                f"[layer_overrides[{i}]/porosity 参数存在问题: {lo.porosity} "
                f"超出范围 (0,1), 请确认后再输入]")
        if lo.ksat is not None and lo.ksat <= 0:
            raise ValueError(
                f"[layer_overrides[{i}]/ksat 参数存在问题: 层间排水上限必须大于 0, "
                f"请确认后再输入]")
        if lo.ksat_surface is not None and lo.ksat_surface <= 0:
            raise ValueError(
                f"[layer_overrides[{i}]/ksat_surface 参数存在问题: 基质导水率必须大于 0, "
                f"请确认后再输入]")
        if lo.clay_pct is not None and not (0.0 <= lo.clay_pct <= 100.0):
            raise ValueError(
                f"[layer_overrides[{i}]/clay_pct 参数存在问题: {lo.clay_pct} "
                f"超出范围 (0~100), 请确认后再输入]")
        # v0.5.3 VGM 显式参数值域校验 (D8 ① 优先级)
        if lo.vgm_theta_r is not None and not (0.0 <= lo.vgm_theta_r < 1.0):
            raise ValueError(
                f"[layer_overrides[{i}]/vgm_theta_r 参数存在问题: "
                f"残余含水量 {lo.vgm_theta_r} 超出范围 [0,1), "
                f"请确认后再输入]")
        if lo.vgm_alpha is not None and lo.vgm_alpha <= 0:
            raise ValueError(
                f"[layer_overrides[{i}]/vgm_alpha 参数存在问题: "
                f"进气值倒数 {lo.vgm_alpha} 必须大于 0 (1/cm), "
                f"请确认后再输入]")
        if lo.vgm_n is not None and lo.vgm_n <= 1:
            raise ValueError(
                f"[layer_overrides[{i}]/vgm_n 参数存在问题: "
                f"孔隙分布指数 {lo.vgm_n} 必须大于 1, "
                f"请确认后再输入]")


def _validate_precip_chemistry(cfg) -> None:
    """校验降水化学配置 (v0.2.3)

    规则:
        1. 整块校验: ph + 10 离子 → 混合填写 (部分 -1) → 报错
        2. 全有效值: 离子占比之和必须 = 100; H⁺ 占比必须 > 0
        3. 全 -1: JSON 文件必须存在 (Q7)
    """
    pc = cfg.precip_chemistry
    pc_vals = {"ph": pc.ph, **vars(pc.ions)}
    minus_one = [k for k, v in pc_vals.items() if v == -1]

    if 0 < len(minus_one) < len(pc_vals):
        bad = '、'.join(f'"{k}"' for k in minus_one)
        raise ValueError(
            f"[precipitation_chemistry] {bad} 参数存在问题: 填 -1 表示使用 "
            f"JSON 默认值, 请确认后再输入 (要么全部填 -1, 要么全部填有效值)")

    if not minus_one:
        # 全有效值: 校验离子占比之和与 H⁺ 占比
        total = sum(getattr(pc.ions, k) for k in PRECIP_ION_KEYS)
        if abs(total - 100.0) > 1e-6:
            raise ValueError(
                "['ions' 参数存在问题: 10 种离子当量占比之和必须等于 100, "
                f"当前为 {total:.2f}, 请确认后再输入]")
        if pc.ions.H <= 0:
            raise ValueError(
                "['H' 参数存在问题: H⁺ 当量占比必须大于 0, 请确认后再输入]")
    else:
        # 全 -1: 回退 JSON, 文件必须存在 (Q7)
        data_file = Path(pc.input_file or 'config/precip_chemistry_default.json')
        if not data_file.exists():
            raise FileNotFoundError(
                f"降水化学参数全部为 -1 (需读取 JSON 默认值), "
                f"但文件不存在: {data_file}")


def _validate_texture_code(code: int) -> None:
    """校验质地编码合法性 (config/texture_code.json)

    参数:
        code: 用户填写的质地编码数字
    异常:
        ValueError: 编码不在编码表中
    """
    path = Path("config/texture_code.json")
    if not path.exists():
        raise FileNotFoundError(f"质地编码表不存在: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    codes = {int(k): v['name'] for k, v in data.get('texture_codes', {}).items()}
    if code not in codes:
        valid = ', '.join(f"{k}({v})" for k, v in sorted(codes.items()))
        raise ValueError(
            f"['texture' 参数存在问题: 编码 {code} 无效, 可选: {valid}, "
            f"请确认后再输入]")


def _validate_soil_block(block_name: str, values: dict) -> None:
    """校验土壤数据子块: 禁止混合填写 (-1 与有效值并存)

    参数:
        block_name: 子块名称 (survey / exchangeable_ions), 用于报错提示
        values: 子块字段名 → 值的 dict
    异常:
        ValueError: 存在混合填写时, 一次性列出所有 -1 字段
    """
    minus_one = [k for k, v in values.items() if v == -1]
    if 0 < len(minus_one) < len(values):
        bad = '、'.join(f'"{k}"' for k in minus_one)
        raise ValueError(
            f"[{block_name}] {bad} 参数存在问题: 填 -1 表示使用 CSV 默认值, "
            f"请确认后再输入 (要么全部填 -1, 要么全部填有效值)")