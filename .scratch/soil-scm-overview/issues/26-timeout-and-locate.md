# 26 — 子进程超时机制 + 卡顿定位

**What to build:** run_monthly_step 的 PHREEQC 调用封装为 multiprocessing 子进程（超时 10s 强制终止），保存卡顿步输入（error.inp），返回降级信号；定位脚本扫描 fertilizer 30 年，确认卡顿机制（迭代振荡 vs 子步爆炸）。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] 月度步子进程超时封装（10s 终止，返回降级信号）
- [ ] 卡顿步输入保存（error.inp 复用）+ 日志
- [ ] 定位脚本：30 年扫描记录卡顿步（年/月/状态特征），多次复现
- [ ] 机制确认（迭代振荡 / 子步爆炸 / 状态困难区）记录

## Background

- v0.6.0 KINETICS 偶发卡顿（非确定），error.inp 只捕获异常
- grilling Q1=a（迭代振荡假设）/ Q2=A（子进程超时定位）
