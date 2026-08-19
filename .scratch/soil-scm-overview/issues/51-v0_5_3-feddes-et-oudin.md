# 51 — v0.5.3 Feddes ET / Oudin PET（T2）

**What to build:** `climate_forcing.py` 新增 `calc_pet_oudin(T_mean, latitude, month)` 逐月 n_years×12 PET 数组（月中日 J、含年际温变）+ `pet_correction_factor` 月度修正；`pet_method="oudin"` 为主，`pet_monthly_climate`（12 值）兜底（提供时优先）；config 新增 `climate.latitude`（默认 23.1）/`pet_method`/`pet_monthly_climate`/`pet_correction_factor`（长度 12 校验；`pet_method="hargreaves"` 显式报错=v0.6.0 预留）；`src/vgm.py` 新增 `feddes_alpha(ψ)` 四阈值分段（h1=−25/h2=−100/h3=−800/h4=−15000 cm）；`hydrology.py` 新增 `apply_feddes_et` 逐层独立抽取（AET_i = PET×f_root,i×α(ψ_i)，根权重 60/30/10/0，亏缺丢弃+et_deficit_mm，α=0 钳制 θ 不取负）。

**Blocked by:** 50（依赖 θ 状态 + VGM ψ(θ)）

**Status:** ready-for-agent

- [ ] calc_pet_oudin 逐月数组正确（纬度/温变/修正系数生效；广州 φ=23.1 参照）
- [ ] config：latitude∈(−60,60)、pet_method 枚举、pet_correction_factor 长度 12；`pet_method="hargreaves"` 显式报错（S4 专家★4）
- [ ] pet_monthly_climate 提供时优先于公式（解析断言）
- [ ] feddes_alpha 四阈值分段：ψ≥h1→0 / h1→h2 线性升 / h2→h3=1 / h3→h4 线性降 / ψ≤h4→0（S1）
- [ ] apply_feddes_et：逐层独立、亏缺丢弃、α=0 钳制（θ 不取负）、AET_i 与 et_deficit 数值手算验证
- [ ] 测试（S3 + S2）：全绿
