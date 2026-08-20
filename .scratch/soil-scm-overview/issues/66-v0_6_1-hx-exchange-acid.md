# 66 — v0.6.1 HX 交换酸注入 + GAP_H 缺口重分配

**What to build:** 为模型注入真实的**交换性 H 酸库**：通过 `EXCHANGE_SPECIES H+ + X- = HX`（log_k=1.0）自定义注入（phreeqc.dat 已注释禁用 HX 定义，须仿照 ALX3 注入先例）；初始条件中 `exch_h` 直接映射 HX（从 Na 剥离，不再并入 NaX）；CEC 缺口按 `GAP_H_FRACTION=0.3 / GAP_AL_FRACTION=0.3 / NaX 余量` 三通道重分配。使表层交换性酸缓冲真实存在、Natural 酸化有 H 缓冲（对治 pH 暴降至钳制值的极端趋向）。

**Blocked by:** None — can start immediately（依赖 spec 62 决策表 Q7，2026-08-20 定案）。

**Status:** ready-for-agent

- [ ] `constants.py` 新增 `HX_LOGK=1.0`、`GAP_H_FRACTION=0.3`（可配）
- [ ] `_build_phreeqc_input()` 注入 `EXCHANGE_SPECIES` 块：`H+ + X- = HX` + `-log_k 1.0`（仿 ALX3 注入先例，SELECTED_OUTPUT 增 HX molality 列）
- [ ] `build_exchange()`：`exch_h` 直接映射 HX（`h_mol = exch_h/100 × mass`），不再并入 `na_mol`
- [ ] 缺口重分配：`gap_cmol × GAP_H_FRACTION → HX`、`gap_cmol × GAP_AL_FRACTION → AlX3`、余量 → NaX；CEC 总量守恒不变量保持
- [ ] `_parse_official_output` 交换解析列表增 HX（`m_HX(mol/kgw)`）；SELECTED_OUTPUT molalities 增 HX
- [ ] 测试（S4）：`exch_h→HX` 映射（从 Na 剥离的数学断言）、GAP_H 缺口重分配、CEC 总量守恒、HX EXCHANGE_SPECIES 注入字符串断言、HX 平衡后状态回填
- [ ] E1 预平衡收敛值变化如实记录（工单 68 复验，本单仅实现）
