# WF5 — 多分层 + SURFACE 集成验证与回归

**Label:** `wayfinder:task`
**Status:** open
**Parent:** 多分层模型与 SURFACE 表面络合（wayfinder:map）

## Question

多分层模型与 SURFACE 表面络合两项改造全部落地后，进行集成验证与回归收尾。

验证目标（对应 ROADMAP 已知局限的解决确认）：

1. **pH 突升问题验证**：`n_layers=4` + SURFACE 下运行 30 年 natural 情景，确认交换性 Al 不再耗尽、pH 不再突升（对比 ROADMAP "第 8 年 pH 突升 10.2" 的已知局限）。
2. **Al 垂直分布**：确认 Al 在下层累积（真实红壤特征），而非单层被淋洗殆尽。
3. **盐基优先淋洗**：确认表层盐基优先流失、下层相对富集的垂直梯度。
4. **SURFACE 吸附生效**：确认 P/Zn/Al 吸附描述在多层下正常工作。
5. **文档收尾**：更新 README/ROADMAP/OPTIMIZATION_PLAN，标记 Q12*、Q9 为已解决；更新 spec。
6. **回归护栏**：`n_layers=1` 单层路径仍可用、结果与历史一致。

## 阻塞

- **WF2 — 多分层模型实现**
- **WF4 — SURFACE 表面络合启用决策与实现**

## 验收

- [ ] 30 年 natural 多层模拟 pH 曲线物理合理（无突升）
- [ ] 交换性 Al 逐层分布合理（下层累积）
- [ ] SURFACE 吸附在多层下生效
- [ ] `n_layers=1` 单层回归通过
- [ ] 文档与 spec 已更新，Q12*/Q9 标记已解决
- [ ] 完整测试套件全绿
