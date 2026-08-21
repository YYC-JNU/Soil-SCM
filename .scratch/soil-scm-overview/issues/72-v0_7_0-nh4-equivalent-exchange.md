# 72 — NH₄⁺ 等效置换 + NH4X_virtual（spec 69 工单 71）

**What to build:** 让氮肥"NH₄⁺ 置换盐基→盐基淋失"的农业酸化通道被近似表达且**不触碰 L4 Q3=A"氮不进溶液"决策**：施肥月尿素水解后（`hydrolyzed = n_urea×k1`，≈857 eq/次），按当前交换相 Ca:Mg:K:Na 电荷占比经 REACTION 注入等当量阳离子到溶液（与硝化 H⁺ 同场平衡，净效应 H⁺ 主导酸化）；`NH4X_virtual` 记账列统计假设占用的交换位点（**不进 EXCHANGE 总量**，CEC 守恒审计与预平衡锚定不受扰）；接受 PHREEQC 自然回吸 + 观测门（`nh4_exchanged_eq` vs 交换相盐基净减，净效率 <50% 触发重新评估告警）；`simulation.companion.nh4_exchange` config 开关。

**Blocked by:** 70（消费 `advance_nitrification` 的 `hydrolyzed` 契约键与池/记账基础设施）。与工单 71 无强制依赖（置换注入为既有物种 Ca/Mg/K/Na，不依赖 CompAn）。

**Status:** ready-for-agent

- [ ] 置换注入：施肥月水解后 `nh4_exchanged_eq = hydrolyzed × 1`，按当前交换相 Ca:Mg:K:Na 电荷占比注入对应阳离子（REACTION），`companion.exchange_ratio` 可选覆盖
- [ ] 与硝化 H⁺ 同场平衡：净效应 H⁺ 主导酸化（pH 方向正确）
- [ ] `NH4X_virtual_L{i}` 记账列输出；CEC 总量守恒测试不破（虚拟占用不进交换）
- [ ] 观测门：`nh4_exchanged_eq_L1` 列 + 净效率 <50% 告警
- [ ] config `simulation.companion.nh4_exchange: true` 解析/校验；`enable: false` 完全回退
- [ ] 现有 289 测试全绿（expand-contract）
