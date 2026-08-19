# 49 — v0.5.3 水文物理化阶段② spec（VGM 水分特征 + Feddes ET + LayerCascade 重构 + OM 矿化产 CO₂）

**What to build:** 将 v0.5.2 水文盒子的"水桶模型"（缺陷 2）与"缺失 ET"（缺陷 3）彻底物理化：**θ 状态迁移**（`stored_water`→`theta`，纯函数派生，决策 Q1/Q7）+ **VGM 水分特征**（三级参数化 + 田间持水量初始化，Q8/D8）+ **达西层间通量**（纯向下 K(θ) + 界面木桶短板，Q2/Q11）+ **Feddes ET**（Oudin PET 逐月正算 + ψ 版 α + 亏缺丢弃，Q3/Q9）+ **OM 矿化产 CO₂**（GAS_PHASE pCO₂ 加性调制 + 上限钳制，Q4/Q10）+ 验收实验集 E1~E3（Q13）。`n_layers=1` 完全回退现状（Q5）。

**Blocked by:** None — can start immediately（依赖 /grilling 决策总表 Q1~Q13，2026-08-19 定案；专家接缝审查 2026-08-19）。

**Status:** ready-for-agent

**来源：** /grilling 3 轮决策拷问（2026-08-19，13 项定案）+ 专家接缝审查（2026-08-19，7 处补漏）

---

## Problem Statement

v0.5.2（Green-Ampt 阶段①）已修复"入渗非物理补丁"缺陷，但 `docs/analysis/OPTIMIZATION_PLAN.md` §7.1 的缺陷 2/3 仍存：

- **缺陷 2（水桶模型替代达西定律）**：`LayerCascade` 的 `space = 0.5×sat` 持水逻辑 + `drain = min(drainable, ksat_cap)` 无基质势/水势梯度；初始含水量卡死 50% 饱和（`main.py` `theta_i = 0.5×θ_s` 与化学初始溶液体积 `0.5×φ×depth` 两处魔法数）；水分只能向下漏，无 K(θ) 非饱和导水率。
- **缺陷 3（缺失 ET 与水分平衡闭合）**：`LayerCascade.run()` 无任何 Sink 项；华南 40%~60% 降水未返回大气 → 土壤长期偏湿 → 高估矿物风化/离子交换速率、碳酸缓冲过强、pH 偏高（v0.5.2 末月表层 pH ~6.9 的直接推手之一）。

同时，表层酸性强化仍缺"温度驱动 OM 分解产 CO₂"这一持续源（决策 D7），初始 θ 缺乏物理校准（`VGM参数化方案.txt`：50% 饱和对红壤过湿，接近永久萎蔫而非田间持水）。

本 spec 落实 v0.5.3 阶段②全部工程细节（grilling Q1~Q13 定案），科学诚实边界：**pH 回落 4.5~5.5 只验收方向**（L1/L2 干湿交替 + 表层酸化增强），不承诺具体值。

---

## Solution

### 1. 状态迁移（Q1/Q7/Q8）

- `SoilState.stored_water` 字段**删除**，新增 `theta`（体积含水量 m³/m³）为规范跨月状态；`stored_water`（L/ha）由纯函数派生，**换算收于 `src/vgm.py`**（专家★1）：
  - `theta_to_water_L(theta, depth_cm) = theta × depth_cm × 1e5`
  - `water_L_to_theta(water_L, depth_cm) = water_L / (depth_cm × 1e5)`
  - 往返恒等（θ→L→θ），不依赖孔隙度（φ 抵消）。
- 初始 θ：`build_initial_state` 设 `state.theta = vgm_theta_from_psi(initial_psi_cm, layer_vgm_params)`；`config.simulation.initial_psi_cm` 默认 **−100**（田间持水量）。
- **化学初始溶液体积联动**：`InitialConditionBuilder._calc_solution_volume` 从 `0.5×φ×depth` 改为 `θ_init×depth×1e5`（L1 ≈ 8.9e5 L/ha，D8 废弃 50% 饱和）；预平衡仍锚定观测 pH，需复验收敛（E1）。
- 月度化学溶液体积**保持增量式**（REACTION H2O = `inflow_water_L`），不逐月重设（留 v0.6.0）。

