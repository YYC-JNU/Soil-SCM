# WF4 — SURFACE 表面络合启用决策与实现

**Label:** `wayfinder:grilling` + `wayfinder:task`
**Status:** ✅ closed (2026-08-13, via /implement + /code-review)
**Parent:** 多分层模型与 SURFACE 表面络合（wayfinder:map）

## Question

基于 WF3 的调研结果，决定并实现 SURFACE 表面络合的启用方案。

## Resolution — 决策汇总（2026-08-13 /grilling 确认）

| # | 决策 | 选定方案 |
|---|------|---------|
| Q1 | 完整启用 Hfo+有机质的数据需求 | 事实调研确认：交换物种/矿物相/Hfo 两库（phreeqc.dat 与 Tipping_Hurley.dat）兼容；需新增 WHAM 位点密度 + Fulvate/Humate 浓度；**Al 表面两库均缺** |
| Q2 | Al 表面络合处理 | **调整为推迟**（四源查证：phreeqc.dat/minteq.v4/wateq4f/RES3T 均无 Al-Hfo 标准数据，属研究空白）；Al 表面扩展列为独立工单 |
| Q3 | 数据库策略 | **分阶段**：阶段一 `phreeqc.dat`（已含 Hfo_s/Hfo_w，无需自定义库）；阶段二（后续）`Tipping_Hurley.dat` + 自定义扩展（独立工单） |
| Q4 | 有机质表面是否纳入 WF4 | **A — 不纳入**（WHAM/Fulvate 列为独立后续工单） |

## Resolution — 实现完成说明

**实现内容**（阶段一：Hfo_s/Hfo_w 铁氧化物表面）：

1. **`src/constants.py`**：新增 `HFO_SPECIFIC_AREA=600.0`（比表面 m²/g）、`HFO_STRONG_SITE_DENSITY=8.35e-4`、`HFO_WEAK_SITE_DENSITY=1.67e-2`（位点密度 mol/m²，Dzombak & Morel 1990）。
2. **`src/initial_condition.py`**：`build_surface()` 重构为返回铁氧化物表面积（`{'area_m2': ...}`），面积 = 质量 × 比表面 × MINERAL_SCALE（与矿物量折中一致）；移除 Som/OM_SITE_DENSITY/FE_OXIDE_SITE_DENSITY。
3. **`src/phreeqc_engine.py`**：`SoilState` 加 `surface` 字段；`__init__` 加 `enable_surface`（默认 False）；`build_initial_state` 填充 surface；`_build_phreeqc_input` 生成 SURFACE 块（PHREEQC 标准语法：`{name} {面积} {比表面} {位点密度}` + `-equilibrate with solution 1`）；`_parse_official_output`/`_run_simplified_step` 保留 surface（状态连续）。
4. **`src/config_manager.py`** + **`main.py`** + **`config.yaml`**：`enable_surface` 配置贯通（默认 false）。
5. **`tests/test_surface.py`**：7 个测试（面积构建/输入含 SURFACE/默认关闭回归/初始状态/收敛无降级/P-Zn 吸附）。

**测试验证**：完整测试套件 **78 passed**（原 71 + 新增 7）。
**E2E 验证**：`enable_surface: true` 完整模拟 `[SUCCESS]`，无永久降级；施肥后 P/Zn 被铁氧化物强吸附（红壤磷固定现象）。

**代码审查**：`/code-review` 双轴通过——Standards 0 硬性发现（3 判断性观察：area_m2 设计/P-完全吸附物理性/MINERAL_SCALE 缩放，均不阻塞）；Spec 5 条验收全达成。

**Al 表面络合**：四源查证（phreeqc.dat/minteq.v4.dat/wateq4f.dat/RES³T）确认无 Al³⁺-Hfo 标准表面络合数据——研究空白，需独立工单（参考 Karamalidis & Dzombak 2010 Gibbsite 数据或自建实验）。

**阻塞 WF5 已解除**（WF5 阻塞于 WF2 + WF4，现均完成）。


