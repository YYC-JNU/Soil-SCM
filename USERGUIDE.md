# Soil-SCM 用户指南（USERGUIDE）

> **适用版本**：v0.3.1（2026-08-17）
> **配套文档**：项目总览与开发历史见 `README.md`；已知模型局限的科学细节见 `docs/reports/V0_3_0_FINAL_REPORT.md`。
> 本文面向**使用该模型的科研人员**：讲解如何安装、配置、运行模拟并解读输出结果，末尾附常见问题排查与开发者速览。

---

## 一、简介与适用范围

**Soil-SCM** 是一个基于 **PHREEQC 地球化学引擎**的**土壤物理化学单点数值模式**，用于模拟**长期（数十年）** 施肥、酸化、淋溶、石灰改良与气候变化情景下土壤化学的演变，主要输出指标包括：

- **土壤 pH**
- **盐基饱和度**（base saturation，%）
- **阳离子交换量占用**（CEC occupied）
- **交换性钙 / 交换性铝**（及矿物相、溶液离子等扩展变量）

### 能模拟什么

| 过程 | 说明 |
|------|------|
| 自然淋溶 | 降水入渗（含酸雨化学组分）带走盐基，土壤酸化 |
| 施肥 | 氮磷钾镁锌肥（N/P₂O₅/K₂O/MgO/ZnSO₄），含尿素水解→硝化产酸 |
| 石灰改良 | 生石灰（CaO）施入中和酸性、补充交换性钙 |
| 气候变化 | 降水年递增 / 温度年递增对淋溶与土壤 CO₂ 分压的影响 |
| 多分层 | 可选 1~4 层垂直剖面，模拟上层排水的级联下渗 |

### 边界与适用性（务必先读）

1. **单点模式**：模拟单位面积（ha）土柱的化学演变，**不含**空间分布、作物根系吸水与有机质分解（均在扩展规划中）。
2. **施肥单层长期模拟存在已知局限**：单层排水会导致交换性铝（AlX₃）淋洗耗尽，`fertilizer`/`fertilizer_lime` 情景**约第 3~4 年 pH 突升至 ~10**（本指南第 6 章案例可复现）。**建议干预类情景使用 `n_layers: 4` 多分层**（详见第 5 章示例 2 与第 9 章 FAQ）。
3. 矿物量采用缩放系数 `0.001`（折中方案），矿物缓冲容量被压缩——结果应作**趋势对比**而非绝对定量。

> 📎 延伸阅读：上述局限的完整证据链与科学讨论见 `docs/reports/V0_3_0_FINAL_REPORT.md`（第六节）。

---

## 二、环境与安装

### 2.1 依赖清单

| 依赖 | 版本要求 | 用途 |
|------|----------|------|
| Python | ≥ 3.10（开发环境 3.13） | 运行环境 |
| `phreeqc` | ≥ 1.1.1 | **官方 IPhreeqc 地球化学引擎**（核心，必装） |
| `numpy` | ≥ 1.20 | 数值计算 |
| `pandas` | ≥ 1.3 | CSV/表格处理 |
| `matplotlib` | ≥ 3.4 | 结果绘图 |
| `pyyaml` | ≥ 5.4 | 配置文件解析 |
| `netCDF4` | ≥ 1.5 | NetCDF 输出格式（可选） |
| `pytest` | ≥ 9.0 | 运行单元测试（可选） |

### 2.2 安装步骤

```bash
cd Soil-SCM
pip install -r requirements.txt
```

> **引擎说明**：化学计算依赖官方 `phreeqc` 包（IPhreeqc 3.8.6，USGS 官方引擎，随包自带 `phreeqc.dat` 热力学数据库，无需额外下载）。
> - 若 `phreeqc` 未安装，或某次计算失败，引擎会**自动降级到内置简化经验模式**，保证模拟流程不中断（此时结果精度大幅下降，日志会记录降级原因）。
> - 如何确认引擎状态？见第 7 章"运行与监控"。

### 2.3 验证安装

```bash
pytest tests/ -v        # 应显示 115 passed
```