### 2. VGM 水分特征（D8）

- 三级参数优先级 `get_vgm_params(layer_config)`：①`layer_overrides` 显式 `vgm_theta_r`/`vgm_alpha`/`vgm_n`；②`clay_pct` 连续回归（θ_r=0.01+0.002×clay；α=0.04−0.0006×clay；n=1.5−0.008×clay）；③红壤兜底（0.08/0.015/1.25）。`l=0.5` 固定；`θ_s≡porosity`。
- 纯函数：`vgm_theta_from_psi(psi, θ_s, θ_r, α, n)`（m=1−1/n）；`calc_psi(θ)`（VGM 反解）；`calc_Kr(θ)`/`calc_K(θ)`（Mualem：K_r = S_e^0.5 × [1−(1−S_e^(1/m))^m]²，S_e=(θ−θ_r)/(θ_s−θ_r)）。

### 3. Feddes ET / Oudin PET（D5/Q3/Q9）

- `climate_forcing.py` 新增 `calc_pet_oudin(T_mean, latitude, month)`：逐月 `n_years×12` 数组（月中日 J，含年际温变）；`pet_correction_factor`（12 值）月度修正；`pet_method="oudin"` 为主，`pet_monthly_climate`（12 值）兜底（提供时优先）。
- `LayerCascade.run()` **最前端**执行 ET（顺序：ET → 入渗 → 级联，`v0.5.3水分平衡闭合.txt` §4.3）；`apply_feddes_et` 逐层计算 AET_i = PET × f_root,i × α(ψ_i)，根系权重 60/30/10/0；**ψ 版 Feddes** 四阈值 h1=−25 / h2=−100 / h3=−800 / h4=−15000 cm（constants.py）；**逐层独立、无跨层补偿**；不足即丢弃并计入 `et_deficit_mm` 诊断列（α=0 天然钳制，θ 不取负）。
- config 新增：`climate.latitude`（默认 23.1）/`pet_method`/`pet_monthly_climate`/`pet_correction_factor`（默认 [1.0]×12，注释附华南修正示例）。

### 4. LayerCascade 重构（D3/Q2/Q11）

- `θ_FC` = `vgm_theta_from_psi(−100)`（与初始 θ 同源，系统自田间持水量启动）。
- 可排水量_i = max(0, θ_i − θ_FC,i) × depth_i × 1e5 (L/ha)。
- 界面通量_i→i+1 = min(可排水量_i, min(K_r(θ_i)·ksat_i, ksat_{i+1}) × 1e5 × n_days)——源层非饱和 K(θ) × 接收层饱和 ksat 木桶短板；θ→θ_s 时退化为 min(ksat_i, ksat_{i+1})×1e5×n_days（与 D3 精确一致）。
- 底部边界：L4 无接收层，通量 = min(可排水量_4, K_r(θ_4)·ksat_4×1e5×n_days) = 深层排水。
- 超饱和溢出（θ>θ_s/积水）继续计入 runoff（既有语义保留）。
- **纯向下 + 接口预留**：`calc_interface_flux(θ_up, θ_dn, ψ_up, ψ_dn, depth_up, depth_dn, mode="downward")` 独立纯函数；v0.5.3 上行项恒 0；`mode="bidirectional"` 解锁（v0.6.0+ 毛细上升，ROADMAP 条目）。
- Green-Ampt `θ_i` = L1 当前 θ（删除 `main.py` 的 `theta_i = 0.5×θ_s` 魔法数）。

### 5. OM 矿化产 CO₂（D7/Q4/Q10）

