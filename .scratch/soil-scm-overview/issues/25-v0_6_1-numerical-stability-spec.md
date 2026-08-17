# 25 — v0.6.1 数值稳定性 spec（KINETICS 偶发卡顿定位与解决）

**What to build:** 解决 v0.6.0 Al 动力学（KINETICS）引入的长期模拟偶发 PHREEQC 卡顿（RunString 不返回，非确定）——子进程超时定位 + KNOBS/防护调参 + 超时降级兜底，使 30 年 fertilizer 模拟可完成。工单 26-28 由本 spec 拆分。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

---

## Problem Statement

v0.6.0 KINETICS 后 5 年+ fertilizer 模拟偶发卡顿（非确定：同输入有时快有时卡）。30 年验收受阻，Al 动力学长期效果无法定论。现有 error.inp 只捕获异常，捕获不到卡顿。

## Solution

- 子进程超时定位（10s 终止，保存卡顿步输入，确认机制）
- KNOBS 容差放宽（1e-12→1e-9）+ 状态防护（矿物下限/pH 界限）
- 超时降级兜底（卡顿步降级 simplified/沿用状态 + 日志，流程永不卡死）
- 验收：优先完整（30 年无降级步）；降级则文档记录原因（定位结论）

## User Stories

1. 作为土壤学家，我希望 30 年 fertilizer 模拟不被卡顿中断。
2. 作为模型开发者，我希望卡顿精确定位（年/月/输入）。
3. 作为模型开发者，我希望卡顿不阻塞流程（降级兜底）。
4. 作为研究者，我希望 KNOBS/防护减少振荡（完整验收）。
5. 作为研究者，我希望降级验收说明原因（科学诚实）。
6. 作为模型开发者，我希望卡顿步输入可复现。
7. 作为土壤学家，我希望降级步结果偏差被评估。
8. 作为模型开发者，我希望全量测试保持绿。
9. 作为研究者，我希望方案文档化（V0_6_1_REPORT）。
10. 作为模型开发者，我希望 KINETICS 长期效果在验收后定论。

## Implementation Decisions

- 子进程超时：月度步封装 multiprocessing，超时终止 + 输入保存 + 降级返回
- KNOBS：-tolerance 1e-12→1e-9，-iterations 保持 1000
- 状态防护：矿物量下限、pH 界限（已有）、溶液浓度下限
- 超时降级：卡顿步 → simplified/沿用状态 + 日志 + 降级计数
- 定位脚本：30 年扫描记录卡顿步特征

## Testing Decisions

- 接缝：run_monthly_step + 子进程超时封装
- 测试：超时触发、降级兜底、KNOBS 参数化、状态防护、E2E 30 年
- 先例：v0.6.0 E2E、test_al_kinetics、error.inp 机制

## Out of Scope

- KINETICS 算法级优化（若定位为子步爆炸则部分纳入）
- L6/L7/L8、KINETICS 性能加速

## Further Notes

- 降级原因必须基于定位结论，不得含糊
- 降级步结果偏差需评估
- 方案与结论写入 docs/V0_6_1_REPORT.md
