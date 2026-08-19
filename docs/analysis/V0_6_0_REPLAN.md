# Soil-SCM v0.6.0 重新规划（事件驱动化学最小闭环）

> **文档编号**：V0_6_0_REPLAN
> **创建日期**：2026-08-19（v0.5.3 发布后）
> **状态**：已定案（用户 2026-08-19 确认范围划分）
> **依据**：HANDOFF_Soil-SCM.md（v0.5.3）、《v0.6.0优化开发具体步骤.txt》、《v0.7.0优化开发具体步骤.txt》、`docs/analysis/OPTIMIZATION_PLAN.md` §7、`docs/analysis/ROADMAP.md` §5

---

## 一、现状盘点（v0.5.3，234 测试全绿）

### 1. 《v0.6.0优化开发具体步骤》四大模块 vs 现状

| 模块 | 状态 | 实际落点 |
|---|---|---|
| ① Green-Ampt 入渗 | ✅ 已完成 | v0.5.2（工单 44~48）：`solve_green_ampt_F`/`green_ampt_infiltration`，废弃 `surface_coeff` |
| ② VGM 水分特征 | ✅ 已完成 | v0.5.3（工单 50）：`src/vgm.py` + `SoilState.theta` 迁移 |
| ③ Feddes ET | ✅ 已完成 | v0.5.3（工单 51/52）：`feddes_alpha(ψ)` + Oudin PET + `apply_feddes_et` |
| ④ **化学子步长拆分** | 🔴 未做（v0.6.0 主线） | 仍为 `run_monthly_step` 月度单次平衡，`generate_rainfall` 场次被 `sum()` 抹平 |

### 2. 《v0.7.0优化开发具体步骤》四大缺陷 vs 现状

| 缺陷 | 现状核查 | 结论 |
|---|---|---|
| D1 质量不守恒（溶质淋失） | 多层级联已通过 `inflow_ions = conc×drain` 传递溶质；但化学溶液体积-θ 仍解耦（Q8b），底层排水核算待审计 | 🟡 部分解决 |
| D2 原生矿物瞬时溶解 | `red_soil` 矿物库无长石/云母（kaolinite/goethite/hematite/quartz/gibbsite/illite）；矿物仍全走 `EQUILIBRIUM_PHASES` 瞬时平衡，风化动力学化未做 | 🔴 未做 |
| D3 NO₃⁻ 伴随淋失缺失 | `n_no3` 仅为累计器，不参与淋失、不带走盐基阳离子 | 🔴 未做（重要） |
| D4 初始 CEC 缺口填补 | v0.5.0 已落地 `GAP_AL_FRACTION=0.3` + `pre_equilibrate`（E1 收敛 pH 4.92） | ✅ 已解决 |

### 3. v0.5.3 未达成项（重新规划的直接动因）

- pH 回落 4.5~5.5 未达成（表层末月恒 ~6.94，碳酸缓冲主导）
- E2/E3 无方向响应根因（OPTIMIZATION_PLAN §7.6）：**① 月度聚合丢失旱季干化 ② 化学溶液体积-θ 解耦（Q8b）③ OM 被矿物缓冲抵消（k_om 需重参数化）**

> **关键洞察**：v0.5.3 暴露的 pH 无方向响应根因 ①② 恰好是《v0.6.0 文档》模块④（子步长+体积耦合）要解决的问题。两份文档不是两条并行路线，而是**一条路线的两个阶段**。

---

## 二、版本路线（已定案）

### v0.6.0 — 化学子步长拆分（最小闭环）【本版范围】

| 工单（55 起） | 内容 | 关键设计点 |
|---|---|---|
| 55 | v0.6.0 spec | 接口契约 / 聚合口径 / 测试破坏面控制 |
| 56 | `run_event` 引擎接口 | `run_event(state, event, action, profile)`；每场全量 PHREEQC；`run_monthly_step` 保留为月度聚合包装（expand-contract） |
| 57 | 主循环嵌套改造 | `for month → for event: 水文步 → 化学步 → 月末聚合`；水文下钻到事件粒度 |
| 58 | 化学溶液体积-θ 耦合（Q8b） | 每场后 `-water = θ×depth×1e5`，替换恒定 volume → 旱季浓缩酸化 |
| 59 | First-Flush 输出 | 逐场淋失诊断列（NO₃⁻/盐基/重金属事件峰值） |
| 60 | Hargreaves-Samani PET | `pet_method="hargreaves"` 已有预留报错；T_max/T_min 数据源 grill-me 敲定 |
| 61 | 集成 + E2/E3 复验 + 发布 | 方向性验收 + 断点续跑兜底 4~12 倍计算量 |

### v0.7.0 — 地球化学动力学化【后续版本，范围已预留】

工单 62~67：NO₃⁻ 示踪池 + 伴随阳离子淋失（D3，优先）→ 原生矿物风化动力学化（D2，恒定力率法兜底）→ k_om 重参数化 → 质量守恒审计 + 数值下限防护 → 30 年三情景验收（Natural 缓降 / Fertilizer 剧烈酸化 / Lime 3~5 年回落）。

### 长期（v0.7.x）

毛细上升/双向达西（`calc_interface_flux` 已预留）→ AET 跨层根系补偿 → L1 Al 表面络合实现 → L7 pip 包 / L8 敏感性框架 → 水文参数标定 → WRF 耦合。

---

## 三、grilling 决策表（Q1~Q16，2026-08-19 定案）

> 来源：/grilling 2 轮决策拷问（2026-08-19）。选项原文见会话记录，此处仅录定案。

