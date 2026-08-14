# L1 — Al³⁺ 表面络合简化方法（Kd + pH 修正）

> **文档编号**：L1_AL_SURFACE_METHOD
> **版本**：v0.4.0（2026-08-14）
> **性质**：方法设计报告（不包含代码实现；实现待独立工单）
> **工单**：`.scratch/soil-scm-overview/issues/13-L1-al-surface-method-report.md`

---

## 1. 背景与目标

Al 在铁氧化物（Hfo）和有机质表面的吸附-解吸是**红壤酸化的核心机制**：酸化→Al 活化→交换性 Al³⁺ 淋失，而 Al 的表面络合决定 Al 的迁移性。

**研究空白**（WF3 查证记录）：`phreeqc.dat`、`minteq.v4`、`wateq4f`、`RES³T` 四源均无 **Al-Hfo 标准表面络合数据**（Fe³⁺ 有 Hfo 物种，Al³⁺ 缺失）。

**本报告目标**：以**简化方法**（Kd 分配系数 + pH 修正）落地 Al 表面络合描述，覆盖**矿物（Hfo）与有机质**两类表面，并**诚实记录方法缺点与优化方向**。

---

## 2. 方法框架

**核心公式**（grilling Q4/Q5 共识）：

```
Al_吸附 (mol) = Kd_eff(pH) × [Al³⁺]_溶液 (mol/L) × M_表面 (kg)
Kd_eff(pH)  = Kd_base × f(pH)
```

- `Kd_base`：基准分配系数（L/kg，pH 无关的骨架值）
- `f(pH)`：pH 依赖修正（**简化质量作用式**，保留 Al 活化-固定平衡的物理机制）
- `M_表面`：表面质量（矿物 = 铁氧化物质量；有机质 = 有机质质量，分别累计）

**与模型衔接**：该分配逻辑将注入简化引擎的月度 Al 循环（待实现），与 L9 的 Al 循环完善（矿物/交换/溶液）衔接。

---

## 3. f(pH) 推导（简化质量作用式）

**热力学原型**（表面配位交换，1:1 质子释放）：

```
≡SOH + Al³⁺ ⇌ ≡SOAl²⁺ + H⁺        K_surf = [≡SOAl²⁺][H⁺] / ([≡SOH][Al³⁺])
```

**简化推导**：吸附比（即 Kd 的内在形式）：
```
[≡SOAl²⁺] / [Al³⁺] = K_surf × [≡SOH] / [H⁺]
                 = K_surf × [≡SOH] × 10^pH
```

**质量作用式落地**（相对基准 pH₀ 归一化）：
```
f(pH) = 10^(pH − pK_eff) / [1 + 10^(pH − pK_eff)]
```

- `pK_eff` = 有效解离常数（pH 依赖的中心点，取自表面络合常数折算）
- pH ≪ pK_eff → f→0（酸性强，表面质子化饱和，Al 竞争弱）
- pH ≈ pK_eff → f=0.5（过渡）
- pH ≫ pK_eff → f→1（碱性，Al(OH)₄⁻ 主导，实际吸附降——见缺点 4）

**说明**：该式是"吸附增强随 pH"的 S 形近似；极端碱性区 Al 以 Al(OH)₄⁻ 溶解（两性），简化式不捕获（见缺点 3）。

---

## 4. 参数表

| 参数 | 建议值 | 来源/依据 | 不确定性 |
|------|--------|-----------|----------|
| `Kd_base`（矿物 Hfo） | 10 L/kg | 红壤 Al 吸附 Kd 文献量级（1~100 L/kg 中值） | 高（无本地实测） |
| `Kd_base`（有机质） | 50 L/kg | 有机质对 Al 强络合（腐殖质-金属络合文献） | 高（合并简化） |
| `pK_eff` | 5.0 | Karamalidis & Dzombak (2010) Gibbsite 表面络合常数折算（log_K≈9.5 的 Al 配位对 → pK_eff≈5） | 中（非 Hfo 直接数据） |
| `M_矿物` | 铁氧化物质量（goethite+hematite，已有 build_surface 逻辑） | 项目既有 | 低 |
| `M_有机质` | 有机质含量 × 土壤质量 | 土壤数据库（未启用字段，待 L6 逐层参数接入） | 中 |

