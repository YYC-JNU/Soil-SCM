# 29 — L6 逐层参数覆盖（layer_overrides）spec

**What to build:** config 支持逐层参数覆盖（ph/有机质/容重/CEC/交换性离子/矿物/pCO₂ + layer_depths），真实剖面约束下的 fertilizer 行为诊断；保持 n_layers=1 单层兼容与各层默认相同。

**Blocked by:** None — can start immediately.

**Status:** ✅ 已完成 (2026-08-17, v0.4.0)

**来源：** 工单 23（L6）+ /grilling 设计敲定（10 项决策，2026-08-17）

---

## Problem Statement

当前多层模型**所有层共用同一 `SoilProfile` / 矿物信息 / pCO₂**（`main.py` 阶段 7 循环 `build_initial_state(soil_profile, soil_info, initial_pCO2)`），无法应用真实剖面观测约束。L9 完整证伪链确认：**仅多层 + L6 逐层参数未被证伪**（多层已验证推迟耗尽 y2→y4）。真实剖面数据接入是研究应用的基础（ROADMAP 长期）。工单 23 设计要求已完成，**完整实现未做**（状态 🟡）。

**现状不一致**：当前多层各层 `effective_depth=30cm`（物理总厚 120cm），但 `OutputWriter._layer_suffixes` 在无 `layer_depths` 时等分 0~60cm → 输出列名（pH_0_15…）与实际物理厚度**错位**，L6 一并修正。

## Solution

- `simulation.layer_overrides`：**config 内联 YAML 密集列表**（长度必须 = n_layers，每项可空 dict），逐层覆盖 **7 类字段**：`ph` / `organic_matter` / `cec` / `bulk_density` / 交换性离子(`exch_*`×6) / `pCO2` / `minerals`(增量替换质量分数)。
- **部分覆盖 + 默认回退**：未写字段回退"全局默认 profile"（survey+exchangeable_ions+soil_mineral_db+pCO2_ref）。
- `simulation.layer_depths`（一并落地）：每层厚度 cm，**`effective_depth` 由 `layer_depths[i]` 派生**（隐含字段），输出层深后缀与物理厚度一致。
- `n_layers=1` 时 `layer_overrides`/`layer_depths` **忽略 + 警告**（单层回归护栏）。
- **矿物增量替换**：只替换指定矿物质量分数，不归一化；总和≠1 警告。
- **每层独立 `pre_equilibrate`**：覆盖后的 profile 作为该层观测锚定目标。
- **月度 pCO₂ 按层注入**：`run_monthly_multi_layer` 为每层设置 `layer_forcing['pCO2']`，深度 pCO₂ 梯度全程保持。
- **诊断实验**：`tools/plot_L6_layer_overrides.py` 真实剖面 4 层 vs 等参 4 层基线（fertilizer 30 年），输出对比图并**标注 good/bad influence**（绿色 good / 红色 bad，含耗尽年/年 pH 差数值）。

## User Stories

1. 作为土壤学家，我希望逐层覆盖容重/CEC/交换性离子/矿物/pCO₂，以便应用真实剖面观测约束（工单 23 What to build）。
2. 作为土壤学家，我希望逐层覆盖初始 pH 与有机质，以便表层-底层剖面差异真实表达（L1 方法报告 `M_有机质` 前置依赖）。
3. 作为模型开发者，我希望 `layer_overrides` 用 config 内联密集列表且长度必须 = n_layers，以便配置可预测、越界即报错。
4. 作为模型开发者，我希望部分覆盖（未写字段回退默认），以便只写有观测差异的层与字段。
5. 作为模型开发者，我希望 `n_layers=1` 时忽略 overrides 并警告，以便既有单层基线（115 测试护栏）不受影响。
6. 作为模型开发者，我希望 `layer_depths` 一并落地且每层 `effective_depth=layer_depths[i]`，以便层厚与交换/矿物/溶液缓冲物理自洽（修正现状后缀错位）。
7. 作为模型开发者，我希望矿物增量替换且不归一化（总和≠1 警告），以便覆盖意图不被归一化扭曲。
8. 作为研究者，我希望每层独立预平衡（用该层覆盖后 profile 锚定），以便逐层覆盖在初始态自洽中生效。
9. 作为研究者，我希望逐层 pCO₂ 在月度 GAS_PHASE 中按层注入，以便深度 pCO₂ 梯度（表层低/底层高）全程保持而非仅首月。
10. 作为研究者，我希望附带真实剖面 vs 等参基线诊断实验，以便量化 L6 对 fertilizer AlX₃ 耗尽年/pH 突升的 good/bad 影响。
11. 作为研究者，我希望诊断图片标注 good influence 与 bad influence，以便直观传达覆盖的真实收益与代价。
12. 作为模型开发者，我希望 L6 不改变既有单层行为且全部测试保持全绿，以便回归护栏成立。

## Implementation Decisions

