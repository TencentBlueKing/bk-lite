# APM 官方 Trace 探针补齐

Status: done

## Problem Statement

APM 接入已经按 OpenTelemetry 官方探针交付：一种语言钉一个版本，Trace 打进所选云区域的区域 Collector，指标和日志导出保持关闭。已经能用的是 Java、Python、Node.js、Go SDK 和 .NET Linux x86_64 glibc。

还不能接的是官方零代码里的 PHP、.NET 的 Windows 制品，以及没装语言探针时的 eBPF。接入页有三处和已经交付的包不一致：Node.js 写了 Fastify，Go SDK 把 MySQL、PostgreSQL、Redis、Kafka 写成推断下游，Linux 的 .NET 卡片写了 ASP.NET Framework。手动 SDK 里 Trace 已经稳定的 Ruby、C++、Erlang/Elixir、Swift 也还没有离线包。

目标主机不访问 GitHub、PECL、NuGet 或 Packagist。新探针装不上时，不能影响已经在跑的语言探针和调用链查询。

## Solution

分两批补齐，调用链仍然只收 Trace。

第一批补 PHP 零代码、.NET Windows 制品和 eBPF，并改掉三处页面口径。PHP 是一张新语言卡片。Windows 是同一张 .NET 卡片上的第二份制品，Linux 下载地址不变。eBPF 打开接入页上已经存在、目前标为规划中的那张卡片，安装片段只盯用户指定的 Go 可执行文件。第二批按现有 Go SDK 的方式补 Ruby、C++、Erlang/Elixir、Swift 四种手动语言。

页面只写进了离线包、并且该版本默认会打出的库。拓扑推断查询不改：任何语言打出 Client Span，应用详情画布仍按现有别名出推断下游。

## User Stories

1. As an APM 使用者, I want 在接入页选择 PHP 后拿到只从本系统下载的离线包和片段, so that Linux 上的 PHP 8.1–8.5 NTS 应用不用上 PECL 或 Packagist 就能打出入口 Span。PHP 8.1 安装 Symfony、Slim 和 Guzzle；Laravel、PDO、MySQLi 从 8.2 起。
2. As an APM 使用者, I want PHP 页面和片段只出现 Linux x86_64 glibc 的 NTS 步骤, so that 我不会按 ARM、Windows 或 ZTS 去装一份对不上的扩展。
3. As an APM 使用者, I want .NET 卡片同时提供 Linux 和 Windows 两份 1.16.0 制品, so that Windows 上的 ASP.NET Core 能接入，而现有 Linux 片段和下载地址保持不变。
4. As an APM 使用者, I want ASP.NET Framework 只出现在 Windows 说明里, so that 我不会在 Linux 制品上寻找它。
5. As an APM 使用者, I want 打开 eBPF 卡片后填写 Go 可执行文件并得到只采集该进程 Trace 的片段, so that 未装 Go SDK 的 net/http 服务能出入口 Span，同机已装语言探针的进程不会再出一份 Trace。
6. As an APM 使用者, I want 新探针失败时只影响这一种接入, so that 已有 Java、Python、Node.js、Go SDK、.NET Linux 的调用链查询不受影响。
7. As an APM 使用者, I want 接入页的 Node.js 不再写 Fastify，Go SDK 不再把 MySQL、PostgreSQL、Redis、Kafka 写成推断下游, so that 页面和离线包一致。
8. As an APM 使用者, I want 第二批按 Ruby、C++、Erlang/Elixir、Swift 的顺序各得到一个钉死版本的手动离线包, so that Trace 已稳定的语言能用和 Go SDK 相同的方式接入。
9. As 运维, I want 新制品沿用现有白名单、系统内下载地址和部署期初始化, so that 缺包只让对应片段生成失败，不阻断服务启动。

## Implementation Decisions

### 批次与卡片

- 第一批交付 PHP、.NET Windows、eBPF，以及三处口径修正。第二批在版本写入发布手册后打开 Ruby、C++、Erlang/Elixir、Swift。
- PHP 使用语言 `php`。eBPF 使用语言 `obi`，挂在现有 eBPF 卡片上，不挂在 Go 语言下面。Kubernetes Operator 和自建 Collector 卡片保持不可用。
- 接入配置仍然不落库。`service.namespace` 等于已创建应用 ID，组织继承应用，OTLP 不携带组织 ID，采样率只写进本次片段。这些约定对新语言不做例外。
- 区域 Collector 保持只有 traces 流水线。不新增指标流水线，不把 OBI 或 PHP 的指标写入监控的 VictoriaMetrics，也不写入 APM 聚合库。

