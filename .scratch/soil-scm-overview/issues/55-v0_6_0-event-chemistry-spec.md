# 55 — v0.6.0 事件驱动化学 spec（化学子步长拆分最小闭环）

**What to build:** 将 v0.5.3 的"月度单次化学平衡"升级为**事件驱动化学最小闭环**：`RainEvent` dataclass + `generate_events` 事件生成 + `run_event_step` 事件级引擎接口 + 主循环逐场嵌套（水文步→化学步→月末聚合）+ **化学溶液体积-θ 耦合**（Q8b 修复：逐事件重建 `-water` + 月末浓缩平衡）+ **First-Flush 捕获**（月度峰值列 + 可选事件明细 CSV）+ **Hargreaves PET**（`calc_pet` 单入口分派，Oudin 精度增强模式）。严格 **expand-contract**：`run_monthly_step` 保留为月度聚合包装（签名不变）、`run_monthly_multi_layer` 接口不变（hydrology 可选 `events` 键），现有 **234 测试全部不破**（Q10）。

**Blocked by:** None — can start immediately（依赖 /grilling 决策表 Q1~Q16，2026-08-19 定案）。

**Status:** ready-for-agent

**来源：** /grilling 2 轮决策拷问（2026-08-19，16 项定案）→ `docs/analysis/V0_6_0_REPLAN.md` §三

---

## Problem Statement

v0.5.3 暴露的 pH 无方向响应（E2/E3）的两个根因——**① 月度聚合丢失旱季干化 ② 化学溶液体积-θ 解耦（Q8b）**——正是《v0.6.0优化开发具体步骤.txt》模块④与 ROADMAP §5 定案的"化学子步长拆分"要解决的问题：

1. **月度平滑抹杀脉冲淋溶**（OPTIMIZATION_PLAN §7.1 缺陷 4）：`main.py` 月循环把场次入渗 `sum()` 累加后单次化学平衡（`monthly_hydrology` 现状），一场 50mm 暴雨与 10 场 5mm 小雨被等价处理，First-Flush 被抹平、低估瞬态淋失峰值。
2. **化学溶液体积与 θ 解耦**（Q8b）：`SOLUTION -water` 恒定 `state.volume`，旱季干化不产生浓缩酸化——干燥→体积缩小→离子浓缩这一物理机制完全缺失。
3. **PET 通道单一**：仅 Oudin（月均温+纬度），无日较差区分干热/湿热；`pet_method="hargreaves"` 已预留报错。

科学诚实边界：**pH 回落 4.5~5.5 只验收方向**（干湿交替下 pH 方向性响应 + First-Flush 峰值如实输出），不承诺具体值（同 v0.5.3 E1~E3 口径）。

---

## Solution

### 1. 事件生成（Q1/Q11）

- 新建 `RainEvent` dataclass（`src/hydrology.py`）：`precip_mm`（单场降水 mm）、`duration_h`（历时 h，默认 `EVENT_HOURS=2.0`）、`date_hint`（年/月/场序，诊断用）、`precip_chem`（可选，None=继承引擎级降水化学）。
- 新增 `generate_events(monthly_precip_mm, year, month, seed) -> List[RainEvent]`：复用 `generate_rainfall` 的 seed 派生逻辑（`rng = default_rng(seed + year*12 + month)`），返回事件列表，Σ `precip_mm` = 月总量（质量守恒不变量）。

### 2. `run_event_step` 事件级引擎接口（Q1/Q3/Q5/Q6/Q15）

- `PhreeqcEngine.run_event_step(state, event, action, profile) -> (SoilState, DiagnosticOutput)`：
  - 事件级 forcing：`precip` = 单场量；`inflow_water_L` = 该场入渗量（由事件级水文注入）；`bypass_water_L` = 该场径流×β（逐场注入 L2，Q15）。
  - **体积-θ 耦合（Q5）**：`SOLUTION -water = θ_事件后 × depth × 1e5`（`theta_to_water_L`），替换恒定 `state.volume`；REACTION 只注入该场净入渗水量与化学。
  - **交换相/矿物相绝对摩尔量不变（Q6）**：EXCHANGE/EQUILIBRIUM_PHASES 块 mol 为绝对量，仅溶液体积随 θ 重建，PHREEQC 自动重平衡浓度。
  - 层间溶质**逐场传递**（Q4）：上层排水溶质（`conc×drain_vol`）作为下层当场 `inflow_ions`（First-Flush 本质）。
