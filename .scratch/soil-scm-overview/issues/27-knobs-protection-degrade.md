# 27 — KNOBS 调参 + 状态防护 + 超时降级兜底

**What to build:** 三层防御——KNOBS 收敛容差放宽（1e-12→1e-9）+ 状态防护（矿物量下限/pH 界限/溶液下限）+ 超时降级兜底（卡顿步降级 simplified/沿用状态 + 计数 + 日志），保证流程永不卡死。

**Blocked by:** 26 — 子进程超时机制 + 卡顿定位

**Status:** ready-for-agent

## Acceptance criteria

- [ ] KNOBS -tolerance 1e-12 → 1e-9（参数化，评估精度损失）
- [ ] 状态防护：矿物量下限（防除零）、pH 界限（已有）、溶液浓度下限
- [ ] 超时降级：卡顿步 → simplified/沿用状态 + 降级计数 + 日志
- [ ] 全量测试绿（分块验证）

## Background

- grilling Q3=D（组合防御）、定位结论决定主次
- 若定位为子步爆炸：KINETICS 步长控制（-steps/-step_divide）纳入
