# 74 — k_om 重参数化（spec 69 工单 73）

**What to build:** 让 OM 矿化产 CO₂ 的 pCO₂ 调制系数有实测依据：`K_OM_PCO2` 自 0.0005 起在 **0.0003 / 0.0005 / 0.0008** 三档扫描标定（E3 验收：表层 pCO₂_eff 0.024→0.039 方向、L1 pH 酸化方向复验）；选定值入常量模块并记录扫描表（同 v0.4.0 L9 扫描纪律）。

**Blocked by:** None — can start immediately（独立参数标定，不依赖 70~73）。

**Status:** ready-for-agent

- [ ] 三档扫描运行并记录扫描表（pCO₂_eff/L1 pH/表层酸化方向）
- [ ] 选定值写入常量模块 + 相关测试断言更新
- [ ] E3 复验：表层 pCO₂_eff 单调随 k_om、L1 pH 酸化方向达成
- [ ] 现有 289 测试全绿（expand-contract）
