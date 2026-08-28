# APM 探针制品发布 Runbook

本文面向负责 BK-Lite 构建、镜像发布和环境初始化的运维同学，说明本版本
可用的 Java / Python / Node.js / Go 接入脚本改为系统内下载后，发布流水线
必须归档的离线包和对象存储初始化步骤。

## 1. 变更摘要

四类接入脚本都不再访问 GitHub、PyPI、npm 或 Go module 公网源。目标主机改为
从本系统下载对应离线包：

```text
{NODE_SERVER_URL}/api/v1/apm/open_api/probe/download/<制品名>
```

存储后端与节点管理安装器相同：NATS JetStream Object Store。上传命令不同，
**不要**复用 `installer_init`、`controller_package_init`、`collector_package_init`
或节点管理前端包上传接口。

| 语言 | 制品名 | 对象 key | 包内容 |
|---|---|---|---|
| Java | `opentelemetry-javaagent.jar` | `apm/probe/java/opentelemetry-javaagent.jar` | 单个 Java Agent jar |
| Python | `opentelemetry-python-wheels.tar.gz` | `apm/probe/python/opentelemetry-python-wheels.tar.gz` | `opentelemetry-distro[otlp]` 及常见 instrumentation 的 wheelhouse |
| Node.js | `opentelemetry-js-auto.tgz` | `apm/probe/nodejs/opentelemetry-js-auto.tgz` | `@opentelemetry/auto-instrumentations-node` 的离线包（含依赖） |
| Go | `opentelemetry-go-sdk.zip` | `apm/probe/go/opentelemetry-go-sdk.zip` | Go module proxy 目录树，至少含 otel / sdk / otlptracehttp 及其依赖 |

四类都要初始化。缺任意一个，对应语言的接入脚本 `curl --fail` 会失败。

首版 Java 对象 key `apm/probe/opentelemetry-javaagent.jar` 仅下载兼容；新上传
只写 `apm/probe/java/opentelemetry-javaagent.jar`。

## 2. 流水线必须改造的内容

发布流水线必须完成以下三项，缺少任意一项都不能开放对应语言的接入指引：

1. 归档上表四份**固定版本**离线包（禁止依赖 GitHub / PyPI / npm `latest`）。
2. 在部署准备期、NATS 已可用的环境中，对每个制品执行一次 `apm_probe_init`。
3. 确认各云区域 `NODE_SERVER_URL` 已配置，且目标主机能访问该地址的 8011
   （或实际 Server HTTP 端口）。

建议顺序：归档四份离线包 → 发布 Server → NATS 就绪后执行四次 `apm_probe_init`
→ 验收四个下载地址。该初始化是**部署准备期**步骤，失败应终止发布流水线并
保留原始错误。

禁止把 `apm_probe_init` 放进 Server 容器 `startup.sh` 或 `batch_init`。制品缺失
只影响接入脚本，不阻断 API、Worker、Beat、Listener 启动。启动边界见
[Server 启动顺序与服务依赖边界](server-startup-dependencies.md)。

## 3. 构建并归档产物

四份制品都必须固定版本，记录字节数和 SHA-256，不提交 Git，并至少保留上一版本
供回滚。内网无法访问公网时，由构建环境一次性拉取后作为流水线制品传递。

本版本钉死的探针号（与 Collector `0.153.0` 无关；发布时若流水线归档不同，以归档为准）：

| 语言 | 制品 | 钉死版本 |
|---|---|---|
| Java | `opentelemetry-javaagent.jar` | `opentelemetry-java-instrumentation` **v2.31.1** |
| Python | `opentelemetry-python-wheels.tar.gz` | `opentelemetry-distro[otlp]==0.65b0`，配套 SDK **1.44.0** |
| Node.js | `opentelemetry-js-auto.tgz` | `@opentelemetry/auto-instrumentations-node@0.79.0` |
| Go | `opentelemetry-go-sdk.zip` | `go.opentelemetry.io/otel` **v1.46.0**（contrib 取同期模块） |

### Java

```text
https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v2.31.1/opentelemetry-javaagent.jar
```

文件名必须是 `opentelemetry-javaagent.jar`。

### Python

在可访问 PyPI 的构建环境生成 wheelhouse，必须包含 `opentelemetry-distro[otlp]`
及其依赖，以及准备支持的常见 instrumentation（Django / Flask / FastAPI 等）。
接入脚本会 `pip install --no-index --find-links`，随后把
`opentelemetry-bootstrap -a requirements` 的结果也从同一目录安装；wheelhouse
里没有的包会安装失败，不会回退公网。

```bash
mkdir -p wheels
python -m pip download -d wheels \
  "opentelemetry-distro[otlp]==0.65b0" \
  "opentelemetry-sdk==1.44.0"
# 按产品支持的框架继续 pip download 对应已钉版本的 opentelemetry-instrumentation-*
# 禁止不带版本号的 pip download，避免构建漂移。
tar -czf opentelemetry-python-wheels.tar.gz -C wheels .
```

归档文件名必须是 `opentelemetry-python-wheels.tar.gz`，解压后目录内直接是
`.whl` 文件。

### Node.js

必须是可离线安装的包，不能只 `npm pack` 主包名（目标机仍会去 npmjs 拉依赖）。
构建环境应生成带齐依赖的 tarball，例如在锁定依赖的工程里打包，或使用
`bundledDependencies` / 完整 `node_modules` 离线包。

归档文件名必须是 `opentelemetry-js-auto.tgz`。接入脚本执行
`npm install --offline --save ./opentelemetry-js-auto.tgz`。构建必须钉
`@opentelemetry/auto-instrumentations-node@0.79.0`，禁止打包 `latest`。

