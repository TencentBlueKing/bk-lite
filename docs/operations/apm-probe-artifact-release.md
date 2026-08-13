# APM 探针制品发布 Runbook

本文面向负责 BK-Lite 构建、镜像发布和环境初始化的运维同学，说明 APM
Java 接入脚本改为系统内下载后，发布流水线必须增加的产物归档和对象存储
初始化步骤。

## 1. 变更摘要

APM 接入页为 Java（host / docker）生成的安装命令，不再从 GitHub 公网下载
`opentelemetry-javaagent.jar`。目标主机改为从本系统下载：

```text
{NODE_SERVER_URL}/api/v1/apm/open_api/probe/download/opentelemetry-javaagent.jar
```

存储后端与节点管理安装器相同：NATS JetStream Object Store。上传命令不同，
**不要**复用 `installer_init`、`controller_package_init`、`collector_package_init`
或节点管理前端包上传接口。

| 用途 | 产物 | 对象 key | 初始化命令 |
|---|---|---|---|
| Java 自动探针 | `opentelemetry-javaagent.jar` | `apm/probe/opentelemetry-javaagent.jar` | `apm_probe_init` |

当前只有这一份探针制品。Python / Node.js / Go 仍走 pip、npm、go modules，
流水线不需要为它们上传二进制。

## 2. 流水线必须改造的内容

发布流水线必须完成以下三项，缺少任意一项都不能开放 Java 接入指引：

1. 归档一份固定版本的 `opentelemetry-javaagent.jar`（禁止依赖 GitHub `latest`）。
2. 在部署准备期、NATS 已可用的环境中执行 `apm_probe_init`，把 jar 写入对象存储。
3. 确认各云区域 `NODE_SERVER_URL` 已配置，且目标主机能访问该地址的 8011
   （或实际 Server HTTP 端口）。

建议顺序：归档 jar → 发布 Server → NATS 就绪后执行 `apm_probe_init` → 验收下载
地址。该初始化是**部署准备期**步骤，失败应终止发布流水线并保留原始错误。

禁止把 `apm_probe_init` 放进 Server 容器 `startup.sh` 或 `batch_init`。制品缺失
只影响 Java 接入脚本，不阻断 API、Worker、Beat、Listener 启动。NATS 在启动期
尚未作为可靠依赖，把上传塞进启动脚本会形成“等 NATS → 启动失败 → NATS 消费者
无法起来”的循环。启动边界见
[Server 启动顺序与服务依赖边界](server-startup-dependencies.md)。

## 3. 构建并归档产物

流水线需要自行获取并归档 OpenTelemetry Java Agent，不要让运行中的接入脚本去
拉公网。建议使用 GitHub Release 的**不可变版本标签**，不要使用
`/releases/latest/`：

```text
https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v<VERSION>/opentelemetry-javaagent.jar
```

归档要求：

- 文件名必须是 `opentelemetry-javaagent.jar`。
- 文件非空；记录字节数和 SHA-256，写入本次发布记录。
- 固定版本，升级 Agent 时单独发版并重新执行初始化。
- 二进制不提交到 Git。
- 至少保留上一版本 jar，供回滚时重新上传。

内网无法访问 GitHub 时，由构建环境一次性拉取后作为流水线制品传递，后续环境
只消费归档文件。

## 4. 初始化对象存储

在具备正式环境配置、且能连接该环境 NATS 的 Server 运行环境中执行。命令工作
目录为 Server 容器或 `server/` 代码目录：

```bash
python manage.py apm_probe_init \
  --artifact opentelemetry-javaagent.jar \
  --file_path /path/to/opentelemetry-javaagent.jar
```

本地开发可用 `uv run python manage.py ...`。`--artifact` 当前只接受
`opentelemetry-javaagent.jar`。

命令会覆盖对象存储中的 latest 对象：

```text
bucket: ${NATS_NAMESPACE}
key:    apm/probe/opentelemetry-javaagent.jar
```

与节点管理安装器共用同一个 Object Store bucket（`NATS_NAMESPACE`），仅对象
key 不同。命令幂等：重复执行会覆盖同名对象。

流水线必须将命令失败视为发布失败，不得忽略退出码。上传完成后应校验：

- [ ] 对象存在且大小非零。
- [ ] 对象大小和 SHA-256 与本次归档记录一致。
- [ ] 匿名下载接口返回 200，且响应体摘要与归档一致。

NATS 连接超时的排查顺序与节点管理包初始化相同，见
[NATS 包初始化连接超时排查手册](nats-package-init-timeout-troubleshooting.md)。
把文中的 `controller_package_init` 换成 `apm_probe_init` 即可，底层都是
`JetStreamService.connect`。

## 5. 下载地址与云区域配置

接入脚本里的下载前缀来自云区域环境变量 `NODE_SERVER_URL`，与节点安装命令同源。
Java host / docker 接入配置生成时会读取该值；缺失或格式非法时，接入页返回
`probe_download_unavailable`，不会回退到 GitHub。

示例（`NODE_SERVER_URL=http://10.10.10.1:8011`）：

```text
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-javaagent.jar
```

注意：

- OTLP 上报地址仍是 `http://<receiver_host>:4318`，与探针下载地址不是同一个端口。
- 下载接口免登录，但只允许白名单文件名，不能用来下载任意对象。
- 目标主机（以及 docker 构建环境，如果把 curl 写进 Dockerfile）必须能访问
  `NODE_SERVER_URL`，不再需要访问 GitHub。
- 未初始化时该 URL 返回 404，接入脚本中的 `curl --fail` 会明确失败。

## 6. 验收

在正式环境完成初始化后执行：

```bash
curl --fail --silent --show-error --location \
  --output /tmp/opentelemetry-javaagent.jar \
  "${NODE_SERVER_URL%/}/api/v1/apm/open_api/probe/download/opentelemetry-javaagent.jar"

test -s /tmp/opentelemetry-javaagent.jar
sha256sum /tmp/opentelemetry-javaagent.jar
```

摘要必须与发布记录一致。再在 APM 接入页选择 Java + host 或 docker，确认生成
脚本中的 curl 地址是上述系统内 URL，且不含 `github.com`。

## 7. 常见失败与定位

| 现象 | 优先检查 |
|---|---|
| `apm_probe_init` 报 `FileNotFoundError` | `--file_path` 是否指向已归档的非空 jar |
| `apm_probe_init` 报 NATS 连接超时 / TLS / 认证错误 | 按包初始化排查手册检查 NATS 与 Server 网络 |
| 下载接口 404，`probe_artifact_not_found` | 初始化命令是否在本环境成功执行，对象 key 是否为 `apm/probe/opentelemetry-javaagent.jar` |
| 下载接口 503，`probe_artifact_unavailable` | 运行期 NATS / Object Store 是否可用 |
| 接入页 `probe_download_unavailable` | 所选云区域是否配置了合法的 `NODE_SERVER_URL` |
| 目标主机 curl 失败 | 主机到 `NODE_SERVER_URL` 的网络、证书和端口，而不是 GitHub |
| Python / Node / Go 脚本仍走 pip / npm / go | 预期行为，本次不托管这些 SDK |

## 8. 回滚

探针制品与 Server 镜像解耦，回滚不必回退整个 Server：

1. 取出上一已验证版本的 `opentelemetry-javaagent.jar`。
2. 再次执行 `apm_probe_init`，覆盖对象存储中的同名对象。
3. 按第 6 节重新验收下载摘要。

不要删除 Object Store bucket 或 NATS volume 来“清理”该文件，否则会同时丢失
节点管理安装器和采集器包。
