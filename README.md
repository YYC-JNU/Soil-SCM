# Soil-SCM: 土壤物理化学数值模式

> **版本：v0.2.6**（2026-08-14）

基于 PHREEQC 地球化学引擎的土壤单点物理化学数值模式，用于模拟长期（数十年）施肥、酸化、淋溶与改良条件下的土壤化学演变（pH、盐基饱和度、交换性阳离子等）。

## 一、项目目录结构

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
├── tests/                      # pytest 单元测试（85 用例）
│   ├── conftest.py
│   └── test_*.py
├── docs/                       # 项目文档
│   ├── ROADMAP.md              # 优化路线图
│   ├── OPTIMIZATION_PLAN.md    # 问题清单与优化计划（Q1-Q26）
│   ├── V0_2_4_TICKET_SUMMARY.md # v0.2.4 工单验收汇总（T01/T02/T04）
│   ├── V0_2_5_FINAL_REPORT.md   # v0.2.5 最终总结汇报（多分层+SURFACE）
│   ├── Q1_ANALYSIS.md          # Q1 引擎分析
│   ├── Q1_plus_ANALYSIS.md     # Q1+ 矿物量诊断
│   ├── Q7_PRECIP_CHEMISTRY.md  # Q7 降水化学集成
│   ├── V0_2_0_ENGINEERING_REPORT.md
│   ├── V0_2_2_SHORT_TERM_REPORT.md
│   └── GIT_GUIDE.md            # Git 协作指南
├── .scratch/                   # 本地工单追踪（spec + 工单）
│   └── soil-scm-overview/issues/
├── output/                     # 运行产物（gitignore，自动生成）
├── _plot_pH_scenarios.py       # 辅助：4 情景 pH 对比图
├── _plot_ion_concentrations.py # 辅助：离子浓度曲线图
├── _plot_Q7_30yr.py            # 辅助：Q7 降水化学 30 年模拟图
├── _compare_before_after.py    # 辅助：50 年化学演化监控
├── error.inp                   # PHREEQC 失败输入复现文件（Q18）
├── main.py                     # 主程序入口
├── requirements.txt            # Python 依赖
└── README.md
```

## 二、依赖与安装

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

### 运行测试

```bash
# v0.2.0 起建立 pytest 测试框架（tests/，当前 85 用例）
pytest tests/ -v
```

## 三、运行模拟

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
| `simulation` | `enable_surface` | `false` | SURFACE 表面络合（v0.2.5）：`true`=启用 Hfo_s/Hfo_w 铁氧化物表面，P/Zn 吸附生效 |
| `simulation` | `sub_time_step_days` | `0` | 子时间步长（天）：`0`=关闭，`1~7`=启用（与月步长结果一致，Q10） |
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

### 运行模拟

```bash
python main.py --config config/config.yaml
```

## 四、情景说明

修改 `config/config.yaml` 中的 `simulation.scenario` 字段切换情景：

| 情景 | 说明 |
|------|------|
| `natural` | 自然状态，无任何干预 |
| `fertilizer` | 定期施肥（氮磷钾镁锌，按农业农村部2021指导意见，3/6/9 月） |
| `fertilizer_lime` | 施肥 + 生石灰改良 |
| `precip_increase` | 降水逐年增加（默认 2%/yr） |
| `temp_increase` | 温度逐年升高（默认 0.05°C/yr） |

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

## 七、输出

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

根目录下 `_*.py` 为分析/绘图辅助脚本（独立运行，不参与主流程）：

| 脚本 | 说明 |
|------|------|
| `_plot_pH_scenarios.py` | 4 情景（natural / fertilizer / lime_only / fertilizer_lime）土壤 pH 演化对比图（5 年，官方引擎） |
| `_plot_ion_concentrations.py` | fertilizer_lime 情景 30 年 pH + 11 种离子浓度曲线（PHREEQC 溶液输出，mol/kgw） |
| `_plot_Q7_30yr.py` | Q7 降水化学集成 + F1 pCO₂ 传递后 natural 情景 30 年 pH 与全部离子浓度曲线 |
| `_compare_before_after.py` | 官方引擎 50 年 fertilizer_lime 化学演化监控（pH / 盐基饱和度 / 交换性 Al / Ca 四联图） |

`error.inp` 为 PHREEQC 计算失败时**自动生成**的完整输入复现文件（Q18 异常分级，T01 修复）：当官方引擎 `RunString` 抛出异常并降级时，完整输入字符串写入 `error.inp`，每次失败刷新；写入失败不影响主流程（记录日志后继续降级模拟）。可据此复现与调试。

## 八、后续扩展建议

| 扩展方向 | 说明 |
|----------|------|
| 多土层模式 | 将单层扩展为 3-5 层，模拟垂直淋溶 |
| 根系吸水 | 添加植物根系对水分和养分的吸收 |
| 有机质分解 | 添加有机质矿化动力学模块 |
| 更多肥料类型 | 支持复合肥、缓释肥等 |
| WRF 耦合 | 通过 IPhreeqc 接口与 WRF 气候输出耦合 |
| 参数敏感性分析 | 自动化扫描参数空间 |

## 九、主要参考文献

- 熊毅, 李庆逵. 中国土壤. 科学出版社, 1987.
- 龚子同. 中国土壤地理. 江苏科学技术出版社, 2004.
- Brook G.A., Folkoff M.E., Box E.O. A world model of soil carbon dioxide. Earth Surface Processes and Landforms, 1983, 8(1): 79-88.
- Davidson E.A., Trumbore S.E. Gas diffusivity and production of CO2 in deep soils of the eastern Amazon. Tellus B, 1995, 47(5): 550-565.
- Plummer L.N., Wigley T.M.L., Parkhurst D.L. The kinetics of calcite dissolution in CO2-water systems. American Journal of Science, 1978, 278(2): 179-216.
- Lindsay W.L. Chemical Equilibria in Soils. John Wiley & Sons, 1979.
- Parton W.J. et al. Analysis of factors controlling soil organic matter levels in Great Plains grasslands. SSSAJ, 1987, 51(5): 1173-1179.
- Tang D., Larssen T., Lange R.D. et al. Soil acidification and soil quality in China. European Journal of Soil Science, 2006, 57(1): 1-11.

## 十、已知模型局限（v0.2.5）

1. ~~**交换性 Al 缓冲库耗尽 → pH 突变**~~ ✅ **已解决（L2，v0.2.6）**：原单层模型 + 排水使交换性 Al 淋洗耗尽（第 8 年），pH 突升至 ~10。**根因是矿物相被冻结**（`_parse_official_output` 占位实现丢弃矿物演化）——现已实现**矿物演化回填**（`-equilibrium_phases` 读取矿物摩尔量），gibbsite 溶解回补交换 Al。验证：单层 12 年 AlX3 稳定、pH 平缓至 6.46（无突升）；4 层 8 年各层 Al 保留、pH 梯度稳定。
2. **Al(OH)₄⁻ 两性溶解**：pH 升高后总 Al 浓度反而上升——Al 以铝酸根（Al(OH)₄⁻）形态碱性溶解，Al³⁺ 实际剧降（pH 10 时 ~10⁻²³）。
3. **矿物量折中**：矿物量取物理值 0.001（`mineral_scale`），以避免矿物量大导致的碱性突变，但压缩了矿物缓冲容量（详见 `docs/Q1_plus_ANALYSIS.md`）。
4. **SURFACE 与雨季交互**：启用 SURFACE（`enable_surface: true`）后，Hfo 表面质子化在雨季强入渗时加速交换 Al 耗尽，pH 上升更快——建议与多分层配合使用，独立启用会加剧。

> ✅ **v0.1.4 已解决**：**降水化学集成（Q7）**——降水含 Cl⁻/SO₄²⁻/NO₃⁻/NH₄⁺ 等离子（据《2025年广东省生态环境状况公报》），原"保守离子 Cl⁻ 持续淋失"局限已解决（详见 `docs/Q7_PRECIP_CHEMISTRY.md`）。

> ✅ **v0.2.4 工程化改进（T01/T02/T04）**：
> - **T01**：PHREEQC 失败自动落盘 `error.inp` 复现文件（README 承诺兑现，含写入失败隔离）。
> - **T02**：气候修正机制收敛——`MonthlyAction` 移除永不生效的 `precip_factor`/`temp_offset` 死字段，气候修正明确由气候强迫生成器（ClimateForcing）承担。
> - **T04**：重复计算收敛与死函数清理——土壤质量/静态盐基饱和度/cmol 换算/pCO2 公式收敛为单一事实来源；`utils.py` 删除 6 个零调用函数。
>
> 详见 `docs/V0_2_4_TICKET_SUMMARY.md`。

> ✅ **v0.2.5 中期架构（WF1-WF5）**：
> - **多分层模型**：`n_layers` 配置（默认 1），4 层时推迟 pH 突升并建立垂直梯度（`run_monthly_multi_layer` 编排层）。
> - **SURFACE 表面络合**：`enable_surface` 配置（默认 false），Hfo_s/Hfo_w 铁氧化物表面，P/Zn 吸附显著增强（红壤磷固定）；**Al 表面络合未实现**（研究空白，独立工单）。
>
> 详见 `docs/OPTIMIZATION_PLAN.md` 的 WF1-WF5 记录。
