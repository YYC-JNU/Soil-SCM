# 16 — pre_equilibrate 引擎方法 + config 开关（默认开启）

**What to build:** 新增引擎层 `pre_equilibrate` 方法——无干预多步化学平衡（复用 run_monthly_step，无降水/施肥，固定 pCO₂），使初始状态热力学自洽；config 新增 `enable_pre_equilibration`（默认 true）与 `pre_equilibration_max_steps`（默认 60）；main.py 集成；simplified 跳过。

**Blocked by:** None — can start immediately.

**Status:** ✅ 已完成 (2026-08-14, via /implement + /tdd)

## 完成说明

`pre_equilibrate` 观测锚定实现（v0.5.0 支柱②）：先平衡一步暴露漂移 → 仅锚定交换离子（比例-阻尼控制，REACTION 注入对应阳离子）→ 收敛（偏差<10%）→ 偏离度诊断（pH 自然平衡记录）。pH 锚定已移除（GAS_PHASE 固定分压 CO₂ 缓冲吸收碱，实测无效）。config `enable_pre_equilibration` 默认 true + `pre_equilibration_max_steps` 默认 100。main.py 集成（enable 时调用）。simplified 跳过。

**验证**：113 passed（含交换离子锚定/诊断/缺口修正测试）。

## Acceptance criteria

- [ ] `pre_equilibrate(state, soil_profile)` 无干预多步平衡，收敛判据（连续两步 pH 变化 <0.01 且 AlX₃ 相对变化 <1%）或 max_steps 截断
- [ ] config `enable_pre_equilibration` 默认 true、`pre_equilibration_max_steps` 默认 60
- [ ] main.py 在 build_initial_state 后调用（enable 时）
- [ ] simplified 引擎跳过（返回原状态）
- [ ] 全量 pytest 全绿

## Background

- v0.4.0 L9 扫描：调参数/相均无效，根因是初始状态不自洽（三相独立估算，首次平衡剧烈重分配）
- grilling Q3=A：无干预多步平衡；Q4=A：默认开启
- 预平衡走 run_monthly_step（含 L2 矿物回填），不引入淋洗/施肥
