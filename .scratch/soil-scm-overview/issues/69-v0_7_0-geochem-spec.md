# 69 — v0.7.0 地球化学重构 spec（NO₃⁻ 伴随淋失 + NH₄⁺ 等效置换 + 矿物风化动力学化 + k_om 重参数化 + PET 判别 + 方向带验收）

**What to build:** 将 v0.6.1 "数值稳定性根治"的稳定基线上叠加**地球化学真实性**：① **NO₃⁻ 示踪池 + 水库串联淋失**（工单 70：`n_no3_pool` 逐层入 SoilState、逐场 lost_no3 水库串联 + bypass 携带 + 全局 `min(公式, pool)` 不变量）② **伴随阳离子淋失（CompAn 虚拟伴生）**（工单 70：自定义惰性阴离子 `CompAn` 经 REACTION 等当量注入 + 按盐基饱和度分级——inert/hybrid/acid 三态，交换相不动靠 Gapon 自洽）③ **NH₄⁺ 等效置换**（工单 71：施肥月水解后按交换占比注入置换盐基 + `NH4X_virtual` 记账列，不触碰 L4 Q3=A "氮不进溶液"决策）④ **原生矿物风化动力学化**（工单 72：illite/gibbsite/kaolinite 平衡降级评估 + 集总风化碱度注入，**不用 KINETICS**）⑤ **k_om 重参数化**（工单 73）⑥ **E2 PET 机制判别**（工单 74）⑦ **30 年 8 情景方向带验收 + 发布**（工单 75）。严格 **expand-contract**：现有 **289 测试不破**，水文/引擎/输出接口向后兼容（新增 config 均带默认值）。

**Blocked by:** None — can start immediately（依赖 /grilling 决策 Q11~Q22，2026-08-21 定案）。

**Status:** ready-for-agent

**来源：** /grilling 决策拷问（2026-08-21，Q11~Q22 定案）→ 本 spec 决策表（见 Implementation Decisions）。工单 70~75 对应 REPLAN 工单 69~73（编号顺延一位容纳 spec 69 + 新增 NH₄⁺ 置换工单 71）。

**对应关系：** REPLAN `docs/analysis/V0_7_0_REPLAN.md` 工单 69→本 spec 工单 70；工单 70→工单 72；工单 71→工单 73；工单 72→工单 74；工单 73→工单 75；新增 NH₄⁺ 置换→工单 71。

---

## Problem Statement

v0.6.1 完成"30 年 8 情景全程无降级"（数值稳定性，`output/sensitivity_pH_30yr_v061.csv`），但 30 年敏感性实验暴露三个**地球化学**疑点（非数值 bug，科学解读见 `v0.6.1敏感性实验科学解读.md`）：

1. **自然情景 pH 上升**（5.32→5.68，实际华南红壤应酸化下降）：机制 B 淋失选择性颠倒（盐基留在交换相、Al/H 随排水走）+ 机制 A 矿物瞬时平衡"闪蒸"无限供碱 + 机制 C HX 锁酸。
2. **气候情景与自然无显著区别**：风化无温度依存（瞬时平衡非速率控制）+ NO₃⁻ 伴随淋失缺失 → 敏感性传导断裂。
3. **施肥情景碱化**（8.4→11.4，实际应 <4.0）：偏差 1 NH₄⁺ 不占交换位点（不置换盐基）+ 偏差 2 GAS_PHASE 固定缓冲吞酸 + 偏差 3 **NO₃⁻ 伴随淋失缺失**（盐基只进不出）+ 偏差 4 降水/矿物持续补盐基。

**共同根源（v0.7.0 立项依据）**：D3 NO₃⁻ 伴随淋失（工单 70）+ D2 矿物风化速率化（工单 72）是三个疑点的共同解。NH₄⁺ 置换（工单 71）补偏差 1 的酸化主通道——量级核算：每次施肥 NO₃⁻ 淋失当量 ≈343 eq ≈ 盐基投入 352 eq（临界平衡、不保证枯竭），而 NH₄⁺ 置换 ≈857 eq/次（尿素全水解），是 salt 枯竭到酸化的**必要补充**。

