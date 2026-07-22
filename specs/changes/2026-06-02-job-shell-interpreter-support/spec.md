# 2026 06 02 Job Shell Interpreter Support

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-02-job-shell-interpreter-support/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

Job 系统支持两种执行驱动：

- **sidecar**（nats-executor，Go）：调用 `Executor.execute_local()`，通过 `shell -c "脚本内容"` 执行
- **ansible**（ansible-executor，Python）：调用 `AnsibleExecutor.adhoc()`，使用 `shell` 模块，`module_args=脚本内容`

两条路径均以命令字符串方式传递脚本内容，Shebang 行（`#!/bin/bash`）只是普通注释，**不会被系统解析**。

当前 `ScriptType.SHELL_MAPPING` 硬编码 `SHELL → "sh"`，而 nats-executor 已支持 `sh`、`bash`、`powershell` 等多种 shell，只是上层未暴露选择。

## Goals / Non-Goals

**Goals:**

- 将 Shell 类型默认解释器从 `sh` 改为 `bash`，消除"本地 bash 能跑、线上 sh 报错"问题
- 支持通过脚本 Shebang 自动识别解释器（`#!/bin/bash` → bash，`#!/bin/sh` → sh）
- sidecar 和 ansible 两条执行路径均生效
- 向后兼容：无 shebang、无显式选择时，行为与改前一致（只是默认值变为 bash）

**Non-Goals:**

- 不新增前端 UI 字段（不做显式解释器下拉选择）
- 不修改 nats-executor Go 代码
- 不修改 ansible-executor Python 代码
- 不支持 zsh、fish 等非常规 shell
- 不处理 Windows 路径的 Shebang（`#!C:\...`）

## Decisions

### D1：改造点放在 Django 服务层，而非 executor 层

**选择**：在 `server/apps/job_mgmt/services/` 层解析 Shebang，统一决定 shell，再传递给两种 executor。

**备选方案**：
- 改 nats-executor（Go）内部解析 → 需要改 agent 代码并重新部署，且 ansible 路径不受益
- 改 ansible-executor（Python）内部解析 → 同上，sidecar 路径不受益
- 新增前端 UI 选择 → 用户需要额外操作，且 Shebang 是 Unix 惯例，用户学习成本更低

**理由**：改动集中、影响两条路径、不需要重新部署 agent。

---

### D2：解释器优先级

```
shebang 解析结果 > SHELL_MAPPING 默认值（bash）
```

- 有 shebang → 用 shebang 指定的解释器（需在白名单内）
- 无 shebang → 用 `SHELL_MAPPING.get(script_type, "bash")`

不引入 API 字段覆盖层（显式 shell_interpreter 字段），保持接口简洁，后续有需求再扩展。

---

### D3：Shebang 解析白名单

只允许已知安全的解释器名称，拒绝任意路径：

```python
SUPPORTED_SHELLS = {"sh", "bash", "python", "python3", "powershell", "pwsh"}
```

解析逻辑：
- `#!/bin/bash` → `bash`（取路径末段）
- `#!/usr/bin/env bash` → `bash`（取 env 后的参数）
- 解析结果不在白名单 → 忽略，回退到默认值

---

### D4：Ansible 路径传递方式

通过 `extra_vars` 传递 `ansible_shell_executable`：

```python
executor.adhoc(
    module="shell",
    module_args=script_content,
    extra_vars={"ansible_shell_executable": f"/bin/{shell}"},
)
```

Ansible shell 模块原生支持此参数，无需改动 ansible-executor。

## Risks / Trade-offs

**[风险] 目标机器无 bash** → 执行报错 `bash: not found`，错误信息明确，用户可在脚本中写 `#!/bin/sh` 回退
**[风险] bash 默认值与现有 sh 行为不一致** → bash 向下兼容 sh 语法，实际影响极小；有严格 POSIX 需求的用户可通过 shebang 指定 sh
**[风险] Shebang 白名单遗漏** → 非白名单解释器会静默回退到默认值，行为可预期，不会报错

## Migration Plan

1. 修改 `SHELL_MAPPING[SHELL] = "bash"`
2. 在 `script_execution_runner.py` 和 `execution_base_service.py` 中加入 `parse_shebang()` 逻辑
3. 运行现有测试套件验证回归
4. 回滚方式：将 `SHELL_MAPPING[SHELL]` 改回 `"sh"` 并去掉 shebang 解析逻辑，无数据库变更，无需迁移

## Open Questions

- Python 类型脚本的 shebang（`#!/usr/bin/env python3`）是否需要支持？当前 `ScriptType.PYTHON` 已单独映射，意义不大，暂不支持。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-06-02
```

## Capability Deltas

### job-shell-interpreter

## ADDED Requirements

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

## Work Checklist

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
