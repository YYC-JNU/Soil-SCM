# 59 — v0.6.0 main 事件编排 + First-Flush 输出

**What to build:** 主程序事件化编排与脉冲淋失输出（spec 55 §4/§5，Q3/Q14/Q15）：`main._apply_hydrology_month` 扩展为事件级编排——月首 ET 一次（Feddes 复用）+ 逐场 Green-Ampt 入渗（θ_i 逐场更新）+ 逐场层间级联（复用 LayerCascade）+ 逐场 bypass（Q15），返回含 `events` 键的 hydrology dict；主循环传 `run_monthly_multi_layer`。First-Flush 输出：月度主 CSV 新增峰值列 `flush_NO3_peak_mmol`/`flush_base_peak_mmol`（当月 L1 各场淋失 max，默认开）；config 新增 `output.event_output: false`（默认关）→ 开启时输出事件明细 CSV `output/event_leaching_<scenario>.csv`（事件日期/月/各层淋失 mol/ha/事件 pH）。

**Blocked by:** 56 — RainEvent + generate_events；57 — run_event_step + 体积-θ 耦合；58 — run_monthly_step 包装 + 多层 events 路径

**Status:** ready-for-agent

- [ ] `_apply_hydrology_month` 逐场编排：月首 ET + 逐场 Green-Ampt（θ_i 逐场）+ 逐场级联 + 逐场 bypass；返回 `events` 键
- [ ] 事件级 `inflows/drains/bypass_water_L` 与月聚合值一致（月水文不变量）
- [ ] 月度峰值列 `flush_NO3_peak_mmol`/`flush_base_peak_mmol` = 当月 L1 各场淋失 max（S6 接缝）
- [ ] `output.event_output=true` 时事件明细 CSV 生成（列结构：日期/月/层/淋失/pH）；`false`（默认）不产生文件
- [ ] 单层护栏：n_layers=1 事件化行为一致（冒烟）
- [ ] 全测试绿（S6 接缝 test_multilayer_output.py + 新增 test_output_writer.py）
