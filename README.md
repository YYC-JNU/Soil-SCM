# Soil-SCM: 土壤物理化学数值模式

基于 PHREEQC 地球化学引擎的土壤单点物理化学数值模式，用于模拟长期（数十年）施肥、酸化、淋溶与改良条件下的土壤化学演变（pH、盐基饱和度、交换性阳离子等）。

> **当前版本**：**v0.7.2**（2026-08-25：工单 83 **深层 CEC/BS 物理化** + 工单 84 **验证探针 + natural 碱化归因**；355 测试）+ **v0.7.1**（2026-08-25：工单 82 L4 深层盐基运移数值稳定化，30y 全量解锁）+ 地球化学深化（工单 77/78/80，见 §十一）
> **快速上手**：见 [USERGUIDE.md](USERGUIDE.md) ｜ **版本历史**：见 [§十一 版本更新记录](#十一版本更新记录)

---

## 一、快速开始

### 1.1 安装依赖

```bash
# 安装依赖
pip install -r requirements.txt
```

依赖清单：

- phreeqc>=1.1.1    （官方 IPhreeqc 引擎封装）
- numpy>=1.20.0
- pandas>=1.3.0
- matplotlib>=3.4.0
- pyyaml>=5.4.0
- netCDF4>=1.5.0
- pytest>=9.0        （测试框架，v0.2.0 起）

> **说明**
> - 化学计算依赖官方 `phreeqc` 包（IPhreeqc 3.8.6，USGS 官方引擎）；`phreeqpython` 兼容后端已于 v0.1.3 废弃移除。
> - 若 `phreeqc` 未安装或 PHREEQC 计算块与数据库不兼容导致计算失败，引擎会自动**降级到内置简化模式**，保证模拟流程稳定运行。

### 1.2 运行模拟

```bash
python main.py --config config/config.yaml
```

### 1.3 运行测试

```bash
# v0.2.0 起建立 pytest 测试框架（tests/，当前 351 用例）
pytest tests/ -v
```

---

## 二、项目目录结构

```
Soil-SCM/
├── config/                     # 配置文件
│   ├── config.yaml             # 主配置文件（类似 WRF namelist.input）
│   ├── config_example.yaml     # 配置模板（参数速查表 + 完整可填配置）
│   ├── soil_mineral_db.json    # 土壤矿物数据库
│   ├── soil_mineral.tbl        # 矿物热力学表
│   ├── precip_chemistry_default.json  # 降水化学默认值（广东 2025 公报）
│   └── texture_code.json       # 土壤质地编码表（卡钦斯基制，v0.2.3）
├── src/                        # 源码
│   ├── __init__.py
│   ├── config_manager.py       # 配置加载与校验
│   ├── soil_database.py        # 土壤/矿物数据库查询
│   ├── input_reader.py         # 土壤普查/交换性离子数据读取
│   ├── climate_forcing.py      # 气候强迫（降水/温度/pCO₂）
│   ├── hydrology.py            # 水文物理（v0.5.x：Green-Ampt 入渗 + 层间级联）
│   ├── scenario_controller.py  # 情景控制（施肥/石灰/气候变化）
│   ├── phreeqc_engine.py       # PHREEQC 化学引擎（官方 + 简化降级）
│   ├── output_writer.py        # 结果输出（CSV/NetCDF/绘图）
│   ├── initial_condition.py    # 初始条件构建（溶液/交换/矿物/气相）
│   ├── precip_chemistry.py     # 降水化学（Q7）
│   ├── logging_config.py       # 日志（Q15）
│   ├── constants.py            # 全局常量（Q19）
│   └── utils.py                # 工具函数
├── data/                       # 输入数据
│   ├── soil_survey.csv         # 土壤普查数据
│   └── exchangeable_ions.csv   # 交换性阳离子初始值
├── tests/                      # pytest 单元测试（351 用例）
│   ├── conftest.py
│   └── test_*.py
├── docs/                       # 项目文档
│   ├── reports/                # 版本总结报告
│   │   ├── V0_3_0_FINAL_REPORT.md  # v0.3.0 最终总结报告（v0.2.2 后全部优化合并）
│   │   ├── V0_2_0_ENGINEERING_REPORT.md
│   │   └── V0_2_2_SHORT_TERM_REPORT.md
│   ├── analysis/               # 专项分析与规划
│   │   ├── OPTIMIZATION_PLAN.md    # 问题清单与优化计划（Q1-Q26）
│   │   ├── ROADMAP.md              # 优化路线图
│   │   ├── L1_AL_SURFACE_METHOD.md # L1 Al³⁺ 表面络合简化方法报告（含缺点/优化方向）
│   │   ├── Q1_ANALYSIS.md          # Q1 引擎分析
│   │   ├── Q1_plus_ANALYSIS.md     # Q1+ 矿物量诊断
│   │   ├── Q7_PRECIP_CHEMISTRY.md  # Q7 降水化学集成
│   │   ├── HYDROLOGY_BOX.md         # v0.5.0 水文盒子模型设计
│   │   ├── L6_LAYER_OVERRIDES.md    # L6 逐层参数覆盖诊断
│   │   └── SENSITIVITY_INFILTRATION.md  # v0.5.1 入渗率敏感性
│   ├── guides/                 # 指南
│   │   └── GIT_GUIDE.md            # Git 协作指南
│   └── images/                 # 文档示例图（USERGUIDE 案例图）
├── tools/                      # 分析/绘图辅助脚本（从项目根运行）
│   ├── plot_pH_scenarios.py        # 4 情景 pH 对比图
│   ├── plot_ion_concentrations.py  # 离子浓度曲线图
│   ├── plot_Q7_30yr.py             # Q7 降水化学 30 年模拟图
│   ├── compare_before_after.py     # 50 年化学演化监控
│   ├── plot_exp1_4layer.py         # 实验1: 4 层 30 年演化
│   ├── plot_exp2_single_vs_multi.py# 实验2: 单层 vs 多层
│   ├── plot_exp3_plot.py           # 实验3: 表层对比
│   ├── plot_exp3_surface_onoff.py  # 实验3: SURFACE 开关对比
│   ├── plot_L6_layer_overrides.py  # L6 逐层参数覆盖诊断图
│   ├── plot_v0_5_hydrology_baseline.py  # v0.5.0 水文基线验证
│   └── sensitivity_infiltration.py  # v0.5.1 入渗率敏感性实验
├── .scratch/                   # 本地工单追踪（spec + 工单）
│   └── soil-scm-overview/
│       ├── TICKETS_SUMMARY.md  # 工单汇总表（成立时间/状态，2026-08-17 整理）
│       ├── issues/             # 开发工单 01~48
│       └── wayfinder/          # 架构决策工单 WF1~5
├── output/                     # 运行产物（gitignore，自动生成；含 output/error.inp 失败复现文件）
├── main.py                     # 主程序入口
├── requirements.txt            # Python 依赖
├── USERGUIDE.md                # 用户指南（安装/配置/情景/输出解读/FAQ）
└── README.md
```

---

## 三、配置说明

> **完整操作指南**（配置字段详解、输入数据格式、模拟情景案例、输出解读、常见问题排查）见 **[`USERGUIDE.md`](USERGUIDE.md)**。

### 引擎与入渗配置（v0.2.2）

`config.yaml` 中 `simulation` 关键参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `engine_mode` | `auto` | 引擎模式：`auto`=官方 PHREEQC 优先、不可用时自动降级简化模式；`phreeqc`=强制官方引擎；`simplified`=始终简化模式 |
| `precip_infiltration` | `0.05` | 降水入渗系数（0~1）：实际进入土壤溶液的比例，其余为径流/排水（T3） |
| `scenario` | `natural` | 情景选择（见第四节） |

### 其他常用参数

| 区块 | 参数 | 默认值 | 说明 |
|------|------|--------|------|
| `simulation` | `n_years` | `50` | 模拟年数 |
| `simulation` | `n_layers` | `1` | 分层数（v0.2.5）：`1`=单层，`4`=多分层（各层默认参数相同） |
| `simulation` | `layer_depths` | `None` | 每层厚度 cm（v0.4.0 L6）：长度必须 = n_layers，派生每层 `effective_depth`；缺省等分 0~60cm 兜底 |
| `simulation` | `layer_overrides` | `[]` | 逐层参数覆盖（v0.4.0 L6）：密集列表长度必须 = n_layers，部分覆盖 ph/有机质/CEC/容重/交换性离子/pCO2/矿物；`n_layers=1` 时忽略 |
| `simulation` | `enable_surface` | `false` | SURFACE 表面络合（v0.2.5）：`true`=启用 Hfo_s/Hfo_w 铁氧化物表面，P/Zn 吸附生效 |
| `simulation` | `enable_pre_equilibration` | `true` | 初始状态预平衡（v0.5.0，建议保持开启） |
| `simulation` | `pre_equilibration_max_steps` | `60` | 预平衡最大迭代步数 |
| `simulation` | `nitrification_k1` | `1.0` | 尿素水解速率（/月，L4；`0~1`，1.0=当月全水解） |
| `simulation` | `nitrification_k2` | `0.4` | 硝化速率（/月，L4；`0~1`，NH₄⁺→NO₃⁻ 比例） |
| `simulation` | `hydrology_seed` | `42` | 随机降雨种子（v0.5.0；同 seed 可复现） |
| `simulation` | `layer_overrides` 水文 | — | 逐层水文字段（v0.5.0）：`clay_pct`/`porosity`/`ksat`/`infiltration_initial`/`infiltration_steady`；`n_layers=4` 自动启用内置默认 |
| `simulation` | `sub_time_step_days` | `0` | 子时间步长（天）：`0`=关闭，`1~7`=启用（与月步长结果一致，Q10；水文模式不适用） |
| `climate` | `base_annual_precip` | `1893.0` | 基准年降水量（mm/yr） |
| `climate` | `base_annual_temp` | `25.0` | 基准年平均温度（°C） |
| `climate` | `precip_increase_rate` | `0.02` | `precip_increase` 情景：每年降水增加比例 |
| `climate` | `temp_increase_rate` | `0.05` | `temp_increase` 情景：每年增温幅度（°C/yr） |
| `soil_data` | `soil_type` | `red_soil` | 土壤类型标识符（用于查询矿物数据库） |
| `fertilizer` | `n / p2o5 / k2o / mgo / znso4` | `12 / 4 / 9 / 3 / 1` | 每次施用量（kg/ha），详见第五节 |
| `fertilizer` | `apply_months` | `[3, 6, 9]` | 施肥月份 |
| `lime` | `amount_per_apply` | `45.0` | 生石灰每次施用量（kg/ha，按 CaO 计），3/6/9 月 |
| `soil_co2` | `pCO2_ref` | `0.015` | 参考 CO₂ 分压（atm） |
| `soil_co2` | `T_ref` | `25.0` | 参考温度（°C） |
| `soil_co2` | `beta` | `0.05` | 土壤 CO₂ 温度响应系数（1/°C） |
| `precipitation_chemistry` | `input_file` | `config/precip_chemistry_default.json` | 回退 JSON 路径（全 -1 时读取） |
| `precipitation_chemistry` | `ph` / `ions` | `-1` | 内联降水化学（v0.2.3）：全部 -1 回退 JSON；全部有效值覆盖；混合报错 |
| `output` | `directory` | `./output` | 输出目录 |
| `output` | `format` | `csv` | 输出格式：`csv` / `netcdf`（未装 netCDF4 时回退 CSV） |
| `output` | `variables` | 见第七节 | 输出变量列表（Q11） |

> **v0.3.0 化学参数（L4/L5，位于 `src/constants.py`，非 config 字段）**：
> - `NITRIFICATION_K1 = 1.0`：尿素水解速率（/month），默认当月全水解（urease 快速）
> - `NITRIFICATION_K2 = 0.4`：硝化速率（/month），红壤酸性受抑取保守值（2-3 月完成大部分）
> - `HENRY_CO2` / `KA1_H2CO3` / `KA2_HCO3` / `KW_WATER`：碳酸体系常数（25°C），决定初始 HCO₃⁻（与 GAS_PHASE pCO₂ 联动）
> - `CHARGE_BALANCE_CL_RESIDUAL = 1e-6`：Cl⁻ 背景残留（电荷盈余大时由盈余决定）
> - `SOLUTION_TOTAL_CATION_CONC = 2e-3`：初始溶液总阳离子浓度（mol/L，土壤溶液量级）
> - 完整参数表与可修改性说明见 `docs/reports/V0_3_0_FINAL_REPORT.md` 第四节

> **v0.3.0 化学参数（L9，非晶质 Al 相）**：
> - `AMORPHOUS_ALOH3_MASS_FRACTION = 0.02`：非晶质氢氧化铝质量分数（红壤典型量级），`build_minerals()` 添加 `Al(OH)3(a)` 相（phreeqc.dat 原生相，提供 Al 缓冲源；扫描结论：无法根治 fertilizer 单层 AlX₃ 耗尽，见 `docs/reports/V0_3_0_FINAL_REPORT.md` 第六节）

> **v0.3.0 化学参数（三支柱自洽化）**：
> - `GAP_AL_FRACTION = 0.3`：CEC 缺口中 Al 占比（扫描确定：首平衡 pH 4.92 接近观测 5.0；缺口 Al/Na 按比例分配）
> - `enable_pre_equilibration: true`（config）：初始状态预平衡（交换离子锚定 + 偏离度诊断，不锚定 pH——GAS_PHASE 缓冲吸收已验证）
> - `ALX3_SELECTIVITY_LOGK = 0.41`：AlX₃ 交换 log_k（引擎 EXCHANGE_SPECIES 覆盖；**L9 扫描 0.41→10 全部无效**，结构性局限确认）
> - 完整报告见 `docs/reports/V0_3_0_FINAL_REPORT.md` 第三、六节

---

## 四、情景说明

修改 `config/config.yaml` 中的 `simulation.scenario` 字段切换情景：

| 情景 | 说明 |
|------|------|
| `natural` | 自然状态，无任何干预 |
| `fertilizer` | 定期施肥（氮磷钾镁锌，按农业农村部2021指导意见，3/6/9 月） |
| `fertilizer_lime` | 施肥 + 生石灰改良 |
| `precip_increase` | 降水逐年增加（默认 2%/yr） |
| `temp_increase` | 温度逐年升高（默认 0.05°C/yr） |

---

## 五、施肥方案（默认）

依据农业农村部《2021年春季主要农作物科学施肥指导意见》（水稻，产量 500 kg/ha），
**每次施用量**（每年 3/6/9 月各施用一次）：

| 肥料 | 按元素计 | 每次施用量 (kg/ha) |
|------|----------|--------------------|
| 氮肥 | N | 12 |
| 磷肥 | P₂O₅ | 4 |
| 钾肥 | K₂O | 9 |
| 镁肥 | MgO | 3 |
| 硫酸锌 | ZnSO₄ | 1 |
| 生石灰 | CaO | 45 |

对应 PHREEQC 输入换算：
- 氮：`NO₃⁻` + `H⁺`（硝化产酸）；磷：`H₂PO₄⁻`；钾：`K⁺`；镁：`Mg⁺²`；锌：`Zn⁺²`+`SO₄⁻²`
- 生石灰：`Ca` + `OH⁻`（CaO 水化）

---

## 六、数据文件

### `data/soil_survey.csv`

```csv
pH,有机质_g_kg,CEC_cmol_kg,容重_g_cm3,耕地面积_ha,有效土层厚度_cm,有效磷_mg_kg,速效钾_mg_kg,质地,砂粒_pct,粉粒_pct,黏粒_pct
5.0,20.0,12.0,1.2,1.0,30.0,15.0,100.0,壤土,35.0,40.0,25.0
```

### `data/exchangeable_ions.csv`

```csv
交换性Ca_cmol_kg,交换性Mg_cmol_kg,交换性K_cmol_kg,交换性Na_cmol_kg,交换性Al_cmol_kg,交换性H_cmol_kg
3.0,1.5,0.5,0.2,2.0,1.0
```

---

## 七、输出与辅助工具

### 输出文件

模拟完成后在 `output/` 目录生成：

| 文件 | 说明 |
|------|------|
| `soil_scm_<scenario>_output.csv` | 时间序列 CSV（`output.format=csv` 时） |
| `soil_scm_<scenario>_output.nc` | 时间序列 NetCDF（`output.format=netcdf` 时） |
| `pH_<scenario>.png` | 土壤 pH 演变图 |

### 输出变量

时间序列包含时间列（`year`、`month`、`time_decimal`）与以下变量（由 `config.output.variables` 控制，Q11）：

| 变量 | 说明 |
|------|------|
| `pH` | 土壤溶液 pH |
| `base_saturation` | 盐基饱和度（%） |
| `CEC_occupied` | 交换位点占据总量（cmol(+)/kg） |
| `exchangeable_Ca` | 交换性 Ca |
| `exchangeable_Al` | 交换性 Al |
| `mineral_mass` | 矿物相质量（可选，JSON 序列化） |
| `solution_ions` | 溶液中离子浓度（可选，JSON 序列化） |

> **说明**
> - `mineral_mass`、`solution_ions` 为可选诊断列，以 JSON 字符串形式存储，仅在配置中包含时输出。
> - NetCDF 格式需要安装 `netCDF4`；未安装时自动回退为 CSV（Q23）。

### 辅助分析与绘图脚本

`tools/` 下的 `plot_*.py` 为分析/绘图辅助脚本（独立运行，不参与主流程；**需从项目根目录运行** `python tools/plot_xxx.py`）：

| 脚本 | 说明 |
|------|------|
| `tools/plot_pH_scenarios.py` | 4 情景（natural / fertilizer / lime_only / fertilizer_lime）土壤 pH 演化对比图（5 年，官方引擎） |
| `tools/plot_ion_concentrations.py` | fertilizer_lime 情景 30 年 pH + 11 种离子浓度曲线（PHREEQC 溶液输出，mol/kgw） |
| `tools/plot_Q7_30yr.py` | Q7 降水化学集成 + F1 pCO₂ 传递后 natural 情景 30 年 pH 与全部离子浓度曲线 |
| `tools/compare_before_after.py` | 官方引擎 50 年 fertilizer_lime 化学演化监控（pH / 盐基饱和度 / 交换性 Al / Ca 四联图） |
| `tools/plot_exp1_4layer.py` 等 | 实验验证绘图脚本（4 层演化 / 单层 vs 多层 / SURFACE 开关） |

`output/error.inp` 为 PHREEQC 计算失败时**自动生成**的完整输入复现文件（Q18 异常分级，T01 修复）：当官方引擎 `RunString` 抛出异常并降级时，完整输入字符串写入 `output/error.inp`，每次失败刷新；写入失败不影响主流程（记录日志后继续降级模拟）。可据此复现与调试。

---

## 八、已知模型局限

1. ~~**交换性 Al 缓冲库耗尽 → pH 突变**~~ ✅ **已解决（L2，v0.2.6）**：原单层模型 + 排水使交换性 Al 淋洗耗尽（第 8 年），pH 突升至 ~10。**根因是矿物相被冻结**（`_parse_official_output` 占位实现丢弃矿物演化）——现已实现**矿物演化回填**（`-equilibrium_phases` 读取矿物摩尔量），gibbsite 溶解回补交换 Al。验证：单层 12 年 AlX3 稳定、pH 平缓至 6.46（无突升）；4 层 8 年各层 Al 保留、pH 梯度稳定。
2. **Al(OH)₄⁻ 两性溶解**：pH 升高后总 Al 浓度反而上升——Al 以铝酸根（Al(OH)₄⁻）形态碱性溶解，Al³⁺ 实际剧降（pH 10 时 ~10⁻²³）。
3. **矿物量折中**：矿物量取物理值 0.001（`mineral_scale`），以避免矿物量大导致的碱性突变，但压缩了矿物缓冲容量（详见 `docs/analysis/Q1_plus_ANALYSIS.md`）。
4. **SURFACE 与雨季交互**：启用 SURFACE（`enable_surface: true`）后，Hfo 表面质子化在雨季强入渗时加速交换 Al 耗尽，pH 上升更快——建议与多分层配合使用，独立启用会加剧。
5. **PHREEQC 无法维持溶液无机氮形态（v0.3.0 确认）**：`phreeqc.dat` 的 N 氧化还原平衡将任何注入溶液的无机氮（NH₄⁺/NO₃⁻）热力学平衡为 N₂（实测 pe=0~12 下 N(-3)/N(5)≈0）。L4 采用**模型库存层**方案（氮形态为模型状态，硝化产酸 2H⁺ 注入 REACTION）；这是既有局限的显式化——旧实现施肥氮同样 100% 流失为 N₂。
6. **fertilizer 单层长期 AlX₃ 耗尽→pH 突升（结构性局限确认，v0.5.0）**：k₂=0.4 弱产酸下 AlX₃ 被盐基置换 + 排水淋失耗尽（约第 2-3 年）→ pH 突升 ~10。**完整证伪链**（v0.4.0+v0.5.0+v0.6.0）：MINERAL_SCALE 扫描、非晶质 Al(OH)₃ 相、预平衡、缺口修正、**AlX₃ 交换 log_k（0.41→10）全部无效**，Al KINETICS 亦证据否定——确认为模型架构层局限（**排水淋失为耗尽主因**，单层排水无法模拟 Al 垂直缓冲）。**建议**：fertilizer 情景使用多层（n_layers≥4，推迟耗尽）+ 文档记录；架构级解决（多层 + L6 逐层参数）列入 backlog。详见 `docs/reports/V0_3_0_FINAL_REPORT.md` 第六节。**v0.4.0 L6 落地**：`layer_overrides` 支持逐层参数覆盖（真实剖面约束），诊断实验见 `docs/analysis/L6_LAYER_OVERRIDES.md` 与 `tools/plot_L6_layer_overrides.py`。

> ✅ **v0.1.4 已解决**：**降水化学集成（Q7）**——降水含 Cl⁻/SO₄²⁻/NO₃⁻/NH₄⁺ 等离子（据《2025年广东省生态环境状况公报》），原"保守离子 Cl⁻ 持续淋失"局限已解决（详见 `docs/analysis/Q7_PRECIP_CHEMISTRY.md`）。

> ✅ **v0.2.4 工程化改进（T01/T02/T04）**：
> - **T01**：PHREEQC 失败自动落盘 `error.inp` 复现文件（README 承诺兑现，含写入失败隔离）。
> - **T02**：气候修正机制收敛——`MonthlyAction` 移除永不生效的 `precip_factor`/`temp_offset` 死字段，气候修正明确由气候强迫生成器（ClimateForcing）承担。
> - **T04**：重复计算收敛与死函数清理——土壤质量/静态盐基饱和度/cmol 换算/pCO2 公式收敛为单一事实来源；`utils.py` 删除 6 个零调用函数。
>
> 详见 `docs/reports/V0_3_0_FINAL_REPORT.md` 第三节（工程化地基里程碑）。

> ✅ **v0.2.5 中期架构（WF1-WF5）**：
> - **多分层模型**：`n_layers` 配置（默认 1），4 层时推迟 pH 突升并建立垂直梯度（`run_monthly_multi_layer` 编排层）。
> - **SURFACE 表面络合**：`enable_surface` 配置（默认 false），Hfo_s/Hfo_w 铁氧化物表面，P/Zn 吸附显著增强（红壤磷固定）；**Al 表面络合未实现**（研究空白，独立工单）。
>
> 详见 `docs/analysis/OPTIMIZATION_PLAN.md` 的 WF1-WF5 记录。

---

## 九、后续扩展建议

| 扩展方向 | 说明 |
|----------|------|
| 多土层模式 | ✅ 已实现（v0.2.5 多分层，n_layers≥4） |
| 根系吸水 / 蒸散发 | 🔜 规划（v0.5.3 Feddes ET + Oudin PET） |
| 有机质分解 | 🔜 规划（v0.5.3 OM 矿化产 CO₂ 模块） |
| 更多肥料类型 | 支持复合肥、缓释肥等 |
| WRF 耦合 | 通过 IPhreeqc 接口与 WRF 气候输出耦合 |
| 参数敏感性分析 | 自动化扫描参数空间 |

---

## 十、主要参考文献

- 熊毅, 李庆逵. 中国土壤. 科学出版社, 1987.
- 龚子同. 中国土壤地理. 江苏科学技术出版社, 2004.
- Brook G.A., Folkoff M.E., Box E.O. A world model of soil carbon dioxide. Earth Surface Processes and Landforms, 1983, 8(1): 79-88.
- Davidson E.A., Trumbore S.E. Gas diffusivity and production of CO2 in deep soils of the eastern Amazon. Tellus B, 1995, 47(5): 550-565.
- Plummer L.N., Wigley T.M.L., Parkhurst D.L. The kinetics of calcite dissolution in CO2-water systems. American Journal of Science, 1978, 278(2): 179-216.
- Lindsay W.L. Chemical Equilibria in Soils. John Wiley & Sons, 1979.
- Parton W.J. et al. Analysis of factors controlling soil organic matter levels in Great Plains grasslands. SSSAJ, 1987, 51(5): 1173-1179.
- Tang D., Larssen T., Lange R.D. et al. Soil acidification and soil quality in China. European Journal of Soil Science, 2006, 57(1): 1-11.

---

## 十一、版本更新记录

### v0.7.2（2026-08-25，工单 83 + 工单 84 发布）

> - **工单 83 多层 CEC/BS 物理化（深层风化剖面默认）**：修复深层交换盐基库
>   单点观测外推 × 层厚 40cm 放大的物理失真——L2~L4 CEC 12→9/6/4 + 盐基淋洗 +
>   交换 Al 主导 + 风化层 GAP 偏 AlX3；L4 CaX2 90,630→9,063 / BS 56%→16% /
>   预平衡 pH 自然酸化 3.83 / 交换相:溶液 200:1→~50:1（详见 spec 83 +
>   `docs/analysis/V0_7_x_DEEP_SALT_SINK_ANALYSIS.md`）
> - **工单 84 验证探针 + natural 碱化归因**：**归因定案——natural 早期碱化 ~8 =
>   L1 自身交换盐基库释放（纯水稀释解吸 + AlX3 耗尽），与深层交换库无关**（L1
>   上游独立性结构论证 + **30y 全量实测：物理化前后 L1 轨迹最大 |Δ|=0.002**）；
>   深层关联链证伪；计算量：难步率 30.8%→21.8%、L3 占比 33%→12%（物理化数值
>   收益）、L4 仍占 71%（工单 86 靶心）（详见 spec 84 +
>   `docs/analysis/V0_7_x_ALKALIZATION_ATTRIBUTION.md` + 对比图
>   `docs/images/probe_84_attribution_v83_30y.png`）
> - **测试**：**355 passed**（工单 83/84 均无 src/ 新增，探针/验证类工单）
> - **⚠️ 科学诚实**：工单 84 探针证实工单 83 的"碱化缓解预期"不成立（L1 轨迹与
>   物理化前逐位一致）；30y 中期碱化 ~8 为表层机制伪影，修复候选转工单 79/81 或
>   新工单，工单 85 全量重跑如实记录

### v0.7.1（2026-08-25，工单 82 发布）

> - **L4 深层盐基运移数值稳定化（根因重新定位）**：真根因 = 工单 78 自引入的
>   `-step_size` KNOBS 行致预平衡第一步数值发散（IPhreeqc 3.8.6 对该行存在本身
>   敏感）→ 移除该行 + 废弃 1e-12 兜底 + 事件平衡体积 = 排水前混合体积 V_mix +
>   Q3 摩尔绝对量扣除（修复 L4 baseflow>V 溶质清空）；**30y 全量解锁**
> - **测试**：**353 passed**；详细内容见下方"v0.7.x 工单 82 详情"与
>   `docs/analysis/V0_7_x_L4_DEEP_SALT_STABILITY.md` + spec 82


### v0.7.x 工单 78（2026-08-24，未独立发布，合并于 v0.7.0 基线之上）

> - **探针证伪 `-tolerance 1e-12` 静默假收敛（关键科学发现）**：lime 高 pH 平衡在
>   `-tolerance 1e-12` 下 PHREEQC"认为收敛"（**零警告**）但返回错误解（lime 月 pH
>   4.89 未碱化 vs 真实 1e-9 下 10.18）。**工单 80 报告的"lime 10y 回落 5.59"是
>   假收敛数值伪影**——真实容差下 lime 10y 9.30 不回落（BASE_LEACHING 已修正）。
> - **双 tolerance**：预平衡（远平衡起点）用 `KNOBS_TOLERANCE_PRE=1e-12`（宽松假收敛
>   稳定；1e-9 会迭代超限返回交换相全 0 垃圾解）；模拟步（预平衡状态近平衡）用
>   `KNOBS_TOLERANCE=1e-9`（lime 高 pH 真收敛）。
> - **收敛失败检测 + 自动重试**：模拟步超限（"Maximum iterations exceeded"）→
>   提高迭代（250）重试 → 1e-12 宽松兜底（防垃圾解污染状态链）；`-convergence_tolerance`
>   显式化（1e-8）。
> - **KNOBS 参数化**：`KNOBS_ITERATIONS/KNOBS_TOLERANCE/KNOBS_TOLERANCE_PRE/
>   KNOBS_CONVERGENCE_TOLERANCE/KNOBS_STEP_SIZE` 入 constants（消除硬编码）。
> - **测试**：**351 passed**（新增 6 KNOBS 测试；4 个 PHREEQC 实测测试加预平衡反映真实流程）
> - **科学诚实**：详见 `docs/analysis/KNOBS_CONVERGENCE.md`（探针数据 + 定案 + 影响）；
>   30y 全量在模拟 1e-9 下后期深层盐基累积触发收敛重试，耗时较慢（正确性优先）

### v0.7.x 工单 82 详情（2026-08-25，已随 v0.7.1 发布）

> - **根因重新定位（数据驱动，修正 spec 82 初判）**：初判"首月事件路径 L4 体积-溶质交互"
>   被探针推翻——真根因 = **工单 78 自引入的 `-step_size 0.1` KNOBS 行**致预平衡第一步
>   （远起点大交换相）数值发散（Ca=2000/4000 垃圾解 + 交换相全 0）→ 连续 3 层失败 →
>   永久降级 → 首月事件 simplified（"Ca=4000 首月降级"实为预平衡垃圾解）。A/B 消融 +
>   v0.7.0 tag 对照确凿（同初始状态无 step_size 行成功）
> - **修复**：① 移除 `-step_size` 注入行（回退 PHREEQC 默认牛顿步长）；② 废弃 1e-12 宽松
>   兜底（提高迭代仍失败 → fallback 计数，绝不回落假收敛）；③ **Q5=A** `run_event_step`
>   平衡体积 = 排水前混合体积 `V_mix`（消除雨水事件内"排水=浓缩 3×"伪影）；④ **Q2=A**
>   Q3/drains 溶质扣除统一摩尔绝对量（修复 L4 baseflow 99.6万L>48万L 时 frac 钳 1 溶质清空）
> - **验证**：**353 passed**（+2 KNOBS 测试）；预平衡 4 层真收敛 pH=4.86；首月事件无降级、
>   L4 溶质保留/体积落回 θ_out；natural 5y phreeqc_ok=1（详见
>   `docs/analysis/V0_7_x_L4_DEEP_SALT_STABILITY.md` + spec 82）
> - **⚠️ 科学诚实**：1e-9 真收敛暴露 **natural 碱化 ~8**（独立地球化学遗留，非本工单数值
>   范围）；工单 78 报告的"短程方向带 natural 4.89→4.5"实为预平衡降级后的 simplified 伪影

### v0.7.x 工单 80（2026-08-24，未独立发布，合并于 v0.7.0 基线之上）

> - **修复 v0.6.0 事件化层间溶质传递遗漏（工单 80 核心）**：事件路径 `_run_multi_layer_events`
>   只传递 NO₃⁻ 池、无层间溶质传递（`inflow_ions` 从未更新）→ **垂直渗漏不搬盐基** →
>   fertilizer/lime 盐基滞留碱化的结构性根因。修复：每层 drains 按 `drains/V` 比例扣除
>   溶液溶质并作为 mol 注入下层（对齐月级路径 Q7 平流守恒）。
> - **E_base 伴随通道（`simulation.base_leaching`）**：出系统出口水（lateral+baseflow）携带的
>   溶液盐基当量 `E_base` → 下一场平衡前注入等当量保守 `An⁻`（`# 盐基淋失伴随`）→ Gapon 自洽
>   拽交换盐基；BS 分级降权（`bs_high` 全量 / 中间线性衰减 / `bs_low` 以下归零不注酸）。
>   **全水道版（Q4 草案）探针证伪**：drains 不搬溶质 → An⁻ 泵正反馈 → Al³⁺ 水解酸化崩盘
>   （fertilizer/lime pH 崩至 1）；修正为出系统出口（自限）。
> - **方向带全达标（sensitivity 口径）**：natural 30y 5.08→4.90（4.5~5.0 带 ✓）/
>   fertilizer 5y 6.53→2.07（<4.0 ✓）/ lime_low 10y 峰 9.22→5.59（回落 ✓）/ 排序 N<F<L ✓ /
>   无降级 ✓。A/B 分解：成效根源为 drains 传递修复，E_base 净贡献 ±0.1 pH（科学诚实见
>   `docs/analysis/V0_7_x_BASE_LEACHING.md`）
> - **配置新增**：`simulation.base_leaching.{enable/anion/bs_high/bs_low}`（默认启用；
>   `enable:false` = 工单 80 前基线）
> - **工具**：`tools/sensitivity_pH_30yr.py --no-base-leaching`；
>   `tools/compare_natural_base_leaching.py`（natural 30y A/B 叠加对比 →
>   `output/natural_pH_30yr_base_leaching_compare.png` + `docs/images/`）
> - **测试**：**345 passed**（新增 12）

### v0.7.x 工单 77（2026-08-21，未独立发布，合并于 v0.7.0 基线之上）

> - **REACTION 电荷平衡修复（charge pairing）**：实测证伪"GAS_PHASE 固定缓冲是
>   fertilizer 碱化核心障碍"（`-fixed_volume` 数值不可靠、`-fixed_pressure` 吞酸幅度
>   仅 +0.05 pH）；真因 = **REACTION 裸注入电荷不平衡**——裸阳离子（NH₄⁺ 置换
>   Ca²⁺/钾镁肥）使 PHREEQC 电荷中性约束被迫产生 OH⁻ → **伪碱化**（裸 `Ca+2 343`
>   → pH 9.28，精确复现 v0.7.0 fertilizer 8~11）；裸 `H+`（硝化产酸）**从不真正
>   酸化**。修复：净电荷注入按等当量伴随保守惰性阴离子 `An⁻`（硝化产酸/置换盐基/
>   companion acid/钾镁肥/预平衡锚定），电中性盐进入
> - **验证**：单层施肥月 pH 4.87 不碱化（伪碱化机制修复实证）；sensitivity fertilizer
>   3y 11.20 → 10.86（改善）；**333 测试全绿**（新增 9）
> - **配置新增**：`simulation.charge_pairing.{enable/anion}`（默认启用）
> - **科学诚实**：详见 `docs/analysis/V0_7_X_REACTION_CHARGE_POSTMORTEM.md`（问题复盘）
>   + `docs/analysis/V0_7_x_CHARGE_PAIRING.md`（科学发现）+ spec 77；GAS_PHASE
>   保持 `-fixed_pressure` 现状

### v0.7.0（2026-08-21）

> - **NO₃⁻ 示踪池 + 水库串联淋失（D3）**：`n_no3_pool` 逐层入 SoilState；逐场 `lost_no3 = min(pool×ΣQ/V_pool, pool)`（全局不变量 pool≥0）；垂直下移+体积稀释；bypass 携带 L1 池直通 L2；`leach_no3/n_no3_pool` 记账列（工单 70）
> - **伴随阳离子淋失（CompAn 分级注入）**：自定义惰性阴离子 `An⁻`（`SOLUTION_MASTER_SPECIES`，单元素名约束）经 REACTION 等当量注入 E_loss；按盐基饱和度分级（BS≥30 全量 / 10~30 线性衰减 / <10 酸化注入 H⁺+枯竭警告）；交换相不动靠 Gapon 自洽（工单 71）
> - **NH₄⁺ 等效置换**：施肥月水解后按交换相电荷占比注入置换盐基（当量=硝化量 343 eq/次，工单 76 调优）；`NH4X_virtual` 记账列（不进交换，CEC 守恒不破）（工单 72）
> - **D2 矿物风化集总注入**：Arrhenius 温度依赖风化碱度（`rate(T)=rate_ref×exp(−Ea/R×(1/T−1/T_ref))`，Ea=40 kJ/mol）+ `degrade_minerals` 从平衡相降级（消除矿物闪蒸供碱）；不用 KINETICS（v0.3.0 证伪）（工单 73）
> - **k_om 重参数化**：E3 三档标定（0.024/0.030/0.039 单调锚点固化），维持 0.0005（工单 74）
> - **E2 PET 机制判别**：PET 1000/1100 中间点扫描 + NaX/CaX2 时序 → 假设 A 部分成立/B/C 不成立；HX 首月清空交换相盐基消除 v0.6.0 非单调跳变（`docs/analysis/V0_7_0_PET_DISCRIMINATION.md`）（工单 75）
> - **调优 A+B+D**（工单 76）：NH₄⁺ 置换量级 857→343、HX log_k 3.0→2.8（减弱锁酸）、weathering 500+降 gibbsite/kaolinite（fertilizer 11.4→8.1）
> - **配置新增**：`simulation.companion.{enable/bypass_no3_carry/bs_high/bs_low/inert_anion/nh4_exchange}` + `simulation.weathering.{enable/rate_molc_ha_yr/ca_frac/mg_frac/k_frac/activation_energy_kJ/degrade_minerals}`
> - **验收**：`tools/verify_v0_7_0_acceptance.py` 方向带断言（natural 缓降/fertilizer<4.0/lime 回落/排序/无降级/N 收支闭合）；短程（5~10y）方向带可判，**30 年 8 情景全量被 PHREEQC 卡顿阻塞**（工单 78 双 tolerance 后暴露 L4 深层数值边界 → 工单 82，P0）
> - **科学诚实**：方向带部分达标（natural 5.34 持平接近达标；fertilizer 8.1 从 11.4 大幅改善但未达 <4.0；lime 未回落）——~~GAS_PHASE 固定缓冲吞酸是剩余障碍~~（**工单 77 探针证伪**：吞酸幅度仅 +0.05 pH；真因 = REACTION 裸注入电荷伪碱化，工单 77 配对抗酸/盐基已修复）；剩余盐基滞留 → 工单 80（drains 传递修复后 natural 4.90 / fertilizer 2.07 达标；lime 回落未真实达成，工单 78 修正为 `-tolerance 1e-12` 假收敛伪影，真实 `1e-9` 下 lime_low 10y 9.30 不回落）
> - **测试**：289 → **324 passed**；grilling Q11~Q22 定案见 spec 69 + 工单 70~76

### v0.6.1（2026-08-20）

> - **数值稳定性根治**：VIC 深层基流（L4 底部，`D_max=100/D_s=0.10/n_base=2.5/θ_c=θ_r`，防抽干 min()）+ Darcy 侧向排水（各层 `k_lat=[0.04/0.025/0.015/0.008]/f_slope=0.10`，严格 FC 闸门）——Na⁺/Cl⁻ 不再在 L4 "死胡同"累积（对治 30 年敏感性实验全部情景 4~8 年崩溃的根因）
> - **溶质随水移出 + 浓度冲洗**：侧向/基流排水按 `Q_out/V` 比例扣除溶液溶质（`n_new=max(n_old×(1−Q_out/V), C_min×V)`），交换相靠 Gapon 自动补偿；C_warn=0.5 mol/L 超限触发基流/侧向激增冲洗（`flush_L` 列）；出口记账入 event_details + 月度诊断列
> - **HX 交换酸注入**：`EXCHANGE_SPECIES H+ + X- = HX`（log_k=3.0 扫描标定，平衡 pH 4.99 收敛观测）+ `exch_h→HX`（从 Na 剥离）+ CEC 缺口 GAP_H/GAP_AL/NaX 三通道重分配——表层交换性酸库真实存在（对治 Natural pH 暴降 2.0 极端）
> - **fallback 事件级局部降级**：单场失败保留前一状态跳过，连续 N=3 次才永久降级（事件/月级分开计数，成功后重置）
> - **闭合审计**：`tools/water_salt_balance.py` 逐月水量闭合 <1% / 盐分对账 <5%
> - **验收**：`verify_v0_6_1_numerical.py`（30 年 natural 全程无降级 + L4 max 浓度 <1 mol/L + E1 预平衡 5.0 复验）；`sensitivity_pH_30yr.py --tag v061` 重跑 8 情景
> - **科学诚实**：pH 具体值不在 v0.6.1 承诺范围（数值稳定性为本版承诺）；natural 首年 pH 5.40（HX 酸库使自然回归合理范围）；E2 PET 判别留 v0.7.0
> - **grilling Q1~Q10 定案**：决策记录见 spec 62（`.scratch/soil-scm-overview/issues/62-v0_6_1-numerical-hx-spec.md`）+ 工单 63~68

### v0.6.0（2026-08-19）

### v0.6.0（2026-08-19）

> - **事件驱动化学（子步长拆分）**：`RainEvent` dataclass + `generate_events`（seed 可复现，Σ 事件=月降水）+ `run_event_step` 事件级 PHREEQC（每场全量平衡）+ 主循环嵌套（for month → for event: 水文步→化学步→月末聚合）；`run_monthly_step` 保持签名（`event_driven` 标记激活，expand-contract 门禁，既有测试零改动）
> - **化学溶液体积-θ 耦合（Q8b）**：`SOLUTION -water = θ_事件后×depth×1e5`（替换恒定 volume）；浓度按绝对量守恒换算（C_new=C_old×V_old/V_new）；月末浓缩平衡（θ 下降才触发）；交换相/矿物相绝对摩尔量不变；数值防护（θ_r 体积下限 + 单步浓缩比上限 3× + 离子浓度 >10 mol/L 判定失败）
> - **First-Flush 捕获**：月度峰值列 `flush_NO3_peak_mmol`/`flush_base_peak_mmol`（当月 L1 最大单场淋失，默认开）+ 可选事件明细 CSV `output/event_leaching_<scenario>.csv`（`output.event_output: true`）
> - **Hargreaves PET**：`calc_pet` 单入口分派（`pet_method: oudin|hargreaves`，`hargreaves_enhanced` 预留报错）；`climate.diurnal_range_deg`（默认 8.0）——Oudin 精度增强模式，下游 ET 无需感知
> - **breaking change**：`pet_method="hargreaves"` 由"预留报错"转为可用；config 新增 `simulation.event_driven`（默认 false）/`output.event_output`（默认 false）
> - **运行验证**（事件驱动 2 年 4 层 natural, seed=42）：预平衡 pH 4.92、末月表层 pH **3.86**（酸化方向，对比 v0.5.3 恒 6.94）、年均 AET 957mm（水分闭合）、First-Flush 峰值/月均比 3.15；**科学诚实**——E2 PET 敏感性 pH 非单调（600/900→3.87，1200/1400→5.49），E3 k_om 表层酸化方向达成（5.57→3.86）；3 年+ 深层盐分累积极端场景存在 PHREEQC 数值边界（留 v0.6.1），详见 `docs/analysis/OPTIMIZATION_PLAN.md` §8
> - **测试**：234 → **259 passed**（事件生成/事件级化学/体积-θ 耦合/浓缩平衡/多层 events 路径/First-Flush 输出/Hargreaves）

### v0.5.3（2026-08-19）

> - **VGM 水分特征（θ 状态迁移）**：`SoilState.stored_water` → `theta`（规范状态，L/ha 由 `vgm.theta_to_water_L` 派生）；初始 θ 由 VGM 从 `initial_psi_cm=-100`（田间持水量）正算（废弃"50% 饱和"）；化学初始溶液体积联动 `θ_init×depth×1e5`；VGM 参数三级优先级（layer_overrides 显式 > clay_pct 回归 > 红壤兜底）
> - **Feddes ET / Oudin PET**：`calc_pet_oudin` 逐月 PET（月均温+纬度）；`LayerCascade` 最前端扣除 AET_i=PET×f_root,i×α(ψ_i)（ψ 版 Feddes 四阈值，根系 60/30/10/0）；亏缺丢弃计 `et_deficit_mm`；config 新增 `latitude/pet_method/pet_monthly_climate/pet_correction_factor`
> - **LayerCascade 重构**：θ_FC 可排水量 + K(θ) Mualem 界面通量（min(上下层 ksat) 木桶短板）+ 底部深层排水；`calc_interface_flux` 纯向下（`mode="bidirectional"` 预留 v0.6.0 毛细上升）
> - **OM 矿化产 CO₂**：加性调制每层 pCO₂（`pCO₂_eff = base + k_om×OM_i`，钳制 0.05 atm）；4 层默认 OM 剖面 [30,15,8,5] 强化表层酸性
> - **输出扩展**：新增 `AET_mm`/`et_deficit_mm`/`soil_moisture_Li`/`pCO2_eff` 列；`stored_water` 列语义不变（向后兼容）
> - **breaking change**：`infiltration_initial/infiltration_steady`（Horton f0/fc）已移除，config 残留显式报错；`pet_method="hargreaves"` 报错（v0.6.0 预留）
> - **运行验证**（E1：4 层 15 年 natural, seed=42）：预平衡收敛 pH 4.92（4 层）、年均 AET 935mm（水分闭合）；**科学诚实**——末月表层 pH 6.94（仍碳酸缓冲主导），E2/E3 显示 pH 无 PET/OM 方向响应（月尾 θ 恒 θ_FC + 化学体积解耦），pH 回落依赖 v0.6.0（子步长+体积耦合+Ks 重标定），详见 `docs/analysis/OPTIMIZATION_PLAN.md` §7.6
> - **测试**：178 → **234 passed**（VGM/Feddes/OM/级联重构/输出扩展/废弃字段报错）

### v0.5.2（2026-08-18）

> - **Green-Ampt 物理入渗**：废弃 Horton + `surface_coeff` 人为系数；累积入渗能力由隐式方程
>   F − ψ_f·Δθ·ln(1+F/(ψ_f·Δθ)) = K_s·t（牛顿迭代）解出；降雨强度 > 入渗能力 → 超渗产流**自然产生**
> - **Ksat 字段拆分**：`ksat`（层间排水上限，默认 [12,1.9,0.48,0.05] cm/day，仅 LayerCascade 用）
>   + `ksat_surface`（Green-Ampt 基质导水率，默认 7.2 cm/day）；华南暴雨 >15mm/h 自然触发超渗产流
> - **大孔隙优先流**：`simulation.bypass_fraction=0.2`（config 开放）——超基质 Ks 积水 20% 绕过表层
>   直通 **L2**，**携带原始降水化学**（红壤旱地"暴雨直通深层"物理观测）
> - **硝化产酸限 L1**：`run_monthly_multi_layer` 仅 L1 执行 `advance_nitrification`（表层酸化源强化）
> - **breaking change**：`simulation.surface_infiltration_coeff` 已废弃（config 中出现报错）；
>   `tools/sensitivity_infiltration.py` 扫描参数改为 `ksat_surface`
> - **运行验证**（2 年 4 层 natural, seed=42）：入渗 66%（vs v0.5.1 的 75%）、径流 34%（自然超渗产流）、
>   优先流占径流 20%、质量守恒；**初始表层 pH 4.63（回落至红壤区间方向）**，深层保持酸性（3.2~5.3）
> - **测试**：168 → **178 passed**（Green-Ampt/Ksat 拆分/优先流/硝化限 L1/废弃字段报错）

### v0.5.1（2026-08-17）

> - **表层入渗系数 config 化**：新增 `simulation.surface_infiltration_coeff`（默认 0.75，0~1）替代 `hydrology.py` 硬编码；Horton 入渗 = min(场降水×系数, 能力)
> - ⚠️ **v0.5.2 已废弃**：`simulation.surface_infiltration_coeff` 字段于 v0.5.2 移除（Green-Ampt 物理入渗替代 Horton + surface_coeff），残留配置将显式报错——见下方 v0.5.2 记录
> - **敏感性实验**：`tools/sensitivity_infiltration.py` 表层入渗率 5%~95%（5% 间隔）对 4 层 15 年 natural 最终 pH 的扫描（seed=42，CSV 断点续跑，散点图 RdYlBu_r）；**发现层间"级联穿透阈值"**（L2~0.25 / L3~0.45 / L4~0.65 入渗系数突跃中和强酸）——详见 `docs/analysis/SENSITIVITY_INFILTRATION.md`
> - **测试**：164 → **168 passed**（+4：config 解析/校验 + surface_coeff 生效）

### v0.5.0（2026-08-17）

> - **逐层水文盒子模型**：Horton 入渗（随机日降雨 seed 可配、初渗/稳渗率、表层入渗系数 0.75）+ Ksat 层间渗漏 + 孔隙度持水 + 跨月滞水（`stored_water`）；`n_layers=4` **自动启用内置物理剖面默认**（厚度[20,20,20,40]cm/粘粒/孔隙度/Ksat/初渗/稳渗）；孔隙度反推容重 ρ=2.65(1−φ)
> - **配置**：`layer_overrides` 扩展 5 水文字段 + `hydrology_seed`（默认 42，可复现）；`n_layers=1` 完全回退现状（回归护栏）
> - **输出**：新增逐层水文列（infiltration/drainage/stored_water/runoff）
> - **基线漂移（如实记录）**：水文模式入渗量 ~14 倍于旧（年 ~1349mm vs 95mm）→ 表层 pH 升高、AlX₃ 垂直重分配（底层累积）——详见 `docs/analysis/HYDROLOGY_BOX.md`，参数（0.75 系数/入渗率/降雨假设）需结合研究区标定
> - **测试**：145 → **164 passed**（新增 19 项：水文配置/随机降雨/Horton/级联/引擎集成/main 编排）

### v0.4.0（2026-08-17）

> - **L6 逐层参数覆盖（layer_overrides）**：新增 `simulation.layer_overrides`（config 内联密集列表，长度必须 = n_layers，逐层覆盖 ph/有机质/CEC/容重/交换性离子×6/pCO2/矿物质量分数）+ `simulation.layer_depths`（每层厚度 cm，派生每层 `effective_depth`，修正输出列后缀与物理厚度错位）；部分覆盖回退默认、`n_layers=1` 忽略+警告、矿物增量替换不归一化、每层独立预平衡、月度 pCO₂ 按层注入
> - **诊断实验**：`tools/plot_L6_layer_overrides.py` 真实剖面 vs 等参基线（fertilizer 长期）对比图，逐层标注 good/bad influence（绿=缓冲增强/耗尽推迟，红=更早耗尽/酸化加剧）；实测记录见 `docs/analysis/L6_LAYER_OVERRIDES.md`
> - **版本纪律**：L6 为 L9 唯一未被证伪的结构性方向（多层 + 真实剖面约束），完整证伪链见 `docs/reports/V0_3_0_FINAL_REPORT.md` 第六节

### v0.3.1（2026-08-17）

> - **error.inp 路径修正**：PHREEQC 失败复现文件从根目录移入 `output/error.inp`（写入前自动创建目录，相关测试同步适配）
> - **文件归置**：8 个辅助绘图脚本移入 `tools/`（去掉 `_` 前缀）；删除根目录 30+ 运行日志；`output/` 3 个历史 PNG 取消跟踪（修复 .gitignore 语义）
> - **文档同步**：`docs/` 按类型分类（`reports/` / `analysis/` / `guides/`）；新增工单汇总表 `.scratch/soil-scm-overview/TICKETS_SUMMARY.md`；新增用户指南 `USERGUIDE.md`；README/USERGUIDE 全量引用同步（死链清零）

基于 PHREEQC 地球化学引擎的土壤单点物理化学数值模式，用于模拟长期（数十年）施肥、酸化、淋溶与改良条件下的土壤化学演变（pH、盐基饱和度、交换性阳离子等）。
