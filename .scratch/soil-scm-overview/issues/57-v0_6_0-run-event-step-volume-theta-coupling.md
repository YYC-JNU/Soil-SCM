# 57 — v0.6.0 run_event_step + 化学溶液体积-θ 耦合

**What to build:** 事件级化学核心引擎接口（spec 55 §2，Q1/Q3/Q5/Q6/Q15）：`PhreeqcEngine.run_event_step(state, event, action, profile) -> (SoilState, DiagnosticOutput)`——单场事件一次全量 PHREEQC；**体积-θ 耦合（Q8b）**：`SOLUTION -water = θ_事件后×depth×1e5`（复用 `vgm.theta_to_water_L`），REACTION 只注入该场净入渗水量与化学；交换相/矿物相绝对摩尔量不变；层间溶质逐场传递契约（上层排水溶质→下层当场 `inflow_ions`）。新增 `apply_concentration_equilibrium(state, theta, depth, forcing)`：月末浓缩平衡（θ 下降才触发，仅 `-water` 重建、无 REACTION）。溶液浓度下限 `1e-10 mol/L` 统一施加（数值稳定性，v0.7.0 文档 §三.3 预留）。

**Blocked by:** 56 — RainEvent + generate_events

**Status:** ✅ 已完成 (2026-08-19, v0.6.0)

- [x] `run_event_step` 事件级 forcing 契约：precip（单场）/inflow_water_L/bypass_water_L/inflow_ions/temp/pCO2/skip_nitrification/injection
- [x] 体积-θ 重建：`-water` = θ_事件后×depth×1e5（数值断言，S2 接缝）+ 浓度按绝对量守恒换算（C_new = C_old×V_old/V_new）
- [x] 交换相/矿物相绝对摩尔量不变（仅溶液体积随 θ 变化）
- [x] `apply_concentration_equilibrium`：θ 下降触发浓缩平衡、θ 不变跳过（零额外计算）
- [x] 浓度下限 `1e-10 mol/L` 施加于 `_build_phreeqc_input`
- [x] 全测试绿（S2 接缝新 test_event_chemistry.py）；**244 passed 全绿**
