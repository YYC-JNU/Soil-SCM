# 71 — CompAn 惰性阴离子 + 伴随淋失分级注入（spec 69 工单 70b）

**What to build:** 让 NO₃⁻ 淋失携带等当量盐基（真实农业酸化核心机制）且**不手工改交换相**：定义自定义保守惰性阴离子 `CompAn`（`SOLUTION_MASTER_SPECIES`/`SOLUTION_SPECIES`，log_k=0、不参与氧化还原，注入 PHREEQC 输入头段，不碰 phreeqc.dat）；每层随 NO₃⁻ 移出的盐基当量 `E_loss = lost_no3 × 1` 经 REACTION 注入 CompAn（进平衡前注），交换相盐基解吸由 PHREEQC 平衡自洽完成（Gapon 哲学保留）；按盐基饱和度分级注入——BS≥30 全量 / 10~30 线性衰减 / <10 切换酸化注入 H⁺（等当量）+ 盐基枯竭警告；`companion_mode/inert_eq/acid_eq` 记账列；与 v0.6.1 Q3 溶液比例扣除**正交互补**（不双重计数）。

**Blocked by:** 70（消费 `n_no3_pool`/`leach_no3` 池输出与 `advance_nitrification` 契约）。

**Status:** ready-for-agent

- [ ] CompAn 物种定义注入输入头段 + SELECTED_OUTPUT 含 CompAn；PHREEQC 实测平衡：CompAn 保守示踪（平衡后浓度按水量守恒）、交换相 Ca/Mg/K/Na 响应解吸
- [ ] `E_loss = lost_no3 × 1 eq/mol` 计算，REACTION 注入 CompAn（进平衡前）
- [ ] BS 分级三态：BS≥30 全量 / 10≤BS<30 线性衰减 `×(BS−10)/20` / BS<10 酸化注入 H⁺=E_loss eq + `companion_mode=acid` + 警告；BS 取各层动态盐基饱和度（复用既有诊断）
- [ ] 记账列 `companion_eq_L{i}`/`companion_mode_L{i}`/`inert_eq_L{i}`/`acid_eq_L{i}`
- [ ] 与 Q3 正交互补验证：CompAn 注入（平衡前）与 `frac_out` 溶液扣除（平衡后）两笔账分开记账，`water_salt_balance` 盐基行不重复
- [ ] config `simulation.companion.{bs_high: 30, bs_low: 10}` 解析/校验（0<bs_low<bs_high≤100）；`enable: false` 完全回退
- [ ] 现有 289 测试全绿（expand-contract）