- **配置层**：`SimulationConfig` 新增 `layer_depths: List[float] = None` 与 `layer_overrides: List[LayerOverrideConfig] = field(default_factory=list)`；新增 `LayerOverrideConfig` dataclass（7 类字段 + `minerals: dict` + `exchangeable_ions` 子块）。
- **校验（`_validate_config`）**：
  - `n_layers == 1` 且 overrides/layer_depths 非空 → **警告 + 忽略**（不报错）；
  - `n_layers > 1` 且 overrides 非空 → `len == n_layers` 否则 `ValueError`；`layer_depths` 同理；
  - 值域：`ph ∈ (3,10)`、`cec > 0`、`bulk_density > 0`、`pCO2 > 0`、`exch_* ≥ 0`、矿物质量分数 `∈ (0,1)`；
  - minerals 质量分数总和 ≠ 1 → **警告**（不归一化、不报错）。
- **构建层**：`InputReader` 新增按层应用函数（深拷贝默认 profile → 字段覆盖 → `effective_depth = layer_depths[i]`）；`SoilDatabase` 新增矿物增量覆盖辅助（返回覆盖后的 `SoilTypeInfo` 或覆盖 dict，未覆盖矿物保留）。
- **引擎层**：`run_monthly_multi_layer` 增加可选 `layer_pco2s: List[float] = None`；每层 `layer_forcing['pCO2'] = layer_pco2s[i]`（缺省用全局 `monthly_forcing['pCO2']`）。
- **编排层（main.py）**：`n_layers>1` 时构建逐层 profile 列表 / 逐层矿物信息 / 逐层 pCO₂ → 逐层 `build_initial_state` → 逐层 `pre_equilibrate`；`layer_depths` 传入 `OutputWriter`（替换现状 `getattr` 兜底）。
- **实验工具**：`tools/plot_L6_layer_overrides.py`（从项目根运行）；`matplotlib` 标注约定——绿色 annotate 标 good、红色标 bad，含数值（耗尽年、pH 差）。

## Testing Decisions

- **好测试标准**：只测外部行为（配置解析结果 / 构建出的 profile 字段 / 月度 pCO₂ 注入效果 / 各层 state 差异化），不测实现细节。
- **接缝（复用既有，不新增）**：
  - S1 `ConfigManager._load_config` + `_validate_config` — 先例 `test_config_manager.py`（纯单元）；
  - S2 `InputReader` 逐层构建 — 先例 `test_input_reader.py`（纯单元）；
  - S3 矿物增量覆盖 — 并入 S1/S2 单元测试；
  - S4 `build_initial_state` + `run_monthly_multi_layer` **2 层集成** — 先例 `test_multilayer.py`（2 层一步，不跑 30 年）；
  - S5 `OutputWriter` layer_depths — 既有 `test_multilayer_output.py` 已覆盖。
- **测试清单**：
  - layer_overrides 解析（7 类字段映射 / 长度硬校验报错 / 值域报错 / 单层忽略+警告）
  - 部分覆盖（空 dict 完全回退 / 部分字段保持其余默认）
  - `effective_depth == layer_depths[i]`
  - 矿物增量替换 + 不归一化 + 总和≠1 警告
  - 2 层集成：各层 exchange/minerals/pCO₂ 差异化生效
  - 月度 pCO₂ 按层注入（`layer_forcing['pCO2']` 生效、缺省回退全局）
  - 单层回归护栏：既有 `test_multi_layer_equivalent_to_single_when_n1` 等保持
  - 全量 `pytest tests/` 保持全绿

## Out of Scope

- L1 Al 表面络合实现（本 spec 的逐层有机质仅为其预留字段）。
- L7/L8 工程化批次。
- 逐层矿物**整体替换**（本期仅增量替换单矿物质量分数）。
- 其余 survey 字段（texture / available_p / available_k / sand / silt / clay / area）逐层覆盖。
- pCO₂ 温度响应（beta）逐层差异化——本期仅固定分压逐层。
- 分层输出 NetCDF 的深度维度重构（保持现有列后缀机制）。

## Further Notes

- **修正现状不一致**：L6 后每层 `effective_depth = layer_depths[i]`，输出后缀（0_10/10_20/20_40/40_60）与物理厚度一致。
- **L1 联动**：`docs/analysis/L1_AL_SURFACE_METHOD.md` 参数表 `M_有机质` 标注"待 L6 逐层参数接入"——本 spec 已覆盖。
- **科学诚实**：诊断实验预期"推迟+诊断"，good 与 bad 影响都须如实标注并文档化（延续 L9 六次证伪先例）。
- **层厚度物理含义**：`effective_depth` 是缓冲库容量线性乘子（交换位点/矿物/溶液体积 ∝ 厚度），而排水量不随厚度缩放 → 淋失应力 ∝ 1/厚度，层厚本身就是模拟结果的重要参数。
