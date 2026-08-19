# 54 — v0.5.3 集成、验收 E1~E3 与发布（T5）

**What to build:** main 编排集成 VGM/ET/级联重构/OM：逐层 pCO₂=apply_om_pco2 加性调制、ET 传递（AET_mm/et_deficit_mm）、诊断扩展（soil_moisture_L1~L4/pCO2_eff/stored_water_Li 换算向后兼容）；`run_monthly_multi_layer` hydrology 契约（L/ha）不变；config.yaml/config_example.yaml 同步（latitude/pet_method/pet_monthly_climate/pet_correction_factor/initial_psi_cm/vgm_* 新增 + infiltration_initial/steady 移除报错）；验收实验 E1（4 层 15 年 natural + 预平衡收敛复验）/ E2（PET 敏感性 600~1400mm 扫描，L1/L2 干湿交替 + pH 回落方向）/ E3（k_om 0.0003/0.0005/0.0008 敏感性扫描，表层酸化方向，科学诚实）；文档同步（README/ROADMAP/OPTIMIZATION_PLAN §7.6 执行日志/USERGUIDE/TICKETS_SUMMARY）；发布 v0.5.3（版本号 → commit → annotated tag → push main + push tag）。

**Blocked by:** 50、51、52、53

**Status:** ready-for-agent

- [ ] main 编排集成：逐层 pCO₂（含 OM 增量）+ ET 传递 + 诊断扩展；输出列完整且 stored_water 向后兼容（S6 专家★5）
- [ ] 水量守恒不变量保持（入渗+径流+ET+优先流+深层排水+Δ储水=降水）（S6）
- [ ] config.yaml/config_example.yaml 同步；f0/fc 残留显式报错（breaking change 明示）
- [ ] E1：预平衡收敛复验（初始溶液体积变更后）+ 4 层 15 年 natural 基线记录
- [ ] E2：PET 600~1400mm 扫描 → L1/L2 干湿交替 + pH 回落方向（不承诺具体值）
- [ ] E3：k_om 敏感性扫描 → 表层酸化方向
- [ ] 全量 pytest 195~210 全绿（Q6 契约：不变量四类一字不改）
- [ ] 文档同步（README/ROADMAP 勾选/OPTIMIZATION_PLAN §7.6/USERGUIDE/TICKETS_SUMMARY）
- [ ] 发布 v0.5.3：commit + annotated tag + push main + push tag