**科学诚实边界**：v0.7.0 承诺 = 方向带（Q14=A：natural 30 年 4.5~5.0 缓降或持平 / fertilizer <4.0 / lime 3~5 年回落 / 排序 Natural<Fertilizer<Lime / 全情景 30 年无降级）+ N 收支闭合；**不承诺 pH 具体值**。

---

## Solution

从用户（土壤模型开发/研究者）视角：v0.7.0 交付一个"**地球化学方向正确**"的基线——NO₃⁻ 淋失携带等当量盐基（真实农业酸化机制）、NH₄⁺ 置换盐基（氮肥酸化通道）、矿物风化从"无限缓冲"改为速率控制、气候敏感性传导恢复。

1. **NO₃⁻ 示踪池（工单 70）**：`n_no3_pool` 逐层入 SoilState；`advance_nitrification` 硝化量同步入池；逐场水库串联 `lost_no3_i = min(pool_i×ΣQ/V_pool_i, pool_i)`；垂直排水按比例下移池（+体积稀释）；bypass 携带 L1 池 NO₃⁻ 直通 L2。
2. **伴随淋失（工单 70）**：每层随 NO₃⁻ 移出的盐基当量 `E_loss = lost_no3_i × 1`；REACTION 注入自定义惰性阴离子 `CompAn`（分级：BS≥30 全量 / 10~30 线性衰减 / <10 酸化注入 H⁺）；交换相不动、靠平衡自洽解吸（Gapon 哲学保留）。
3. **NH₄⁺ 等效置换（工单 71）**：施肥月尿素水解后，按当前交换相电荷占比注入等当量 Ca/Mg/K/Na 到溶液；`NH4X_virtual` 记账列（不进 EXCHANGE 总量）；接受自然回吸 + 观测门。
4. **矿物风化动力学化（工单 72）**：集总风化碱度注入（weathering_rate molc/ha/yr 可配、Ca:Mg:K=5:3:2 + HCO₃⁻、Arrhenius 温度依赖）；评估 illite/gibbsite/kaolinite 从瞬时平衡降级；不用 KINETICS。
5. **k_om 重参数化（工单 73）**：0.0005 起点，E3 标定区间 0.0003/0.0005/0.0008。
6. **E2 PET 判别（工单 74）**：PET 900→1200 中间点扫描（1000/1100）+ NaX/CaX2 时序 → 判别假设 A/B/C。
7. **验收（工单 75）**：`tools/verify_v0_7_0_acceptance.py` 方向带断言 + N 收支闭合 + 30 年无降级；发布 v0.7.0。

---

## User Stories

