# 47 — v0.5.2 硝化产酸限 L1（T4）

**What to build:** `run_monthly_multi_layer` 仅 L1（`i==0`）执行 `advance_nitrification`（施肥/尿素水解/硝化/产酸 2H⁺），L2~L4 跳过全部氮过程（氮不随层间传递；完整氮运移留待 v0.6.0 子步长）。修正 4 层 pH 剖面行为（表层酸化源强化、深层不再重复产酸）。

**Blocked by:** None — can start immediately（独立行为修正）

**Status:** ✅ 已完成 (2026-08-18, v0.5.2)

- [x] `run_monthly_multi_layer` 仅 i==0 传递氮过程开关；`_run_official_step` 对非 L1 层跳过 `advance_nitrification`
- [x] 确认 n_urea/n_nh4/n_no3 库存状态对非 L1 层保持 0（不污染状态）
- [x] 更新 4 层 pH 剖面相关测试断言（test_layer_overrides.py 中多层演化测试）
- [x] 测试（S4 seam）：L2~L4 无产酸（n_reaction 空/无 H⁺）、L1 产酸正常、单层路径不变（回归护栏）
