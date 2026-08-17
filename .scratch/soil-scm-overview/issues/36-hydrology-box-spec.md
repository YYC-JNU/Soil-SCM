# 36 — v0.5.0 逐层土壤水文盒子模型 spec

**What to build:** 将模型从"全局入渗系数"升级为**逐层土壤水文过程**：Horton 入渗（随机日降雨 + 初渗/稳渗率）、Ksat 层间渗漏、孔隙度持水与跨月滞水；4 层模拟内置物理剖面默认（厚度/粘粒/孔隙度/Ksat/初渗/稳渗）。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

**来源：** /grill-me 敲定 12 项决策（2026-08-17）

---

## Problem Statement

当前模型水文处理为**全局 `precip_infiltration=0.05`**（降水固定 5% 入渗、95% 径流；排水量每层相同），**无土壤导水/入渗/持水物理概念**。多层模拟默认各层参数相同（L6 提供覆盖但默认关闭）。真实剖面约束（L9 唯一未被证伪方向）需要**物理水文过程**支撑：Horton 入渗（初渗率高→稳渗率）、Ksat 层间渗漏（透水性差的下层限制渗漏）、孔隙度持水（土壤储水）。4 层模拟需要**物理合理的默认剖面**（厚度随深度增大、粘粒增多、孔隙度减小、导水/入渗能力递减）。

## Solution

- **随机日降雨生成器**：每月场次 `N~U(4,12)`、每场降水指数分布拆分（月总量守恒）、单场历时 2h、种子默认 42（config 可配，可复现）。
- **Horton 入渗**（`k=5/h`）：单场入渗能力 `A = fc×T + (f0−fc)/k·(1−e^(−kT))`（f0/fc 用表层）；入渗 = `min(场降水×0.75, A)`（0.75=表层入渗系数；降水耗尽则全入渗）；月径流 = 月降水 − 月入渗。
- **Ksat 层间渗漏**：每层排水 `= min(可排水量, Ksat_i×面积×月天数)`；最底层=深层排水。
- **孔隙度持水**：溶液体积维持 50% 饱和度；持水增量 = 0.5×φ×厚度；排水 = max(0, 来水 − 持水增量)；跨月滞水 `stored_water` 累积（层内水量，饱和后 Ksat 限制下渗，超饱和部分计入径流）。
- **4 层内置默认剖面**（n_layers=4 且未配置 layer_overrides 时自动启用）：厚度 [20,20,20,40]cm / 粘粒 [25,35,45,50]% / 孔隙度 [55,47,45,43]% / 反推容重 ρ=2.65(1−φ) / Ksat [76.8,24.5,7.2,2.9] cm/day / 初渗 [1.0,0.4,0.15,0.04] / 稳渗 [0.4,0.2,0.08,0.02] mm/min。
- **水文模式替代**：n_layers>1 且（4 层自动或 layer_overrides 含水文字段）启用水文 → 入渗量由水文计算（弃用全局 precip_infiltration）；n_layers=1 完全回退现状。
- **诊断输出**：新增逐层水文列（infiltration/runoff/drainage/stored_water，复用 L6 层后缀）。

## User Stories

1. 作为土壤学家，我希望 4 层模拟默认使用物理剖面（表层薄/粘粒少/孔隙度大/导水强，底层厚/粘粒多/致密/导水弱），以便反映真实红壤垂直分层。
2. 作为研究者，我希望降雨事件由随机数生成（场次与日降水随机、月总量守恒），以便模拟次降雨脉冲对入渗-径流的影响。
3. 作为研究者，我希望随机降雨可复现（固定种子），以便结果可验证、可对比（科学诚实）。
4. 作为模型开发者，我希望 Horton 入渗（初渗率 f0/稳渗率 fc/衰减 k）决定入渗 vs 径流，以便超渗径流物理表达。
5. 作为模型开发者，我希望表层入渗系数 0.75 限制入渗上限（降水耗尽则全入渗），以便与既有"入渗系数"语义衔接。
6. 作为研究者，我希望 Ksat 逐层限制渗漏（透水性差的下层限制排水），以便模拟滞水与深层排水。
7. 作为研究者，我希望孔隙度决定持水容量与溶液体积（50% 饱和度），以便土壤储水缓冲淋失。
8. 作为研究者，我希望跨月滞水状态（stored_water）累积与释放，以便雨季连续降水下的水分连续。
9. 作为模型开发者，我希望 n_layers=1 完全走原路径，以便既有单层基线不回归。
10. 作为模型开发者，我希望 layer_overrides 扩展水文字段（部分覆盖/默认回退），以便用户可覆盖内置剖面。
11. 作为研究者，我希望新增逐层水文诊断列，以便验证入渗/径流/排水/储水。
12. 作为研究者，我希望 4 层自动启用水文后基线与耗尽行为变化被运行验证并文档化（科学诚实记录基线漂移）。

