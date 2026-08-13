# WF2 — 多分层模型实现

**Label:** `wayfinder:task`
**Status:** ✅ closed (2026-08-13, via /implement + /code-review)

## Resolution — 实现完成说明

**实现内容**（依据 WF1 Q1-Q7 架构决策）：

1. **`src/phreeqc_engine.py`**：新增 `run_monthly_multi_layer` 高层编排层——对每层调用 `run_monthly_step`（S1 接缝不变）+ 级联平流交换（上层排水溶质 → 下层 REACTION）；`n==1` 防御性退化为单层。`_build_phreeqc_input` 支持 `inflow_ions` 层间输入。
2. **`src/config_manager.py`**：`SimulationConfig` 新增 `n_layers`（默认 1）+ 解析逻辑。
3. **`src/output_writer.py`**：新增 `record_multi_step` + `_layer_suffixes`（层深度后缀命名）；`_save_csv`/`_save_netcdf` 的 variables 过滤支持层后缀前缀匹配；单层列名不变。
4. **`main.py`**：提取 `_extract_diagnostics` 辅助函数；主循环按 `n_layers` 分支——多层走 `run_monthly_multi_layer` + `record_multi_step`，单层走原路径（回归护栏）。
5. **`config/config.yaml`**：新增 `n_layers: 1`（默认单层）。

**测试**：
- 新增 `tests/test_multilayer.py`（4 用例：多层运行/新状态对象/n=1 等价/平流溶质下移）。
- 新增 `tests/test_multilayer_output.py`（5 用例：层后缀/单层不变/默认等分/variables 过滤/CSV 保存）。
- 完整测试套件 **71 passed**（原 62 + 新增 9）。

**E2E 验证**：
- 4 层 1 年完整模拟 `[SUCCESS]`；CSV 输出 `pH_0_15`/`pH_15_30`/`pH_30_45`/`pH_45_60` 等层后缀列，数据有效。
- 平流守恒：Ca 浓度逐层递增（1.07e-5→3.42e-5 mol/L），级联下渗生效。
- 单层回归：`n_layers=1` CSV 列名与历史完全一致（`pH`/`base_saturation`/`CEC_occupied`/`exchangeable_Ca`/`exchangeable_Al`），pH=4.906 正常。

**代码审查**：`/code-review` 双轴通过——Standards 0 硬性发现（3 判断性观察：子循环重复/防御性分支/作用域，均不阻塞）；Spec 5 条验收标准全部达成。

**阻塞 WF5 已解除**（WF5 阻塞于 WF2 + WF4）。
**Parent:** 多分层模型与 SURFACE 表面络合（wayfinder:map）

## Question

基于 WF1 确定的架构决策，实现多分层模型的代码改造。

实现范围（依据 WF1 决策细化）：

1. **状态结构**：按 WF1 决策引入层索引或分层状态集合。
2. **层间垂直迁移**：按 WF1 选定的数值方案（完全混合 / 一维平流 / 弥散）实现逐月层间传递。
3. **排水模型逐层分配**：`precip_infiltration` 入渗水量按层分配逻辑。
4. **接缝扩展**：`run_monthly_step` 公共接口支持多层（保持 `n_layers=1` 兼容）。
5. **配置**：`config.yaml` 增加 `n_layers` 及可选逐层参数覆盖（CSV/JSON）。
6. **输出**：诊断量表达逐层结果。
7. **测试**：在最高接缝（月度化学步）扩展测试；`n_layers=1` 时数值行为应与当前一致（回归护栏）。

## 阻塞

- **WF1 — 多分层模型架构决策**（必须先确定架构方案）

## 验收

- [ ] `n_layers=4` 可运行完整模拟
- [ ] `n_layers=1` 结果与当前版本数值一致（回归）
- [ ] 逐层输出诊断量正确生成
- [ ] 完整测试套件全绿（新增多层测试）
- [ ] `/code-review` 双轴通过
