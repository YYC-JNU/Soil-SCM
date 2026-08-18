# Soil-SCM 优化处理计划与执行日志

> **创建时间**：2026-08-11
> **更新日期**：2026-08-18
> **状态**：进行中
> **目标**：让 InitialConditionBuilder 生成的 PHREEQC 输入在 `phreeqc.dat` 下可收敛运行，使主程序走真实 PHREEQC 化学计算路径（而非降级简化模式）
> **v0.6.0 目标（2026-08-18 更新）**：修复 v0.5.1 水文盒子的 4 个物理缺陷（surface_coeff 非物理补丁 / 水桶模型 / 缺 ET / 月度平滑抹杀），按 **v0.5.2 → v0.5.3 → v0.6.0** 三阶段推进水文物理化重构——Green-Ampt / VGM / Feddes ET / 化学子步长（已定案决策见 §7）

---

## 一、问题诊断汇总

| 编号 | 问题描述 | 根因 | 证据 | 状态 |
|------|----------|------|------|------|
| P1 | EQUILIBRIUM_PHASES 块报 `Phase not found: anatase` | `anatase` 矿物相不存在于 `phreeqc.dat`（PHASES 段共 39 种相） | `phreeqc.dat` 第 905 行起 PHASES 段 | ✅ 已修复 (S2) |
| P2 | EXCHANGE 块 `HX` 交换物种无效 | `phreeqc.dat` 中 `H+ + X- = HX` 被注释禁用（`# !!!!!`） | `phreeqc.dat` EXCHANGE_SPECIES 段（约第 1278 行） | ✅ 已修复 (S1) |
| P3 | SURFACE 块无法识别 | `phreeqc.dat` 仅定义 `Hfo_s`/`Hfo_w`（Dzombak & Morel 模型），而文档代码使用 `Som`/`Hfo`；且 `-sites` 语法缺单位说明 | `phreeqc.dat` SURFACE_SPECIES 段（约第 1354 行） | ✅ 已处理 (S3, 默认关闭) |
| P4 | SOLUTION 数值不收敛（C、Ca not converged） | SOLUTION 预设 `C(4)` 与 GAS_PHASE 固定 CO₂(g) 分压约束冲突；初始浓度与交换/气相不平衡 | run_string 实测错误输出 | ✅ 已修复 (S0/S4, 加入矿物相锚定后收敛) |
| P5 | CEC 与交换性阳离子总量不一致 | CEC=12 cmol(+)/kg，交换性阳离子电荷总和仅 8.2 cmol(+)/kg | `validate()` 输出：位点 2.952e5 mol vs CEC 4.32e5 mol | ✅ 已修复 (S1, NaX 补齐) |

---

## 二、优化步骤与时间节点

| 步骤 | 内容 | 计划时间 | 状态 | 实际完成 |
|------|------|----------|------|----------|
| S0 | 最小可运行基线：逐块叠加测试（SOLUTION→+EXCHANGE→+GAS_PHASE→+EQUILIBRIUM_PHASES），定位不收敛源头 | 2026-08-11 14:00-14:30 | ✅ 已完成 | 2026-08-11 |
| S1 | 修复 `build_exchange()`：移除 HX、用 NaX 补齐 CEC 未覆盖位点 | 2026-08-11 14:30-15:00 | ✅ 已完成 | 2026-08-11 |
| S2 | 修复矿物相：`build_minerals()` 过滤数据库不支持的相（anatase） | 2026-08-11 15:00-15:30 | ✅ 已完成 | 2026-08-11 |
| S3 | 修复 SURFACE 块：默认 `include_surface=False`（关闭） | 2026-08-11 15:30-16:00 | ✅ 已完成 | 2026-08-11 |
| S4 | 数值收敛验证：完整输入（无 SURFACE）run_string 收敛，pH=5.0 | 2026-08-11 16:00-16:30 | ✅ 已完成 | 2026-08-11 |
| S5 | 引擎集成：`build_initial_state` 复用 `InitialConditionBuilder`；新增 `engine_mode` 配置（simplified/phreeqc/auto） | 2026-08-11 16:30-17:30 | ✅ 已完成 | 2026-08-11 |
| S6 | 回归与情景验证：natural / fertilizer / fertilizer_lime 三情景对比 | 2026-08-11 17:30-18:00 | ✅ 已完成 | 2026-08-11 |

---

## 三、执行日志

> 每完成一个步骤在此追加记录（时间、改动文件、验证结果）。

### S0 — 最小可运行基线（2026-08-11）
**做法**：逐块叠加测试（SOLUTION → +EXCHANGE → +GAS_PHASE → +EQUILIBRIUM_PHASES → 交换物种单项检查）。
**发现**：
- SOLUTION only ✅ 收敛（pH=5.0）
- +EXCHANGE ❌ Al 不收敛（AlX3=2.4e4 mol 与溶液/交换耦合失衡）
- +GAS_PHASE ❌ 同样 Al 不收敛
- +EQUILIBRIUM_PHASES(含 anatase) ❌ `Phase not found: anatase`
- +EQUILIBRIUM_PHASES(排除 anatase) ✅ **收敛 pH=5.0**（矿物相锚定 Al/Fe 平衡）
- 交换物种单项测试：`HX` ❌ 失败；`NaX/KX/CaX2/MgX2/AlX3/NH4X` ✅

### S1 — 修复 build_exchange（2026-08-11）
**改动**（`src/initial_condition.py`）：
- 移除 `HX`（phreeqc.dat 未定义该交换物种）
- 交换性 H 位点并入 NaX；用 NaX 补齐 CEC 未覆盖位点（`gap = CEC - Σ交换阳离子电荷`）
- `_calc_exchange_site_total` 同步移除 HX 项
**验证**：总位点 = CEC = 4.32e5 mol，validate() 的 CEC 一致性告警消失。