1. As a **土壤模型研究者**, I want NO₃⁻ 以逐层示踪池（`n_no3_pool`）显式建模并随逐场排水淋失（水库串联 `lost_no3 = min(pool×ΣQ/V_pool, pool)`），so that 硝态氮的淋失量级与真实农业可比、First-Flush 脉冲如实输出。
2. As a **土壤模型研究者**, I want 每层随 NO₃⁻ 移出同步携带等当量盐基（伴随淋失 E_loss），so that 施肥情景盐基持续流失、最终枯竭酸化（而非 v0.6.1 碱化 8.4→11.4）。
3. As a **土壤模型研究者**, I want 伴随淋失通过 REACTION 注入自定义惰性阴离子 `CompAn`（而非手工改 EXCHANGE 块），so that 交换相仍由 Gapon 方程自动调控、盐基解吸由化学势驱动（真实物理）。
4. As a **土壤模型研究者**, I want 伴随淋失按盐基饱和度分级（BS≥30 全量注入 / 10~30 线性衰减 / <10 切换酸化注入 H⁺ 并警告），so that 盐基枯竭后不会用 InertAnion 继续拽 Al/H 造成 pH 异常。
5. As a **土壤模型研究者**, I want `bypass` 优先流携带 L1 池 NO₃⁻ 直通 L2（默认模式），so that 台风/龙舟水期大孔隙流的 NO₃⁻ 脉冲淋失被模拟。
6. As a **土壤模型研究者**, I want 全局不变量 `lost_no3 ≤ n_no3_pool`（对每层每出口通道 min 钳制），so that 干旱期 V_pool 极小时池不出现负值（与 v0.6.1 "防抽干"同哲学）。
7. As a **土壤模型研究者**, I want 垂直排水的 NO₃⁻ 按比例下移下层池并自然稀释（mass_down = pool×drains/V_pool、V_new 随水量更新），so that NO₃⁻ 一维运移守恒且浓度梯度真实。
8. As a **土壤模型研究者**, I want NH₄⁺ 吸附阶段等效置换等当量盐基（按交换相电荷占比注入 Ca/Mg/K/Na），so that 氮肥"NH₄⁺ 置换盐基→盐基淋失"的农业酸化机制被近似表达。
9. As a **土壤模型研究者**, I want `NH4X_virtual` 记账列统计 NH₄⁺ 假设占用的交换位点（不进 EXCHANGE 总量），so that CEC 守恒审计不被破坏、预平衡锚定不受扰、且位点占用可观测。
10. As a **土壤模型研究者**, I want 原生矿物风化从瞬时平衡改为集总速率注入（weathering_rate 可配、Ca:Mg:K=5:3:2+HCO₃⁻、Arrhenius 温度依赖），so that "矿物闪蒸"无限供碱被消除、增温情景产生可观测的风化响应。
11. As a **模型开发者**, I want D2 不使用 KINETICS（集总 REACTION 注入），so that 规避 v0.3.0 证伪的"冻结矿物切断 L2 回补"陷阱。
12. As a **模型开发者**, I want `simulation.companion.*` 全部 config 可配（enable/bs_high/bs_low/bypass_no3_carry/nh4_exchange），so that 关闭开关即完全回退 v0.6.1 行为（回归护栏）。
13. As a **模型开发者**, I want event_details 与月度诊断列新增 N 收支列（n_no3_pool/leach_no3/companion_eq/companion_mode/inert_eq/acid_eq/nh4_exchanged_eq/NH4X_virtual），so that N 收支可被 `water_salt_balance.py` 审计。
14. As a **模型开发者**, I want `tools/water_salt_balance.py` 扩展 N 收支行（施肥输入−硝化转化−淋失−置换），so that N 守恒闭合逐月可验证（<阈值）。
15. As a **验收工程师**, I want `tools/verify_v0_7_0_acceptance.py` 断言方向带（natural 4.5~5.0 缓降/持平、fertilizer<4.0、lime 3~5 年回落、排序 Natural<Fertilizer<Lime、30 年无降级），so that v0.7.0 发布门槛科学诚实可执行。
16. As a **土壤模型研究者**, I want k_om 在 0.0003/0.0005/0.0008 区间标定（E3 表层酸化方向复验），so that OM 产 CO₂ 的 pCO₂ 调制幅度有实测依据。
17. As a **土壤模型研究者**, I want E2 PET 机制判别（PET 1000/1100 中间点 + NaX/CaX2 时序），so that PET 非单调机制的假设 A/B/C 在稳定数值框架下被判别。
18. As a **模型开发者**, I want 预平衡/E1 收敛（pH 5.0）与现有 289 测试保持全绿（expand-contract），so that v0.7.0 改动不破坏 v0.6.1 数值稳定性承诺。
19. As a **土壤模型研究者**, I want 动态阈值自适应（土壤类型/初始 BS）留 v0.7.x，so that v0.7.0 先用固定可配阈值控制范围、避免"一刀切"争议被误引入主线。
20. As a **土壤模型研究者**, I want bypass 深度分布（60/30/10 注入 L2/L3/L4）与 NH₄⁺ 吸附-解吸动态平衡留 v0.7.x，so that v0.7.0 聚焦核心机制、进阶物理逐步叠加。

