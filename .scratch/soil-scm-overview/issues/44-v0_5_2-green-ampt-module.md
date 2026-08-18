# 44 — v0.5.2 Green-Ampt 入渗模块（T1）

**What to build:** 在 `src/hydrology.py` 中新增 Green-Ampt 物理入渗替代 Horton + `surface_coeff`：`green_ampt_infiltration(precip_mm, Ks_cm_day, psi_f_mm, theta_s, theta_i, hours)` 用牛顿迭代解隐式方程；`monthly_hydrology` 改调 Green-Ampt（逐场），月入渗 = Σ场次入渗，月径流 = 月降水 − 月入渗；删除 `horton_event_infiltration` 与 `HORTON_DECAY_K_PER_H`；`surface_coeff` 参数全部移除。

**Blocked by:** None — can start immediately（spec 43 已定案）

**Status:** ✅ 已完成 (2026-08-18, v0.5.2)

- [x] 新增 `green_ampt_infiltration`：隐式方程 F − ψ_f·Δθ·ln(1+F/(ψ_f·Δθ)) = K_s·t，牛顿迭代求解（手算验证数值）
- [x] K_s 单位换算 cm/day→mm/h；θ_s 用 L1 porosity；θ_i 由 stored_water 换算（初始 50% 饱和 → θ_i=0.5×θ_s）
- [x] ψ_f 默认 150mm（constants 常量，可配）；场次历时保持 EVENT_HOURS=2
- [x] `monthly_hydrology` 改调 Green-Ampt（逐场循环），返回 (infiltration_mm, runoff_mm, events)
- [x] 删除 `horton_event_infiltration` + `HORTON_DECAY_K_PER_H`；`surface_coeff` 参数从函数签名移除
- [x] 测试（S1 seam，先例 test_hydrology.py）：Green-Ampt 手算数值、降雨强度>K_s 触发产流、月守恒（入渗+径流=降水）、seed 可复现
