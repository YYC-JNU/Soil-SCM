"""
模块: config_manager.py
功能: 配置文件加载与管理 (类似 WRF namelist 读取器)

输入: config.yaml 文件路径
输出: Config 对象 (包含所有配置参数)
"""

import json
import yaml
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from src.logging_config import get_logger
from src.constants import (PRECIP_INFILTRATION_DEFAULT,
                           NITRIFICATION_K1, NITRIFICATION_K2,
                           INITIAL_PSI_CM)

logger = get_logger("config_manager")


@dataclass
class LayerOverrideConfig:
    """单层覆盖配置 (L6, v0.4.0)

    字段为 None 表示该层该字段回退全局默认 profile (部分覆盖语义)。
    minerals 为矿物质量分数增量替换 dict (只替换指定矿物, 不归一化, 总和≠1 警告)。
    """
    ph: Optional[float] = None
    organic_matter: Optional[float] = None
    cec: Optional[float] = None
    bulk_density: Optional[float] = None
    exch_ca: Optional[float] = None
    exch_mg: Optional[float] = None
    exch_k: Optional[float] = None
    exch_na: Optional[float] = None
    exch_al: Optional[float] = None
    exch_h: Optional[float] = None
    pCO2: Optional[float] = None
    minerals: Dict[str, float] = field(default_factory=dict)
    # v0.5.0 水文: 逐层土壤水文参数 (孔隙度覆盖时反推容重 ρ=2.65(1−φ))
    clay_pct: Optional[float] = None             # 粘粒含量 (%)
    porosity: Optional[float] = None             # 孔隙度 (0~1), 覆盖容重派生
    ksat: Optional[float] = None                 # 层间排水上限 (cm/day, v0.5.2 起仅 LayerCascade 用)
    ksat_surface: Optional[float] = None         # v0.5.2: 基质导水率 (cm/day, 仅 Green-Ampt 地表入渗)
    infiltration_initial: Optional[float] = None  # 初渗率 f0 (mm/min, deprecated)
    infiltration_steady: Optional[float] = None   # 稳渗率 fc (mm/min, deprecated)
    # v0.5.3 VGM 显式参数 (D8 三级优先级 ①: None=走 clay_pct 回归/红壤兜底)
    vgm_theta_r: Optional[float] = None           # 残余含水量 θ_r
    vgm_alpha: Optional[float] = None             # 进气值倒数 α (1/cm)
    vgm_n: Optional[float] = None                 # 孔隙分布指数 n


@dataclass
class SimulationConfig:
    """模拟控制参数"""
    n_years: int = 50
    time_step: str = "monthly"
    sub_time_step_days: int = 0  # 0=不启用子时间步
    scenario: str = "natural"
    engine_mode: str = "auto"  # auto / phreeqc / simplified (v0.2.1 默认官方引擎)
    precip_infiltration: float = PRECIP_INFILTRATION_DEFAULT  # 降水入渗系数 0~1 (T3)
    n_layers: int = 1  # 分层数 (WF2): 1=单层, 4=多分层 (各层默认参数相同)
    enable_surface: bool = False  # WF4: 启用 SURFACE 表面络合 (Hfo_s/Hfo_w), 默认关闭
    enable_pre_equilibration: bool = True  # v0.5.0: 初始状态预平衡 (热力学自洽, 默认开启)
    pre_equilibration_max_steps: int = 60  # v0.5.0: 预平衡最大步数 (收敛判据见引擎)
    layer_depths: Optional[List[float]] = None  # L6: 每层厚度 (cm), None=等分兜底; 每层 effective_depth 由此派生
    layer_overrides: List[LayerOverrideConfig] = field(default_factory=list)  # L6: 逐层参数覆盖 (密集列表, 长度=n_layers)
    nitrification_k1: float = NITRIFICATION_K1  # L4: 尿素水解速率 (/月), 1.0=当月全水解
    nitrification_k2: float = NITRIFICATION_K2  # L4: 硝化速率 (/月), NH4+→NO3- 比例
    hydrology_seed: int = 42                    # v0.5.0: 随机降雨生成种子 (可复现)
    bypass_fraction: float = 0.2                # v0.5.2: 大孔隙优先流比例 (0~1, 超基质 Ks 积水直通 L2)
    initial_psi_cm: float = INITIAL_PSI_CM      # v0.5.3: 初始基质势 (cm, 负值, 田间持水量, VGM 正算 θ_init)


