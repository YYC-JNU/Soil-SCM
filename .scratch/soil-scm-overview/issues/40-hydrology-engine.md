# 40 — v0.5.0 引擎水文集成（T4）

**What to build:** 引擎接受水文结果（各层来水量/排水量）替代 precip_infiltration 排水计算：run_monthly_multi_layer 用水文级联排水量做层间溶质传递；_build_phreeqc_input REACTION H2O 用量用该层来水量；单层路径不变。

**Blocked by:** 38（水文模块）、39（状态扩展）

**Status:** ready-for-agent

- [ ] 引擎接收各层来水量/排水量（水文模式）
- [ ] 层间 inflow_ions 用水文排水量（替代 precip_infiltration 排水）
- [ ] 单层 n_layers=1 完全原路径（回归护栏）
- [ ] 测试：4 层月度步运行、层间排水传递正确、单层回归（S4 seam）
