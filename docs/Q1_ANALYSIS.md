# Q1 问题分析报告与解决方案

## 0. 基本信息

| 项目 | 内容 |
|------|------|
| 问题编号 | **Q1** |
| 问题标题 | PHREEQC 状态不传递、无化学演化 |
| 优先级 | 🔴 高 |
| 状态 | 🔄 进行中 |
| 涉及文件 | `src/phreeqc_engine.py`、`main.py` |
| 报告日期 | 2026-08-11 |

---

## 1. 问题描述与具体体现

**核心问题**：`_parse_phreeqc_output` 只提取 pH，溶液/交换/矿物每月用初始值重建，PHREEQC 平衡结果被丢弃，导致化学状态无法随时间演化。

**代码路径**：`main.py` 月循环 → `engine.run_monthly_step` → `_run_phreeqc_step` → `_build_phreeqc_input`（重建输入）→ `run_string`（平衡计算）→ `_parse_phreeqc_output`（解析结果）

**4 个具体表现**：

### 表现 1：第 1 月后状态退化为空
`_parse_phreeqc_output`（`phreeqc_engine.py` L271）创建**全新空 `SoilState()`**，只填 `ph` 和 `diag.ph`。`solution` / `exchange` / `minerals` / `gas_phase` 全部为默认空 dict。

```python
new_state = SoilState()          # 全新空对象
new_state.ph = float(sol.pH)     # 只填 pH
diag.ph = new_state.ph
return new_state, diag           # solution/exchange/minerals 全为空!
```

### 表现 2：第 2 月起化学计算"名存实亡"
空状态传入 `_build_phreeqc_input` 后，生成的输入中：
- SOLUTION 块只有 `temp/pH/pe/units`（**无任何离子**）
- EXCHANGE 块**为空**
- EQUILIBRIUM_PHASES 块**为空**

每月都是"纯水 + 固定 pH"的退化计算，初始矿物/交换/溶液组成完全不参与。
**这是 phreeqc 模式 pH 恒为 5.000 的直接原因之一**（另一原因是 Q2 库限制）。

### 表现 3：PHREEQC 平衡结果全部丢弃
`run_string` 后 PHREEQC 内存中有一套完整平衡状态（离子分布、交换位点、矿物饱和量），但代码只通过 `get_solution(1).pH` 取了 pH。
phreeqpython 提供的查询 API 均未使用：
- `Solution.elements`（元素总摩尔量）、`Solution.species`（物种摩尔量）、`Solution.total(element)`
- `VIPhreeqc.get_equilibrium_phase_component_moles(phase, component)`（矿物相组分摩尔量）
- `VIPhreeqc.get_phases(solution)` / `get_phases_si`（矿物饱和指数）

### 表现 4：输出与状态脱钩
`main.py` L185-197 诊断量用 `soil_profile.exch_ca` 等**初始观测值**（常量）计算，与 `soil_state` 无关——即使状态正确演化，`base_saturation` / `exchangeable_Ca` / `exchangeable_Al` 输出也永远是初始值。

---

## 2. 原因分析

| # | 原因 | 说明 |
|---|------|------|
| 1 | **骨架占位遗留** | `_parse_phreeqc_output` 从文档代码起就是 placeholder，只提取 pH 是占位逻辑从未实现 |
| 2 | **`new_state = SoilState()` 全新对象** | 未复制/更新 `old_state` 的化学字段，状态链在每月被切断 |
| 3 | **状态查询未实现** | phreeqpython 完整查询 API（elements/species/total、矿物摩尔量）未使用 |
| 4 | **SOLUTION 用浓度重建缺乏守恒** | 用 mol/L 浓度 + 固定 pH 重建，而非"上月摩尔量 + 反应"的摩尔守恒方式 |
| 5 | **诊断输出绑定初始数据** | main.py 用 `soil_profile`（观测初始值）而非 `soil_state`（模拟状态） |

---

## 3. 解决方案设计（查询回填法）

**目标**：建立完整"PHREEQC 状态传递"闭环——每月平衡后提取溶液组成/交换/矿物摩尔量回填 `SoilState`，下月基于真实状态重建输入，使化学状态可累积演化。

**方案对比**：

| 方案 | 原理 | 优点 | 缺点 | 结论 |
|------|------|------|------|------|
| A: USE/SAVE 会话保持 | PHREEQC 内部维护状态，每月 USE 各相 + REACTION | 摩尔守恒最好 | GAS_PHASE 每月 CO₂ 变化处理复杂；受 Q2 pH 锁定影响；调试困难 | 不采用 |
| B: 每月重建 + 查询回填 | 每月用 state 重建输入，平衡后从结果查询回填 | 输入自包含、可控性强、可逐步验证、改动最小 | 需处理体积/浓度换算 | ✅ **采用** |