---

## 三、快速开始

按默认配置跑通一次模拟（`natural` 情景、50 年、单层）：

```bash
python main.py
```

预期流程与输出（约 1 分钟）：

1. 控制台打印**配置摘要**（模拟年数/情景/引擎模式/土壤类型等）；
2. 打印**土壤信息**（红壤矿物组成）与**初始条件摘要**（交换位点/溶液浓度/矿物量）；
3. 开始时间积分，**每年（或每 10 年）打印一次进度**与当前 pH；
4. 结束打印 `[SUCCESS]`，在 `output/` 目录生成：

| 文件 | 说明 |
|------|------|
| `output/soil_scm_natural_output.csv` | 逐月诊断量时间序列（主结果） |
| `output/pH_natural.png` | pH 演化曲线图 |
| `output/soil_scm.log` | 运行日志 |

修改配置只需编辑 `config/config.yaml` 后重新运行（无需重装依赖）：

```bash
python main.py --config config/config.yaml
python main.py --config /path/to/your_config.yaml   # 任意自定义配置文件
```

---

## 四、配置文件详解

配置文件为 YAML 格式（`config/config.yaml`），结构类似 WRF 的 `namelist.input`。全部参数速查表见 `config/config_example.yaml` 顶部注释（含单位/默认值/取值范围）。

### 4.1 `simulation`：模拟控制

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `n_years` | `50` | 模拟年数（短期试验 5~10，长期 50~100） |
| `time_step` | `monthly` | 时间步长（当前唯一支持值） |
| `sub_time_step_days` | `0` | 子时间步长（天）；`0`=关闭，`1~7`=降水按子步均分 |
| `scenario` | `natural` | 情景：`natural`/`fertilizer`/`fertilizer_lime`/`precip_increase`/`temp_increase`（见第 6 章） |
| `engine_mode` | `auto` | `auto`=PHREEQC 可用则用，否则降级简化；`phreeqc`=强制官方；`simplified`=始终简化 |
| `precip_infiltration` | `0.05` | 降水入渗系数（0~1）：实际进入土壤溶液的比例，其余为径流/排水 |
| `n_layers` | `1` | 分层数（1=单层，4=多分层；各层默认参数相同） |
| `enable_surface` | `false` | 是否启用 Hfo 铁氧化物表面络合（P/Zn 吸附；与多分层配合使用） |
| `enable_pre_equilibration` | `true` | 初始状态观测锚定预平衡（热力学自洽，建议保持开启） |
| `pre_equilibration_max_steps` | `60` | 预平衡最大迭代步数 |

