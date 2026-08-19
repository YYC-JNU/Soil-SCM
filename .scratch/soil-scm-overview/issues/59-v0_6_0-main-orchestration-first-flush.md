# 59 — v0.6.0 main 事件编排 + First-Flush 输出

**What to build:** 主程序事件化编排与脉冲淋失输出（spec 55 §4/§5，Q3/Q14/Q15）：`main._apply_hydrology_month` 扩展为事件级编排——月首 ET 一次（Feddes 复用）+ 逐场 Green-Ampt 入渗（θ_i 逐场更新）+ 逐场层间级联（复用 LayerCascade）+ 逐场 bypass（Q15），返回含 `events` 键的 hydrology dict；主循环传 `run_monthly_multi_layer`。First-Flush 输出：月度主 CSV 新增峰值列 `flush_NO3_peak_mmol`/`flush_base_peak_mmol`（当月 L1 各场淋失 max，默认开）；config 新增 `output.event_output: false`（默认关）→ 开启时输出事件明细 CSV `output/event_leaching_<scenario>.csv`（事件日期/月/各层淋失 mol/ha/事件 pH）。

**Blocked by:** 56 — RainEvent + generate_events；57 — run_event_step + 体积-θ 耦合；58 — run_monthly_step 包装 + 多层 events 路径

**Status:** ✅ 已完成 (2026-08-19, v0.6.0)

- [x] `_apply_hydrology_events` 逐场编排：月首 ET + 逐场 Green-Ampt（θ_i 逐场）+ 逐场级联（排水窗=月/场次）+ 逐场 bypass；返回 `events` 键 + 月聚合键
- [x] 事件级 `inflows/drains/bypass_water_L` 与月聚合值一致（月水文不变量测试）
- [x] 月度峰值列 `flush_NO3_peak_mmol`/`flush_base_peak_mmol` = 当月 L1 各场淋失 max（S6 接缝）
- [x] `output.event_output=true` 时事件明细 CSV 生成（列结构：日期/月/层/淋失/pH）；`false`（默认）不产生文件
- [x] 单层护栏：n_layers=1 事件化行为一致（`event_driven` 走 run_monthly_step 内部事件化）
- [x] 全测试绿（S6 接缝 test_output_writer.py 新增 + test_multilayer_output.py + test_event_chemistry.py）；**259 passed 全绿**
