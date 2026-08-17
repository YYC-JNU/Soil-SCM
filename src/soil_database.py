"""
模块: soil_database.py
功能: 土壤矿物数据库读取 (支持 JSON 和 WRF TBL 格式)

输入: 土壤类型标识符
输出: 矿物组成、CO2分压、参考信息
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from src.logging_config import get_logger

logger = get_logger("soil_database")


@dataclass
class MineralInfo:
    """单个矿物信息"""
    name: str
    mass_fraction: float       # 质量分数
    molar_mass: float          # 摩尔质量 (g/mol)
    specific_area: float       # 比表面积 (m2/g)


@dataclass
class SoilTypeInfo:
    """土壤类型完整信息"""
    name: str
    description: str
    ph_range: Tuple[float, float]
    minerals: Dict[str, MineralInfo]
    cec_range: Tuple[float, float]
    om_range: Tuple[float, float]
    pCO2: float
    pCO2_beta: float
    references: list


class SoilDatabase:
    """土壤矿物数据库管理器"""

    def __init__(self, json_path: str = "config/soil_mineral_db.json",
                 tbl_path: str = "config/soil_mineral.tbl"):
        self.json_path = Path(json_path)
        self.tbl_path = Path(tbl_path)
        self._data = {}
        self._load()

    def _load(self):
        """加载数据库 (优先 JSON，fallback TBL)"""
        if self.json_path.exists():
            self._load_json()
        elif self.tbl_path.exists():
            self._load_tbl()
        else:
            raise FileNotFoundError(
                f"未找到矿物数据库: {self.json_path} 或 {self.tbl_path}")

    def _load_json(self):
        """从 JSON 文件加载"""
        with open(self.json_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)

        for soil_type, info in raw.items():
            minerals = {}
            for mname, frac in info['dominant_minerals'].items():
                # JSON中只有质量分数，摩尔质量和比表面积用默认值
                minerals[mname] = MineralInfo(
                    name=mname,
                    mass_fraction=frac,
                    molar_mass=self._get_default_molar_mass(mname),
                    specific_area=self._get_default_specific_area(mname)
                )

            self._data[soil_type] = SoilTypeInfo(
                name=soil_type,
                description=info.get('description', ''),
                ph_range=tuple(info.get('pH_range', [4.0, 9.0])),
                minerals=minerals,
                cec_range=tuple(info.get('cation_exchange_capacity_range',
                                         [5, 50])),
                om_range=tuple(info.get('organic_matter_content_range',
                                        [0.5, 10])),
                pCO2=info.get('soil_CO2_pCO2_atm', 0.015),
                pCO2_beta=info.get('soil_CO2_beta', 0.05),
                references=info.get('references', [])
            )

    def _load_tbl(self):
        """从 WRF TBL 风格文件加载"""
        if not self.tbl_path.exists():
            raise FileNotFoundError(f"TBL文件不存在: {self.tbl_path}")

        current_soil = None
        current_minerals = {}

        with open(self.tbl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过注释和空行
                if not line or line.startswith('#'):
                    continue

                # 检测新土壤类型开始
                if line.startswith('&SOIL_MINERAL'):
                    current_soil = line.split()[1]
                    current_minerals = {}
                    continue

                # 检测结束标记
                if line == '/':
                    if current_soil:
                        self._data[current_soil] = SoilTypeInfo(
                            name=current_soil,
                            description=f"TBL定义: {current_soil}",
                            ph_range=(4.0, 9.0),
                            minerals=current_minerals,
                            cec_range=(5, 50),
                            om_range=(0.5, 10),
                            pCO2=0.015,
                            pCO2_beta=0.05,
                            references=[]
                        )
                    current_soil = None
                    continue

                # 解析矿物行: name fraction molar_mass specific_area
                parts = line.split()
                if len(parts) >= 4 and current_soil:
                    mname = parts[0]
                    frac = float(parts[1])
                    molar_mass = float(parts[2])
                    spec_area = float(parts[3])
                    current_minerals[mname] = MineralInfo(
                        name=mname,
                        mass_fraction=frac,
                        molar_mass=molar_mass,
                        specific_area=spec_area
                    )

    def _get_default_molar_mass(self, mineral_name: str) -> float:
        """获取矿物默认摩尔质量"""
        molar_masses = {
            'kaolinite': 258.16,
            'goethite': 88.85,
            'hematite': 159.69,
            'quartz': 60.08,
            'gibbsite': 78.00,
            'illite': 398.30,
            'montmorillonite': 540.00,
            'anatase': 79.87,
            'calcite': 100.09,
            'feldspar': 278.30,
        }
        return molar_masses.get(mineral_name, 100.0)

    def _get_default_specific_area(self, mineral_name: str) -> float:
        """获取矿物默认比表面积"""
        areas = {
            'kaolinite': 10.0,
            'goethite': 50.0,
            'hematite': 20.0,
            'quartz': 0.5,
            'gibbsite': 15.0,
            'illite': 30.0,
            'montmorillonite': 700.0,
            'anatase': 5.0,
            'calcite': 1.0,
            'feldspar': 2.0,
        }
        return areas.get(mineral_name, 10.0)

    def get_soil_info(self, soil_type: str) -> SoilTypeInfo:
        """根据土壤类型获取完整信息"""
        if soil_type not in self._data:
            available = list(self._data.keys())
            raise KeyError(
                f"土壤类型 '{soil_type}' 不在数据库中。可用类型: {available}")
        return self._data[soil_type]

    def get_minerals(self, soil_type: str) -> Dict[str, MineralInfo]:
        """获取矿物组成"""
        return self.get_soil_info(soil_type).minerals

    def get_pCO2(self, soil_type: str) -> float:
        """获取土壤CO2分压"""
        return self.get_soil_info(soil_type).pCO2

    def get_pCO2_beta(self, soil_type: str) -> float:
        """获取CO2温度响应系数"""
        return self.get_soil_info(soil_type).pCO2_beta

    def list_soil_types(self) -> list:
        """列出所有可用土壤类型"""
        return list(self._data.keys())

    def print_soil_info(self, soil_type: str):
        """打印土壤类型详细信息"""
        info = self.get_soil_info(soil_type)
        print(f"\n{'='*50}")
        print(f"土壤类型: {info.name}")
        print(f"描述: {info.description}")
        print(f"pH范围: {info.ph_range}")
        print(f"CEC范围: {info.cec_range} cmol(+)/kg")
        print(f"有机质范围: {info.om_range} %")
        print(f"土壤pCO2: {info.pCO2} atm")
        print(f"\n矿物组成:")
        print(f"  {'矿物':<20} {'质量分数':<10} {'摩尔质量':<12} {'比表面积':<10}")
        print(f"  {'-'*52}")
        for mname, minfo in info.minerals.items():
            print(f"  {mname:<20} {minfo.mass_fraction:<10.3f} "
                  f"{minfo.molar_mass:<12.2f} {minfo.specific_area:<10.1f}")
        print(f"\n参考文献:")
        for ref in info.references:
            print(f"  - {ref}")
        print(f"{'='*50}\n")


def apply_mineral_overrides(mineral_info: SoilTypeInfo,
                            overrides: Dict[str, float]) -> SoilTypeInfo:
    """矿物增量覆盖 (L6, v0.4.0): 返回覆盖后的新 SoilTypeInfo

    只替换 overrides 中指定的矿物质量分数, 未覆盖矿物保留原值; **不归一化**
    (质量分数总和 ≠ 1 时由 config 校验层警告, 覆盖意图不被归一化扭曲)。
    overrides 中出现默认矿物库不存在的矿物名 → 警告并忽略 (需摩尔质量等
    数据, 超出增量覆盖范围)。

    参数:
        mineral_info: 原始 SoilTypeInfo (默认来自 soil_mineral_db)
        overrides: {矿物名: 质量分数} 增量覆盖 dict
    返回:
        SoilTypeInfo: 覆盖后的新对象 (不影响 mineral_info)
    """
    new_minerals = {}
    for mname, minfo in mineral_info.minerals.items():
        frac = overrides.get(mname, minfo.mass_fraction)
        new_minerals[mname] = MineralInfo(
            name=mname, mass_fraction=frac,
            molar_mass=minfo.molar_mass, specific_area=minfo.specific_area)

    unknown = [m for m in overrides if m not in mineral_info.minerals]
    if unknown:
        logger.warning("矿物覆盖跳过未知矿物: %s (默认矿物库无此矿物)",
                       ", ".join(unknown))

    return SoilTypeInfo(
        name=mineral_info.name,
        description=mineral_info.description,
        ph_range=mineral_info.ph_range,
        minerals=new_minerals,
        cec_range=mineral_info.cec_range,
        om_range=mineral_info.om_range,
        pCO2=mineral_info.pCO2,
        pCO2_beta=mineral_info.pCO2_beta,
        references=mineral_info.references,
    )

