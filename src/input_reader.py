"""
模块: input_reader.py
功能: 读取土壤普查数据和交换性阳离子数据

输入: CSV 数据文件路径
输出: SoilProfile 对象
"""

import pandas as pd
import numpy as np
from pathlib import Path
from dataclasses import dataclass
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

    def __init__(self, soil_file: str, exchangeable_file: str):
        self.soil_file = Path(soil_file)
        self.exchangeable_file = Path(exchangeable_file)

    def read_soil_survey(self) -> dict:
        """读取土壤普查数据"""
        if not self.soil_file.exists():
            print(f"[WARNING] 土壤普查文件 {self.soil_file} 不存在，使用默认值")
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
            print(f"[WARNING] 交换性阳离子文件不存在，使用估算值")
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

    def build_soil_profile(self) -> SoilProfile:
        """构建完整的土壤剖面对象"""
        survey = self.read_soil_survey()
        exch = self.read_exchangeable_ions()

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

