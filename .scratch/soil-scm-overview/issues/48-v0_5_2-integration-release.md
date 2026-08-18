# 48 — v0.5.2 集成、运行验证与发布（T5）

**What to build:** main 编排集成 Green-Ampt + Ksat 拆分 + 优先流 + 硝化限 L1；移除 `surface_infiltration_coeff`（config 出现时报错）；输出新增优先流诊断列；运行验证（2 年 4 层 natural 基线对比 v0.5.1 vs v0.5.2，如实记录入渗/径流/pH 方向变化）；更新文档（README/ROADMAP/OPTIMIZATION_PLAN/HYDROLOGY 相关）与工具脚本；版本发布 v0.5.2（commit + annotated tag + push）。

**Blocked by:** 44、45、46、47

**Status:** ✅ 已完成 (2026-08-18, v0.5.2)

- [x] `SimulationConfig.surface_infiltration_coeff` 字段删除；ConfigManager 对残留字段报错（breaking change 明示）
- [x] `main._apply_hydrology_month`：Green-Ampt 调用 + bypass 传递 + runoff 守恒（含优先流）；`run_simulation` 主循环集成
- [x] `OutputWriter`：新增优先流/地表径流分离列（可选 bypass_drainage 诊断）
- [x] `config_example.yaml`/`config.yaml` 同步（移除 surface_infiltration_coeff，新增 ksat_surface/bypass_fraction）
- [x] `tools/sensitivity_infiltration.py`：扫描 surface_coeff → 改为扫描 `ksat_surface` 或标记暂停
- [x] 运行验证：2 年 4 层 natural 基线对比（v0.5.1 Horton+0.75 vs v0.5.2 Green-Ampt），记录入渗量/径流量/表层 pH 变化方向，如实文档化（科学诚实）
- [x] 文档同步：README 顶部 v0.5.2 更新说明、ROADMAP §5 近期规划勾选、OPTIMIZATION_PLAN §7 执行日志、HYDROLOGY_BOX 或新分析文档
- [x] 版本发布：版本号同步 → commit → annotated tag `v0.5.2` → push main + push tag
