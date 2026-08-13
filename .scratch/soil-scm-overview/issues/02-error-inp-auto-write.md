# 02 — PHREEQC 失败自动落盘 error.inp 复现文件

**What to build:** 当 PHREEQC 官方引擎计算失败并降级时，将完整的失败输入字符串自动写入磁盘复现文件（而非仅保存在内存属性中），使任何使用者都能拿到失败的完整输入进行复现与调试。当前行为与文档承诺不符——README 声称"PHREEQC 计算失败时自动生成 error.inp 完整输入复现文件"，但实际仅设置内存属性，磁盘上无自动生成的文件。

**Blocked by:** None — can start immediately.

**Status:** ✅ 已完成 (implemented via /implement)

## 完成说明 (2026-08-13)

**改动内容**：
1. `src/constants.py`：新增 `ERROR_INP_PATH = "error.inp"` 常量（Q19 收敛约定）。
2. `src/phreeqc_engine.py`：`_run_official_step` 异常分支追加磁盘写入——`Path(ERROR_INP_PATH).write_text(input_string)`，写入失败 try/except 隔离，不影响降级主流程。
3. `tests/test_phreeqc_engine.py`：增强 `test_error_diagnostics_on_failure`（断言 `error.inp` 磁盘生成 + 内容含 SOLUTION/SELECTED_OUTPUT，`tmp_path` 隔离）；新增 `test_error_write_failure_does_not_break_flow`（非法路径 → 降级正常）。

**验证**：
- 完整测试套件 62 passed（含 2 个新/增强 T01 测试）。
- E2E 实测：模拟引擎失败后 `error.inp` 真实生成（1071 字节，含完整输入），降级后 pH 正常（4.998）。
- `/code-review` 双轴通过（Standards 0 硬性发现，Spec 4 条验收全达成）。

## Background（审查发现 P1）

- 文档承诺（README.md）："`error.inp` 为 PHREEQC 计算失败时自动生成的完整输入复现文件（Q18 异常分级），可据此复现与调试。"
- 实际实现（phreeqc_engine.py）：`_run_official_step` 异常分支仅执行 `self.last_error_input = input_string`（内存属性），无任何写文件逻辑。
- 根目录历史遗留的 `error.inp`（9KB）是旧文件，并非每次失败自动刷新。
- 现有测试 `test_error_diagnostics_on_failure` 只断言属性有值（`last_error_input`），不断言文件生成——测试固化了"属性"行为而非"落盘"承诺。

## 行为要求

1. 当官方引擎 `RunString` 抛出异常、引擎进入降级路径时，将完整输入字符串写入磁盘上的复现文件。
2. 复现文件命名遵循现有 `error.inp` 约定（含 Q18 标识），位于项目根或 `output/` 目录（与现有 `error.inp` 位置保持一致）。
3. 每次失败应刷新文件内容，确保反映最近一次失败输入。
4. 文件写入失败不应影响主流程（降级后继续模拟），需捕获写入异常并记录日志。

## 实现方向（供参考，非硬性要求）

- 在 `_run_official_step` 的异常分支中，于设置 `last_error_input` 之后追加写文件逻辑（`Path.write_text` 或 `open()`），路径与既有 `error.inp` 约定一致。
- 文件路径常量可收敛到 `constants.py`（遵循 Q19 常量收敛约定）。

## Acceptance criteria

- [ ] 模拟引擎失败后，磁盘上自动生成（或刷新）复现文件，内容为完整 PHREEQC 输入字符串
- [ ] 新增/修改回归测试：断言失败后文件在磁盘生成且内容包含完整输入（如含 SELECTED_OUTPUT 块），而非仅断言内存属性
- [ ] 写入失败时主流程不中断，降级路径正常完成
- [ ] 全部测试套件保持全绿
