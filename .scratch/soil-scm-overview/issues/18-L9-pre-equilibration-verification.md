# 18 — L9 重定义验证（预平衡后 fertilizer 30 年稳定）

**What to build:** 预平衡默认开启后，验证 fertilizer 单层 30 年 AlX₃ 稳定、pH 无突升、无降级——L9 深层修复落地验证。同时复核 natural 30 年基线（预平衡后新稳态合理性）。

**Blocked by:** 16 — pre_equilibrate 引擎方法 + config 开关; 17 — 偏离度诊断

**Status:** ✅ 已完成 (2026-08-14, via /implement + /tdd) — 结构性局限确认

## 完成说明

三支柱落地后验证：缺口修正（GAP_AL_FRACTION=0.3）改善初始自洽（首平衡 pH 4.92）但 fertilizer 仍耗尽（y3）；**AlX₃ 交换 log_k 扫描（0.41/2/5/10）全部无效**——L9 交换选择性方向证伪，确认结构性局限（单层排水 + 盐基置换）。完整证伪链见 `docs/V0_5_0_REPORT.md` 第四节。natural 基线复核通过。

**验证**：113 passed。

## Acceptance criteria

- [ ] 预平衡默认开后 fertilizer 单层 30 年 AlX₃ > 1e4 mol + pH 全程 < 9 + 官方引擎不降级
- [ ] natural 30 年基线复核（预平衡后 pH/AlX₃ 行为科学评估）
- [ ] 偏离度诊断符合"稳态接近观测"预期（或记录合理偏离）
- [ ] 全量 pytest 全绿

## Background

- grilling Q6=A：预平衡成为 L9 深层修复落地载体；"交换选择性/动力学"降为备选
- 若预平衡后仍无法稳定 fertilizer，L9 备选方向（Al 交换选择性校准）启用
