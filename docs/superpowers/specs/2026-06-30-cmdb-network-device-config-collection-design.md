# CMDB 网络设备配置文件采集设计

## 背景

当前 CMDB 已支持主机配置文件采集：CMDB 创建采集任务，Stargazer 执行采集，结果通过 `receive_config_file_result` 回调进入 `ConfigFileService`，最终以 `ConfigFileVersion` 归档并支持版本比对。

本设计扩展同一条配置文件版本链路，使 CMDB 支持对网络设备执行只读配置命令，并把命令输出作为配置文件版本挂到已有网络设备实例下。驱动在 Stargazer 侧实现，优先使用 Netmiko。

## 目标

- 支持对已有网络设备实例采集配置内容。
- 复用现有配置文件版本归档、diff、订阅触发和任务闭环能力。
- Stargazer 使用 Netmiko 连接网络设备，逐条执行用户配置的只读命令。
- 支持多行命令输入：每行一条命令，空行忽略，按顺序执行，最终合并为一份配置内容。
- 支持可选 enable/特权模式，默认不提权，必须显式启用。
- 前端、CMDB 后端、Stargazer 执行端都要有命令安全校验。
- 日志不得暴露密码、enable 密码或完整命令输出。

## 非目标

- 不做网络设备发现或自动创建设备实例。
- 不支持非内置网络设备模型。
- 不承诺 Netmiko 支持所有品牌、型号和命令。
- 不执行配置变更命令，不使用 `send_config_set`。
- 不把多条命令拆成多份配置版本；第一版合并为一份配置文件内容。

## 支持范围

MVP 只支持以下 CMDB 模型下的实例：

- `switch`
- `router`
- `firewall`
- `loadbalance`

这些模型在 `server/apps/cmdb/support-files/model_config.xlsx` 中均包含统一字段：

- `ip_addr`：管理 IP
- `port`：管理端口
- `brand`：厂商
- `model`：型号
- `soid`：sysObjectID

前端实例选择器只允许选择这四类模型下的实例。实例必须满足：

- `brand` 非空。
- `brand` 可映射到受支持的 Netmiko `device_type`。

后端保存任务时必须再次校验这些条件，防止 API 绕过前端约束。

## 品牌与驱动映射

采集执行依赖 Netmiko 的 `device_type`，不是直接依赖展示用品牌。CMDB 使用实例字段 `brand` 推导 `device_type`。

第一版内置映射建议如下：

| brand 归一化值 | Netmiko device_type |
| --- | --- |
| 华为 / Huawei | `huawei` |
| H3C / HP Comware / Hewlett-Packard | `hp_comware` |
| Cisco | `cisco_ios` |
| Juniper | `juniper_junos` |
| F5 | `f5_tmsh` |
| Fortinet | `fortinet` |

前端在任务表单中展示小提示：

> 当前支持厂商：华为/Huawei、H3C/HP Comware、Cisco、Juniper、F5、Fortinet。不在支持范围内的设备暂不支持配置采集。

支持品牌映射由 CMDB 后端提供，前端通过接口获取后渲染提示和禁选逻辑，避免前后端各维护一份枚举导致不一致。Stargazer 保留同名执行端常量作为最终执行校验，CMDB 下发的 `device_type` 必须命中 Stargazer 支持列表。

如果实例 `brand` 为空，前端禁选并提示：

> 该设备缺少厂商字段，无法匹配采集驱动，请先补充厂商。

如果实例 `brand` 不在支持范围内，前端禁选并提示：

> 当前厂商暂不支持网络配置采集。

## 任务参数

网络设备配置采集任务需要以下业务参数：

- `config_name`：配置名称，用户手动填写，例如 `running-config`。
- `commands`：采集命令，多行文本，每行一条命令。
- `need_enable`：是否需要 enable/特权模式，默认 `false`。
- `collect_task_id`：CMDB 采集任务 ID。
- `target_model_id`：目标实例模型，例如 `switch`。
- `target_instance_id`：目标实例 ID。
- `callback_subject`：固定为 `receive_config_file_result`。