@dataclass
class SurveyConfig:
    """土壤普查参数 (config 内联字段)

    -1 = 不填写, 回退读取 data/soil_survey.csv 中的默认值 (v0.2.3)
    逻辑: 全部字段为 -1 → 使用 CSV; 全部字段为有效值 → 覆盖 CSV; 混合 → 报错
    """
    ph: float = -1.0                # 初始 pH
    organic_matter: float = -1.0    # 有机质 (g/kg)
    cec: float = -1.0               # 阳离子交换量 (cmol(+)/kg)
    bulk_density: float = -1.0      # 容重 (g/cm³)
    area: float = -1.0              # 耕地面积 (ha)
    effective_depth: float = -1.0   # 有效土层厚度 (cm)
    available_p: float = -1.0       # 有效磷 (mg/kg)
    available_k: float = -1.0       # 速效钾 (mg/kg)
    texture: int = -1               # 质地编码 (见 config/texture_code.json), -1=使用CSV
    sand_pct: float = -1.0          # 砂粒 (%)
    silt_pct: float = -1.0          # 粉粒 (%)
    clay_pct: float = -1.0          # 黏粒 (%)


@dataclass
class ExchangeableIonsConfig:
    """交换性阳离子参数 (config 内联字段)

    -1 = 不填写, 回退读取 data/exchangeable_ions.csv 中的默认值 (v0.2.3)
    逻辑与 SurveyConfig 一致: 全部 -1 → 使用 CSV; 全部有效值 → 覆盖 CSV; 混合 → 报错
    """
    exch_ca: float = -1.0           # 交换性 Ca (cmol(+)/kg)
    exch_mg: float = -1.0           # 交换性 Mg (cmol(+)/kg)
    exch_k: float = -1.0            # 交换性 K (cmol(+)/kg)
    exch_na: float = -1.0           # 交换性 Na (cmol(+)/kg)
    exch_al: float = -1.0           # 交换性 Al (cmol(+)/kg)
    exch_h: float = -1.0            # 交换性 H (cmol(+)/kg)


@dataclass
class SoilDataConfig:
    """土壤数据配置"""
    input_file: str = "data/soil_survey.csv"
    exchangeable_ions_file: str = "data/exchangeable_ions.csv"
    soil_type: str = "red_soil"
    survey: SurveyConfig = field(default_factory=SurveyConfig)
    exchangeable_ions: ExchangeableIonsConfig = field(default_factory=ExchangeableIonsConfig)


@dataclass
class ClimateConfig:
    """气候强迫配置"""
    base_annual_precip: float = 1893.0   # mm/yr
    base_annual_temp: float = 25.0       # °C
    precip_increase_rate: float = 0.02   # 情景3: 2%/yr
    temp_increase_rate: float = 0.05     # 情景4: 0.05°C/yr


@dataclass
class FertilizerConfig:
    """肥料配置 (农业农村部2021指导意见, 水稻500kg/ha)
    每次施用量 (kg/ha), 每年 3/6/9 月各一次
    """
    n: float = 12.0          # 氮肥 (按N元素)
    p2o5: float = 4.0        # 磷肥 (按P2O5)
    k2o: float = 9.0         # 钾肥 (按K2O)
    mgo: float = 3.0         # 镁肥 (按MgO)
    znso4: float = 1.0       # 硫酸锌 (按ZnSO4)
    apply_months: List[int] = field(default_factory=lambda: [3, 6, 9])


@dataclass
class LimeConfig:
    """生石灰配置 (按CaO, 每次施用量kg/ha)"""
    amount_per_apply: float = 45.0       # kg CaO/ha/次 (推荐 40~50)
    apply_months: List[int] = field(default_factory=lambda: [3, 6, 9])


