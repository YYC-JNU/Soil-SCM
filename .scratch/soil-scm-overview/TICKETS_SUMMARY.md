# Soil-SCM 工单汇总表（TICKETS_SUMMARY）

> **生成日期**：2026-08-17（项目文件整理）
> **覆盖范围**：`.scratch/soil-scm-overview/` 下全部工单——开发工单（issues/01~28）+ 架构决策工单（wayfinder/tickets/WF1~5）+ 遗留规划工单（backlog/L1~L9）
> **成立时间**：工单文件在 git 中的**首次提交日期**（`git log --diff-filter=A`）
> **状态口径**：以工单文件内 `**Status:**` 字段为权威标记；spec 类工单（01/05/11/15/20）按其对应子工单的落地情况标注为"已落地（经子工单）"；25~28 号工单文件状态为 `ready-for-agent`，但对应功能已由 2026-08-17 提交（f7f92bf / 7d19f9d）落地，故标注"已落地"

---

## 一、开发工单（issues/01~28）

| 工单 | 标题 | 成立时间 | 状态 | 说明 |
|------|------|----------|------|------|
| 01 | Soil-SCM 核心功能规格说明书 | 2026-08-13 | ✅ 已落地 | 经工单 05~10（v0.3.0 规格化链路）落地 |
| 02 | PHREEQC 失败自动落盘 error.inp 复现文件 | 2026-08-13 | ✅ 已完成 | implemented via /implement（T01） |
| 03 | 气候修正机制收敛 + MonthlyAction 死字段清理 | 2026-08-13 | ✅ 已完成 | implemented via /implement（T02） |
| 04 | 重复计算收敛 + utils 死函数清理 | 2026-08-13 | ✅ 已完成 | implemented via /implement（T04） |
| 05 | v0.3.0 化学机理收尾 spec（L4 硝化两步 + L5 HCO₃⁻ 电荷平衡） | 2026-08-14 | ✅ 已落地 | 经工单 06~10 全部实现 |
| 06 | L4 氮循环库存层引擎修正与测试 | 2026-08-14 | ✅ 已完成 | 2026-08-14 via /implement；commit 62d8e66 |
| 07 | v0.3.0 施肥情景 E2E 验证（氮形态时序） | 2026-08-14 | ✅ 已完成 | 2026-08-14 via /implement |
| 08 | V0_3_0_REPORT 工程报告 | 2026-08-14 | ✅ 已完成 | 2026-08-14 via /implement；已合并入 docs/reports/V0_3_0_FINAL_REPORT.md |
| 09 | 项目文档同步（README/ROADMAP/OPTIMIZATION_PLAN/backlog） | 2026-08-14 | ✅ 已完成 | 2026-08-14 via /implement |
| 10 | 双轴 code-review 与 git 提交 | 2026-08-14 | ✅ 已完成 | 2026-08-14 via /implement + /code-review；commit 62d8e66 |
| 11 | v0.4.0 后续优化 spec（L9 矿物缓冲校准 + L1 Al 表面简化方法） | 2026-08-14 | ✅ 已落地 | 经工单 12~14 全部实现 |
| 12 | L9 矿物缓冲校准（MINERAL_SCALE 参数扫描） | 2026-08-14 | ✅ 已结束（结构性局限确认） | 扫描证伪交换选择性方向；v0.5.0 确认 |
| 13 | L1 Al³⁺ 表面络合简化方法报告 | 2026-08-14 | ✅ 已完成 | 产出 docs/analysis/L1_AL_SURFACE_METHOD.md |
| 14 | v0.4.0 收尾（文档同步 + code-review + commit） | 2026-08-14 | ✅ 已完成 | via /implement + /tdd + /code-review |
| 15 | v0.5.0 初始状态自洽化 spec（pre_equilibrate 预平衡） | 2026-08-14 | ✅ 已落地 | 经工单 16~19 全部实现 |
| 16 | pre_equilibrate 引擎方法 + config 开关（默认开启） | 2026-08-14 | ✅ 已完成 | via /implement + /tdd |
| 17 | 偏离度诊断（初始 vs 稳态，全部交换离子） | 2026-08-14 | ✅ 已完成 | via /implement + /tdd |
| 18 | L9 重定义验证（预平衡后 fertilizer 30 年稳定） | 2026-08-14 | ✅ 已结束（结构性局限确认） | 三支柱后 fertilizer 仍耗尽（y3） |
| 19 | v0.5.0 收尾（文档同步 + code-review + commit） | 2026-08-14 | ✅ 已完成 | via /implement + /code-review |
| 20 | v0.6.0 Al 动力学（KINETICS）+ L6 逐层参数 spec | 2026-08-14 | ✅ 已落地 | 经工单 21~24（KINETICS 回退，L6 待实现） |
| 21 | RATES/KINETICS 实现 + L2 矿物回填双路径 | 2026-08-14 | 🔄 已回退 | v0.6.1 证据否定：冻结矿物切断 L2 回补 |
| 22 | k 参数扫描 + fertilizer 30 年验收 | 2026-08-14 | 🔄 已回退 | v0.6.1 结论撤回（排水淋失为主因） |
| 23 | L6 逐层参数覆盖（诊断性，研究应用基础） | 2026-08-14 | ✅ 已完成 | v0.4.0 (2026-08-17)：spec 29 + 工单 30~35 落地；139 测试全绿 |
| 24 | v0.6.0 收尾（文档同步 + code-review + commit） | 2026-08-14 | ✅ 已完成 | via /implement + /code-review |
| 25 | v0.6.1 数值稳定性 spec（KINETICS 偶发卡顿定位与解决） | 2026-08-17 | ✅ 已落地 | commit f7f92bf（子进程超时机制） |
| 26 | 子进程超时机制 + 卡顿定位 | 2026-08-17 | ✅ 已落地 | commit f7f92bf 保留 |
| 27 | KNOBS 调参 + 状态防护 + 超时降级兜底 | 2026-08-17 | ✅ 已落地 | commit f7f92bf |
| 28 | 30 年验收 + V0_6_1 报告收尾 | 2026-08-17 | ✅ 已落地 | 合并入 docs/reports/V0_3_0_FINAL_REPORT.md（7d19f9d） |
| 29 | L6 逐层参数覆盖 spec（layer_overrides/layer_depths） | 2026-08-17 | ✅ 已完成 | v0.4.0：spec 落地（/grilling 10 项决策） |
| 30 | L6 layer_overrides/layer_depths 配置解析与校验 | 2026-08-17 | ✅ 已完成 | v0.4.0：config_manager 解析/校验 + 测试 |
| 31 | L6 逐层 profile 构建与矿物增量覆盖 | 2026-08-17 | ✅ 已完成 | v0.4.0：InputReader/SoilDatabase + 测试 |
| 32 | L6 引擎逐层应用（初始态差异化 + 月度 pCO₂ 注入） | 2026-08-17 | ✅ 已完成 | v0.4.0：run_monthly_multi_layer layer_pco2s + 2 层集成 |
| 33 | L6 main.py 多层编排集成 | 2026-08-17 | ✅ 已完成 | v0.4.0：_build_initial_layer_states + 逐层预平衡 + 单层护栏 |
| 34 | L6 诊断实验工具 + 文档同步 | 2026-08-17 | ✅ 已完成 | v0.4.0：tools/plot_L6_layer_overrides.py + good/bad 标注图 + README/USERGUIDE/config 同步 |
| 35 | L6 收尾（全量测试 + code-review + commit + tag） | 2026-08-17 | ✅ 已完成 | v0.4.0：139 全绿 + 双轴审查 + 发布 |

