# 56 — v0.6.0 RainEvent + generate_events（事件生成）

**What to build:** 事件驱动化学的事件数据层：新建 `RainEvent` dataclass（`precip_mm` 单场降水 mm / `duration_h` 历时 h 默认 2.0 / `date_hint` 年·月·场序诊断 / `precip_chem` 可选，None=继承引擎级）放 `src/hydrology.py`；新增 `generate_events(monthly_precip_mm, year, month, seed) -> List[RainEvent]`，复用 `generate_rainfall` 的 seed 派生逻辑（`default_rng(seed + year*12 + month)`），Σ 事件降水 = 月总量（质量守恒不变量）。这是后续 `run_event_step`/主循环嵌套的基础数据契约（spec 55 §1，Q1/Q11）。

**Blocked by:** None — can start immediately（spec 55 已定案）

**Status:** ready-for-agent

- [ ] `RainEvent` dataclass 落位 `src/hydrology.py`：precip_mm/duration_h/date_hint/precip_chem，默认值正确（duration_h=EVENT_HOURS=2.0）
- [ ] `generate_events` 复用 `generate_rainfall` seed 派生，同 seed 同事件序列（可复现测试）
- [ ] 事件数量落在 [4,12] 范围；Σ precip_mm = 月总量（质量守恒不变量测试）
- [ ] 事件降水均为正；单场历时默认 2.0 h（RainEvent.duration_h）
- [ ] 全测试绿（S3 接缝 test_hydrology.py 扩展）