### 主题 A：`run_event` 接口契约

| # | 决策项 | 定案 |
|---|--------|------|
| Q1 | 事件数据形态 | 新建 `RainEvent` dataclass（`precip_mm/duration_h/precip_chem/日期`）；`run_event_step(state, event, action, profile)` |
| Q2 | 月末输出口径 | 月末 pH/交换离子 = **最后一场事件**的 PHREEQC 状态（状态顺序传递）；逐场淋失单独输出序列 |
| Q3 | 水文-化学耦合顺序 | **逐场闭环**：场事件 → 水文步（Green-Ampt 入渗+层间级联更新 θ）→ 化学步（`run_event_step`，用事件后 θ 作体积基准）→ 下一场 |
| Q4 | 事件内层间溶质传递 | **逐场级联**：每场事件后上层排水溶质（`conc×drain_vol`）作为下层当场 `inflow_ions`（First-Flush 本质） |
| Q10 | expand-contract 边界 | **三接口并存**：`run_event_step`（核心）+ `run_monthly_step` 改为月度聚合包装（内部逐场循环，签名不变）+ `run_monthly_multi_layer` 不动 → 现有 234 测试全部不破 |
| Q11 | 事件列表生成归属 | 新增 `generate_events(monthly_precip_mm, year, month, seed) -> List[RainEvent]` 放 `src/hydrology.py`（复用 `generate_rainfall` seed 派生）；`RainEvent` dataclass 同模块 |
| Q15 | 事件级 bypass 优先流 | **逐场注入**：每场事件径流水×β 注入 L2（与子步长一致） |

### 主题 B：化学溶液体积-θ 耦合（Q8b 修复）

| # | 决策项 | 定案 |
|---|--------|------|
| Q5 | 体积耦合方式 | **逐事件重建**：`SOLUTION -water = θ_事件后×depth×1e5`（`theta_to_water_L`）；REACTION 只注入该场净入渗水量与化学 |
| Q6 | 交换相/矿物相响应 | **绝对摩尔量不变**（PHREEQC EXCHANGE/EQUILIBRIUM_PHASES mol 为绝对量，自动与溶液重平衡浓度） |
| Q7 | 旱季无事件期化学 | 无降水事件**不调 PHREEQC**；θ 随 ET/排水演化；**月末一次"体积浓缩平衡"**（θ 月内下降时重设 `-water`，否则跳过） |
| Q12 | 浓缩平衡调度粒度 | **月末一次**：每层若 θ 月内下降 → 重设 `-water` 做浓缩平衡；θ 无变化则跳过（对治"月尾 θ 恒 θ_FC 掩盖旱季干化"根因） |

### 主题 C：Hargreaves PET（Oudin 精度增强模式）

| # | 决策项 | 定案 |
|---|--------|------|
| Q8 | T_max/T_min 来源 | config 新增 `climate.diurnal_range_deg`（默认 8.0，校验 >0）；`T_max = T_mean + range/2`、`T_min = T_mean − range/2`（非硬编码） |
| Q9 | 方法与关系 | **共享 `calc_pet()` 单入口分派**：`"oudin"`（默认，现状不变）/ `"hargreaves"`（`PET = 0.0023×R_a×(T_mean+17.8)×√(T_max−T_min)`，R_a 复用 Oudin 计算）/ `"hargreaves_enhanced"`（v0.6.0 **只预留枚举+报错**，数据管线留 v0.7.0）。下游 ET 扣除无需知道方法来源 |
| Q13 | 公式确认 | ✅ 按 Q9 定案落地 |

### 主题 D：输出与性能

| # | 决策项 | 定案 |
|---|--------|------|
| Q14 | First-Flush 输出格式 | **双轨**：月度主 CSV 新增峰值列 `flush_NO3_peak_mmol`/`flush_base_peak_mmol`（当月最大单场淋失，默认开）+ 新增 `output.event_output: true` 开关→逐场明细 CSV（`output/event_leaching_<scenario>.csv`，默认关） |
| Q16 | 性能预算与断点续跑 | 接受量级（15 年 4 层 ≈ 0.3~0.9 万次 PHREEQC，50 年全量 ≈ 1~4 分钟）；事件级 `run_event_step` 复用子进程超时包装（`_monthly_step_worker` 模式）；sensitivity `--all --max N` 分批断点续跑；**不加** `max_events_per_month` 上限开关 |

### 主题 E：验收红线（科学诚实）

- E2 复验：PET 敏感性 → 旱季 θ 下降 + 溶液浓缩酸化 → **pH 方向性响应**
- E3 复验：k_om 敏感性 → 表层酸化方向
- First-Flush：雨季单场淋失峰值 > 月均（峰值列可验证）
- 不承诺 pH 具体回落值（4.5~5.5 为方向目标）

---

## 四、风险与纪律

1. **测试破坏面**：事件化是宽重构 → expand-contract（Q10）+ 单层护栏（`n_layers=1` 回退）
2. **计算成本**：50 年×~8 场×4 层 ≈ 1.6 万次 PHREEQC（Q16 确认可接受）→ `_monthly_step_worker` 子进程超时 + sensitivity 分批断点续跑
3. **数值稳定性**：事件级小水量 → 离子浓度下限 `1e-10 mol/L` + 体积骤变防护（v0.7.0 文档 §三.3 预留）
4. **版本纪律**：v0.6.0 / v0.7.0 独立 spec+工单+tag，发布前与用户确认编号
5. **科学诚实**：pH 回落 4.5~5.5 是**方向性**目标，逐版本验收只承诺方向证据（同 v0.5.3 E1~E3 口径）
