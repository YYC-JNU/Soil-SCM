# 65 — v0.6.1 浓度硬上限冲洗 + 溶质出口记账

**What to build:** 在 `run_event_step` 化学平衡后，实现**溶质随水移出系统**的完整记账：① 侧向/基流排水按 `Q_out/V` 比例从 `state.solution` 扣除溶质（`n_new=max(n_old×(1−Q_out/V), C_min×V)`，C_min=1e-10）；② 某层 max 离子浓度超 `C_warn=0.5 mol/L` 时触发**冲洗=基流/侧向激增**（Q_flush 折算 + 同比例溶质扣除）；③ 出口溶质记入 `event_details` 与 `total_lateral_i`/`total_base_i`/`flush_L` 诊断列。使每一个水分出口都对应盐分移出（对治"只排水不排盐"），极端盐分累积有物理式加速出口、质量守恒记账完整。

**Blocked by:** 63（VIC 深层基流 + Darcy 侧向排水模块）— 溶质扣除需要 Q_lat/Q_base 水量来源。

**Status:** ready-for-agent

- [ ] `run_event_step` 化学平衡后新增溶质比例扣除：对 Q_lat（各层）与 Q_base（L4）按 `n_new=max(n_old×(1−Q_out/V), C_min×V)` 更新 `state.solution`（`constants.py` 新增 `C_MIN=1e-10`）
- [ ] 交换相不动（靠下场/下月平衡 Gapon 自动解吸补偿）
- [ ] 冲洗机制：事件后某层 max 离子浓度 > `C_warn=0.5 mol/L`（`constants.py` 新增）→ 超出部分折算额外 Q_flush（基流/侧向激增），按同比例扣溶质，记入 `flush_L` 诊断列
- [ ] 出口记账：`total_lateral_i`/`total_base_i`/`flush_L` 逐月诊断列（output_writer）+ event_details 事件明细 CSV 扩列
- [ ] 与既有 `inflow_ions`（垂直排水进下层）语义区分：lateral/base 溶质移出系统（不进任何层）
- [ ] 测试（S2/S6）：比例扣除数学恒等、C_min 下限保护、C_warn 触发 flush 激增、诊断列/事件 CSV 扩列、垂直 vs 侧向/基流出口语义区分
