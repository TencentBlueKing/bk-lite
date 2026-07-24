# 中心系统 Vector 运维接入手册

## 1. 适用范围

本文用于默认部署中的中心系统 Vector。它从 Server NATS 接收所有区域转发的日志，按 Server 发布的全局配置处理事件，再写入 VictoriaLogs。

以下对象不使用本手册中的配置，不需要随日志提取器功能改造：

- 非默认云区域的 proxy 与 fusion-collector；
- fusion-collector 内负责将 logstash、syslog、SNMP 等输入写入 NATS 的采集侧 Vector；
- webhookd、NodeMgmt 配置推送和系统 Telegraf；
- Kubernetes 日志采集 DaemonSet 等采集端 Vector。

## 2. 流水线改造边界

- Server/Web 镜像的既有构建与推送逻辑可以继续使用；日志提取器不需要新增独立镜像。
- 正式安装包或部署清单必须新增本目录的 `bootstrap.yaml`，并把默认部署的中心 Vector 从旧静态配置切换到 HTTP provider。
- 发布编排必须增加迁移、初始快照/Token、接口探测和最后启动中心 Vector 的顺序控制。
- 如果正式安装资产位于独立部署仓库或由外部安装脚本生成，应在该仓库同步修改；只发布新的 Server 镜像不会自动完成中心 Vector 切换。

## 3. 运维需要接入的接口

### 3.1 配置读取接口

| 项目 | 值 |
|---|---|
| 方法 | `GET` |
| 路径 | `/api/v1/log/open_api/system_vector/config/` |
| 认证 | `Authorization: Bearer <部署级 Token>` |
| 成功响应 | `200 application/yaml` |
| 响应头 | `X-Config-Checksum`、`X-Config-Generation`、`Cache-Control: no-store` |
| Token 缺失或错误 | `401` |
| 尚无初始快照 | `503` |

该接口返回 Server 最后一次成功发布的完整原始 YAML。它不会在请求时查询规则或临时编译配置。

`X-Config-Generation` 表示 Server 已发布的配置版本，不表示中心 Vector 已经拉取或应用该版本。

### 3.2 Token 初始化和轮换命令

在带有完整 Server 运行环境和数据库连接配置的 Server 发布镜像中执行：

```bash
python manage.py system_vector_token
```

该命令会：

1. 确保无提取规则时也存在完整的 no-op 初始快照；
2. 生成或轮换一个部署级全局 Token；
3. 在数据库中只保存 Token 摘要；
4. 在受控标准输出中一次性输出 `token=<明文>`。

每次执行都会使旧 Token 立即失效。若明文丢失，应再次执行命令并使用新 Token，不能从数据库恢复旧明文。

## 4. 部署资产

中心 Vector 固定使用 Vector `0.48.x`，启动配置使用同目录的 `bootstrap.yaml`：

```yaml
provider:
  type: http
  url: ${SYSTEM_VECTOR_CONFIG_URL}
  poll_interval_secs: 30
  config_format: yaml
  request:
    headers:
      Authorization: Bearer ${SYSTEM_VECTOR_CONFIG_TOKEN}
```

bootstrap 只能声明 HTTP configuration provider，不能同时放置 `sources`、`transforms` 或 `sinks`。不要增加 Vector 0.48 不支持的 `interpolate_env` 配置项。

## 5. 环境变量和 Secret

| 变量 | 用途 | 示例形式 |
|---|---|---|
| `SYSTEM_VECTOR_CONFIG_URL` | 配置接口完整地址 | `http://server:8000/api/v1/log/open_api/system_vector/config/` |
| `SYSTEM_VECTOR_CONFIG_TOKEN` | 部署级 Token | 由 Secret 注入，禁止写入镜像和配置仓库 |
| `VECTOR_NATS_SERVERS` | Server NATS 地址 | `nats://nats:4222` |
| `NATS_ADMIN_USERNAME` | Server NATS 用户名 | 由 Secret 注入 |
| `NATS_ADMIN_PASSWORD` | Server NATS 密码 | 由 Secret 注入 |
| `VECTOR_VICTORIA_LOGS_URL` | VictoriaLogs 基础地址 | `http://victoria-logs:9428` |

要求：

- Token、NATS 密码等凭据只能通过部署 Secret 或等价的受控环境注入；
- 禁止把 Token 写入镜像层、Git、普通流水线日志、Compose 模板明文或远程 YAML；
- 流水线执行 Token 命令和接口探测时必须关闭 shell 命令回显；
- 一个默认部署只保留一个活动 Token，不按用户、组织或云区域拆分。

## 6. 首次上线流程

顺序必须固定，不能只依赖容器编排工具的 `depends_on`：

### 第一步：执行数据库迁移

使用新 Server 镜像执行一次性 migration job：

```bash
python manage.py migrate
```

迁移失败必须终止发布。不得用 `|| true` 或其他方式忽略迁移失败。

### 第二步：生成初始快照和 Token

```bash
python manage.py system_vector_token
```

将输出的 Token 立即写入部署 Secret。不得把明文作为普通流水线产物保存。

### 第三步：启动 Server

启动 Web/ASGI、Celery worker 和其他既有 Server 进程。Celery worker 必须能注册任务：

```text
apps.log.tasks.extractor.publish_system_vector_config
```

### 第四步：探测配置接口

从中心 Vector 所在网络使用刚生成的 Token 请求配置接口。执行探测前关闭 shell 命令回显：

```bash
set +x
curl --fail-with-body --silent --show-error \
  --header "Authorization: Bearer ${SYSTEM_VECTOR_CONFIG_TOKEN}" \
  --dump-header /tmp/system-vector-config.headers \
  --output /tmp/system-vector-config.yaml \
  "${SYSTEM_VECTOR_CONFIG_URL}"
```

