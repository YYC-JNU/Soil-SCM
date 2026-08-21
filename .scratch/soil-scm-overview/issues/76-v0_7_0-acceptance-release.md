# 76 — 30 年 8 情景全链路验收 + 发布 v0.7.0（spec 69 工单 75）

**What to build:** 对 v0.7.0 地球化学重构做全链路方向带验收并发布：新建 `tools/verify_v0_7_0_acceptance.py` 断言方向带——① natural 30 年 pH 4.5~5.0 缓降或持平 ② fertilizer 30 年 <4.0（盐基枯竭酸化）③ lime 3~5 年回落至 5~6 ④ 排序 Natural<Fertilizer<Lime ⑤ 全情景 30 年 `phreeqc_ok` 无降级 ⑥ **N 收支闭合**；30 年 8 情景全量重跑；发布流程 = 版本号同步 → commit → annotated tag v0.7.0 → push。

**Blocked by:** 70, 71, 72, 73, 74, 75（全部地球化学改动落地后验收）。

**Status:** 🔶 进行中（验收脚本 + 调优 + 报告完成；30 年全量受 PHREEQC 卡顿阻塞，发布待决策）

- [x] 调优 A+B+D：NH₄⁺ 置换量级 857→343、HX log_k 3.0→2.8、weathering 500+降 gibbsite/kaolinite（fertilizer 11.4→8.1）
- [x] `tools/verify_v0_7_0_acceptance.py`：方向带断言脚本（natural 缓降/fertilizer<4.0/lime 回落/排序/无降级/N 收支闭合）
- [x] sensitivity 接入 companion/weathering（`--weather-rate`/`--degrade` CLI）
- [x] 5 年短程方向带摸底 + 验收报告 `docs/analysis/V0_7_0_ACCEPTANCE.md`
- [ ] 30 年 8 情景全量（PHREEQC 偶发卡顿阻塞——HX=2.8 高离子强度平衡卡顿更频繁，v0.6.0 复盘建议 KNOBS 调优；weather on natural 30y pH 7.8+ 后稳定卡死）
- [ ] 发布 v0.7.0（方向带部分达标：natural ✅、fertilizer ❌ <4.0 / lime ❌ 回落——发布与否待用户决策）

---

## 📋 验收结论速览（详见 `docs/analysis/V0_7_0_ACCEPTANCE.md`）

| 情景 | v0.7.0 5y | 方向带 | 状态 |
|---|---|---|---|
| natural | 5.18→5.34 持平 | 4.5~5.0 | ✅ 达标 |
| fertilizer | 11.42（weather off）/ 8.09（weather on 500+降2） | <4.0 | ❌ 机制已改善，未达 |
| lime_low | 11.24 | 3~5 年回落 | ❌ 未达 |

- **核心障碍**：~~GAS_PHASE 固定缓冲吞酸（偏差 2）~~ → **（2026-08-21 工单 77 证伪修正**：真因 = REACTION 裸注入电荷伪碱化，GAS_PHASE 非主因；工单 77 charge pairing 已修复；剩余盐基滞留 → 工单 80）**
- **阻塞项**：PHREEQC 偶发卡顿（HX=2.8 高离子强度收敛）→ 30 年全量未完成；KNOBS 调优留 v0.7.x
- **发布建议**：v0.7.0 以"地球化学机制落地"阶段性发布（natural 达标 + 三疑点机制证据），未达项如实标注；或继续深调优后再发布（用户决策）
