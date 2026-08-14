# 11 — v0.4.0 后续优化 spec（L9 矿物缓冲校准 + L1 Al 表面简化方法）

**What to build:** Soil-SCM v0.4.0 两个后续优化工单的规格——L9（MINERAL_SCALE 参数扫描 + 非晶质 Al(OH)₃ 兜底，解决 fertilizer 长期 AlX₃ 耗尽→pH 突升）与 L1（Al³⁺ 表面络合简化方法 Kd+pH 修正 + 单独报告含缺点与优化方向）。工单 12-14 由本 spec 拆分。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

---

## Problem Statement

1. **模型长期稳定性受损（L9）**：v0.3.0 实测发现 fertilizer 单层模拟中 AlX₃ 缓冲于第 2-3 年耗尽 → pH 突升 10.4。根因是矿物量压缩（Q1+ MINERAL_SCALE=0.001）与单层排水（Q12*）的组合。
2. **Al³⁺ 表面络合缺失（L1）**：Al 在铁氧化物/有机质表面的络合是红壤酸化核心机制，四源查证无标准数据（研究空白），需简化方法落地并诚实记录不确定性。

## Solution

- **L9**：MINERAL_SCALE 参数扫描（0.001→0.005→0.01→0.05→0.1；0.1 档成功则继续 0.2→0.5→0.7→1.0），验收 = fertilizer 单层 30 年 AlX₃>1e4 + pH<9 + 无降级 + 102 测试全绿；单一 scale 无法兼顾则增加非晶质 Al(OH)₃ 相兜底。
- **L1**：`Kd_eff(pH)=Kd×f(pH)` 简化质量作用式（Kd 文献骨架 + Sverjensky/Karamalidis 模型交叉验证）；产出 `docs/L1_AL_SURFACE_METHOD.md`（框架/参数/f(pH)/缺点专节/优化方向专节）。

## User Stories

1. 作为土壤学家，我希望 fertilizer 30 年模拟中 AlX₃ 缓冲不耗尽，以便长期施肥-酸化演化可信。
2. 作为土壤学家，我希望 pH 不再第 3 年突升 ~10，以便模型输出可解释。
3. 作为模型开发者，我希望 MINERAL_SCALE 选定有完整扫描记录与依据。
4. 作为模型开发者，我希望扩大 MINERAL_SCALE 不破坏 P1-P5 收敛与既有测试基线。
5. 作为土壤学家，我希望 Al³⁺ 吸附以简化方式（Kd+pH 修正）纳入模型。
6. 作为研究者，我希望 L1 报告明确缺点与优化方向，科学边界诚实。
7. 作为模型开发者，我希望 L1 简化吸附逻辑与 L9 Al 循环可衔接。
8. 作为土壤学家，我希望 Kd 参数有文献依据并标注不确定性。
9. 作为模型开发者，我希望 L9 与 L1 并行推进互不阻塞。
10. 作为研究者，我希望非晶质 Al(OH)₃ 兜底方案有启用条件说明。

## Implementation Decisions

- **L9（引擎）**：MINERAL_SCALE 扫描（Q7=A，0.1 成功后扩展至 1.0）；成功判定 AlX₃>1e4 + pH<9 + 无降级 + 全量回归；trade-off 无解则启用非晶质 Al(OH)₃ 相（Q3=D）；选定值入常量模块（Q19）+ 扫描表记录。
- **L1（文档）**：Kd_eff(pH)=Kd×f(pH)，f(pH) 简化质量作用式（有效 log_K）；Kd 文献骨架 + 模型交叉验证；覆盖矿物（Hfo）+ 有机质表面（合并 L3，标注不确定）；报告含缺点与优化方向专节。

## Testing Decisions

- **接缝**：run_monthly_step（月度化学步）+ E2E 长期模拟（L9）；L1 纯文档（审查式验收）。
- **L9**：参数扫描脚本（临时，逐档跑 fertilizer 单层 30 年记录 pH/AlX₃/收敛）；验收断言 AlX₃>1e4、pH<9、无降级；全量 pytest 回归（MINERAL_SCALE 影响 P1-P5 收敛、矿物回填、SURFACE、多层）。
- **先例**：v0.3.0 E2E 脚本 + test_mineral_evolution.py（L2 矿物回填测试）。

## Out of Scope

- 工程化批次（L6/L7/L8）、硝化 KINETICS 升级、本地吸附实验标定、标准表面络合数据库切换。

## Further Notes

- **Q1+ 历史风险**：物理矿物量曾导致碱性突变（pH~9.9）——扫描须关注 scale 增大 vs 收敛 trade-off。
- **兜底条件**：非晶质 Al(OH)₃ 仅在扫描无法同时满足收敛与稳定时启用。
- **v0.4.0 交付**：L9 选定 scale + 30 年验证；L1 报告；测试与文档同步；code-review + commit。