### 4.2 `soil_data`：土壤数据

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input_file` | `data/soil_survey.csv` | 土壤普查 CSV 路径 |
| `exchangeable_ions_file` | `data/exchangeable_ions.csv` | 交换性阳离子 CSV 路径 |
| `soil_type` | `red_soil` | 土壤类型标识（`red_soil`/`black_soil`/`purple_soil`，对应矿物数据库） |
| `survey.*` | 全 `-1` | 内联土壤参数（pH、CEC 等，见第 5 章覆盖规则） |
| `exchangeable_ions.*` | 全 `-1` | 内联交换性阳离子（Ca/Mg/K/Na/Al/H） |

### 4.3 `climate`：气候强迫

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `base_annual_precip` | `1893.0` mm/yr | 基准年降水量（广东量级） |
| `base_annual_temp` | `25.0` °C | 基准年平均温度 |
| `precip_increase_rate` | `0.02` /yr | 情景 `precip_increase` 的降水年递增比例 |
| `temp_increase_rate` | `0.05` °C/yr | 情景 `temp_increase` 的温度年增量 |

### 4.4 `fertilizer` / `lime`：施肥与石灰

每次施用量（kg/ha），每年 `apply_months`（默认 3/6/9 月）各施一次（参考农业农村部 2021 水稻施肥指导意见）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `n` | `12.0` | 氮肥（按 N 计） |
| `p2o5` | `4.0` | 磷肥（按 P₂O₅ 计） |
| `k2o` | `9.0` | 钾肥（按 K₂O 计） |
| `mgo` | `3.0` | 镁肥（按 MgO 计） |
| `znso4` | `1.0` | 硫酸锌（按 ZnSO₄ 计） |
| `apply_months` | `[3, 6, 9]` | 施肥/施石灰月份 |
| `lime.amount_per_apply` | `45.0` | 生石灰（按 CaO 计）kg/ha/次 |

### 4.5 `soil_co2`：土壤 CO₂

`pCO2_ref=0.015 atm`，`T_ref=25.0 °C`，`beta=0.05 /°C`。逐月 pCO₂ 按 **Brook (1983)** 公式随温度变化：`pCO₂(T) = pCO₂_ref × exp(β·(T − T_ref))`。

### 4.6 `precipitation_chemistry`：降水化学

酸雨组分（默认据《2025 年广东省生态环境状况公报》）：`ph=5.75`，10 种离子当量占比（Cl 18.4 / SO₄ 12.5 / NO₃ 10.8 / F 2.1 / Ca 20.9 / NH₄ 15.8 / Na 11.5 / Mg 5.1 / K 1.9 / H 1.0，单位 %，总和必须=100）。降水中的离子随入渗水进入土壤溶液，是**酸沉降驱动土壤酸化的主要来源**。

### 4.7 `output`：输出控制

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `directory` | `./output` | 输出目录 |
| `format` | `csv` | 输出格式：`csv` / `netcdf` |
| `variables` | `[pH, base_saturation, ...]` | 输出变量列表（第 8 章详述） |

> 📎 延伸阅读：`config/config_example.yaml` 顶部为**完整参数速查表**（类型/默认值/单位/可选值），配置前建议通读。

---

## 五、输入数据准备

模型输入数据分三类：**配置文件**（`config/config.yaml`）、**土壤普查 CSV**（`data/soil_survey.csv`）、**交换性阳离子 CSV**（`data/exchangeable_ions.csv`）。

### 5.1 土壤普查 CSV（`data/soil_survey.csv`）

单行数据，逗号分隔，**表头必须与示例完全一致**：

```csv
pH,有机质_g_kg,CEC_cmol_kg,容重_g_cm3,耕地面积_ha,有效土层厚度_cm,有效磷_mg_kg,速效钾_mg_kg,质地,砂粒_pct,粉粒_pct,黏粒_pct
5.0,20.0,12.0,1.2,1.0,30.0,15.0,100.0,壤土,35.0,40.0,25.0
```

| 列 | 含义 | 单位 | 示例值 |
|----|------|------|--------|
| `pH` | 初始土壤 pH | - | 5.0 |
| `有机质_g_kg` | 有机质含量 | g/kg | 20.0 |
| `CEC_cmol_kg` | 阳离子交换量 | cmol(+)/kg | 12.0 |
| `容重_g_cm3` | 土壤容重 | g/cm³ | 1.2 |
| `耕地面积_ha` | 耕地面积 | ha | 1.0 |
| `有效土层厚度_cm` | 有效土层厚度 | cm | 30.0 |
| `有效磷_mg_kg` | 有效磷 | mg/kg | 15.0 |
| `速效钾_mg_kg` | 速效钾 | mg/kg | 100.0 |
| `质地` | 土壤质地名称 | - | 壤土 |
| `砂粒/粉粒/黏粒_pct` | 机械组成 | % | 35/40/25 |

### 5.2 交换性阳离子 CSV（`data/exchangeable_ions.csv`）

单行数据，**单位 cmol(+)/kg**：

```csv
交换性Ca_cmol_kg,交换性Mg_cmol_kg,交换性K_cmol_kg,交换性Na_cmol_kg,交换性Al_cmol_kg,交换性H_cmol_kg
3.0,1.5,0.5,0.2,2.0,1.0
```

### 5.3 config 内联覆盖规则（v0.2.3 起）

`config.yaml` 的 `soil_data.survey` 与 `soil_data.exchangeable_ions` 支持**内联字段**，规则如下：

| 填写方式 | 行为 |
|----------|------|
| **全部填 `-1`**（默认） | 回退读取 `data/` 下的 CSV 默认值 |
| **全部填有效值** | 覆盖 CSV 值 |
| **混合填写**（部分 -1、部分有效值） | **直接报错**，提示列出所有 -1 字段 |

示例：只想改 pH 与 CEC、其余用 CSV 默认值，必须把 `survey` 子块**所有字段**都写成有效值。

### 5.4 完整示例 1：改成 `fertilizer_lime` 情景（单层）

目标：模拟施肥 + 石灰干预下的土壤演变。修改 `config/config.yaml`：

```yaml
simulation:
  n_years: 30            # 30 年
  scenario: fertilizer_lime   # ← 关键改动：由 natural 改为 fertilizer_lime
