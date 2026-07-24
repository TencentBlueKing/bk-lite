# Windows Telegraf 连通性检测兼容设计

## 背景

监控接入页的“测试连通性”会在所选采集节点上渲染临时 Telegraf 配置，并执行一次 `telegraf --once`。当前实现固定使用 Linux 的 Telegraf 路径、`/tmp` 临时目录和 `sh` 命令，因此 Windows 节点虽然可以通过正式 Sidecar 链路正常采集，测试任务仍会在启动 Telegraf 前失败并产生假失败结果。

## 目标

- 连通性检测根据所选节点的操作系统与 CPU 架构执行正确的 Telegraf 程序。
- Windows 节点使用 PowerShell 写入和清理临时配置；Linux 保持现有 `sh` 行为。
- Telegraf 可执行文件路径复用 NodeMgmt 的 `Collector` 定义，不在 Monitor 模块重复维护平台路径。
- 检测仍只执行一次真实采集，并将输出改写到 stdout，不向 VictoriaMetrics 写入测试指标。
- 节点或适用采集器无法解析时明确失败，不静默回退到 Linux。

## 非目标

- 不改变正式 Sidecar 采集、配置下发或服务生命周期。
- 不扩展非内置、非 Telegraf 插件的连通性检测能力。
- 不改变前端交互、任务状态模型、权限校验或超时上限。
- 不引入新的数据库字段或迁移。

## 方案选择

采用节点感知且复用 `Collector` 定义的方案。

未采用以下方案：

- 在 Monitor 模块新增 Windows 路径常量：实现较快，但与 `server/apps/node_mgmt/support-files/collectors/Telegraf.json` 形成重复配置，路径变更时容易再次漂移。
- 直接复用正式 Sidecar 配置执行检测：会让接入前检测依赖已下发配置与服务状态，扩大耦合和改动范围。

## 架构与数据流

1. `CollectDetectService.run_task` 根据任务中的 `node_id` 查询 NodeMgmt `Node`。
2. 使用节点的 `operating_system` 和规范化后的 `cpu_architecture` 解析名称为 `Telegraf` 的适用 `Collector`：优先精确架构，其次使用仓库现有的 x86_64/空架构兼容规则；不得跨操作系统回退。
3. 服务将节点操作系统和 `Collector.executable_path` 传给运行时命令构造器。
4. 运行时构造器返回命令及 Shell 类型：
   - Linux：继续使用唯一临时 TOML、`trap` 清理、`sh` 和 `telegraf --once --config`。
   - Windows：使用 `$env:TEMP` 下的唯一 TOML、Base64 UTF-8 解码写入、`try/finally` 清理，以及 `& '<collector executable>' --once --config '<config path>'`。
5. `Executor.execute_local` 使用构造器返回的 Shell 执行命令；现有超时、环境变量透传、输出脱敏与任务状态逻辑保持不变。

## Windows 命令安全

- 临时文件名由服务端生成的任务 ID 与 UUID 构成，不接受用户路径。
- Telegraf 路径来自服务端持久化的内置 `Collector` 定义，并按 PowerShell 单引号规则转义。
- TOML 内容在服务端编码为 Base64，PowerShell 通过 `[Convert]::FromBase64String` 和无 BOM 的 UTF-8 编码写入，避免脚本插值、结束标记注入和 Windows PowerShell 默认 UTF-16 编码问题。
- 清理逻辑放入 `finally`，Telegraf 正常或失败退出时删除临时配置；执行器强制终止脚本时仍由唯一文件名限制残留文件的覆盖风险。
- 密码仍通过执行环境变量传递，任务快照和执行输出继续沿用现有脱敏逻辑。

## 错误处理

- `node_id` 不存在：任务失败并返回“采集节点不存在”的安全错误。
- 节点操作系统不是 Linux 或 Windows：任务失败并返回“不支持的节点操作系统”。
- 找不到对应平台和架构的 Telegraf `Collector`：任务失败并返回“未找到适用的 Telegraf 采集器”。
- 远程执行失败：沿用现有 `sanitize_execution_result`，保存脱敏后的 stdout、stderr 与退出码。
- Windows 不得回退执行 Linux 命令，避免把平台配置问题误报为目标连通失败。

## 测试设计

按 TDD 完成以下行为测试：

1. Windows 运行时命令使用 `C:\\fusion-collectors\\bin\\telegraf.exe`、PowerShell 临时目录、Base64 UTF-8 配置写入、`--once --config` 和 `finally` 清理，不包含 `/tmp`、`trap` 或 `rm`。
2. Windows 检测任务根据节点解析 Windows Telegraf `Collector`，并以 `shell="powershell"` 调用执行器。
3. Linux 检测任务继续以 `shell="sh"` 执行现有路径，防止回归。
4. Windows 节点缺少适用采集器时明确失败，且执行器不被调用。
5. 运行现有 `test_collect_detect_service.py` 全集，验证渲染、脱敏、权限和任务状态契约不变。

## 验收标准

- Windows 节点的连通性测试实际启动 Windows Telegraf 并返回单次采集结果。
- Linux 节点的现有检测行为和测试保持通过。
- 测试过程中不写入真实指标后端，临时文件会被清理，敏感信息不进入任务快照或返回结果。
- 监控连通性检测专项测试全部通过，触及 Python 文件通过项目格式与静态检查。
