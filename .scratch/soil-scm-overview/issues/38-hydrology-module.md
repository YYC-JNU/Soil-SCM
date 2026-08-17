# 38 — v0.5.0 水文模块（随机降雨+Horton+级联）（T2）

**What to build:** 新水文模块：随机日降雨生成器（seed 固定可复现、场次 U(4,12)、指数分配月总量守恒、单场 2h）；Horton 单场入渗（k=5/h、表层入渗系数 0.75、降水耗尽全入渗）；层间级联（50% 饱和度持水增量、Ksat 限制渗漏、stored_water 跨月累积、超饱和溢出计入径流）。

**Blocked by:** 37（配置结构）

**Status:** ready-for-agent

- [ ] 随机降雨：同 seed 可复现、月降水总量守恒、场次数∈[4,12]
- [ ] Horton 单场：手算验证（f0=1.0/fc=0.4/k=5/h/T=2h → A≈55.2mm；min(P_j×0.75, A)）
- [ ] 级联：持水填满→Ksat 限制→stored_water 累积→超饱和 overflow；逐层排水正确
- [ ] 测试：全部纯函数路径（S1 seam）
