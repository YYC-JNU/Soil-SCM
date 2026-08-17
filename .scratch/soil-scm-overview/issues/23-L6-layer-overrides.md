# 23 — L6 逐层参数覆盖（诊断性，研究应用基础）

**What to build:** config 支持逐层参数覆盖（容重/CEC/交换性离子/矿物/pCO₂），真实剖面约束下的 fertilizer 行为诊断；保持 n_layers=1 单层兼容与各层默认相同（无覆盖时）。

**Blocked by:** None — can start immediately (与工单 21 并行).

**Status:** ✅ 已完成 (2026-08-17, v0.4.0)

## 完成说明

config `layer_overrides` 设计（容重/CEC/交换离子/矿物/pCO₂，单层兼容）记录于 V0_6_0_REPORT 第五节；**完整实现已落地 v0.4.0**（2026-08-17）：spec 见 `issues/29-L6-layer-overrides-spec.md`，实现工单 30~35，测试 139 全绿，诊断实验 `tools/plot_L6_layer_overrides.py` + `docs/analysis/L6_LAYER_OVERRIDES.md`。

## Acceptance criteria

- [x] config `layer_overrides` 解析（逐层容重/CEC/交换离子/矿物/pCO₂，另含 ph/有机质/layer_depths）
- [x] 按层应用覆盖（InputReader/初始构建），各层默认相同保持兼容
- [x] 单层（n_layers=1）回归不受影响
- [x] 测试覆盖：覆盖解析、按层应用、单层回归

## Background

- grilling Q2=A：L6 作为诊断性方向（预期"推迟耗尽"而非"根治"）
- ROADMAP 长期：研究区实测剖面数据接入（研究应用必需）
- 真实剖面数据缺失时各层默认相同（既有 WF1 决策）
