# 控制器安装前校验节点与 Server 时间

Status: implemented

## 问题

控制器安装依赖限时安装会话、远程执行截止时间、TLS 证书和带时间戳的运行事件。目标节点时间与 BK-Lite Server 偏差过大时，安装可能表现为令牌过期、远程任务过期、TLS 校验失败或安装后数据时间异常，当前流程没有在安装阶段给出可定位的时间偏差错误。

现有安装路径包括：

- Linux 远程安装：Server 经 SSH 在目标节点运行原生安装器。
- Windows 远程安装：云区域 Ansible Executor 经 WinRM 分发并运行原生 bootstrap。
- Linux/Windows 手动安装：运维人员在目标节点直接运行原生安装器。

页面提交安装任务时无法可靠获得目标节点时间，手动安装也没有 SSH/WinRM 凭据。因此校验不能只放在 Web API 或远程调度层，必须由节点侧原生安装器在取得安装会话后执行，才能覆盖全部安装方式。

## 目标行为

- 新版原生安装器取得安装会话后、下载控制器包和修改节点文件前，校验节点与 Server 的绝对时间偏差。
- 默认允许最大偏差为 300 秒；偏差小于或等于阈值时继续安装，超过阈值时终止安装。
- 比较 Unix 时间戳，不比较时区、时区名称或格式化时间。
- 校验同时覆盖节点时间领先和落后 Server 的情况。
- 失败信息包含节点时间、Server 时间、偏差秒数、允许阈值，以及配置 NTP/Chrony/Windows Time 后重试的建议。
- 校验只读时间，不自动修改目标节点时间或时间同步配置。
- 单节点失败只终止该节点的安装；批量任务中的其他节点继续独立执行。
- 重试安装时重新获取 Server 时间并重新校验。

## 方案

### 1. Server 提供可信时间基准

`InstallerSessionService.build_session_config()` 在现有安装会话 JSON 中增加：

```json
{
  "clock_validation": {
    "server_time_unix_ms": 1785168000123,
    "max_skew_seconds": 300
  }
}
```

- `server_time_unix_ms` 在会话响应生成末尾取当前 Server Unix 毫秒时间，尽量缩短取值到发送响应之间的间隔。
- `max_skew_seconds` 读取 `CONTROLLER_INSTALL_MAX_CLOCK_SKEW_SECONDS`，默认 `300`，配置值必须是正整数。
- 时间基准来自处理安装会话的 Server 运行环境，而不是浏览器、Celery 任务创建时间、数据库时间或节点上报时间。
- 字段位于现有一次性安装会话中，不新增未认证的时间接口，也不增加一次网络请求。

### 2. 安装器计算偏差

原生安装器请求会话前记录本地时间 `request_started_at`，完整读取并解析响应后记录 `request_finished_at`，以两者中点估算收到的 Server 时间对应的本地时刻：

```text
node_midpoint = request_started_at + (request_finished_at - request_started_at) / 2
offset_ms = node_midpoint_unix_ms - server_time_unix_ms
skew_ms = abs(offset_ms)
```

判断规则：

```text
skew_ms <= max_skew_seconds * 1000  -> 通过
skew_ms >  max_skew_seconds * 1000  -> 阻断
```

采用请求中点可吸收常见的网络往返延迟；300 秒阈值也不会把普通弱网误判为时钟异常。校验函数保持为无网络、无文件写入的纯函数，便于覆盖边界测试。

### 3. 安装步骤与错误契约

安装器在 `fetch_session` 成功后发出新的 `clock_check` 事件：

- 开始：`status=running`，消息为正在校验节点与 Server 时间。
- 通过：`status=success`，详情包含 `clock_skew_seconds` 与 `max_clock_skew_seconds`。
- 超限：`status=error`、`error_type=clock_skew`，详情额外包含：
  - `node_time`
  - `server_time`
  - `clock_offset_seconds`（保留正负方向）
  - `clock_skew_seconds`（绝对值）
  - `max_clock_skew_seconds`

错误消息不得只显示“时间不一致”，应能区分节点领先或落后。例如：

```text
Node clock is 726 seconds ahead of Server; maximum allowed skew is 300 seconds. Synchronize the node clock with NTP and retry.
```

远程安装通过现有安装事件流进入任务详情；手动 CLI/GUI 安装在本地步骤日志中展示同一错误。失败发生在包下载、解压、服务停止和目录替换之前，不需要安装回滚。

### 4. 后端任务结果兼容

- `clock_check` 加入安装事件动作映射、步骤顺序和失败类型映射。
- `clock_skew` 是不可通过原样重试恢复的环境错误；任务仍允许用户在修正节点时间后手工重试，但错误建议必须先提示同步时钟。
- 前端为 `clock_check` 增加中英文步骤名称，为 `clock_skew` 增加专用修复建议。
- `clock_check` 不加入历史任务的固定必需步骤集合。否则后端升级后，旧安装器产生的历史任务会被重新标记为缺失步骤。
- 新安装器事件可以携带新的步骤总数；旧事件原有步骤数和历史展示保持不变。

### 5. 协议与发布兼容

