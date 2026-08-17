# 28 — 30 年验收 + V0_6_1 报告收尾

**What to build:** fertilizer 单层 30 年验收（完整验收：降级步=0；或降级验收：降级步少 + 原因文档化 + 结果偏差评估）+ V0_6_1_REPORT + 文档同步 + commit。

**Blocked by:** 27 — KNOBS 调参 + 状态防护 + 超时降级兜底

**Status:** ready-for-agent

## Acceptance criteria

- [ ] fertilizer 30 年模拟完成（子进程超时下不卡死）
- [ ] 完整验收（降级步=0）或降级验收（降级步计数 + **无法完整验收的原因** + 结果偏差评估）
- [ ] AlX₃ 长期稳定性定论（KINETICS 效果）
- [ ] V0_6_1_REPORT + README/ROADMAP 同步
- [ ] 全量测试 + commit

## Background

- grilling Q4：优先完整验收；降级需说明原因（定位结论）