- 新增 `apply_concentration_equilibrium(state, theta, depth, forcing)`：**月末浓缩平衡**（Q7/Q12）——θ 月内下降时仅重设 `-water = θ×depth×1e5`（无 REACTION）做一次浓缩平衡；θ 未下降（回充至 θ_FC）则跳过，零额外计算。

### 3. `run_monthly_step` 月度聚合包装（Q10，expand-contract）

- **签名与返回契约不变**（state, monthly_forcing, action, profile）→ `(SoilState, DiagnosticOutput)`；语义从"单次化学平衡"升级为"月内逐场循环 + 月末浓缩平衡 + 月内淋失聚合"。
- 内部：`generate_events(月总量) → for each event: 事件级水文步（Green-Ampt 入渗 + θ 更新）→ run_event_step → 月末浓缩平衡`。
- 调用方（main 单层路径 / `run_monthly_multi_layer` 月级路径 / 现有 234 测试）**零改动**。

### 4. 主循环嵌套与逐场级联（Q3/Q4/Q10/Q15）

- `run_monthly_multi_layer`：**接口不变**；`hydrology` dict 新增**可选 `events` 键**（`List[dict]`，每场含 `inflows/drains/bypass_water_L`）→ 内部逐场逐层级联（for event: for layer: `run_event_step`，层间溶质事件粒度传递）；无 `events` 键走旧月级路径（向后兼容护栏）。
- `main._apply_hydrology_month`：扩展为事件级编排——月首 ET 一次（Feddes，复用 `apply_feddes_et`）+ 逐场 Green-Ampt 入渗（θ_i 逐场更新）+ 逐场层间级联（复用 `LayerCascade`）+ 逐场 bypass（Q15）；返回含 `events` 键。
- 单层护栏：`n_layers=1` 事件化同样生效（单层走 `run_monthly_step` 包装，语义一致）。

### 5. First-Flush 输出（Q14）

- 月度主 CSV 新增**峰值列**（默认开）：`flush_NO3_peak_mmol`、`flush_base_peak_mmol`（当月 L1 最大单场淋失量，mmol/ha，base = Ca+Mg+K 盐基）。
- 新增 config `output.event_output: false`（默认关）：开启时输出逐场明细 CSV `output/event_leaching_<scenario>.csv`（事件日期、月、各层淋失 mol/ha、事件 pH）。

### 6. Hargreaves PET（Q8/Q9/Q13，Oudin 精度增强模式）

- `climate_forcing.py` 新增单入口 `calc_pet(t_mean, latitude, month, method='oudin', diurnal_range_deg=8.0)`，内部按 `pet_method` 分派：
  - `"oudin"`（默认）：现状 `calc_pet_oudin` 不变；
  - `"hargreaves"`：`PET = 0.0023 × R_a × (T_mean + 17.8) × √(T_max − T_min)`，`T_max = T_mean + range/2`、`T_min = T_mean − range/2`，`R_a` 复用 Oudin 已有日地/赤纬/时角计算；
  - `"hargreaves_enhanced"`：v0.6.0 **只预留枚举 + 显式报错**（数据管线留 v0.7.0）。
- 输出格式完全相同（`n_years × 12` 逐月 PET 数组），下游 ET 扣除（`LayerCascade`）无需知道方法来源。
- config 新增：`climate.diurnal_range_deg`（默认 8.0，校验 >0）。

---

## User Stories

