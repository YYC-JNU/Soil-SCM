# 50 — v0.5.3 VGM 模块 + θ 状态迁移（T1）

**What to build:** 新建 `src/vgm.py`（VGM 水分特征纯函数：`vgm_theta_from_psi`/`calc_psi`/`calc_Kr`/`calc_K` + `get_vgm_params` 三级优先级 + `feddes_alpha` + θ↔L/ha 换算 `theta_to_water_L`/`water_L_to_theta`，往返恒等）；`SoilState.stored_water`→`theta` 字段迁移（θ 规范状态，stored_water 由纯函数派生，引擎/输出边界换算）；`build_initial_state` 设初始 θ=vgm(initial_psi_cm=−100)（L1≈0.81θ_s）；化学初始溶液体积 `_calc_solution_volume` 改 `θ_init×depth×1e5`（删 0.5×φ）；config 新增 `simulation.initial_psi_cm` + `layer_overrides.vgm_theta_r/vgm_alpha/vgm_n`（值域校验）。n_layers=1 不启用 VGM 物理（护栏）。

**Blocked by:** None — can start immediately（spec 49 已定案）

**Status:** ✅ 已完成 (2026-08-19, v0.5.3)

- [x] `src/vgm.py`：vgm_theta_from_psi/calc_psi/calc_Kr/calc_K 数值正确（手算验证）；Mualem l=0.5；θ_s≡porosity
- [x] `get_vgm_params` 三级优先级：layer_overrides 显式 > clay_pct 回归（θ_r=0.01+0.002×clay；α=0.04−0.0006×clay；n=1.5−0.008×clay）> 红壤兜底（0.08/0.015/1.25）
- [x] 换算函数往返恒等：θ→L→θ（覆盖 depth 20/20/20/40、θ=0、θ=θ_s 边界）（S1 专家★1）
- [x] `SoilState`：`stored_water`→`theta` 字段；引擎/输出边界换算无单位泄漏（S5 专家★1）
- [x] `build_initial_state` 设 state.theta = vgm_theta_from_psi(−100)；L1 实测 θ≈0.410（0.75θ_s）——注：VGM参数化方案.txt 的 "0.81θ_s/0.88θ_s" 为粗略估计，与给定参数下 VGM 公式精确值不符（0.75θ_s/0.95θ_s），测试以公式精确值为准并记录该差异
- [x] `_calc_solution_volume` = θ_init×depth×1e5（删 saturation=0.5）
- [x] config：initial_psi_cm<0、vgm_theta_r∈[0,θ_s)、vgm_alpha>0、vgm_n>1 校验
- [x] n_layers=1 单层回归不变量不变
- [x] 测试（S1 新 seam test_vgm.py + S4/S5）：全绿 + 既有测试按 Q6 契约更新（每条记录理由）；**202 passed 全绿**
