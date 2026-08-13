# WF1 — 多分层模型架构决策

**Label:** `wayfinder:grilling`
**Status:** ✅ closed (2026-08-13, via /grilling)
**Parent:** 多分层模型与 SURFACE 表面络合（wayfinder:map）

## Question

将 Soil-SCM 从单层（n_layers=1）升级为多分层（默认 4 层：0-10/10-20/20-40/40-60cm）时，架构如何设计？

## Resolution — 决策汇总（2026-08-13 /grilling 解析）

| # | 决策 | 选定方案 |
|---|------|---------|
| Q1 | **分层物理表示** | `List[SoilState]` — 每层独立完整 PHREEQC 状态；单层退化为长度 1 列表；`SoilProfile` 只提供各层参数 |
| Q2 | **层间垂直迁移** | **一维平流** — 上层排水量 + 平衡后溶液浓度（SELECTED_OUTPUT totals）作为下层 REACTION 输入；平流主导真实淋溶，弥散在 4 层分辨率下收益低 |
| Q3 | **排水逐层分配** | **级联下渗** — 最上层接受 `precip × infiltration`；每层平衡后超出持水水量（含溶质）逐层下渗，最底层成为深层排水流失 |
| Q4 | **最高接缝（S1）** | **保持 `run_monthly_step` 单层接口不变**（深模块）+ 新增 `run_monthly_multi_layer` 高层编排层（层循环 + 级联平流交换）；`n_layers=1` 走完全相同的原路径（回归护栏） |
| Q5 | **配置接口** | `simulation.n_layers`（默认 1）+ 可选 `layer_overrides` 指向外部 CSV/JSON 逐层覆盖容重/CEC/交换性阳离子/矿物/pCO₂；各层默认参数相同 |
| Q6 | **逐层输出** | **列名加层后缀**（`pH_0_10`、`base_saturation_10_20`…）；单层列名不变（回归）；保持宽格式 CSV |
| Q7 | **溶质守恒核算** | **SELECTED_OUTPUT totals × 排水水量** = 移出摩尔量 → 下层 REACTION；守恒可验证（各层收支平衡测试） |

### 架构蓝图

```
main.py 时间积分主循环
  └─ run_monthly_multi_layer (新编排层)
       ├─ 对每层调用 run_monthly_step (S1 接缝不变, 深模块)
       ├─ 层间平流: 上层排水量 + SELECTED_OUTPUT totals × 水量
       │      └─ → 下层 REACTION 离子输入 (级联下渗)
       └─ 更新 List[SoilState]
config: simulation.n_layers=1|4 + 可选 layer_overrides
output: pH_0_10, base_saturation_10_20 ... (单层列名不变)
```

### 验收确认

- [x] 分层物理表示决策明确 — `List[SoilState]`
- [x] 层间垂直迁移数值方案选定 — 一维平流
- [x] 排水模型逐层分配机制明确 — 级联下渗
- [x] 最高测试接缝（S1）的多层扩展方案确定 — 单层接口不变 + 高层编排
- [x] 配置与输出接口方案确定 — `n_layers` + 层后缀列名

**决策记录**：经 `/grilling` 两轮 7 决策全部达成共识（用户确认），WF2 阻塞已解除。

