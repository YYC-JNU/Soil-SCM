# 43 — v0.5.2 Green-Ampt 表层入渗物理化 spec

**What to build:** 废弃 Horton + `surface_coeff` 非物理入渗，改为 **Green-Ampt 物理入渗**（基于基质导水率 / 湿润锋吸力 / 初始含水量）；`ksat` 拆分为 `ksat_surface`（仅地表入渗）与排水语义（仅层间排水，默认值更新）；新增 `bypass_fraction=0.2` 大孔隙优先流注入 L2（携带原始降水化学）；**硝化产酸限制在 L1**。保留 `stored_water` 状态（θ/ψ 状态迁移留待 v0.5.3）。

**Blocked by:** None — can start immediately（依赖 `docs/analysis/OPTIMIZATION_PLAN.md` §7 已定案决策 D1~D9）。

**Status:** ✅ 已落地 (2026-08-18, v0.5.2, 经工单 44~48)

**来源：** /grill-me 9 轮决策拷问（2026-08-18）+ /to-spec 综合（2026-08-18）

---

## Problem Statement

v0.5.0/v0.5.1 水文盒子模型的 4 个物理缺陷已经源码审查确认（`docs/analysis/OPTIMIZATION_PLAN.md` §7.1）。本 spec 解决其中 **缺陷 1（surface_coeff 非物理补丁）** 与 **缺陷 4 的入渗部分（Horton 经验曲线）**：

- `src/hydrology.py:73` `available = precip_mm * surface_coeff`（默认 0.75）——即使入渗能力未触顶也**人为强制 25% 降水成径流**，破坏质量守恒，是表层 pH ~6.9 基线漂移的直接推手。
- Horton `f0/fc/k` 为经验曲线，无法表达"**降雨强度 vs 土壤导水能力**"的物理竞争——超渗产流应自然产生而非靠系数限制。

同时落实专家方案三项要求（grill-me 决策 D2/D3/D6/D7）：
1. **K_s 基质导水率**（L1=7.2 cm/day），使华南暴雨（>15mm/h）自然触发超渗产流；
2. **大孔隙优先流**（`bypass_fraction=0.2`）——超过基质 K_s 的积水绕过表层直通 L2（红壤旱地"暴雨直通深层"观测），携带原始降水化学；
3. **硝化产酸限 L1**——强化表层酸化源，深层不再重复产酸。

## Solution

- **Green-Ampt 入渗**（替代 Horton + `surface_coeff`）：隐式方程
  $F - \psi_f \Delta\theta \ln\left(1 + \frac{F}{\psi_f \Delta\theta}\right) = K_s t$
  牛顿迭代求解；单场降雨强度 > 入渗能力 → 超出部分自然成为地表径流（Hortonian runoff）；`K_s` 取 `ksat_surface`（基质导水率）；`ψ_f` 默认 150mm（Rawls 1983 红壤 100~200mm）；`θ_s` = L1 孔隙度；`θ_i` 由 `stored_water` 换算（初始 50% 饱和 → θ_i = 0.5×θ_s）。
- **Ksat 字段拆分**：`ksat` 语义变为**层间排水上限**（默认值更新为 `[12.0, 1.9, 0.48, 0.05]` cm/day，LayerCascade 用）；新增 `ksat_surface`（Green-Ampt 地表入渗用，默认 `7.2` cm/day）。
- **优先流**：`simulation.bypass_fraction=0.2`（config 开放，0~1 校验）；径流水中 β=20% 作为优先流注入 **L2**，**携带原始降水化学**（非 L1 平衡溶液、非纯水）；质量守恒核算扩展。
- **硝化限 L1**：`run_monthly_multi_layer` 仅 L1 执行 `advance_nitrification`（施肥/水解/硝化/产酸），L2~L4 跳过全部氮过程（氮不随层间传递；完整氮运移留待 v0.6.0 子步长）。
- **保留 `stored_water` 状态**与现有 LayerCascade 级联逻辑（50% 饱和持水 + ksat_cap 排水），仅切换 `ksat` 语义。

## User Stories