---

## Implementation Decisions

### 工单 70 — NO₃⁻ 示踪池 + 水库串联淋失 + bypass 携带 + CompAn 分级注入（D3 全集，🔴 P0，最先）

- **状态字段**：`SoilState` 新增 `n_no3_pool: float = 0.0`（逐层，mol N）。`n_no3` 保留为累计器（向后兼容），`n_no3_pool` 为淋失示踪池，两者由 `advance_nitrification` 同步推进（`state.n_no3 += nitrified`；`state.n_no3_pool += nitrified`）。
- **水库串联淋失（Q12=A）**：逐场、逐层执行
  - `V_pool_i = max(state.volume, 1.0)`（复用 v0.6.1 Q3 的 vol_L 语义）
  - 垂直下移：`mass_down = min(pool_i × drains_i / V_pool_i, pool_i)` → `pool_i -= mass_down`；`pool_{i+1} += mass_down`（体积稀释自然出现：V_new 由水文层水量更新，池为质量存量）
  - 出系统淋失：`lost_out_i = min(pool_i × (lateral_i + baseflow_i) / V_pool_i, pool_i)` → `pool_i -= lost_out_i`
  - **全局不变量（Q19 审查通过）**：对每层每出口通道 `lost = min(公式量, pool)`，单元测试固化 `pool ≥ 0`。
- **bypass 携带（Q16=D 默认模式）**：`ev['bypass_water_L'] > 0` 时 `m_bypass = min(pool_L1 × bypass_water_L / V_pool_L1, pool_L1)` → `pool_L1 -= m_bypass`；`pool_L2 += m_bypass`；该 m_bypass 计入该场 L1 的淋失（触发 E_loss）。`bypass_water_L` 仍携带原始降水化学（现状不动）。深度分布（60/30/10）留 v0.7.x。
- **伴随淋失（Q11=E-InertAnion）**：每层 `E_loss = 该层该场淋失 NO₃⁻ 当量`（含 drains 下移 + 出系统 + bypass，mol × 1 eq/mol）→ 在 **`_build_phreeqc_input` 的 REACTION 块**注入：
  - **CompAn 物种定义**（输入字符串头段，不碰 phreeqc.dat）：`SOLUTION_MASTER_SPECIES` + `SOLUTION_SPECIES` 定义 `CompAn-`（log_k=0，不参与氧化还原，保守示踪）；SELECTED_OUTPUT 含 CompAn 供审计。
  - **分级注入（Q18=A）**：BS 取各层动态盐基饱和度（复用 main.py `base_saturation` 诊断，`(Ca+Mg+K+Na)/CEC_occupied×100`）
    - BS ≥ `bs_high(30)`：注入 CompAn = E_loss eq
    - `bs_low(10) ≤ BS < bs_high`：注入 CompAn = E_loss × `(BS−bs_low)/(bs_high−bs_low)`（线性衰减）
    - BS < `bs_low(10)`：**酸化注入** REACTION `H+ = E_loss eq` + 记录 `companion_mode=acid` + 盐基枯竭警告（logger）；H⁺ 与硝化产酸同场叠加，pH 由既有 `PH_LOWER=2.0` 兜底，不额外钳制（先试跑再定）
  - 交换相**绝不手工改**——盐基解吸由 PHREEQC 平衡自洽完成（v0.6.1 Q3 哲学延续）。负 REACTION 直移盐基留作备选（数值边缘：负注入超溶液现有量会报错）。
