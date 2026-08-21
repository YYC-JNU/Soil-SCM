# 73 — 原生矿物风化动力学化（D2，spec 69 工单 72）

**What to build:** 让原生矿物从"瞬时平衡闪蒸→无限供碱"改为**速率控制的风化碱度注入**：逐月 REACTION 注入集总风化碱度（`weathering_rate` molc/ha/yr 可配，Ca:Mg:K=5:3:2 + HCO₃⁻ 等当量）；Arrhenius 温度依赖（`rate(T)=rate_ref×exp(−Ea/R×(1/T−1/T_ref))`，Ea 默认 40 kJ/mol、T_ref=298.15K）使增温情景产生可观测风化响应；评估 red_soil 矿物库 illite/gibbsite/kaolinite 从 `EQUILIBRIUM_PHASES` 降级（保 Al 循环通道不断——v0.3.0 KINETICS 证伪教训）；**不用 KINETICS**；`simulation.weathering.*` config。

**Blocked by:** 70, 71, 72（盐基扣除与置换改变矿物基线后，风化注入量级才有对标基础）。

**Status:** ✅ 已完成 (2026-08-21, v0.7.0)

- [x] 风化注入：逐月 REACTION Ca/Mg/K/HCO₃⁻（电荷占比 5:3:2，HCO₃⁻ 等当量电荷守恒），weathering_rate 默认 500 molc/ha/yr 可配（扫描 100/500/1000 留工单 76）
- [x] Arrhenius 温度依赖：`weathering_arrhenius_factor` 纯函数 + 注入量随 T 缩放（30°C≈1.30 倍；增温风化↑测试验证）
- [x] 矿物降级：`degrade_minerals` config → 从 EQUILIBRIUM_PHASES 移除（状态保留，SELECTED_OUTPUT 回填不破坏）；PHREEQC 实测平衡成功（降 gibbsite/kaolinite 后 AlX3 仍存，Al 循环通道不断）
- [x] config `simulation.weathering.{enable, rate_molc_ha_yr, ca_frac, mg_frac, k_frac, activation_energy_kJ, degrade_minerals}` 解析/校验（rate>0、占比和=1、活化能>0）；`enable: false` 完全回退
- [x] 现有 289 测试全绿（expand-contract；**323 passed**）

> **里程碑观察**：自然情景 30 年 pH 缓降方向依赖 weathering + degrade 组合启用，其参数扫描（rate 100/500/1000 + 降级名单）属工单 76 方向带验收范畴，本工单交付机制 + config 结构。