- `climate_forcing.py` 新增 `apply_om_pco2(pco2_base, om_gkg, k_om, pco2_max)`：**加性** `pCO₂_eff,i = pCO₂_base,i(T) + k_om × OM_i`，**钳制** `≤ pCO₂_max`。
- **温度独立性**：ΔpCO₂ 不随 T 变化（温度响应只归 base 项 Brook β=0.05，不 double-count，专家★3）。
- 常量（constants.py）：`k_om = 0.0005`（L1 30 g/kg → +0.015 atm）、`pCO₂_max = 0.05 atm`、4 层 OM 剖面 `[30, 15, 8, 5]` g/kg（内置默认，强化**表层**酸性，`layer_overrides` 可逐层覆盖）。
- 输出诊断列：`pCO2_eff`（每层有效 pCO₂）。

### 6. 输出扩展

- 新增列：`AET_mm`（月总实际蒸散）、`et_deficit_mm`、`soil_moisture_L1~L4`（θ）、`pCO2_eff`。
- `stored_water_Li` 列语义不变（L/ha，诊断处用 depth 换算）——**向后兼容**（专家★5）。

### 7. 配置面

- `simulation.initial_psi_cm`（默认 −100，值域 <0）。
- `layer_overrides` 新增 `vgm_theta_r`/`vgm_alpha`/`vgm_n`。
- `infiltration_initial`/`infiltration_steady`（f0/fc）**删除**：config 残留显式报错（Horton 废弃清理，breaking change 明示，先例 `surface_infiltration_coeff`）。
- `pet_method="hargreaves"` 显式报错（v0.6.0 预留，不静默接受，专家★4）。

---

## User Stories

1. 作为研究者，我希望 LayerCascade 状态从 `stored_water` 迁移为 `theta`（θ 为规范状态，L/ha 由纯函数派生），以便水分物理以体积含水量为基本变量、与 Richards 语境一致。
2. 作为模型开发者，我希望 θ↔L/ha 换算函数收于 `src/vgm.py` 且往返恒等，以便单位换算单点收敛、无重复公式。
3. 作为研究者，我希望初始 θ 由 VGM 从 `initial_psi_cm=-100`（田间持水量）正算，以便废弃"50% 饱和"的过湿假设（红壤 L1≈0.81θ_s）。
4. 作为模型开发者，我希望化学初始溶液体积 = θ_init×depth×1e5 与水文初始 θ 严格联动，以便同一层不出现两个初始水量的矛盾态。
5. 作为研究者，我希望 VGM 参数三级优先级（layer_overrides 显式 > clay_pct 回归 > 红壤兜底），以便无实测数据时开箱即用、有实测时可率定。
6. 作为研究者，我希望 θ_s≡porosity 且 Mualem l=0.5 固定，以便水分特征与既有物理剖面自洽。
7. 作为研究者，我希望层间排水由 K(θ) 非饱和导水率驱动且界面通量受 min(上下层 ksat) 木桶短板约束，以便干旱期排水自然减缓、饱和时退化为 D3 定案公式。
8. 作为研究者，我希望 v0.5.3 通量**纯向下**且 `calc_interface_flux` 预留双向接口，以便不引入月度盒子无法支撑的毛细上升伪物理、并给 v0.6.0 留扩展点。
9. 作为研究者，我希望 `LayerCascade.run()` 最前端扣除 Feddes ET（根系 60/30/10/0、ψ 版 α 四阈值），以便旱季 L1/L2 干湿交替、水分平衡闭合。
10. 作为研究者，我希望 AET 逐层独立、不足即丢弃并输出 `et_deficit_mm`，以便蒸散不会抽取不存在的水、亏缺可诊断。
11. 作为研究者，我希望 PET 由 Oudin(2005) 逐月正算（月均温+纬度，n_years×12 数组）并支持月度修正系数与固定气候态兜底，以便年际温变情景可响应。
12. 作为研究者，我希望 OM 矿化以加性方式调制每层 GAS_PHASE pCO₂ 并钳制上限，以便表层酸性持续强化且高 OM 下不失控。
13. 作为研究者，我希望 OM 增量温度独立、4 层默认 OM 剖面 [30,15,8,5]，以便温度响应不 double-count、表层 pCO2_eff 梯度最大。
14. 作为研究者，我希望输出新增 AET_mm/et_deficit_mm/soil_moisture_L1~L4/pCO2_eff，以便验证水分平衡闭合与酸化强度。
15. 作为模型开发者，我希望 `stored_water` 输出列保持 L/ha 语义向后兼容，以便既有输出消费者不破坏。
16. 作为模型开发者，我希望 n_layers=1 完全回退现状（无 VGM/ET/OM），以便单层基线零回归。
17. 作为模型开发者，我希望 f0/fc 字段删除且 config 残留显式报错，以便 Horton 废弃彻底清理、breaking change 明示。
18. 作为模型开发者，我希望 `pet_method="hargreaves"` 显式报错（v0.6.0 预留），以便未来字段不被静默吞掉。
19. 作为研究者，我希望发布前完成 E1（基线+预平衡复验）/E2（PET 敏感性 600~1400mm）/E3（k_om 或 pCO₂_max 敏感性）验收实验，以便物理方向在发布前暴露。
20. 作为模型开发者，我希望四类不变量测试（质量守恒/单层回归/数值稳定性/化学基线）一字不改，以便回归护栏不破。

