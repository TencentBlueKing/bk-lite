## 1. 修改默认 Shell

- [x] 1.1 修改 `server/apps/job_mgmt/constants/choices.py`：将 `SHELL_MAPPING[SHELL]` 从 `"sh"` 改为 `"bash"`

## 2. 实现 Shebang 解析工具函数

- [x] 2.1 在 `server/apps/job_mgmt/services/` 中新增 `parse_shebang(script: str) -> str | None` 函数，支持解析 `#!/bin/bash`、`#!/bin/sh`、`#!/usr/bin/env bash` 等格式
- [x] 2.2 定义 `SUPPORTED_SHELLS` 白名单：`{"sh", "bash", "python", "python3", "powershell", "pwsh"}`，解析结果不在白名单时返回 `None`

## 3. sidecar 路径接入 Shebang 解析

- [x] 3.1 修改 `server/apps/job_mgmt/services/script_execution_runner.py`：在调用 `executor.execute_local()` 前，优先从 shebang 解析 shell，无结果时回退到 `SHELL_MAPPING`

## 4. ansible 路径接入 Shebang 解析

- [x] 4.1 修改 `server/apps/job_mgmt/services/execution_base_service.py` 的 `_execute_script_via_ansible()`：解析 shebang 得到解释器名，通过 `extra_vars` 传递 `ansible_shell_executable: /bin/<shell>`

## 5. 测试验证

- [x] 5.1 验证 bash 语法脚本（含数组、`[[`）在默认情况下可成功执行
- [x] 5.2 验证 `#!/bin/bash` shebang 正确触发 bash 执行
- [x] 5.3 验证 `#!/bin/sh` shebang 正确触发 sh 执行
- [x] 5.4 验证无 shebang 脚本使用默认 bash 执行
- [x] 5.5 验证 Python/PowerShell 脚本类型不受影响
- [x] 5.6 运行现有测试套件确认无回归：`cd server && make test`
