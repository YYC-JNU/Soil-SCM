# 61 — v0.6.0 集成 + E2/E3 复验 + 发布

**What to build:** v0.6.0 集成、科学诚实验收与发布（spec 55 Further Notes，Q16）：全量运行（默认 config 50 年 4 层 ≈ 1~4 分钟量级，Q16 确认可接受）；E2 复验（PET 敏感性 600~1400mm → 旱季 θ 下降 + 溶液浓缩酸化 → **pH 方向性响应**）；E3 复验（k_om 敏感性 → 表层酸化方向）；First-Flush 峰值验证（雨季单场淋失峰值 > 月均，峰值列可验证）；事件级 `run_event_step` 子进程超时包装确认；README/config 文档同步；版本号同步 v0.6.0 → commit → annotated tag → push main + push tag。

**Blocked by:** 56、57、58、59、60 — 全部工单

**Status:** ready-for-agent

- [ ] 全量运行 50 年 4 层 natural 冒烟通过（性能量级确认，无崩溃/无 fallback）
- [ ] E2 复验：PET 敏感性 → 旱季 θ 下降 + pH 方向性响应（科学诚实：只承诺方向，不承诺具体值）
- [ ] E3 复验：k_om 敏感性 → 表层酸化方向
- [ ] First-Flush 验证：雨季单场淋失峰值 > 月均（峰值列/事件明细证据）
- [ ] 事件级子进程超时包装确认（`run_event_step` 粒度）
- [ ] 文档同步：README 版本记录 + config.yaml/config_example.yaml + ROADMAP/OPTIMIZATION_PLAN 执行日志
- [ ] 测试全绿（目标 260~270）
- [ ] v0.6.0 发布：版本号 → commit → annotated tag → push main + push tag
