# 37 — v0.5.0 水文配置扩展与校验（T1）

**What to build:** config 支持逐层水文字段（clay_pct/porosity/ksat/infiltration_initial/infiltration_steady）+ 随机降雨种子（hydrology_seed）；孔隙度覆盖时反推容重 ρ=2.65(1−φ)；值域校验（φ∈(0,1)、ksat>0、f0>fc≥0）。

**Blocked by:** None — can start immediately.

**Status:** ✅ 已完成 (2026-08-17, v0.5.0)

- [ ] layer_overrides 解析 5 个水文字段（部分覆盖回退默认）
- [ ] hydrology_seed 解析（默认 42）
- [ ] 反推容重：porosity=0.55 → bulk_density≈1.19（与显式 bulk_density 冲突时 porosity 优先+警告）
- [ ] 值域校验：φ∈(0,1)、ksat>0、f0>fc≥0、f0/fc∈(0,~3)
- [ ] 测试：解析/反推/校验全部路径
