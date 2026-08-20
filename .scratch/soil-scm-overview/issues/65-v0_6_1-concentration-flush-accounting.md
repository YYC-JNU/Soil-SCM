# 65 — v0.6.1 浓度硬上限冲洗 + 溶质出口记账

**What to build:** 在 `run_event_step` 化学平衡后，实现**溶质随水移出系统**的完整记账：① 侧向/基流排水按 `Q_out/V` 比例从 `state.solution` 扣除溶质（`n_new=max(n_old×(1−Q_out/V), C_min×V)`，C_min=1e-10）；② 某层 max 离子浓度超 `C_warn=0.5 mol/L` 时触发**冲洗=基流/侧向激增**（Q_flush 折算 + 同比例溶质扣除）；③ 出口溶质记入 `event_details` 与 `total_lateral_i`/`total_base_i`/`flush_L` 诊断列。使每一个水分出口都对应盐分移出（对治"只排水不排盐"），极端盐分累积有物理式加速出口、质量守恒记账完整。

**Blocked by:** 63（VIC 深层基流 + Darcy 侧向排水模块）— 溶质扣除需要 Q_lat/Q_base 水量来源。

**Status:** ✅ 已完成 (2026-08-20, v0.6.1)

- [x] `_run_multi_layer_events` 逐层平衡后新增溶质比例扣除：侧向/基流出口按 `n_new=max(n_old×(1−Q_out/V), C_min×V)`（C_min=1e-10）更新 `state.solution`
- [x] 交换相不动（靠下场/下月平衡 Gapon 自动解吸补偿）
- [x] 冲洗机制：事件后某层 max 离子浓度 > C_warn=0.5 mol/L → 折算 Q_flush（`flush_L` 列）并按同比例扣溶质（质量守恒）
- [x] 出口记账：event_details 增 `lateral_Li_L`/`baseflow_Li_L`/`flush_Li_L`；main `_extract_diagnostics_with_hydrology` 增 `baseflow`/`lateral` 月度列
- [x] 与既有 `inflow_ions`（垂直排水进下层）语义区分：lateral/base 溶质移出系统
- [x] 测试（S2/S6）：比例扣除数学恒等、C_min 下限保护、C_warn 触发 flush 激增、正常浓度不触发、诊断列输出；**285 passed 全绿**
