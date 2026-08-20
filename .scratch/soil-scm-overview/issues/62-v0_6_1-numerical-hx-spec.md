# 62 — v0.6.1 数值稳定性根治 + HX 交换酸注入 spec（基流/侧向出口 + fallback 局部降级 + 浓度冲洗 + HX/GAP_H）

**What to build:** 将 v0.6.0 的"三层数值防护 + 永久降级"升级为**数值稳定性根治版**：① **VIC 深层基流 + Darcy 侧向排水**（L4 底部基流替换 `min(drainable, ksat_cap)`、逐层侧向出口，溶质随水移出系统，质量守恒记账）② **fallback 事件级局部降级**（连续 N=3 次失败才永久降级，失败场保留状态跳过）③ **浓度硬上限冲洗**（C_warn=0.5 mol/L 触发基流/侧向激增 Q_flush）④ **HX 交换酸注入**（`EXCHANGE_SPECIES H+ + X- = HX` log_k=1.0 + `exch_h→HX` + GAP_H_FRACTION 缺口重分配）⑤ **`tools/water_salt_balance.py` 水量/盐分闭合审计** ⑥ **30 年 8 情景重跑 + E1 复验**。严格 **expand-contract**：现有 **259 测试不破**（fallback 契约测试按 Q5 明确修订除外），水文/引擎/输出接口向后兼容。

**Blocked by:** None — can start immediately（依赖 /grilling 决策表 Q1~Q10，2026-08-20 定案）。

**Status:** ready-for-agent

**来源：** /grilling 决策拷问（2026-08-20，10 项定案 Q1~Q10）→ 本 spec 决策表（见 Implementation Decisions）。

---

## Problem Statement

v0.6.0 发布后 30 年敏感性实验（`1d9b7bb`，`SENSITIVITY_PH_30YR_V060.md`）暴露两级硬障碍：

1. **数值崩溃（P-NUM-1 根治）**：8 情景全部在 4~8 年触发 PHREEQC 永久降级（深层 L4 盐分累积 Na/Cl ≈9 mol/L → 不收敛 → simplified 钳制伪影）。根因：`LayerCascade` L4 底部深层排水上限 = `K_r·ksat₄·1e5·30` ≈ 15 mm/month，华南红壤年渗漏 ~500-800 mm/yr 无法排出 → 保守离子（Na⁺/Cl⁻）在 L4 "死胡同"无限累积。石灰 Ca²⁺ 同样出不去 → Lime pH 永不衰减（异常 C）。**只排水不排盐等于没修**——每个水分出口必须对应溶质移出。
2. **交换性酸库缺失（P-E2-1 相关的 A 类异常）**：`build_exchange()` 将交换性 H（`exch_h`）并入 Na（`na_mol = (na + exch_h)×mass`），天然不存在 HX 酸库；phreeqc.dat 的 `H+ + X- = HX` 定义被注释禁用（第 1362 行）。表层交换性酸缓冲缺失导致 Natural pH 从 3.9 暴降至 2.0（钳制值）的极端趋向。
3. **fallback 过度降级（P-NUM-3）**：单场单层 PHREEQC 失败 → 全局 `_permanent_fallback=True` → 50 年模拟后续全部简化（v0.5.3 契约）。事件化下不合理。

科学诚实边界：**v0.6.1 是数值稳定性版本——pH 具体值不在承诺范围**（natural 4.5~5.0 等目标带留 v0.7.0）。本版验收 = 30 年 8 情景全 `phreeqc_ok` + L4 max 浓度 <1 mol/L + 水量闭合 <1% / 盐分 <5%。

---

## Solution

从用户（土壤模型开发/研究者）视角：v0.6.1 交付一个"**30 年跑得完、盐分出得去、酸库守得住**"的稳定基线。