由 CMDB 根据实例与凭据补齐的执行参数：

- `host` 或 `hosts`：目标设备管理 IP。
- `port`：优先使用凭据端口，其次使用实例 `port`，两者都为空时默认 `22`。
- `username`：SSH 用户名。
- `password`：SSH 密码，使用现有加密字段和环境变量占位机制下发。
- `enable_password`：特权密码，仅当 `need_enable=true` 时需要和下发。
- `device_type`：由实例 `brand` 推导出的 Netmiko 驱动。

## 前端交互

任务表单沿用配置文件采集的新增任务抽屉体验，但目标对象切换为网络设备实例。

表单字段：

- 任务名称。
- 周期。
- 组织。
- 接入点。
- 选择网络设备实例。
- 配置名称。
- 采集命令，多行 textarea，每行一条命令。
- 是否需要特权模式。
- SSH 凭据；当启用特权模式时展示并要求特权密码。

选择实例时：

- 仅展示或允许选择 `switch/router/firewall/loadbalance`。
- `brand` 为空的实例置灰不可选。
- `brand` 不支持的实例置灰不可选。
- 批量选择时跳过不可选实例，并提示跳过数量和原因。

命令输入时：

- 前端按换行切分命令，空行忽略。
- 每条命令都进行危险命令提示。
- 命中危险命令时禁止保存，并明确标出问题行。

## 命令安全

命令安全必须有三层校验：

1. 前端输入提示和保存拦截。
2. CMDB 后端保存任务时校验。
3. Stargazer 执行前最终校验。

第一版采用黑名单策略，拦截明显危险命令。黑名单匹配应优先按命令首词和明确危险组合判断，避免误伤只读命令。

建议拦截示例：

- `configure`
- `conf t`
- `reload`
- `reboot`
- `reset`
- `delete`
- `erase`
- `format`
- `write erase`
- `copy`
- `scp`
- `tftp`
- `ftp`
- `install`
- `upgrade`
- `commit`
- `save`
- `shutdown`
- `undo`
- `set`

注意：不能简单按全文包含匹配。例如 `display saved-configuration` 是只读查看命令，不应因包含 `save` 字符串被拦截。

## Stargazer 执行设计

Stargazer 新增网络设备配置采集插件，例如：

- `agents/stargazer/plugins/inputs/network_config_file/plugin.yml`
- `agents/stargazer/plugins/inputs/network_config_file/network_config_file_info.py`

执行流程：

1. 校验 `device_type`、`config_name`、`commands`、凭据和目标 IP。
2. 按换行切分 `commands`，空行忽略。
3. 对每条命令执行危险命令校验。
4. 使用 Netmiko `ConnectHandler` 建立连接。
5. 如果 `need_enable=true`，调用 `net_connect.enable()`。
6. 根据 `device_type` 执行关闭分页命令。
7. 按顺序逐条执行命令。
8. 每条命令记录结构化执行结果：`command`、`status`、`output`、`error`、`duration_ms`。
9. 全部成功时合并输出，构造配置文件回调 payload。
10. 任一命令失败时整体 `status=error`，返回错误详情，不写成功版本。

分页和大输出处理可参考已有 AutoMate 项目做法：

- 为常见 `device_type` 维护关闭分页命令。
- 大输出命令或 `pattern not detected` 时，兜底使用 `send_command_timing`。
- 续页次数设置上限，例如 `MAX_PAGER_PAGES`，避免无限读取。
- 清理分页提示符后再合并内容。

建议维护常量：

- `BRAND_DEVICE_TYPE_MAP`
- `DEVICE_TYPE_DISABLE_PAGING`
- `LARGE_OUTPUT_COMMANDS`
- `PAGER_PROMPT_PATTERNS`
- `COMMAND_ERROR_PATTERNS`
- `DANGEROUS_COMMAND_RULES`

