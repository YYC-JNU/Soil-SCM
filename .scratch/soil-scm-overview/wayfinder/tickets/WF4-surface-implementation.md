# WF4 — SURFACE 表面络合启用决策与实现

**Label:** `wayfinder:grilling` + `wayfinder:task`
**Status:** open
**Parent:** 多分层模型与 SURFACE 表面络合（wayfinder:map）

## Question

基于 WF3 的调研结果，决定并实现 SURFACE 表面络合的启用方案。

需解析的决策：

1. **位点方案**：采用 phreeqc.dat 的 `Hfo_s`/`Hfo_w`（Dzombak & Morel）位点，`build_surface()` 如何重构以生成兼容输入（强/弱位点 10%/90%）？
2. **有机质表面**：是否启用有机质表面位点（若 phreeqc.dat 支持），`OM_SITE_DENSITY` 如何配置？
3. **参数来源**：位点密度、比表面积、矿物质量等参数从哪来（当前 `MineralInfo` 有 `specific_area` 字段，可复用）？
4. **收敛风险**：针对 WF3 识别的收敛注意事项，是否需要在 `_build_phreeqc_input` 增加 KNOBS 调优？
5. **测试**：如何验证吸附生效（如 P/Zn/Al 在启用 SURFACE 后浓度变化测试）？

## 阻塞

- **WF3 — SURFACE 表面络合可行性调研**（必须先确认 phreeqc.dat 参数边界）

## 验收

- [ ] `build_surface()` 生成与 phreeqc.dat 兼容的 SURFACE 块
- [ ] 启用 SURFACE 后模拟收敛、无永久降级
- [ ] P/Zn/Al 吸附行为生效（有测试锁定）
- [ ] 完整测试套件全绿
- [ ] `/code-review` 双轴通过
