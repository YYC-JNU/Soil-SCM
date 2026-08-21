# 73 — 原生矿物风化动力学化（D2，spec 69 工单 72）

**What to build:** 让原生矿物从"瞬时平衡闪蒸→无限供碱"改为**速率控制的风化碱度注入**：逐月 REACTION 注入集总风化碱度（`weathering_rate` molc/ha/yr 可配，Ca:Mg:K=5:3:2 + HCO₃⁻ 等当量）；Arrhenius 温度依赖（`rate(T)=rate_ref×exp(−Ea/R×(1/T−1/T_ref))`，Ea 默认 40 kJ/mol、T_ref=298.15K）使增温情景产生可观测风化响应；评估 red_soil 矿物库 illite/gibbsite/kaolinite 从 `EQUILIBRIUM_PHASES` 降级（保 Al 循环通道不断——v0.3.0 KINETICS 证伪教训）；**不用 KINETICS**；`simulation.weathering.*` config。

**Blocked by:** 70, 71, 72（盐基扣除与置换改变矿物基线后，风化注入量级才有对标基础）。

**Status:** ready-for-agent

- [ ] 风化注入：逐月 REACTION Ca/Mg/K/HCO₃⁻（比例 5:3:2，等当量），weathering_rate 默认 500 molc/ha/yr 可配（初值，方向带扫描 100/500/1000 后定案）
- [ ] Arrhenius 温度依赖：增温情景风化速率↑（单元测试验证温度导数正）
- [ ] 矿物降级评估：illite/gibbsite/kaolinite 从平衡相移除或降量后，Al 循环不中断（AlX₃ 不加速耗尽——对照 v0.3.0 证伪链）
- [ ] 自然情景 30 年 pH 缓降方向（里程碑观察：工单 73+70/71 后 natural 不再上升）
- [ ] config `simulation.weathering.{enable, rate_molc_ha_yr, ca_frac, mg_frac, k_frac, activation_energy_kJ}` 解析/校验；`enable: false` 完全回退
- [ ] 现有 289 测试全绿（expand-contract）
