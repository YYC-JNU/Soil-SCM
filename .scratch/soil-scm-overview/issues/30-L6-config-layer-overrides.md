# 30 — L6 layer_overrides/layer_depths 配置解析与校验（T1）

**What to build:** config 能解析 `simulation.layer_overrides`（config 内联密集列表，长度必须 = n_layers，逐层覆盖 ph/organic_matter/cec/bulk_density/交换性离子×6/pCO2/minerals 7 类字段）与 `simulation.layer_depths`（逐层厚度 cm）；越界/长度不符/值域非法即报错；n_layers=1 时忽略并警告；矿物体质量分数总和≠1 警告（不归一化）。

**Blocked by:** None — can start immediately.

**Status:** ✅ 已完成 (2026-08-17, v0.4.0)

- [ ] `layer_overrides` 解析：7 类字段映射到配置 dataclass，缺失字段为 None（回退默认）
- [ ] `layer_depths` 解析（List[float]）
- [ ] 校验：n_layers>1 时 `len(layer_overrides)==n_layers` 否则 ValueError；`len(layer_depths)==n_layers` 否则 ValueError
- [ ] 校验：值域（ph∈(3,10)、cec>0、bulk_density>0、pCO2>0、exch_*≥0、矿物质量分数∈(0,1)）
- [ ] 校验：n_layers=1 且 layer_overrides/layer_depths 非空 → 警告并忽略（不报错）
- [ ] 校验：minerals 质量分数总和≠1 → 警告
- [ ] 测试：解析/校验全部路径（含报错信息可读），单层忽略警告
