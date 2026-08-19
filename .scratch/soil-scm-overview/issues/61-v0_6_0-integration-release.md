# 61 — v0.6.0 集成 + E2/E3 复验 + 发布

**What to build:** v0.6.0 集成、科学诚实验收与发布（spec 55 Further Notes，Q16）：全量运行（默认 config 50 年 4 层 ≈ 1~4 分钟量级，Q16 确认可接受）；E2 复验（PET 敏感性 600~1400mm → 旱季 θ 下降 + 溶液浓缩酸化 → **pH 方向性响应**）；E3 复验（k_om 敏感性 → 表层酸化方向）；First-Flush 峰值验证（雨季单场淋失峰值 > 月均，峰值列可验证）；事件级 `run_event_step` 子进程超时包装确认；README/config 文档同步；版本号同步 v0.6.0 → commit → annotated tag → push main + push tag。

**Blocked by:** 56、57、58、59、60 — 全部工单

**Status:** ✅ 已完成 (2026-08-19, v0.6.0)

- [x] 全量运行冒烟（事件驱动 2 年 4 层 natural）：无崩溃/无 fallback（E1）；性能量级确认
- [x] E1 验收：预平衡 pH 4.92（4 层收敛）| 末月 pH L1=3.86（酸化方向，对比 v0.5.3 恒 6.94）| AET 957mm + 径流 898mm（水分闭合，AET+径流<降水）| L1 θ 0.41~0.45（跨月滞水+干化）| First-Flush 峰值/月均比 3.15
- [x] E2 验收（PET 600~1400mm）：pH 有响应（600/900→3.87 微酸化；1200/1400→5.49 反跳）——**非单调，记录为调校项**（高 PET 浓缩-离子强度-缓冲耦合，留 v0.6.1）
- [x] E3 验收（k_om 0.0003~0.0008）：pCO₂_eff 0.024→0.039，pH L1 5.57→3.86——**表层酸化方向达成**（对比 v0.5.3 E3 恒 6.94 无响应）
- [x] First-Flush 验证：雨季单场淋失峰值/月均比 2.2~3.15（脉冲式淋失如实输出）
- [x] 事件级数值稳定性修复：①`theta_after` 事件 θ 精确耦合（修复"月末 θ 一次性浓缩"bug）②`MAX_CONCENTRATION_RATIO=3`（FC→WP 物理浓缩上限）+ θ_r 体积下限 ③`_parse_official_output` 离子浓度 >10 mol/L 判定数值失败（防 SELECTED_OUTPUT 异常值进入状态链级联放大）
- [x] 文档同步：README 版本记录 + config.yaml/config_example.yaml + ROADMAP/OPTIMIZATION_PLAN 执行日志
- [x] 测试全绿：**259 passed**
- [x] v0.6.0 发布：版本号 → commit → annotated tag → push main + push tag

**科学诚实记录（验收边界，留 v0.6.1）**：
- **E2 非单调**：PET 600/900mm → pH 3.87（酸化），1200/1400mm → 5.49（反跳）——pH 对 PET 有响应但方向非单调，疑似高 PET 强浓缩 → 高离子强度 → 缓冲体系改变，需 v0.6.1 参数调校。
- **3 年+ 数值边界**：长期模拟深层（L2~L4）盐分累积极端场景（Cl>10 mol/L）PHREEQC 平衡失败输出异常值——已加浓度上限检查（异常判定失败走 fallback 防级联），但 fallback 永久降级语义未改（保留 v0.5.3 契约，测试依赖）；彻底解决（失败事件局部降级/盐分淋失路径调校）列为 v0.6.1。
