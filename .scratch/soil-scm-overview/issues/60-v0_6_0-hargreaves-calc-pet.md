# 60 — v0.6.0 Hargreaves calc_pet 单入口分派

**What to build:** PET 通道升级（spec 55 §6，Q8/Q9/Q13，Oudin 精度增强模式）：`climate_forcing.py` 新增单入口 `calc_pet(t_mean, latitude, month, method='oudin', diurnal_range_deg=8.0)`，内部按 `pet_method` 分派——`"oudin"`（默认，`calc_pet_oudin` 回归不变）/ `"hargreaves"`（`PET = 0.0023×R_a×(T_mean+17.8)×√(T_max−T_min)`，`T_max=T_mean+range/2`、`T_min=T_mean−range/2`，R_a 复用 Oudin 日地/赤纬/时角计算）/ `"hargreaves_enhanced"`（**只预留枚举 + 显式报错**，数据管线留 v0.7.0）。`ClimateForcing._generate_pet` 改走 `calc_pet`。config 新增 `climate.diurnal_range_deg`（默认 8.0，>0 校验）。输出仍为 n_years×12 逐月 PET 数组，下游 ET 扣除无需知道方法来源。与事件化主链完全解耦，可并行。

**Blocked by:** None — can start immediately（spec 55 已定案）

**Status:** ready-for-agent

- [ ] `calc_pet` 单入口分派：`"oudin"` 与 `calc_pet_oudin` 数值等价（回归测试）
- [ ] `"hargreaves"` 公式端点正确（T_max/T_min 代入断言）；日较差敏感性（range↑→PET↑）
- [ ] `"hargreaves_enhanced"` 显式报错（不静默）
- [ ] `_generate_pet` 改走 `calc_pet`；`pet_monthly_climate` 兜底优先语义不变
- [ ] config：`diurnal_range_deg` 解析 + 值域校验（>0）；config.yaml/config_example.yaml 同步
- [ ] 全测试绿（S4 接缝 test_climate_forcing.py 扩展 + test_config_manager.py）
