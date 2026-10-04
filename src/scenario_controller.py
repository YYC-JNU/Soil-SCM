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

import copy


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


def surface_scoped(action):
    """v0.7.13 (工单99·B2′ / 工单98·W4 改写): 表层化操作指令 — 石灰/施肥仅表层 L1

    【为什么】石灰与施肥是**表面撒施**干预（USERGUIDE §4.4「生石灰（CaO）
    施入中和酸性」「石灰月份 3/6/9」），只作用于表层。但多层编排
    （`phreeqc_engine._run_multi_layer_events`）把**同一个** `MonthlyAction`
    传给每一层的 `run_event_step`，而 `build_phreeqc_input` 对
    `apply_lime`/`apply_fertilizer` **无 layer 门控** ⇒ 实际注入了全部 4 层
    = **4× 剂量 + 直施深层 L2~L4**。
    对照：`surface_acid_eq`（引擎 :1064，`i == 0`）与 `skip_nitrification`
    （:1060，`i > 0`）**均已显式层门控** ⇒ 石灰/施肥属**漏加门控**。

    【后果（dev 只读归因，证据级）】深层获得本地碱/盐基源 ⇒ 深层溶液
    Ca 顶到 0.5 mol/L（盐水态）⇒ Q6 浓度钳制（`CONC_WARN`）→ `E_base`
    腔回路 ⇒ L4 交换相一年内翻转、pH 崩到 ~2.1（D7）。
    全文：`.scratch/soil-scm-overview/dev-notes/W4_LAYER_GATING_ROOTCAUSE.md`。

    【语义】返回**新对象**（`copy.copy`；**绝不就地改共享 action**，否则会污染
    同一月的后续层、以及后续月份复用同一对象的调用方）：
      - `apply_lime`/`apply_fertilizer` → False
      - `lime_amount` 及各肥料量 → 0.0（防未来新增路径绕过 `apply_*` 门控读取）
    其余字段原样保留。

    【A/B】`PhreeqcEngine(amendments_surface_only=False)`（或配置
    `simulation.amendments_surface_only: false`）= 旧「逐层注入」行为（对照）。
    """
    if action is None:
        return None
    scoped = copy.copy(action)
    for flag in ('apply_lime', 'apply_fertilizer'):
        if hasattr(scoped, flag):
            setattr(scoped, flag, False)
    for fld in ('lime_amount', 'n_amount', 'p2o5_amount', 'k2o_amount',
                'mgo_amount', 'znso4_amount'):
        if hasattr(scoped, fld):
            setattr(scoped, fld, 0.0)
    return scoped


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
