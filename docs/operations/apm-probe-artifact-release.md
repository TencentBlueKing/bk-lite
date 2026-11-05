# APM 探针制品发布 Runbook

本文面向负责 BK-Lite 构建、镜像发布和环境初始化的运维同学，说明接入脚本改为
系统内下载后，发布流水线必须归档的离线包和对象存储初始化步骤。当前范围是
Java、Python、Node.js、Go、PHP、.NET Linux、.NET Windows、OBI、Ruby、C++、Erlang/Elixir 和 Swift。

## 1. 变更摘要

接入脚本不再访问 GitHub、PyPI、npm、NuGet、PECL、Packagist、RubyGems、Hex 或 Go module 公网源。
目标主机改为从本系统下载对应离线包：

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
| Go | `opentelemetry-go-sdk.zip` | `apm/probe/go/opentelemetry-go-sdk.zip` | Go module proxy 目录树，含 otel / sdk / otlptracehttp、otelhttp / otelgrpc / otelgin / otelecho 及其依赖 |
| PHP | `opentelemetry-php-auto-linux-glibc-x64.tar.gz` | `apm/probe/php/opentelemetry-php-auto-linux-glibc-x64.tar.gz` | 自建包：`php/8.1`–`8.4/nts/opentelemetry.so`，以及 `dist/` 里钉死的 Composer 包和传递依赖 |
| .NET Linux | `opentelemetry-dotnet-auto-linux-glibc-x64.zip` | `apm/probe/dotnet/opentelemetry-dotnet-auto-linux-glibc-x64.zip` | 官方 `opentelemetry-dotnet-instrumentation-linux-glibc-x64.zip` 原文件；仅 Linux x86_64 glibc |
| .NET Windows | `opentelemetry-dotnet-auto-windows.zip` | `apm/probe/dotnet/opentelemetry-dotnet-auto-windows.zip` | 官方 `opentelemetry-dotnet-instrumentation-windows.zip` 改名；仅 Windows x64 主机 |
| eBPF | `opentelemetry-ebpf-obi-linux-amd64.tar.gz` | `apm/probe/ebpf/opentelemetry-ebpf-obi-linux-amd64.tar.gz` | 官方 `obi-v1.0.0-linux-amd64.tar.gz` 改名；只收 amd64 |
| Ruby | `opentelemetry-ruby-sdk.tar.gz` | `apm/probe/ruby/opentelemetry-ruby-sdk.tar.gz` | gem `cache/`：sdk 1.13.1、exporter-otlp 0.37.0、instrumentation-rack 0.31.2 及运行时依赖 |
| C++ | `opentelemetry-cpp-sdk.tar.gz` | `apm/probe/cpp/opentelemetry-cpp-sdk.tar.gz` | v1.30.0 的安装前缀 `prefix/`，只含 OTLP/HTTP |
| Erlang/Elixir | `opentelemetry-erlang-sdk.tar.gz` | `apm/probe/erlang/opentelemetry-erlang-sdk.tar.gz` | 已解包的 `opentelemetry` 1.7.0、`opentelemetry_exporter` 1.11.0、`opentelemetry_api` 1.5.0 及编译所需的 Hex 传递依赖 |
| Swift | `opentelemetry-swift-sdk.tar.gz` | `apm/probe/swift/opentelemetry-swift-sdk.tar.gz` | `opentelemetry-swift` 2.6.0、配套 core 2.6.0，以及 HTTP exporter 的本地 path 依赖 |

十二份都要初始化。缺任意一个，只影响使用该制品的接入脚本。
相对已经交付的 Java、Python、Node.js、Go 和 .NET Linux，本次流水线新增 PHP、.NET Windows、eBPF、Ruby、C++、Erlang/Elixir 和 Swift。前五份下载仍为 200 且 SHA-256 与归档记录一致时，不重打。
Linux .NET 制品仍不支持 Alpine / musl、ARM64 和 Windows；Windows 是另一份制品，不要合并进 Linux zip。
ARM 探针继续不做，见 `docs/design/product-decisions/apm-probe-coverage.md`。

