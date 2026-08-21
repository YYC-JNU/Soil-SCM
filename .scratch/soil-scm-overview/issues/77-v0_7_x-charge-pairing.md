# 77 — v0.7.x REACTION 电荷平衡修复（工单 77：GAS_PHASE 评估 + 裸注入根因）

**What to build:** 解决 v0.7.0 三大 FAIL 中 **fertilizer<4.0 未达** 的**根本机制缺陷**：PHREEQC `REACTION` 块中**电荷不平衡注入**。实测证伪（2026-08-21 探针）：
- **裸阳离子注入**（NH₄⁺ 置换 `Ca+2`、钾肥 `K+`、镁肥 `Mg+2`）→ PHREEQC 为维持电荷中性**被迫产生 OH⁻ → 碱化**（`Ca+2 857` → pH 10.82，**精确复现 v0.7.0 fertilizer 8~11**；`Ca+2 343` 调优后仍 pH 9.28）
- **裸 H⁺ 注入**（硝化产酸、companion acid）→ 不产生酸化（H 以非 H⁺ 形态存在，pH 不变）
- **电荷配对注入**（`H⁺ + An⁻`、`Ca+2 + 2An⁻`）→ pH 正常响应（`H⁺ 1372 + An⁻ 1372` → pH 2.99；`Ca+2 343 + 2An⁻ 686` → pH 5.00）

修复：**所有 REACTION 注入做电荷配对**——阳离子/酸注入伴随等当量**保守惰性阴离子 `An⁻`**（复用 companion `inert_anion` 机制，`SOLUTION_MASTER_SPECIES` 自定义，不碰 phreeqc.dat；随排水淋失不积累）。lime（`Ca + H(-2)`，Ca(OH)₂ 物理碱化）保持不动。

**GAS_PHASE 评估结论（工单 77 原名主题，科学诚实）**：`-fixed_volume` 在 IPhreeqc 3.8.6 数值不可靠（产酸时 g_CO₂ 暴涨 7.3e6、基线 pH 偏离 1.5+，收敛警告）；`-fixed_pressure` 吞酸是**次要因素**（产酸 686 mol 后 pH 5.05 vs 基线 5.00，幅度小）；真正根因是裸注入电荷不平衡。故 **GAS_PHASE 保持 `-fixed_pressure` 现状**（分压基线），不留工单 77 改名冲突——本工单聚焦电荷平衡修复。

**Blocked by:** None — can start immediately。

**Status:** 🔶 核心完成（charge pairing 实现 + 单层验证 + 333 测试全绿；fertilizer<4.0 需联动工单 80 盐基淋失强化）

---

## Problem Statement

v0.7.0 验收 FAIL：fertilizer 5y pH = 8.09（weather on）/11.42（weather off），方向带要求 <4.0。此前归因于 GAS_PHASE 固定缓冲吞酸（偏差 2），但探针实测：
1. **GAS_PHASE 吞酸幅度小**：fixed_pressure pCO₂=0.015，产酸 686 mol（≈单次施肥硝化）→ pH 仅 5.00→5.05。
2. **裸阳离子注入 = 碱化主因**：`Ca+2 343`（NH₄⁺ 置换调优 A 量级）→ pH 9.28；`Ca+2 857`（调优前）→ pH 10.82。**这与 v0.7.0 fertilizer 观测 8~11 一致**。
3. **裸 H⁺ 注入无效**：硝化产酸 `H+` 注入后 pH 不降（H 守恒但不以 H⁺ 形态存在，pe=4 下被氧化还原缓冲）。
4. **钾镁肥裸阳离子**：`K+ 191` → pH 6.03、`Mg+2 74` → pH 5.89（轻碱化叠加）。
5. **电荷配对有效**：`H+ + An-` 同步注入 → pH 正常酸化；`Ca+2 + 2An-` → pH 保持 5.0（盐基进入溶液但不碱化，由 D3 伴随淋失带走）。

