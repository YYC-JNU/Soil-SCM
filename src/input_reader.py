"""
模块: input_reader.py
功能: 读取土壤普查数据和交换性阳离子数据

输入: CSV 数据文件路径
输出: SoilProfile 对象
"""

import pandas as pd
import numpy as np
import json
import copy
from pathlib import Path
from dataclasses import dataclass
from src.logging_config import get_logger

logger = get_logger("input_reader")
from typing import Optional


@dataclass
class SoilProfile:
    """土壤剖面数据对象"""
    # 基本物理性质
    ph: float                    # 初始 pH
    organic_matter: float        # 有机质含量 (g/kg)
    cec: float                   # 阳离子交换量 (cmol(+)/kg)
    bulk_density: float          # 土壤容重 (g/cm³)
    area: float                  # 耕地面积 (ha)
    effective_depth: float       # 有效土层厚度 (cm)

    # 有效养分
    available_p: float           # 有效磷 (mg/kg)
    available_k: float           # 速效钾 (mg/kg)

    # 质地
    texture: str                 # 质地名称
    sand_pct: float              # 砂粒 (%)
    silt_pct: float              # 粉粒 (%)
    clay_pct: float              # 黏粒 (%)

    # 交换性阳离子 (cmol(+)/kg)
    exch_ca: float = 0.0
    exch_mg: float = 0.0
    exch_k: float = 0.0
    exch_na: float = 0.0
    exch_al: float = 0.0
    exch_h: float = 0.0

    # v0.5.0 水文 (逐层土壤水文盒子模型)
    ksat: float = 0.0                   # 层间排水上限 (cm/day, v0.5.2 起仅 LayerCascade 用)
    ksat_surface: float = 0.0           # v0.5.2: 基质导水率 (cm/day, 仅 Green-Ampt 地表入渗)

    # v0.5.3 VGM 水分特征参数 (D8 三级优先级: None=未显式 → clay_pct 回归 → 红壤兜底)
    vgm_theta_r: Optional[float] = None   # 残余含水量 θ_r (m³/m³)
    vgm_alpha: Optional[float] = None     # 进气值倒数 α (1/cm)
    vgm_n: Optional[float] = None         # 孔隙分布指数 n (>1)

    # 衍生量
    @property
    def base_saturation(self) -> float:
        """盐基饱和度 (%)"""
        total_base = self.exch_ca + self.exch_mg + self.exch_k + self.exch_na
        if self.cec > 0:
            return total_base / self.cec * 100.0
        return 0.0

    @property
    def soil_mass_per_ha(self) -> float:
        """单位面积土壤质量 (kg/ha)"""
        # 容重(g/cm³) × 深度(cm) × 10000 m²/ha × 1000000 cm²/m² / 1000 g/kg
        depth_m = self.effective_depth / 100.0  # cm → m
        volume_m3 = depth_m * 10000.0           # m³/ha
        mass_kg = self.bulk_density * 1000.0 * volume_m3  # kg/ha
        return mass_kg

    @property
    def porosity(self) -> float:
        """孔隙度估算"""
        # 假设土壤颗粒密度 2.65 g/cm³
        return 1.0 - self.bulk_density / 2.65


