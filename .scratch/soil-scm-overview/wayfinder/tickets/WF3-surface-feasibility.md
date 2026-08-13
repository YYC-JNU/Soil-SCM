# WF3 — SURFACE 表面络合可行性调研

**Label:** `wayfinder:research`
**Status:** open
**Parent:** 多分层模型与 SURFACE 表面络合（wayfinder:map）

## Question

phreeqc.dat 数据库中 SURFACE 表面络合的可行性与参数边界是什么？

需调研的内容：

1. **phreeqc.dat 已定义的表面物种**：确认 `Hfo_s`/`Hfo_w`（Dzombak & Morel 模型）的位点类型、密度默认值、表面络合反应（强/弱位点 10%/90% 比例，如 OPTIMIZATION_PLAN P3 所述）。
2. **与现有数据对象的兼容**：`InitialConditionBuilder.build_surface()` 当前生成 `Som`/`Hfo` 位点（与 phreeqc.dat 不兼容，已被 S3 默认关闭）——需要确认改用 `Hfo_s`/`Hfo_w` 后需要哪些参数（位点密度、比表面积、质量）。
3. **有机质表面位点**：phreeqc.dat 是否支持有机质表面（humic/fulvic）？若支持，`OM_SITE_DENSITY`（当前 1.0 mol/kg）应如何配置？
4. **P/Zn/Al 吸附描述**：启用 SURFACE 后，哪些吸附反应会自动生效（对 P/Zn/Al 的描述增强到什么程度）？
5. **风险**：启用 SURFACE 对 PHREEQC 收敛性的影响（SURFACE 会增加非线性），是否有已知的数值收敛注意事项。

## 阻塞

None — 可立即开始。

## 验收

- [ ] 输出 phreeqc.dat 中 Hfo_s/Hfo_w 的完整定义摘要（位点类型/密度/反应）
- [ ] 明确 `build_surface()` 需要哪些参数调整才能在 phreeqc.dat 下运行
- [ ] 明确 P/Zn/Al 吸附增强的实际范围
- [ ] 列出 SURFACE 启用的收敛风险与缓解措施