首版 Java 对象 key `apm/probe/opentelemetry-javaagent.jar` 仅下载兼容；新上传
只写 `apm/probe/java/opentelemetry-javaagent.jar`。

## 2. 流水线必须改造的内容

发布流水线必须完成以下三项，缺少任意一项都不能开放对应语言的接入指引：

1. 归档上表十二份**固定版本**离线包（禁止依赖 GitHub / PyPI / npm / NuGet / Packagist / RubyGems / Hex 的 `latest`）。
2. 在部署准备期、NATS 已可用的环境中，对每个制品执行一次 `apm_probe_init`。
3. 确认各云区域 `NODE_SERVER_URL` 已配置，且目标主机能访问该地址的 8011
   （或实际 Server HTTP 端口）。

建议顺序：归档十二份离线包 → 发布带新白名单的 Server → NATS 就绪后执行十二次 `apm_probe_init`
→ 验收十二个下载地址。先发布 Server，再初始化；旧 Server 会拒绝新制品名。该初始化是**部署准备期**步骤，失败应终止发布流水线并
保留原始错误。已有制品下载仍为 200 且 SHA-256 与归档记录一致时，不重新构建那份离线包；初始化命令可以重跑，它会覆盖同名对象。

禁止把 `apm_probe_init` 放进 Server 容器 `startup.sh` 或 `batch_init`。制品缺失
只影响接入脚本，不阻断 API、Worker、Beat、Listener 启动。启动边界见
[Server 启动顺序与服务依赖边界](server-startup-dependencies.md)。

## 3. 构建并归档产物

十二份制品都必须固定版本，记录字节数和 SHA-256，不提交 Git，并至少保留上一版本
供回滚。内网无法访问公网时，由构建环境一次性拉取后作为流水线制品传递。

本版本钉死的探针号（与 Collector `0.153.0` 无关；发布时若流水线归档不同，以归档为准）：

| 语言 | 制品 | 钉死版本 |
|---|---|---|
| Java | `opentelemetry-javaagent.jar` | `opentelemetry-java-instrumentation` **v2.31.1** |
| Python | `opentelemetry-python-wheels.tar.gz` | `opentelemetry-distro[otlp]==0.65b0`，配套 SDK **1.44.0** |
| Node.js | `opentelemetry-js-auto.tgz` | `@opentelemetry/auto-instrumentations-node@0.79.0` |
| Go | `opentelemetry-go-sdk.zip` | `go.opentelemetry.io/otel` **v1.46.0**，contrib 取同期模块 |
| PHP | `opentelemetry-php-auto-linux-glibc-x64.tar.gz` | `opentelemetry-php-instrumentation` **1.4.2**；构建镜像 `php:8.1-cli-bookworm` 至 `php:8.4-cli-bookworm`（Debian 12，glibc 2.36）。Composer 钉 `sdk 1.15.0`、`exporter-otlp 1.4.0`、Laravel `1.10.0`、Symfony `1.7.0`、Slim `1.5.1`、Guzzle `1.5.0`、PDO `0.6.0`、MySQLi `0.5.0` |
| .NET Linux | `opentelemetry-dotnet-auto-linux-glibc-x64.zip` | `opentelemetry-dotnet-instrumentation` **v1.16.0**（官方 `opentelemetry-dotnet-instrumentation-linux-glibc-x64.zip`） |
| .NET Windows | `opentelemetry-dotnet-auto-windows.zip` | 同一 **v1.16.0** 的官方 `opentelemetry-dotnet-instrumentation-windows.zip` |
| eBPF | `opentelemetry-ebpf-obi-linux-amd64.tar.gz` | OBI **v1.0.0** 的 `obi-v1.0.0-linux-amd64.tar.gz` |
| Ruby | `opentelemetry-ruby-sdk.tar.gz` | `opentelemetry-sdk` **1.13.1**，`opentelemetry-exporter-otlp` **0.37.0**，`opentelemetry-instrumentation-rack` **0.31.2** |
| C++ | `opentelemetry-cpp-sdk.tar.gz` | `opentelemetry-cpp` **v1.30.0**，只含 OTLP/HTTP 安装前缀 |
| Erlang/Elixir | `opentelemetry-erlang-sdk.tar.gz` | `opentelemetry` **1.7.0**，`opentelemetry_exporter` **1.11.0**，以及编译所需的 Hex 传递依赖 |
| Swift | `opentelemetry-swift-sdk.tar.gz` | `opentelemetry-swift` **2.6.0**，配套 core **2.6.0**，HTTP exporter 闭包，Swift tools **6.2** |

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
go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp
go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc
go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin
go.opentelemetry.io/contrib/instrumentation/github.com/labstack/echo/otelecho
```

及其传递依赖。接入脚本会 `export GOSUMDB=off` 并从该目录 `go mod download`，
不再执行 `go get`。归档文件名必须是 `opentelemetry-go-sdk.zip`。模块版本钉
`go.opentelemetry.io/otel@v1.46.0` 及同期 `opentelemetry-go-contrib`，禁止不钉版本的 `go get`。

### .NET

从官方 Release 下载 **v1.16.0** 的 `opentelemetry-dotnet-instrumentation-linux-glibc-x64.zip`，原文件归档并改名为制品名：

```text
https://github.com/open-telemetry/opentelemetry-dotnet-instrumentation/releases/download/v1.16.0/opentelemetry-dotnet-instrumentation-linux-glibc-x64.zip
```

```bash
curl --fail --silent --show-error --location \
  --output opentelemetry-dotnet-auto-linux-glibc-x64.zip \
  https://github.com/open-telemetry/opentelemetry-dotnet-instrumentation/releases/download/v1.16.0/opentelemetry-dotnet-instrumentation-linux-glibc-x64.zip