### S2 — 过滤不支持矿物相（2026-08-11）
**改动**（`src/initial_condition.py`）：`build_minerals()` 增加 `unsupported = ('anatase',)` 过滤（phreeqc.dat PHASES 段无此相）。
**验证**：mineral keys 不含 anatase（kaolinite/goethite/hematite/quartz/gibbsite/illite）。

### S3 — SURFACE 默认关闭（2026-08-11）
**改动**（`main.py`）：阶段 4 的 `build_phreeqc_input(include_surface=True)` → `False`。
**原因**：phreeqc.dat 仅定义 `Hfo_s`/`Hfo_w`（Dzombak & Morel），文档生成的 `Som`/`Hfo` 位点不兼容。

### S4 — 数值收敛验证（2026-08-11）
**验证**：`build_phreeqc_input(include_surface=False)` 完整输入 run_string 收敛，pH=5.0。P1-P5 全部修复。

### S5 — 引擎集成与模式配置（2026-08-11）
**改动**：
- `phreeqc_engine.build_initial_state()` 复用 `InitialConditionBuilder`（正确交换物种名/矿物相）
- 新增 `engine_mode` 配置（simplified/phreeqc/auto），贯穿 config.yaml、config_manager.py、phreeqc_engine.py、main.py
**验证**：
- phreeqc 模式：引擎初始化、月循环 run_string 收敛、**不降级**，pH 稳定 5.0
- 实验证实 phreeqpython 1.6.2 内置引擎限制：SOLUTION 指定 pH 后 pH 被锁定；REACTION（加酸/碱/水）与 USE/SAVE 均无法驱动 pH 变化；`-charge` 选项不被识别

### S6 — 回归与情景验证（2026-08-11）
**验证**（simplified 模式，50 年）：natural 4.81→3.50；fertilizer 4.66→3.50；fertilizer_lime 4.96→3.50（前 30 年石灰缓减酸化效果显著）。情景差异符合物理预期。

---

## 四、验收标准（检查结果）

| # | 验收标准 | 结果 |
|---|----------|------|
| 1 | `build_phreeqc_input(include_surface=False)` 在 phreeqc.dat 下收敛且 pH 合理 | ✅ 收敛，pH=5.0（红壤合理范围） |
| 2 | `validate()` 不再报告 CEC 不一致 | ✅ CEC 告警消失；电荷平衡警告保留（`_check_charge_balance` 为简化估算，PHREEQC 可自行平衡） |
| 3 | main.py PHREEQC 引擎执行真实计算、不再"永久降级" | ✅ phreeqc 模式全程无降级 |
| 4 | 三情景 pH 演变有化学响应 | ✅ natural/fertilizer/fertilizer_lime 差异显著 |

---

## 五、已知限制与后续方向

### 已知限制（phreeqpython 1.6.2 内置引擎，实验证实）
1. **pH 锁定**：SOLUTION 块指定 pH 后，即使 REACTION（加酸/加碱/加 H2O）或 USE/SAVE 状态传递也无法改变 pH —— 因此 phreeqc 模式下 pH 保持初始平衡值，无长期演化。
2. **`-charge` 选项不可用**：SOLUTION 的 `-charge <元素>` 报 "Unknown option"，无法通过电荷平衡让 pH 自由。
3. **SURFACE 兼容性**：phreeqc.dat 只有 `Hfo_s`/`Hfo_w` 表面物种，文档代码的 `Som`/`Hfo` 不兼容（已默认关闭）。
4. **数值收敛窗口窄**：CO₂ 分压偏离 0.015 atm、或初始 pH 偏离 5.0 时 Al/Ca 易不收敛（当前用矿物相锚定缓解）。

### 引擎模式说明（config.yaml → simulation.engine_mode）
| 模式 | 行为 | 适用 |
|------|------|------|
| `simplified`（默认） | 简化动力学：pH 随降水淋溶/施肥/石灰长期演变 | 情景对比、教学演示 |
| `phreeqc` | PHREEQC 化学平衡：初始化学状态精确、矿物/交换/气相平衡；受库限制 pH 锁定 | 初始化学状态验证 |
| `auto` | PHREEQC 可用则用，否则简化 | 通用 |

### 后续优化方向
1. **完整 PHREEQC 演化**：换用支持自由 pH 的 PHREEQC 分发（如 phreeqc 官方 IPhreeqc）或升级 phreeqpython；实现 USE/SAVE 状态传递与 SELECTED_OUTPUT 提取
2. **SURFACE 络合**：按 phreeqc.dat 的 `Hfo_s`/`Hfo_w`（强/弱位点 10%/90%）重构 `build_surface()`，启用表面络合
3. **扩展数据库**：为 `anatase`（及更多 TiO₂/有机质相）在自定义 .dat 中补充 `PHASES`/`SURFACE_SPECIES` 定义
4. **收敛稳健性**：为 EXCHANGE 增加 `-gamma`、为矿物相设置 `-tolerance`，扩大收敛窗口

---

## 六、现存问题清单（v0.1.0，暂未修复）

> 记录日期：2026-08-11。以下问题已完成诊断确认，**仅登记备查，暂不修改代码**。
> 优先级：高 = 影响科研可用性；中 = 影响架构完整性；低 = 完善项。
>
> **2026-08-11 Q1 实施已解决以下问题**（详见 `docs/analysis/Q1_ANALYSIS.md`）：
> - **Q1** PHREEQC 状态传递与化学演化（换用官方 phreeqc 引擎，SELECTED_OUTPUT 回填）
> - **Q2** REACTION 无效 / pH 锁定（官方引擎 REACTION 有效，pH 演化验证 3.53→3.65）
> - **Q6** 简化模式状态丢失（`_run_simplified_step` 保留化学状态）
> - **Q12** 交换性阳离子与 CEC 不匹配（缺口位点由 NaX 改为 AlX3 补齐）
> - **Q13** 电荷平衡告警（`build_solution` 用 Cl⁻ 补足阳离子盈余）