### 制品与下载

- 下载仍只接受白名单制品名，沿用现有免登录下载路径。非白名单名字拒绝。初始化命令随白名单接受新制品名，不进入服务启动，不在 `batch_init` 完成前依赖对象存储。
- 已交付五种制品的名字、对象 key 和下载地址不变。
- PHP 制品名 `opentelemetry-php-auto-linux-glibc-x64.tar.gz`，对象 key `apm/probe/php/opentelemetry-php-auto-linux-glibc-x64.tar.gz`。一份归档同时包含 PHP 8.1–8.5 的 NTS 扩展和 Composer 包，不按框架再拆制品。
- .NET Windows 制品名 `opentelemetry-dotnet-auto-windows.zip`，对象 key `apm/probe/dotnet/opentelemetry-dotnet-auto-windows.zip`。归档官方 v1.16.0 的 `opentelemetry-dotnet-instrumentation-windows.zip` 原文件并改名，不与 Linux zip 合并。
- eBPF 制品名 `opentelemetry-ebpf-obi-linux-amd64.tar.gz`，对象 key `apm/probe/ebpf/opentelemetry-ebpf-obi-linux-amd64.tar.gz`。归档官方 OBI v1.0.0 的 `obi-v1.0.0-linux-amd64.tar.gz` 原文件并改名。不放入 arm64 包。
- 未传平台时，.NET 仍解析到现有 Linux glibc 制品。语言到制品的默认映射保持 Linux 这一份，Windows 只在显式选择 Windows 时使用。

### 接入接口

- 控制台接入接口和已暴露的 `apm/integration-configs` 同时增加语言 `php`、`obi`。这是在既有可选值上追加，不改 path，不收紧已有字段。
- 新增可选字段 `probe_platform`，取值 `linux` 或 `windows`，缺省 `linux`。只有 `dotnet` 接受 `windows`。其他语言传入 `windows` 时拒绝生成片段。
- 新增可选字段 `process_executable`。只有 `obi` 必填。值必须是绝对路径，拒绝空值、控制字符、空格和 shell 元字符。片段把校验后的路径写入 OBI 发现规则。
- `obi` 只接受运行方式 `host`。`docker`、`kubernetes`、`other` 拒绝生成片段。
- `dotnet` 加 `windows` 只接受运行方式 `host`。`docker` 和 `kubernetes` 仍只生成现有 Linux 片段。

### PHP

- 扩展版本钉 `opentelemetry-php-instrumentation` 1.4.2。官方该版本没有 Linux 预编译包，由发布构建在 x86_64 glibc 环境编出 PHP 8.1、8.2、8.3、8.4、8.5 的 NTS `.so`。不编 ZTS，不在目标机执行 `pecl`。构建使用的镜像和 glibc 版本写进制品清单。2026-11-10 确认不升到扩展 1.5.0 或 SDK 1.16.1：这两档的 Composer 约束是 PHP `^8.2`，覆盖的 PHP 版本没有变多。
- 同一归档带上这些钉死版本的 Composer 包：`open-telemetry/sdk` 1.15.0、`open-telemetry/exporter-otlp` 1.4.0、`open-telemetry/opentelemetry-auto-laravel` 1.10.0、`open-telemetry/opentelemetry-auto-symfony` 1.7.0、`open-telemetry/opentelemetry-auto-slim` 1.5.1、`open-telemetry/opentelemetry-auto-guzzle` 1.5.0、`open-telemetry/opentelemetry-auto-pdo` 0.6.0、`open-telemetry/opentelemetry-auto-mysqli` 0.5.0，以及各 PHP 小版本会选中的框架传递依赖。`dist/` 同时保留 8.1、8.2、8.4 三套解析结果；8.3 落在 8.2 与 8.4 的并集里，8.5 与 8.4 相同。禁止未钉版本的 `composer require`。不打入被 Composer 安全公告拦截的 Laravel 10 和 11。
- 页面入口写 Symfony、Slim、Guzzle；Laravel 标成 PHP 8.2+。推断下游只写 PDO、MySQLi，并标成 PHP 8.2+。WordPress、Magento 等其余上游库不进归档，也不上页面。
- 片段关闭指标和日志导出，Trace 用 OTLP/HTTP 打到所选云区域。安装时核对 PHP 是 8.1–8.5 且为 NTS，否则退出并说明原因，不复制错误的 `.so`。ZTS 判断使用 `PHP_ZTS` 的真值，8.4 起该常量是布尔值。没有 `composer.json` 时先创建最小项目，再关闭 Packagist，然后只从归档离线安装。8.1 不安装 Laravel、PDO、MySQLi。片段不出现 `pecl`、`packagist.org`、`https://github.com`、ARM 或 Windows 步骤。
- host、docker、kubernetes、other 四种运行方式都提供，实例 ID 沿用各运行方式的既有规则。验收用 Slim 打出一条入口 Span。页面上的 Laravel、Symfony 不逐个搭集成环境。

