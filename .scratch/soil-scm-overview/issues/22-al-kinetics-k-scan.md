# 22 — k 参数扫描 + fertilizer 30 年验收

**What to build:** 动力学速率常数 k 参数扫描（初值 1e-8~1e-10 mol/s），验收 fertilizer 30 年 AlX₃>1e4 + pH<9 + 无降级；确定有效区间并文档化扫描记录（延续 L9 扫描方法论）。

**Blocked by:** 21 — RATES/KINETICS 实现 + L2 矿物回填双路径

**Status:** 🟡 部分完成 (2026-08-14) — 2 年验证 AlX₃ 稳定 (k 不敏感)，30 年验收受 PHREEQC 数值卡顿限制

## 完成说明

k 扫描（1e-10~1e-7）：fertilizer 单层 2 年 AlX₃ 稳定 ~34,000 mol（无耗尽，pH 5.5）——KINETICS 阻断 Al 汇效果初步确认。5 年+ 偶发 PHREEQC 收敛卡顿（RunString 不返回），30 年验收改为 2 年验证 + 数值限制文档化（V0_6_0_REPORT 第四节）。

## Acceptance criteria

- [ ] k 扫描（多档，分档运行）记录 pH/AlX₃/耗尽年/降级
- [ ] 选定 k 档：fertilizer 30 年 AlX₃ > 1e4 + pH < 9 + 无降级
- [ ] 扫描结论（有效或结构性局限）文档化（V0_6_0 报告）
- [ ] natural 基线复核（动力学切换不显著改变）

## Background

- grilling Q5=A：TST 一阶 + k 扫描；Q7=A 完整验收
- 若全档无效：记录为结构性局限（与 L9 证伪链一致），L6 仍是研究应用方向