```

（其余区块保持默认；`fertilizer` 与 `lime` 区块已含默认施用量。）

运行：

```bash
python main.py
```

预期输出文件：`output/soil_scm_fertilizer_lime_output.csv`、`output/pH_fertilizer_lime.png`。

> ⚠️ **注意**：单层模式下 `fertilizer_lime` 约第 4 年 pH 会突升至 ~10（交换性 Al 淋洗耗尽的已知局限），这是**模型结构性局限**而非配置错误，建议改用示例 2 的多分层配置。

### 5.5 完整示例 2：启用 4 层多分层（推荐用于干预类情景）

目标：建立垂直剖面，通过上层排水级联下渗缓解单层 Al 耗尽。修改 `config/config.yaml`：

```yaml
simulation:
  n_years: 30
  scenario: fertilizer_lime   # 干预情景
  n_layers: 4                 # ← 关键改动：分层数改为 4
```

运行后输出列名带层深后缀（`pH_0_10`、`pH_10_20` 等），顶层代表 0~15 cm 表土、底层代表 45~60 cm 底土。

> 📎 延伸阅读：多分层的物理机制（级联下渗、一维平流守恒）与 SURFACE 表面络合的用法见 `docs/analysis/OPTIMIZATION_PLAN.md`（WF1~WF5）。

---

## 六、模拟情景与案例

### 6.1 五种情景

| 情景 | 干预方式 | 典型用途 |
|------|----------|----------|
| `natural` | 无任何干预，仅降水淋溶 + 酸沉降 | 基线/对照（默认） |
| `fertilizer` | 3/6/9 月施氮磷钾镁锌肥（尿素水解→硝化产酸） | 长期施肥酸化评估 |
| `fertilizer_lime` | 施肥 + 同期施生石灰 | 施肥 + 改良对比（推荐多分层） |
| `precip_increase` | 降水每年递增 `precip_increase_rate` | 气候变化（降水）情景 |
| `temp_increase` | 温度每年递增 `temp_increase_rate`（影响 pCO₂） | 气候变化（增温）情景 |

### 6.2 模拟案例：natural vs fertilizer_lime（30 年，单层）

**输入数据**：使用项目自带默认数据，配置仅修改两处：

```yaml
simulation:
  n_years: 30
  scenario: natural          # 分别运行 natural 与 fertilizer_lime 两次
```

`data/soil_survey.csv` 与 `data/exchangeable_ions.csv` 即 5.1/5.2 节中的内容（pH=5.0，CEC=12 cmol(+)/kg，交换性 Ca/Al/H 分别为 3.0/2.0/1.0 cmol(+)/kg）。

**模拟结果**（PHREEQC 官方引擎，2026-08 实测数据）：

![30 年 pH 演化对比（natural vs fertilizer_lime）](docs/images/userguide_case_pH_comparison.png)

| 指标 | `natural` | `fertilizer_lime` |
|------|-----------|-------------------|
| 首月 pH（平衡后） | 4.18 | 4.18 |
| 30 年 pH 区间 | 3.61 ~ 4.47 | 4.18 ~ 10.40 |
| 趋势 | 缓降后稳定（淋溶酸化） | 第 4 年起 pH 突升至 ~10 |
| 结果解读 | 酸雨入渗持续消耗盐基，pH 低位稳定 | 石灰补充盐基 → pH 回升，但单层排水使交换性 Al 耗尽 → pH 突升（结构性局限，见 FAQ Q4） |

**关键结论**：`natural` 呈现真实红壤淋溶酸化趋势（可用作基线）；`fertilizer_lime` 单层下 pH 突升是模型局限的复现——**同一配置改用 `n_layers: 4` 后 pH 突变推迟、并建立垂直梯度**（见 5.5 节示例 2）。

### 6.3 气候变化情景示例

```yaml
simulation:
  n_years: 50
  scenario: precip_increase    # 或 temp_increase