### .NET Windows

- 版本仍是 `opentelemetry-dotnet-instrumentation` v1.16.0。Linux 片段继续使用现有 glibc x64 制品、`instrument.sh` 和 `linux-x64` 原生库路径。
- Linux 片段保留现有范围句：这份制品仅支持 Linux x86_64 glibc，不支持 Alpine、ARM64 和 Windows。这句话只描述这一份 zip。页面另外提供 Windows 制品，ASP.NET Framework 不出现在 Linux 能力里。
- Windows 片段是 PowerShell，不是 POSIX shell。它从本系统下载 Windows 制品，用 `Get-FileHash` 做 SHA-256 校验，设置当前进程的 Profiler 与 `OTEL_*`，关闭指标和日志导出。操作者自己重启应用。
- 片段不调用 `Register-OpenTelemetryForWindowsService`，不调用 `Restart-Service`，不写注册表。官方该命令默认会重启 Windows 服务。
- Windows 入口写 ASP.NET Core、ASP.NET Framework、gRPC。不新增推断下游种类。验收是 Windows 上的 ASP.NET Core 入口 Span，不把 Linux 卡片上的数据库和消息库自动抄到 Windows 说明里。

### eBPF

- 版本钉 OpenTelemetry eBPF Instrumentation v1.0.0 的 Linux amd64 包。内核低于 6.6 时片段退出并说明 OBI v1.0.0 需要 `uprobe_multi`。仍需要可读的 BTF 和 root 或该版本要求的 capabilities。
- 片段使用 Config v2，只导出 Trace，关闭指标。发现规则只包含 `process_executable`。不使用端口发现，不扫描整个 PID 命名空间，不注入 JVM。
- `resource.attributes` 写入所选 `service.name` 和 `service.namespace`。OBI v1.0.0 用这两项确定服务身份。只放在 `OTEL_RESOURCE_ATTRIBUTES` 时，服务名会被可执行文件名覆盖。
- 每个可执行文件路径单独写一份配置：`$HOME/.otel-obi/configs/<去掉开头斜杠的绝对路径>/obi.yaml`。探针包仍解压到 `$HOME/.otel-obi`。同一路径再次生成只刷新这一份。片段不删除旧的 `$HOME/.otel-obi/obi.yaml`。查找 `obi` 二进制时排除 `configs` 目录。
- 页面卡片说明这是另起进程盯住这一个 Go 程序，程序本身不用改。同一进程不要再装 Java、Python、Node.js、.NET、PHP 或 Go SDK，写在抽屉操作说明和片段注释里。页面只写 Go `net/http` 入口，推断下游留空。它不替换 Go SDK。
- 内核、BTF 或权限不够时，片段说明失败原因并退出。不修改应用二进制。
- 子 Span 时间戳可能早于父 Span，这是 v1.0.0 已记录的限制，写进片段说明。验收不把瀑布时序当作通过条件。
- 验收：未装 Go SDK 的 Go `net/http` 出现入口 Span。已装 Go SDK 的进程不要求再出一份 eBPF Trace。

### 三处口径与 Go 离线模块

