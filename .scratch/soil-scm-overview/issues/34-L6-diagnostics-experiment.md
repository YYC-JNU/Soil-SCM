# 34 — L6 诊断实验工具 + 文档同步（T5）

**What to build:** 诊断脚本运行"真实剖面 4 层（表层薄+低pH+高CEC+高有机质+富铁氧化物 / 底层厚+紧实+高pCO₂）vs 等参 4 层基线"的 fertilizer 长期对比，输出对比图（pH 时间序列 + AlX₃ 时间序列），并用 matplotlib 标注 **good influence（绿色）与 bad influence（红色）**（含耗尽年/年 pH 差数值）；实验结论记录到文档；README/USERGUIDE/config.yaml 同步 layer_overrides 用法。

**Blocked by:** 33（端到端编排能力）

**Status:** ✅ 已完成 (2026-08-17, v0.4.0)

- [ ] 诊断脚本：真实剖面 vs 等参基线，fertilizer 长期模拟
- [ ] 对比图：pH + AlX₃ 子图，good/bad influence 标注（含数值）
- [ ] 实验结论文档记录（good 与 bad 都如实记录，科学诚实）
- [ ] 文档同步：README 已知局限/新功能、USERGUIDE 配置章节、config.yaml 注释示例
