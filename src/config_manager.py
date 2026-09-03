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
                           INITIAL_PSI_CM, DEFAULT_LATITUDE,
                           DEFAULT_DIURNAL_RANGE,
                           PRECIP_ION_KEYS)
from src.config_validation import validate_config

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
    # v0.5.3 VGM 显式参数 (D8 三级优先级 ①: None=走 clay_pct 回归/红壤兜底)
    vgm_theta_r: Optional[float] = None           # 残余含水量 θ_r
    vgm_alpha: Optional[float] = None             # 进气值倒数 α (1/cm)
    vgm_n: Optional[float] = None                 # 孔隙分布指数 n


@dataclass
class BaseflowConfig:
    """v0.6.1 VIC 深层基流配置 (spec 62, Q1/Q10)

    Q_base = D_max·[D_s·S + (1−D_s)·Sⁿ], S=(θ−θ_r)/(θ_s−θ_r)
      - theta_c="auto" → 用 VGM 残余含水量 θ_r (专家参数表: 旱季裂隙基流基线)
      - None 字段回退 constants 默认; 整个节点缺省 → 不启用基流
    """
    D_max: Optional[float] = None      # 最大基流速率 (mm/month), 默认 BASE_D_MAX
    D_s: Optional[float] = None        # 线性排水比例 (裂隙流基线)
    n_base: Optional[float] = None     # 非线性指数
    theta_c: str = "auto"              # "auto" → θ_r (仅支持 auto, 暂不开放自定义)


@dataclass
class LateralConfig:
    """v0.6.1 Darcy 侧向排水配置 (spec 62, Q1/Q10)

    Q_lat = k_lat·f_slope·max(0, θ−θ_FC)·d·10, 严格 FC 闸门
      - k_lat: 各层侧向系数 (1/day), 长度=n_layers 或标量 (广播)
      - 整个节点缺省 → 不启用侧向
    """
    f_slope: Optional[float] = None    # 地形坡度因子 (tan β, 默认 LAT_F_SLOPE)
    k_lat: Optional[list] = None       # 各层侧向系数 (默认 LAT_K)


@dataclass
class CompanionConfig:
    """v0.7.0 (spec 69, 工单70): NO₃⁻ 伴随淋失配置

    D3 为 v0.7.0 主线功能, 默认启用; enable: false → 完全回退 v0.6.1。
      - enable: 总开关
      - bypass_no3_carry: bypass 优先流携带 L1 池 NO₃⁻ 直通 L2 (工单70)
      - bs_high/bs_low: 分级注入阈值 % (工单71 CompAn 分级用)
      - inert_anion: 惰性阴离子元素名 (PHREEQC 要求单元素名, 物种 = 名+'-';
        默认 An; 引擎输入头段自定义 SOLUTION_MASTER_SPECIES, 不碰 phreeqc.dat)
      - nh4_exchange: NH4+ 等效置换开关 (工单72; 施肥月水解后按交换占比注入盐基,
        模拟 NH4+ 置换盐基的农业酸化通道; 不触碰 L4 Q3=A 氮不进溶液)
    """
    enable: bool = True
    bypass_no3_carry: bool = True
    bs_high: float = 30.0
    bs_low: float = 10.0
    inert_anion: str = "An"
    nh4_exchange: bool = True


@dataclass
class WeatheringConfig:
    """v0.7.0 (spec 69, 工单73): 原生矿物风化集总注入配置 (D2, 不用 KINETICS)

    v0.3.0 证伪 KINETICS (冻结矿物切断 L2 回补→加速 AlX3 耗尽), 故用集总
    REACTION 注入风化碱度替代瞬时平衡相:
      - rate_molc_ha_yr: 每层年均风化碱度 (molc/ha/yr, 默认 500; 工单 76 按
        方向带扫描 100/500/1000 定案)
      - ca_frac/mg_frac/k_frac: 盐基电荷占比 (Ca:Mg:K=5:3:2 归一, Σ=1)
      - activation_energy_kJ: Arrhenius 活化能 (硅酸盐风化典型 40 kJ/mol,
        增温情景风化↑ → 气候敏感性传导恢复)
      - degrade_minerals: 从 EQUILIBRIUM_PHASES 降级的矿物名列表 (默认空=不降级,
        保 Al 循环通道不断 — v0.3.0 教训; 工单 76 按方向带扫描定案后用户配置)
    """
    enable: bool = False
    rate_molc_ha_yr: float = 500.0
    ca_frac: float = 0.5
    mg_frac: float = 0.3
    k_frac: float = 0.2
    activation_energy_kJ: float = 40.0
    degrade_minerals: List[str] = field(default_factory=list)