### 一、模型核心限制

| 编号 | 问题 | 位置 | 影响 | 优先级 |
|------|------|------|------|--------|
| Q1 | PHREEQC 状态不传递、无化学演化：`_parse_phreeqc_output` 只提取 pH，溶液/交换/矿物每月用初始值重建，平衡结果被丢弃 | `src/phreeqc_engine.py` | phreeqc 模式下无累积演化 | 高 |
| Q2 | phreeqpython 内置引擎 pH 锁定：SOLUTION 指定 pH 后加酸/碱/水均无法改变；`-charge` 选项不可用（实验证实） | 库限制（viphreeqc.dll） | phreeqc 模式 pH 恒定 5.0，`fertilizer`/`lime` 情景无差异 | 高 |
| Q3 | 数值收敛窗口窄：CO₂ 偏离 0.015 atm、初始 pH 偏离 5.0 即 Al/Ca 不收敛 | `src/initial_condition.py` / PHREEQC 输入 | 气候情景（precip/temp increase）下 PHREEQC 易降级 | 高 |
| Q4 | 简化模式物理近似粗糙：pH 变化由经验系数驱动（`precip×0.0001`、`fert×0.0005`、`lime×0.0003`），无真实化学平衡/缓冲 | `src/phreeqc_engine._run_simplified_step` | 结果仅具演示意义 | ✅ 已完成 (v0.2.1, 默认auto+物理量级校准) |
| Q5 | pH 下限硬编码 3.5：长期淋溶触底"封底"，后期曲线无区分度 | `src/phreeqc_engine._run_simplified_step` | natural/fertilizer 结局相同 | ✅ 已完成 (v0.2.1, 放宽至2.0~12.0) |
| Q6 | 简化模式状态丢失：`_run_simplified_step` 返回的 `new_state` 只含 `ph`，溶液/交换/矿物被清空 | `src/phreeqc_engine.py` | 架构不完整 | ✅ 已完成（部分，v0.1.1 起保留化学状态） |

### 二、功能未集成 / 半成品

| 编号 | 问题 | 位置 | 影响 | 优先级 |
|------|------|------|------|--------|
| Q7 | 降水化学从未生效：`precip_chemistry_default.json`（酸雨 SO₄/NO₃/NH₄ 离子）与 `PrecipChemConfig` 仅被解析，无代码加载使用 | 全局（`src/config_manager.py`） | 酸雨驱动土壤酸化的核心机制缺失 | ✅ 已完成 (v0.1.4, 见 docs/analysis/Q7_PRECIP_CHEMISTRY.md) |
| Q8 | `phreeqc_initial_input` 生成后只打印不用：阶段 4 生成的 PHREEQC 输入与阶段 7 引擎是两条独立路径 | `main.py` | 功能割裂 | ✅ 已完成 (v0.2.2) |
| Q9 | SURFACE 表面络合未启用：有机质（Som）/铁氧化物（Hfo_s/Hfo_w）吸附缓冲未模拟，`include_surface=False` 硬编码 | `main.py` / `src/initial_condition.py` | 养分离子吸附缓冲缺失 | 中 |
| Q10 | 子时间步长未验证：`sub_time_step_days` 配置与循环存在但从未实测（`n_sub=int(30/sub_steps)` 假设每月 30 天） | `main.py` / `config.yaml` | 功能可信度未知 | ✅ 已完成 (v0.2.2, 与月步长一致) |
| Q11 | `output.variables` 配置未生效：config 中 `[pH, ..., mineral_mass, solution_ions]` 与代码默认值不一致，输出列写死 | `config.yaml` vs `src/output_writer.py` | 配置项为摆设 | ✅ 已完成 (v0.2.2) |

### 三、数据与物理一致性

| 编号 | 问题 | 位置 | 影响 | 优先级 |
|------|------|------|------|--------|
| Q12 | 交换性阳离子与 CEC 不匹配：`exchangeable_ions.csv` 电荷总和 8.2 cmol/kg < CEC 12，差额被强制用 `NaX` 填充——真实红壤剩余位点应主要由 Ca/Al/H 占据，Na 通常很少 | `data/exchangeable_ions.csv` / `src/initial_condition.build_exchange` | 物理不严谨 | 高 |
| Q13 | 电荷平衡检查仍报警告：`_check_charge_balance` 把 C(4) 按一价简化，阳离子估算偏高 | `src/initial_condition.py` | `validate()` 输出 3.07e-3 mol/L 不平衡 | 中 |
| Q14 | anatase（TiO₂）被排除：phreeqc.dat 无此相，红壤矿物组成中 TiO₂ 贡献被静默忽略 | `src/initial_condition.build_minerals` | 矿物相不完整（2% 质量） | 低 |

### 四、代码质量与工程化

| 编号 | 问题 | 位置 | 影响 | 优先级 |
|------|------|------|------|--------|
| Q15 | 全部用 `print` 输出，无 `logging` 模块 | 全局 | 无法分级、持久化日志 | ✅ 已完成 (v0.2.0) |
| Q16 | 无单元测试：`InitialConditionBuilder` 单位换算、`PhreeqcEngine` 降级逻辑等无回归保护 | 全局 | 修改易引入回归 | ✅ 已完成 (v0.2.0, tests/ 36用例) |
| Q17 | main.py 用 `sys.path.insert(0, ...)` hack，非正规包结构 | `main.py` | 无法 `pip install` 或从别处 import | 低 |
| Q18 | `_run_phreeqc_step` 捕获所有异常静默降级，PHREEQC 失败真实原因被掩盖 | `src/phreeqc_engine.py` | 不利于排查 | ✅ 已完成 (v0.2.0) |
| Q19 | 魔法数字过多：简化模式系数、pH 上下限、热力学常数散落 | `src/phreeqc_engine.py` / `src/initial_condition.py` | 维护困难 | ✅ 已完成 (v0.2.2, src/constants.py) |
| Q20 | requirements.txt 无版本上限，未来 `phreeqpython`/`numpy` 升级可能破坏兼容 | `requirements.txt` | 兼容性风险 | 低 |

