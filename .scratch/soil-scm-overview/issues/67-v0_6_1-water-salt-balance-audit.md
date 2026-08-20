# 67 — v0.6.1 water_salt_balance 水量/盐分闭合审计工具

**What to build:** 新增 `tools/water_salt_balance.py` 闭合审计工具：读主 CSV（降水/径流/AET/排水/存储）与事件明细 CSV，逐月输出水量闭合 `ΣP=ΣRunoff+ΣAET+ΣQlat+ΣQbase+ΔS`（阈值 <1%）与盐分进出口对账（阈值 <5%）。为 v0.6.1 的水文/化学出口正确性提供工程保障底线。

**Blocked by:** 63（VIC 深层基流 + Darcy 侧向排水模块）、65（浓度硬上限冲洗 + 溶质出口记账）— 需要水量出口（Qlat/Qbase）与溶质出口（total_lateral_i/total_base_i）都已落地才能对账。

**Status:** ✅ 已完成 (2026-08-20, v0.6.1)

- [x] `tools/water_salt_balance.py`：读取主 CSV，计算逐月水量闭合（P − Runoff − AET − Qlat − Qbase − ΔS，|<1%|）与盐分进出口对账（|<5%|）
- [x] 输出闭合报表（CSV/控制台）：每月水量项、年度聚合、残差、是否超阈值告警
- [x] 30 年 8 情景闭合验证跑通（后台进程，避免工具 30s 超时）
- [x] 测试（S7）：构造已知收支样例验证闭合公式、阈值告警逻辑、年度聚合跳过前月占位行；**289 passed 全绿**
