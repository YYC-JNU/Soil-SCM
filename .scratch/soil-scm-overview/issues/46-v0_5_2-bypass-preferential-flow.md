# 46 — v0.5.2 大孔隙优先流 bypass（T3）

**What to build:** 新增 `simulation.bypass_fraction=0.2`（config，0~1 校验）：超过基质 K_s 的地表积水中 β=20% 作为优先流绕过 L1 注入 **L2**，**携带原始降水化学**（非 L1 平衡溶液、非纯水）。`main._apply_hydrology_month` 返回优先流水量；`run_monthly_multi_layer` 对 L2 额外注入优先流水量 + 降水化学；质量守恒核算扩展。

**Blocked by:** 44、45

**Status:** ✅ 已完成 (2026-08-18, v0.5.2)

- [x] `SimulationConfig.bypass_fraction = 0.2` + 校验（0~1）
- [x] `main._apply_hydrology_month`：返回优先流水量（径流水量 × β）与注入层位置（L2）
- [x] `run_monthly_multi_layer`：对 L2 额外注入优先流水量 + 原始降水化学（同 L1 入渗化学口径）
- [x] 质量守恒：月降水 = L1 入渗 + 地表径流（含优先流）；优先流水量/化学计入降水总量核算（Q7 平流守恒口径扩展）
- [x] 测试（S4/S5 seam）：优先流注入 L2 且水量守恒（β×径流）、携带降水化学、L1 不受影响
