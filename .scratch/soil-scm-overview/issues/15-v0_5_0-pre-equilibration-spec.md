# 15 — v0.5.0 初始状态自洽化 spec（pre_equilibrate 预平衡）

**What to build:** Soil-SCM v0.5.0 的初始状态自洽化规格——新增引擎层 `pre_equilibrate` 前处理预平衡（默认开启），让初始状态热力学自洽，解决 fertilizer 长期 AlX₃ 耗尽→pH 突升（L9 根因）；并产出偏离度诊断（初始 vs 稳态的 pH 与全部交换性离子）。工单 16-19 由本 spec 拆分。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

---

## Problem Statement

v0.4.0 L9 扫描证明 MINERAL_SCALE 参数调整与非晶质 Al(OH)₃ 相均无法解决 fertilizer 单层 AlX₃ 耗尽。根因是**初始状态不自洽**：溶液/交换/矿物三相独立估算拼合，首次 PHREEQC 平衡剧烈重分配（矿物量大时 AlX₃ 一次性骤降 24,000 mol，矿物成"单向 Al 汇"）。用户提供的观测数据（pH/CEC/交换性离子/矿物质量分数）不足以直接构成热力学自洽，缺溶液组成观测与矿物平衡量。

## Solution

前处理预平衡：初始构建后连续执行无干预多步平衡（无降水/施肥/石灰，固定 pCO₂），溶液/交换/矿物纯内部重分配至稳态，以平衡态作为长期模拟初始状态。**默认开启**（config 可配）。预平衡同时产出偏离度诊断（pH + 全部交换性离子 Δ）——既是 L9 验证，也是输入参数物理性检验（稳态应接近观测）。

## User Stories

1. 作为土壤学家，我希望初始状态热力学自洽，以便 30 年长期模拟不因首次平衡剧烈重分配失真。
2. 作为土壤学家，我希望 fertilizer 30 年 AlX₃ 缓冲不耗尽、pH 无突升。
3. 作为模型开发者，我希望预平衡默认开但可配置（开关 + 最大步数）。
4. 作为模型开发者，我希望预平衡在引擎层实现（复用 run_monthly_step），与既有架构一致。
5. 作为土壤学家，我希望预平衡产出偏离度诊断（pH + 全部交换性离子），验证"稳态接近实测"预期。
6. 作为研究者，我希望偏离度超范围时获得警示，识别输入参数不物理性。
7. 作为模型开发者，我希望 simplified 引擎跳过预平衡（无化学平衡概念）。
8. 作为土壤学家，我希望预平衡不引入淋洗/施肥干扰（无干预平衡）。
9. 作为模型开发者，我希望收敛判据可复现（连续两步变化 < 阈值）。
10. 作为研究者，我希望未来研究区实测溶液数据可接入（L6 逐层参数）。

## Implementation Decisions

- **引擎层**：新增 `pre_equilibrate(state, soil_profile)` 方法——无干预多步平衡（复用 run_monthly_step，forcing 无降水/固定 pCO₂/temp，action 无操作），收敛判据（连续两步 pH 变化 <0.01 且 AlX₃ 相对变化 <1%）或 max_steps 截断（默认 60）；返回平衡后状态 + 偏离度诊断。
- **config**：`enable_pre_equilibration`（**默认 true**）、`pre_equilibration_max_steps`（默认 60）。
- **偏离度诊断**：对比初始 vs 稳态 pH 与交换位点（CaX2/MgX2/KX/NaX/AlX3），Δ 日志输出；科学判据（初值）：ΔpH<0.5、各交换离子相对变化 <20%，超出警示。
- **simplified**：跳过（返回原状态）。
- **流程集成**：main.py 在 build_initial_state 后、长期模拟前调用 pre_equilibrate。
- **L9 重定义**：预平衡成为 L9 落地载体；交换选择性/动力学降为备选。

## Testing Decisions

- **接缝**：run_monthly_step（既有）+ pre_equilibrate（新）。
- **测试**：收敛性（稳态稳定）、无干预（无降水/施肥）、max_steps 截断、simplified 跳过、偏离度 Δ 计算与阈值、E2E（预平衡默认开后 fertilizer 30 年 AlX₃>1e4 + pH<9 + 无降级）。
- **先例**：v0.3.0/v0.4.0 E2E 脚本、test_mineral_evolution.py、test_nitrification.py。

## Out of Scope

- 研究区实测数据接入（L6，后续）、Al 交换选择性/矿物化动力学（L9 备选）、工程化批次（L7/L8）。

## Further Notes

- **默认开影响**：改变全部模拟基线——natural 30 年 pH 可能偏离 v0.3.0 的 6.46，需科学评估新稳态合理性（用户预期稳态接近观测）。
- **诊断价值**：偏离度同时验证"稳态≈观测"预期与输入参数物理性。
- L1 不受影响（纯文档）。
