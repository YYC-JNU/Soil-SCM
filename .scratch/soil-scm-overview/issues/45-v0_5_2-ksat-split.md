# 45 — v0.5.2 Ksat 字段拆分（T2）

**What to build:** 将 `ksat` 拆分为两个独立字段：`ksat`（排水语义，LayerCascade 层间排水上限）与 `ksat_surface`（Green-Ampt 地表入渗，基质导水率）。更新 4 层内置默认值 `DEFAULT_4LAYER_KSAT=[12.0, 1.9, 0.48, 0.05]` + 新增 `DEFAULT_KSAT_SURFACE=7.2`；`SoilProfile`/`LayerOverrideConfig`/`apply_layer_override`/ConfigManager 校验全部同步。

**Blocked by:** 44（Green-Ampt 模块依赖 ksat_surface）

**Status:** ✅ 已完成 (2026-08-18, v0.5.2)

- [x] constants：`DEFAULT_4LAYER_KSAT` 更新为排水值 [12.0, 1.9, 0.48, 0.05]；新增 `DEFAULT_KSAT_SURFACE=7.2`（cm/day）
- [x] `SoilProfile`：`ksat` 注释改为"层间排水上限"；新增 `ksat_surface` 字段
- [x] `LayerOverrideConfig`：新增 `ksat_surface`（ksat 保留=排水语义）；值域校验（ksat>0、ksat_surface>0）
- [x] `apply_layer_override`：应用 `ksat` + `ksat_surface` 两个字段
- [x] `main._build_initial_layer_states`：4 层内置默认注入 `ksat_surface`
- [x] `infiltration_initial`/`infiltration_steady` 标记 deprecated（保留字段，不再参与入渗）
- [x] 测试（S2/S3 seam）：config 解析新字段、值域校验、apply_layer_override 两字段生效、内置默认注入
