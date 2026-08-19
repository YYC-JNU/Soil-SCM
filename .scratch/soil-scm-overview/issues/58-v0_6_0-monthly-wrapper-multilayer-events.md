# 58 — v0.6.0 run_monthly_step 月度聚合包装 + 多层 events 路径

**What to build:** expand-contract 核心（spec 55 §3/§4，Q10/Q4）：`run_monthly_step` 签名与返回契约不变，内部升级为"月内逐场循环 + 月末浓缩平衡 + 月内淋失聚合"（调用方 main/多层级联/既有测试**零改动**，现有 234 测试不破门禁）。`run_monthly_multi_layer` 接口不变，`hydrology` dict 新增**可选 `events` 键**（`List[dict]`，每场含 `inflows/drains/bypass_water_L`）→ 内部逐场逐层级联（for event: for layer: `run_event_step`，层间溶质事件粒度传递，Q4 First-Flush 本质）；无 `events` 键走旧月级路径（向后兼容护栏）。

**Blocked by:** 56 — RainEvent + generate_events；57 — run_event_step + 体积-θ 耦合

**Status:** ✅ 已完成 (2026-08-19, v0.6.0)

- [x] `run_monthly_step` 事件化包装（`event_driven=True` 触发）：内部 `generate_events` → 逐场 Green-Ampt+θ 更新 → `run_event_step` → 月末浓缩平衡；签名/返回契约不变
- [x] 现有 234 测试**一字不改全部通过**（expand-contract 门禁，S1 接缝）；无 `event_driven` 标记回退旧单次平衡（预平衡不受影响）
- [x] 新增"月内事件聚合"不变量测试：Σ事件降水=月降水、月末状态=最后事件状态（S1 扩展）
- [x] `run_monthly_multi_layer` `events` 路径：逐场逐层级联（上层事件排水→下层当场，S5 接缝）
- [x] 无 `events` 键回退旧月级路径（护栏测试）
- [x] bypass 逐场注入 L2（事件粒度，S5 扩展）
- [x] 全测试绿（S1/S5 接缝）；**248 passed 全绿**
