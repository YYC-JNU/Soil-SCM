# 13 — L1 Al³⁺ 表面络合简化方法报告

**What to build:** 产出 Al³⁺ 表面络合简化方法的单独报告 `docs/L1_AL_SURFACE_METHOD.md`——Kd+pH 修正框架、参数表（文献骨架 + 模型交叉验证）、f(pH) 推导、已知缺点专节与优化方向专节。为后续实现预留设计依据。

**Blocked by:** None — can start immediately (与工单 12 并行).

**Status:** ✅ 已完成 (2026-08-14, via /implement)

## 完成说明

`docs/L1_AL_SURFACE_METHOD.md` 已创建：
- 方法框架：`Al_吸附 = Kd_eff(pH) × [Al³⁺] × M_表面`，`Kd_eff = Kd_base × f(pH)`
- f(pH) 简化质量作用式（表面配位交换 1:1 质子释放推导，S 形归一化）
- 参数表：Kd_base（矿物 10 / 有机质 50 L/kg，文献量级）+ pK_eff≈5（Karamalidis & Dzombak 2010 折算，Sverjensky 1996 交叉验证）
- 覆盖矿物（Hfo）+ 有机质（合并 L3），参数合并标注不确定
- **已知缺点专节**（6 项：无本地校准/竞争离子/两性溶解/聚合物/表面合并/线性假设）
- **优化方向专节**（6 项：本地实验标定/竞争吸附/L9 集成/两性修正/分层参数/标准数据库切换）

## Acceptance criteria

- [x] 报告含 Kd_eff(pH)=Kd×f(pH) 简化质量作用式框架（f(pH) 用有效 log_K 平衡式）
- [x] 参数表：Kd 文献骨架值 + Sverjensky (1996)/Karamalidis & Dzombak (2010) 模型交叉验证 + 不确定性标注
- [x] 覆盖表面：矿物（Hfo）+ 有机质（合并 L3），参数合并标注不确定
- [x] **已知缺点专节**：Kd 无本地实测校准、忽略竞争离子、f(pH) 简化近似、表面参数合并的不确定
- [x] **优化方向专节**：本地吸附实验标定、竞争吸附、与 L9 Al 循环集成、未来切换标准表面络合数据库


## Background

- 四源查证（phreeqc.dat/minteq.v4/wateq4f/RES³T）无 Al-Hfo 标准表面络合数据（WF3 记录）
- grilling Q4：Kd 文献骨架 + 模型交叉验证；f(pH) 简化质量作用式；单独报告含缺点与优化方向
- 纯文档交付（无代码改动），审查式验收
