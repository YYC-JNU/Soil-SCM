# 04 — 重复计算收敛与 utils 死函数清理

**What to build:** 将土壤质量、盐基饱和度、cmol 单位换算三处重复实现收敛为单一事实来源，并清理 `utils.py` 中 7 个零调用函数。当前同一计算公式在多个模块中重复实现（土壤质量 ×3、盐基饱和度 ×3、cmol 换算 ×2），且工具模块中大量函数在整个代码库零调用，构成重复代码与投机性通用化。

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

## Background（审查发现 S2 + S3 + S1）

- **土壤质量公式**（`ρ×1000×depth/100×10000`）三处实现：土壤剖面对象属性 `soil_mass_per_ha`、初始条件构建器 `_calc_soil_mass`、工具函数 `calc_soil_mass_per_ha`。
- **盐基饱和度公式**（`(Ca+Mg+K+Na)/CEC×100`）三处实现：土壤剖面属性 `base_saturation`、工具函数 `estimate_base_saturation`、主程序内联计算。
- **cmol(+)/kg→mol 换算**（`/100`）两处实现：工具函数 `cmol_to_mol_per_kg`、初始条件构建器 `_calc_cec_total`。
- **Feature Envy**：初始条件构建器重复实现土壤剖面已有属性（`soil_mass_per_ha`、`porosity`）的计算，本应复用。
- **零调用函数**（7 个）：`calcite_dissolution_rate`、`urea_to_hno3_equivalent`、`kg_per_ha_to_mol_per_ha`、`cmol_to_mol_per_kg`、`mol_per_kg_to_cmol`、`calc_soil_mass_per_ha`、`estimate_base_saturation`——搜索仅命中定义处。

## 行为要求

1. 以**土壤剖面对象**的既有属性（`soil_mass_per_ha`、`base_saturation`、`porosity`）为单一事实来源，让初始条件构建器、主程序复用而非重复实现。
2. `utils.py` 的零调用函数逐一定夺：被复用场景接入实际调用（如主程序内联盐基饱和度改用 `estimate_base_saturation`），其余无实际用途的删除。
3. 保持单元换算逻辑的物理正确性（cmol→mol 的 `/100` 与电荷数处理），不得因重构改变数值结果。

## 实现方向（供参考，非硬性要求）

- 初始条件构建器：`self.soil_mass_kg = profile.soil_mass_per_ha`、`self.porosity = profile.porosity`（复用属性）。
- 主程序盐基饱和度计算改用单一函数来源。
- 收敛后删除无引用函数，并运行测试验证数值行为不变（关键：现有测试锁定了转换正确性，如 `test_initial_condition` 相关用例）。

## Acceptance criteria

- [ ] 同一计算公式不再存在多份实现（土壤质量 / 盐基饱和度 / cmol 换算各仅一处权威实现）
- [ ] `utils.py` 无零调用函数（被接入或被删除）
- [ ] 数值行为不变：全部测试套件保持全绿（含锁定 Q12 交换补齐、Q7 降水换算的用例）
- [ ] 重构不改变任何输出数值（可用 git diff 数值对比或现有快照测试验证）
