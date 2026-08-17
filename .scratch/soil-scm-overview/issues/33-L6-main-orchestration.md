# 33 — L6 main.py 多层编排集成（T4）

**What to build:** 主程序 n_layers>1 时按逐层 profile/矿物/pCO₂ 构建初始状态、逐层独立预平衡、月度循环用逐层 pCO₂ 运行多层编排；`layer_depths` 传入输出器使列后缀与物理厚度一致；单层路径完全不变（回归护栏）。端到端运行验证多层差异化与单层回归。

**Blocked by:** 32（引擎逐层应用）

**Status:** ✅ 已完成 (2026-08-17, v0.4.0)

- [ ] n_layers>1：逐层构建初始状态 + 逐层 `pre_equilibrate`（覆盖后 profile 作锚定）
- [ ] `layer_depths` 传入输出器（替换现状 getattr 兜底）
- [ ] n_layers=1：路径不变，无 layer_overrides 时行为与现状完全一致
- [ ] 验证：既有单层回归护栏测试保持全绿