```

文件名必须是 `opentelemetry-dotnet-auto-linux-glibc-x64.zip`。禁止把 glibc / musl /
多架构 zip 打成集合包，禁止使用 `otel-dotnet-auto-install.sh`（会联网选型）。
zip 内应含 `instrument.sh` 与 `linux-x64/OpenTelemetry.AutoInstrumentation.Native.so`。
该 Linux zip 不支持 Alpine、ARM64、Windows。

Windows 制品从同一版本的官方包改名，不和 Linux zip 合并：

```text
https://github.com/open-telemetry/opentelemetry-dotnet-instrumentation/releases/download/v1.16.0/opentelemetry-dotnet-instrumentation-windows.zip
```

归档文件名必须是 `opentelemetry-dotnet-auto-windows.zip`。接入页只在主机运行方式生成
PowerShell 片段，片段校验 SHA-256 后设置当前进程环境，不重启服务，不写注册表。

### PHP

这不是官方改名包。扩展版本钉 `opentelemetry-php-instrumentation` 1.4.2。
在 `php:8.1-cli-bookworm`、`php:8.2-cli-bookworm`、`php:8.3-cli-bookworm`、
`php:8.4-cli-bookworm` 里分别编译对应 NTS `.so`。这些镜像是 Debian 12，glibc 2.36。
归档布局：

```text
php/8.1/nts/opentelemetry.so
php/8.2/nts/opentelemetry.so
php/8.3/nts/opentelemetry.so
php/8.4/nts/opentelemetry.so
dist/
```

`dist/` 是 Composer artifact 仓库，必须包含上面钉死的包及其传递依赖。不要打入 ZTS
扩展，不要打入 Windows 或 ARM 扩展。

### eBPF

从 OBI v1.0.0 下载官方 amd64 包，原文件改名为制品名。不要打入 arm64 包。

```text
https://github.com/open-telemetry/opentelemetry-ebpf-instrumentation/releases/download/v1.0.0/obi-v1.0.0-linux-amd64.tar.gz
```

```bash
curl --fail --silent --show-error --location \
  --output opentelemetry-ebpf-obi-linux-amd64.tar.gz \
  https://github.com/open-telemetry/opentelemetry-ebpf-instrumentation/releases/download/v1.0.0/obi-v1.0.0-linux-amd64.tar.gz