@dataclass
class SoilCO2Config:
    """土壤CO2分压配置
    参考文献:
      Brook G.A., Folkoff M.E., Box E.O. (1983). A world model of soil
      carbon dioxide. Earth Surface Processes and Landforms, 8(1), 79-88.
      Davidson E.A., Trumbore S.E. (1995). Gas diffusivity and production
      of CO2 in deep soils of the eastern Amazon. Tellus B, 47(5), 550-565.
    """
    pCO2_ref: float = 0.015              # atm
    T_ref: float = 25.0                  # °C
    beta: float = 0.05                   # 温度响应系数 (1/°C)


# 降水化学离子键 (与 JSON 文件 ions 键一致, v0.2.3)
PRECIP_ION_KEYS = ["Cl", "SO4", "NO3", "F", "Ca", "NH4", "Na", "Mg", "K", "H"]


@dataclass
class PrecipIonsConfig:
    """降水化学离子当量占比 (config 内联字段)

    -1 = 不填写, 回退读取 input_file 指定的 JSON 默认值 (v0.2.3)
    逻辑: 全部字段为 -1 → 使用 JSON; 全部字段为有效值 → 覆盖 JSON; 混合 → 报错
    """
    Cl: float = -1.0        # Cl⁻ 当量占比 (%)
    SO4: float = -1.0       # SO₄²⁻ 当量占比 (%)
    NO3: float = -1.0       # NO₃⁻ 当量占比 (%)
    F: float = -1.0         # F⁻ 当量占比 (%)
    Ca: float = -1.0        # Ca²⁺ 当量占比 (%)
    NH4: float = -1.0       # NH₄⁺ 当量占比 (%)
    Na: float = -1.0        # Na⁺ 当量占比 (%)
    Mg: float = -1.0        # Mg²⁺ 当量占比 (%)
    K: float = -1.0         # K⁺ 当量占比 (%)
    H: float = -1.0         # H⁺ 当量占比 (%)


@dataclass
class PrecipChemConfig:
    """降水化学配置 (v0.2.3: config 内联优先, -1 回退 JSON)"""
    input_file: str = "config/precip_chemistry_default.json"
    ph: float = -1.0        # 降水 pH, -1=使用JSON
    ions: PrecipIonsConfig = field(default_factory=PrecipIonsConfig)
    data: dict = field(default_factory=dict)  # 最终生效的降水化学数据 (pH + ions)


@dataclass
class OutputConfig:
    """输出配置"""
    directory: str = "./output"
    format: str = "csv"                  # csv / netcdf
    variables: List[str] = field(default_factory=lambda: [
        "pH", "base_saturation", "CEC_occupied",
        "exchangeable_Ca", "exchangeable_Al"
    ])


