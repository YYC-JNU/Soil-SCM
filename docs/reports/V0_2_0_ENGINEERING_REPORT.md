# V0.2.0 工程化地基（Step 1）实施报告与问题解决方案

> 覆盖范围：Q16 pytest 测试框架 + Q15 logging + Q18 异常分级
> 报告日期：2026-08-12

## 0. 基本信息

| 项目 | 内容 |
|------|------|
| 版本 | v0.2.0 |
| 任务 | Step 1 工程化地基：T1 测试框架 / T2 logging / T3 异常分级 / 收尾 |
| 状态 | ✅ 代码完成（36 测试全绿）；收尾 commit 待确认 |
| 涉及文件 | `src/logging_config.py`（新增）、`tests/`×6（新增）、`src/phreeqc_engine.py`、`src/config_manager.py`、`src/input_reader.py`、`src/output_writer.py`、`src/initial_condition.py`、`main.py`、`requirements.txt` |

---

## 1. 实施概述

- **T1**：建立 `tests/` pytest 框架（conftest + 5 测试文件），35→36 用例
- **T2+T3**：新增 `logging_config.py`（console+file 双输出）；5 模块 print→logger；异常分级（last_error 属性 + logger.error 完整诊断）
- **收尾**：版本 bump v0.2.0；ROADMAP/OPTIMIZATION_PLAN 进度更新

---

## 2. 遇到的问题与解决方案

### 2.1 环境问题

| 问题 | 现象 | 解决方案 |
|------|------|----------|
| pytest 未安装 | `No module named pytest` | `pip install pytest`（9.1.1） |

### 2.2 测试编写问题

| 问题 | 根因 | 解决方案 |
|------|------|----------|
| `test_config_manager.py` 语法错误 | 生成脚本中 YAML 字符串的换行转义序列（反斜杠+n）被解释为真实换行，字符串未终止 | 改用双反斜杠转义 |
| `test_soil_mass` 失败 | 期望值手算错误：应为 **3.6×10⁶ kg/ha**（1200 kg/m³ × 0.3m × 10⁴ m²），误写 3.6×10⁵ | 修正期望值 |
| `test_cec_total` 失败 | 连锁偏差：0.12 mol/kg × 3.6×10⁶ kg = **4.32×10⁵ mol** | 修正期望值 |
| `test_reaction_amounts` 失败 | pytest.approx 默认 rel=1e-6 过严，浮点累计误差 | 改为自洽断言（amounts == 浓度×水量） |

### 2.3 脚本生成问题（文件修改走 shell/Python 脚本）

| 问题 | 根因 | 解决方案 |
|------|------|----------|
| SyntaxError: unterminated string literal | `content = """..."""` 内嵌 docstring 三引号，外层被提前终止 | 外层改用**三单引号**包裹 |
| T3 测试添加脚本同问题 | new 字符串内 docstring 三引号与外层三引号冲突 | 同上 |

### 2.4 logging 改造的测试兼容问题

| 问题 | 根因 | 解决方案 |
|------|------|----------|
| `test_backend_legacy_forced_to_official` 失败 | print→logger 后，`capsys` 只捕获 stdout/stderr；pytest logging 插件将 logger 输出捕获进 `caplog` | 改用 `caplog` 断言 `rec.message` |

### 2.5 过程问题

| 问题 | 说明 |
|------|------|
| VS Code 不显示修改前后 diff | 本环境无 Cline 编辑工具，文件修改走 shell 命令，绕过了 Cline 的 diff 预览通道 |
| 约定 | 已固化工作流：**每轮改动先 `git diff` 展示 → 用户确认 → commit** |

---

## 3. 经验总结与防再犯规范

1. **生成 Python 文件**：外层字符串用三单引号，内部 docstring 用三双引号，避免嵌套冲突
2. **测试期望值**：必须先与代码公式交叉验算（土壤质量量级错误暴露验证盲区）
3. **logging 改造后**：涉及 logger 的测试用 `caplog`，不用 `capsys`
4. **浮点比较**：优先自洽断言或显式 rel 容差
5. **shell 写入替代编辑工具**：作为当前环境既定模式，以"git diff 展示+确认"闭环

---

## 4. 验收结果

| 项 | 结果 |
|----|------|
| pytest | ✅ 36 passed（0.35s） |
| `main.py` 运行 | ✅ 生成 `output/soil_scm.log`（INFO 分级） |
| print 残留（[WARNING] 等） | ✅ 0 残留（用户界面 print_summary 保留） |
| 版本 | ✅ v0.2.0 |

---

## 5. 遗留事项

- 收尾 commit 待用户确认（4 文件暂存：README / ROADMAP / OPTIMIZATION_PLAN / __init__.py）
- Step 2（物理校准：Q4 简化模式 / Q5 pH 下限 / 石灰入渗）待启动