---

## 二、架构决策工单（wayfinder/tickets/WF1~5）

| 工单 | 标题 | 成立时间 | 状态 | 说明 |
|------|------|----------|------|------|
| WF1 | 多分层模型架构决策（List[SoilState] + 一维平流 + 级联下渗） | 2026-08-13 | ✅ 已落地 | 决策完成，WF2 实现 |
| WF2 | 多分层模型实现（run_monthly_multi_layer 编排层 + n_layers 配置） | 2026-08-13 | ✅ 已完成 | 71 测试全绿 |
| WF3 | SURFACE 表面络合可行性调研（Hfo_s/Hfo_w） | 2026-08-13 | ✅ 已完成 | 确认 phreeqc.dat 原生支持 |
| WF4 | SURFACE 表面络合启用（enable_surface 配置 + P/Zn 吸附） | 2026-08-13 | ✅ 已完成 | 78 测试全绿 |
| WF5 | 多分层 + SURFACE 集成验证与回归 | 2026-08-13 | ✅ 已完成 | 82 测试全绿；Al 表面络合列独立工单 |

---

## 三、遗留规划工单（backlog/L1~L9）

| 工单 | 标题 | 成立时间 | 状态 | 说明 |
|------|------|----------|------|------|
| L1 | Al³⁺ 表面络合简化方法（Kd_eff + pH 修正） | 2026-08-14 | 🟡 方法报告完成，实现待独立工单 | docs/analysis/L1_AL_SURFACE_METHOD.md（v0.4.0）；吸收合并 L3 |
| L2 | Al 矿物化抑制（pH 突升根治） | 2026-08-14 | ✅ 已解决 | 矿物演化回填（SELECTED_OUTPUT -equilibrium_phases） |
| L3 | 有机质表面络合（换库 Tipping_Hurley） | 2026-08-14 | ✅ 已合并入 L1 | 换库方案搁置（热力学基线重校准风险） |
| L4 | 硝化两步动力学（尿素→NH₄⁺→NO₃⁻） | 2026-08-14 | ✅ 已完成 | v0.3.0 库存层实现（工单 06） |
| L5 | 电荷平衡 HCO₃ 缓冲（Q13*） | 2026-08-14 | ✅ 已完成 | v0.3.0 修正方案（工单 06；HCO₃⁻ 由 pCO₂ 决定 + Cl⁻ 兜底） |
| L6 | 逐层参数外部覆盖（layer_overrides） | 2026-08-14 | ✅ 已完成 | v0.4.0 (2026-08-17)：工单 23 + spec 29 + 工单 30~35；139 测试全绿；诊断实验 docs/analysis/L6_LAYER_OVERRIDES.md |
| L7 | 完整包结构（pip install） | 2026-08-14 | 📋 规划中 | 长期路线图 |
| L8 | 参数敏感性分析框架 | 2026-08-14 | 📋 规划中 | 长期路线图 |
| L9 | 矿物缓冲重新校准（fertilizer 长期 pH 突升根治） | 2026-08-14 | 🔴 结构性局限确认 | 排水淋失主导（v0.6.1）；方向 = 多层 + L6，完整证伪链见 docs/reports/V0_3_0_FINAL_REPORT.md 第六节 |

---

## 四、状态图例

| 标记 | 含义 |
|------|------|
| ✅ 已完成 | 实现 + 验证 + 提交均完成 |
| ✅ 已落地 | spec 类工单：其目标经一个或多个子工单完成 |
| 🔄 已回退 | 方案被证据否定后回退（KINETICS） |
| 🔴 结构性局限确认 | 扫描/证伪链确认模型架构层局限，非参数问题 |
| 🟡 部分完成 | 设计或方法报告完成，实现待后续独立工单 |
| 📋 规划中 | 长期路线图，未开工 |

> 汇总表由项目文件整理时生成；工单细节以各 `.md` 文件为准。