- Node.js 0.79.0 的能力列表和卡片文案去掉 Fastify。Express、NestJS、Koa、HTTP 保留。
- Go SDK 推断下游去掉 MySQL、PostgreSQL、Redis、Kafka。入口仍保留 net/http、gRPC、Gin、Echo，并继续标明需要手动加入 contrib。
- 现有 Go 片段下载钉死版本：`go.opentelemetry.io/otel`、`sdk`、`otlptracehttp` 为 v1.46.0，四个 contrib 模块为 v0.70.0。命令仍是一条 `go mod download`，不使用 `go get`。Go 低于 1.26 时退出，并设置 `GOTOOLCHAIN=local`，避免去公网下载工具链。四个 contrib 模块是：
  - `go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp`
  - `go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc`
  - `go.opentelemetry.io/contrib/instrumentation/github.com/gin-gonic/gin/otelgin`
  - `go.opentelemetry.io/contrib/instrumentation/github.com/labstack/echo/otelecho`
- 已有三个核心模块的下载保留。Go 制品名和下载地址不变。
- 这四个模块路径含有 `github.com` 字样，但不是下载地址。片段仍禁止 `https://github.com`、`go get` 和其他公网源。现有「host 片段不含子串 github.com」的断言对 Go 过宽，改为拒绝下载 URL，并允许上述模块路径。

### 第二批手动 SDK

- 顺序是 Ruby，然后 C++、Erlang/Elixir、Swift。每种语言一个离线包、一个钉死版本、一段片段，Trace 打到现有 OTLP 地址，指标和日志导出关闭。
- 2026-11-04 钉死的非预发布版本：Ruby `opentelemetry-sdk` 1.13.1、`opentelemetry-exporter-otlp` 0.37.0、`opentelemetry-instrumentation-rack` 0.31.2；C++ `opentelemetry-cpp` v1.30.0；Erlang/Elixir `opentelemetry` 1.7.0、`opentelemetry_exporter` 1.11.0；Swift `opentelemetry-swift` 2.6.0。这些版本写入发布手册后，四张卡片可用。
- 语言名分别是 `ruby`、`cpp`、`erlang`、`swift`。Erlang/Elixir 共用 `erlang` 这一张卡片。Swift 使用 Swift Package Manager，片段面向 Linux，不提供 macOS 安装步骤。
- Ruby 验收一个 Rack Web 进程的入口 Span。后三种各自一个最小进程的入口 Span。
- 交付形态对齐现有 Go SDK：系统内下载、校验 SHA-256、不访问公网、不覆盖已有应用源码。片段生成示例文件；目标文件已存在时退出。
- 制品名：`opentelemetry-ruby-sdk.tar.gz`、`opentelemetry-cpp-sdk.tar.gz`、`opentelemetry-erlang-sdk.tar.gz`、`opentelemetry-swift-sdk.tar.gz`。对象 key 分别在 `apm/probe/ruby/`、`apm/probe/cpp/`、`apm/probe/erlang/`、`apm/probe/swift/`。四种语言传入 `probe_platform=windows` 时拒绝生成片段。
- Erlang 片段的 OTLP 协议值是 `http_protobuf`，对应同一条 OTLP/HTTP 上报地址。其他语言仍是 `http/protobuf`。
- Erlang 归档包含 `opentelemetry` 1.7.0、`opentelemetry_exporter` 1.11.0、`opentelemetry_api` 1.5.0，以及它们编译所需的 Hex 传递依赖。rebar3 没有 path 依赖类型，片段使用 `_checkouts`。Mix 示例使用本地 path。
- Swift 归档包含 `opentelemetry-swift` 2.6.0、配套 `opentelemetry-swift-core` 2.6.0，以及 HTTP exporter 编译所需的 `swift-atomics` 1.3.1、`swift-log` 1.16.2、`swift-protobuf` 1.39.0。包内依赖改为本地 path，清单只保留 HTTP Trace exporter。片段 tools 版本是 6.2。

### 失败与权限

- 制品缺失时，只有该语言或该平台的片段生成失败，错误仍是现有的制品不存在或下载地址不可用。其他语言片段照常生成。
- 下载接口不新增端口，不新增上传入口。用户不能上传探针包，也不能把 SkyWalking 或其他 Agent 登记进来。
- 片段生成不记录制品内容、下载 URL 中的敏感查询或目标机路径以外的无界对象。`process_executable` 只作为校验后的路径进入片段。

## Testing Decisions

