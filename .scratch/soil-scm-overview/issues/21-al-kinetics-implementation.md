# 21 — RATES/KINETICS 实现 + L2 矿物回填双路径

**What to build:** Al 动力学核心——gibbsite / Al(OH)₃(a) 从 EQUILIBRIUM_PHASES 切到 KINETICS（RATES TST 一阶速率控制），SELECTED_OUTPUT 增加 -kinetics，`_parse_official_output` 按相分流回填（动力学相读 kinetics、平衡相读 equilibrium_phases）。其余矿物保持平衡路径。

**Blocked by:** None — can start immediately.

**Status:** ✅ 已完成 (2026-08-14, via /implement + /tdd)

## 完成说明

RATES/KINETICS 实现（gibbsite/Al(OH)₃(a) 切动力学，TST 一阶），L2 双路径回填（-kinetics 输出 k_<db_name>，动力学相/平衡相分流）。相名映射（minerals 键小写 ↔ 数据库相名大写）、BASIC 调试（si↔sat、10^si↔EXP）、性能优化（rate 去 ×m）。KNOBS 迭代 KINETICS 时 1000。

**验证**：117 passed（分块）；Al 动力学测试 4 全绿。

## Acceptance criteria

- [ ] 输入含 RATES（gibbsite + Al(OH)₃(a)，`rate = k×(10^SI−1)`）与 KINETICS 块
- [ ] Al 相不在 EQUILIBRIUM_PHASES（其余矿物保留）
- [ ] SELECTED_OUTPUT 含 `-kinetics`
- [ ] `_parse_official_output` 双路径回填正确（动力学相摩尔量、平衡相不受影响）
- [ ] 全量 pytest 全绿（含新增回填测试）

## Background

- L9 证伪链：Al 矿物化单向汇是 fertilizer 耗尽核心机制（v0.5.0）
- grilling Q3=B：仅 Al 关键相切 KINETICS，改动可控
- L2 矿物回填（-equilibrium_phases）需适配动力学相
