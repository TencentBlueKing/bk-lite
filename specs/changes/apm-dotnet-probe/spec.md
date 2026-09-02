# APM .NET 自动探针接入（Linux x86_64 glibc）

Status: implemented

## Completion Evidence

- 制品白名单新增 `opentelemetry-dotnet-auto-linux-glibc-x64.zip` → `apm/probe/dotnet/...`，`LANGUAGE_PROBE_ARTIFACTS["dotnet"]` 指向该制品，无兼容 key。`apm_probe_init --artifact` 随白名单接受新名字。
- 接入片段 `language=dotnet` 三种运行方式共用同一系统内下载地址；host 解压后 `source instrument.sh` 并钉死 glibc x64 CLR 环境（含 Additional Deps / Shared Store）；Docker / K8s 注入同一组变量与 `dotnet App.dll`。片段顶部写明仅支持 Linux x86_64 glibc；`OTEL_METRICS_EXPORTER=none`、`OTEL_LOGS_EXPORTER=none`。不含 `github.com` / `nuget.org` / `otel-dotnet-auto-install.sh`。
- 接入页 .NET 卡片可用，`language: dotnet`，描述与 i18n 中英同步支持范围；运行方式仍是自动探针 / Docker / Kubernetes。
- 发布 Runbook、`deploy/apm/README.md`、功能清单与推断下游版本表补第五份制品与 v1.16.0。
- 测试：`test_probe_artifacts.py`（白名单 / 新 key / init 接受新制品名）、`test_ingest_snippets.py`（dotnet 三档片段）、接入页 `page.test.tsx` 通过。`test_api_permissions.py` 与探针下载 `@pytest.mark.django_db` 用例在 sqlite 下仍因无关迁移 `NewSessionEventRelation.event` 无法建库（既有基线）。`apm-i18n-coverage-test.ts` 在无关文件 `topology-object-icon.ts` 上有既有硬编码文案失败。

## Problem Statement

APM 接入页的 SDK 卡片里，.NET 一直是「暂不可用」。已有 .NET 服务的团队只能自己去
GitHub 下 OpenTelemetry .NET 自动探针、自己拼环境变量，而目标主机通常访问不了公网；
接入方式与 Java / Python / Node.js / Go 完全不同，也拿不到系统生成的
`service.namespace` / `service.instance.id` 约定，服务无法正确归属到已创建的应用。

之所以一直没开，是 .NET 自动探针与前四种语言的交付形态不同：它是 CLR Profiler 加
原生动态库，官方按 OS × libc × CPU 架构拆成多份 zip，没有一份像 Java Agent jar
那样通吃的文件。如果不先划定范围，要么被迫做「多份包 + 安装时选型」，要么做一个
把多份 zip 合并的集合包，两者都与现有「一种语言、一份制品、一个下载地址」的模型不一致。

## Solution

第一版把 .NET 自动探针按**与其他四种语言完全同构**的方式开放：一种语言、一个制品名、
一次对象存储初始化、一个系统内下载地址，接入页三种运行方式（自动探针 / Docker /
Kubernetes）共用同一份文件。

支持范围明确收窄为 **Linux x86_64 + glibc**（Ubuntu / Debian / CentOS / RHEL 类主机，以及
以这些发行版为基础镜像的容器）。制品直接归档官方 `opentelemetry-dotnet-instrumentation-linux-glibc-x64.zip`，不重打包、不合集。
Alpine（musl）、ARM64、Windows / IIS、macOS 与 .NET Framework 均不在第一版内，在接入
页文案里明写，不做选项。

制品名与对象 key 里带 `linux-glibc-x64`，为后续新增 musl 或 ARM64 制品留出并列位置，
届时只新增制品与接入页选项，不改本版契约。

## User Stories

1. As an APM 使用者, I want 在接入页选择 .NET 后与 Python 一样看到「自动探针 / Docker /
   Kubernetes」三种运行方式的可复制片段, so that 我的 .NET 服务能用和其他语言相同的路径
   接入，并正确归属到已创建的应用。