---

## Implementation Decisions

- **模块组织**（Q12）：新建 `src/vgm.py`（VGM 数学 + `get_vgm_params` + `feddes_alpha` + θ↔L/ha 换算，专家★1）；`hydrology.py` 保留降雨/Green-Ampt + 新增 `apply_feddes_et` + LayerCascade 重构 + `calc_interface_flux`；`climate_forcing.py` 新增 `calc_pet_oudin`/`apply_om_pco2`；`constants.py` 新增 `k_om`/`pco2_max`/`OM_PROFILE_4LAYER`/`FEDDES_H1..H4`。
- **`phreeqc_engine.py`**：`SoilState.stored_water`→`theta` 字段；`build_initial_state` 设 `state.theta = vgm_theta_from_psi(initial_psi_cm, ...)`；`run_monthly_multi_layer` hydrology 契约（`inflows`/`drains` 单位 L/ha）不变。
- **`initial_condition.py`**：`_calc_solution_volume` = `θ_init×depth×1e5`（删 `saturation=0.5`）。
- **`config_manager.py`**：新字段解析/校验（`initial_psi_cm<0`、`latitude∈(−60,60)`、`pet_correction_factor` 长度 12、`pet_method` 枚举、`vgm_theta_r∈[0,θ_s)`、`vgm_alpha>0`、`vgm_n>1`）；`infiltration_initial/steady` 删除报错；`pet_method="hargreaves"` 预留报错。
- **`main.py`**：删 `theta_i=0.5×θ_s` → `states[0].theta`；逐层 pCO₂ 经 `apply_om_pco2` 加性调制；诊断扩展（AET_mm/et_deficit_mm/soil_moisture_Li/pCO2_eff/stored_water_Li 换算）。
- **接口契约**：`LayerCascade.run()` 签名扩展接收 PET 与 ET 配置；`_apply_hydrology_month` 返回字典扩展 ET 相关键；`run_monthly_multi_layer` 层间溶质传递（L/ha 排水量）逻辑不变。
- **单位约定**：水文域内部用 θ；引擎/输出边界用 L/ha（1 cm/day = 1e5 L/ha/day；θ×depth×1e5 = L/ha）。

## Testing Decisions