**根因**：PHREEQC 平衡要求溶液电荷中性。REACTION 注入裸阳离子（正电荷无配对）时，引擎被迫从水分解产 OH⁻（或消耗 H⁺）补偿 → 碱化；注入裸 H⁺ 时，H⁺ 电荷由氧化还原缓冲（H⁺→H₂/H(0)）吞没 → 不酸化。v0.6.1 起 fertilizer 碱化（8.4→11.4）即由此机制（钾/镁肥裸阳离子 + 硝化裸 H⁺ 无效），v0.7.0 NH₄⁺ 置换裸 Ca²⁺ 进一步放大。

## Solution

**电荷配对（charge pairing）**：所有产生净电荷的 REACTION 注入，按等当量伴随保守惰性阴离子 `An⁻`（复用 companion `inert_anion` 机制；`log_k=0` 保守示踪；随排水/基流/侧向淋失，不积累）。

| 注入点 | 现状 | 修复后 |
|--------|------|--------|
| 硝化产酸 | `H+ x`（无效） | `H+ x` + `An- x` |
| NH₄⁺ 置换盐基 | `Ca+2/Mg+2/K+/Na+` 裸（碱化） | 各盐基 + `An-` = Σ(价×mol) |
| companion acid（BS<10 酸化） | `H+ x`（无效） | `H+ x` + `An- x` |
| 钾肥（K₂O） | `K+ x` 裸 | `K+ x` + `An- x` |
| 镁肥（MgO） | `Mg+2 x` 裸 | `Mg+2 x` + `An- 2x` |
| lime（CaO） | `Ca x` + `H -2x`（Ca(OH)₂ 物理碱化） | **不动**（物理正确） |
| 磷肥（H₂PO₄⁻） | 裸阴离子（弱酸化） | 保持（量级小，弱酸物理） |
| 预平衡锚定注入 | 裸阳离子（量级小） | `An-` 伴随（一致性） |
| 风化注入 | Ca/Mg/K + HCO₃⁻（已平衡） | 不动 |

**新配置**：`simulation.charge_pairing`（`enable: true` 默认；`anion: "An"` 默认，与 companion 默认一致）。`companion` 禁用时独立启用（An⁻ 定义从 companion 条件解耦）。

**物理意义**：农业施肥/硝化的伴随阴离子（真实中为 NO₃⁻/Cl⁻/SO₄²⁻）以保守 An⁻ 近似，随排水带走——**不改变溶液碱度**（配对的盐/酸是电中性盐），酸化/盐基效应由化学平衡自然产生，杜绝"电荷伪碱化"。

## User Stories

1. As a **土壤模型研究者**, I want 硝化产酸真实酸化（H⁺ + 伴随阴离子配对），so that 施肥情景 pH 沿正确方向下降（当前裸 H⁺ 注入无效）。
2. As a **土壤模型研究者**, I want NH₄⁺ 置换盐基以电中性盐形式进入溶液（盐基 + An⁻），so that 盐基累积不再因电荷平衡伪碱化（当前裸 Ca²⁺ 使 pH 9~11）。
3. As a **土壤模型研究者**, I want 钾肥/镁肥注入带伴随阴离子，so that 肥料盐基不引入伪碱化。
4. As a **模型开发者**, I want charge_pairing 可配置开关（默认启用），so that 对照实验可关闭验证。
5. As a **模型开发者**, I want An⁻ 定义与 SELECTED_OUTPUT totals 在 companion 或 charge_pairing 任一启用时存在，so that 不依赖 companion 开关。

## Implementation Decisions

