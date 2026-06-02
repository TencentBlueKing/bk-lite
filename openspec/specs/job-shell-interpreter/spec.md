# job-shell-interpreter Specification

## Purpose
TBD - created by archiving change job-shell-interpreter-support. Update Purpose after archive.
## Requirements
### Requirement: Shell 类型脚本默认使用 bash 解释器
Job 系统执行 Shell 类型（`script_type=shell`）脚本时，SHALL 默认使用 `bash` 作为解释器，而非 `sh`。

#### Scenario: 无 Shebang 的 Shell 脚本使用 bash 执行
- **WHEN** 用户提交 `script_type=shell` 的脚本且脚本内容不包含 Shebang 行
- **THEN** 系统 SHALL 使用 `bash -c` 执行该脚本

#### Scenario: bash 语法在默认情况下可正常执行
- **WHEN** 用户提交包含 bash 特有语法（如数组 `arr=(1 2 3)`）的脚本
- **THEN** 系统 SHALL 成功执行并返回正确结果，不报语法错误

---

### Requirement: 支持通过 Shebang 自动识别解释器
当脚本第一行为合法 Shebang 时，系统 SHALL 优先使用 Shebang 指定的解释器执行脚本。

#### Scenario: #!/bin/bash 使用 bash 执行
- **WHEN** 脚本第一行为 `#!/bin/bash`
- **THEN** 系统 SHALL 使用 `bash -c` 执行该脚本

#### Scenario: #!/bin/sh 使用 sh 执行
- **WHEN** 脚本第一行为 `#!/bin/sh`
- **THEN** 系统 SHALL 使用 `sh -c` 执行该脚本

#### Scenario: #!/usr/bin/env bash 使用 bash 执行
- **WHEN** 脚本第一行为 `#!/usr/bin/env bash`
- **THEN** 系统 SHALL 使用 `bash -c` 执行该脚本

#### Scenario: 不支持的解释器回退到默认值
- **WHEN** 脚本 Shebang 指定的解释器不在支持白名单（`sh`、`bash`、`python`、`python3`、`powershell`、`pwsh`）内
- **THEN** 系统 SHALL 忽略该 Shebang，回退使用 `SHELL_MAPPING` 默认值

---

### Requirement: sidecar 和 ansible 两条执行路径均支持解释器选择
无论目标节点使用 sidecar（nats-executor）还是 ansible 驱动，解释器选择逻辑 SHALL 保持一致。

#### Scenario: sidecar 路径传递正确的 shell 参数
- **WHEN** 目标节点 `driver=sidecar` 且脚本 Shebang 为 `#!/bin/bash`
- **THEN** 系统 SHALL 调用 `executor.execute_local(script, shell="bash")`

#### Scenario: ansible 路径传递正确的 shell 参数
- **WHEN** 目标节点 `driver=ansible` 且脚本 Shebang 为 `#!/bin/bash`
- **THEN** 系统 SHALL 在 `extra_vars` 中传递 `ansible_shell_executable: /bin/bash`

---

### Requirement: 向后兼容，现有接口无变更
本次改动 SHALL 不修改任何 API 接口字段，不引入 Breaking Change。

#### Scenario: 现有不含 Shebang 的脚本继续正常执行
- **WHEN** 现有脚本不包含 Shebang 且 `script_type=shell`
- **THEN** 系统 SHALL 使用 bash 执行（原为 sh），脚本功能不受影响（bash 兼容 sh 语法）

#### Scenario: Python/PowerShell/Batch 类型不受影响
- **WHEN** `script_type` 为 `python`、`powershell`、`bat` 之一
- **THEN** 系统 SHALL 继续使用原有解释器，不受 Shebang 解析逻辑影响