1. **深层基流（专家方案 L4 底部）**：VIC 风格非线性 `Q_base = D_max·[D_s·S + (1−D_s)·Sⁿ]`，`S=(θ−θ_r)/(θ_s−θ_r)`，θ_c=θ_r（残余含水量），D_s=0.10（裂隙流基线），n_base=2.5，D_max=100 mm/month；防抽干 `Q_base = min(公式, (θ−θ_r)·d·10)`。旱季 θ_r<θ<θ_FC 有微量基流（D_s 线性项），不抽到 θ_r 以下。
2. **侧向排水（各层）**：Darcy 集总 `Q_lat,i = k_lat,i · f_slope · max(0, θ_i−θ_FC,i) · d_i · 10`，`k_lat=[0.04/0.025/0.015/0.008] /day`，f_slope=0.10（tan 6°）；严格 FC 闸门（θ≤θ_FC 零侧向）；防抽干 `Q_lat = min(公式, (θ−θ_FC)·d·10)`。
3. **溶质随水移出**：侧向/基流排水带走的溶质从 `state.solution` 比例扣除（`n_new = max(n_old×(1−Q_out/V), C_min×V)`），交换相不动靠下场平衡 Gapon 自动补偿；出口溶质记入 `event_details` 与 `total_lateral_i`/`total_base_i` 诊断列。
4. **fallback 事件级局部降级**：单场失败保留前一正常状态跳过（不调 simplified）+ error.inp + 计数；连续 3 次失败才永久降级；事件/月级路径分开计数。
5. **HX 交换酸注入**：`EXCHANGE_SPECIES` 注入 HX（log_k=1.0）；`exch_h` 直接映射 HX（从 Na 剥离）；CEC 缺口 `GAP_H_FRACTION=0.3` 与 `GAP_AL_FRACTION` 并列，剩余按原比例分 AlX3/NaX。
6. **浓度冲洗**：C_warn=0.5 mol/L，事件后某层 max 离子浓度超限 → 超出部分折算为额外 Q_flush（记 `flush_L`）+ 同比例溶质扣除。
7. **闭合审计**：`tools/water_salt_balance.py` 逐月输出 ΣP=ΣRunoff+ΣAET+ΣQlat+ΣQbase+ΔS 与盐分进出口对账（水量 <1% / 盐分 <5%）。
8. **验收**：`tools/sensitivity_pH_30yr.py --tag v061` 重跑 30 年 8 情景 + E1 预平衡收敛复验（HX 影响 4.92 需重验）。

---

## User Stories

1. As a **土壤模型研究者**, I want L4 底部深层排水从固定 ksat 上限改为 **VIC 非线性基流**（θ_c=θ_r、D_s=0.10、n_base=2.5、D_max=100 mm/month），so that 年深层渗漏 ~500-800 mm/yr 能真实排出、Na⁺/Cl⁻ 不再在 L4 死胡同无限累积。
2. As a **土壤模型研究者**, I want 各层具备**侧向排水出口**（k_lat 分层 [0.04/0.025/0.015/0.008]，f_slope=0.10，严格 FC 闸门），so that 坡地侧向壤中流的盐分排泄途径被建模、石灰 Ca²⁺ 3~5 年内可淋出。
3. As a **土壤模型研究者**, I want 基流/侧向排水**带走溶解溶质**（比例扣除 n_new=max(n_old×(1−Q_out/V), C_min×V)），so that 每一个水分出口都对应盐分移出（只排水不排盐等于没修）。
4. As a **土壤模型研究者**, I want 基流/侧向以**事件粒度**调度（事件后 θ 逐场计算、溶质随场移出记入 event_details），so that First-Flush 与盐分移出节奏在事件分辨率下真实。
5. As a **土壤模型研究者**, I want 溶质扣除后交换相**靠后续平衡 Gapon 自动解吸补偿**（不手工改交换相），so that 盐基淋失与交换缓冲的动态平衡由 PHREEQC 自然表达。
6. As a **模型开发者**, I want `calc_baseflow`/`calc_lateral_drainage` 为**纯函数**且 `LayerCascade.run()` 返回 `(drains, runoff_extra, baseflow, lateral, theta_out)`，so that 事件/月路径共用、既有 drains 垂直语义不变、便于单元测试。
7. As a **模型开发者**, I want 新参数入 **config 顶层节点** `simulation.baseflow`/`simulation.lateral` 且 `n_layers=1` 自动禁用，so that 单层回退护栏保持、校验简单、与 layer_overrides 解耦。
8. As a **土壤模型研究者**, I want 单场 PHREEQC 失败时**保留前一正常状态跳过该场**（连续 3 次才永久降级），so that 50 年模拟不被单层单场偶发失败永久降级。
9. As a **模型开发者**, I want 失败计数**事件/月级路径分开**且每次失败落盘 error.inp，so that 数值问题可复现、降级边界可审计。
10. As a **土壤模型研究者**, I want 某层离子浓度超 C_warn=0.5 mol/L 时**触发基流/侧向激增冲洗**（Q_flush 记入 flush_L 诊断列），so that 极端盐分累积有物理式加速出口、质量守恒不破。
11. As a **土壤模型研究者**, I want 初始条件中 **exch_h 直接映射 HX 交换物种**（不再并入 Na），so that 表层交换性酸库真实存在、Natural 酸化有 H 缓冲。
12. As a **土壤模型研究者**, I want **HX 交换物种经 EXCHANGE_SPECIES 注入**（log_k=1.0，phreeqc.dat 已注释禁用需自定义），so that 模型可识别 HX 参与 Gapon 交换。
13. As a **土壤模型研究者**, I want CEC 缺口按 **GAP_H_FRACTION=0.3 / GAP_AL_FRACTION=0.3 / NaX 余量** 重分配，so that 缺口填补有 HX/AlX3/NaX 三通道体现交换性酸与盐基比例。
14. As a **模型开发者**, I want log_k/GAP_H/D_max/f_slope/k_lat 等全部**入 constants.py 可配**，so that 参数化可标定、可扫描。
15. As a **土壤模型研究者**, I want **`tools/water_salt_balance.py` 逐月水量/盐分闭合审计**（ΣP=ΣRunoff+ΣAET+ΣQlat+ΣQbase+ΔS，水量<1%/盐分<5%），so that 出口正确性可验证、质量守恒底线有工程保障。
16. As a **土壤模型研究者**, I want 30 年 8 情景全 `phreeqc_ok=True` + L4 max 浓度 <1 mol/L，so that 长期模拟不再永久降级、曲线后期可信。
17. As a **模型维护者**, I want E1 预平衡收敛值（v0.6.0=4.92）在 HX 注入+GAP_H 重分配后**复验**，so that HX 改变交换基线的影响被科学诚实记录。
18. As a **模型维护者**, I want v0.6.1 发布为独立版本（版本号同步 → commit → annotated tag → push），so that 版本纪律维持、与 v0.7.0 地球化学修复清晰衔接。