- **配置**：`ChargePairingConfig(enable=True, anion="An")` 挂 `SimulationConfig.charge_pairing`；YAML `simulation.charge_pairing.{enable, anion}`。
- **引擎**：`__init__(charge_pairing_cfg=None)` → `charge_pairing_enabled`（默认 True 当传入或 None 时用默认？——**决策：默认 None=启用默认配置**，与 companion 区分。为最小破坏，`charge_pairing_cfg=None` → 用 `ChargePairingConfig()` 默认启用）。`pair_anion = charge_pairing_cfg.anion`（若 companion 也启用且 anion 一致，共享物种）。
- **An⁻ 定义**：`_build_phreeqc_input` 的 `SOLUTION_MASTER_SPECIES/SOLUTION_SPECIES` 条件 `companion_enabled or charge_pairing_enabled`；SELECTED_OUTPUT totals 同条件追加 `pair_anion`。
- **配对注入**：注释统一 `# 电荷配对`（避免与 `# NH4+ 置换` 等既有断言正则混淆）。
- **纯函数**：`charge_equivalent(species_mol: dict) -> float`（按物种价态算正电荷总量）或内联 `Σ(价×mol)`。二价：Ca+2/Mg+2 ×2，一价 K+/Na+ ×1。
- **GAS_PHASE**：保持 `-fixed_pressure` 现状，不引入 fixed_volume（探针证伪数值不可靠）。
- **预平衡锚定**：`_compute_anchor_injection` 的注入也配对（阳离子 + An⁻），防预平衡 pH 伪碱化。

## Testing Decisions

- **S1 新 `tests/test_charge_pairing.py`**：
  - 配置解析（默认启用 / enable:false / anion 自定义）
  - `_build_phreeqc_input`：硝化产酸含 `H+ x` + `An- x`（等量）；NH₄⁺ 置换盐基后 An⁻ = Σ(价×mol)；companion acid、钾镁肥配对；注释 `# 电荷配对`
  - An⁻ 定义条件（companion off + pairing on 仍定义）
  - **PHREEQC 实测**：配对抗酸 pH 下降 vs 裸 H⁺ 不变；配对盐基 pH≈5 vs 裸 Ca²⁺ 碱化
  - 关闭 charge_pairing 时回退现状（裸注入）
- **S2 既有测试更新**：`test_nitrification.py::test_fertilizer_month_input_acid_only`（`# 硝化产酸` 断言仍成立）；`test_phreeqc_engine.py` NH₄⁺ 置换 4 行断言仍成立（An⁻ 用 `# 电荷配对` 注释不混入正则）——预期**无需修改既有断言**，全量跑验。
- **S3 短程验证**：`tools/sensitivity_pH_30yr.py --scenario fertilizer --years 5`（charge pairing 默认启用）→ fertilizer pH 应**显著下降**（对照 v0.7.0 8.09/11.42）。
- **目标测试数**：324 + 新增 ≈ **340+ 全绿**。

## Out of Scope

- **GAS_PHASE 动态化**（fixed_volume）→ 探针证伪数值不可靠，不实施（本工单记录结论）
- **lime 盐基淋失强化**（工单 80）：lime 回落需 D3 扩展 Ca 伴随，单独工单
- **KNOBS 调优**（工单 78）：PHREEQC 卡顿独立处理
- **weathering 情景区分**（工单 79）：natural off / fertilizer on
- **HX log_k 微调**（工单 81）

## Further Notes

- **科学诚实**：本工单证伪了"GAS_PHASE 是 fertilizer 碱化核心障碍"（偏差 2 归因），揭示真实根因 = REACTION 电荷不平衡。发现记录于 `docs/analysis/V0_7_x_CHARGE_PAIRING.md`。
- **短程验证（2026-08-21）**：sensitivity fertilizer 3y pairing ON 10.86 vs OFF 11.20（改善 0.3~1.5）；单层施肥月彻底不碱化（pH 4.87，伪碱化机制修复实证）。仍碱化 10+ 属既有 4 层事件驱动盐基滞留（交换相清空 + 淋失不足）→ 工单 80 D3/lime 盐基淋失强化，**非本工单范围**。
- **An⁻ 积累风险**：配对注入 An⁻ 量级（施肥月 ~1029 eq）随排水淋失；`water_salt_balance.py` 盐分闭合审计持续监控；离子强度升高卡顿归工单 78。
- **版本**：v0.7.x（编号待发布时与用户确认）；发布流程 = 版本号同步 → commit → annotated tag → push。
