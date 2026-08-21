# 70 — NO₃⁻ 示踪池 + 水库串联淋失 + bypass 携带（spec 69 工单 70a）

**What to build:** 让硝态氮以逐层示踪池显式建模并随排水真实淋失：`n_no3_pool` 入 SoilState，`advance_nitrification` 硝化量同步入池（返回契约扩展 `hydrolyzed/nitrified` 键）；逐场逐层水库串联淋失——垂直排水按比例下移池（体积自然稀释）、侧向/基流携出池余额（出系统）、bypass 优先流携带 L1 池 NO₃⁻ 直通 L2；全局不变量 `lost = min(公式量, pool)`（`pool ≥ 0`）；`n_no3_pool_L{i}`/`leach_no3_L{i}_mol` 记账列；`simulation.companion.enable/bypass_no3_carry` config 开关（关闭=完全回退 v0.6.1）。这是 v0.7.0 的**地基**——后续工单 71（CompAn 伴随淋失）与 72（NH₄⁺ 置换）都消费本工单的池输出。

**Blocked by:** None — can start immediately（spec 69 决策 Q12=A/Q16=D/Q19 已定案）。

**Status:** ✅ 已完成 (2026-08-21, v0.7.0)

- [x] `SoilState.n_no3_pool` 字段 + `advance_nitrification` 同步入池（`n_no3` 累计器向后兼容），返回契约扩展 `nitrified/hydrolyzed` 键，既有 `{'H+': ...}` 键不变
- [x] `lost_no3` 纯函数：逐层水库串联（垂直下移 `min(pool×drains/V_pool, pool)`、出系统 `min(pool×(lateral+baseflow)/V_pool, pool)`）
- [x] **全局不变量**：所有出口通道 `lost = min(公式量, pool)`，单元测试含干旱期 V_pool 极小、Q/V 远超 1 的极端用例，`pool ≥ 0` 恒成立
- [x] bypass 携带：`m_bypass = min(pool_L1×bypass_water_L/V_pool_L1, pool_L1)`，pool_L1 减、pool_L2 加、计入该场 L1 淋失；bypass 水仍携带原始降水化学（现状不动）
- [x] 记账列 `n_no3_pool_L{i}`/`leach_no3_L{i}_mol`（event_details + 月度诊断聚合）
- [x] config `simulation.companion.{enable: true, bypass_no3_carry: true}` 解析/校验；`enable: false` 完整回退 v0.6.1（回归护栏）
- [x] 现有 289 测试全绿（expand-contract，仅新增断言；**301 passed**）
