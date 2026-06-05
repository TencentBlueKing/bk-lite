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