climate:
  precip_increase_rate: 0.02   # 降水年递增 2%
  temp_increase_rate: 0.05     # 温度年递增 0.05°C（仅在 temp_increase 时生效）
```

---

## 七、运行与监控

### 7.1 命令行

```bash
python main.py                                        # 默认 config/config.yaml
python main.py --config path/to/config.yaml           # 自定义配置
python main.py --config config/config_example.yaml    # 基于模板配置
```

### 7.2 控制台进度

时间积分开始后，控制台每 10 年（及第 1 年）打印一次进度与当前 pH：

```
  第    1 年完成 | pH = 4.448
  第   10 年完成 | pH = 4.460
  ...
```

### 7.3 日志文件

- 运行日志：`output/soil_scm.log`（记录引擎初始化、输出保存等）。
- 引擎降级、预平衡偏离超阈值等**警告/错误**均在日志中带时间戳记录。

### 7.4 引擎模式与降级

配置 `engine_mode` 决定化学计算路径：

| 模式 | 行为 |
|------|------|
| `auto`（默认） | PHREEQC 可用则用官方引擎；不可用自动降级简化模式 |
| `phreeqc` | 强制官方引擎（失败时降级简化） |
| `simplified` | 始终使用简化经验模式（仅 pH 经验演化，精度低，仅兜底） |

**如何确认本次运行用了哪个引擎？** 日志中可见：

```
[INFO] soil_scm.phreeqc_engine: 官方 PHREEQC 引擎已初始化 (IPhreeqc 3.8.6-17100-x64)   ← 官方引擎
[WARNING] ... 无可用 PHREEQC 引擎，使用简化模式                                        ← 已降级
```

### 7.5 异常与失败复现文件

官方引擎计算失败时：
1. 引擎自动**永久降级**到简化模式继续模拟（主流程不中断）；
2. 失败的完整 PHREEQC 输入写入 **`output/error.inp`**（每次失败刷新）——可据此复现与调试；
3. 控制台/日志记录错误详情。

> 若 `output/error.inp` 出现，说明配置或数据触发了 PHREEQC 求解失败（多为矿物相/表面位点量级不合理），详见第 9 章 FAQ。

---

## 八、输出结果解读

### 8.1 CSV 主输出（`output/soil_scm_{scenario}_output.csv`）

默认配置下每行 = 一个月的模拟结果，共 8 列：

| 列名 | 含义 | 单位/说明 |
|------|------|-----------|
| `year` | 年（1 起） | 第 1 年 = 模拟起始年 |
| `month` | 月（1~12） | 1 月 = 第 1 年 1 月 |
| `time_decimal` | 连续时间 | 年（= year + (month−1)/12） |
| `pH` | 土壤 pH | 化学平衡后值 |
| `base_saturation` | 盐基饱和度 | %（(Ca+Mg+K+Na)/CEC 占用） |
| `CEC_occupied` | 被占用的交换位点总量 | mol（含 Al） |
| `exchangeable_Ca` | 交换性钙 | mol |
| `exchangeable_Al` | 交换性铝 | mol |

> 注：`config.output.variables` 中 `mineral_mass` / `solution_ions` 为**预留扩展变量**，当前引擎诊断尚未回填，故默认 CSV 不含这两列。

### 8.2 多分层输出

`n_layers > 1` 时，诊断列名追加**层深后缀**（如 `pH_0_10`、`base_saturation_10_20`…），便于逐层分析垂直剖面演化。

### 8.3 NetCDF 输出

`output.format: netcdf` 时生成 `output/soil_scm_{scenario}_output.nc`：时间维度 `time`（单位：years since 2000-01-01），每个变量为一个维度数组。若 `netCDF4` 未安装则自动回退 CSV。

### 8.4 结果图

运行结束自动绘制 `output/pH_{scenario}.png`（逐月 pH 时间序列，150 dpi）。多情景对比、离子浓度曲线等进阶图可参考 `tools/` 下辅助脚本（独立运行，不参与主流程；从项目根目录运行 `python tools/plot_xxx.py`）。

### 8.5 结果合理性检查清单

- [ ] 初始首月 pH 与输入 `survey.ph` 偏差 < 0.5（若预平衡日志提示"偏离度超阈值"，检查输入观测值）
- [ ] `natural` 情景 pH 趋势为缓降或稳定（若持续上升需排查，见 FAQ Q3）
- [ ] `fertilizer_lime` 单层 pH 突升 ≥ 9 → 属于已知局限，改用 `n_layers: 4`
- [ ] `output/error.inp` 未出现（出现则本次运行已降级简化模式）

---

## 九、常见问题排查（FAQ）

### 环境类

**Q1：运行报 `ModuleNotFoundError: No module named 'phreeqc'`**
- 原因：`phreeqc` 包未安装。
- 解决：`pip install -r requirements.txt`。未安装时模型会自动降级简化模式，但结果精度大幅下降，建议安装后使用官方引擎。

**Q2：提示 `matplotlib 未安装，跳过绘图` / `netCDF4 未安装，回退到 CSV`**
- 原因：可选依赖缺失。
- 解决：安装 `matplotlib` 或 `netCDF4`（后者仅在输出格式选 `netcdf` 时需要）。

**Q3：报错 `survey 参数全部为 -1，但土壤普查文件不存在`**
- 原因：config 内联字段全 -1 时依赖 `data/soil_survey.csv`，文件缺失或路径错误。
- 解决：检查 `config.yaml` 的 `soil_data.input_file` 路径，或改用内联字段全部填有效值。

### 运行类

**Q4：`fertilizer`/`fertilizer_lime` 情景 pH 突升至 ~10（第 3~4 年）**
- 原因：**模型结构性局限**——单层排水导致交换性 Al（AlX₃）被盐基置换并淋洗耗尽，Al 缓冲库枯竭后 pH 失稳（与真实红壤不符）。
- 建议：改用 `n_layers: 4` 多分层（推迟耗尽、建立垂直梯度）；或仅作趋势研究并记录局限。完整证伪链见 `docs/reports/V0_3_0_FINAL_REPORT.md` 第六节。

**Q5：日志出现 `PHREEQC 计算失败` 并生成 `output/error.inp`，后续结果异常**
- 原因：某月化学平衡求解失败（矿物量/表面位点量级、或 PHREEQC 数值失稳），引擎已永久降级简化模式。
- 建议：检查矿物量缩放相关配置；若 `enable_surface: true`，确认未独立启用（需与多分层配合）；可提交 `output/error.inp` 复现调试。

**Q6：`natural` 情景 pH 反而上升（脱酸）**
- 原因：单层模型的 Al 淋洗/矿物缓冲行为导致；另需检查是否误设了 `precip_infiltration` 过小。
- 建议：使用多分层配置重新运行，并将结果与 `docs/analysis/Q1_ANALYSIS.md` 的诊断对比。

**Q7：模拟耗时过长 / 卡住**
- 原因：官方引擎每月需做化学平衡计算，情景/分层数增加后耗时线性上升；SURFACE 开启时迭代数提高至 1000，耗时显著增加。
- 建议：先缩短 `n_years` 验证流程；干预情景避免同时开启 `enable_surface` 与多层；日志可定位耗时步骤。

### 结果解读类

**Q8：如何判断一次模拟结果"合理"？**
- 先跑 `natural` 基线，对照 8.5 节检查清单；再跑目标情景并与基线对比趋势（pH 升降方向、盐基饱和度变化方向）。

**Q9：怎样对比不同情景/参数？**
- 修改配置分别运行，CSV 输出到同一 `output/` 目录（文件名含情景名，不会互相覆盖）；用 pandas 读入两个 CSV 叠加绘图，或参考 `tools/` 下辅助脚本。

**Q10：初始首月 pH 与输入值差异大，正常吗？**
- 正常：输入 pH 是观测值，经 PHREEQC 三相平衡与预平衡锚定后首月即达稳态，偏离 < 0.5 视为合理；若偏差大且日志警示"输入参数可能不物理"，请核对 CEC 与交换性离子观测值。

> 📎 延伸阅读：模型局限的完整清单与科学讨论见 `docs/reports/V0_3_0_FINAL_REPORT.md` 第六节；气候/降水化学集成见 `docs/analysis/Q7_PRECIP_CHEMISTRY.md`。

---

## 十、开发者速览

> 本节面向需要理解或扩展模型的开发者。模块级设计文档见 `docs/analysis/ROADMAP.md` 与 `docs/analysis/OPTIMIZATION_PLAN.md`。

### 10.1 模块地图与数据流

```
config/config.yaml ──► ConfigManager ──► 各 *Config
data/soil_survey.csv ──► InputReader ──► SoilProfile
data/exchangeable_ions.csv ─┘
config/soil_mineral_db.json ──► SoilDatabase ──► SoilTypeInfo
config/precip_chemistry_default.json ──► PrecipChemistry
┌───────────────────────────────────────────────────────────────┐
│ InitialConditionBuilder（溶液/交换/矿物/气相初始状态）           │
│ ClimateForcing（逐月降水/温度/pCO₂）                            │
│ ScenarioController（月度施肥/石灰指令）                         │
│ PhreeqcEngine（官方 PHREEQC ⇄ 简化模式兜底）                    │
│   └─ build_phreeqc_input → RunString → _parse_official_output   │
│ OutputWriter（CSV / NetCDF / PNG）                             │
└───────────────────────────────────────────────────────────────┘
```

### 10.2 核心机制速览

| 机制 | 位置 | 一句话说明 |
|------|------|-----------|
| 月度化学平衡 | `phreeqc_engine._run_official_step` | 构建 PHREEQC 输入串 → 平衡求解 → SELECTED_OUTPUT 回填状态 |
| 简化模式 | `_run_simplified_step` | 经验公式（降水淋溶降 pH / 施肥产酸 / 石灰提碱），仅兜底 |
| 氮形态库存层 | `advance_nitrification` | 尿素→NH₄⁺→NO₃⁻ 一阶转化，硝化产酸 2H⁺/mol N 注入 REACTION（phreeqc.dat 会把溶液无机氮平衡为 N₂） |
| 矿物演化回填 | `_parse_official_output` | `-equilibrium_phases` 读回矿物摩尔量（L2 修复：不冻结，Al 循环通道建立） |
| 预平衡 | `pre_equilibrate` | 观测锚定迭代（交换离子比例-阻尼控制），使初始状态自洽 |
| 多分层 | `run_monthly_multi_layer` | 每层独立状态，上层排水溶质级联注入下层（一维平流守恒） |
| 表面络合 | `build_surface` / SURFACE 块 | Hfo_s/Hfo_w 铁氧化物位点，P/Zn 吸附（`enable_surface` 控制） |

### 10.3 扩展提示

- **新增情景**：修改 `scenario_controller.get_action()` 的分支即可；
- **新增肥料种类**：在 `_build_phreeqc_input()` 的 REACTION 段添加离子摩尔量换算；
- **新增输出变量**：在 `_extract_diagnostics()`（main.py）与 `SELECTED_OUTPUT` 查询列中同步添加；
- **引擎升级路径**：`advance_nitrification` 为独立函数，可整体替换为 PHREEQC `KINETICS` 动力学块而不改调用契约。