1. 作为模型研究者，我希望每月降雨被拆分为逐场事件并每场执行一次 PHREEQC 全量平衡，以便 50mm 暴雨与 5mm 小雨不再被等价处理。
2. 作为模型研究者，我希望化学溶液体积随事件后 θ 重建，以便旱季干化产生真实的浓缩酸化效应（对治 pH 无方向响应根因 ②）。
3. 作为模型研究者，我希望无降水事件的旱季月末做一次"浓缩平衡"，以便月尾 θ 回充不掩盖月内干化的化学效应。
4. 作为模型研究者，我希望上层排水溶质逐场传递到下层，以便暴雨事件的重金属/硝酸盐脉冲式淋失如实贯通 4 层（First-Flush 的本质）。
5. 作为模型研究者，我希望月度输出新增 First-Flush 峰值列，以便无需打开明细即可在长时间序列中定位脉冲淋失事件。
6. 作为模型研究者，我希望可选开启逐场事件明细 CSV，以便输出发表级"脉冲式淋溶"动态图表。
7. 作为模型研究者，我希望 `pet_method="hargreaves"` 可用，以便用日较差区分干热/湿热（仅需 config 单一日较差参数）。
8. 作为模型研究者，我希望 `hargreaves_enhanced` 预留报错而非静默吞掉，以便未来字段不被错误使用。
9. 作为模型研究者，我希望现有 234 测试全部保持通过，以便 v0.5.3 回归护栏（质量守恒/单层回归/数值稳定性/化学基线）不因宽重构而破坏。
10. 作为模型研究者，我希望 `n_layers=1` 单层路径事件化后行为一致，以便单点调试不受多层级联干扰。
11. 作为模型开发者，我希望 `run_monthly_step` 签名不变、内部事件化，以便 main 与多层级联调用面零改动（expand-contract）。
12. 作为模型开发者，我希望 `generate_events` 的 seed 派生与 `generate_rainfall` 一致，以便同 seed 模拟可复现。
13. 作为模型开发者，我希望事件级 `run_event_step` 复用子进程超时机制，以便长模拟不被偶发 PHREEQC 卡顿阻塞。
14. 作为模型研究者，我希望浓度下限与体积骤变防护存在，以便事件级小水量不触发 PHREEQC 数值发散。
15. 作为模型研究者，我希望 E2（PET 敏感性）复验呈现旱季 θ 下降与 pH 方向性响应，以便发布前验证物理方向。
16. 作为模型研究者，我希望 E3（k_om 敏感性）复验呈现表层酸化方向，以便发布前验证 OM 产酸路径有效性。

---

## Implementation Decisions

- **模块组织**（Q12）：`src/hydrology.py` 新增 `RainEvent` dataclass + `generate_events`；`src/phreeqc_engine.py` 新增 `run_event_step` + `apply_concentration_equilibrium`，`run_monthly_step` 改聚合包装；`src/climate_forcing.py` 新增 `calc_pet` 分派入口（`calc_pet_oudin` 保留为内部实现）；`src/config_manager.py` 新增 `climate.diurnal_range_deg` / `output.event_output` 解析与校验；`src/output_writer.py` 新增事件明细输出与峰值列；`main.py` 的 `_apply_hydrology_month` 扩展 `events` 键。
- **`run_monthly_multi_layer` 调和（Q4∩Q10）**：签名不变；`hydrology` dict 新增可选 `events` 键（每场 `inflows/drains/bypass_water_L`）；有 `events` → 逐场逐层级联；无 → 旧月级路径（护栏）。层间溶质传递粒度 = 事件（Q4）。
- **体积-θ 耦合契约（Q5/Q6）**：`run_event_step` 内 `-water = θ_事件后×depth×1e5`；交换相/矿物相绝对摩尔量不缩放；溶液浓度下限 `1e-10 mol/L`（`_build_phreeqc_input` 统一施加，v0.7.0 文档 §三.3 预留）；体积骤变防发散（KNOBS 迭代数不变，状态防护沿用）。
- **月末浓缩平衡（Q7/Q12）**：`apply_concentration_equilibrium` 在 `run_monthly_step` 事件循环后调用一次；θ_月末 < θ_月初（各层）才触发；无 REACTION、无降水化学，仅 `-water` 重建。
- **事件级 forcing 契约**：`run_event_step` 接收的事件 forcing 键：`precip`（单场 mm）/`inflow_water_L`/`bypass_water_L`/`inflow_ions`/`temp`/`pCO2`/`skip_nitrification`/`injection`；`precip_chem` 由 event 携带或继承引擎级（Q1）。
- **First-Flush 聚合口径（Q2/Q14）**：月末 pH/交换离子 = 最后一场事件状态；峰值列 = 月内 L1 各场淋失 max；事件明细 CSV 记录每场（日期、月、层、淋失 mol/ha、pH）。
- **bypass（Q15）**：逐场事件径流×β 注入 L2；月聚合值 = Σ 事件值（诊断列语义不变）。
- **Hargreaves（Q8/Q9）**：`calc_pet` 单入口；`hargreaves_enhanced` 显式报错（预留）；`diurnal_range_deg` config 化（默认 8.0，非硬编码）；`calc_pet_oudin` 签名保持（既有测试回归）。
- **单位约定**：水文域 θ（m³/m³）；引擎/输出边界 L/ha（1 cm/day = 1e5 L/ha/day；θ×depth×1e5 = L/ha，复用 `vgm.theta_to_water_L`）。
- **性能（Q16）**：`run_event_step` 复用子进程超时包装（`_monthly_step_worker` 模式，按事件粒度）；sensitivity 脚本 `--all --max N` 分批断点续跑；不加 `max_events_per_month` 上限。

## Testing Decisions

