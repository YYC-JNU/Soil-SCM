# 54 — v0.5.3 集成、验收 E1~E3 与发布（T5）

**What to build:** main 编排集成 VGM/ET/级联重构/OM：逐层 pCO₂=apply_om_pco2 加性调制、ET 传递（AET_mm/et_deficit_mm）、诊断扩展（soil_moisture_L1~L4/pCO2_eff/stored_water_Li 换算向后兼容）；`run_monthly_multi_layer` hydrology 契约（L/ha）不变；config.yaml/config_example.yaml 同步（latitude/pet_method/pet_monthly_climate/pet_correction_factor/initial_psi_cm/vgm_* 新增 + infiltration_initial/steady 移除报错）；验收实验 E1（4 层 15 年 natural + 预平衡收敛复验）/ E2（PET 敏感性 600~1400mm 扫描，L1/L2 干湿交替 + pH 回落方向）/ E3（k_om 0.0003/0.0005/0.0008 敏感性扫描，表层酸化方向，科学诚实）；文档同步（README/ROADMAP/OPTIMIZATION_PLAN §7.6 执行日志/USERGUIDE/TICKETS_SUMMARY）；发布 v0.5.3（版本号 → commit → annotated tag → push main + push tag）。

**Blocked by:** 50、51、52、53

**Status:** ✅ 已完成 (2026-08-19, v0.5.3)

- [x] main 编排集成：逐层 pCO₂（含 OM 增量）+ ET 传递 + 诊断扩展；输出列完整且 stored_water 向后兼容（S6 专家★5）
- [x] 水量守恒不变量保持（入渗+径流+ET+优先流+深层排水+Δ储水=降水）（S6）
- [x] config.yaml/config_example.yaml 同步；f0/fc 残留显式报错（breaking change 明示）
- [x] E1：预平衡收敛复验（初始溶液体积变更后）+ 4 层 15 年 natural 基线记录——**预平衡 4 层全收敛 pH 4.92（观测 5.0 偏差 0.08）✓；年均 AET 935mm（水分闭合）✓**
- [x] E2：PET 600~1400mm 扫描 → L1/L2 干湿交替 + pH 回落方向——**✗ 未达成**：月尾 θ 恒 θ_FC（0.41）、pH 恒 6.94（月度聚合丢失旱季干化 + 化学体积与 θ 解耦）；诚实记录
- [x] E3：k_om 敏感性扫描 → 表层酸化方向——**✗ 未达成**：pCO₂_eff 注入生效（0.024→0.039）但 pH 恒 6.94（矿物/碳酸缓冲抵消，k_om 需重参数化）；E3 发布前暴露（符合 spec 49 Q13）
- [x] 全量 pytest 195~210 全绿（Q6 契约：不变量四类一字不改）——**234 passed**
- [x] 文档同步（README v0.5.3/ROADMAP 勾选/OPTIMIZATION_PLAN §7.6/USERGUIDE/TICKETS_SUMMARY）
- [x] 发布 v0.5.3：commit + annotated tag + push main + push tag

**科学诚实验收结论**：v0.5.3 验收覆盖 **机制落地 + 水分平衡闭合 + 预平衡收敛**（对照 spec 49 边界）；**pH 回落 4.5~5.5 未达成**（E2/E3 无方向响应），留待 v0.6.0 子步长/体积耦合/Ks 重标定。不夸大。