@dataclass
class BaseLeachingConfig:
    """v0.7.x (工单80): 盐基淋失强化配置 (D3 扩展至无 NO₃⁻ 通道)

    /grilling Q1~Q10 定案 (2026-08-24): 对每层每场, \"离开本层的全部水\"
    (drains+lateral+baseflow) 携带的溶液盐基当量作为 E_base, 下一场平衡前
    REACTION 注入等当量保守惰性阴离子 (默认 An-) → 平衡自洽拽出交换相盐基
    (Gapon), 盐基被持续追赶带走。按 BS 分级降权:
      - BS ≥ bs_high: 全量注入
      - bs_low ≤ BS < bs_high: 线性衰减 ×(BS−bs_low)/(bs_high−bs_low)
      - BS < bs_low: 归零 (zero, 不注入 — 酸化职责保留给硝化/companion acid,
        防 natural 被本通道额外酸化拉出 4.5~5.0 带)
    全情景启用 (含 natural); enable: false = 工单 80 前基线 (A/B 对照)。
    """
    enable: bool = True
    anion: str = "An"          # 保守惰性阴离子元素名 (单元素名, 复用 companion/pairing 物种)
    bs_high: float = 30.0
    bs_low: float = 10.0
    # 工单87 (P0-A): 溶液盐基保底浓度下限 (mmol/L 当量) — E_base 不把溶液盐基
    # 逼到该浓度以下 (护栏, H1 归因落地); 0 = 关闭护栏 (工单 80 行为兼容)。
    # 华南红壤深层渗滤液盐基观测量级 ~1 meq/L (0.5~2.0 区间, 定案值见 spec 87)
    c_floor_mmol_L: float = 0.0


@dataclass
class ChargePairingConfig:
    """v0.7.x (工单77): REACTION 电荷平衡修复配置

    2026-08-21 探针实测: PHREEQC REACTION 注入裸阳离子 (无伴随阴离子)
    因电荷平衡被迫产生 OH- → 伪碱化 (Ca+2 343 → pH 9.28, 复现 v0.7.0
    fertilizer 8~11); 裸 H+ 注入不酸化 (H 以非 H+ 形态存在)。修复:
    净电荷注入按等当量伴随保守惰性阴离子 (默认 An-, 复用 companion
    inert_anion 机制, 独立开关):
      - enable: 总开关 (默认 true; false=回退裸注入, 对照实验)
      - anion: 保守惰性阴离子元素名 (PHREEQC 要求单元素名, 物种 = 名+'-';
        默认 An; 引擎输入头段自定义 SOLUTION_MASTER_SPECIES, 不碰 phreeqc.dat;
        companion 启用时与其 inert_anion 共享物种名)
    """
    enable: bool = True
    anion: str = "An"


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
    event_driven: bool = False                  # v0.6.0: 事件驱动化学 (子步长拆分, 逐场 PHREEQC), 默认关
    baseflow: Optional[BaseflowConfig] = None   # v0.6.1: VIC 深层基流 (None=禁用)
    lateral: Optional[LateralConfig] = None     # v0.6.1: Darcy 侧向排水 (None=禁用)
    companion: CompanionConfig = field(default_factory=CompanionConfig)  # v0.7.0: NO3- 伴随淋失
    weathering: WeatheringConfig = field(default_factory=WeatheringConfig)  # v0.7.0: 矿物风化集总注入
    charge_pairing: ChargePairingConfig = field(default_factory=ChargePairingConfig)  # v0.7.x: REACTION 电荷平衡
    base_leaching: BaseLeachingConfig = field(default_factory=BaseLeachingConfig)  # v0.7.x (工单80): 盐基淋失强化


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
    # v0.5.3 PET 通道 (D5)
    latitude: float = DEFAULT_LATITUDE                  # 站点纬度 (°N, Oudin 必需)
    pet_method: str = "oudin"                           # "oudin" | "fixed" | "hargreaves"
                                                        # (hargreaves_enhanced=v0.6.0 预留报错)
    pet_monthly_climate: Optional[List[float]] = None   # 12 值固定气候态月 PET (mm/month, 提供时优先)
    pet_correction_factor: List[float] = field(
        default_factory=lambda: [1.0] * 12)             # 12 值月度修正系数 (默认恒等)
    # v0.6.0 Hargreaves PET (Q8/Q9): 日较差 T_max−T_min (°C, 默认 8.0, 校验 >0)
    diurnal_range_deg: float = DEFAULT_DIURNAL_RANGE


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
    event_output: bool = False           # v0.6.0: 逐场事件明细 CSV (默认关, 文件体积控制)


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


def _parse_baseflow(raw):
    """v0.6.1: 解析 simulation.baseflow 节点 (None/空 → None=禁用)"""
    if not isinstance(raw, dict) or not raw:
        return None
    return BaseflowConfig(
        D_max=raw.get('D_max'),
        D_s=raw.get('D_s'),
        n_base=raw.get('n_base'),
        theta_c=raw.get('theta_c', 'auto'))


def _parse_lateral(raw):
    """v0.6.1: 解析 simulation.lateral 节点 (None/空 → None=禁用)"""
    if not isinstance(raw, dict) or not raw:
        return None
    k_lat = raw.get('k_lat')
    if isinstance(k_lat, list):
        k_lat = list(k_lat)
    return LateralConfig(
        f_slope=raw.get('f_slope'),
        k_lat=k_lat)


