"""
模块: precip_chemistry.py
功能: 降水化学组成加载与浓度换算 (Q7 修复)

输入: 降水化学配置文件 (JSON), 默认 config/precip_chemistry_default.json
输出: 每月降水带入溶液的各离子摩尔量 (mol), 供 PHREEQC REACTION 使用

换算逻辑 (2026-08-12 确认, 数据源: 《2025年广东省生态环境状况公报》):
  1. JSON 中离子以当量浓度占比 (percent) 存储
  2. 总当量浓度由 pH 与 H+ 占比自洽推算:
       total_eq (eq/L) = 10^(-pH) / (H_frac/100)
  3. 某离子摩尔浓度 (mol/L) = total_eq x (frac/100) / 离子电荷数
  4. 每月输入量 (mol) = 浓度 (mol/L) x 入渗水量 (L)

参考文献:
  广东省生态环境厅. 2025年广东省生态环境状况公报.
"""

import json
from pathlib import Path
from typing import Dict, Optional


class PrecipChemistry:
    """降水化学组成与换算"""

    # PHREEQC 物种名映射 (JSON 键 -> REACTION 物种)
    SPECIES_MAP = {
        "Cl": "Cl-",
        "SO4": "SO4-2",
        "NO3": "NO3-",
        "F": "F-",
        "Ca": "Ca+2",
        "NH4": "NH4+",
        "Na": "Na+",
        "Mg": "Mg+2",
        "K": "K+",
        "H": "H+",
    }

    # 离子电荷数
    CHARGE = {
        "Cl": 1, "SO4": 2, "NO3": 1, "F": 1,
        "Ca": 2, "NH4": 1, "Na": 1, "Mg": 2, "K": 1, "H": 1,
    }

    def __init__(self, filepath: Optional[str] = None,
                 data: Optional[dict] = None):
        """
        参数:
            filepath: 降水化学 JSON 文件路径
            data: 直接传入已加载的 dict (优先于 filepath)
        """
        if data is not None:
            self.data = data
        else:
            self.filepath = filepath or "config/precip_chemistry_default.json"
            self.data = self._load()

    def _load(self) -> dict:
        fp = Path(self.filepath)
        if not fp.exists():
            raise FileNotFoundError(f"降水化学配置文件不存在: {fp}")
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)

    @property
    def ph(self) -> float:
        return float(self.data.get("pH", 5.75))

    @property
    def ions(self) -> dict:
        return self.data.get("ions", {})

    def total_eq_concentration(self) -> float:
        """总当量浓度 (eq/L), 由 pH 与 H+ 占比自洽推算"""
        h_frac = self.ions.get("H", 1.0) / 100.0
        if h_frac <= 0:
            raise ValueError("降水化学中 H+ 占比必须大于 0")
        return 10.0 ** (-self.ph) / h_frac

    def ion_mol_per_l(self) -> Dict[str, float]:
        """各离子摩尔浓度 (mol/L)"""
        total_eq = self.total_eq_concentration()
        out = {}
        for ion, frac in self.ions.items():
            charge = self.CHARGE.get(ion, 1)
            out[ion] = total_eq * (frac / 100.0) / charge
        return out

    def reaction_amounts(self, water_volume_L: float) -> Dict[str, float]:
        """降水入渗水量对应的各物质摩尔量 (mol), 供 REACTION 使用

        参数:
            water_volume_L: 当月降水入渗进入溶液的水量 (L)
        返回:
            dict: PHREEQC 物种名 -> 摩尔量 (mol)
        """
        conc = self.ion_mol_per_l()
        amounts = {}
        for ion, c in conc.items():
            sp = self.SPECIES_MAP[ion]
            amounts[sp] = c * water_volume_L
        return amounts

    def print_summary(self):
        """打印降水化学摘要"""
        total_eq = self.total_eq_concentration()
        conc = self.ion_mol_per_l()
        print("\n降水化学组成:")
        print(f"  pH: {self.ph}")
        print(f"  总当量浓度: {total_eq:.4e} eq/L")
        print(f"  {'离子':<6}{'占比%':<8}{'mol/L':<14}{'PHREEQC物种'}")
        for ion, frac in self.ions.items():
            print(f"  {ion:<6}{frac:<8.1f}{conc[ion]:<14.4e}{self.SPECIES_MAP[ion]}")