**设计要点**：
- `SoilState.solution` 保存**元素总摩尔量（mol）**（非浓度），`_build_phreeqc_input` 时除以溶液体积换算 mol/L
- `SoilState.exchange` 保存各交换复合物（CaX2/MgX2/KX/NaX/AlX3）的**摩尔量**
- `SoilState.minerals` 保存各矿物相**当前摩尔量**（扣除溶解/沉淀变化）
- `_parse_phreeqc_output` 通过 phreeqpython API 完整提取上述状态

---

## 4. 实施步骤与时间节点

| 步骤 | 内容 | 计划时间 | 状态 | 实际完成 |
|------|------|----------|------|----------|
| S1 | API 实验验证：实测 `Solution.elements`、矿物摩尔量、交换查询的返回值与单位 | 2026-08-11 | ✅ 已完成 | 2026-08-11 |
| S1* | 替代引擎调研：验证官方 `phreeqc`（IPhreeqc 3.8.6）REACTION 与状态查询 | 2026-08-11 | ✅ 已完成 | 2026-08-11 |
| S2 | 重构 `_parse_phreeqc_output`：完整提取溶液/交换/矿物状态并回填 | 2026-08-11 | ⬜ | |
| S3 | 调整 `_build_phreeqc_input`：SOLUTION 用摩尔量÷体积换算浓度、EXCHANGE/EQUILIBRIUM_PHASES 用真实状态 | 2026-08-11 | ⬜ | |
| S4 | 简化模式保留状态：`_run_simplified_step` 复制 old_state 化学字段（缓解 Q6） | 2026-08-11 | ⬜ | |
| S5 | main.py 诊断输出绑定模拟状态（base_saturation/exchangeable_Ca/Al 从 state 提取） | 2026-08-11 | ⬜ | |
| S6 | 测试与回归：单月回填正确性、多月累积演化、两种引擎模式行为 | 2026-08-11 | ⬜ | |

---

## 5. 执行日志

> 每完成一个步骤在此追加记录（时间、改动文件、验证结果）。

### S1 — API 实验验证（2026-08-11）

**phreeqpython 1.6.2 查询 API 实测结果**：
- ✅ `Solution.elements`：返回 mol/L 浓度（1L 溶液下数值即摩尔量），可用
- ✅ `Solution.total(el)`：返回 mmol，可用
- ✅ `get_equilibrium_phase_component_moles`：矿物摩尔量精确可用（quartz=1.498e7 mol 与初始一致）
- ❌ `get_moles('CaX2')`：交换物种全部返回 0（交换相不在溶液中，查询不可用）
- ⚠️ `SELECTED_OUTPUT`：交换物种列存在但行为不稳定（含 GAS/矿物时 row_count=0 或数值异常）

**决定性发现（phreeqpython 根本缺陷）**：
1. **REACTION 完全无效**：加 HCl 5e-4 mol 后 total Cl 变化 0.000000 mmol（降水/施肥/酸雨无法驱动演化）
2. **复杂体系数值异常**：含 GAS_PHASE + 大量矿物时，平衡后交换相坍塌（CaX2 从 5.4e4 → 0.734 mol）、pH 异常升至 10.87

### S1* — 替代引擎调研（2026-08-11）

**官方 `phreeqc` 包（IPhreeqc 3.8.6，USGS 官方引擎）实测**：
- ✅ API：`LoadDatabase` / `RunString` / `GetSelectedOutput*` / `GetComponent`（引擎版本 3.8.6-17100-x64）
- ✅ **REACTION 有效**：加 HCl 5e-4 mol → total Cl 精确 +0.0005 mol/kgw
- ✅ **pH 响应正常**：pH 5.0 → 3.32（加酸显著下降）
- ✅ SELECTED_OUTPUT 可靠输出

**结论**：phreeqpython 引擎无法支撑 Q1（状态传递/演化）目标；**换用官方 phreeqc 包**是解决 Q1+Q2 的正确技术路线。需用户确认后实施（涉及新依赖与 PhreeqcEngine API 重写）。

---

## 6. 验收标准

1. **单月回填正确**：run_string 平衡后，`state.solution`（元素摩尔量）、`state.exchange`、`state.minerals` 非空且数值合理（与 PHREEQC 查询一致）
2. **多月累积演化**：连续 N 月模拟中，溶液/交换/矿物组成随降水/施肥/石灰发生物理合理变化（如施肥后 N(5) 增加、石灰后 CaX2 增加）
3. **phreeqc 模式不降级**：月循环 run_string 全部成功，无"永久降级"警告
4. **simplified 模式行为不变**：回归验证 pH 演变与之前一致
5. **诊断输出反映演化**：输出的 base_saturation / exchangeable_Ca / Al 不再恒定，随状态变化

---

## 7. 边界说明

- Q2（phreeqpython pH 锁定）不在 Q1 范围内。Q1 修复后 phreeqc 模式 pH 可能仍锁定，但**溶液/交换/矿物组成将正确演化**，为 Q2 解决（换引擎/库）打基础。
- 若 API 实验（S1）发现查询不可行，将回退到方案 A（USE/SAVE），并在日志中记录原因。