class InputReader:
    """输入数据读取器"""

    # 质地编码表路径 (v0.2.3: config 内联质地编码 → 中文名称)
    TEXTURE_CODE_PATH = "config/texture_code.json"

    def __init__(self, soil_file: str, exchangeable_file: str):
        self.soil_file = Path(soil_file)
        self.exchangeable_file = Path(exchangeable_file)
        self.texture_codes = self._load_texture_codes()

    def _load_texture_codes(self) -> dict:
        """加载质地编码表: {编码数字: 中文名称}

        返回:
            dict: 编码数字(int) → 质地中文名称(str)
        """
        path = Path(self.TEXTURE_CODE_PATH)
        if not path.exists():
            logger.warning("质地编码表 %s 不存在, 质地编码转换不可用", path)
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {int(k): v["name"] for k, v in data.get("texture_codes", {}).items()}

    @staticmethod
    def _all_minus_one(values: dict) -> bool:
        """判断字段值 dict 是否全部为 -1 (空 dict 视为全部 -1)

        参数:
            values: 字段名 → 值的 dict
        返回:
            bool: True=全部为 -1 或为空 (回退 CSV)
        """
        return all(v == -1 for v in values.values()) if values else True

    def read_soil_survey(self) -> dict:
        """读取土壤普查数据"""
        if not self.soil_file.exists():
            logger.warning("土壤普查文件 %s 不存在，使用默认值", self.soil_file)
            return self._default_soil_survey()

        df = pd.read_csv(self.soil_file)

        # 假设只有一行数据(单点模式)
        if len(df) == 0:
            return self._default_soil_survey()

        row = df.iloc[0]
        return {
            'ph': float(row.get('pH', 5.0)),
            'organic_matter': float(row.get('有机质_g_kg', 20.0)),
            'cec': float(row.get('CEC_cmol_kg', 12.0)),
            'bulk_density': float(row.get('容重_g_cm3', 1.2)),
            'area': float(row.get('耕地面积_ha', 1.0)),
            'effective_depth': float(row.get('有效土层厚度_cm', 30.0)),
            'available_p': float(row.get('有效磷_mg_kg', 15.0)),
            'available_k': float(row.get('速效钾_mg_kg', 100.0)),
            'texture': str(row.get('质地', '壤土')),
            'sand_pct': float(row.get('砂粒_pct', 40.0)),
            'silt_pct': float(row.get('粉粒_pct', 35.0)),
            'clay_pct': float(row.get('黏粒_pct', 25.0)),
        }

    def read_exchangeable_ions(self) -> dict:
        """读取交换性阳离子数据"""
        if not self.exchangeable_file.exists():
            logger.warning("交换性阳离子文件不存在，使用估算值")
            return self._default_exchangeable()

        df = pd.read_csv(self.exchangeable_file)
        if len(df) == 0:
            return self._default_exchangeable()

        row = df.iloc[0]
        return {
            'exch_ca': float(row.get('交换性Ca_cmol_kg', 3.0)),
            'exch_mg': float(row.get('交换性Mg_cmol_kg', 1.5)),
            'exch_k': float(row.get('交换性K_cmol_kg', 0.5)),
            'exch_na': float(row.get('交换性Na_cmol_kg', 0.2)),
            'exch_al': float(row.get('交换性Al_cmol_kg', 2.0)),
            'exch_h': float(row.get('交换性H_cmol_kg', 1.0)),
        }

    def build_soil_profile(self, survey_config: dict = None,
                           exchangeable_config: dict = None) -> SoilProfile:
        """构建完整的土壤剖面对象 (v0.2.3: 支持 config 内联字段)

        参数:
            survey_config: config 中 soil_data.survey 字段值 dict。
                全部字段为 -1 (或省略/空 dict) → 回退读取 CSV 默认值;
                全部字段为有效值 → 覆盖 CSV (混合填写已由 config_manager 拦截报错)。
            exchangeable_config: config 中 soil_data.exchangeable_ions 字段值 dict。
                逻辑同上。

        返回:
            SoilProfile 对象
        """
        survey_config = survey_config or {}
        exchangeable_config = exchangeable_config or {}

        # ---- 土壤普查块: config 全 -1 → 回退 CSV ----
        if self._all_minus_one(survey_config):
            # Q14: 全 -1 时 CSV 必须存在
            if not self.soil_file.exists():
                raise FileNotFoundError(
                    f"survey 参数全部为 -1 (需读取 CSV 默认值), "
                    f"但土壤普查文件不存在: {self.soil_file}")
            survey = self.read_soil_survey()
        else:
            survey = dict(survey_config)
            # 质地编码数字 → 中文名称 (config_manager 已校验编码合法性, 此处兜底)
            texture_code = survey.get('texture')
            if isinstance(texture_code, int) and texture_code != -1:
                if texture_code in self.texture_codes:
                    survey['texture'] = self.texture_codes[texture_code]
                else:
                    raise ValueError(
                        f"['texture' 参数存在问题: 编码 {texture_code} 无效, "
                        f"请确认后再输入]")

        # ---- 交换性阳离子块: config 全 -1 → 回退 CSV ----
        if self._all_minus_one(exchangeable_config):
            # Q14: 全 -1 时 CSV 必须存在
            if not self.exchangeable_file.exists():
                raise FileNotFoundError(
                    f"exchangeable_ions 参数全部为 -1 (需读取 CSV 默认值), "
                    f"但交换性阳离子文件不存在: {self.exchangeable_file}")
            exch = self.read_exchangeable_ions()
        else:
            exch = dict(exchangeable_config)

        return SoilProfile(
            ph=survey['ph'],
            organic_matter=survey['organic_matter'],
            cec=survey['cec'],
            bulk_density=survey['bulk_density'],
            area=survey['area'],
            effective_depth=survey['effective_depth'],
            available_p=survey['available_p'],
            available_k=survey['available_k'],
            texture=survey['texture'],
            sand_pct=survey['sand_pct'],
            silt_pct=survey['silt_pct'],
            clay_pct=survey['clay_pct'],
            exch_ca=exch['exch_ca'],
            exch_mg=exch['exch_mg'],
            exch_k=exch['exch_k'],
            exch_na=exch['exch_na'],
            exch_al=exch['exch_al'],
            exch_h=exch['exch_h'],
        )

    def apply_layer_override(self, base_profile, override,
                             depth: float) -> SoilProfile:
        """按层覆盖构建新 SoilProfile (L6, v0.4.0)

        部分覆盖语义: override 中为 None 的字段回退 base_profile (深拷贝)。
        effective_depth 由 layer_depths[i] 派生 (层厚 = 缓冲库容量乘子)。

        参数:
            base_profile: 全局默认 SoilProfile
            override: LayerOverrideConfig (src.config_manager) 或具有
                相同字段名的对象/dict (ph/organic_matter/cec/bulk_density/
                exch_ca/exch_mg/exch_k/exch_na/exch_al/exch_h)
            depth: 该层厚度 (cm)
        返回:
            SoilProfile: 覆盖后的新对象 (不影响 base_profile)
        """
        prof = copy.deepcopy(base_profile)
        prof.effective_depth = depth
        for fld in ('ph', 'organic_matter', 'cec', 'bulk_density',
                    'exch_ca', 'exch_mg', 'exch_k', 'exch_na',
                    'exch_al', 'exch_h'):
            v = getattr(override, fld, None)
            if v is not None:
                setattr(prof, fld, v)
        # v0.5.0 水文: 水文字段应用 (clay_pct 已有; ksat)
        # v0.5.2: +ksat_surface (Green-Ampt 基质导水率)
        # v0.5.3: +vgm_theta_r/vgm_alpha/vgm_n (VGM 显式参数, D8 最高优先级)
        for fld in ('clay_pct', 'ksat', 'ksat_surface',
                    'vgm_theta_r', 'vgm_alpha', 'vgm_n'):
            v = getattr(override, fld, None)
            if v is not None:
                setattr(prof, fld, v)
        # v0.5.0 水文: 孔隙度覆盖 → 反推容重 ρ=2.65(1−φ) (覆盖 bulk_density;
        # porosity property = 1−ρ/2.65 自然返回给定 φ, 保持物理自洽)
        porosity = getattr(override, 'porosity', None)
        if porosity is not None:
            prof.bulk_density = 2.65 * (1.0 - porosity)
        return prof

    def _default_soil_survey(self) -> dict:
        """南方红壤默认普查数据"""
        return {
            'ph': 5.0,
            'organic_matter': 20.0,       # g/kg
            'cec': 12.0,                  # cmol(+)/kg
            'bulk_density': 1.2,          # g/cm³
            'area': 1.0,                  # ha
            'effective_depth': 30.0,      # cm
            'available_p': 15.0,          # mg/kg
            'available_k': 100.0,         # mg/kg
            'texture': '壤土',
            'sand_pct': 35.0,
            'silt_pct': 40.0,
            'clay_pct': 25.0,
        }

    def _default_exchangeable(self) -> dict:
        """默认交换性阳离子 (南方红壤典型值)"""
        return {
            'exch_ca': 3.0,
            'exch_mg': 1.5,
            'exch_k': 0.5,
            'exch_na': 0.2,
            'exch_al': 2.0,
            'exch_h': 1.0,
        }

