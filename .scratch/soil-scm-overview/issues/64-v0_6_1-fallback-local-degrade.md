# 64 — v0.6.1 fallback 事件级局部降级

**What to build:** 将"单场单层 PHREEQC 失败 → 全局永久降级简化模式"（v0.5.3 契约）升级为**事件级局部降级**：单场失败保留前一正常状态跳过该场化学（不调 simplified），连续 3 次失败才永久降级；失败计数事件/月级路径分开；每次失败落盘 error.inp。使 50 年模拟不被单层单场偶发失败永久降级、数值问题可复现可审计。

**Blocked by:** None — can start immediately（依赖 spec 62 决策表 Q5，2026-08-20 定案）。

**Status:** ready-for-agent

- [ ] `_run_official_step` 失败处理改为连续计数：`_consecutive_failures_event` / `_consecutive_failures_monthly` 两个计数器（事件/月级路径分开）
- [ ] 失败场行为：保留前一正常状态（不调 `_run_simplified_step`）跳过该场化学 + error.inp 每次落盘 + 计数 +1
- [ ] 连续失败数 ≥ FALLBACK_MAX_CONSECUTIVE=3（`constants.py` 新增）→ 永久降级（既有 `_permanent_fallback=True` 语义）
- [ ] 单次成功重置对应路径的失败计数（滑动窗口语义）
- [ ] 测试（S3）：前 1~2 次失败保留状态跳过不降级、第 3 次永久降级、失败计数事件/月级分离、成功后计数重置、`test_error_diagnostics_on_failure` 等契约测试按 Q5 修订
