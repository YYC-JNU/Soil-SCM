# Soil-SCM: 土壤物理化学数值模式

> **版本：v0.1.2**（2026-08-11）

基于 PHREEQC 地球化学引擎的土壤单点物理化学数值模式，用于模拟长期（数十年）施肥、酸化、淋溶与改良条件下的土壤化学演变（pH、盐基饱和度、交换性阳离子等）。

## 一、项目目录结构

```
soil_scm/
├── config/
│   ├── config.yaml
│   ├── soil_mineral_db.json
│   ├── soil_mineral.tbl
│   └── precip_chemistry_default.json
├── src/
│   ├── __init__.py
│   ├── config_manager.py
│   ├── soil_database.py
│   ├── input_reader.py
│   ├── climate_forcing.py
│   ├── scenario_controller.py
│   ├── phreeqc_engine.py
│   ├── output_writer.py
│   └── utils.py
├── data/
│   ├── soil_survey.csv
│   └── exchangeable_ions.csv
├── output/
├── main.py
├── requirements.txt
└── README.md
```

## 二、依赖与安装

```bash
# 安装依赖
pip install -r requirements.txt
```

依赖清单：

- phreeqpython>=3.7.0  （PHREEQC 引擎封装；未安装时自动使用简化模式）
- numpy>=1.20.0
- pandas>=1.3.0
- matplotlib>=3.4.0
- pyyaml>=5.4.0
- netCDF4>=1.5.0

> **说明**
> - phreeqpython 1.6.2 目前只发布 cp312 预编译 wheel，在 Python 3.13 下 pip 会自动选择源码包安装——该包以"纯 Python + 预编译 viphreeqc.dll"方式分发，**无需编译工具链**，可正常安装。
> - 若 `phreeqpython` 未安装或 PHREEQC 计算块与数据库不兼容导致计算失败，引擎会自动**降级到内置简化模式**，保证模拟流程稳定运行。

## 三、运行模拟

```bash
# 运行模拟
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

- CSV / NetCDF 时间序列：`output/soil_scm_<scenario>_output.csv|.nc`
- pH 演变图：`output/pH_<scenario>.png`

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

## 十、已知模型局限（v0.1.1）

1. **交换性 Al 缓冲库耗尽 → pH 突变**：单层模型 + 排水使交换性 Al 被淋洗耗尽（约第 8 年，AlX3→0），土壤失去主要产酸源后 pH 突升至 ~10。真实红壤 Al 会下移累积，需**多分层模型**解决。
2. **保守离子（Cl⁻）持续淋失**：降水为纯水（无 Cl⁻ 输入），Cl⁻ 被排水逐年淋洗（30 年 10⁻³→10⁻¹⁷）。需集成**降水化学**（Q7）。
3. **Al(OH)₄⁻ 两性溶解**：pH 升高后总 Al 浓度反而上升——Al 以铝酸根（Al(OH)₄⁻）形态碱性溶解，Al³⁺ 实际剧降（pH 10 时 ~10⁻²³）。
4. **矿物量折中**：矿物量取物理值 0.001（`mineral_scale`），以避免矿物量大导致的碱性突变，但压缩了矿物缓冲容量（详见 `docs/Q1_plus_ANALYSIS.md`）。
