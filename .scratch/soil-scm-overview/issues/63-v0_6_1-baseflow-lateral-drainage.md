# 63 — v0.6.1 VIC 深层基流 + Darcy 侧向排水模块

**What to build:** 为水文层新增两个物理出口——**L4 底部 VIC 非线性深层基流**与**各层 Darcy 集总侧向排水**，使华南红壤年深层渗漏（~500-800 mm/yr）与坡地侧向壤中流被真实建模，Na⁺/Cl⁻ 不再在 L4 "死胡同"累积、石灰 Ca²⁺ 有排泄通道。以**纯函数**实现并以**事件粒度**调度，`LayerCascade.run()` 返回结构向后扩展，`n_layers=1` 自动禁用（回退护栏）。

**Blocked by:** None — can start immediately（依赖 spec 62 决策表 Q1/Q2/Q4/Q10，2026-08-20 定案）。

**Status:** ✅ 已完成 (2026-08-20, v0.6.1)

- [x] 新增纯函数 `calc_baseflow(theta, profile, baseflow_cfg)`：VIC 方程 `Q_base = D_max·[D_s·S + (1−D_s)·Sⁿ]`，`S=(θ−θ_r)/(θ_s−θ_r)`；参数 `D_max=100 / D_s=0.10 / n_base=2.5 / θ_c=θ_r`；防抽干 `Q_base=min(公式, (θ−θ_r)·d·10)`；端点 θ≤θ_r→0、θ→θ_s→D_max
- [x] 新增纯函数 `calc_lateral_drainage(theta, profile, lateral_cfg)`：`Q_lat=k_lat·f_slope·max(0, θ−θ_FC)·d·10`；严格 FC 闸门（θ≤θ_FC→0）；防抽干 `Q_lat=min(公式, (θ−θ_FC)·d·10)`；`k_lat=[0.04/0.025/0.015/0.008] /day`、`f_slope=0.10`
- [x] `LayerCascade.run()` 返回扩展为 `(drains, runoff_extra, baseflow, lateral, theta_out)`（`run_extended` 方法 + `run` 3 元组兼容）；执行顺序=垂直排水→侧向→基流；drains 保持垂直语义（进下层），lateral/baseflow 出系统；θ 更新含新增出口
- [x] config 顶层节点 `simulation.baseflow={D_max, D_s, n_base, theta_c:"auto"}` 与 `simulation.lateral={f_slope, k_lat}` 解析与校验（D_max>0 / k_lat 长度=n_layers / f_slope 范围）；`n_layers=1` 自动禁用返回零出口
- [x] 事件路径（`_apply_hydrology_events`）逐场用事件后 θ 计算 Q_base/Q_lat，水量出口随场记录；月末非事件路径同步月粒度版本（`_apply_hydrology_month`）
- [x] 测试（S1/S5）：纯函数端点（θ≤θ_r→0 / θ→θ_s→D_max / FC 闸门 / 防抽干 min）、`LayerCascade.run()` 返回结构（drains 垂直语义、baseflow/lateral 出系统、theta_out 守恒）、config 解析校验、n_layers=1 护栏、事件路径逐场水量出口；**272 passed 全绿**