### 五、文档与配置不一致

| 编号 | 问题 | 位置 | 影响 | 优先级 |
|------|------|------|------|--------|
| Q21 | README 目录结构过时：`src/` 缺少 `initial_condition.py`；未列 `docs/` 目录 | `README.md` | 文档与代码不一致 | 低 |
| Q22 | README 未说明 `engine_mode`（simplified/phreeqc/auto）配置项与 PHREEQC 库限制 | `README.md` | 用户不知三种模式差异 | 低 |
| Q23 | NetCDF 输出静默回退：未安装 netCDF4 时回退 CSV 且无提示 | `src/output_writer._save_netcdf` | 输出格式与预期不符 | 低 |

### 六、安全与运维

| 编号 | 问题 | 位置 | 影响 | 优先级 |
|------|------|------|------|--------|
| Q24 | commit 作者邮箱 `yycfab@sina.com` 含用户名 | git 配置 | 身份信息暴露（可改用 GitHub noreply 邮箱） | 低 |
| Q25 | GitHub Token 明文存于 `~/.git-credentials` | 本机 `~/.git-credentials` | 本机安全风险，30 天过期 | 中 |
| Q26 | GitHub 服务器可能残留旧 commit blob（已被 force push 覆盖、无引用） | GitHub 远端 | 风险低，但无法完全清除 | 低 |

---

### Q7+F1+F2 — 降水化学集成与引擎修复（2026-08-12）

**改动**：
- 新增 `src/precip_chemistry.py`：占比→浓度换算（pH 自洽总当量 1.7783e-4 eq/L）、`reaction_amounts()`
- `phreeqc_engine._build_phreeqc_input`：REACTION 追加降水离子（× 入渗系数）、GAS_PHASE pCO₂ 用 `forcing['pCO2']`（F1）、SELECTED_OUTPUT 加 F
- `initial_condition`：`MINERAL_SCALE=0.001` 常量统一（F2）、GAS_PHASE 用 `self.pCO2`
- `config_manager`/`main.py`：降水数据加载与引擎传递；config.yaml 补充说明
- 默认数据：广东2025公报 pH=5.75（v0.1.3 已更新）

**验证**（30 年 natural，官方引擎）：
- 全程无降级
- Cl⁻ 从"跌至 10⁻¹⁷"改善为"稳定于降水浓度 3.27e-5 mol/kgw"（Q7 核心目标达成）
- F/N 持续输入；pCO₂ 季节波动 0.0117~0.0208 atm（F1 生效）
- pH 第 8 年突升 10.3（单层模型已知局限，需 Phase 3 多分层）

---

### Q15+Q16+Q18 — 工程化地基（2026-08-12, v0.2.0）

**改动**：
- 新增 `src/logging_config.py`：`setup_logging()`（console+file 双输出、幂等）+ `get_logger()`
- Q16：新增 `tests/` pytest 框架，36 用例全绿（锁定 Q7 换算、F1 pCO₂、F2 矿物量、T3 异常诊断）
- Q15：5 个模块 print→logger（`[WARNING]/[INFO]/[OUTPUT]/[PLOT]` 0 残留；`print_summary` 用户界面保留）
- Q18：`_run_official_step` 失败时记录 `last_error_message`/`last_error_input`（完整输入落盘）+ `logger.error(exc_info)`
- main.py 阶段 1 接入 `setup_logging()`，生成 `output/soil_scm.log`

**验证**：pytest 36 passed；main.py 运行生成 soil_scm.log（INFO 分级）

---

### Q4+Q5+P4 — T1 物理校准（2026-08-12, v0.2.1）

**改动**：
- S3 默认引擎改 `auto`（config.yaml + config_manager 默认值）
- P4 修复：`_run_simplified_step` 引用不存在的 `fertilizer_amount` → 改用各肥料量之和（simplified+施肥不再崩溃）
- S4 简化系数物理量级校准：k_precip 1.5e-5 / k_fert 0.0007 / k_lime 0.002（natural 30 年不再触底 3.5）
- S5 Q5 修复：移除 3.5/9.0 硬编码，放宽至 2.0~12.0

**验证**：pytest 38 passed（新增 P4 回归 + auto 默认断言）；simplified 30 年曲线方向物理合理

**说明**：official natural 前 7 年 pH 上升是单层 Al 淋洗局限，故简化模式采用物理量级校准而非对标

---

### T3+T4+T5+T6 — 短期收尾（2026-08-12, v0.2.2）

**改动**：
- T3: `precip_infiltration` 参数化（config + 引擎）；石灰量 30/45/60 kg 扫描验证（pH 差异 +0.6，默认 45kg 保留，pH 偏高归因单层 Al 淋洗局限）
- T4(Q19): 新增 `src/constants.py` 统一 `SIMPLIFIED_K_*/PH_*/PRECIP_INFILTRATION_DEFAULT/MINERAL_SCALE`
- T5(Q8): main.py 移除 `build_phreeqc_input` 只打印不用的调用（引擎经阶段 7 build_initial_state 复用 InitialConditionBuilder）
- T6(Q10/Q11): 子时间步验证（max diff=0）；`output.variables` 配置生效 + JSON 序列化可选诊断（mineral_mass/solution_ions）

