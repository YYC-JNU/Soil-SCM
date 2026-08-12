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

logger = get_logger("config_manager")


@dataclass
class SimulationConfig:
    """模拟控制参数"""
    n_years: int = 50
    time_step: str = "monthly"
    sub_time_step_days: int = 0  # 0=不启用子时间步
    scenario: str = "natural"
    engine_mode: str = "auto"  # auto / phreeqc / simplified (v0.2.1 默认官方引擎)


@dataclass
class SoilDataConfig:
    """土壤数据配置"""
    input_file: str = "data/soil_survey.csv"
    exchangeable_ions_file: str = "data/exchangeable_ions.csv"
    soil_type: str = "red_soil"


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


@dataclass
class PrecipChemConfig:
    """降水化学配置"""
    use_custom: bool = False
    input_file: Optional[str] = None
    data: dict = field(default_factory=dict)  # 加载后的降水化学数据 (Q7)


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
            config.simulation = SimulationConfig(
                n_years=s.get('n_years', 50),
                time_step=s.get('time_step', 'monthly'),
                sub_time_step_days=s.get('sub_time_step_days', 0),
                scenario=s.get('scenario', 'natural'),
                engine_mode=s.get('engine_mode', 'auto')
            )

        # 解析 soil_data
        if 'soil_data' in raw:
            s = raw['soil_data']
            config.soil_data = SoilDataConfig(
                input_file=s.get('input_file', 'data/soil_survey.csv'),
                exchangeable_ions_file=s.get('exchangeable_ions_file',
                                             'data/exchangeable_ions.csv'),
                soil_type=s.get('soil_type', 'red_soil')
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

        # 解析 precipitation_chemistry (Q7: 加载默认或用户自定义数据)
        if 'precipitation_chemistry' in raw:
            p = raw['precipitation_chemistry']
            use_custom = p.get('use_custom', False)
            input_file = p.get('input_file', None)
            data = {}
            data_file = input_file if (use_custom and input_file) else 'config/precip_chemistry_default.json'
            try:
                if Path(data_file).exists():
                    with open(data_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                else:
                    logger.warning("降水化学数据文件不存在: %s", data_file)
            except Exception as e:
                logger.warning("降水化学数据加载失败: %s", e)
            config.precip_chemistry = PrecipChemConfig(
                use_custom=use_custom, input_file=input_file, data=data)

        # 解析 output
        if 'output' in raw:
            o = raw['output']
            config.output = OutputConfig(
                directory=o.get('directory', './output'),
                format=o.get('format', 'csv'),
                variables=o.get('variables', config.output.variables)
            )

        return config

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

        # 创建输出目录
        os.makedirs(self.config.output.directory, exist_ok=True)

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