必须确认：

- HTTP 状态为 `200`；
- 响应体不是空文件，并且是完整 YAML；
- 存在 `X-Config-Checksum` 和 `X-Config-Generation`；
- 使用部署固定的 Vector 0.48 镜像校验响应 YAML 成功。

探测结束后删除临时响应文件。临时文件中不应包含 Token，但可能包含内部拓扑信息，仍应按部署配置处理。

### 第五步：启动中心 Vector

挂载 `bootstrap.yaml`，注入第 5 节中的变量并启动中心 Vector。容器必须配置失败重启策略。

首次 provider 请求失败时 Vector 无法构建初始拓扑，应由容器重启策略重试。运行期间的拉取失败或坏配置不会替换当前有效拓扑，Vector 会继续使用上一次成功加载的配置。

## 7. 日常版本升级

日常 Server/Web 镜像升级按以下顺序执行：

1. 执行数据库迁移，失败即停止；
2. 发布并启动新 Server 与 Celery worker；
3. 使用现有 Token 探测配置接口；
4. 按需滚动重启中心 Vector。

日常升级不要重复运行 `system_vector_token`。只要部署 Secret 未丢失且探测返回 `200`，就应复用现有 Token。

日志提取规则变化不需要重启中心 Vector。Server 会异步发布新的全局 generation，中心 Vector 每 30 秒拉取并尝试热加载。

## 8. Token 主动轮换

需要轮换 Token 时：

1. 关闭命令回显，在受控环境执行 `python manage.py system_vector_token`；
2. 立即用新 Token 覆盖部署 Secret；
3. 使用新 Token 探测配置接口并确认 `200`；
4. 重启中心 Vector，使其进程环境使用新 Token；
5. 确认中心 Vector 成功获取配置并启动或热加载。

命令完成后旧 Token 已失效，不存在双 Token 宽限期。不要先重启 Vector、后更新 Secret。

## 9. 发布与运行状态判断

日志提取器的全局发布状态只有：

- `pending`：等待生成；
- `generating`：正在生成；
- `published`：Server 已保存并可提供该 generation；
- `failed`：最新 generation 生成或任务投递失败。

`published` 不等于 Vector 已拉取或已生效。第一版没有 Vector 回调、心跳或精确 applied 状态。运行端是否加载成功，应检查中心 Vector 日志，例如：

```text
Response received
New configuration loaded successfully
Vector has reloaded
```

如果最新 generation 生成失败，配置接口仍会返回上一份成功快照，业务规则保存不会回滚，日志链路应继续工作。

## 10. 故障处理

| 现象 | 检查和处理 |
|---|---|
| 配置接口返回 `401` | 检查中心 Vector Secret 是否为当前 Token；Token 刚轮换时更新 Secret 并重启 Vector |
| 配置接口返回 `503` | 数据库迁移后执行 `system_vector_token`，确保初始快照存在 |
| Token 明文丢失 | 重新执行 `system_vector_token`，保存新 Token；旧 Token 随即失效 |
| 规则长期停留在 `pending` | 检查 Celery worker 是否运行并注册 `publish_system_vector_config` 任务 |
| 状态为 `failed` | 查看脱敏后的发布错误并手工重试；配置接口仍提供上一份有效快照 |
| Vector 首次启动失败 | 检查 Server 可达性、URL、Token、DNS、网络和响应 YAML；依赖容器重启策略重试 |
| Vector 运行中拉取失败 | 保持当前拓扑运行，修复接口或网络后等待下一次 30 秒轮询 |
| Vector 拒绝新配置 | 使用同一 Vector 0.48 镜像校验 YAML，修复 Server 生成问题；不要手工编辑远程快照 |
| 有日志但没有新提取字段 | 确认规则 generation 已发布、Vector 日志出现 reload，并只检查发布后的新日志 |

## 11. 回滚

如果只回滚业务代码且回滚版本仍提供配置接口，可保留现有 Token、bootstrap 和最后成功快照。

如果回滚到不包含该配置接口的旧 Server 版本，必须在停止旧接口前完成以下二选一操作：

1. 恢复中心 Vector 原有的完整静态配置；或
2. 保留一个仍能提供最后成功快照的兼容 Server 实例。

否则中心 Vector 下次冷启动时无法取得初始拓扑。删除日志提取器相关数据库表前，也必须先恢复静态 Vector 配置并停止 HTTP provider。

## 12. 上线验收清单

- [ ] 新 Server 镜像包含日志模块最新迁移、配置 OpenAPI 和 Celery 发布任务；
- [ ] migration job 成功，且失败会阻断发布；
- [ ] `system_vector_token` 首次执行成功，Token 已写入受控 Secret；
- [ ] 无提取规则时配置接口也返回完整 no-op YAML；
- [ ] 无 Token 和错误 Token 返回 `401`；
- [ ] 正确 Token 返回 `200 application/yaml`；
- [ ] 响应包含 checksum 和 generation；
- [ ] 响应 YAML 通过 Vector 0.48 校验；
- [ ] 中心 Vector 使用 bootstrap 启动并成功连接 Server NATS；
- [ ] 创建或修改规则后 generation 递增，Celery 成功发布；
- [ ] 中心 Vector 在 30 秒轮询周期内记录成功 reload；
- [ ] 发布后的新日志包含预期提取字段；
- [ ] 最新生成失败时仍可获取上一份有效快照；
- [ ] 非默认云区域部署、fusion-collector、webhookd、NodeMgmt 和系统 Telegraf 未发生变化。