- **好测试标准**：只测外部行为与物理不变量——换算往返恒等、纯向下方向约束（q≥0、无逆向回流）、水量守恒、预平衡收敛、单层回归；不测实现细节。
- **接缝 S1~S6**（专家修订版）：
  - **S1 `test_vgm.py`（新）**：VGM 正反算/三级参数/feddes_alpha 四阈值分段 + **★换算函数与往返断言**（θ→L→θ 恒等，覆盖 depth 20/20/20/40、θ=0、θ=θ_s）。
  - **S2 `test_hydrology.py`**：级联重构（θ_FC 可排水量/K(θ) 界面 min/底部边界/溢出）+ apply_feddes_et（最前端/亏缺/α=0 钳制）+ Green-Ampt θ_i=L1θ + **★纯向下方向约束**（q≥0、干上层无回流、`mode="downward"` 上行恒 0、单位边界）。
  - **S3 `test_climate_forcing.py`**：calc_pet_oudin 逐月数组（纬度/修正/温变）+ apply_om_pco2（加性/钳制）+ **★温度独立性**（ΔpCO₂ 不随 T 变）+ **★垂直梯度**（OM [30,15,8,5] → pCO2_eff L1≥L2≥L3≥L4 且表层增量最大）。
  - **S4 `test_config_manager.py`+`test_initial_condition.py`**：新字段解析校验 + f0/fc 删除报错 + 初始溶液体积=θ_init×depth×1e5 + state.theta 注入 + **★v0.6.0 预留字段**（`pet_method="hargreaves"` 报错、`pet_monthly_climate` 优先、`initial_psi_cm<0` 校验）。
  - **S5 `test_layer_overrides.py`/`test_multilayer.py`**：SoilState.theta 迁移 + hydrology 契约（L/ha）不变 + 逐层 pCO2_eff + 单层护栏 + **★θ→L/ha 边界换算**（引擎边界无单位泄漏）。
  - **S6 `test_multilayer_output.py`/main**：新诊断列 + 守恒不变量 + bypass 不变 + **★stored_water 列向后兼容**（L/ha 语义、单层等效、soil_moisture 与 stored_water 双列互证 θ=stored_water/(depth×1e5)）。
- **不变量保护**（Q6）：质量守恒/单层回归/数值稳定性-timeout/化学引擎基线 四类一字不改；仅重写编码"50% 饱和"过时物理的断言，每条在工单记录理由；禁止无替代删除。
- **目标测试数**：179 − Δ + 新增 ≈ **195~210 全绿**。
- **先例**：spec 43（S1~S5 接缝）/ `test_hydrology.py`（纯函数）/ `test_config_manager.py` / `test_layer_overrides.py`（引擎集成）。

## Out of Scope

- 毛细上升/双向达西（v0.6.0+，`mode="bidirectional"` 接口已预留，ROADMAP 条目）
- SWAP 式 AET 跨层根系补偿（后续版本）
- 月度化学溶液体积 = θ×depth 完全耦合（v0.6.0 子步长）
- 动态 OM-C 池（OM 视为静态源，不枯竭）
- Hargreaves PET（v0.6.0，需 T_max/T_min 数据）
- GAS_PHASE 固定体积 + 动态 CO₂ mol（Q4 备选 C）
- 氮形态层间运移（v0.6.0）
- 子步长/逐场 PHREEQC（v0.6.0）
- β 旱雨季动态调整（后续小版本）

## Further Notes

- **config 默认**：`climate.latitude=23.1`（广州，与广东降水化学源一致）；`pet_correction_factor=[1.0]×12`（恒等，注释附华南修正示例，不预设未验证修正）；`simulation.initial_psi_cm=-100`。
- **科学诚实**：pH 回落 4.5~5.5 为目标方向，E2/E3 只验收方向；预平衡收敛（E1）是 Q8 变更的发布门禁。
- **版本**：v0.5.3（阶段②）；发布流程 = 版本号同步 → commit → annotated tag → push。
- **关联工单**：50（VGM 模块+状态迁移）→ 51（ET/Oudin）→ 52（LayerCascade 重构）→ 53（OM 产 CO₂）→ 54（集成+验收+发布）。
- **风险评估**：初始溶液体积 +38%（L1 5.5e5→8.9e5 L/ha）改变化学基线，预平衡收敛性需 E1 复验；K(θ) 排水可能显著改变 4 层 pH 剖面断言（Q6 契约覆盖）。