- **config（`simulation.companion.*`）**：`enable: true`（false=完全回退 v0.6.1）、`bs_high: 30`、`bs_low: 10`、`bypass_no3_carry: true`、`inert_anion: "CompAn"`。config_manager 校验（阈值 0<bs_low<bs_high≤100、开关布尔）。
- **记账列**（event_details + 月度诊断）：`n_no3_pool_L{i}`（mol）、`leach_no3_L{i}_mol`（淋失 NO₃⁻ 合计）、`companion_eq_L{i}`（随 NO₃⁻ 移出盐基当量）、`companion_mode_L{i}`（inert/hybrid/acid）、`inert_eq_L{i}`、`acid_eq_L{i}`。
- **接口**：`advance_nitrification` 返回契约扩展可选键 `{'H+':..., 'nitrified':..., 'hydrolyzed':...}`（调用方按旧键不变，新键仅供 D3/NH₄⁺ 使用）；`run_event_step`/`run_monthly_multi_layer` 在事件逐场循环内（`phreeqc_engine.py` L780~846 区域）串联池淋失逻辑与出口记账。

### 工单 71 — NH₄⁺ 等效置换 + NH4X_virtual（Q17=A 一次性，🟡 P1，依赖工单 70）

- **触发**：施肥月尿素水解后（`advance_nitrification` 的 `hydrolyzed = n_urea×k1`），`nh4_exchanged_eq = hydrolyzed × 1`（≈857 eq/次）。
- **注入**：REACTION 按**当前交换相 Ca:Mg:K:Na 电荷占比**注入对应阳离子到溶液（`companion.exchange_ratio` 可选覆盖）；与硝化 H⁺ 同场进入平衡（净效应 H⁺ 主导酸化，物理正确）。
- **再吸附**：接受 PHREEQC 平衡自然回吸（不做定向移除）；**观测门**：`nh4_exchanged_eq` vs 交换相盐基净减对比，若净效率 <50% 触发重新评估（风险 1 兜底）。
- **位点占用**：`NH4X_virtual_L{i}` 记账列（统计假设占用），**不进 EXCHANGE 总量**（CEC 守恒审计不破、预平衡锚定不受扰）。
- **config**：`simulation.companion.nh4_exchange: true`。
- **记账列**：`nh4_exchanged_eq_L1`、`NH4X_virtual_L{i}`。

### 工单 72 — 原生矿物风化动力学化（D2，🟡 P1，依赖工单 70+71）

- **集总风化注入（不用 KINETICS，v0.3.0 证伪）**：REACTION 逐月注入风化碱度 `Ca:Mg:K = 5:3:2 + HCO₃⁻ 等当量`；`weathering_rate`（molc/ha/yr，默认 **500**，config 可配，工单拆解时按 E3/方向带扫描 100/500/1000）。
- **Arrhenius 温度依赖**：`rate(T) = weathering_rate × exp(−Ea/R × (1/T − 1/T_ref))`，`Ea` 默认 40 kJ/mol（硅酸盐风化典型量级），`T_ref=298.15 K`；增温情景由此产生可观测风化响应（疑点 2 传导恢复）。
- **矿物平衡相降级评估**：red_soil 库 `illite/gibbsite/kaolinite` 从 `EQUILIBRIUM_PHASES` 移除或降量（`MINERAL_SCALE` 维持 0.001），消除"矿物闪蒸"无限供碱（疑点 1 机制 A）；先评估后落地（保 Al 循环通道不断——v0.3.0 教训）。
- **config**：`simulation.weathering.{enable, rate_molc_ha_yr, ca_frac, mg_frac, k_frac, activation_energy_kJ}`。

### 工单 73 — k_om 重参数化（🟡 P1，独立）

- `K_OM_PCO2` 0.0005 起点，E3 标定区间扫描 **0.0003 / 0.0005 / 0.0008**（表层 pCO₂_eff 0.024→0.039 方向复验，L1 pH 酸化方向）；选定值入常量模块 + 扫描表记录（同 v0.4.0 L9 扫描纪律）。

### 工单 74 — E2 PET 机制判别（🟡 P1，依赖工单 70~73 基线稳定）

