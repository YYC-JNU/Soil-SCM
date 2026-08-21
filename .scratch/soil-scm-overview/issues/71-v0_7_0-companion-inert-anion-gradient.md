# 71 — 惰性阴离子 + 伴随淋失分级注入（spec 69 工单 70b）

**What to build:** 让 NO₃⁻ 淋失携带等当量盐基（真实农业酸化核心机制）且**不手工改交换相**：定义自定义保守惰性阴离子（`inert_anion` 元素名默认 `An`，`SOLUTION_MASTER_SPECIES`/`SOLUTION_SPECIES`，log_k=0、不参与氧化还原，注入 PHREEQC 输入头段，不碰 phreeqc.dat）；每层随 NO₃⁻ 移出的盐基当量 `E_loss = lost_no3 × 1` 经 REACTION 注入 An⁻（进平衡前注），交换相盐基解吸由 PHREEQC 平衡自洽完成（Gapon 哲学保留）；按盐基饱和度分级注入——BS≥30 全量 / 10~30 线性衰减 / <10 切换酸化注入 H⁺（等当量）+ 盐基枯竭警告；`companion_mode/inert_eq/acid_eq` 记账列；与 v0.6.1 Q3 溶液比例扣除**正交互补**（不双重计数）。

**Blocked by:** 70（消费 `n_no3_pool`/`leach_no3` 池输出与 `advance_nitrification` 契约）。

**Status:** ✅ 已完成 (2026-08-21, v0.7.0)

- [x] 惰性阴离子物种定义注入输入头段 + SELECTED_OUTPUT 含 An；PHREEQC 实测平衡：An 保守示踪（平衡后按水量守恒）、交换相 Ca/Mg/K/Na 响应解吸
- [x] `E_loss = lost_no3 × 1 eq/mol` 计算，REACTION 注入 An⁻（进平衡前，跨场滚动：本场淋失→下场注入）
- [x] BS 分级三态：BS≥30 全量 / 10≤BS<30 线性衰减 `×(BS−10)/20` / BS<10 酸化注入 H⁺=E_loss eq + `companion_mode=acid` + 警告；BS 取各层动态盐基饱和度（与既有诊断同公式 `calc_base_saturation`）
- [x] 记账列 `companion_eq_L{i}`/`companion_mode_L{i}`/`inert_eq_L{i}`/`acid_eq_L{i}`
- [x] 与 Q3 正交互补：An⁻ 注入（平衡前 REACTION）与 `frac_out` 溶液扣除（平衡后）分开记账，`companion_eq` 基于 NO₃⁻ 淋失当量（非 Q3 溶液扣除量）
- [x] config `simulation.companion.{bs_high: 30, bs_low: 10, inert_anion: "An"}` 解析/校验（0<bs_low<bs_high≤100）；`enable: false` 完全回退
- [x] 现有 289 测试全绿（expand-contract；**307 passed**）

> ⚠️ **PHREEQC 元素名约束**（实现中发现）：`SOLUTION_MASTER_SPECIES` 元素名必须为单元素（`CompAn` 会拆为 Comp+An 报错），故惰性阴离子元素名默认 `An`、物种 `An-`，`inert_anion` config 可配（须为单元素名）。