## 逐条命令结果与合并格式

每条命令独立执行，独立记录结果。采集完成后合并为一份文本内容。

合并格式：

```text
===== command: show running-config =====
<output>

===== command: show version =====
<output>
```

整体状态规则：

- 全部命令成功：`status=success`，合并内容 base64 编码后回调。
- 任一命令失败：`status=error`，错误详情包含失败命令和逐条摘要，不生成成功版本。

失败类型包括：

- 连接失败。
- 认证失败。
- enable 失败。
- 命令超时。
- Netmiko 执行异常。
- 输出命中设备错误提示，例如 `Invalid input`、`Unknown command`、`Ambiguous command`、`Incomplete command`。

## 回调与版本归档

继续复用 CMDB 现有 `receive_config_file_result` 回调和 `ConfigFileService.process_collect_result`。

成功回调建议字段：

```json
{
  "collect_task_id": 1001,
  "instance_id": "<网络设备实例标识>",
  "instance_name": "<网络设备实例名或管理IP>",
  "model_id": "switch",
  "file_path": "network://running-config",
  "file_name": "running-config",
  "version": "1780000000000",
  "status": "success",
  "size": 12345,
  "error": "",
  "content_base64": "<base64>"
}
```

其中：

- `file_name` 使用用户填写的 `config_name`。
- `file_path` 使用稳定伪路径 `network://<config_name>`，确保同一实例同一配置名称形成连续版本线。
- `model_id` 使用目标实例模型 ID。

失败回调：

- `status=error`。
- `content_base64=""`。
- `error` 包含简洁错误摘要，最大长度 2000 字符，超出后截断并追加截断标记。
- 可在错误摘要中包含逐条命令状态，但不包含完整输出。

## 日志与敏感信息

日志只能记录：

- `task_id`
- `host`
- `model_id`
- `device_type`
- `command`
- `status`
- `duration_ms`
- 错误类型和简短错误信息

日志禁止记录：

- `password`
- `enable_password`
- 完整命令输出
- `content_base64`
- 凭据池明文

完整输出只走回调 payload，最终由 CMDB 配置文件版本内容保存机制处理。

## 错误处理

CMDB 保存阶段：

- 目标模型不在支持范围内：拒绝保存。
- 实例 `brand` 为空：拒绝保存。
- 实例 `brand` 不支持：拒绝保存。
- 命令为空：拒绝保存。
- 命中危险命令：拒绝保存。
- `need_enable=true` 但未配置特权密码：拒绝保存。

Stargazer 执行阶段：

- 参数缺失：返回 `error`。
- 连接或认证失败：返回 `error`。
- enable 失败：返回 `error`。
- 单条命令失败：记录本条失败，继续执行剩余命令，最终整体返回 `error`。
- 所有命令成功：返回 `success`。

继续执行剩余命令的原因是提升诊断价值；整体仍保持严格，不把半成功结果写为成功版本。

## 测试策略

CMDB 后端测试：

- 支持模型校验：仅允许 `switch/router/firewall/loadbalance`。
- 实例 `brand` 为空时拒绝保存。
- 不支持品牌时拒绝保存。
- 支持品牌能正确映射 `device_type`。
- 多行命令切分和危险命令校验。
- `config_name` 生成稳定 `network://<config_name>` 伪路径。

Stargazer 测试：

- `brand/device_type` 支持校验。
- Netmiko 连接参数构造不泄露敏感信息。
- `need_enable=true` 时调用 enable。
- 多命令逐条执行并合并输出。
- 单条命令失败时整体失败，但保留逐条摘要。
- 分页提示清理和大输出兜底。
- 日志不包含密码、enable 密码、完整输出和 base64 内容。

前端测试：

- 实例选择器禁选 `brand` 为空实例。
- 实例选择器禁选不支持品牌实例。
- 支持品牌 tip 展示。
- 命令 textarea 按行校验危险命令。
- 启用特权模式时展示并要求特权密码。