**验证**：pytest 38 passed；编译 OK；Q10 三种步长（0/7/1）结果完全一致

---

### 优先级统计

| 优先级 | 数量 | 编号 |
|--------|------|------|
| 高 | 2 | Q3 Q12 |
| 中 | 3 | Q9 Q13 Q25 |
| 低 | 8 | Q14 Q17 Q20 Q21 Q22 Q23 Q24 Q26 |

> 合计 26 项。

---

### T01+T02+T04 — 工程化清理（2026-08-13, v0.2.4）

**背景**：基于 `.scratch/soil-scm-overview/` spec 与 `/code-review` 审查发现（P1/P2/S1/S2/S3）拆分的三张工单，经 `/implement`+`/tdd`+`/code-review` 完成。

**改动**：
- **T01**（P1）：`src/phreeqc_engine.py` 异常分支追加 `Path(ERROR_INP_PATH).write_text(input_string)`（写入失败 try/except 隔离）；`src/constants.py` 新增 `ERROR_INP_PATH="error.inp"`（Q19 收敛）。README 承诺的"失败自动生成 error.inp"兑现。
- **T02**（P2+S1）：`src/scenario_controller.py` 移除 `MonthlyAction.precip_factor`/`temp_offset` 死字段（从未赋值/读取）；spec 4 处同步（US28/情景-动作分离/领域词汇/S2 接缝）。
- **T04**（S2+S3+S1）：`src/utils.py` 删除 6 个零调用函数；`initial_condition.py` 复用 `SoilProfile` 属性（修复 Feature Envy）+ `_calc_cec_total` 接入 `cmol_to_mol_per_kg`；`climate_forcing.py` 接入 `estimate_soil_pCO2`。

**验证**：pytest 62 passed（+2 新增）；E2E 数值一致（soil_mass=3.6e6/porosity=0.5472/cec_total=4.32e5/pCO2=0.011682）；`/code-review` 双轴通过。

**说明**：main.py 盐基饱和度为动态交换位点电荷占比（与静态 cmol 语义不同），保留内联，未按工单示例改用 `estimate_base_saturation`。

---

### WF1-WF5 — 中期架构：多分层 + SURFACE（2026-08-13, v0.2.5）

**背景**：经 wayfinder 地图（WF1-WF5）规划的中期架构升级——多分层模型（Q12*）+ SURFACE 表面络合（Q9）。

**改动**：
- **WF1（决策）**：`List[SoilState]` + 一维平流 + 级联下渗；`run_monthly_step` 接口不变 + 新增 `run_monthly_multi_layer` 编排层；`n_layers` 配置 + 层后缀输出。
- **WF2（多分层实现）**：`run_monthly_multi_layer` 编排层（层循环 + 级联平流交换）；`SoilState` 列表状态；SELECTED_OUTPUT totals × 排水量守恒核算。
- **WF3（SURFACE 调研）**：phreeqc.dat 原生支持 Hfo_s/Hfo_w（Dzombak & Morel 1990），P/Zn 吸附丰富但 **Al 表面物种缺失**（minteq.v4/wateq4f/RES³T 四源查证均为研究空白）。
- **WF4（SURFACE 实现）**：`build_surface()` 重构（Hfo_s/Hfo_w 位点，HFO_TARGET_SITES 约束收敛）；`enable_surface` 配置；KNOBS 迭代数自适应（SURFACE 时 1000）；P/Zn 吸附显著增强。
- **WF5（集成验证）**：4 层 + SURFACE 组合测试（82 用例全绿）；验证结论——多层**推迟** pH 突升（第 8→10 年）+ 垂直梯度；SURFACE 增强 P/Zn 吸附但**雨季加速 Al 耗尽**；**Al 表面络合未实现**（研究空白，独立工单）。

**验证**：pytest 82 passed；4 层无 SURFACE 15 年模拟：前 7 年 pH 梯度稳定（4.9→7.9 顶层），第 10 年突升（Al 耗尽不可避免）。

**结论**：Q12* 部分解决（多层推迟 + 垂直梯度）、Q9 解决（P/Zn 吸附）；完整解决 pH 突升需 Al 矿物化抑制等进一步机制。

---

### L2 — 矿物演化回填（2026-08-13, v0.2.6, Q12* 根治）

**背景**：WF5 验证确认多层推迟但未根治 pH 突升。实验定位真正根因——**非矿物量不足**（增大矿物量反而加速 Al 耗尽），而是 `_parse_official_output` 的 Q1 占位实现 `new_state.minerals = old_state.minerals` 将矿物相**冻结**，使矿物成为"单向 Al 汇"（吸收交换 Al 沉淀但不回补）。

**改动**：
- `phreeqc_engine._build_phreeqc_input`：SELECTED_OUTPUT 加 `-equilibrium_phases`（输出矿物摩尔量）
- `phreeqc_engine._parse_official_output`：读取矿物摩尔量回填 `new_state.minerals`（含 `max(0.0)` 防御 + 未输出兜底）

**验证**（修复前后对比）：
- 修复前：单层 AlX3 第 8 年耗尽 → pH 突升 10.66
- 修复后：单层 12 年 AlX3 稳定 67,409 mol → pH 平缓 6.46；4 层 8 年各层 Al 保留、pH 梯度稳定（6.08/4.14）
- 新增 `tests/test_mineral_evolution.py`（3 用例），完整套件 85 passed

**结论**：Q12* 从"部分解决（推迟）"升级为"**根治**"——矿物演化回填建立 Al 循环通道。

---

### L4 + L5 — v0.3.0 化学机理收尾（2026-08-14）

**背景**：基于 `.scratch/soil-scm-overview/issues/05-10` spec/工单，经 `/to-spec` + `/to-tickets` + `/grilling`（3 轮共识）完成。

