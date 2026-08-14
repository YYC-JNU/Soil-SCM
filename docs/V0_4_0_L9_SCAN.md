# L9 MINERAL_SCALE 参数扫描记录（v0.4.0）

> **日期**：2026-08-14
> **目标**：解决 fertilizer 单层长期 AlX₃ 耗尽→pH 突升（Q12* 残留 + Q1+ 矿物压缩）
> **工单**：`.scratch/soil-scm-overview/issues/12-L9-mineral-scale-calibration.md`

---

## 1. MINERAL_SCALE 参数扫描（fertilizer 单层 5 年）

| MINERAL_SCALE | pHmax | AlX₃min (mol) | 耗尽年 | 结论 |
|---------------|-------|----------------|--------|------|
| 0.001（基准） | 10.47 | 0.0 | y2 | FAIL |
| 0.005 | 10.41 | 0.0 | y3 | FAIL |
| 0.010 | 10.38 | 0.0 | y3 | FAIL |
| 0.050 | 10.47 | 0.0 | y2 | FAIL |
| 0.100 | 10.52 | 0.0 | y2 | FAIL |
| 0.200 | 10.60 | 0.0 | y2 | FAIL |

**结论**：单纯增大 MINERAL_SCALE **无效**，甚至更糟（0.1-0.2 档耗尽更早、pH 更高）。
与 Q1+/L2 历史发现一致：**矿物量增大 → 矿物化加速吸收交换 Al → AlX₃ 更早耗尽**。
（Q1+ 记录"反直觉实验：矿物×10 反而加速 Al 耗尽"）

## 2. 非晶质 Al(OH)₃(a) 缓冲相实验（MINERAL_SCALE=0.001 保持）

| 方案 | pHmax | AlX₃min | 耗尽年 | 结论 |
|------|-------|---------|--------|------|
| 无非晶质（基准） | 10.47 | 0.0 | y2 | FAIL |
| 非晶质 2%（SI=0 平衡） | 10.37 | 0.0 | y2 | FAIL |
| 非晶质 5%（SI=0） | 10.37 | 0.0 | y2 | FAIL |
| 非晶质 10% | 10.40 | 0.0 | y2 | FAIL |
| 非晶质 20% | 10.47 | 0.0 | y2 | FAIL |
| 非晶质 5%（SI=-0.3 欠饱和） | 10.70 | 0.0 | y2 | FAIL |

**结论**：非晶质 Al(OH)₃(a) 相（SI=0 平衡与欠饱和）均**无法回补**交换 Al。
根因：矿物化沉淀是"单向 Al 汇"（L2 记录），非晶质溶解的 Al³⁺ 被同一汇吸收
或被排水带走，无法进入交换位点。

## 3. 基线影响验证

- 完整测试套件 **102 passed**（非晶质相加入不破坏测试）
- **natural 30 年 pH 6.46、AlX₃ 67421 mol 稳定**——与非晶质相加入前完全一致（无副作用）

## 4. 结论与决策

1. **L9 参数扫描与非晶质相均无法根治 fertilizer 单层 AlX₃ 耗尽**——深层机制未解。
2. **保留非晶质 Al(OH)₃(a) 相**（`AMORPHOUS_ALOH3_MASS_FRACTION=0.02`）：
   - 是红壤真实矿物组分（非晶质铝氧化物普遍存在），提高矿物学真实性
   - natural 基线不变（pH 6.46）、测试全绿、无副作用
   - 提供部分 Al 源（虽 fertilizer 下不足）
3. **深层修复方向**（后续立项）：
   - **Al 交换选择性校准**：调整 AlX3 交换常数（Gapon log_k），抑制盐基置换
   - **Al 矿物化动力学**：抑制矿物沉淀吸收交换 Al 的单向汇（KINETICS）
   - **多层 + 逐层参数（L6）**：多层已验证可推迟耗尽，配合真实剖面矿物分布
   - 建议：fertilizer 情景科学应用当前使用多层（n_layers≥4）+ 记录局限

## 5. 影响文件

- `src/constants.py`：`AMORPHOUS_ALOH3_MASS_FRACTION=0.02`、`AMORPHOUS_ALOH3_MOLAR_MASS=78.0`
- `src/initial_condition.py`：`build_minerals()` 添加非晶质 Al(OH)₃(a) 相
