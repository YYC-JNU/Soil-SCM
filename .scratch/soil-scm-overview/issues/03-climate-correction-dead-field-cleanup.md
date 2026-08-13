# 03 — 气候修正机制收敛 + MonthlyAction 死字段清理

**What to build:** 明确气候修正（降水/温度递增）的单一职责归属，并移除 `MonthlyAction` 中从未被赋值或读取的降水/温度修正字段。当前 `precip_increase` / `temp_increase` 情景的修正完全由气候强迫生成器承担，但月度操作指令对象上还残留两个永不生效的字段（`precip_factor`、`temp_offset`），构成死代码并误导读者以为情景可叠加。同步更新 spec 中相关用户故事（US28）的表述，消除"气候情景与施肥石灰操作可叠加"的虚假承诺。

**Blocked by:** None — can start immediately.

**Status:** ✅ 已完成 (implemented via /implement)

## 完成说明 (2026-08-13)

**决策**：气候修正保持由气候强迫生成器（ClimateForcing）承担——单一职责、机制清晰。不采用"回填 MonthlyAction 使情景可叠加"方案（属更大改动，如需另行成单）。

**改动内容**：
1. 移除 `MonthlyAction.precip_factor` / `temp_offset` 死字段，更新模块 docstring 说明气候修正归属。
2. 新增回归测试 `test_no_dead_climate_correction_fields`（TDD 红→绿），锁定字段不再存在。
3. spec（01-core-overview-spec.md）4 处更新：US28、情景-动作分离、领域词汇"情景操作"、S2 测试接缝描述，全部与"气候修正由气候强迫承担"的实际机制一致。

**验证**：完整测试套件 61 passed（含新增测试）；src/ 与 tests/ 无死字段残留引用。

## Background（审查发现 P2 + S1）

- 审查发现：`MonthlyAction.precip_factor` / `temp_offset` 字段在 `get_action()` 中从未赋值，代码库中从未被读取。
- `precip_increase` / `temp_increase` 情景在情景控制器中直接 `pass`，实际修正由气候强迫生成器在生成逐月序列时完成。
- spec（01-core-overview-spec.md US28）承诺"月度操作指令包含降水/温度修正系数，so that 气候情景与施肥石灰操作可叠加"——与实际机制不符，属于 Spec 偏差。

## 决策点（需先确认，再实现）

**气候修正归属决策**：气候修正保持由气候强迫生成器承担（现状，推荐——单一职责、机制清晰），还是回填到月度操作指令（使情景可叠加）？本工单默认采用前者（保持现状归属），仅清理死字段并修正文档；若决定后者则需扩展情景组合逻辑，属于更大改动，应另行成单。

## 行为要求

1. 移除 `MonthlyAction` 中永不生效的 `precip_factor`、`temp_offset` 字段（若决策为保持气候强迫单一归属）。
2. 确保移除后无任何代码引用这些字段，测试保持全绿。
3. 更新 spec（01-core-overview-spec.md）中 US28 及相关 Implementation Decisions 表述，使文档与实际机制一致（气候修正由气候强迫承担，不通过月度操作指令叠加）。

## Acceptance criteria

- [ ] `MonthlyAction` 中死字段已移除，代码库无残留引用
- [ ] 全部测试套件保持全绿（含情景控制器相关测试）
- [ ] spec 中 US28 / Implementation Decisions 已更新为与实际机制一致
- [ ] 决策（气候修正归属）已明确记录在工单完成说明中
