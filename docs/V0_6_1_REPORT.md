# Soil-SCM v0.6.1 工程报告：KINETICS 回退与证据链

> **文档编号**：V0_6_1_REPORT
> **版本**：v0.6.1（2026-08-14）
> **性质**：回退记录 + 实验证据链（科学诚实）
> **测试**：115 passed（全量，回退后性能恢复 ~4 秒）

---

## 一、回退原因（摘要）

v0.6.0 引入的 Al 动力学（KINETICS）方案被**实验证据否定**：把 gibbsite/Al(OH)₃(a) 从瞬时平衡（EQUILIBRIUM_PHASES）切到速率控制（RATES/KINETICS）后，因速率常数过小（1e-9 mol/s）**冻结了矿物**，切断了 L2 矿物演化回补通道，导致 fertilizer 单层 AlX₃ 耗尽**反而提前**（y1 m7 vs 平衡相 y3）。同时引入非确定数值卡顿。v0.6.1 **回退 KINETICS**，恢复平衡相 + L2 回补。

---

## 二、完整实验证据链（需回退的依据）

### 证据 1：KINETICS 冻结矿物，AlX₃ 提前耗尽

- 实验：KINETICS（k=1e-9）下 fertilizer 单层 y1 逐月
- 结果：**y1 m7 AlX₃ = 0（耗尽）**，且 **gibbsite = 2307692（恒定不变）**
- 推论：速率太小，gibbsite 完全不动——L2 矿物回补通道被切断

### 证据 2：对照（平衡相）AlX₃ 到 y3 才耗尽

- 实验：无 KINETICS（gibbsite 平衡相，L2 回补工作）fertilizer 单层
- 结果：AlX₃ 到 **y3 耗尽**（v0.5.0 基线）
- 推论：KINETICS 使 AlX₃ 耗尽从 y3 提前到 y1 m7——**方向有害**

### 证据 3：v0.6.0 "2 年 AlX₃ 稳定"结论为误导

- 实验：3 次重跑 v0.6.0 代码（KINETICS）fertilizer 2 年
- 结果：3 次全部**卡顿/耗尽**（非确定）；v0.6.0 记录的"2 年 AlX₃=34017 稳定"未复现
- 推论：v0.6.0 的 PASS 是**非确定路径 + 排水时程差异**的偶然结果，不构成科学结论

### 证据 4：AlX₃ 耗尽主因 = 排水淋失（结构性）

- 实验：gibbsite 冻结（KINETICS 下矿物不动）时 AlX₃ 仍耗尽
- 推论：即使**完全阻断矿物化**，单层排水（雨季 189mm）仍把溶液 Al³⁺ 带走 → AlX₃ 持续失血
- **认知修正**：L9 的"矿物化单向 Al 汇"假设不完整——**排水淋失是主因**，矿物化是次要

### 证据 5：KNOBS tolerance 1e-9 破坏 L2 精度（v0.6.1 附带发现）

- 实验：v0.6.1 回退 KINETICS 后保留 tolerance 1e-9 → `test_alx3_depletion_slower_with_mineral_evolution` 失败（AlX₃=3.4e-113）
- 恢复 1e-12 → 测试通过
- 推论：tolerance 1e-9 的初衷（减 KINETICS 卡顿）已随回退失效，且放宽容差破坏 L2 矿物回填精度——**一并恢复 1e-12**

---

## 三、回退范围

**删除（v0.6.0 KINETICS）**：
- `phreeqc_engine.py`：RATES/KINETICS 块生成、L2 双路径回填（恢复单路径）、has_kinetics 逻辑
- `constants.py`：AL_KINETIC_RATE / AL_KINETIC_PHASES / AL_KINETIC_DB_NAMES
- `tests/test_al_kinetics.py`

**保留（通用基础设施）**：
- `run_monthly_step_with_timeout`（子进程超时机制，`tests/test_numerical_stability.py` 保持）——通用数值鲁棒性，不依赖 KINETICS 假设

**恢复（v0.5.0 值）**：
- KNOBS tolerance 1e-12（证据 5）

---

## 四、回退后验证（Step 2）

| 指标 | 回退前（v0.6.0 KINETICS） | 回退后（v0.6.1） |
|------|---------------------------|-------------------|
| y1 m7 AlX₃ | 0（耗尽，gibbsite 冻结） | **35,965（L2 回补恢复）** |
| 耗尽年 | y1 m7 | **y3（v0.5.0 基线恢复）** |
| 全量测试 | 117（KINETICS 测试） | **115**（Al 动力学测试移除，子进程测试保留；性能恢复 ~4s） |
| KNOBS tolerance | 1e-9（破坏 L2 精度） | **1e-12（恢复）** |

---

## 五、L9 机制认知更新（Q3=A）

- **主因**：单层排水淋失（结构性）——矿物化是次要
- **方向**：多层（垂直缓冲，已验证推迟耗尽 y2→y4）+ L6（逐层参数，真实剖面）——v0.5.0 Q2=A 诊断方向
- **证伪清单更新**（v0.4.0+v0.5.0+v0.6.0）：MINERAL_SCALE / 非晶质相 / 预平衡 / 缺口修正 / 交换选择性 / **KINETICS**——全部证伪；仅多层+L6 未被证伪

---

## 六、v0.6.0 结论正式撤回

- v0.6.0 "KINETICS 初步有效（2 年 AlX₃ 稳定）"**撤回**——证据 3 证明为误导
- v0.6.0 "Al 汇阻断"假设修正——排水淋失主导（证据 4）
- 版本定位：v0.6.1 = 回退 + 认知修正 + 子进程机制保留

---

## 七、后续方向

- **L9 机制修正**（排水淋失主导）：多层 + L6 逐层参数实现
- **子进程超时机制**：保留为通用鲁棒性（长期模拟防卡顿）
- 性能/数值优化独立方向
