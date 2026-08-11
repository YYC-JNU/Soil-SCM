"""
模块: scenario_controller.py
功能: 情景控制器，决定每月的干预操作

输入: 情景类型、当前年月、配置参数
输出: 当月操作指令 (施肥/施石灰/降水修正/温度修正)
"""

from dataclasses import dataclass
from typing import List


@dataclass
class MonthlyAction:
    """月度操作指令"""
    apply_fertilizer: bool = False
    fertilizer_amount: float = 0.0       # kg/ha
    fertilizer_type: str = "urea"

    apply_lime: bool = False
    lime_amount: float = 0.0             # kg/ha

    precip_factor: float = 1.0           # 降水修正系数
    temp_offset: float = 0.0             # 温度修正 (°C)


class ScenarioController:
    """情景控制器"""

    def __init__(self, scenario: str, fertilizer_config: dict,
                 lime_config: dict):
        """
        参数:
            scenario: 情景类型
            fertilizer_config: 肥料配置字典
            lime_config: 石灰配置字典
        """
        self.scenario = scenario
        self.fert_config = fertilizer_config
        self.lime_config = lime_config

        # 解析施肥月份
        self.apply_months = fertilizer_config.get('apply_months', [3, 6, 9])
        self.annual_fert_amount = fertilizer_config.get('annual_amount', 300.0)
        self.fert_type = fertilizer_config.get('type', 'urea')

        # 石灰施用月份
        self.lime_month = lime_config.get('apply_month', 1)
        self.annual_lime_amount = lime_config.get('annual_amount', 1000.0)

    def get_action(self, year: int, month: int) -> MonthlyAction:
        """获取指定年月的操作指令

        参数:
            year: 年 (1-indexed, 1=第1年)
            month: 月 (1-indexed, 1=1月)

        返回:
            MonthlyAction 对象
        """
        action = MonthlyAction()

        # 情景0: 自然状态 - 无任何干预
        if self.scenario == 'natural':
            return action

        # 情景1: 定期施肥
        if self.scenario == 'fertilizer':
            if month in self.apply_months:
                action.apply_fertilizer = True
                action.fertilizer_amount = self._calc_fert_per_application()
                action.fertilizer_type = self.fert_type

        # 情景2: 施肥 + 石灰
        elif self.scenario == 'fertilizer_lime':
            if month in self.apply_months:
                action.apply_fertilizer = True
                action.fertilizer_amount = self._calc_fert_per_application()
                action.fertilizer_type = self.fert_type

            if month == self.lime_month:
                action.apply_lime = True
                action.lime_amount = self.annual_lime_amount

        # 情景3: 降水增加 (已在 climate_forcing 中处理)
        elif self.scenario == 'precip_increase':
            pass  # 降水修正已在 ClimateForcing 中实现

        # 情景4: 温度增加 (已在 climate_forcing 中处理)
        elif self.scenario == 'temp_increase':
            pass  # 温度修正已在 ClimateForcing 中实现

        return action

    def _calc_fert_per_application(self) -> float:
        """计算每次施肥量 (kg/ha)"""
        n_apps = len(self.apply_months)
        if n_apps > 0:
            return self.annual_fert_amount / n_apps
        return 0.0

    def print_scenario_info(self):
        """打印情景信息"""
        print(f"\n情景: {self.scenario}")
        if self.scenario == 'fertilizer':
            print(f"  施肥月份: {self.apply_months}")
            print(f"  年施肥量: {self.annual_fert_amount} kg/ha")
            print(f"  每次施肥: {self._calc_fert_per_application():.1f} kg/ha")
        elif self.scenario == 'fertilizer_lime':
            print(f"  施肥月份: {self.apply_months}")
            print(f"  石灰月份: {self.lime_month}")
            print(f"  石灰量: {self.annual_lime_amount} kg/ha")