---

## Implementation Decisions（/grilling Q1~Q10 决策表，2026-08-20 定案）

| # | 决策项 | 定案 |
|---|--------|------|
| Q1 | 基流/侧向排水出口 | **VIC 非线性基流**（L4 底部替换原 `min(drainable, ksat_cap)`）：`Q_base = D_max·[D_s·S + (1−D_s)·Sⁿ]`，`S=(θ−θ_r)/(θ_s−θ_r)`；`θ_c=θ_r`、`D_s=0.10`、`n_base=2.5`、`D_max=100 mm/month`；防抽干 `Q_base=min(公式, (θ−θ_r)·d·10)`。**侧向排水**（各层）：`Q_lat=k_lat,i·f_slope·max(0, θ_i−θ_FC,i)·d_i·10`，`k_lat=[0.04/0.025/0.015/0.008] /day`、`f_slope=0.10`（tan 6°）；严格 FC 闸门；防抽干 `Q_lat=min(公式, (θ_i−θ_FC,i)·d_i·10)`。 |
| Q2 | 调度粒度 | **事件粒度**：每场事件用事件后 θ 计算 Q_base/Q_lat，溶质随场移出记入 event_details；月末非事件路径同步月粒度版本。 |
| Q3 | 溶质扣除实现 | **引擎层比例扣除 + 出口记账**：`run_event_step` 化学平衡后按 Q_out/V 比例扣溶液（`n_new=max(n_old×(1−Q_out/V), C_min×V)`，C_min=1e-10）；出口记 event_details + `total_lateral_i`/`total_base_i` 诊断列；交换相不动靠 Gapon 补偿。 |
| Q4 | 水量出口实施 | **纯函数** `calc_baseflow`/`calc_lateral_drainage`；`LayerCascade.run()` 顺序=垂直→侧向→基流；返回扩展 `(drains, runoff_extra, baseflow, lateral, theta_out)`；事件/月路径共用；drains 保持垂直语义（进下层）。 |
| Q5 | fallback 局部降级 | **连续 N=3 次失败才永久降级**；失败场保留前一正常状态跳过（不调 simplified）；失败计数事件/月级路径分开；error.inp 每次落盘。 |
| Q6 | 浓度硬上限+冲洗 | **冲洗=基流/侧向激增**：C_warn=0.5 mol/L，事件后某层 max 离子浓度超限 → 超出部分折算 Q_flush（记 `flush_L` 列）并按同比例扣溶液；质量守恒记账完整。 |
| Q7 | HX 注入 | **log_k=1.0 + GAP_H 重分配**：`EXCHANGE_SPECIES H+ + X- = HX` log_k=1.0（phreeqc.dat 注释基准，ALX3 注入先例）；`exch_h` 直接映射 HX（从 Na 剥离）；缺口 `GAP_H_FRACTION=0.3` 与 `GAP_AL_FRACTION=0.3` 并列，剩余 AlX3/NaX 重分配；log_k/GAP_H 入 constants.py 可配；E1 收敛复验。 |
| Q8 | 验收口径 | **数值验收 + 闭合审计**：新增 `tools/water_salt_balance.py`（逐月 ΣP=ΣRunoff+ΣAET+ΣQlat+ΣQbase+ΔS 水量<1%、盐分进出口对账<5%）；30 年 8 情景全 `phreeqc_ok=True` + L4 max 浓度<1 mol/L；pH 值仅诊断不承诺（科学诚实）。 |
| Q9 | 事件聚类 | **不引入**（维持 v0.6.0 Q16 原判）；聚类设计留 v0.7.x 与逐日粒度合并。 |
| Q10 | config & 护栏 | **hydrology 顶层节点** `simulation.baseflow={D_max:100, D_s:0.10, n_base:2.5, theta_c:"auto"(=θ_r)}`、`simulation.lateral={f_slope:0.10, k_lat:[0.04,0.025,0.015,0.008]}`；`n_layers=1` 自动禁用（回退护栏）；与 layer_overrides 解耦。 |

