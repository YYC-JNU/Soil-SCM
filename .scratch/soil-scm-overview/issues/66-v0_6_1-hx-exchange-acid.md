# 66 — v0.6.1 HX 交换酸注入 + GAP_H 缺口重分配

**What to build:** 为模型注入真实的**交换性 H 酸库**：通过 `EXCHANGE_SPECIES H+ + X- = HX`（log_k=1.0）自定义注入（phreeqc.dat 已注释禁用 HX 定义，须仿照 ALX3 注入先例）；初始条件中 `exch_h` 直接映射 HX（从 Na 剥离，不再并入 NaX）；CEC 缺口按 `GAP_H_FRACTION=0.3 / GAP_AL_FRACTION=0.3 / NaX 余量` 三通道重分配。使表层交换性酸缓冲真实存在、Natural 酸化有 H 缓冲（对治 pH 暴降至钳制值的极端趋向）。

**Blocked by:** None — can start immediately（依赖 spec 62 决策表 Q7，2026-08-20 定案）。

**Status:** ✅ 已完成 (2026-08-20, v0.6.1)

- [x] `constants.py` 新增 `HX_LOGK=3.0`（扫描标定值，见下）、`GAP_H_FRACTION=0.3`（可配）
- [x] `_build_phreeqc_input()` 注入 `EXCHANGE_SPECIES` 块：`H+ + X- = HX` + `-log_k 3.0`；SELECTED_OUTPUT molalities 增 HX
- [x] `build_exchange()`：`exch_h` 直接映射 HX（从 Na 剥离）；缺口三通道 HX/AlX3/NaX 重分配；`_calc_exchange_site_total` 计入 HX
- [x] `_parse_official_output` 交换解析列表增 HX；预平衡诊断快照增 HX
- [x] **HX_LOGK 扫描标定**（2026-08-20 实测）：log_k=1.0→平衡 pH 3.74（预平衡无法锚定观测 5.0）；**log_k=3.0→pH 4.99（自然收敛观测）**；≥5.0→pH 过高且 HX 膨胀超 CEC
- [x] **预平衡契约修订**：HX 为标定酸库不纳入观测锚定；偏差>50% 离子跳过锚定（防注入冲垮交换相）；盐基 Ca/Mg/K/Na 锚定 <10% 保持
- [x] 测试（S4）：`exch_h→HX` 映射、GAP_H 缺口重分配、CEC 总量守恒、HX EXCHANGE_SPECIES 注入断言、HX 平衡状态回填、预平衡盐基锚定；**279 passed 全绿**