1. 作为研究者，我希望入渗由 Green-Ampt 物理方程驱动（K_s / 湿润锋吸力 / 初始含水量），以便超渗产流**自然产生**、质量守恒。
2. 作为研究者，我希望移除 `surface_coeff` 人为系数，以便"永远 25% 降水成径流"的非物理假设不再存在。
3. 作为研究者，我希望 `K_s` 使用基质导水率（L1=7.2 cm/day），以便华南暴雨（>15mm/h）自然超过入渗能力触发产流。
4. 作为模型开发者，我希望 `ksat` 拆分为 `ksat_surface`（仅地表入渗）与排水语义（仅层间排水），以便压表层入渗的同时不误伤层间排水物理。
5. 作为研究者，我希望超过基质 K_s 的积水按 `bypass_fraction=0.2` 作为优先流注入 L2 并携带原始降水化学，以便模拟红壤旱地"暴雨直通深层"。
6. 作为模型开发者，我希望 `bypass_fraction` 通过 config 开放，以便用户按地块耕作方式（免耕/翻耕）调整。
7. 作为研究者，我希望硝化产酸（2H⁺）仅 L1 发生，以便表层酸化源强化、深层不再重复产酸。
8. 作为模型开发者，我希望 v0.5.2 保留 `stored_water` 状态，以便本阶段不引入 θ/ψ 状态迁移（改动量/风险最小，决策 D1）。
9. 作为模型开发者，我希望 `n_layers=1` 完全回退现状，以便单层基线不回归（回归护栏）。
10. 作为研究者，我希望 Green-Ampt 入渗在固定 seed 下可复现，以便结果可对比、可验证。
11. 作为模型开发者，我希望 `surface_infiltration_coeff` 字段移除且 config 出现时报错，以便 breaking change 显式化、不静默忽略。
12. 作为研究者，我希望月度输出保留 runoff/infiltration/stored_water 列并新增优先流诊断，以便验证水量守恒。

## Implementation Decisions

- **Green-Ampt 模块**（`src/hydrology.py`）：
  - 新增 `green_ampt_infiltration(precip_mm, Ks_cm_day, psi_f_mm, theta_s, theta_i, hours) -> (infiltration_mm, runoff_mm)`：牛顿迭代解隐式方程；`K_s` 单位 cm/day→mm/h 转换；场次历时保持 `EVENT_HOURS=2`。
  - 删除 `horton_event_infiltration` 与 `HORTON_DECAY_K_PER_H`；`monthly_hydrology` 改调 Green-Ampt（逐场），月入渗 = Σ场次入渗，月径流 = 月降水 − 月入渗。
  - `surface_coeff` 参数从 `horton_event_infiltration` / `monthly_hydrology` / `main._apply_hydrology_month` 全部移除。
  - `SimulationConfig.surface_infiltration_coeff` 字段**删除**；config 中出现时 ConfigManager 校验报错（breaking change 明示）。
- **Ksat 字段拆分**：
  - `SoilProfile.ksat` 语义 = 层间排水上限（LayerCascade `ksat_cap` 继续用它），默认值更新 `DEFAULT_4LAYER_KSAT=[12.0, 1.9, 0.48, 0.05]`。
  - 新增 `SoilProfile.ksat_surface`（Green-Ampt 用），默认 `DEFAULT_KSAT_SURFACE=7.2`（cm/day）。
  - `LayerOverrideConfig` 新增 `ksat_surface`（`ksat` 保留=排水语义）；`apply_layer_override` 应用两个字段。
  - `infiltration_initial` / `infiltration_steady`（f0/fc）字段**保留但不再参与入渗计算**（Horton 废弃，标记 deprecated；v0.5.3 清理）。
- **优先流 bypass**：
  - `SimulationConfig.bypass_fraction = 0.2`（0~1 校验）。
  - `main._apply_hydrology_month` 返回优先流水量（径流水量 × β）与位置（L2）；`run_monthly_multi_layer` 对 L2 额外注入优先流水量 + 原始降水化学（同 L1 入渗化学口径）。
  - 质量守恒：月降水 = L1 入渗 + 地表径流（含优先流）；优先流水量与化学计入降水总量核算（Q7 平流守恒口径扩展）。
