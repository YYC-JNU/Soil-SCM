# 68 — v0.6.1 集成：30 年 8 情景重跑 + E1 复验 + 发布

**What to build:** 集成 v0.6.1 全部改动，重跑 30 年 8 情景敏感性实验（`--tag v061`）验证数值稳定性目标——全情景 `phreeqc_ok=True`、L4 max 浓度 <1 mol/L、水量闭合 <1%/盐分 <5%；复验 E1 预平衡收敛（HX/GAP_H 注入后收敛值可能从 4.92 变化，如实记录）；同步版本（README 徽章/版本记录/ROADMAP/OPTIMIZATION_PLAN）+ 发布 v0.6.1（commit + annotated tag + push）。

**Blocked by:** 63、64、65、66、67（全部 v0.6.1 前置工单）。

**Status:** ready-for-agent

- [ ] `tools/sensitivity_pH_30yr.py --tag v061`：8 情景 × 30 年重跑（每情景独立引擎实例，隔离降级污染）
- [ ] 验收判定：全情景 `phreeqc_ok` 全程 True + L4 max 离子浓度 <1 mol/L + 无 2.0/12.0 钳制触碰（pH 值仅诊断不承诺）
- [ ] E1 预平衡收敛复验（natural 4 层，HX/GAP_H 基线）：新旧收敛值如实记录；若预平衡发散 → 回退 GAP_H_FRACTION=0（HX 仅 exch_h 来源）重验
- [ ] `tools/verify_v0_6_1_numerical.py`：数值稳定性验收脚本（后台进程跑长模拟）
- [ ] 文档同步：README 版本记录 + config.yaml/config_example.yaml + ROADMAP（v0.6.1 行）+ OPTIMIZATION_PLAN 执行日志 + SENSITIVITY_PH_30YR_V061.md
- [ ] 测试全绿（259 + 新增 ≈ 280~300）后发布：版本号同步 → commit → annotated tag v0.6.1 → push main + push tag