- **好测试标准**：只测外部行为与物理不变量——事件总量守恒、seed 复现、体积-θ 数学恒等、月末=最后事件状态、峰值=月内 max、hargreaves 公式端点、单层回归；不测实现细节。
- **接缝 S1~S6**（2026-08-19 to-spec 定案）：
  - **S1 `test_phreeqc_engine.py`（既有，最高接缝）**：现有断言**一字不改**（expand-contract 门禁）；新增"月内事件聚合"不变量（Σ事件降水=月降水、月末状态=最后事件）。
  - **S2 新增 `test_event_chemistry.py`**：`run_event_step` 契约——事件级 forcing、体积-θ 重建（`-water = θ×depth×1e5` 数值断言）、交换相/矿物相绝对摩尔量不变、`apply_concentration_equilibrium`（θ 下降触发/θ 不变跳过）、浓度下限 `1e-10` 施加。
  - **S3 `test_hydrology.py`（既有扩展）**：`generate_events` 数量范围 [4,12]、Σ=月总量、seed 复现、`RainEvent.duration_h` 默认 2.0。
  - **S4 `test_climate_forcing.py`（既有扩展）**：`calc_pet` 分派——`"oudin"` 与 `calc_pet_oudin` 等价回归、`"hargreaves"` 公式端点（T_max=T_mean+range/2 代入）、日较差敏感性（range↑→PET↑）、`"hargreaves_enhanced"` 显式报错。
  - **S5 `test_multilayer.py`/`test_layer_overrides.py`（既有扩展）**：`run_monthly_multi_layer` `events` 路径——逐场级联（上层事件1排水→下层事件1）、无 `events` 键回退月级护栏、bypass 逐场注入 L2 总量=月值。
  - **S6 `test_multilayer_output.py`/新增 `test_output_writer.py`**：月度峰值列 `flush_NO3_peak_mmol`/`flush_base_peak_mmol` = 月内 L1 各场 max；`output.event_output=true` 时事件 CSV 列结构（日期/层/淋失/pH）；`false`（默认）不产生文件。
- **不变量保护（Q6 口径延续）**：质量守恒/单层回归/数值稳定性-timeout/化学引擎基线四类一字不改；仅新增事件级断言；禁止无替代删除。
- **目标测试数**：234 + 新增 ≈ **260~270 全绿**。
- **先例**：spec 49（S1~S6 接缝）/ `test_phreeqc_engine.py`（引擎基线）/ `test_hydrology.py`（纯函数）/ `test_climate_forcing.py`。

## Out of Scope

- NO₃⁻ 示踪池 + 伴随阳离子淋失（v0.7.0，D3）
- 原生矿物风化动力学化（v0.7.0，D2）
- k_om 重参数化 / 动态 OM-C 池（v0.7.0）
- `hargreaves_enhanced` 数据管线（v0.6.0 仅预留枚举+报错，数据管线留 v0.7.0）
- 毛细上升/双向达西（`calc_interface_flux(mode="bidirectional")` 后续版本）
- SWAP 式 AET 跨层根系补偿（后续版本）
- β 旱雨季动态调整（后续小版本）
- `max_events_per_month` 事件上限（Q16 明确不做）
- GAS_PHASE 固定体积 + 动态 CO₂ mol（既有备选 C，未采纳）

## Further Notes

- **config 默认**：`climate.diurnal_range_deg=8.0`（华南典型日较差 6~10°C 中值，注释附依据）；`output.event_output=false`（默认关，避免文件体积爆炸）；`pet_method` 默认仍 `"oudin"`（最小破坏面）。
- **科学诚实**：pH 回落 4.5~5.5 为目标方向，E2/E3 只验收方向（旱季 θ 下降 + 浓缩酸化 + First-Flush 峰值）；不承诺具体值。
- **版本**：v0.6.0；发布流程 = 版本号同步 → commit → annotated tag → push main + push tag。
- **关联工单**：56（RainEvent+generate_events）→ 57（run_event_step+浓缩平衡）→ 58（run_monthly_step 包装+多层 events 路径）→ 59（main 事件编排+First-Flush 输出）→ 60（Hargreaves calc_pet）→ 61（集成+验收 E2/E3 复验+发布）。
- **风险评估**：事件化后 PHREEQC 调用次数 ×(4~12)，50 年 4 层 ≈ 1~4 分钟（Q16 确认可接受）；事件级小水量数值稳定性靠浓度下限防护；`run_monthly_step` 语义变化对既有测试是"行为增强"（月内淋失聚合），需 S1 新增不变量测试锚定。