### Go

zip 内必须是 `GOPROXY=file://` 可消费的 module proxy 目录树，至少包含：

```text
go.opentelemetry.io/otel
go.opentelemetry.io/otel/sdk
go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp
```

及其传递依赖。接入脚本会 `export GOSUMDB=off` 并从该目录 `go mod download`，
不再执行 `go get`。归档文件名必须是 `opentelemetry-go-sdk.zip`。模块版本钉
`go.opentelemetry.io/otel@v1.46.0` 及同期 `opentelemetry-go-contrib`，禁止不钉版本的 `go get`。

## 4. 初始化对象存储

在具备正式环境配置、且能连接该环境 NATS 的 Server 运行环境中，对每个制品执行：

```bash
python manage.py apm_probe_init \
  --artifact opentelemetry-javaagent.jar \
  --file_path /path/to/opentelemetry-javaagent.jar

python manage.py apm_probe_init \
  --artifact opentelemetry-python-wheels.tar.gz \
  --file_path /path/to/opentelemetry-python-wheels.tar.gz

python manage.py apm_probe_init \
  --artifact opentelemetry-js-auto.tgz \
  --file_path /path/to/opentelemetry-js-auto.tgz

python manage.py apm_probe_init \
  --artifact opentelemetry-go-sdk.zip \
  --file_path /path/to/opentelemetry-go-sdk.zip
```

本地开发可用 `uv run python manage.py ...`。`--artifact` 只接受上表四个名字。
命令覆盖同名对象，可重复执行。

```text
bucket: ${NATS_NAMESPACE}
key:    apm/probe/<language>/<制品名>
```

与节点管理安装器共用同一个 Object Store bucket，仅对象 key 不同。任一命令失败
视为发布失败，不得忽略退出码。每个对象上传后校验：存在、大小非零、SHA-256
与归档记录一致，且匿名下载接口返回 200。

NATS 连接超时的排查顺序与节点管理包初始化相同，见
[NATS 包初始化连接超时排查手册](nats-package-init-timeout-troubleshooting.md)。

## 5. 下载地址与云区域配置

接入脚本里的下载前缀来自云区域环境变量 `NODE_SERVER_URL`，与节点安装命令同源。
四类接入配置生成时都会读取该值；缺失或格式非法时，接入页返回
`probe_download_unavailable`，不会回退公网。

示例（`NODE_SERVER_URL=http://10.10.10.1:8011`）：

```text
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-javaagent.jar
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-python-wheels.tar.gz
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-js-auto.tgz
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-go-sdk.zip
```

注意：

- OTLP 上报地址仍是 `http://<receiver_host>:4318`，与探针下载地址不是同一个端口。
- 下载接口免登录，但只允许白名单文件名。
- 目标主机（以及 docker 构建环境）必须能访问 `NODE_SERVER_URL`，不再需要访问
  GitHub / PyPI / npm / proxy.golang.org。
- Kubernetes 脚本不在集群内 curl；注释里会带上同一下载地址，供制作应用镜像。

## 6. 验收

对四个制品分别执行：

```bash
for artifact in \
  opentelemetry-javaagent.jar \
  opentelemetry-python-wheels.tar.gz \
  opentelemetry-js-auto.tgz \
  opentelemetry-go-sdk.zip
do
  curl --fail --silent --show-error --location \
    --output "/tmp/${artifact}" \
    "${NODE_SERVER_URL%/}/api/v1/apm/open_api/probe/download/${artifact}"
  test -s "/tmp/${artifact}"
  sha256sum "/tmp/${artifact}"
done
```

摘要必须与发布记录一致。再在 APM 接入页分别选择 Java / Python / Node.js / Go
的 host 或 docker，确认生成脚本中的 curl 地址是上述系统内 URL，且不含
`github.com`、`pypi.org`、`npmjs`、`go get`。

## 7. 常见失败与定位

| 现象 | 优先检查 |
|---|---|
| `apm_probe_init` 报 `FileNotFoundError` | `--file_path` 是否指向已归档的非空文件 |
| `apm_probe_init` 报 NATS 连接超时 / TLS / 认证错误 | 按包初始化排查手册检查 NATS 与 Server 网络 |
| 下载接口 404，`probe_artifact_not_found` | 对应 `--artifact` 是否在本环境执行成功；Java 新 key 为 `apm/probe/java/...` |
| 下载接口 503，`probe_artifact_unavailable` | 运行期 NATS / Object Store 是否可用 |
| 接入页 `probe_download_unavailable` | 所选云区域是否配置了合法的 `NODE_SERVER_URL` |
| 目标主机 curl 失败 | 主机到 `NODE_SERVER_URL` 的网络、证书和端口 |
| Python `pip install --no-index` 失败 | wheelhouse 是否含 distro[otlp] 及 bootstrap 列出的 instrumentation |
| Node `npm install --offline` 失败 | tgz 是否带齐依赖，而不是只有主包 |
| Go `go mod download` 失败 | zip 是否为 GOPROXY file 目录树，且含传递依赖 |

## 8. 回滚

探针制品与 Server 镜像解耦，回滚不必回退整个 Server：

1. 取出上一已验证版本的对应离线包。
2. 再次执行 `apm_probe_init --artifact <制品名>`，覆盖对象存储中的同名对象。
3. 按第 6 节重新验收下载摘要。

不要删除 Object Store bucket 或 NATS volume 来“清理”这些文件，否则会同时丢失
节点管理安装器和采集器包。