```

文件名必须是 `opentelemetry-ebpf-obi-linux-amd64.tar.gz`。接入片段只把用户填写的
绝对路径写入 `exe_path_glob`，HTTP traces 打开、metrics 关闭，不配置 meter provider
或端口发现。

### Ruby

在 **linux/amd64**、Ruby `>= 3.3` 的构建机上安装下面三个钉死版本。安装会带上运行时依赖，其中 `google-protobuf` 必须是 `x86_64-linux` 平台。不要使用 aarch64 构建机的 gem 代替。

- `opentelemetry-sdk` 1.13.1
- `opentelemetry-exporter-otlp` 0.37.0
- `opentelemetry-instrumentation-rack` 0.31.2

```bash
gem install --no-document --install-dir /tmp/otel-gems \
  opentelemetry-sdk:1.13.1 \
  opentelemetry-exporter-otlp:0.37.0 \
  opentelemetry-instrumentation-rack:0.31.2
mkdir -p /tmp/ruby-sdk/cache
find /tmp/otel-gems -name '*.gem' -exec cp {} /tmp/ruby-sdk/cache/ \;
tar -C /tmp/ruby-sdk -czf opentelemetry-ruby-sdk.tar.gz cache
```

归档根目录就是 `cache/`，里面直接是 `.gem` 文件。文件名必须是 `opentelemetry-ruby-sdk.tar.gz`。目标机执行 `gem install --local --no-document --ignore-dependencies`，不再访问 RubyGems。页面只写 Rack。不要把 Rack 框架、Rails 或其他未列在上面的 instrumentation 打进归档。

### C++

在 **linux/amd64** 构建机上取出官方 tag `v1.30.0` 的源码，安装到 `prefix/`。CMake 选项名是 `OTELCPP_WITH_*`。只打开 OTLP/HTTP，关闭 OTLP/gRPC、OTLP 文件导出、Prometheus 和测试。构建机安装 libcurl 开发包，使用系统 curl，不要再抓一份 curl 源码。

```text
https://github.com/open-telemetry/opentelemetry-cpp/archive/refs/tags/v1.30.0.tar.gz
```

```bash
cmake -S . -B /tmp/build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/opt/prefix \
  -DBUILD_SHARED_LIBS=ON \
  -DOTELCPP_INSTALL=ON \
  -DOTELCPP_WITH_OTLP_HTTP=ON \
  -DOTELCPP_WITH_OTLP_GRPC=OFF \
  -DOTELCPP_WITH_OTLP_FILE=OFF \
  -DOTELCPP_WITH_PROMETHEUS=OFF \
  -DOTELCPP_BUILD_TESTING=OFF \
  -DOTELCPP_WITH_BENCHMARK=OFF \
  -DOTELCPP_WITH_EXAMPLES=OFF
cmake --build /tmp/build
cmake --install /tmp/build
tar -C /opt -czf opentelemetry-cpp-sdk.tar.gz prefix
```

归档根目录就是 `prefix/`，文件名必须是 `opentelemetry-cpp-sdk.tar.gz`。目标机只对着这个前缀编译示例，不再拉取 CMake 依赖。进程启动时把 `prefix/lib` 放进 `LD_LIBRARY_PATH`。可执行文件上的 RUNPATH 不会传给它依赖的 OpenTelemetry 动态库。

### Erlang/Elixir

从 Hex 下载下面这些包。每个地址形如 `https://repo.hex.pm/tarballs/<包名>-<版本>.tar`，其中的 `contents.tar.gz` 解到与包名相同的目录。归档根目录就是这些目录，不要改成应用名，也不要打入 `_build` 或 beam。文件名必须是 `opentelemetry-erlang-sdk.tar.gz`。

- `opentelemetry` 1.7.0
- `opentelemetry_exporter` 1.11.0
- `opentelemetry_api` 1.5.0
- `grpcbox` 0.18.0
- `tls_certificate_check` 1.18.1
- `acceptor_pool` 1.0.1
- `ctx` 0.6.0
- `gproc` 1.2.0
- `ts_chatterbox` 0.16.0（应用名 `chatterbox`，目录仍叫 `ts_chatterbox`）
- `ssl_verify_fun` 1.1.9
- `hpack_erl` 0.3.0（应用名 `hpack`，目录仍叫 `hpack_erl`）

rebar3 没有 path 依赖类型。片段把这些目录链到应用的 `_checkouts`，并覆盖会再去 Hex 或 Git 拉包的依赖和插件。Mix 示例使用本地 path。

