# 17 — 偏离度诊断（初始 vs 稳态，全部交换性离子）

**What to build:** pre_equilibrate 产出偏离度诊断——对比初始 vs 稳态的 pH 与全部交换性离子（CaX2/MgX2/KX/NaX/AlX3 对应 config 输入），计算 Δ 并日志输出；科学判据（ΔpH<0.5、各交换离子相对变化 <20%）超出警示。用于验证"稳态接近实测"预期与输入参数物理性。

**Blocked by:** 16 — pre_equilibrate 引擎方法 + config 开关

**Status:** ✅ 已完成 (2026-08-14, via /implement + /tdd)

## 完成说明

偏离度诊断覆盖 pH + 全部交换性离子（CaX2/MgX2/KX/NaX/AlX3），Δ 日志输出 + 阈值警示（ΔpH<0.5 / 离子<20%）。测试覆盖 Δ 计算与诊断数据完整性。

**验证**：113 passed。

## Acceptance criteria

- [ ] 诊断覆盖 pH + 全部交换性离子（Ca/Mg/K/Na/Al，对应 config exchangeable_ions 输入）
- [ ] Δ 计算正确（初始 vs 稳态）并日志输出
- [ ] 科学判据：ΔpH<0.5、各交换离子相对变化 <20% 视为"输入物理合理"，超出警示
- [ ] 测试覆盖 Δ 计算与阈值判定

## Background

- grilling Q5=A：不能只看 pH 和 Al³⁺，config 输入的交换性离子观测值都应纳入判断
- 诊断同时是 L9 验证（AlX₃ 不再被矿物吸干）与输入参数物理性检验