def _parse_companion(raw):
    """v0.7.0: 解析 simulation.companion 节点 (缺省/空 → 默认启用)

    与 baseflow/lateral 不同: companion 缺省 = 启用 (D3 为 v0.7.0 主线),
    显式 enable: false 才完全回退 v0.6.1。
    """
    if not isinstance(raw, dict):
        raw = {}
    return CompanionConfig(
        enable=raw.get('enable', True),
        bypass_no3_carry=raw.get('bypass_no3_carry', True),
        bs_high=raw.get('bs_high', 30.0),
        bs_low=raw.get('bs_low', 10.0),
        inert_anion=raw.get('inert_anion', 'An'),
        nh4_exchange=raw.get('nh4_exchange', True))


def _parse_weathering(raw):
    """v0.7.0: 解析 simulation.weathering 节点 (缺省/空 → 默认不启用)"""
    if not isinstance(raw, dict):
        raw = {}
    degrade = raw.get('degrade_minerals', []) or []
    return WeatheringConfig(
        enable=raw.get('enable', False),
        rate_molc_ha_yr=raw.get('rate_molc_ha_yr', 500.0),
        ca_frac=raw.get('ca_frac', 0.5),
        mg_frac=raw.get('mg_frac', 0.3),
        k_frac=raw.get('k_frac', 0.2),
        activation_energy_kJ=raw.get('activation_energy_kJ', 40.0),
        degrade_minerals=list(degrade))


def _parse_charge_pairing(raw):
    """v0.7.x (工单77): 解析 simulation.charge_pairing 节点 (缺省 → 默认启用)

    与 companion 不同: charge pairing 缺省 = 启用 (裸注入电荷不平衡是
    施肥碱化根因, 2026-08-21 实测), 显式 enable: false 才回退裸注入。
    """
    if not isinstance(raw, dict):
        raw = {}
    return ChargePairingConfig(
        enable=raw.get('enable', True),
        anion=raw.get('anion', 'An'))


def _parse_base_leaching(raw):
    """v0.7.x (工单80): 解析 simulation.base_leaching 节点 (缺省 → 默认启用)

    全情景启用 (Q3=C, 含 natural 由 BS 分级自然降权); 显式 enable: false
    即工单 80 前基线 (A/B 对照, 供 natural 30y 轨迹叠加对比)。
    """
    if not isinstance(raw, dict):
        raw = {}
    return BaseLeachingConfig(
        enable=raw.get('enable', True),
        anion=raw.get('anion', 'An'),
        bs_high=raw.get('bs_high', 30.0),
        bs_low=raw.get('bs_low', 10.0),
        c_floor_mmol_L=raw.get('c_floor_mmol_L', 0.0))


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
                # v0.5.3: Horton 废弃清理 — infiltration_initial/steady (f0/fc)
                # 残留配置显式报错 (breaking change 明示, 先例 surface_infiltration_coeff)
                if 'infiltration_initial' in item or 'infiltration_steady' in item:
                    raise ValueError(
                        "[layer_overrides infiltration_initial/infiltration_steady "
                        "参数存在问题: v0.5.3 已废弃 (Horton 入渗移除, Green-Ampt 替代), "
                        "请移除这些字段, 请确认后再输入]")
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
                initial_psi_cm=s.get('initial_psi_cm', INITIAL_PSI_CM),
                event_driven=s.get('event_driven', False),
                baseflow=_parse_baseflow(s.get('baseflow')),
                lateral=_parse_lateral(s.get('lateral')),
                companion=_parse_companion(s.get('companion')),
                weathering=_parse_weathering(s.get('weathering')),
                charge_pairing=_parse_charge_pairing(s.get('charge_pairing')),
                base_leaching=_parse_base_leaching(s.get('base_leaching'))
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
                temp_increase_rate=c.get('temp_increase_rate', 0.05),
                latitude=c.get('latitude', DEFAULT_LATITUDE),
                pet_method=c.get('pet_method', 'oudin'),
                pet_monthly_climate=c.get('pet_monthly_climate'),
                pet_correction_factor=(c.get('pet_correction_factor')
                                       or [1.0] * 12),
                diurnal_range_deg=c.get('diurnal_range_deg',
                                        DEFAULT_DIURNAL_RANGE)
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
                variables=o.get('variables', config.output.variables),
                event_output=o.get('event_output', False)
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
        """验证配置参数合法性 (2026-09-02 候选5: 逻辑迁 src/config_validation.py)

        薄委托: 全部规则 (simulation/climate/soil_data/precip_chemistry/
        layer_overrides/baseflow/lateral/companion/weathering/base_leaching)
        迁至 src.config_validation.validate_config 纯函数, 零 ConfigManager
        状态依赖。唯一保留的副作用: 创建输出目录 (运行时行为, 非校验)。
        """
        validate_config(self.config)
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