- **硝化限 L1**：
  - `run_monthly_multi_layer` 仅 `i==0` 执行 `advance_nitrification`（施肥/水解/硝化/产酸）；`i>0` 跳过全部氮过程。
  - 行为变更 → 4 层 pH 剖面相关测试断言需同步更新。
- **输出**：`OutputWriter` 新增优先流/地表径流分离列（可选 `bypass_drainage` 诊断）；既有 infiltration/runoff/drainage/stored_water 保留。

### 测试接缝（复用既有，无新 seam）

- S1 `src/hydrology.py` 纯函数（Green-Ampt 隐式/牛顿/单场/月度分配）——先例 `test_hydrology.py`
- S2 `ConfigManager` 解析/校验（`ksat_surface`/`bypass_fraction` 新增 + `surface_infiltration_coeff` 移除报错 + 值域）——先例 `test_config_manager.py`
- S3 `SoilProfile`/`LayerOverrideConfig` 字段拆分（排水语义切换 + 新字段应用）——先例 `test_input_reader.py` / `test_layer_overrides.py`
- S4 引擎集成（优先流注入 L2 携带降水化学 + 硝化限 L1）——先例 `test_layer_overrides.py`
- S5 main 编排（Green-Ampt 月度调用 + bypass 传递 + runoff 守恒 + 单层回归护栏）——先例 `test_layer_overrides.py`

## Testing Decisions

- **好测试标准**：只测外部行为——质量守恒（入渗+径流=降水）、超渗产流触发（降雨强度>K_s 时产流）、优先流注入守恒（β×径流注入 L2 且携带化学）、硝化 L1-only（L2~L4 无产酸）、单层回归（n_layers=1 原路径）；手算独立验证 Green-Ampt 数值；不测实现细节。
- **模块测试**：hydrology（S1）/ config（S2）/ profile（S3）/ 引擎（S4）/ 编排（S5）。
- **先例**：`test_hydrology` / `test_config_manager` / `test_input_reader` / `test_layer_overrides`。
- **验证**：2 年 4 层 natural 基线对比（v0.5.1 Horton+0.75 vs v0.5.2 Green-Ampt），记录入渗量/径流量/表层 pH 变化**方向**；`tools/sensitivity_infiltration.py`（扫描 surface_coeff）改为扫描 `ksat_surface` 或标记暂停；全量 pytest 保持全绿。

## Out of Scope

- VGM 水分特征曲线与 θ/ψ 状态迁移（v0.5.3）
- Feddes ET / Oudin PET（v0.5.3）
- LayerCascade 下游接收能力重构（v0.5.3）
- OM 矿化产 CO₂ 模块（v0.5.3）
- 化学子步长拆分 / 逐场 PHREEQC（v0.6.0）
- β 旱/雨季动态调整（0.30~0.40 / 0.10~0.15，后续小版本）
- Kozeny-Carman Ksat 修正公式（后续小版本）
- 氮形态层间运移（v0.6.0）
- 单层水文（n_layers=1 保持现状，不引入）

## Further Notes

- **科学诚实**：Green-Ampt 是消除非物理系数的**必要步骤**，但**不承诺"去系数即 pH 回落 4.5~5.5"**——pH 回落依赖 Ks 重标定 + ET 闭合 + 产酸源强化的联合作用（决策 D2）；v0.5.2 验收仅要求"入渗/径流物理方向正确 + 质量守恒"。
- **版本**：v0.5.2（阶段①）；后续 v0.5.3（阶段②，VGM+ET+级联重构）、v0.6.0（阶段③，子步长）。
- **关联工单**：44（Green-Ampt 模块）→ 45（Ksat 拆分）→ 46（优先流）→ 47（硝化限 L1）→ 48（集成+发布）。
- **基线漂移警告**：Green-Ampt + 基质 K_s 使入渗量显著下降、径流增加 → 既有 4 层 pH 剖面与 AlX₃ 淋失行为将变化，必须运行验证并如实文档化（延续 L9 科学诚实先例）。

