# 39 — v0.5.0 SoilProfile/SoilState 扩展 + 4 层内置默认（T3）

**What to build:** SoilProfile 新增 porosity（显式覆盖否则 1−ρ/2.65）/ksat/infiltration_initial/infiltration_steady 字段；SoilState 新增 stored_water；4 层内置物理剖面默认（厚度[20,20,20,40]cm/粘粒[25,35,45,50]/孔隙度[55,47,45,43]/Ksat[76.8,24.5,7.2,2.9]/f0[1.0,0.4,0.15,0.04]/fc[0.4,0.2,0.08,0.02]）收敛于常量模块。

**Blocked by:** 37（字段定义）

**Status:** ready-for-agent

- [ ] SoilProfile 水文字段 + porosity 属性覆盖逻辑
- [ ] SoilState.stored_water 字段
- [ ] 4 层内置默认常量 + n_layers=4 且未配置 layer_overrides 时自动注入
- [ ] 测试：porosity 覆盖/反推容重、字段默认、内置默认注入（S3 seam）
