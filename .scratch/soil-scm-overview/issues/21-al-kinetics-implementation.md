# 21 — RATES/KINETICS 实现 + L2 矿物回填双路径

**What to build:** Al 动力学核心——gibbsite / Al(OH)₃(a) 从 EQUILIBRIUM_PHASES 切到 KINETICS（RATES TST 一阶速率控制），SELECTED_OUTPUT 增加 -kinetics，`_parse_official_output` 按相分流回填（动力学相读 kinetics、平衡相读 equilibrium_phases）。其余矿物保持平衡路径。

**Blocked by:** None — can start immediately.

**Status:** ↩️ 已回退 (v0.6.1, 2026-08-14) — KINETICS 方案被证据否定

## 回退说明

KINETICS 实验证明有害（详见 `docs/V0_6_1_REPORT.md` 证据链）：速率太小冻结 gibbsite → 切断 L2 矿物回补 → AlX₃ 耗尽提前（y1 m7 vs 平衡相 y3）；v0.6.0 "2 年稳定"结论为误导。RATES/KINETICS 块、AL_KINETIC_* 常量、双路径回填已删除，恢复平衡相 + L2 单路径回填。

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
