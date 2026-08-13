# WF3 — SURFACE 表面络合可行性调研

**Label:** `wayfinder:research`
**Status:** ✅ closed (2026-08-13, via 本地调研)
**Parent:** 多分层模型与 SURFACE 表面络合（wayfinder:map）

## Question

phreeqc.dat 数据库中 SURFACE 表面络合的可行性与参数边界是什么？

## Resolution — 调研报告

> 调研方法：本地代码库 + `phreeqc.dat`（D:\python\Lib\site-packages\phreeqc\databases\）+ Tipping_Hurley.dat 对比分析。
> 调研日期：2026-08-13

### 1. phreeqc.dat 已定义的表面物种（验收 1 ✅）

**SURFACE_MASTER_SPECIES**（phreeqc.dat L1424-1426）：
```
Hfo_s Hfo_sOH      # 强结合位点 (strong binding site)
Hfo_w Hfo_wOH      # 弱结合位点 (weak binding site)
```

**位点酸碱性质**（Dzombak & Morel, 1990, table 5.7）：
| 反应 | log_k | 说明 |
|------|-------|------|
| Hfo_sOH + H+ = Hfo_sOH2+ | 7.29 | 强位点 pKa1,int |
| Hfo_sOH = Hfo_sO- + H+ | -8.93 | 强位点 pKa2,int |
| Hfo_wOH + H+ = Hfo_wOH2+ | 7.29 | 弱位点 pKa1,int |
| Hfo_wOH = Hfo_wO- + H+ | -8.93 | 弱位点 pKa2,int |

**位点类型与比例**：强:弱 = 1:9（Dzombak & Morel 标准 10%/90%，PHREEQC 惯例在 SURFACE 块用 `-sites` 分别指定密度）。**数据库中未硬编码默认密度**——位点摩尔量完全由输入 SURFACE 块提供。

**已定义的表面络合反应**（完整清单）：

*阳离子（Hfo_s 强位点 + Hfo_w 弱位点各一条，除非注明）*：
- Ca+2 → Hfo_sOHCa+2 (log_k 4.97) / Hfo_wOCa+ (log_k -5.85)
- Sr+2 → Hfo_sOHSr+2 / Hfo_wOSr+ / Hfo_wOSrOH
- Ba+2 → Hfo_sOHBa+2 / Hfo_wOBa+
- Cd+2 → Hfo_sOCd+ / Hfo_wOCd+
- **Zn+2 → Hfo_sOZn+ (log_k 0.99) / Hfo_wOZn+ (log_k -1.99)**
- Cu+2 → Hfo_sOCu+ / Hfo_wOCu+
- Pb+2 → Hfo_sOPb+ / Hfo_wOPb+
- Mg+2 → Hfo_wOMg+（仅弱位点）
- Mn+2 → Hfo_sOMn+ / Hfo_wOMn+
- Fe+2 → Hfo_sOFe+ / Hfo_wOFe+ / Hfo_wOFeOH

*阴离子（弱位点为主）*：
- **磷酸盐（P）：Hfo_wH2PO4 (log_k 31.29)、Hfo_wHPO4- (25.39)、Hfo_wPO4-2 (17.72)——3 个质子化态**
- 硼酸盐：Hfo_wH2BO3
- 硫酸盐：Hfo_wSO4-、Hfo_wOHSO4-2
- 氟化物：Hfo_wF、Hfo_wOHF-
- 碳酸盐：Hfo_wCO3-、Hfo_wHCO3
- 硅酸盐：Hfo_wH3SiO4、Hfo_wH2SiO4-、Hfo_wHSiO4-2

**Al 表面络合：未定义**。phreeqc.dat 中 Al 仅以溶液物种（AlOH+2 + X- = AlOHX2 交换）与矿物相形式存在，**无 Hfo_sAl/Hfo_wAl 表面物种**。

### 2. build_surface() 需要的参数调整（验收 2 ✅）

**当前问题**：`InitialConditionBuilder.build_surface()`（initial_condition.py L394）生成 `Som`（有机质）与 `Hfo`（铁氧化物）两种位点——**两者都不在 phreeqc.dat 的 SURFACE_MASTER_SPECIES 中**（phreeqc.dat 只有 `Hfo_s`/`Hfo_w`），且 SURFACE 块写法 `{stype} {sites}` 后跟 `-sites {sites}` 重复指定位点量（疑似语法冗余）。这就是 OPTIMIZATION_PLAN P3 所述"SURFACE 默认关闭"的根因。

**需要的调整**：
1. **位点名**：`Hfo` → `Hfo_s` + `Hfo_w`（10%/90% 拆分）。
2. **`Som` 移除**：phreeqc.dat 无有机质表面；若启用有机质络合需换用 `Tipping_Hurley.dat` 数据库（含 Fulvate-2/Humate-2 及 WHAM 模型），属更大改动，不在 WF4 默认范围。
3. **位点密度来源**：`FE_OXIDE_SITE_DENSITY = 0.5 mol/kg`（铁氧化物）用于计算 Hfo_s/Hfo_w 总量；再按 10%/90% 拆分为强/弱位点。`specific_area` 可选（-specific_area 参数，非必需）。
4. **SURFACE 块写法**：应改为 `Hfo_s <mol>` + `-sites 1 <density>`（或直接 `Hfo_s <mol>` + `-equilibrate solution`），参考 PHREEQC 标准用法。

