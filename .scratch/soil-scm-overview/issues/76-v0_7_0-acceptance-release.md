# 76 — 30 年 8 情景全链路验收 + 发布 v0.7.0（spec 69 工单 75）

**What to build:** 对 v0.7.0 地球化学重构做全链路方向带验收并发布：新建 `tools/verify_v0_7_0_acceptance.py` 断言方向带——① natural 30 年 pH 4.5~5.0 缓降或持平 ② fertilizer 30 年 <4.0（盐基枯竭酸化）③ lime 3~5 年回落至 5~6 ④ 排序 Natural<Fertilizer<Lime ⑤ 全情景 30 年 `phreeqc_ok` 无降级 ⑥ **N 收支闭合**（`water_salt_balance.py` N 行逐月 <阈值，初定 5%）；30 年 8 情景全量重跑；发布流程 = 版本号同步 → commit → annotated tag v0.7.0 → push main + push tag + 文档同步（README/ROADMAP/HANDOFF）。

**Blocked by:** 70, 71, 72, 73, 74, 75（全部地球化学改动落地后验收）。

**Status:** ready-for-agent

- [ ] `tools/verify_v0_7_0_acceptance.py`：方向带六断言全部 PASS + N 收支闭合
- [ ] 30 年 8 情景全量重跑：`output/sensitivity_pH_30yr_v070.csv` + `.png` + 科学解读更新（三疑点解决状态）
- [ ] 中间里程碑复核：fertilizer 3~5 年转向下降（工单 70/71 后）、natural 缓降（工单 73 后）
- [ ] 发布 v0.7.0：版本号 → commit → annotated tag → push main + push tag；README/ROADMAP/HANDOFF 同步
- [ ] 全测试套件全绿（含既有 289 回归）
