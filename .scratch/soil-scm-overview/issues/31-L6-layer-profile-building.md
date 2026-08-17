# 31 — L6 逐层 profile 构建与矿物增量覆盖（T2）

**What to build:** 给定默认土壤 profile 与 `layer_overrides[i]` + `layer_depths[i]`，能产出该层**独立**的 `SoilProfile`（字段级覆盖、未覆盖字段保持默认、`effective_depth = layer_depths[i]`）与**矿物增量覆盖**后的矿物信息（只替换指定矿物质量分数，其余保留，不归一化）。

**Blocked by:** 30（需要 layer_overrides/layer_depths 配置结构）

**Status:** ✅ 已完成 (2026-08-17, v0.4.0)

- [ ] 逐层 profile 构建：空 override 完全回退默认；部分字段覆盖其余保持；`effective_depth == layer_depths[i]`
- [ ] 交换性离子逐层覆盖（exch_ca/exch_mg/exch_k/exch_na/exch_al/exch_h）
- [ ] 矿物增量覆盖：覆盖矿物替换质量分数、未覆盖矿物保留、总和≠1 时不归一化
- [ ] 测试：部分覆盖、默认回退、effective_depth 派生、矿物增量替换
