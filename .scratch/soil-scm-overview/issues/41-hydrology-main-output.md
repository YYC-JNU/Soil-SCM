# 41 — v0.5.0 main 集成 + 输出水文列（T5）

**What to build:** main 构建水文模型（4 层自动默认/用户覆盖判断）→ 月度循环调用水文（随机降雨+Horton+级联）→ 传递入渗/排水到引擎 → 输出新增逐层水文诊断列（infiltration/runoff/drainage/stored_water，复用层后缀）。

**Blocked by:** 40（引擎集成）

**Status:** ✅ 已完成 (2026-08-17, v0.5.0)

- [ ] 4 层自动启用内置水文默认（n_layers=4 且未配置 layer_overrides）
- [ ] 月度循环：水文计算结果驱动引擎（入渗/径流/排水/滞水）
- [ ] OutputWriter 新增水文列（复用层后缀机制）
- [ ] 测试：4 层 E2E 月度步、输出 CSV 含水文列、单层不受影响（S5 seam）