**L4 硝化两步（库存层）**：
- 实测发现 `phreeqc.dat` N 氧化还原平衡将任何注入溶液的无机氮全转为 N₂（pe=0~12 下 N(-3)/N(5)≈0）——旧实现施肥氮同样 100% 流失，系既有局限显式化
- 氮形态（尿素/NH₄⁺/NO₃⁻）为 `SoilState` 模型库存，不注入溶液；硝化产酸 2H⁺/mol N 注入 REACTION（酸化真实）
- `advance_nitrification` 独立函数（升级空间：KINETICS 替换）；k₁=1.0/k₂=0.4 进 constants.py

**L5 电荷平衡修正**：
- 初版"HCO₃⁻ 全量补足 + 总阳离子 5e-5"**实测否决**：pH=5 下 HCO₃⁻ 承载有限，强制补足使 C(4) 暴涨至 0.09 mol/L（PHREEQC 数值失稳）；阳离子 5e-5 与交换相 NaX 失衡触发 pH 碱化漂移
- 落地：HCO₃⁻ 由 pCO₂ 决定（GAS_PHASE 联动）+ `_check_charge_balance` 碳酸真实电荷 + Cl⁻ 兜底 + `total_cation_conc` 保留 2e-3（与交换相自洽）

**实测科学发现**：fertilizer 单层在 k₂=0.4 弱产酸下 AlX₃ 于第 2-3 年耗尽→pH 突升 ~10（根因：Q1+ 矿物压缩 + Q12* 单层排水）；grilling Q1=A 接受为已知局限，k₂=1.0 对照实验证实产酸强度为关键变量；深层修复立项 backlog **L9「矿物缓冲重新校准」**。

**验证**：pytest **102 passed**；E2E natural 30 年 pH 6.46 无突升（AlX₃ 稳定 6.7e4）、单月施肥酸化 5.00→4.35、n_nh4 峰值 649 mol、n_no3 累计 76870 mol。

---

### L9 + L1 — v0.4.0 后续优化（2026-08-14）

**背景**：基于 `.scratch/soil-scm-overview/issues/11-14` spec/工单，经 `/to-spec`+`/to-tickets`+`/tdd` 完成。

**L9 矿物缓冲校准（扫描结论）**：
- MINERAL_SCALE 扫描 0.001→0.2：**增大无效**（0.1-0.2 档耗尽更早、pH 更高），与 Q1+/L2 历史一致（矿物量增大→矿物化加速吸收交换 Al）
- 非晶质 Al(OH)₃(a) 相（2%~20%、SI=0 与欠饱和）：**均无法回补**——矿物化沉淀为"单向 Al 汇"
- **保留非晶质相**（红壤真实组分，natural 基线不变 pH 6.46，103 测试全绿）
- **未根治**：fertilizer 单层 AlX₃ 耗尽；深层修复方向（Al 交换选择性校准 / 矿物化动力学 / 多层+逐层参数）列入后续 backlog
- 完整扫描表见 `docs/reports/V0_3_0_FINAL_REPORT.md` 第六节（L9 证伪链）

**L1 Al 表面络合简化方法（报告）**：
- `docs/analysis/L1_AL_SURFACE_METHOD.md`：Kd_eff(pH)=Kd×f(pH) 简化质量作用式框架、参数表（Kd 文献骨架 + Sverjensky/Karamalidis 交叉验证）、**已知缺点专节**（6 项）、**优化方向专节**（6 项）
- 纯文档交付（实现待独立工单）

**验证**：pytest **103 passed**（新增非晶质相回归测试）；natural 30 年 pH 6.46 不变。

---

### v0.5.0 — 初始状态自洽化三支柱（2026-08-14）

**背景**：经 `/grilling`（Q1-Q7）确定三支柱路线，解决 L9（fertilizer 单层 AlX₃ 耗尽）与初始状态不自洽。

**支柱① 缺口补齐参数化**：
- B 诊断：CEC 缺口（3.8 cmol/kg）全用 Al 补齐（Q12 决策）使自然平衡 pH 4.36 偏离观测 5.0
- 扫描 GAP_AL_FRACTION ∈ {0.3, 0.5, 0.7, 1.0}：**0.3 → 首平衡 pH 4.92（Δ=0.08 最接近观测）**，落地默认值

**支柱② 预平衡（不锚定 pH）**：
- 实测：注入碱被 GAS_PHASE 固定分压 CO₂ 气相缓冲完全吸收（-3000/-10000/-30000 mol 结果相同 pH 3.612），pH 锚定无效
- 落地：`pre_equilibrate` 仅锚定交换离子（<10%）+ 偏离度诊断（pH 自然平衡记录）

**支柱③ L9 交换选择性校准（证伪）**：
- 引擎 EXCHANGE_SPECIES 覆盖 AlX₃ log_k 扫描 {0.41, 2, 5, 10}：**全部 y3 耗尽、pH 突升 ~10**
- 与 ROADMAP 历史（0.41→5.0 无效）一致 → **结构性局限确认**（单层排水 + 盐基置换），建议多层 + 文档记录

**验证**：pytest **113 passed**；支柱①首平衡 pH 4.92；支柱②交换离子锚定 <10%；支柱③证伪链完整记录。

---

## 七、v0.5.1 结构性缺陷审查与 v0.6.0 物理化重构规划（2026-08-18）

> **依据**：《v0.5.1的结构性缺点与物理漏洞.txt》《v0.6.0 优化开发方案.txt》《v0.6.0优化开发具体步骤.txt》《v0.5.3水分平衡闭合.txt》《VGM参数化方案.txt》
> **方法**：源码逐行比对 + `/grill-me` 9 轮决策拷问（2026-08-18）
> **结论**：4 项物理缺陷全部确认存在（证据 §7.1）；重构方案按三阶段定案（§7.2）；9 项技术决策已锁定（§7.3）