@dataclass
class Config:
    """总配置对象"""
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    soil_data: SoilDataConfig = field(default_factory=SoilDataConfig)
    climate: ClimateConfig = field(default_factory=ClimateConfig)
    fertilizer: FertilizerConfig = field(default_factory=FertilizerConfig)
    lime: LimeConfig = field(default_factory=LimeConfig)
    soil_co2: SoilCO2Config = field(default_factory=SoilCO2Config)
    precip_chemistry: PrecipChemConfig = field(default_factory=PrecipChemConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


class ConfigManager:
    """配置管理器: 加载、验证、提供配置参数"""

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._validate_config()

    def _load_config(self) -> Config:
        """从 YAML 文件加载配置"""
        if not self.config_path.exists():
            logger.warning("配置文件 %s 不存在，使用默认配置", self.config_path)
            return Config()

        with open(self.config_path, 'r', encoding='utf-8') as f:
            raw = yaml.safe_load(f)

        config = Config()

        # 解析 simulation
        if 'simulation' in raw:
            s = raw['simulation']
            # L6: layer_overrides 密集列表解析 (元素为 dict, 缺失字段保持 None)
            overrides_raw = s.get('layer_overrides', []) or []
            overrides = []
            for item in overrides_raw:
                if not isinstance(item, dict):
                    item = {}
                overrides.append(LayerOverrideConfig(
                    ph=item.get('ph'),
                    organic_matter=item.get('organic_matter'),
                    cec=item.get('cec'),
                    bulk_density=item.get('bulk_density'),
                    exch_ca=item.get('exch_ca'),
                    exch_mg=item.get('exch_mg'),
                    exch_k=item.get('exch_k'),
                    exch_na=item.get('exch_na'),
                    exch_al=item.get('exch_al'),
                    exch_h=item.get('exch_h'),
                    pCO2=item.get('pCO2'),
                    minerals=dict(item.get('minerals', {})),
                    clay_pct=item.get('clay_pct'),
                    porosity=item.get('porosity'),
                    ksat=item.get('ksat'),
                    ksat_surface=item.get('ksat_surface'),
                    infiltration_initial=item.get('infiltration_initial'),
                    infiltration_steady=item.get('infiltration_steady'),
                    vgm_theta_r=item.get('vgm_theta_r'),
                    vgm_alpha=item.get('vgm_alpha'),
                    vgm_n=item.get('vgm_n')
                ))
            layer_depths = s.get('layer_depths')  # None 或 List[float]
            config.simulation = SimulationConfig(
                n_years=s.get('n_years', 50),
                time_step=s.get('time_step', 'monthly'),
                sub_time_step_days=s.get('sub_time_step_days', 0),
                scenario=s.get('scenario', 'natural'),
                engine_mode=s.get('engine_mode', 'auto'),
                precip_infiltration=s.get('precip_infiltration', PRECIP_INFILTRATION_DEFAULT),
                n_layers=s.get('n_layers', 1),
                enable_surface=s.get('enable_surface', False),
                enable_pre_equilibration=s.get('enable_pre_equilibration', True),
                pre_equilibration_max_steps=s.get('pre_equilibration_max_steps', 60),
                layer_depths=(list(layer_depths) if layer_depths is not None else None),
                layer_overrides=overrides,
                nitrification_k1=s.get('nitrification_k1', NITRIFICATION_K1),
                nitrification_k2=s.get('nitrification_k2', NITRIFICATION_K2),
                hydrology_seed=s.get('hydrology_seed', 42),
                bypass_fraction=s.get('bypass_fraction', 0.2),
                initial_psi_cm=s.get('initial_psi_cm', INITIAL_PSI_CM)
            )
            # v0.5.2: surface_infiltration_coeff 已废弃 (Green-Ampt 入渗替代
            # Horton), 残留配置显式报错 (breaking change 明示, 不静默忽略)
            if 'surface_infiltration_coeff' in s:
                raise ValueError(
                    "[simulation.surface_infiltration_coeff 参数存在问题: "
                    "v0.5.2 已废弃该字段 (Green-Ampt 入渗替代 Horton), "
                    "请移除并用 ksat_surface/bypass_fraction, 请确认后再输入]")

        # 解析 soil_data (v0.2.3: 支持 config 内联字段, -1=回退 CSV)
        if 'soil_data' in raw:
            s = raw['soil_data']
            survey_raw = s.get('survey', {}) if isinstance(s.get('survey'), dict) else {}
            exch_raw = s.get('exchangeable_ions', {}) if isinstance(s.get('exchangeable_ions'), dict) else {}
            config.soil_data = SoilDataConfig(
                input_file=s.get('input_file', 'data/soil_survey.csv'),
                exchangeable_ions_file=s.get('exchangeable_ions_file',
                                             'data/exchangeable_ions.csv'),
                soil_type=s.get('soil_type', 'red_soil'),
                survey=SurveyConfig(
                    ph=survey_raw.get('ph', -1.0),
                    organic_matter=survey_raw.get('organic_matter', -1.0),
                    cec=survey_raw.get('cec', -1.0),
                    bulk_density=survey_raw.get('bulk_density', -1.0),
                    area=survey_raw.get('area', -1.0),
                    effective_depth=survey_raw.get('effective_depth', -1.0),
                    available_p=survey_raw.get('available_p', -1.0),
                    available_k=survey_raw.get('available_k', -1.0),
                    texture=survey_raw.get('texture', -1),
                    sand_pct=survey_raw.get('sand_pct', -1.0),
                    silt_pct=survey_raw.get('silt_pct', -1.0),
                    clay_pct=survey_raw.get('clay_pct', -1.0),
                ),
                exchangeable_ions=ExchangeableIonsConfig(
                    exch_ca=exch_raw.get('exch_ca', -1.0),
                    exch_mg=exch_raw.get('exch_mg', -1.0),
                    exch_k=exch_raw.get('exch_k', -1.0),
                    exch_na=exch_raw.get('exch_na', -1.0),
                    exch_al=exch_raw.get('exch_al', -1.0),
                    exch_h=exch_raw.get('exch_h', -1.0),
                )
            )

        # 解析 climate
        if 'climate' in raw:
            c = raw['climate']
            config.climate = ClimateConfig(
                base_annual_precip=c.get('base_annual_precip', 1893.0),
                base_annual_temp=c.get('base_annual_temp', 25.0),
                precip_increase_rate=c.get('precip_increase_rate', 0.02),
                temp_increase_rate=c.get('temp_increase_rate', 0.05)
            )

        # 解析 fertilizer
        if 'fertilizer' in raw:
            f = raw['fertilizer']
            config.fertilizer = FertilizerConfig(
                n=f.get('n', 12.0),
                p2o5=f.get('p2o5', 4.0),
                k2o=f.get('k2o', 9.0),
                mgo=f.get('mgo', 3.0),
                znso4=f.get('znso4', 1.0),
                apply_months=f.get('apply_months', [3, 6, 9])
            )

        # 解析 lime
        if 'lime' in raw:
            l = raw['lime']
            config.lime = LimeConfig(
                amount_per_apply=l.get('amount_per_apply', 45.0),
                apply_months=l.get('apply_months', [3, 6, 9])
            )

        # 解析 soil_co2
        if 'soil_co2' in raw:
            s = raw['soil_co2']
            config.soil_co2 = SoilCO2Config(
                pCO2_ref=s.get('pCO2_ref', 0.015),
                T_ref=s.get('T_ref', 25.0),
                beta=s.get('beta', 0.05)
            )

        # 解析 precipitation_chemistry (v0.2.3: config 内联优先, -1 回退 JSON)
        if 'precipitation_chemistry' in raw:
            p = raw['precipitation_chemistry']
            input_file = p.get('input_file', 'config/precip_chemistry_default.json')
            ph = p.get('ph', -1.0)
            ions_raw = p.get('ions', {}) if isinstance(p.get('ions'), dict) else {}
            ions_cfg = PrecipIonsConfig(
                Cl=ions_raw.get('Cl', -1.0),
                SO4=ions_raw.get('SO4', -1.0),
                NO3=ions_raw.get('NO3', -1.0),
                F=ions_raw.get('F', -1.0),
                Ca=ions_raw.get('Ca', -1.0),
                NH4=ions_raw.get('NH4', -1.0),
                Na=ions_raw.get('Na', -1.0),
                Mg=ions_raw.get('Mg', -1.0),
                K=ions_raw.get('K', -1.0),
                H=ions_raw.get('H', -1.0),
            )
            config.precip_chemistry = PrecipChemConfig(
                input_file=input_file, ph=ph, ions=ions_cfg)
            self._load_precip_data(config.precip_chemistry)

        # 解析 output
        if 'output' in raw:
            o = raw['output']
            config.output = OutputConfig(
                directory=o.get('directory', './output'),
                format=o.get('format', 'csv'),
                variables=o.get('variables', config.output.variables)
            )

        return config

    def _load_precip_data(self, pc: PrecipChemConfig):
        """加载降水化学最终生效数据 (v0.2.3)

        逻辑:
            全部字段为 -1  → 从 input_file 读取 JSON 数据
            全部字段有效值 → 构建内联 dict (覆盖 JSON)
            混合填写        → data 保持空, 由 _validate_config 报错

        参数:
            pc: PrecipChemConfig 对象 (解析后未填充 data)
        """
        ions_vals = vars(pc.ions)
        all_minus_one = (pc.ph == -1) and all(v == -1 for v in ions_vals.values())
        has_minus_one = (pc.ph == -1) or any(v == -1 for v in ions_vals.values())

        if all_minus_one:
            data_file = Path(pc.input_file or 'config/precip_chemistry_default.json')
            if data_file.exists():
                with open(data_file, 'r', encoding='utf-8') as f:
                    pc.data = json.load(f)
            else:
                logger.warning("降水化学数据文件不存在: %s", data_file)
        elif not has_minus_one:
            # 全有效值 → 构建内联 dict (与 JSON 文件结构一致)
            pc.data = {
                "pH": pc.ph,
                "ions": {k: ions_vals[k] for k in PRECIP_ION_KEYS},
            }
        # 混合填写: data 保持空, 等待 _validate_config 报错

    def _validate_config(self):
        """验证配置参数合法性"""
        assert self.config.simulation.n_years > 0, "模拟年数必须大于0"
        assert self.config.simulation.sub_time_step_days >= 0, "子时间步长不能为负"
        if self.config.simulation.sub_time_step_days > 7:
            raise ValueError("子时间步长不能超过7天")

        valid_scenarios = ['natural', 'fertilizer', 'fertilizer_lime',
                           'precip_increase', 'temp_increase']
        assert self.config.simulation.scenario in valid_scenarios, \
            f"情景 {self.config.simulation.scenario} 无效"

        valid_modes = ['simplified', 'phreeqc', 'auto']
        assert self.config.simulation.engine_mode in valid_modes, \
            f"引擎模式 {self.config.simulation.engine_mode} 无效, " \
            f"可选: {valid_modes}"

        assert self.config.output.format in ['csv', 'netcdf'], \
            "输出格式仅支持 csv 或 netcdf"

        # ---- soil_data 子块校验 (v0.2.3) ----
        # 每个子块 (survey / exchangeable_ions):
        #   全部字段 = -1 → 回退 CSV (合法)
        #   全部字段为有效值 → 覆盖 CSV (合法)
        #   混合 (部分 -1 部分有效值) → 报错
        self._validate_soil_block("survey", vars(self.config.soil_data.survey))
        self._validate_soil_block("exchangeable_ions",
                                  vars(self.config.soil_data.exchangeable_ions))

        # survey 特有校验: 全部有效值时检查砂粉黏之和与质地编码
        survey_vals = vars(self.config.soil_data.survey)
        if all(v != -1 for v in survey_vals.values()):
            total = survey_vals['sand_pct'] + survey_vals['silt_pct'] + \
                survey_vals['clay_pct']
            if abs(total - 100.0) > 1e-6:
                raise ValueError(
                    "['sand_pct/silt_pct/clay_pct' 参数存在问题: 三者之和必须等于 100, "
                    f"当前为 {total:.2f}, 请确认后再输入]")
            self._validate_texture_code(survey_vals['texture'])

        # ---- precipitation_chemistry 校验 (v0.2.3) ----
        self._validate_precip_chemistry()

        # ---- L6: layer_overrides / layer_depths 校验 (v0.4.0) ----
        self._validate_layer_overrides()

        # ---- L4: 硝化速率校验 (v0.4.0 config 显式化, 0~1 比例) ----
        for name in ('nitrification_k1', 'nitrification_k2'):
            k = getattr(self.config.simulation, name)
            if not (0.0 <= k <= 1.0):
                raise ValueError(
                    f"['simulation.{name}' 参数存在问题: 速率 {k} 超出范围 (0~1), "
                    f"请确认后再输入]")

        # ---- v0.5.2: 大孔隙优先流比例校验 (0~1) ----
        bypass = self.config.simulation.bypass_fraction
        if not (0.0 <= bypass <= 1.0):
            raise ValueError(
                f"['simulation.bypass_fraction' 参数存在问题: "
                f"比例 {bypass} 超出范围 (0~1), 请确认后再输入]")

        # ---- v0.5.3: 初始基质势校验 (负值吸力) ----
        psi = self.config.simulation.initial_psi_cm
        if psi >= 0:
            raise ValueError(
                f"['simulation.initial_psi_cm' 参数存在问题: "
                f"初始水势 {psi} 必须为负 (吸力水头 cm, 田间持水量≈-100), "
                f"请确认后再输入]")

        # 创建输出目录
        os.makedirs(self.config.output.directory, exist_ok=True)

    def _validate_layer_overrides(self):
        """校验逐层参数覆盖 (L6, v0.4.0)

        规则:
            1. n_layers=1 且 layer_overrides/layer_depths 非空 → 警告 + 忽略 (单层回归护栏)
            2. n_layers>1: 密集列表长度必须 = n_layers (否则报错)
            3. 覆盖字段值域校验 (ph∈(3,10), cec/bulk_density/pCO2>0, exch_*≥0, 质量分数∈(0,1))
            4. minerals 质量分数总和≠1 → 警告 (增量替换, 不归一化)
        """
        sim = self.config.simulation
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
            f0 = lo.infiltration_initial
            fc = lo.infiltration_steady
            if f0 is not None and not (0.0 < f0 <= 3.0):
                raise ValueError(
                    f"[layer_overrides[{i}]/infiltration_initial 参数存在问题: "
                    f"初渗率 {f0} 超出合理范围 (0~3 mm/min), 请确认后再输入]")
            if fc is not None and not (0.0 <= fc < 3.0):
                raise ValueError(
                    f"[layer_overrides[{i}]/infiltration_steady 参数存在问题: "
                    f"稳渗率 {fc} 超出合理范围 (0~3 mm/min), 请确认后再输入]")
            if f0 is not None and fc is not None and f0 <= fc:
                raise ValueError(
                    f"[layer_overrides[{i}]/infiltration 参数存在问题: "
                    f"初渗率 {f0} 必须大于稳渗率 {fc}, 请确认后再输入]")
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

    def _validate_precip_chemistry(self):
        """校验降水化学配置 (v0.2.3)

        规则:
            1. 整块校验: ph + 10 离子 → 混合填写 (部分 -1) → 报错
            2. 全有效值: 离子占比之和必须 = 100; H⁺ 占比必须 > 0
            3. 全 -1: JSON 文件必须存在 (Q7)
        """
        pc = self.config.precip_chemistry
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

    def _validate_texture_code(self, code: int):
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

    def _validate_soil_block(self, block_name: str, values: dict):
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

    def get(self, section: str, key: str = None) -> Any:
        """获取配置参数"""
        if key is None:
            return getattr(self.config, section)
        return getattr(getattr(self.config, section), key)

    def print_summary(self):
        """打印配置摘要"""
        print("=" * 60)
        print("Soil-SCM 配置摘要")
        print("=" * 60)
        print(f"  模拟年数: {self.config.simulation.n_years} 年")
        print(f"  时间步长: {self.config.simulation.time_step}")
        if self.config.simulation.sub_time_step_days > 0:
            print(f"  子时间步: {self.config.simulation.sub_time_step_days} 天")
        print(f"  情景: {self.config.simulation.scenario}")
        print(f"  引擎模式: {self.config.simulation.engine_mode}")
        print(f"  土壤类型: {self.config.soil_data.soil_type}")
        print(f"  基准降水: {self.config.climate.base_annual_precip} mm/yr")
        print(f"  基准温度: {self.config.climate.base_annual_temp} °C")
        print(f"  氮肥: {self.config.fertilizer.n} kg N/ha/次")
        print(f"  磷肥: {self.config.fertilizer.p2o5} kg P2O5/ha/次")
        print(f"  钾肥: {self.config.fertilizer.k2o} kg K2O/ha/次")
        print(f"  镁肥: {self.config.fertilizer.mgo} kg MgO/ha/次")
        print(f"  硫酸锌: {self.config.fertilizer.znso4} kg ZnSO4/ha/次")
        print(f"  生石灰: {self.config.lime.amount_per_apply} kg CaO/ha/次")
        print(f"  土壤pCO2: {self.config.soil_co2.pCO2_ref} atm")
        print(f"  输出格式: {self.config.output.format}")
        print("=" * 60)