**参数配置建议**（初始条件类常量，遵循 Q19 收敛到 `constants.py`）：
```
HFO_SITE_DENSITY = 0.5       # mol/kg 铁氧化物 (现有 FE_OXIDE_SITE_DENSITY)
HFO_STRONG_FRACTION = 0.1    # 强位点占比 (Dzombak & Morel)
```

### 3. 有机质表面位点（验收 2 补充）

- **phreeqc.dat 不支持**有机质表面（无 Fulvate/Humate/Hom/Hfo_s 之外的 master species）。
- **Tipping_Hurley.dat 支持**：含 Fulvate-2、Humate-2（NICA-Donnan）以及完整的 WHAM 腐殖质位点（H_a-H_h 单齿 60% + H_ab-H_ch 双齿 40%），且其 Hfo 表面与 phreeqc.dat 完全一致（Dzombak & Morel）。
- **建议**：WF4 默认**仅启用 Hfo_s/Hfo_w 铁氧化物表面**（与 phreeqc.dat 兼容）；有机质表面列为后续增强（需评估换库 Tipping_Hurley.dat 对现有矿物/交换反应的影响）。
- `OM_SITE_DENSITY = 1.0 mol/kg` 在 phreeqc.dat 路径下**不启用**（无有机质表面物种可挂载）。

### 4. P/Zn/Al 吸附增强的实际范围（验收 3 ✅）

| 元素 | 增强程度 | 说明 |
|------|---------|------|
| **P（磷酸盐）** | 🟢 **显著增强** | 3 个质子化态（H2PO4/HPO4/PO4 各 log_k 31.29/25.39/17.72），弱位点吸附，对 pH 敏感 |
| **Zn** | 🟢 **显著增强** | 强位点 log_k 0.99 + 弱位点 log_k -1.99，双位点吸附 |
| **Al** | 🔴 **无增强** | phreeqc.dat **无 Al 表面物种**——需自行扩展数据库（新增 Hfo_sOH + Al+3 = Hfo_sOAl+2 + H+ 等反应与 log_k），文献参考 Dzombak & Morel / Karamalidis & Dzombak (2010) |

**其他自动生效的吸附**：Ca/Mg/K 等阳离子弱吸附（影响盐基离子滞留）、SO4/F/CO3 阴离子吸附（影响酸沉降缓冲）、Si 吸附。

### 5. 收敛风险与缓解措施（验收 4 ✅）

| 风险 | 说明 | 缓解措施 |
|------|------|---------|
| **收敛窗口变窄** | SURFACE 增加非线性（表面电荷随 pH 变化），PHREEQC 迭代可能更难收敛 | 已有 `KNOBS -iterations 100`；可增至 200；`-tolerance` 放宽至 1e-10 |
| **位点密度敏感性** | Hfo_s/Hfo_w 位点量若过大，表面吸附主导平衡，可能抑制矿物缓冲 | 以 `FE_OXIDE_SITE_DENSITY=0.5 mol/kg` × 铁氧化物质量计算，先小规模验证 |
| **矿物量折中交互** | 现有 MINERAL_SCALE=0.001 已压缩矿物缓冲；SURFACE 吸附与矿物平衡竞争 | WF5 集成验证时对比开/关 SURFACE 的 pH 曲线 |
| **多层 × SURFACE 组合** | 4 层每层一个 SURFACE 块，计算量 ×4 | 先单层验证 SURFACE，再集成多层（WF5） |
| **数据库扩展风险** | 若需 Al 表面物种，扩展 phreeqc.dat 需保证 log_k 文献正确性 | Al 表面络合列为独立后续工单，不阻塞 WF4 默认范围 |

## 结论

- **技术上可行**：phreeqc.dat 原生支持 Hfo_s/Hfo_w 双位点表面络合，P/Zn 吸附描述丰富。
- **建议 WF4 范围**：仅启用 Hfo_s/Hfo_w 铁氧化物表面（`build_surface()` 改造 + 位点密度参数化 + SURFACE 块写法修正）；有机质表面与 Al 表面络合列为后续独立工单。
- **关键缺口**：Al 表面络合在 phreeqc.dat 中**不可用**（项目最关心的 Al 吸附需扩展数据库），这是 WF4 前需与用户确认的重要决策。

## 验收确认

- [x] 输出 phreeqc.dat 中 Hfo_s/Hfo_w 的完整定义摘要（位点类型/密度/反应）— 见第 1 节
- [x] 明确 `build_surface()` 需要哪些参数调整才能在 phreeqc.dat 下运行 — 见第 2 节
- [x] 明确 P/Zn/Al 吸附增强的实际范围 — 见第 4 节
- [x] 列出 SURFACE 启用的收敛风险与缓解措施 — 见第 5 节

**决策记录**：WF3 调研完成。WF4（SURFACE 启用决策与实现）阻塞已解除，其核心决策点包括：① 是否仅启用 Hfo_s/Hfo_w（推荐）；② Al 表面络合是否需要扩展数据库（独立工单）。