## Implementation Decisions

- **新模块（水文）**：`src/hydrology.py` 承载随机降雨生成、Horton 单场入渗、层间级联（持水+Ksat+滞水）；纯函数/类设计，与化学引擎解耦。
- **状态**：`SoilState` 新增 `stored_water`（跨月滞水 L/ha）；`SoilProfile` 新增 `porosity`（显式覆盖否则 1−ρ/2.65）、`ksat`、`infiltration_initial`、`infiltration_steady`（clay_pct 已有）。
- **配置**：`LayerOverrideConfig` 扩展 5 字段（clay_pct/porosity/ksat/infiltration_initial/infiltration_steady）+ `SimulationConfig.hydrology_seed`；值域校验（φ∈(0,1)、ksat>0、f0>fc≥0）；孔隙度覆盖时反推容重（ρ=2.65(1−φ)，覆盖 bulk_density）。
- **内置默认**：4 层剖面默认（厚度/粘粒/孔隙度/Ksat/f0/fc）收敛于常量模块；`n_layers=4` 且未配置 layer_overrides 时自动注入。
- **引擎**：`run_monthly_multi_layer` 接受各层来水量/排水量（水文结果），替代 `precip_infiltration` 排水计算；`_build_phreeqc_input` REACTION H2O 用量用该层来水量；单层路径不变。
- **编排**：main 构建水文模型（4 层自动默认/用户覆盖判断）→ 月度循环调用水文 → 传递入渗/排水 → 记录水文诊断。
- **输出**：OutputWriter 复用层后缀，新增 infiltration/runoff/drainage/stored_water 列。

### 测试接缝（复用既有 + 1 新 seam）
- S1 `src/hydrology.py` 纯函数（随机降雨/Horton 单场/级联）——新模块单元 seam
- S2 `ConfigManager` 解析/校验（扩展字段+seed+值域）——先例 test_config_manager.py
- S3 `SoilProfile` 扩展（孔隙度反推容重/水文字段）——先例 test_input_reader.py
- S4 引擎集成（4 层自动启用/月度步/层间排水）——先例 test_multilayer.py / test_layer_overrides.py
- S5 输出（水文诊断列）——先例 test_multilayer_output.py

## Testing Decisions

- **好测试标准**：只测外部行为（随机降雨可复现/总量守恒、Horton 入渗量、级联持水+Ksat+滞水、4 层自动默认注入、单层回归），不测实现细节；手算独立验证数值。
- **模块测试**：hydrology（S1）、config（S2）、profile（S3）、引擎集成（S4）、输出（S5）。
- **先例**：test_config_manager / test_input_reader / test_multilayer / test_layer_overrides / test_multilayer_output。
- **验证**：4 层 natural 基线对比（新水文 vs 旧 precip_infiltration），记录入渗量/AlX₃ 耗尽年/pH 变化；全量 pytest 保持全绿。

## Out of Scope

- 单层水文（n_layers=1 保持现状，不引入）。
- 土壤水分剖面动态（θ(z,t)）——采用月度盒子平衡 + 跨月滞水近似。
- 蒸散发/作物需水过程。
- Horton 衰减系数的逐层差异（统一 k=5/h）。
- 次降雨强度分布（指数分配近似）。
- 地下水/侧向流过程（仅垂直盒子 + 超饱和溢出计入径流）。

## Further Notes

- **基线漂移警告**：4 层自动启用水文后入渗量由 ~5% 变为 ~0.75×Horton 上限，淋失强度增大数倍 → AlX₃ 耗尽年/pH 行为将显著变化。必须运行验证并如实文档化（延续 L9 科学诚实先例）。
- **L9 关联**：物理水文（Ksat 限制渗漏、孔隙度持水缓冲）是"多层 + 真实剖面"方向的深化；Ksat 限制可能推迟深层 AlX₃ 耗尽，但表层入渗增大可能加剧淋失——good/bad 并存，验证后如实报告。
- **版本**：v0.5.0（实质性功能）。