### Swift

打包下面这些源码。归档根目录包含这些目录，文件名必须是 `opentelemetry-swift-sdk.tar.gz`。

```text
opentelemetry-swift/
opentelemetry-swift-core/
swift-atomics/
swift-log/
swift-protobuf/
```

- `opentelemetry-swift` 2.6.0
- `opentelemetry-swift-core` 2.6.0
- `swift-atomics` 1.3.1
- `swift-log` 1.16.2
- `swift-protobuf` 1.39.0

打进归档之前，把包内依赖改成相对本地 path。`opentelemetry-swift-core` 的 atomics 指向 `../swift-atomics`。`opentelemetry-swift` 只保留 HTTP Trace exporter 的 target，path 指向 `../opentelemetry-swift-core`、`../swift-log` 和 `../swift-protobuf`，去掉 gRPC、NIO、metrics 和 tracing。`swift-log` 与 `swift-protobuf` 的清单要求 Swift tools 6.2，片段里的 tools 版本也是 6.2。不要生成 CocoaPods。依赖列表里不要留 GitHub 包地址。上游清单里 SwiftLint 那段只有设置了 `OTEL_ENABLE_SWIFTLINT` 才会启用，不要把它放进 dependencies。Swift 片段面向 Linux，不提供 macOS 安装步骤。

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

python manage.py apm_probe_init \
  --artifact opentelemetry-dotnet-auto-linux-glibc-x64.zip \
  --file_path /path/to/opentelemetry-dotnet-auto-linux-glibc-x64.zip

python manage.py apm_probe_init \
  --artifact opentelemetry-php-auto-linux-glibc-x64.tar.gz \
  --file_path /path/to/opentelemetry-php-auto-linux-glibc-x64.tar.gz

python manage.py apm_probe_init \
  --artifact opentelemetry-dotnet-auto-windows.zip \
  --file_path /path/to/opentelemetry-dotnet-auto-windows.zip

python manage.py apm_probe_init \
  --artifact opentelemetry-ebpf-obi-linux-amd64.tar.gz \
  --file_path /path/to/opentelemetry-ebpf-obi-linux-amd64.tar.gz

python manage.py apm_probe_init \
  --artifact opentelemetry-ruby-sdk.tar.gz \
  --file_path /path/to/opentelemetry-ruby-sdk.tar.gz

python manage.py apm_probe_init \
  --artifact opentelemetry-cpp-sdk.tar.gz \
  --file_path /path/to/opentelemetry-cpp-sdk.tar.gz

python manage.py apm_probe_init \
  --artifact opentelemetry-erlang-sdk.tar.gz \
  --file_path /path/to/opentelemetry-erlang-sdk.tar.gz

python manage.py apm_probe_init \
  --artifact opentelemetry-swift-sdk.tar.gz \
  --file_path /path/to/opentelemetry-swift-sdk.tar.gz
```

本地开发可用 `uv run python manage.py ...`。`--artifact` 只接受上表白名单名字。
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
生成需要离线包的接入配置时都会读取该值；缺失或格式非法时，接入页返回
`probe_download_unavailable`，不会回退公网。

示例（`NODE_SERVER_URL=http://10.10.10.1:8011`）：

```text
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-javaagent.jar
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-python-wheels.tar.gz
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-js-auto.tgz
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-go-sdk.zip
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-dotnet-auto-linux-glibc-x64.zip
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-php-auto-linux-glibc-x64.tar.gz
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-dotnet-auto-windows.zip
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-ebpf-obi-linux-amd64.tar.gz
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-ruby-sdk.tar.gz
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-cpp-sdk.tar.gz
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-erlang-sdk.tar.gz
http://10.10.10.1:8011/api/v1/apm/open_api/probe/download/opentelemetry-swift-sdk.tar.gz
```

注意：

- OTLP 上报地址仍是 `http://<receiver_host>:4318`，与探针下载地址不是同一个端口。
- 下载接口免登录，但只允许白名单文件名。
- 目标主机（以及 docker 构建环境）必须能访问 `NODE_SERVER_URL`，不再需要访问
  GitHub / PyPI / npm / NuGet / proxy.golang.org / RubyGems / Hex。
