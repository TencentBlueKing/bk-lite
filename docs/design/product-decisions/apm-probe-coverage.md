# APM 探针覆盖产品决策记忆

- 最近更新：2026-11-10
- 当前规格：`specs/changes/apm-probe-coverage/spec.md`。已交付的 Linux .NET 见 `specs/changes/apm-dotnet-probe/spec.md`，制品发布见 `docs/operations/apm-probe-artifact-release.md`。

## 产品定位

APM 探针按 OpenTelemetry 官方探针补齐。一种探针钉一个版本，Trace 打进现有区域 Collector。指标和日志导出保持关闭。页面只写进了离线包、并且该版本默认会打出的库。

## 已确认范围

- 已交付：Java、Python、Node.js、Go SDK、.NET Linux x86_64 glibc，各钉一个版本。下载地址不变。
- 第一批：PHP 扩展钉 `1.4.2`，只做 Linux x86_64 glibc 的 PHP NTS 8.1–8.5。同一份离线包含 SDK 1.15.0、exporter-otlp 1.4.0、Symfony、Slim、Guzzle；Laravel、PDO、MySQLi 从 PHP 8.2 起。页面按这个范围写。不升到扩展 1.5.0 或 SDK 1.16.1。
- 第一批：.NET 在 `1.16.0` 上增加 Windows 制品。同一张卡片，Linux 下载地址不变。Windows 片段不重启服务、不写注册表。ASP.NET Framework 只出现在 Windows。
- 第一批：打开现有 eBPF 卡片，钉 OBI `v1.0.0` 的 Linux amd64。片段只盯用户指定的 Go 可执行文件，只接受 host。验收只承诺未装 Go SDK 的 Go `net/http` 入口 Span。
- 2026-11-09：同一主机上不同 Go 可执行文件各生成一份片段、各启动一个 OBI。配置按绝对路径分开写到 `$HOME/.otel-obi/configs/<路径>/obi.yaml`，避免后一份覆盖前一份。探针包和发现规则不变，仍是这一个路径。同一天补上：服务名和命名空间写进 OBI 配置的 `resource.attributes`，调用链归到页面所选服务，而不是可执行文件名。
- 2026-11-09：三处接入主路径补齐，探针包不变。Node.js 主机说明改为把 `--require` 放在脚本名前面。Swift 主机示例补上读取 `OTEL_*` 的最小入口 Span。PHP 主机把上报变量写成 `otel-fpm-pool.conf`，由操作者并进 php-fpm 池后重载；Docker 和 Kubernetes 仍用容器或 Pod 环境变量。
- 第一批口径：Node.js 0.79.0 去掉 Fastify。Go SDK 推断下游去掉 MySQL、PostgreSQL、Redis、Kafka。Gin、Echo、gRPC、net/http 留在手动框架列表，离线包补上对应 contrib 模块。
- 第二批：Ruby SDK 1.13.1 加 Rack 0.31.2，C++ v1.30.0，Erlang/Elixir SDK 1.7.0 加 exporter 1.11.0，Swift 2.6.0。卡片已按发布手册里的这些版本打开。交付形态与 Go SDK 相同：系统内下载、校验 SHA-256、不访问公网、不覆盖已有应用源码。
- 目标主机仍从本系统下载离线包。
- 2026-11-06：自建 Collector 在接入页生成一段合并进已有 Collector 的 Trace 转发配置。端点仍是所选云区域的内网 OTLP/HTTP，片段不写请求头，也不安装探针。`service.namespace` 写成所选应用；已有的服务名保持不变。采样率低于 100 时才写入 Contrib 的 `probabilistic_sampler`。
- Kubernetes Operator 不在接入页展示。语言探针原有的 Kubernetes 环境变量片段保留。

## 已确认设计决策

- ARM 先不做。包括 .NET 的 Linux ARM64 包（glibc 与 musl），以及 PHP、OBI 的 ARM 构建。现有 x86_64 探针维持不变。
- 原因：2026-11-03 用户确认当前只补非 ARM 的缺口。ARM 不进入这一批，也不要在接入页提供 ARM 安装脚本。
- eBPF 不做成 Go 语言下的子卡片，也不按主机扫描全部进程。发现规则限制在指定可执行文件，避免和已装语言探针的进程打出两份 Trace。
- 推断下游查询不改。页面去掉某种库，只表示这份探针默认不会打出它。
- PHP 不改用 Distro 0.7.0。扩展单独装不上不出 Span，所以 Composer 包打进同一份归档。
- 2026-11-10：OBI v1.0.0 的片段在内核低于 6.6 时退出。该版本需要 `uprobe_multi`，6.1 上能挂载但没有 Span 入库。

## 明确后置

- 全部 ARM / ARM64 探针制品与接入说明。
- macOS 探针包。
- .NET 的 Alpine / musl 仍按 `specs/changes/apm-dotnet-probe/spec.md` 后置，本决定不把它提前。
- Rust、Kotlin。上游把 Trace 标成 Stable 之前不钉版本。
- PHP 的 Windows 包、ZTS、PHP Distro。Kubernetes Operator 注入。OBI 的容器和集群运行方式。OBI 仍只承诺指定的 Go `net/http` 进程。
- 指标、日志、Profiles。

## 仍待确认

无。

## 已替代决策

- 「.NET ARM64 作为企业版后置」（`specs/changes/apm-dotnet-probe/spec.md` 原出范围）：2026-11-03 改为全部 APM 探针的 ARM 都先不做，不单指 .NET，也不绑定企业版。
- 「.NET 第一版不做 Windows / .NET Framework」（`specs/changes/apm-dotnet-probe/spec.md`）：2026-11-04 由探针补齐规格承接 Windows 制品。Linux glibc 制品契约不改。
- 「eBPF 作为 Go 语言探针的一种」：2026-11-04 改为打开现有 eBPF 卡片，验收范围收在指定的 Go 进程。
- 「接入页保留不可点击的自建 Collector 与 Kubernetes Operator 卡片」：2026-11-06 改为 Collector 生成转发片段，Operator 从接入页拿掉。
- 「PHP 8.1–8.4 的同一份离线包都含 Laravel」：2026-11-10 改为 8.1–8.5。Laravel 10.50.4 和 11.57.1 被 Composer 安全公告拦截，8.1 只保留 Symfony 6.4、Slim 和 Guzzle。Laravel 从 8.2 起。
- 「eBPF 按 Linux 5.8+ 或带 BTF 的 4.18+ 验收」：2026-11-10 改为内核低于 6.6 时退出。

## 决策来源

- 2026-11-03 用户确认：PHP、.NET Windows、Go eBPF 要补；ARM 先不做。
- 2026-11-04 用户确认：PHP 离线包和页面使用 Laravel、Symfony、Slim、Guzzle、PDO、MySQLi；eBPF 只盯指定 Go 可执行文件。同日规格审查把 Go 手动框架对应的 contrib 模块补进现有离线包，并把 Windows 片段定为不重启服务的 PowerShell。
- 2026-11-10 用户确认按实测口径重打 PHP 包并改片段：扩展保持 1.4.2，PHP NTS 扩到 8.5，Laravel 从 8.2 起。
