# 12 — L9 矿物缓冲校准（MINERAL_SCALE 参数扫描）

**What to build:** 通过 MINERAL_SCALE 参数扫描解决 fertilizer 单层长期模拟中 AlX₃ 耗尽→pH 突升的根因。选定一个能同时满足"AlX₃ 30 年稳定 + pH 无突升 + PHREEQC 收敛"的缩放系数，必要时以非晶质 Al(OH)₃ 缓冲相兜底。

**Blocked by:** None — can start immediately.

**Status:** ✅ 部分完成（扫描结论 + 非晶质相保留；fertilizer 根治未达成，深层机制后续立项）

## Acceptance criteria

- [x] MINERAL_SCALE 扫描 0.001/0.005/0.01/0.05/0.1/0.2（**结论：增大无效**，与 Q1+/L2 历史一致）
- [x] 非晶质 Al(OH)₃(a) 相实验（2%~20% + SI 欠饱和，**结论：均无法回补**，矿物化单向汇）
- [x] 全量 pytest 102 全绿（非晶质相不破坏 P1-P5 收敛、矿物回填、SURFACE、多层基线）
- [x] 扫描结论记录 `docs/V0_4_0_L9_SCAN.md`（含深层修复方向）
- [x] 保留非晶质 Al(OH)₃(a) 相（红壤真实组分，natural 基线不变 pH 6.46）
- [ ] **未达成**：fertilizer 单层 30 年 AlX₃ 稳定（三种方案均无效）→ 深层修复（Al 交换选择性校准 / Al 矿物化动力学 / 多层+逐层参数）后续立项

## 完成说明（2026-08-14）

**科学结论**：MINERAL_SCALE 参数扫描（0.001→0.2）与非晶质 Al(OH)₃(a) 相（2%~20%、SI=0 与欠饱和）**均无法解决** fertilizer 单层 AlX₃ 耗尽→pH 突升。根因是矿物化沉淀为"单向 Al 汇"（L2 记录）——补充的 Al 被同一汇吸收或排水带走，无法进入交换位点。完整扫描表见 `docs/V0_4_0_L9_SCAN.md`。

**保留非晶质相**：红壤真实组分 + natural 基线不变（pH 6.46）+ 102 测试全绿，作为部分 Al 源保留。

**建议**：fertilizer 情景科学应用使用多层（n_layers≥4，推迟耗尽）+ 记录局限；深层修复（交换选择性/矿物化动力学）列入后续 backlog。

## Background

- v0.3.0 实测：k₂=0.4 弱产酸下 fertilizer 单层 AlX₃ 于 y2m12 耗尽 → pH 突升 10.4
- 根因：Q1+ MINERAL_SCALE=0.001 矿物压缩（无法回补交换 Al）+ Q12* 单层排水
- Q1+ 历史风险：scale 增大（物理量）曾导致碱性突变（pH~9.9）——trade-off 是扫描核心
- grilling Q3=D：参数扫描先行 + 非晶质 Al(OH)₃ 兜底；Q7=A：0.1 成功继续扫描至 1.0

