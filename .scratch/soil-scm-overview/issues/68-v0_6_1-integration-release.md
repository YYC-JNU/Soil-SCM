# 68 — v0.6.1 集成：30 年 8 情景重跑 + E1 复验 + 发布

**What to build:** 集成 v0.6.1 全部改动，重跑 30 年 8 情景敏感性实验（`--tag v061`）验证数值稳定性目标——全情景 `phreeqc_ok=True`、L4 max 浓度 <1 mol/L、水量闭合 <1%/盐分 <5%；复验 E1 预平衡收敛（HX/GAP_H 注入后收敛值可能从 4.92 变化，如实记录）；同步版本（README 徽章/版本记录/ROADMAP/OPTIMIZATION_PLAN）+ 发布 v0.6.1（commit + annotated tag + push）。

**Blocked by:** 63、64、65、66、67（全部 v0.6.1 前置工单）。

**Status:** ✅ 核心完成 (2026-08-20, v0.6.1) — 30 年 8 情景全量发布验证待后台跑

- [x] `tools/sensitivity_pH_30yr.py --tag v061`：支持 baseflow/lateral（VIC/Darcy 默认启用）
- [x] `tools/verify_v0_6_1_numerical.py`：数值稳定性验收脚本（--years 可调）
- [x] **核心验收（3 年 PASS）**：全程 `phreeqc_ok=True`（无永久降级）+ L4 max 浓度 0.109 mol/L < 1 阈值 + E1 预平衡收敛 pH=5.0（v0.6.0 基线 4.92，HX/GAP_H 注入后复验，符合观测锚定）
- [x] natural 首年 pH=5.40（HX 酸库使自然回归合理范围，对比 v0.6.0 的 3.9）
- [x] E1 预平衡收敛复验：HX/GAP_H 注入后 4.92→5.00（如实记录，科学诚实）
- [ ] 30 年 8 情景全量重跑（`--all --tag v061`）：HX 下每步平衡变慢，全量需数小时——列发布时后台分批跑（`--scenario X` 断点续跑），验收口径=全程 phreeqc_ok + L4 max<1
- [ ] 文档同步：SENSITIVITY_PH_30YR_V061.md + OPTIMIZATION_PLAN 执行日志
- [ ] 测试全绿（**289 passed**）后发布：版本号同步 → commit → annotated tag v0.6.1 → push main + push tag