- 安装会话新增字段是向后兼容的：旧安装器会忽略未知 JSON 字段。
- 新安装器在 `clock_validation` 存在时必须严格校验其字段和值；字段存在但结构非法时以会话协议错误终止，不能静默跳过。
- 为支持滚动升级，新安装器连接尚未升级的旧 Server、响应中完全不存在 `clock_validation` 时暂时沿用旧行为。正式启用顺序必须为：先发布并验证各 OS/架构的新安装器及 Windows bootstrap 别名，再发布返回 `clock_validation` 的 Server。
- Server 启用新字段后，所有从最新别名下载的新安装器都会执行校验。已经离线保存的旧手动安装器无法被 Server 强制补充该能力，应在发布说明中要求重新下载安装器。
- 不修改已有安装会话 URL、令牌、下载令牌或数据库模型，不需要数据迁移。

## TLS 边界

节点必须先建立安装会话的 HTTP/TLS 连接，才能收到 Server 时间。若节点偏差已经大到导致 HTTPS/WinRM 的证书有效期校验失败，连接会在时间校验前失败，此时无法从已失败的安全通道取得可信 Server 时间。

本需求不通过关闭证书校验或新增明文时间接口绕过该边界。此类情况继续表现为会话或 WinRM TLS 连接失败，但相关连接失败建议中应补充“检查节点系统时间”提示。能够成功取得会话的安装路径则必须给出精确偏差诊断。

## 代码影响范围

### Server

- `server/apps/node_mgmt/constants/installer.py`
  - 增加最大时间偏差配置。
  - 增加 `clock_check` 步骤、`clock_skew` 错误类型所需常量或映射。
- `server/apps/node_mgmt/services/installer_session.py`
  - 在安装会话中生成 `clock_validation`。
- `server/apps/node_mgmt/utils/installer_schema.py`
  - 保留时间校验事件详情，标准化 `clock_skew` 失败。
- `server/apps/node_mgmt/utils/task_result_schema.py`
  - 识别并展示新步骤，但保持旧任务完整性判断兼容。

### 原生安装器

- `agents/sidecar-installer/setup-worker.go`
  - 扩展会话配置结构。
  - 记录会话请求起止时间。
  - 增加纯时间偏差计算与校验函数。
  - 在任何有副作用的安装步骤前发送 `clock_check` 事件并阻断超限安装。
- `agents/sidecar-installer/setup-worker_test.go`
  - 覆盖校验算法、边界和执行时序。

### Web

- `web/src/app/node-manager/utils/installerProgress.ts`
  - 增加步骤标签与失败建议映射。
- `web/src/app/node-manager/locales/zh.json`
- `web/src/app/node-manager/locales/en.json`
  - 增加中英文文案。

## 测试方案

### Server 单元测试

1. 安装会话返回整数毫秒时间和默认 300 秒阈值。
2. 自定义环境变量阈值正确进入会话。
3. 非正整数阈值不会生成可绕过校验的配置；应用采用明确的配置错误处理。
4. `clock_check` 成功、失败事件都能被标准化并保留偏差详情。
5. `clock_skew` 被归类为专用失败类型。
6. 读取旧安装任务时，不因缺少 `clock_check` 产生新的“步骤缺失”。

### Go 单元测试

1. 节点与 Server 时间相同，通过。
2. 节点领先 299 秒，通过。
3. 节点落后 299 秒，通过。
4. 正好偏差 300 秒，通过。
5. 领先 301 秒，失败且方向为 ahead。
6. 落后 301 秒，失败且方向为 behind。
7. 奇数毫秒往返时间的中点计算稳定。
8. `clock_validation` 存在但时间或阈值非法时失败。
9. 超限时未进入建目录、下载、解压、服务操作等后续步骤。
10. 旧 Server 完全不返回 `clock_validation` 时保持兼容。

### Web 测试

1. `clock_check` 显示“校验节点时间”。
2. `clock_skew` 显示时间同步修复建议。
3. 未知旧步骤和历史任务仍可正常展示。

### 手工验收

1. Linux 远程安装：目标机时间正确，安装成功。
2. Linux 远程安装：目标机分别领先、落后 10 分钟，均在下载前失败并显示偏差。
3. Windows 远程安装：重复上述三种场景。
4. Linux 与 Windows 手动安装：重复上述场景，本地安装界面或日志显示时间校验结果。
5. 批量安装中仅一台节点偏差超限，该节点失败，其他节点继续。
6. 同步失败节点时间后点击重试，校验重新执行并可继续安装。
7. 查看升级前历史任务，状态和步骤完整性不变化。

## 实施顺序

1. 先补 Server 会话契约与事件标准化测试。
2. 实现 Go 纯校验函数及边界测试。
3. 将校验接入安装器会话获取之后、任何安装副作用之前。
4. 接入后端任务摘要和前端步骤/建议文案。
5. 运行 Server、Go 和 Web 相关测试。
6. 构建并发布 Linux x86_64/arm64、Windows installer/bootstrap 产物，验证最新别名。
7. 最后发布 Server 会话字段，按手工验收清单验证四条安装路径。

## 不在本次范围

- 自动修改节点时间、时区、NTP/Chrony/Windows Time 配置。
- 持续监控已安装节点的时钟偏差。
- 在节点列表增加长期时间同步状态字段。
- 用浏览器时间作为 Server 时间。
- 为规避错误系统时间而关闭 Windows WinRM、HTTPS、NATS 的证书校验。