### 关键模块接口（Q1~Q10 落地）

- **`src/hydrology.py`**：新增纯函数 `calc_baseflow(theta, profile, baseflow_cfg) -> mm` 与 `calc_lateral_drainage(theta, profile, lateral_cfg) -> mm`；`LayerCascade.run()` 返回扩展 `(drains, runoff_extra, baseflow, lateral, theta_out)`；顺序=垂直→侧向→基流；`n_layers=1` 路径跳过（返回零出口）。
- **`src/phreeqc_engine.py`**：`run_event_step` 新增溶质比例扣除（Q_lat/Q_base 出口）与浓度冲洗（Q6）；`_run_official_step` fallback 改为连续 N=3 计数（事件/月级分开）；`_build_phreeqc_input` 注入 `EXCHANGE_SPECIES H+ + X- = HX`（log_k=1.0）。
- **`src/initial_condition.py`**：`build_exchange()` 中 `exch_h` 直接映射 HX（从 Na 剥离）；缺口重分配 GAP_H/GAP_AL/NaX 三通道。
- **`src/constants.py`**：新增 BASE_D_MAX=100/BASE_DS=0.10/BASE_N=2.5/BASE_THETA_C_MODE="theta_r"、LAT_F_SLOPE=0.10/LAT_K=[0.04,0.025,0.015,0.008]、CONC_WARN=0.5、HX_LOGK=1.0、GAP_H_FRACTION=0.3、FALLBACK_MAX_CONSECUTIVE=3、C_MIN=1e-10。
- **`src/config_manager.py`**：解析/校验 `simulation.baseflow`/`simulation.lateral` 顶层节点；`n_layers=1` 忽略（回退护栏）；`config.yaml`/`config_example.yaml` 同步。
- **`src/output_writer.py`**：新增诊断列 `total_lateral_i`/`total_base_i`/`flush_L`（每层）+ 事件明细 CSV 扩列。
- **`tools/water_salt_balance.py`**：逐月水量/盐分闭合审计（读主 CSV + event 明细，输出闭合报表）。
- **`tools/sensitivity_pH_30yr.py`**：`--tag v061` 重跑 8 情景 30 年。

---

## Testing Decisions