好的测试只锁对外行为：白名单、下载地址、片段里的关键命令和环境变量、不出现的公网地址和危险命令。不断言片段逐字全文，也不把真实 PHP、Windows 或 eBPF 进程放进单元测试。

先验是接入片段测试、制品白名单测试、接入配置权限测试，以及接入页能力矩阵和接入页测试。SHA-256 在片段测试里继续打桩，不连接对象存储。

- 制品：白名单包含三份新制品和原有五份。`php` 默认映射到 PHP 归档，`dotnet` 默认仍是 Linux glibc 制品，显式 Windows 才映射到 Windows 制品，`obi` 映射到 amd64 归档。非白名单名字被拒绝。初始化命令接受新制品名。
- 已有 Java、Python、Node.js、Go、.NET Linux 的下载地址断言保持通过。Go 片段在原有三个模块之外包含上面四个 contrib 模块，制品名不变。
- PHP：host 与 docker 含系统内下载地址、SHA-256 校验和离线 Composer 包名。kubernetes 与现有语言一样，是可解析的环境 patch，注释中带下载地址，环境变量关闭指标和日志，不在 patch 里重复校验和。四种运行方式都含 NTS 与 8.1–8.5 的说明。host 与 docker 在缺少 `composer.json` 时创建它，并关闭 Packagist。片段不含 `pecl`、`packagist.org`、`https://github.com`、ARM 或 Windows 安装步骤。host 与 docker 通过 `sh -n`。传入 `probe_platform=windows` 被拒绝。Java、Python、Node.js、Go 同样关闭指标和日志导出。Python 片段要求 CPython 3.12。
- .NET：缺省平台的片段仍含 `linux-x64` 原生库路径和现有 Linux 制品名，不含 Windows 制品名。Windows host 片段含 Windows 制品名、SHA-256 校验、ASP.NET Framework 说明，不含 `linux-x64` 的 `.so` 路径，不含 `Register-OpenTelemetryForWindowsService`、`Restart-Service` 和注册表写入。Windows 片段不纳入 `sh -n`。Windows 加 docker 或 kubernetes 被拒绝。
- eBPF：host 片段含 amd64 制品、SHA-256、Config v2、关闭指标、以及校验后的绝对路径发现规则。片段不含 arm64 制品名，不含端口发现。空路径、相对路径、带空格或元字符的路径被拒绝。非 host 运行方式被拒绝。
- 接入页：PHP 卡片可用，能力只含约定的六个库。eBPF 卡片可用且只写 Go `net/http`。Operator 与自建 Collector 仍不可用。Node.js 文案和能力列表不含 Fastify。Go 推断下游不含那四种库，框架列表仍含 Gin 与 Echo。Linux .NET 能力不含 ASP.NET Framework，Windows 能力含它。Ruby 只写 Rack。C++、Erlang/Elixir、Swift 只写手动入口 Span，推断下游为空。新增文案中英都有词条。
- 第二批：四种语言的 host 与 docker 含系统内下载地址、SHA-256 校验，且不含 `https://github.com`、`rubygems.org`、`hex.pm`。host 片段在示例文件已存在时退出。kubernetes 带下载地址，不重复校验和。Erlang 片段的协议值是 `http_protobuf`。传入 `probe_platform=windows` 被拒绝。
- 权限：新语言的接入配置沿用现有接入页查看权限和双租户用例。无权限组织不能为该应用生成片段。下载接口仍只按白名单返回，不新增登录态。

本地验证分成两道门，不能互相替代。

合并门禁不启动 Postgres、Redis、NATS，也不需要探针二进制：

- `cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/apm/tests/test_probe_artifacts.py apps/apm/tests/test_ingest_snippets.py apps/apm/tests/test_api_permissions.py --no-cov`
- 接入页与能力矩阵的现有前端测试，以及改了语言类型后的 `pnpm type-check`。

`test_api_permissions.py` 若仍因既有迁移 `NewSessionEventRelation.event` 无法在 sqlite 建库，保留原始失败输出，不把它算成这次改动的通过或失败。

发布门禁在制品已经初始化和下载地址可访问之后执行。缺环境的条目保持未完成，不用单元测试勾掉：