- Kubernetes 脚本不在集群内 curl；注释里会带上同一下载地址，供制作应用镜像。

## 6. 验收

对十二个制品分别执行：

```bash
for artifact in \
  opentelemetry-javaagent.jar \
  opentelemetry-python-wheels.tar.gz \
  opentelemetry-js-auto.tgz \
  opentelemetry-go-sdk.zip \
  opentelemetry-dotnet-auto-linux-glibc-x64.zip \
  opentelemetry-php-auto-linux-glibc-x64.tar.gz \
  opentelemetry-dotnet-auto-windows.zip \
  opentelemetry-ebpf-obi-linux-amd64.tar.gz \
  opentelemetry-ruby-sdk.tar.gz \
  opentelemetry-cpp-sdk.tar.gz \
  opentelemetry-erlang-sdk.tar.gz \
  opentelemetry-swift-sdk.tar.gz
do
  curl --fail --silent --show-error --location \
    --output "/tmp/${artifact}" \
    "${NODE_SERVER_URL%/}/api/v1/apm/open_api/probe/download/${artifact}"
  test -s "/tmp/${artifact}"
  sha256sum "/tmp/${artifact}"
done
```

摘要必须与发布记录一致。再在 APM 接入页分别选择 Java / Python / Node.js / Go / PHP / .NET Linux / Ruby / C++ / Erlang / Swift
的 host 或 docker，以及 .NET Windows 和 eBPF 的主机片段，确认下载地址是上述系统内 URL，
且不含 `https://github.com`、`pypi.org`、`npmjs`、`nuget.org`、`packagist.org`、`rubygems.org`、`hex.pm`、`go get`。
发布验收还包括：PHP 8.2 NTS 的 Slim 入口 Span；ZTS 或 8.0 安装脚本退出；Windows 上
ASP.NET Core 入口 Span，且不重启无关服务；合格 Linux amd64 主机上未插桩 Go net/http
的入口 Span，已插桩进程不再产生第二份 Trace，指标不进入监控 VM 或 APM 聚合存储。
Ruby 在 linux/amd64 上打出 Rack 入口 Span。C++、Erlang/Elixir、Swift 各自打出一个最小进程入口 Span。
C++ 进程要把 `prefix/lib` 放进 `LD_LIBRARY_PATH`。Swift 只在 Linux 上验收。Ruby 的 gem 必须是目标架构，不能用 aarch64 包代替 amd64。

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
| .NET 启动找不到 Profiler | Linux 归档是否为官方 glibc x64 zip，目标是否为 glibc x86_64；Windows 是否用了 Windows zip 且自行重启了应用 |
| PHP 扩展装不上 | 目标是否为 NTS 8.1–8.4；8.1 不应安装 PDO / MySQLi 包 |
| OBI 没有 Span | 内核、BTF 和权限是否满足；`exe_path_glob` 是否就是目标 Go 二进制的绝对路径 |
| Ruby `gem install` 失败或没有 Rack Span | gem `cache/` 是否为目标架构；Ruby 是否 `>= 3.3`；片段是否使用 Rack `middleware_args` |
| C++ 进程找不到 `libopentelemetry_*.so` | 启动时 `LD_LIBRARY_PATH` 是否包含 `prefix/lib` |
| Erlang `rebar3` 仍去拉 Hex 或 Git | 归档是否含手册列出的 Hex 包；应用是否使用 `_checkouts` 和 overrides |
| Swift 解析到远端包或 tools 版本不够 | 归档是否含 2.6.0、core 和三份本地依赖；示例 tools 是否为 6.2；清单是否只保留 HTTP exporter |

## 8. 回滚

探针制品与 Server 镜像解耦，回滚不必回退整个 Server：

1. 取出上一已验证版本的对应离线包。
2. 再次执行 `apm_probe_init --artifact <制品名>`，覆盖对象存储中的同名对象。
3. 按第 6 节重新验收下载摘要。

不要删除 Object Store bucket 或 NATS volume 来“清理”这些文件，否则会同时丢失
节点管理安装器和采集器包。