### 7.1 物理缺陷比对结论（源码证据）

| # | 缺陷 | 代码证据 | 物理影响 | 状态 |
|---|------|----------|----------|------|
| 1 | Horton 非物理补丁 `surface_coeff` | `src/hydrology.py:73` `available = precip_mm * surface_coeff`（默认 0.75） | 即使入渗能力未触顶也人为强制 25% 降水成径流，破坏质量守恒；表层 pH ~6.9 漂移的直接推手 | ✅ 确认，v0.5.2 解决 |
| 2 | 水桶模型替代达西定律 | `src/hydrology.py:139-143` `space=0.5×sat` + `drain=min(drainable, ksat_cap)` | 初始含水量卡死 50% 饱和度；无基质势/水势梯度，水分只能向下漏、无毛细上升；无法对接 WRF 水势 | ✅ 确认，v0.5.3 解决 |
| 3 | 缺失 ET 与水分平衡闭合 | `LayerCascade.run()`（`hydrology.py:121-151`）仅入渗输入 + 排水/溢出输出，无任何 Sink 项 | 华南 40%~60% 降水未返回大气；土壤长期偏湿 → 高估矿物风化/离子交换速率；陆气耦合能量平衡崩溃 | ✅ 确认，v0.5.3 解决 |
| 4 | 月度平滑抹杀脉冲淋溶 | `main.py:158-163` 场次入渗 `sum()` 后 `run_monthly_multi_layer` 每层每月仅 1 次 PHREEQC 平衡；`generate_rainfall` 的 `events` 只用于 Horton 入渗量 | 一场 50mm 暴雨 vs 10 场 5mm 小雨被等价处理；低估重金属/盐基瞬态淋失峰值（First-Flush 抹平） | ✅ 确认，v0.6.0 解决 |

> 附注：缺陷 4 的精确机制为"`monthly_hydrology` 将场次入渗累加后单次化学平衡"；v0.5.0 已实现**层间**逐层化学平衡，但时间维度仍为月度一次。

### 7.2 三阶段重构计划（已定案）

| 阶段 | 版本 | 内容 | 主要改动文件 | 验收标准 |
|------|------|------|-------------|---------|
| ① | **v0.5.2** | Green-Ampt 表层入渗（废弃 `surface_coeff`）+ `Ksat_surface`/`ksat_drainage` 字段拆分 + `bypass_fraction=0.2` 优先流注入 L2 + 硝化产酸限 L1 | `src/hydrology.py` / `src/config_manager.py` / `src/constants.py` / `src/soil_database.py` / `main.py` / `src/phreeqc_engine.py` | 质量守恒（入渗+径流=降水）；超渗产流自然出现；表层 pH 回落方向正确 |
| ② | **v0.5.3** | VGM 水分特征（三级参数化 + `initial_psi_cm=-100` 田间持水量初始化）+ Feddes ET（Oudin PET）+ LayerCascade 下游接收能力重构 + OM 矿化产 CO₂ + `stored_water→θ/ψ` 状态迁移 | `src/hydrology.py` / `src/climate_forcing.py` / `src/constants.py` / `src/output_writer.py` / `src/initial_condition.py` | 干湿交替出现；水量平衡闭合（AET_mm 输出）；pH 回落 4.5~5.5（需实测标定） |
| ③ | **v0.6.0** | 化学子步长拆分（逐场全量 PHREEQC + `run_event` 接口 + 月末聚合）+ First-Flush 捕获 + Hargreaves PET 升级 | `src/phreeqc_engine.py` / `src/scenario_controller.py` / `src/climate_forcing.py` / `main.py` / `src/output_writer.py` | 脉冲淋失峰值如实输出；长模拟分块断点续跑可行 |

### 7.3 已敲定的技术决策（grill-me 2026-08-18）

| # | 决策点 | 定案 |
|---|--------|------|
| D1 | 版本顺序 | 按改动量/风险从小到大：**v0.5.2 → v0.5.3 → v0.6.0**（与方案文档原顺序相反，工程上更稳妥） |
| D2 | 表层 pH 回落机制 | **三管齐下**：K_s 基质导水率（L1=7.2 cm/day，暴雨 >15mm/h 自然触发超渗产流）+ β 优先流 + 产酸源强化；**不承诺"去系数即回落"**（量级核算：L1 原 Ksat=32mm/h 下单场入渗能力远超典型场次降水，换 Green-Ampt 仍近全入渗） |
| D3 | Ksat 语义 | 拆分双字段：`Ksat_surface=7.2 cm/day`（仅 Green-Ampt 地表入渗）+ `ksat_drainage=[12.0, 1.9, 0.48, 0.05] cm/day`（仅层间排水）；级联改"下游接收能力 min(上下层 ksat_drainage)"（木桶短板）；**ET 前置**于 `LayerCascade.run()` 最前端 |
| D4 | 子步长计算成本 | **逐场全量 PHREEQC**（最精确，无解析近似）；接受 4~12 倍计算量；长模拟用 `run_monthly_step_with_timeout` 分块断点续跑 |
| D5 | PET 数据源 | **Oudin (2005)** 为主（仅需月均温+纬度 φ）+ 固定气候态兜底；`pet_correction_factor` 月度修正（华南夏低冬高偏差）；v0.6.0 升 Hargreaves（补 T_max/T_min）；WRF 耦合后 Penman-Monteith 纯读取 |
| D6 | 优先流 | **注入 L2（犁底层）**，**携带原始降水化学**（非 L1 平衡溶液、非纯水）；`bypass_fraction=0.2` config 开放；旱季 0.30~0.40 / 雨季 0.10~0.15 动态调整列后续小版本 |
| D7 | 产酸源强化归属 | 硝化产酸限 L1 → **v0.5.2**（行为修正，改动小）；温度驱动 OM 矿化产 CO₂ 新模块 → **v0.5.3**（与 ψ/θ 联动） |
| D8 | VGM 参数化 | **三级优先级**：①`layer_overrides` 显式配置（`vgm_theta_r`/`vgm_alpha`/`vgm_n`）②`clay_pct` 连续回归（θ_r=0.01+0.002×clay；α=0.04−0.0006×clay；n=1.5−0.008×clay，Saxton & Rawls 2006 + 红壤修正）③红壤兜底（0.08/0.015/1.25）；`l=0.5` 固定；**初始 θ 废弃 50% 饱和**，改 `initial_psi_cm=-100` 田间持水量正算（L1≈0.81θ_s / L4≈0.88θ_s），θ_s≡porosity |
| D9 | 交付边界 | 本会话仅更新 `ROADMAP.md` + `OPTIMIZATION_PLAN.md`（spec/工单待后续 `/to-spec`+`/to-tickets` 拆分，续 43 起） |