2. As an APM 使用者, I want .NET 接入片段只从本系统下载探针、不访问 GitHub / NuGet,
   so that 目标主机在内网也能完成安装。
3. As an APM 使用者, I want 片段顶部明确写出「仅支持 Linux x86_64 glibc」及不支持项,
   so that 我在 Alpine 或 ARM64 环境不会白装一遍再排查失败原因。
4. As 运维, I want .NET 探针制品的归档、版本钉死、初始化命令和验收地址与其他四种语言并列
   写在同一份发布手册里, so that 流水线只需多归档一份文件、多执行一次初始化，不引入新流程。
5. As 运维, I want 制品缺失时 .NET 下载地址与其他语言一样返回稳定的「制品不存在」错误,
   so that 排障方式一致。

## Implementation Decisions

### 支持范围

- 平台：仅 Linux x86_64 glibc。不支持 Alpine / musl、ARM64、Windows、macOS、.NET Framework。
- 运行时：现代 .NET（.NET 8 及以上，以上游 v1.16.0 声明的支持矩阵为准）。
- 上游版本钉死 `opentelemetry-dotnet-instrumentation` **v1.16.0**，归档官方 `opentelemetry-dotnet-instrumentation-linux-glibc-x64.zip`
  原文件。禁止自行合并多份 zip，禁止依赖 `latest`。
- 信号范围与其他语言一致：traces-only。片段把 metrics / logs 导出器关闭，避免探针默认向
  4318 推送 metrics / logs 被区域采集器拒收或产生噪音。

### 制品契约

- 制品名：`opentelemetry-dotnet-auto-linux-glibc-x64.zip`
- 对象 key：`apm/probe/dotnet/opentelemetry-dotnet-auto-linux-glibc-x64.zip`
- 下载地址：`{NODE_SERVER_URL}/api/v1/apm/open_api/probe/download/opentelemetry-dotnet-auto-linux-glibc-x64.zip`
- 加入探针制品白名单，`apm_probe_init --artifact` 随白名单自动接受该制品名；上传只写新 key，
  不设兼容 key。
- 与现有四种一致：不进 `startup.sh` / `batch_init`，由发布流水线在部署准备期执行初始化；
  制品缺失只影响 .NET 接入片段，不阻断服务启动。
- 制品名中的平台后缀是有意为之：后续若增加 `linux-musl-x64` 或 `linux-glibc-arm64`，作为并列制品
  新增，接入页再加「运行环境」切换；本版不预留该切换。

### 语言与片段

- 接入片段序列化器的 `language` 枚举新增 `dotnet`；语言到制品的映射新增 `dotnet`。
- 安装方式使用 zip 内自带的 `instrument.sh`，不使用官方 `otel-dotnet-auto-install.sh`
  （后者默认联网选型，与离线契约冲突，也不再需要）。
- 三种运行方式共用同一个 `probe_download_url`：
  - 自动探针（host）：`curl` 下载 → 解压到用户目录下固定路径 → `source instrument.sh` →
    导出 OTLP 端点、协议、传播器与 `OTEL_RESOURCE_ATTRIBUTES` → 以 `dotnet <App>.dll` 启动。
    实例 ID 沿用 host 运行方式的既有规则。
  - Docker：Dockerfile 中 `curl` + 解压到镜像内固定路径；`docker run -e` 注入 CLR Profiler
    所需环境变量（启用 Profiling、Profiler CLSID、Profiler 原生库路径、Startup Hook、
    Additional Deps、Shared Store、自动探针主目录）与既有 OTLP 环境变量；启动命令仍为
    `dotnet <App>.dll`。实例 ID 沿用 docker 运行方式的既有规则。
  - Kubernetes：与 Java 同型，镜像需预装探针到固定路径；strategic merge patch 注入上述 CLR
    环境变量与 `OTEL_*`，实例 ID 沿用 Pod UID。
