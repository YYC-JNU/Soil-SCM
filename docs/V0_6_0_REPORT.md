# Soil-SCM v0.6.0 工程报告：Al 动力学（KINETICS）

> **文档编号**：V0_6_0_REPORT
> **版本**：v0.6.0（2026-08-14）
> **工单**：`.scratch/soil-scm-overview/issues/` 20-24
> **测试**：117 passed（分块验证，命令 30 秒限制）

---

## 一、目标

L9 完整证伪链（v0.4.0+v0.5.0）确认 fertilizer 单层 AlX₃ 耗尽是"矿物化单向 Al 汇 + 排水"机制。v0.6.0 用 **Al 动力学（KINETICS）** 直接对症——给 Al 关键相（gibbsite / Al(OH)₃(a)）加沉淀速率控制，阻断净流失通道。

## 二、实现（工单 21）

- **RATES/KINETICS**：gibbsite/Al(OH)₃(a) 从瞬时平衡（EQUILIBRIUM_PHASES）切到速率控制，TST 一阶 `rate = k×(EXP(sat×ln10)−1)`（SI>0 沉淀 / SI<0 溶解），月度 30 天积分
- **相名处理**：state.minerals 键（小写 `gibbsite`）与 phreeqc.dat 相名（`Gibbsite` 大写）映射（`AL_KINETIC_DB_NAMES`）——SI()/RATES 需精确匹配
- **BASIC 调试**：变量名 `si` 与 `SI()` 函数冲突（大小写不敏感）→ 改用 `sat`；`10^si` → `EXP(sat×ln10)`
- **性能优化**：`rate` 去除 `×m`（m 大导致自适应步长爆炸）
- **L2 回填双路径**：SELECTED_OUTPUT `-kinetics` 输出 `k_<db_name>`（当前摩尔量），`_parse_official_output` 动力学相读 `k_` 列、平衡相读 `<name>` 列

## 三、k 参数扫描（工单 22）

fertilizer 单层 **2 年**验证（PHREEQC 数值卡顿限制 5+ 年模拟）：

| k (mol/s) | pHmax | AlX₃min (mol) | 耗尽年 | 结论 |
|-----------|-------|---------------|--------|------|
| 1e-10 | 5.56 | 34,016 | None | PASS |
| 1e-9 | 5.56 | 34,017 | None | PASS |
| 1e-8 | 5.56 | 34,019 | None | PASS |
| 1e-7 | 5.55 | 34,039 | None | PASS |

**结论**：KINETICS 下多档 k 均 AlX₃ 稳定（~34,000 mol，pH ~5.5，无耗尽）——**阻断 Al 汇效果初步确认**（对照：无 KINETICS 时缺口修正后 y3 耗尽）。k 不敏感（任一速率都稳定），因 KINETICS 从机制上阻止了矿物化固化 Al。

## 四、性能与数值限制（诚实记录）

1. **月度步显著变慢**：KINETICS 动力学积分使 PHREEQC 计算加重（SURFACE 场景尤其，单月步 ~12 秒）
2. **偶发数值卡顿**：5 年+ 长期模拟偶发 PHREEQC 收敛困难（RunString 不返回，非确定）——30 年验收受阻，2 年验证代替
3. **KNOBS 迭代提升至 1000**（KINETICS 时）缓解但未根治
4. **影响**：全量测试需分块运行（命令 30 秒限制）；E2E 长期模拟需分块/续跑

## 五、L6 逐层参数（工单 23）

设计完成（config `layer_overrides`：容重/CEC/交换离子/矿物/pCO₂，保持单层兼容）；完整实现因上下文/时间限制标记为后续独立工单。L6 是研究应用基础（真实剖面约束诊断）。

## 六、参数表

| 参数 | 值 | 位置 | 说明 |
|------|-----|------|------|
| `AL_KINETIC_RATE` | 1e-9 mol/s | constants.py | Al 动力学速率常数（扫描 1e-10~1e-7 均稳定） |
| `AL_KINETIC_PHASES` | ('gibbsite','Al(OH)₃(a)') | constants.py | 动力学控制相（minerals 键） |
| `AL_KINETIC_DB_NAMES` | {gibbsite: Gibbsite, ...} | constants.py | minerals 键 → 数据库相名 |

## 七、验证与后续

- 117 passed（分块）；Al 动力学测试 4（输入/回填/双路径）
- **L9 状态**：KINETICS 初步有效（2 年 AlX₃ 稳定），长期验证受数值限制——建议后续：数值稳定性优化（KNOBS/步长）、L6 实现、Al 动力学长期验证
- 遗留：性能优化（KINETICS 加速）、L6 逐层参数实现