### 7.4 风险与注意事项

- **Ksat 缩小 10 倍连锁**：`ksat_drainage` 缩小时层间排水变慢 → 中层滞水（物理真实：华南红壤雨季上层滞水），由 ET 前置 + 界面通量 min(上/下) 吸收；不能只压表层入渗不顾级联排水
- **Oudin 偏差**：华南夏季低估 10~20%、冬季高估 5~10% → `pet_correction_factor` 月度修正 + 发布前 PET 敏感性扫描（600~1400 mm/yr）
- **既有测试影响**：硝化限 L1 与 4 层 pH 剖面相关断言（168 项中约 4 层分层测试）需同步更新；`surface_coeff` 相关 4 项 config/测试删除或改 Green-Ampt 等价断言
- **`n_layers=1` 护栏**：全程保持单层回退现状（回归护栏不破坏）；`sub_time_step_days` 在水文模式不适用
- **优先流溶质守恒**：β 优先流注入 L2 时必须携带原始降水化学并计入质量平衡核算（Q7 平流守恒口径扩展）
- **科学诚实**：pH 回落 4.5~5.5 为**目标方向**，需结合研究区实测（Ksat/降雨强度/PET）标定验证，不夸大；`error.inp` 落盘/`run_monthly_step_with_timeout` 等既有工程保障全程保留

### 7.5 v0.5.2 落地执行日志（2026-08-18，工单 44~48）

**实施**：`/implement` + `/tdd`（红→绿循环）+ 运行验证 + 文档同步，对照 spec 43。

| 工单 | 内容 | 落地 |
|------|------|------|
| 44 | Green-Ampt 入渗模块 | `src/hydrology.py`：`solve_green_ampt_F`（牛顿迭代）+ `green_ampt_infiltration`（隐式方程，K_s=ksat_surface，ψ_f=150mm，θ_i 可配）；`monthly_hydrology` 逐场 Green-Ampt；删除 `horton_event_infiltration`/`HORTON_DECAY_K_PER_H`；`main._apply_hydrology_month` 去 surface_coeff |
| 45 | Ksat 字段拆分 | `constants.DEFAULT_4LAYER_KSAT=[12,1.9,0.48,0.05]`（排水）+ `DEFAULT_KSAT_SURFACE=7.2`；`SoilProfile`/`LayerOverrideConfig` 新增 `ksat_surface`；config 解析/校验（>0）；`apply_layer_override`/main 内置注入同步 |
| 46 | 优先流 bypass | `SimulationConfig.bypass_fraction=0.2`（0~1 校验）；`_apply_hydrology_month` 返回 `bypass_water_L`（径流×β）；`run_monthly_multi_layer` 对 L2 注入；`_build_phreeqc_input` 按 bypass 水量追加 H2O+降水化学 |
| 47 | 硝化限 L1 | `run_monthly_multi_layer` 对 i>0 设 `skip_nitrification`；`_run_official_step` 跳过 `advance_nitrification`（L2~L4 不推进氮库存/产酸） |
| 48 | 集成+发布 | `SimulationConfig.surface_infiltration_coeff` 移除 + 残留报错（breaking change）；config.yaml/config_example.yaml 同步；`tools/sensitivity_infiltration.py` 扫描变量改 `ksat_surface`；运行验证 + 文档 + 发布 |

**运行验证（2 年 4 层 natural, seed=42）**：

| 指标 | v0.5.1 (Horton+0.75) | v0.5.2 (Green-Ampt) |
|------|----------------------|---------------------|
| 入渗占比 | 75% | **66.2%**（单场能力约 26.4mm，大场次自然产流） |
| 径流占比 | 25%（人为） | **33.8%**（自然超渗产流） |
| 优先流 | — | 径流的 **20%**（256mm/2yr，注入 L2） |
| 质量守恒 | ✓ | ✓（入渗+径流=降水 3786mm） |
| 初始表层 pH | ~6.9 高位 | **4.63**（回落至红壤区间方向） |
| 深层 pH（末月） | — | L2 5.28 / L3 4.43 / L4 3.23（保持酸性） |

**测试**：168 → **178 passed**（Green-Ampt 4 + Ksat 拆分 4 + 优先流 4 + 硝化限 L1 2 + 废弃字段报错 1 − Horton 旧 5 调整）。

**科学诚实记录**：
- 表层 pH 末月仍升至 6.9（碳酸缓冲主导）——**符合 spec 43 声明**：v0.5.2 仅验收"入渗/径流物理方向正确 + 质量守恒"；pH 完全回落依赖 v0.5.3 的 Ks 重标定 + Feddes ET + OM 矿化产 CO₂ 联合作用。
- `surface_infiltration_coeff` 为 breaking change：config 残留显式报错，`tools/sensitivity_infiltration.py` 已改扫 `ksat_surface`（1~15 cm/day）。
