# 20 — v0.6.0 Al 动力学（KINETICS）+ L6 逐层参数 spec

**What to build:** Soil-SCM v0.6.0 规格——Al 动力学（KINETICS 速率控制阻断"矿物化单向 Al 汇"，解决 L9 fertilizer 单层 AlX₃ 耗尽）+ L6 逐层参数（诊断性，研究应用基础）。工单 21-24 由本 spec 拆分。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

---

## Problem Statement

v0.5.0 完整证伪链（MINERAL_SCALE / 非晶质相 / 预平衡 / 缺口修正 / AlX₃ 交换 log_k）确认：fertilizer 单层 AlX₃ 耗尽是**模型架构层局限**——盐基置换交换 Al + 矿物化沉淀吸收（单向 Al 汇）+ 单层排水淋失。4 层默认参数多层仅推迟（y2→y4）。需架构级解决。

## Solution

- **Al 动力学（KINETICS）**：把 Al 关键相（gibbsite / Al(OH)₃(a)）从瞬时平衡（EQUILIBRIUM_PHASES）切换为**速率控制**（RATES 一阶动力学 `rate = k×(10^SI−1)`）——沉淀速率受限，溶液 Al³⁺ 有时间被排水带走（而非固化到矿物），阻断"单向 Al 汇"。
- **L2 矿物回填双路径**：动力学相（gibbsite/Al(OH)₃(a)）经 SELECTED_OUTPUT `-kinetics` 回填，平衡相（kaolinite 等）保持 `-equilibrium_phases` 回填。
- **k 参数扫描**：速率常数扫描（初值 1e-8~1e-10 mol/s），验收 fertilizer 30 年 AlX₃>1e4 + pH<9 + 无降级。
- **L6 逐层参数**：config 支持逐层覆盖（容重/CEC/交换离子/矿物/pCO₂），真实剖面约束下的 fertilizer 行为诊断。

## User Stories

1. 作为土壤学家，我希望 fertilizer 情景 30 年 AlX₃ 缓冲不耗尽、pH 无突升，以便长期施肥-酸化演化可信。
2. 作为模型开发者，我希望 Al 矿物沉淀受速率控制，以便阻断"矿物化单向 Al 汇"的持续流失通道。
3. 作为模型开发者，我希望仅 Al 关键相走动力学、其余矿物保持平衡路径，以便改动可控、回归面小。
4. 作为模型开发者，我希望 L2 矿物回填支持动力学相/平衡相双路径，以便矿物演化状态连续。
5. 作为研究者，我希望动力学速率常数可配置可扫描，以便标定有效区间。
6. 作为土壤学家，我希望 L6 逐层参数支持真实剖面（容重/CEC/矿物分布差异化），以便研究应用。
7. 作为模型开发者，我希望 L6 保持 n_layers=1 单层兼容与各层默认相同，以便既有行为不回归。
8. 作为研究者，我希望 v0.6.0 扫描结论（有效或无效）文档化，以便科学诚实与可复现。
9. 作为土壤学家，我希望 natural 基线不因动力学切换而显著变化，以便既有验证结论保持。
10. 作为模型开发者，我希望 KINETICS 切换不破坏 P1-P5 收敛与既有测试。

## Implementation Decisions

- **引擎层**：`_build_phreeqc_input` 生成 RATES（gibbsite + Al(OH)₃(a)，TST 一阶）+ KINETICS 块；EQUILIBRIUM_PHASES 仅保留非 Al 相；SELECTED_OUTPUT 增加 `-kinetics`。
- **L2 回填**：`_parse_official_output` 按相分流——动力学相读 kinetics 列（摩尔量）、平衡相读 equilibrium_phases 列。
- **速率常数**：`AL_KINETICS_RATE` 入常量模块（初值 1e-9 mol/s），TST 形式 `rate = k×(10^SI−1)`（SI>0 沉淀 / SI<0 溶解），按月步长 30 天积分。
- **L6 逐层参数**：config `layer_overrides`（可选，默认各层相同保持兼容）；逐层覆盖容重/CEC/交换性离子/矿物/pCO₂；InputReader/初始构建按层应用。
- **常量收敛（Q19）**：动力学参数、L6 相关入常量模块。

## Testing Decisions

- **接缝**：`run_monthly_step`（月度化学步）+ `_build_phreeqc_input`/`_parse_official_output`（KINETICS 生成与回填）+ E2E 长期模拟。
- **测试**：
  - KINETICS 块生成（输入含 RATES/KINETICS、Al 相不在 EQUILIBRIUM）
  - L2 双路径回填（动力学相摩尔量正确、平衡相不受影响）
  - k 参数扫描脚本（fertilizer 30 年 AlX₃/pH/降级）
  - L6 逐层覆盖配置解析与按层应用
  - natural 基线回归、全量 pytest
- **先例**：v0.3.0-v0.5.0 E2E 脚本、test_mineral_evolution.py（L2 回填）、test_pre_equilibration.py。

## Out of Scope

- 全部矿物切 KINETICS（仅 Al 关键相）
- Al 交换选择性校准（已证伪，v0.5.0）
- 工程化批次（L7/L8）、L1 Al 表面简化实现
- 深层矿物学/动力学机理研究（如温度依赖速率）

## Further Notes

- **L9 证伪链**：v0.4.0+v0.5.0 累计 5 类方案无效，Al 动力学是**首个直接对症尝试**（针对单向汇机制）。
- **L6 预期**：真实剖面下 fertilizer 行为为"推迟+诊断"（根治依赖 Al 动力学验证结果）。
- **k 扫描方法论**：延续 L9 扫描（分档 + 30 年验收 + 结论文档化）。
