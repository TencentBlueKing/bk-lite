## Why

Job 系统脚本执行默认使用 `sh` 解释器，但绝大多数用户编写的 Shell 脚本使用 bash 语法（数组、`[[`、字符串切片等），导致"本地能跑、线上报错"的困惑。底层 executor 已经支持 `bash`，只是上层没有暴露，属于低成本高收益的改进。

## What Changes

- 将 `ScriptType.SHELL_MAPPING` 中 Shell 类型的默认解释器从 `"sh"` 改为 `"bash"`
- 在 Django 服务层新增 `parse_shebang()` 工具函数，支持从脚本首行自动识别解释器
- script_execution_runner（sidecar 路径）和 execution_base_service（ansible 路径）均使用 shebang 解析结果决定解释器，无 shebang 时回退到 `SHELL_MAPPING` 默认值
- nats-executor 无需改动（已支持 bash、sh 等多种 shell）
- ansible-executor 通过 `extra_vars` 的 `ansible_shell_executable` 参数传递解释器路径

## Capabilities

### New Capabilities

- `job-shell-interpreter`: Job 系统脚本执行的 Shell 解释器选择能力——支持通过脚本 Shebang 自动识别解释器，默认使用 bash

### Modified Capabilities

（无 spec 级别的行为变更，现有接口字段不变）

## Impact

- `server/apps/job_mgmt/constants/choices.py` — `SHELL_MAPPING` 默认值修改
- `server/apps/job_mgmt/services/script_execution_runner.py` — 新增 shebang 解析逻辑（sidecar 路径）
- `server/apps/job_mgmt/services/execution_base_service.py` — 新增 shebang 解析逻辑（ansible 路径）
- `agents/nats-executor/` — 不需要改动
- `agents/ansible-executor/` — 不需要改动
- 前端 UI — 不需要改动
- API 接口 — 不需要改动，向后兼容