- PET 900→1200 中间点扫描（**1000 / 1100**）+ NaX/CaX2 时序分析 + 单层对比实验 → 判别假设 A/B/C（v0.6.1 数值框架已稳定，中间点不再白做）。

### 工单 75 — 30 年 8 情景全链路验收 + 发布（🔴 P0，依赖全部）

- **验收脚本**：新建 `tools/verify_v0_7_0_acceptance.py`——断言：① natural 30 年 pH 4.5~5.0 缓降或持平 ② fertilizer 30 年 <4.0 ③ lime 3~5 年回落至 5~6 ④ 排序 Natural<Fertilizer<Lime ⑤ 全情景 30 年 `phreeqc_ok` 无降级 ⑥ **N 收支闭合**（`water_salt_balance.py` N 行逐月 <阈值，阈值初定 5%，试跑后定）。
- **中间里程碑**：工单 70 完成后 fertilizer 3~5 年 pH 应开始转向下降；工单 71 完成后确认 <4.0 可达（回吞超预期则回 Q20 上调置换策略）。
- **发布流程**：版本号同步 → commit → annotated tag v0.7.0 → push main + push tag。

---

## Testing Decisions

- **好测试标准**：只测外部行为与物理不变量——NO₃⁻ 池质量守恒（施肥输入 − 淋失 − 下移 = 存量变化）、`pool≥0` 全局不变量、水库串联数学恒等（`lost = min(pool×Q/V, pool)`）、CompAn 物种注入字符串断言、分级注入三态（inert/hybrid/acid）边界、NH₄⁺ 置换 REACTION 注入量、CEC 守恒不破、config 校验、方向带验收；不测实现细节。
- **接缝 S1~S7**（2026-08-21 to-spec 定案）：
  - **S1 `tests/test_nitrification.py`（既有扩展）**：`advance_nitrification` 推进 `n_no3_pool`（与 n_no3 同步）+ 返回契约新键（nitrified/hydrolyzed）+ `lost_no3` 纯函数水库串联 + **`pool ≥ 0` 全局不变量**（含 V_pool 极小、Q/V 远超 1 的干旱期极端用例）。
  - **S2 `tests/test_event_chemistry.py`（既有，最高事件接缝）**：`run_event_step` 级联——CompAn/酸化 H⁺ REACTION 注入、E_loss 分级三态边界（BS=30/10 邻域）、bypass 携带 NO₃⁻（池 L1→L2 + E_loss 同步）、NH₄⁺ 置换 REACTION、`companion_eq`/`companion_mode` 等记账列、mass 守恒（施肥+N0 输入=淋失+下移+存量）。
  - **S3 `tests/test_phreeqc_engine.py`（既有，引擎基线）**：`_build_phreeqc_input` 含 `SOLUTION_MASTER_SPECIES/SOLUTION_SPECIES CompAn` 定义 + REACTION 注入行 + SELECTED_OUTPUT 含 CompAn；PHREEQC 实测平衡（CompAn 保守示踪、交换相响应）。
  - **S4 `tests/test_initial_condition.py`（既有扩展）**：SoilState 新字段 `n_no3_pool` 初始 0 + CEC 总量守恒不变量不破（NH4X_virtual 不进交换）。
  - **S5 `tests/test_config_manager.py`（既有扩展）**：`simulation.companion.*` 解析/校验（bs 阈值区间、布尔开关）+ `simulation.weathering.*`；`enable: false` 完整回退护栏。
  - **S6 `tests/test_multilayer_output.py`/`test_output_writer.py`（既有扩展）**：新诊断列 `n_no3_pool_L{i}`/`leach_no3_L{i}_mol`/`companion_mode_L{i}` 等 + 事件 CSV 扩列。
  - **S7 新增 `tools/verify_v0_7_0_acceptance.py`**：30 年 8 情景方向带断言 + N 收支闭合 + 无降级（后台进程跑，避免工具 30s 超时）。