- 片段顶部统一一行支持范围说明：「仅支持 Linux x86_64 glibc（Ubuntu / Debian / CentOS 及同类
  容器镜像）；不支持 Alpine、ARM64、Windows」。
- `service.namespace` 必须等于已创建应用 ID、组织继承应用组织、OTLP 不携带组织 ID 等现有约定
  不变，.NET 不做例外。

### 前端

- 接入页 .NET 卡片改为可用，绑定 `language: dotnet`；描述文案补支持范围，i18n 中英同步。
- 不新增「本体 / 容器」两份下载，不新增 libc / 架构选择器。运行方式仍是与 Python 相同的三档。

### 文档

- 发布 Runbook 制品表、钉死版本表、归档步骤、初始化命令、验收地址各补 .NET 一行；来源为官方
  Release 的 `opentelemetry-dotnet-instrumentation-linux-glibc-x64.zip`，归档时改名为制品名并记录字节数与 SHA-256。
- APM 产品决策文档的探针版本表补 .NET v1.16.0。
- 功能清单「接入指引」支持语言补 .NET（标注 Linux x86_64 glibc）。

## Testing Decisions

好的测试只断言对外行为：制品名白名单、下载地址、片段文本中的关键指令与环境变量，以及
「不出现公网地址」；不断言片段的逐字内容或内部辅助函数。

- 探针制品服务：语言映射含五种语言；新制品名解析到新 key；非白名单制品名仍被拒绝；
  `apm_probe_init` 的 `--artifact` 接受新制品名。先验：`test_probe_artifacts.py`。
- 接入片段：现有按语言参数化的用例扩到 `dotnet`，三种运行方式都包含系统内下载地址、
  Profiler 原生库路径环境变量、`instrument.sh`（host）、`dotnet` 启动命令与支持范围说明；
  不包含 `github.com` / `nuget.org`；metrics / logs 导出器为关闭。先验：`test_ingest_snippets.py`。
- 开放下载接口：`dotnet` 制品的双租户用例，缺制品时返回 `probe_artifact_not_found`。先验：
  `test_api_permissions.py`。
- 前端：接入页 .NET 卡片可用且选择后出现三种运行方式；i18n 覆盖测试通过；`pnpm lint`、
  `pnpm type-check`。先验：`apm-i18n-coverage-test.ts`。

## Out of Scope

- Alpine / musl 制品与接入页「常规 Linux / Alpine」切换（第二版）。
- ARM64（企业版）。
- Windows / IIS、macOS、.NET Framework。
- 集合包或安装时自动探测 libc / 架构。
- 前四种语言按 glibc / musl 拆分（现有一份 Linux 包维持不变）。
- .NET metrics / logs 上报、Collector 卡片、eBPF、K8s Operator 注入。
- 在 149 等既有环境执行 `apm_probe_init`（由运维按发布手册处理，见 Further Notes）。

## Further Notes

- 与前四种语言的差异根因：Java jar、Node JS 包、Go 源码模块、Python 纯 wheel 都能用一份文件
  覆盖 Linux 主机与容器；.NET 自动探针是原生 CLR Profiler，官方按 libc × arch 拆包，
  没有等价的通吃文件。因此第一版以「只选一份、写清范围」代替「多份包或集合包」。
- glibc / musl 的切分轴是运行时的 C 库，不是「主机 / 容器」。Debian / Ubuntu 容器与主机同用
  glibc 包；Alpine 无论主机还是容器都需要 musl 包。据此否决了「本体版 / 容器版」两份下载。
- 部署侧的现存问题（发布流水线未执行 `apm_probe_init`、制品名与对象 key 不同）见
  [TencentBlueKing/bk-lite#5097](https://github.com/TencentBlueKing/bk-lite/issues/5097)；
  .NET 制品应作为第五项一并纳入该流水线要求。
- 相关 ADR：`0006`（区域 NATS / VictoriaTraces 管道）、`0008`（可信区域入口，客户端 `bk.*` 不进 Span）。
