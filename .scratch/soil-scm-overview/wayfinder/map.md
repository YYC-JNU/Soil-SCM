# 多分层模型与 SURFACE 表面络合 — Wayfinder 地图

**Label:** `wayfinder:map`
**创建日期:** 2026-08-13
**Effort:** Soil-SCM 中期架构升级（多分层 + SURFACE）

## Destination

将单层土壤化学模式升级为**可运行的多分层（4 层）模型**并**启用 SURFACE 表面络合**，使长期（30 年）模拟中交换性 Al 不再因单层排水而耗尽、pH 不再突升，同时增强 P/Zn/Al 的吸附描述——即解决 ROADMAP 中 Q12*（交换性 Al 淋洗）与 Q9（SURFACE 未启用）两个已知关键局限。旅程终点是：`main.py` 可配置 `n_layers`（1 或 4）运行，输出逐层诊断量，30 年模拟 pH 曲线物理合理，SURFACE 块可运行且吸附生效。

## Notes

- **Domain**: 土壤地球化学（PHREEQC 引擎）；领域词汇见 `.scratch/soil-scm-overview/issues/01-core-overview-spec.md`（土壤剖面/土壤化学状态/气候强迫/情景操作/月度化学步/诊断输出/引擎模式）。
- **Skills 每个会话应查阅**: `/codebase-design`（深模块词汇：接口/深度/接缝/适配器）、`/domain-modeling`（领域术语打磨）、`/grilling`（决策拷问）、必要时 `/prototype`（层间通量机制可原型验证）。
- **Standing preferences**:
  - 保留 `n_layers=1` 单层兼容（ROADMAP 设计决策已确认）。
  - 各层默认参数相同（当前无土壤剖面观测约束），后续通过外部 CSV/JSON 逐层覆盖。
  - 遵循 Q19 常量收敛约定（参数入 `constants.py`）。
  - 测试在最高接缝（月度化学步）扩展。
- **Tracker**: 本地 markdown（`.scratch/soil-scm-overview/wayfinder/`）。

## Decisions so far

<!-- the index — one line per closed ticket -->

- [WF1 多分层模型架构决策](tickets/WF1-multilayer-architecture.md) — `List[SoilState]` + 一维平流 + 级联下渗；`run_monthly_step` 接口不变，新增 `run_monthly_multi_layer` 编排层；`n_layers` 配置 + 层后缀输出 + SELECTED_OUTPUT totals 守恒核算
- [WF2 多分层模型实现](tickets/WF2-multilayer-implementation.md) — 已实现：`run_monthly_multi_layer` 编排层 + `n_layers` 配置 + 层后缀输出；4 层 E2E 通过（Ca 逐层累积证明平流生效）；单层回归保持（列名/pH 不变）；71 测试全绿
- [WF3 SURFACE 表面络合可行性调研](tickets/WF3-surface-feasibility.md) — phreeqc.dat 原生支持 Hfo_s/Hfo_w（Dzombak & Morel 1990），P/Zn 吸附丰富但 **Al 无表面物种**；`build_surface()` 需改位点名（Hfo→Hfo_s/Hfo_w）+ 移除 Som；建议 WF4 仅启用铁氧化物表面，有机质/Al 表面列为独立工单
- [WF4 SURFACE 表面络合启用决策](tickets/WF4-surface-implementation.md) — 决策已定：Q2 调整为推迟 Al 表面（四源查证无标准数据）；Q3 阶段一用 phreeqc.dat（已含 Hfo_s/Hfo_w）；Q4 有机质表面排除；实现范围=Hfo_s/Hfo_w + `enable_surface` 配置 + P/Zn 吸附（78 测试全绿）

## Not yet specified

<!-- 当前"战争迷雾"：已知待决策但尚不清晰的方向 -->

- 层间溶液/溶质的垂直迁移数值方案（完全混合 vs 一维平流/弥散）——取决于多分层工单的解析结果，暂不能精确定型。
- SURFACE 位点密度与 phreeqc.dat `Hfo_s`/`Hfo_w` 兼容性的具体参数——需要查证 phreeqc.dat 后确定。
- 多分层下"排水模型"如何逐层分配入渗水量。

## Out of scope

<!-- 超出本目的地的工作 -->

- 有机质分解/碳循环模块（长期路线图）。
- 根系吸水/植物吸收（长期路线图）。
- WRF 气候耦合（长期路线图）。
- 硝化两步动力学、电荷平衡 HCO₃ 缓冲（Q13*）——属于化学动力学完善，不在本地图目的地的关键路径上，另行规划。
- 参数敏感性自动化扫描（长期路线图）。

## 工单清单

<!-- 子工单索引：编号 + 名称 + 类型 + 阻塞关系 + 状态 -->

| 编号 | 名称 | 类型 | 阻塞 | 状态 |
|------|------|------|------|------|
| WF1 | 多分层模型架构决策 | grilling | None | ✅ closed |
| WF2 | 多分层模型实现 | task | WF1 | ✅ closed |
| WF3 | SURFACE 表面络合可行性调研 | research | None | ✅ closed |
| WF4 | SURFACE 表面络合启用决策与实现 | grilling+task | WF3 | ✅ closed |
| WF5 | 多分层 + SURFACE 集成验证与回归 | task | WF2（已解除）, WF4（已解除） | open |

**前沿（可立即开工）**: WF4
