# APM 探针覆盖产品决策记忆

- 最近更新：2026-11-04
- 当前规格：`specs/changes/apm-probe-coverage/spec.md`。已交付的 Linux .NET 见 `specs/changes/apm-dotnet-probe/spec.md`，制品发布见 `docs/operations/apm-probe-artifact-release.md`。

## 产品定位

APM 探针按 OpenTelemetry 官方探针补齐。一种探针钉一个版本，Trace 打进现有区域 Collector。指标和日志导出保持关闭。页面只写进了离线包、并且该版本默认会打出的库。

## 已确认范围

- 已交付：Java、Python、Node.js、Go SDK、.NET Linux x86_64 glibc，各钉一个版本。下载地址不变。
- 第一批：PHP 扩展钉 `1.4.2`，只做 Linux x86_64 glibc 的 PHP 8.1–8.4 NTS。同一份离线包含 Laravel、Symfony、Slim、Guzzle、PDO、MySQLi 及 SDK、OTLP 导出器。页面只写这组。
- 第一批：.NET 在 `1.16.0` 上增加 Windows 制品。同一张卡片，Linux 下载地址不变。Windows 片段不重启服务、不写注册表。ASP.NET Framework 只出现在 Windows。
- 第一批：打开现有 eBPF 卡片，钉 OBI `v1.0.0` 的 Linux amd64。片段只盯用户指定的 Go 可执行文件，只接受 host。验收只承诺未装 Go SDK 的 Go `net/http` 入口 Span。
- 第一批口径：Node.js 0.79.0 去掉 Fastify。Go SDK 推断下游去掉 MySQL、PostgreSQL、Redis、Kafka。Gin、Echo、gRPC、net/http 留在手动框架列表，离线包补上对应 contrib 模块。
- 第二批：Ruby SDK 1.13.1 加 Rack 0.31.2，C++ v1.30.0，Erlang/Elixir SDK 1.7.0 加 exporter 1.11.0，Swift 2.6.0。卡片已按发布手册里的这些版本打开。交付形态与 Go SDK 相同：系统内下载、校验 SHA-256、不访问公网、不覆盖已有应用源码。
- 目标主机仍从本系统下载离线包。

## 已确认设计决策

- ARM 先不做。包括 .NET 的 Linux ARM64 包（glibc 与 musl），以及 PHP、OBI 的 ARM 构建。现有 x86_64 探针维持不变。
- 原因：2026-11-03 用户确认当前只补非 ARM 的缺口。ARM 不进入这一批，也不要在接入页提供 ARM 安装脚本。
- eBPF 不做成 Go 语言下的子卡片，也不按主机扫描全部进程。发现规则限制在指定可执行文件，避免和已装语言探针的进程打出两份 Trace。
- 推断下游查询不改。页面去掉某种库，只表示这份探针默认不会打出它。
- PHP 不改用 Distro 0.7.0。扩展单独装不上不出 Span，所以 Composer 包打进同一份归档。

## 明确后置

- 全部 ARM / ARM64 探针制品与接入说明。
- macOS 探针包。
- .NET 的 Alpine / musl 仍按 `specs/changes/apm-dotnet-probe/spec.md` 后置，本决定不把它提前。
- Rust、Kotlin。上游把 Trace 标成 Stable 之前不钉版本。
- PHP 的 Windows 包、ZTS、PHP Distro。Kubernetes Operator。OBI 的容器和集群运行方式。
- 指标、日志、Profiles。

## 仍待确认

无。

## 已替代决策

- 「.NET ARM64 作为企业版后置」（`specs/changes/apm-dotnet-probe/spec.md` 原出范围）：2026-11-03 改为全部 APM 探针的 ARM 都先不做，不单指 .NET，也不绑定企业版。
- 「.NET 第一版不做 Windows / .NET Framework」（`specs/changes/apm-dotnet-probe/spec.md`）：2026-11-04 由探针补齐规格承接 Windows 制品。Linux glibc 制品契约不改。
- 「eBPF 作为 Go 语言探针的一种」：2026-11-04 改为打开现有 eBPF 卡片，验收范围收在指定的 Go 进程。

## 决策来源

- 2026-11-03 用户确认：PHP、.NET Windows、Go eBPF 要补；ARM 先不做。
- 2026-11-04 用户确认：PHP 离线包和页面使用 Laravel、Symfony、Slim、Guzzle、PDO、MySQLi；eBPF 只盯指定 Go 可执行文件。同日规格审查把 Go 手动框架对应的 contrib 模块补进现有离线包，并把 Windows 片段定为不重启服务的 PowerShell。