- **不变量保护**：质量守恒/单层回归/数值稳定性-timeout/化学引擎基线四类一字不改；仅新增断言；禁止无替代删除。
- **目标测试数**：289 + 新增 ≈ **320~350 全绿**。
- **先例**：spec 62（S1~S6 接缝）/ spec 55（事件接缝）/ `test_event_chemistry.py`（v0.6.1 出口记账数学恒等）/ `test_nitrification.py`（氮库存）。

## Out of Scope

- **动态阈值自适应**（Q18-D：土壤类型/初始 BS 动态 bs_high/bs_low）→ v0.7.x（v0.7.0 固定可配阈值已满足人为调整）
- **bypass 深度分布**（Q16-C 进阶：60/30/10 注入 L2/L3/L4）→ v0.7.x
- **NH₄⁺ 吸附-解吸动态平衡**（Q17-C：Langmuir/Gapon 动态、解吸 NH₄⁺ 进硝化）→ v0.7.x（v0.7.0 一次性置换）
- **氮进溶液**（Q11-D 最终目标：自定义 N 物种绕过 N→N₂）→ 最终优化目标，v0.7.x 评估
- **Gapon 加权置换配比**（Q20 风险 2 改进方向）→ v0.7.x
- **HX log_k 再标定**（科学解读机制 C：3.0→2.5~2.8）→ v0.7.x（与 E1 预平衡锚定联动，改值需重锚定，单独立项）
- **GAS_PHASE 固定缓冲动态化**（科学解读偏差 2）→ v0.7.x 评估
- **事件聚类**（Q9 明确否决）→ 不做（v0.7.x 与逐日排水分辨率合并设计）
- **毛细上升/双向达西 / SWAP 式 AET 跨层根系补偿 / 动态 OM-C 池 / L1 Al 表面络合 / 水文参数标定 / L7 pip / L8 敏感性框架 / WRF 耦合** → 长期（v0.7.x+，REPLAN §6.2）

## Further Notes

- **依赖链**：工单 70（无前置，最先）→ 71（依赖 70 的池/记账）→ 72（依赖 70+71 盐基基线）→ 73（独立）→ 74（依赖 70~73 基线稳定）→ 75（依赖全部）。建议施工顺序 70→71→72→73→74→75。
- **性能**：CompAn 为线性保守物种、REACTION 行数微增——PHREEQC 调用次数与迭代开销量级不变；沿用 `--scenario X` 分批断点续跑 + `--timeout`（默认 1800s）护栏；30 年 8 情景预期与 v0.6.1 同级（~75min）。
- **科学诚实**：方向带是 v0.7.0 承诺（Q14=A）；pH 具体值不在承诺范围。中间里程碑（工单 70 后 fertilizer 3~5 年转向下降）是趋势观察非硬门槛。
- **风险 1（Gapon 回吞，Q20）**：NH₄⁺ 置换盐基可能被平衡回吸——观测门净效率 <50% 触发重新评估（注入配比/一次性量/是否引入定向移除）。
- **风险 2（双重计数）**：CompAn 注入与 v0.6.1 Q3 `frac_out` 溶液扣除**正交互补**——E 负责"随 NO₃⁻ 走的盐基"（进平衡前注）、Q3 负责"随水走的溶液盐基"（平衡后扣）；`water_salt_balance` N 行持续审计防错。
- **InertAnion 物种命名**：`CompAn`（避开 phreeqc.dat 既有物种名；log_k=0、不参与氧化还原、保守示踪）。
- **版本**：v0.7.0；发布流程 = 版本号同步 → commit → annotated tag → push main + push tag。对外编号：spec 69，工单 70~75。
- **工单 72 次轮细节**：weathering_rate 默认 500 molc/ha/yr、Ea=40 kJ/mol、Ca:Mg:K=5:3:2 为初值；工单拆解时按方向带扫描 100/500/1000 定案（同 v0.4.0 L9 扫描纪律）。
