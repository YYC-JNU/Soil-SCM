"""
模块: scenario_controller.py
功能: 情景控制器，决定每月的干预操作

输入: 情景类型、当前年月、配置参数
输出: 当月操作指令 (施肥/施石灰)

说明: 气候修正 (降水/温度递增) 由 climate_forcing 生成逐月序列时承担,
      不通过 MonthlyAction 传递 (T02: 移除曾存在但从未生效的修正字段)。
"""

from dataclasses import dataclass
from typing import List


@dataclass
class MonthlyAction:
    """月度操作指令 (施肥/石灰干预; 气候修正由气候强迫承担, 不在此列)"""
    apply_fertilizer: bool = False
    # 各肥料施用量 (kg/ha/次, 按元素计)
    n_amount: float = 0.0        # 氮 (N)
    p2o5_amount: float = 0.0     # 磷 (P2O5)
    k2o_amount: float = 0.0      # 钾 (K2O)
    mgo_amount: float = 0.0      # 镁 (MgO)
    znso4_amount: float = 0.0    # 硫酸锌 (ZnSO4)

    apply_lime: bool = False
    lime_amount: float = 0.0             # kg CaO/ha/次


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

        # 解析施肥月份与各肥料量 (每次施用量 kg/ha)
        self.apply_months = fertilizer_config.get('apply_months', [3, 6, 9])
        self.n_amount = fertilizer_config.get('n', 12.0)
        self.p2o5_amount = fertilizer_config.get('p2o5', 4.0)
        self.k2o_amount = fertilizer_config.get('k2o', 9.0)
        self.mgo_amount = fertilizer_config.get('mgo', 3.0)
        self.znso4_amount = fertilizer_config.get('znso4', 1.0)

        # 石灰施用月份与量 (kg CaO/ha/次)
        self.lime_months = lime_config.get('apply_months', [3, 6, 9])
        self.lime_amount = lime_config.get('amount_per_apply', 45.0)

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

        # 情景1: 定期施肥 (全部肥料 3/6/9 月各一次)
        if self.scenario == 'fertilizer':
            if month in self.apply_months:
                action.apply_fertilizer = True
                action.n_amount = self.n_amount
                action.p2o5_amount = self.p2o5_amount
                action.k2o_amount = self.k2o_amount
                action.mgo_amount = self.mgo_amount
                action.znso4_amount = self.znso4_amount

        # 情景2: 施肥 + 石灰
        elif self.scenario == 'fertilizer_lime':
            if month in self.apply_months:
                action.apply_fertilizer = True
                action.n_amount = self.n_amount
                action.p2o5_amount = self.p2o5_amount
                action.k2o_amount = self.k2o_amount
                action.mgo_amount = self.mgo_amount
                action.znso4_amount = self.znso4_amount

            if month in self.lime_months:
                action.apply_lime = True
                action.lime_amount = self.lime_amount

        # 情景3: 降水增加 (已在 climate_forcing 中处理)
        elif self.scenario == 'precip_increase':
            pass  # 降水修正已在 ClimateForcing 中实现

        # 情景4: 温度增加 (已在 climate_forcing 中处理)
        elif self.scenario == 'temp_increase':
            pass  # 温度修正已在 ClimateForcing 中实现

        return action

    def print_scenario_info(self):
        """打印情景信息"""
        print(f"\n情景: {self.scenario}")
        if self.scenario == 'fertilizer':
            print(f"  施肥月份: {self.apply_months}")
            print(f"  氮肥: {self.n_amount} kg N/ha/次")
            print(f"  磷肥: {self.p2o5_amount} kg P2O5/ha/次")
            print(f"  钾肥: {self.k2o_amount} kg K2O/ha/次")
            print(f"  镁肥: {self.mgo_amount} kg MgO/ha/次")
            print(f"  硫酸锌: {self.znso4_amount} kg ZnSO4/ha/次")
        elif self.scenario == 'fertilizer_lime':
            print(f"  施肥月份: {self.apply_months}")
            print(f"  石灰月份: {self.lime_months}")
            print(f"  石灰量: {self.lime_amount} kg CaO/ha/次")
