# Soil-SCM v0.2.4 工单验收汇总报告

> **文档编号**：TICKET-SUMMARY  
> **创建日期**：2026-08-13  
> **对应版本**：v0.2.4  
> **来源**：`.scratch/soil-scm-overview/` 本地工单（T01/T02/T04，基于 `/to-spec` 生成的 spec 与 `/code-review` 审查发现拆分）

---

## 1. 概述

本报告汇总 v0.2.4 完成的三张工程工单（T01/T02/T04），全部经由 `/implement` 驱动、`/tdd` 红绿循环验证、`/code-review` 双轴审查后提交。

| 指标 | 数值 |
|------|------|
| 完成工单 | 3（T01 / T02 / T04） |
| 测试用例 | 60 → **62**（+2） |
| 代码净减少 | **123 行**（重复/死代码消除） |
| 重复实现消除 | 8 处 |
| 零调用函数删除 | 7 个 |
| 提交 | `b066cb1` / `558634d` / `2b0eea7` |
| 代码审查 | 双轴均通过（Standards 0 硬性发现） |

---

## 2. T01 — PHREEQC 失败自动落盘 error.inp

> 工单：`.scratch/soil-scm-overview/issues/02-error-inp-auto-write.md`  
> 提交：`558634d`  
> 关联审查发现：**P1**（文档承诺 vs 实现背离）

### 2.1 问题背景

- **文档承诺**（README）："`error.inp` 为 PHREEQC 计算失败时自动生成的完整输入复现文件（Q18 异常分级）"。
- **实际实现**：`_run_official_step` 异常分支仅设置内存属性 `last_error_input`，**无任何写文件逻辑**；根目录 `error.inp`（9KB）是历史遗留文件，并非每次失败自动刷新。
- **测试盲区**：原测试只断言内存属性有值，不断言磁盘文件生成——测试固化了"属性"行为而非"落盘"承诺。

### 2.2 实施方案

1. `src/constants.py`：新增 `ERROR_INP_PATH = "error.inp"` 常量（遵循 Q19 常量收敛约定）。
2. `src/phreeqc_engine.py`：`_run_official_step` 异常分支追加磁盘写入——`Path(ERROR_INP_PATH).write_text(input_string)`，写入失败 try/except 隔离，不影响降级主流程。
3. `tests/test_phreeqc_engine.py`：
   - 增强 `test_error_diagnostics_on_failure`：断言 `error.inp` 磁盘生成 + 内容含 `SOLUTION`/`SELECTED_OUTPUT`（`tmp_path` 隔离，不污染项目根）。
   - 新增 `test_error_write_failure_does_not_break_flow`：非法路径 → 写入失败时降级路径正常完成（`ph > 0`）。

### 2.3 测试验证

- 完整测试套件 **62 passed**。
- E2E 实测：模拟引擎失败后 `error.inp` 真实生成（1071 字节，含完整输入），降级后 pH 正常（4.998）。

### 2.4 代码审查

- **Standards 轴**：0 处硬性发现；2 条判断性观察（相对路径 CWD 依赖、CRLF 换行），均无实际影响。
- **Spec 轴**：4 条验收标准全部达成。

---

## 3. T02 — 气候修正机制收敛 + MonthlyAction 死字段清理

> 工单：`.scratch/soil-scm-overview/issues/03-climate-correction-dead-field-cleanup.md`  
> 提交：`b066cb1`  
> 关联审查发现：**P2 + S1**（Spec 承诺与实际机制不符；永不生效的死字段）

### 3.1 问题背景

- `MonthlyAction.precip_factor` / `temp_offset` 字段在 `get_action()` 中**从未赋值**，代码库中**从未被读取**——典型的死代码。
- `precip_increase` / `temp_increase` 情景在情景控制器中直接 `pass`，实际修正由气候强迫生成器（ClimateForcing）在生成逐月序列时完成。
- spec（`01-core-overview-spec.md` US28）承诺"月度操作指令包含降水/温度修正系数，so that 气候情景与施肥石灰操作可叠加"——与实现机制不符，属于 Spec 偏差。

### 3.2 决策点与实施方案

**决策**：气候修正保持由 `ClimateForcing` 承担（单一职责、机制清晰）。未采用"回填 MonthlyAction 使情景可叠加"方案（属更大改动，如需另行成单）。

1. `src/scenario_controller.py`：移除 `MonthlyAction.precip_factor` / `temp_offset` 死字段，更新模块 docstring 说明气候修正归属。
2. `tests/test_scenario_controller.py`：新增 `test_no_dead_climate_correction_fields`（TDD 红→绿），锁定字段不再存在。
3. spec（`01-core-overview-spec.md`）4 处更新：US28、情景-动作分离、领域词汇"情景操作"、S2 测试接缝描述——全部与"气候修正由气候强迫承担"的实际机制一致。

### 3.3 测试验证

- 完整测试套件 **61 passed**（含新增测试）。
- `src/` 与 `tests/` 无死字段残留引用。

### 3.4 代码审查

- **Standards 轴**：0 处硬性发现；2 条判断性观察（docstring 工单号引用、`hasattr` 断言方式），均为可选优化。
- **Spec 轴**：4 条验收标准全部达成。

---

## 4. T04 — 重复计算收敛与 utils 死函数清理

