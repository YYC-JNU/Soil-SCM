# 64 — v0.6.1 fallback 事件级局部降级

**What to build:** 将"单场单层 PHREEQC 失败 → 全局永久降级简化模式"（v0.5.3 契约）升级为**事件级局部降级**：单场失败保留前一正常状态跳过该场化学（不调 simplified），连续 3 次失败才永久降级；失败计数事件/月级路径分开；每次失败落盘 error.inp。使 50 年模拟不被单层单场偶发失败永久降级、数值问题可复现可审计。

**Blocked by:** None — can start immediately（依赖 spec 62 决策表 Q5，2026-08-20 定案）。

**Status:** ✅ 已完成 (2026-08-20, v0.6.1)

- [x] `_run_official_step` 失败处理改为连续计数：`_consecutive_failures_event` / `_consecutive_failures_monthly`（事件/月级路径分开，`path` 参数）
- [x] 失败场行为：保留前一正常状态（不调 `_run_simplified_step`）跳过该场化学 + error.inp 每次落盘 + 计数 +1；返回 `(state, None)`
- [x] 连续失败数 ≥ FALLBACK_MAX_CONSECUTIVE=3（`constants.py`）→ 永久降级（既有 `_permanent_fallback=True` 语义）
- [x] 单次成功重置对应路径的失败计数（滑动窗口语义）
- [x] 测试（S3）：前 2 次失败保留状态跳过不降级（`test_error_diagnostics_on_failure` 修订）、第 3 次永久降级、事件/月级计数分离（`test_fallback_event_path_counts_separately`）、成功后重置（`test_fallback_reset_on_success`）、error.inp 写入失败不影响流程（`test_error_write_failure_does_not_break_flow` 修订）；**281 passed 全绿**
