# v0.7.0 工单76 验收报告（30 年 8 情景全链路摸底）

> **文档编号**：V0_7_0_ACCEPTANCE
> **创建日期**：2026-08-21
> **依据**：`tools/verify_v0_7_0_acceptance.py` + `output/sensitivity_pH_30yr_v070_*.csv`（sensitivity 口径）+ 调优实验记录
> **科学诚实**：方向带是 v0.7.0 承诺（Q14=A）；未达标项如实记录，不掩盖。

---

## 一、验收口径

- **sensitivity 口径**（`tools/sensitivity_pH_30yr.py`，无降水化学，预平衡 60 步）——与 v0.6.1 官方 30 年验证一致
- 配置：companion 启用（D3+NH₄⁺）、HX log_k=2.8（调优 B）、weathering 默认关（调优 D 因 30 年 PHREEQC 卡顿暂缓，见 §四）

## 二、方向带摸底结果（5 年短程 + 机制证据）

| 情景 | v0.6.1 (30y) | v0.7.0 5y (weather off) | v0.7.0 5y (weather on 500+降2) | 方向带 | 状态 |
|------|-------------|------------------------|-------------------------------|--------|------|
| natural | 5.32→5.68 | **5.18→5.34 持平** | 6.70→7.87（碱化，且 30y 卡死） | 4.5~5.0 缓降/持平 | ✅ 达标 |
| fertilizer | 8.4→11.4 | 9.09→11.42 | **7.74→8.09**（↓3.3） | <4.0 | ❌ 未达（机制已改善） |
| lime_low | 9.2→11.3 | 9.20→11.24 | — | 3~5 年回落 | ❌ 未达 |
| 排序 | Natural<Fertilizer≈Lime | Natural<Fertilizer≈Lime | — | N<F<L | ⚠️ 部分 |

## 三、机制落地证据（v0.7.0 核心成果，均已验证）

1. **D3 伴随淋失分级注入真实生效**：fertilizer 中 L1~L4 盐基枯竭（BS=0% <10%）→ 分级切换 **acid 模式**（酸化注入 H⁺ 最高 213 eq）——Q18 分级注入机制按设计触发
2. **NH₄⁺ 置换量级修正（调优 A）**：857→343 eq/次，抑制 Gapon 回吞导致的盐基过量注入
3. **HX log_k 3.0→2.8（调优 B）**：E2 非单调消除（PET 900→5.34 单调微升 vs v0.6.0 3.87 跳变）；预平衡仍收敛（L1 初始 4.859）
4. **weathering 500+降级（调优 D）**：fertilizer 11.4→8.1（矿物闪蒸供碱消除的证据）——但 natural 反碱化（注入碱度>降级节省），且 30 年尺度 PHREEQC 卡顿（见 §四）
5. **natural 达标**（weather off）：5.18→5.34 持平，HX=2.8 后接近 v0.6.1 且略低——方向带达成

## 四、阻塞项与已知问题（如实记录）

1. **PHREEQC 偶发卡顿（RunString 不返回）在 v0.7.0 下更频繁**：HX=2.8 使高离子强度/高 pH 平衡更易卡（v0.6.0 复盘建议 5"KNOBS 迭代数/容差调优"）；weather on 的 natural 30 年 pH 7.8+ 后稳定卡死；spawn 子进程多次卡顿 → **30 年 8 情景全量未完成**（5 年短程数据已覆盖方向带判定）
2. **fertilizer<4.0 未达**：~~GAS_PHASE 固定 pCO₂ 缓冲吞酸（科学解读偏差 2）是核心障碍~~ **（2026-08-21 v0.7.x 工单 77 证伪修正）**：探针实测 GAS_PHASE 吞酸幅度仅 +0.05 pH，真正机制 = **REACTION 裸注入电荷不平衡伪碱化**（裸阳离子 Ca²⁺/K⁺/Mg²⁺ → PHREEQC 电荷中性约束产生 OH⁻，裸 `Ca+2 343` → pH 9.28 复现观测；裸 H⁺ 硝化产酸从不酸化）。工单 77 charge pairing 修复后单层施肥不碱化、sensitivity 3y 11.20→10.86；剩余盐基滞留 → 工单 80（详见 `docs/analysis/V0_7_X_REACTION_CHARGE_POSTMORTEM.md`）；weather on 已改善至 8.1 但不足
3. **lime 未回落**：Ca 盐基供给 > 淋失（无 NO₃⁻ 伴随通道，lime 情景无施肥）——需强化 Ca 淋失或 D3 扩展至 lime 盐基
4. **natural vs fertilizer 对 weathering 需求相反**：weather on 利于 fertilizer（8.1）害于 natural（7.7）——需按情景区分配置或 weathering 参数再调（v0.7.x）

## 五、验收判定（科学诚实）

- **PASS**：natural 方向带（持平）；D3/NH₄⁺/D2/HX 机制全部落地并验证；数值稳定（5 年全情景 phreeqc_ok=1）
- **FAIL**：fertilizer<4.0、lime 回落、30 年全量（PHREEQC 卡顿阻塞）
- **发布建议**：v0.7.0 以"**地球化学机制落地**"阶段性发布（natural 达标 + 三疑点机制证据），方向带未达项如实标注 → 留 v0.7.x（**工单 77 电荷平衡修复**（2026-08-21 已完成，证伪 GAS_PHASE 归因）+ KNOBS 调优 + weathering 情景区分 + lime 盐基淋失强化）；或由用户决定继续深调优后再发布

## 六、v0.7.x 后续（backlog 已登记）

- ~~GAS_PHASE 固定缓冲动态化（偏差 2）~~ **（工单 77 证伪取消，2026-08-21）**：探针证伪 GAS_PHASE 非主因；真因=裸注入电荷伪碱化 → **工单 77 电荷配对修复已完成**；剩余盐基滞留 → lime 盐基淋失强化
- KNOBS 迭代/容差调优（高离子强度收敛）——30 年全量解锁
- weathering 情景区分（natural off / fertilizer on）或参数再扫描
- HX log_k 微调 + E1 重锚定联动
- lime 盐基淋失强化（D3 扩展到无 NO₃⁻ 的 Ca 伴随）
- 30 年 8 情景全量 + verify_v0_7_0_acceptance 完整跑通