- 五种旧制品的下载地址仍返回原文件，SHA-256 与发布手册一致。
- PHP：一台 Linux x86_64 glibc、PHP 8.2 NTS 的 Slim 进程打出入口 Span。片段在 ZTS 或 8.0 上退出。内核低于 6.6 时 eBPF 片段退出。
- .NET：一台 Windows 主机上的 ASP.NET Core 打出入口 Span，安装过程没有重启无关 Windows 服务。
- eBPF：一台 Linux 6.6 或更新、且有 BTF 的 amd64 主机上，未装 Go SDK 的 `net/http` 打出入口 Span；同机一个已装 Java 或 Go SDK 的进程没有第二份 Trace。指标不进监控库，也不进 APM 聚合库。
- 第二批：Ruby 的 Rack 入口 Span，以及 C++、Erlang/Elixir、Swift 各自一个最小进程入口 Span。缺编译环境的条目保持未完成。

## Out of Scope

- ARM、ARM64、macOS、.NET Alpine / musl、PHP Windows、PHP ZTS、PHP 8.0 与 PHP 7。
- PHP Distro 0.7.0，以及 WordPress、Magento 等未列入归档的 PHP 库。
- 把 OBI 做成主机级或跨语言探针，OBI 的 docker、Kubernetes、DaemonSet 和 Operator 注入。
- 指标、日志、Profiles，以及把 OBI 指标接进监控或 APM 聚合库。
- 修改区域 Collector 流水线，或用 `trace_id + span_id` 去重来代替进程发现规则。两份探针产生的是不同 Span。
- 修改推断下游的查询、别名和画布规则。
- 自建 Collector 转发、用户上传探针、接入 SkyWalking 或其他 Agent。
- Kubernetes Operator 卡片。
- Rust、Kotlin。
- 为历史进程补 Trace。
- Windows 片段重启服务或写注册表。
- 在既有环境执行初始化命令。那一步仍由运维按发布手册做。

## Further Notes

- 已实现的 Linux .NET 规格继续只描述 glibc x64 那一份制品。Windows 由本规格承接，不改 Linux 下载地址。
- 推断下游的产品决定是「有 Client Span 才在应用详情画布出现」。拿掉 Go 页面上的四种库，只修正 Go SDK 不会默认打出这些 Span 的说法，不削弱 Java、Python、Node.js、.NET 已经能打出的推断下游。
- ADR 0006 的重复投递去重不能合并两个探针各自生成的 Span。eBPF 的安全边界是发现规则，不是 Collector。
- ADR 0008 不变：片段仍指向受信区域的 OTLP 地址，不生成 APM Token。
- 官方 PHP 扩展 1.4.2 的 Release 资产只有 Windows 预编译包。Linux `.so` 是本系统的构建产物，不是把官方 zip 改名。
- 2026-11-04 完成第一批代码。合并门禁：`test_ingest_snippets.py` 与不依赖数据库的制品测试通过。`test_probe_artifacts.py` 里 5 个下载接口用例，以及 `test_api_permissions.py`，仍在 sqlite 建库时停在既有错误 `NewSessionEventRelation has no field named 'event'`。前端接入页与能力矩阵测试通过。`pnpm type-check` 停在既有的 node-manager 类型错误，本次 APM 文件不在其中。`pnpm test:apm-i18n` 停在既有的其他 APM 页面文案问题。发布门禁的真实 Span 未执行。
- 2026-11-04 完成第二批代码。四种手动 SDK 的片段测试和接入页测试通过。`test_probe_artifacts.py` 的 5 个下载用例仍在 sqlite 建库时失败，这次的错误是既有字段 `NewApmIngestSourceOrganization.ingest_source`。
- 2026-11-04 在本机 Colima 的 linux/arm64 容器里，对既有区域 Collector 的 OTLP/HTTP `:4318` 打出入口 Span：Ruby Rack 服务 `ruby-rack-b2`（SDK `opentelemetry` 1.13.1）、Erlang 服务 `erlang-entry-b2`（SDK `opentelemetry` 1.7.0）、C++ 服务 `cpp-entry-b2`（SDK `opentelemetry` 1.30.0）、Swift 服务 `swift-entry-b2`。四条 Span 都是 server，资源带 `bk.cloud_region.id=local`。这证明 SDK 和现有采集链路，不是 amd64 发货门禁。Ruby 的 gem 缓存是 `aarch64-linux-gnu`，不能当作 amd64 制品。临时容器和镜像已删除，没有把这四份包写入共享对象存储。