> 工单：`.scratch/soil-scm-overview/issues/04-duplicated-calculation-consolidation.md`  
> 提交：`2b0eea7`  
> 关联审查发现：**S2 + S3 + S1**（重复代码、Feature Envy、投机性通用化）

### 4.1 问题背景

同一计算公式多处重复实现，且工具模块存在大量零调用函数：

| 公式 | 重构前实现数 | 位置 |
|------|------------|------|
| 土壤质量 `ρ×1000×depth/100×10000` | 3 处 | `SoilProfile.soil_mass_per_ha` / `_calc_soil_mass` / `utils.calc_soil_mass_per_ha` |
| 静态盐基饱和度 `(Ca+Mg+K+Na)/CEC×100` | 2 处 | `SoilProfile.base_saturation` / `utils.estimate_base_saturation` |
| cmol(+)/kg→mol 换算 `/100` | 2 处 | `utils.cmol_to_mol_per_kg` / `_calc_cec_total` 内联 |
| pCO2 公式 `ref×exp(β×ΔT)` | 2 处 | `utils.estimate_soil_pCO2` / `_generate_pCO2` 内联 |

另：`InitialConditionBuilder` 重复实现 `SoilProfile` 已有属性（`soil_mass_per_ha`/`porosity`）的计算（Feature Envy）；`utils.py` 7 个零调用函数（+1 个 `estimate_soil_pCO2` 实为 8 个）。

### 4.2 实施方案

1. `utils.py`：删除 6 个零调用死函数（`mol_per_kg_to_cmol`/`kg_per_ha_to_mol_per_ha`/`calc_soil_mass_per_ha`/`estimate_base_saturation`/`urea_to_hno3_equivalent`/`calcite_dissolution_rate`）；保留 `cmol_to_mol_per_kg`、`estimate_soil_pCO2` 并接入实际调用。模块从 140 行瘦身至 ~50 行。
2. `initial_condition.py`：删除 `_calc_soil_mass`/`_calc_porosity` 方法，复用 `SoilProfile.soil_mass_per_ha`/`porosity` 属性（修复 Feature Envy）；`_calc_cec_total` 改用 `utils.cmol_to_mol_per_kg`。
3. `climate_forcing.py`：`_generate_pCO2` 改用 `utils.estimate_soil_pCO2`。

**一处有意偏差**：工单示例"主程序盐基饱和度改用 estimate_base_saturation"未采纳——main.py 的盐基饱和度是**动态交换位点电荷占比**（基于模拟后交换组成），与静态 cmol(+)/kg 语义不同，替换会改变数值。该公式仅 main.py 一处实现，非重复，保留内联。

### 4.3 收敛结果

| 公式 | 重构前 | 重构后 |
|------|--------|--------|
| 土壤质量 | 3 处 | **1 处**（`SoilProfile.soil_mass_per_ha`） |
| 静态盐基饱和度 | 2 处 | **1 处**（`SoilProfile.base_saturation`） |
| cmol(+)/kg→mol | 2 处 | **1 处**（`utils.cmol_to_mol_per_kg`） |
| pCO2 公式 | 2 处 | **1 处**（`utils.estimate_soil_pCO2`） |

### 4.4 测试验证

- 完整测试套件 **62 passed**（数值锁定用例 `test_soil_mass`/`test_porosity`/`test_cec_total` 全过）。
- E2E 数值对比：`soil_mass_kg=3.600e6`、`porosity=0.5472`、`cec_total_mol=4.32e5`、`pCO2[0,0]=0.011682`，与重构前**完全一致**。
- 全仓搜索确认无已删除函数残留引用。

### 4.5 代码审查

- **Standards 轴**：0 处硬性发现（本次改动正是 Duplicated Code / Feature Envy / Speculative Generality 三类异味的正向修复）；3 条判断性观察。
- **Spec 轴**：4 条验收标准全部达成。

---

## 5. 统计与经验总结

### 5.1 工单执行统计

| 工单 | 测试新增 | 代码净变更 | 审查硬性发现 | 提交 |
|------|---------|-----------|-------------|------|
| T01 | +1 增强 +1 新增 | +15 | 0 | `558634d` |
| T02 | +1 | -2 | 0 | `b066cb1` |
| T04 | 0 | -123 | 0 | `2b0eea7` |

### 5.2 经验总结

1. **文档承诺是规格**：README/文档中声明的行为（如 error.inp 自动生成）应视为验收标准；测试应断言"承诺的行为"而非"实现的现状"。
2. **TDD 对死代码清理有效**：先写"断言字段不存在/文件生成"的失败测试，再清理，确保删除不留残余。
3. **语义区分避免误重构**：main.py 的"动态盐基饱和度"与 `SoilProfile` 的"静态盐基饱和度"语义不同，重构前需区分，否则会改变科学数值。
4. **单一事实来源原则**：物理公式应集中在属性/工具函数中，避免多模块重复实现导致维护漂移。

---

## 6. 附录：相关文档与工单

- spec 基准：`.scratch/soil-scm-overview/issues/01-core-overview-spec.md`
- T01 工单：`.scratch/soil-scm-overview/issues/02-error-inp-auto-write.md`
- T02 工单：`.scratch/soil-scm-overview/issues/03-climate-correction-dead-field-cleanup.md`
- T04 工单：`.scratch/soil-scm-overview/issues/04-duplicated-calculation-consolidation.md`