- **好测试标准**：只测外部行为与物理不变量——VIC 基流端点（θ≤θ_r→0、θ→θ_s→D_max、防抽干 min）、侧向 FC 闸门（θ≤θ_FC→0）、溶质比例扣除数学恒等（n_new=max(n_old×(1−Q_out/V), C_min×V)）、fallback 连续 N=3 状态机、HX 注入字符串断言、GAP 缺口 CEC 守恒、config 校验；不测实现细节。
- **接缝 S1~S7**（2026-08-20 to-spec 定案）：
  - **S1 `test_hydrology.py`（既有扩展）**：`calc_baseflow`/`calc_lateral_drainage` 纯函数端点 + `LayerCascade.run()` 返回结构扩展（drains 垂直语义不变、baseflow/lateral 出系统）+ 事件路径逐场水量出口。
  - **S2 `test_event_chemistry.py`（既有，最高事件接缝）**：`run_event_step` 侧向/基流溶质比例扣除数学不变量 + 出口记账 + 冲洗=基流激增（C_warn 触发 flush_L）。
  - **S3 `test_phreeqc_engine.py`（既有，引擎基线）**：fallback 连续 N=3 语义（前 1~2 次失败保留状态跳过不降级、第 3 次永久降级）+ 失败计数事件/月级分离 + HX `EXCHANGE_SPECIES`/`GAP_H` 注入断言。
  - **S4 `test_initial_condition.py`（既有扩展）**：`exch_h→HX` 映射（从 Na 剥离）+ `GAP_H_FRACTION` 缺口重分配 + CEC 总量守恒不变量。
  - **S5 `test_config_manager.py`（既有扩展）**：`simulation.baseflow/lateral` 解析校验（D_max>0 / k_lat 长度=n / f_slope 范围）+ `n_layers=1` 自动禁用护栏。
  - **S6 `test_multilayer_output.py`/`test_output_writer.py`（既有扩展）**：新诊断列 `total_lateral_i`/`total_base_i`/`flush_L` + 事件 CSV 扩列。
  - **S7 新增 `tools/water_salt_balance.py` + `tools/verify_v0_6_1_numerical.py`**：逐月水量闭合 <1% / 盐分对账 <5%；30 年 8 情景全 `phreeqc_ok` + L4 max<1 mol/L（后台进程跑，避免工具 30s 超时）。
- **不变量保护**：质量守恒/单层回归/数值稳定性-timeout/化学引擎基线四类一字不改；仅新增事件级断言；禁止无替代删除。
- **契约修订（明确允许）**：`test_error_diagnostics_on_failure` 等 fallback 断言按 Q5 改为"连续 N=3 才降级"语义。
- **目标测试数**：259 + 新增 ≈ **280~300 全绿**。
- **先例**：spec 55（S1~S6 接缝）/ `test_hydrology.py`（纯函数）/ `test_event_chemistry.py`（事件接缝）。

## Out of Scope

- NO₃⁻ 示踪池 + 伴随阳离子淋失（v0.7.0，D3）
- 原生矿物风化动力学化（v0.7.0，D2：illite/gibbsite/kaolinite 降级 + 集总风化注入）
- k_om 重参数化 / 动态 OM-C 池（v0.7.0）
- E2 PET 非单调机制判别（v0.7.0 工单 73：框架稳定后做中间点扫描）
- 事件聚类性能开关（Q9 明确不引入；v0.7.x 与逐日排水分辨率合并设计）
- 逐日再分解排水时序（专家方案选项③，v0.7.x 最终优化）
- 毛细上升/双向达西（`calc_interface_flux(mode="bidirectional")` 后续版本）
- SWAP 式 AET 跨层根系补偿（后续版本）

## Further Notes

- **config 默认**：`simulation.baseflow={D_max:100, D_s:0.10, n_base:2.5, theta_c:"auto"}`（auto=θ_r）、`simulation.lateral={f_slope:0.10, k_lat:[0.04,0.025,0.015,0.008]}`；注释附 VIC/Darcy 物理依据与华南红壤参数来源。
- **性能**：基流/侧向为纯计算无 PHREEQC 调用（溶质扣除非平衡调用），对 8×30 年重跑影响 <5%；fallback 计数不增加调用。
- **科学诚实**：pH 具体值不在 v0.6.1 承诺范围（natural 4.5~5.0 等目标带留 v0.7.0）；E1 预平衡收敛值因 HX/GAP_H 注入变化需复验并如实记录新旧值。
- **版本**：v0.6.1；发布流程 = 版本号同步 → commit → annotated tag → push main + push tag。
- **关联工单**：63（VIC 基流+侧向模块）→ 64（fallback 局部降级）→ 65（浓度冲洗+出口记账）→ 66（HX+GAP_H）→ 67（water_salt_balance 审计）→ 68（30 年重跑+E1 复验+发布）。
- **风险评估**：HX 注入会改变交换基线（E1 收敛值、Na 行为、E2 分支）——已纳入工单 68 复验；若预平衡发散，退回 GAP_H_FRACTION=0（HX 仅 exch_h 来源）。VIC 基流 D_max=100 远大于原 ksat_L4 物理值，本质是"裂隙/风化壳基流"工程出口，参数可扫描标定。
