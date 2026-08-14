# 06 — L4 氮循环库存层引擎修正与测试

**What to build:** 施肥氮的化学效应以"硝化产酸"真实进入溶液，而 NH₄⁺/NO₃⁻ 形态由模型库存独立追踪、不再被 PHREEQC 的 N₂ 平衡吞没。施肥月 REACTION 只含硝化产酸 `H+`（无 NH₄⁺/NO₃⁻ 注入），月度步后氮库存（尿素/NH₄⁺/NO₃⁻）由水解与硝化推进、不被溶液输出覆盖清零，全量测试保持绿色。

**Blocked by:** None — can start immediately.

**Status:** ✅ 已完成 (2026-08-14, via /implement)

## 完成说明

1. `advance_nitrification` 返回契约收紧为 `{'H+': 2×硝化量}`（Q1=A 库存层）。
2. REACTION 只注入硝化产酸 H+；NH₄⁺/NO₃⁻ 不再注入（phreeqc.dat N→N₂ 实测约束）。
3. `_parse_official_output` 不再用溶液 N(-3)/N(5) 覆盖库存——库存由模型推进（Q4=A）。
4. SELECTED_OUTPUT 移除 N(-3)/N(5)，总 N 保留供层间平流。
5. 测试更新：`test_nitrification.py` 适配新契约 + REACTION 酸注入断言；`test_phreeqc_engine.py` 恢复 totals 行断言。

**验证**：完整测试套件 102 passed（85 基线 + 12 L4 + 5 L5）。

## Acceptance criteria

- [x] 施肥月 REACTION 含 `H+ = 2×硝化量`，且不含 `NH4+`/`NO3-` 注入行
- [x] 月度步后 `n_nh4`/`n_no3` 由 `advance_nitrification` 推进，不被溶液输出覆盖
- [x] SELECTED_OUTPUT 移除 `N(-3)`/`N(5)`（总 `N` 保留供层间平流）
- [x] `advance_nitrification` 返回契约收紧为 `{'H+': ...}`，调用方与测试同步
- [x] 全量 pytest 通过（含更新的 L4 测试断言）

## Background

- grilling 共识（Q1=A/Q3=A/Q4=A/Q5=A）：NH₄⁺/NO₃⁻ 不注入 PHREEQC 溶液平衡（实测 phreeqc.dat 将其全平衡为 N₂）；硝化产酸 2H⁺ 注入 REACTION；`n_no3` 为累计硝化量；库存仅统计施肥氮。
- 当前 act-mode 已实现版本向 REACTION 注入 NH₄⁺/NO₃⁻ 且用溶液 N(-3)/N(5) 覆盖库存——与本工单目标方向相反，需修正。

