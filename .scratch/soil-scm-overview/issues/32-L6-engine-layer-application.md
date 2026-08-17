# 32 — L6 引擎逐层应用（初始态差异化 + 月度 pCO₂ 注入）（T3）

**What to build:** 引擎按逐层 profile / 矿物信息 / pCO₂ 构建**差异化初始状态**（exchange/minerals/solution/gas_phase 逐层不同）；`run_monthly_multi_layer` 支持逐层 pCO₂，月度 GAS_PHASE 固定分压按层注入（缺省回退全局 forcing）。2 层集成测试验证各层 state 差异化与 pCO₂ 注入生效。

**Blocked by:** 30（配置结构）、31（逐层 profile/矿物构建）

**Status:** ✅ 已完成 (2026-08-17, v0.4.0)

- [ ] 逐层 `build_initial_state`：每层用该层 profile/矿物/pCO₂ 产出差异化状态（2 层对比断言 exchange/minerals/gas_phase 不同）
- [ ] `run_monthly_multi_layer` 可选逐层 pCO₂：设置后各层 `layer_forcing['pCO2']` 生效；未设置回退全局
- [ ] 集成测试：2 层一步（跟随既有多层测试先例，不跑 30 年），pCO₂ 注入断言