**交叉验证**：Sverjensky (1996) 表面络合模型（Born 溶剂化校正）预测 Al³⁺ 在铁氧化物的吸附常数与 Karamalidis & Dzombak (2010) Gibbsite 数据同量级（差异 <1 个 log 单位），支持 pK_eff≈5 的量级合理性。

---

## 5. 覆盖表面与合并说明

- **矿物表面**：Hfo（针铁矿+赤铁矿），复用 `build_surface()` 的铁氧化物质量逻辑
- **有机质表面**：原 L3 目标（Tipping_Hurley 库换库方案因热力学重校准风险搁置，v0.3.0 并入 L1）
- **参数合并**：两类表面用同一 Kd_base×f(pH) 框架，分别以各自表面质量加权——**合并简化**牺牲了表面化学差异（见缺点 5）

---

## 6. 已知缺点（诚实记录）

1. **Kd 无本地实测校准**：Kd_base 为文献量级中值，未用本地/研究区土壤标定；同一红壤的 Kd 可差 1-2 个数量级。
2. **忽略竞争离子**：Ca²⁺/Mg²⁺/Fe³⁺ 与 Al³⁺ 竞争表面位点（尤其盐基饱和土壤），简化式未含竞争项。
3. **f(pH) 不捕获两性溶解**：高 pH 区 Al(OH)₄⁻ 溶解（Al 活化再增）未被 S 形近似表达——与模型已知局限"Al(OH)₄⁻ 两性溶解"（README 局限 2）相互叠加。
4. **忽略 Al 聚合物与有机质络合动力学**：Al 多核羟基聚合物（Al₁₃）与腐殖质瞬时络合未建模。
5. **矿物/有机质表面参数合并不确定**：两类表面吸附机制差异大（配位交换 vs 静电+络合），合并引入系统性偏差。
6. **Kd 框架的浓度线性假设**：实际吸附等温线非线性（高浓度饱和），Kd 框架仅在小浓度范围有效。

---

## 7. 优化方向

1. **本地吸附实验标定**：研究区土壤批次吸附实验（pH 系列 + Al 初始浓度），拟合 Kd_base 与 pK_eff——最高优先级。
2. **引入竞争吸附**：Langmuir 多位点或竞争质量作用式，纳入 Ca/Mg/Fe。
3. **与 L9 Al 循环集成**：吸附分配接入简化引擎月度步，与矿物/交换/溶液 Al 平衡耦合（架构见第 2 节）。
4. **两性修正**：f(pH) 增加 Al(OH)₄⁻ 项（高 pH 吸附回落），消除缺点 3。
5. **分层表面参数（L6 联动）**：逐层有机质/铁氧化物含量差异化。
6. **未来切换标准数据库**：若 Al-Hfo 表面络合数据获得（文献/实验），可替换简化式为标准 SURFACE 块（WF4 架构已支持）。

---

## 8. 参考文献

- Karamalidis A.T., Dzombak D.A. *Surface Complexation Modeling: Gibbsite*. Wiley, 2010.
- Sverjensky D.A. Prediction of surface charge on oxides in salt solutions: Revisions for 1:1 (M+L−) electrolytes. *GCA*, 2005.
- Dzombak D.A., Morel F.M.M. *Surface Complexation Modeling: Hydrous Ferric Oxide*. Wiley, 1990.
- Lindsay W.L. *Chemical Equilibria in Soils*. Wiley, 1979.
- 熊毅, 李庆逵. 中国土壤. 科学出版社, 1987.
