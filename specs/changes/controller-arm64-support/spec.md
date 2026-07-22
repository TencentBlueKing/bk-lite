# Controller Arm64 Support

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/controller-arm64-support/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

当前节点管理控制器、安装器、控制器包默认以单一 Linux `x86_64` 形态运行，无法为 Linux ARM64 节点自动分发对应 installer 与控制器包。同时，节点虽然在 sidecar 上报链路中已有 `architecture` 概念，但服务端未完整持久化与展示，导致 ARM64 节点无法自动匹配控制器包、节点属性缺少 CPU 架构、历史节点缺少补齐方案、发布时也缺少多架构 installer/package 的一致性校验。

## What Changes

- 支持 Linux `x86_64` / `ARM64` 双架构控制器
- 原 Linux 控制器展示为 **Linux（x86_64）控制器**
- 增加 **Linux（ARM64）控制器**
- 控制器展示增加架构标签：`x86_64` / `ARM64`
- 安装页交互结构保持不变，不新增架构选择
- 远程安装时先探测目标节点 CPU 架构，再自动选择对应 installer / controller package
- curl/bootstrap 安装时先探测本机架构，再请求对应 installer/session
- 节点属性新增 `cpu_architecture`
- sidecar 回调时将 `architecture` 归一化后写入 `Node.cpu_architecture`
- 提供历史节点架构回填命令
- 提供发布校验命令，检查 installer 与 controller package 是否齐备

## Capabilities

### New Capabilities
- `controller-architecture-routing`: 按 CPU 架构自动分发 installer 与 controller package
- `node-cpu-architecture`: 节点 CPU 架构持久化、展示与历史补齐
- `architecture-rollout-ops`: 多架构发布校验与回填运维能力

## Impact

- **Model**: `server/apps/node_mgmt/models/{sidecar,package,installer}.py`
- **Services**: `server/apps/node_mgmt/services/{installer,installer_session,package,sidecar,version_upgrade}.py`
- **Tasks**: `server/apps/node_mgmt/tasks/{installer,version_discovery}.py`
- **Views**: `server/apps/node_mgmt/views/{installer,sidecar,controller,package}.py`
- **Commands**: `installer_init`, `controller_package_init`, `collector_package_init`, `verify_architecture_rollout`, `backfill_node_cpu_architecture`
- **Frontend**: node-manager 控制器展示、节点属性、安装页版本去重
- **Storage**: installer / package 文件仍存于 NATS JetStream Object Store，而非 MinIO

## Implementation Decisions

## Context

原系统中控制器与控制器包的选择主要按 `os` 维度处理：

- `Controller`: `os + name`
- `PackageVersion`: `os + object + version`
- installer latest path: `installer/<os>/<filename>`

这意味着系统默认“同一 OS 只有一套控制器/安装器”。当 Linux 同时需要 `x86_64` 与 `ARM64` 两种控制器时，会出现同版本 Linux 控制器包无法按架构并存、远程安装无法按目标节点架构自动下发、curl 安装无法按本机架构下载 installer、节点属性无法体现 CPU 架构、历史节点缺少补齐方案等问题。

## Goals / Non-Goals

**Goals**
- 支持 Linux `x86_64` / `ARM64` 双架构控制器
- 保持安装页交互不变
- 自动完成 installer / package 的架构分流
- 节点可持久化并展示 CPU 架构
- 历史节点可按需补齐 CPU 架构
- 提供发布校验与上线 runbook

**Non-Goals**
- 不支持 Windows ARM64 installer / controller package
- 不强制全量历史节点都立即补齐 CPU 架构
- 不对所有采集器运行逻辑同步做多架构改造
- 不把“未知节点架构”默认写死成 `x86_64`

## Decisions

### 1. 将 `cpu_architecture` 作为结构化字段引入

新增字段：

- `Node.cpu_architecture`
- `Controller.cpu_architecture`
- `PackageVersion.cpu_architecture`
- `ControllerTaskNode.cpu_architecture`

原因：架构已是核心业务维度，不适合仅通过 tag 表达。

### 2. 历史数据采用“控制器/包回填，节点保留未知”的兼容策略

#### 回填为 `x86_64`
- `Controller`
- `PackageVersion`

#### 保留空值
- `Node`

原因：历史控制器与包默认就是 `x86_64`；节点空值表示未知，比错误写成 `x86_64` 更安全。

### 3. 安装页保持不变，`package_id` 作为版本锚点

前端仍选择一个 package 作为版本锚点；后端在远程安装或 bootstrap/session 阶段再按 `os + object + version + cpu_architecture` 解析实际包。这样可以保持安装页不新增架构选择，避免用户理解架构差异，并最小化前端改造。

### 4. curl/bootstrap 安装与远程安装都必须做架构探测

#### 远程安装
- Linux: `uname -m`
- Windows: `cmd /c echo %PROCESSOR_ARCHITECTURE%`

#### curl/bootstrap
- 本机 shell 中执行架构探测
- 把架构通过 `arch` 参数带到 installer download / session

### 5. CPU 架构统一归一化

统一保留：
- `x86_64`
- `arm64`

映射：
- `amd64 -> x86_64`
- `aarch64 -> arm64`

### 6. 文件存储仍使用 NATS JetStream Object Store

installer / controller package / collector package 继续通过 `JetStreamService` 存储，bucket 为 `NATS_NAMESPACE` 对应的 object store。不是 MinIO。

## End-to-End Flows

### Remote Install
1. 用户选择控制器版本（前端 package 作为版本锚点）
2. server 创建安装任务
3. 远程连接目标机探测 CPU 架构
4. 归一化架构
5. 解析实际 installer / controller package
6. 执行安装
7. sidecar 回调上报节点信息
8. server 写入 `Node.cpu_architecture`

### Curl / Bootstrap Install
1. 用户执行 install command
2. bootstrap 本机探测 CPU 架构
3. 请求 `installer/linux/download?arch=...`
4. 请求 `installer/session?arch=...`
5. 下载对应架构 installer
6. installer 按 session 中的包信息安装控制器
7. sidecar 回调写入 CPU 架构

### Historical Node Backfill
1. 选出 `Node.cpu_architecture == ""` 的节点
2. 查找最近一次 `ControllerTaskNode`
3. 复用其 SSH 凭据远程探测架构
4. 归一化后写回 `Node.cpu_architecture`
5. 无凭据节点跳过

## Operational Commands

### Build installers
```bash
cd agents/sidecar-installer
make release-artifacts
```

### Upload installers
```bash
cd server
python manage.py installer_init --os windows --cpu_architecture x86_64 --file_path /path/to/dist/windows/x86_64/bklite-controller-installer.exe
python manage.py installer_init --os linux --cpu_architecture x86_64 --file_path /path/to/dist/linux/x86_64/bklite-controller-installer
python manage.py installer_init --os linux --cpu_architecture arm64 --file_path /path/to/dist/linux/arm64/bklite-controller-installer
```

### Upload controller packages
```bash
python manage.py controller_package_init --os linux --cpu_architecture x86_64 --object Controller --pk_version <version> --file_path /path/to/fusion-collectors-x86_64.tar.gz
python manage.py controller_package_init --os linux --cpu_architecture arm64 --object Controller --pk_version <version> --file_path /path/to/fusion-collectors-arm64.tar.gz
```

### Verify rollout
```bash
python manage.py verify_architecture_rollout --version <version>
```

### Backfill historical nodes
```bash
python manage.py backfill_node_cpu_architecture --limit 100
python manage.py backfill_node_cpu_architecture --node-id <node_id>
python manage.py backfill_node_cpu_architecture --dry-run --limit 20
```

## Risks / Trade-offs

- ARM64 产物未完整上传会导致 ARM64 节点安装失败；通过 `verify_architecture_rollout` 缓解。
- 现网 sidecar 若未上报 `architecture`，旧节点不会自然补齐；通过 backfill 命令缓解。
- 历史节点无可复用 SSH 凭据时，backfill 会跳过；保持空值优于误写 `x86_64`。
- Windows 当前仅支持 `x86_64` installer 上传，但节点仍记录 CPU 架构。

## Capability Deltas

### architecture-rollout-ops

## ADDED Requirements

### Requirement: Rollout verification MUST confirm required multi-architecture artifacts

系统必须提供发布校验命令，确认 installer 与控制器包的多架构产物是否齐备。

#### Scenario: verify Linux x86_64 and ARM64 rollout artifacts
- **Given** 运维已上传 Windows `x86_64` installer、Linux `x86_64` installer、Linux `arm64` installer
- **And** 已上传指定版本的 Linux `x86_64` 与 Linux `arm64` 控制器包
- **When** 执行 `verify_architecture_rollout --version <version>`
- **Then** 系统必须确认上述 installer 与控制器包存在
- **And** 输出当前仍为空架构的节点数量

### Requirement: Installer upload MUST support explicit CPU architecture

installer 上传命令必须显式支持 CPU 架构参数，以便分别上传 Linux `x86_64` 与 Linux `arm64` installer。

#### Scenario: upload Linux ARM64 installer
- **Given** 运维执行 `installer_init --os linux --cpu_architecture arm64`
- **When** 上传 installer 文件
- **Then** installer 必须存储到 Linux `arm64` 对应的 latest path

### Requirement: Historical backfill SHOULD skip nodes without reusable credentials

历史节点架构回填命令在没有可复用安装凭据时应跳过节点，而不是猜测默认架构。

#### Scenario: skip node without credentials during backfill
- **Given** 某历史节点 `cpu_architecture` 为空
- **And** 系统中没有该节点可复用的安装凭据
- **When** 执行 `backfill_node_cpu_architecture`
- **Then** 系统应跳过该节点
- **And** 不得将其架构默认写成 `x86_64`

### controller-architecture-routing

## ADDED Requirements

### Requirement: Remote controller installation MUST resolve packages by detected CPU architecture

远程安装控制器时，系统必须先探测目标节点 CPU 架构，再根据操作系统、版本锚点和探测到的架构解析最终安装包。

#### Scenario: install ARM64 controller package on Linux ARM node
- **Given** 用户选择 Linux 控制器版本 `<version>`
- **And** 系统中存在该版本的 Linux `x86_64` 与 Linux `arm64` 控制器包
- **When** 远程安装探测到目标节点架构为 `arm64`
- **Then** 系统必须选择 Linux `arm64` 控制器包执行安装
- **And** 不得下发 Linux `x86_64` 控制器包

### Requirement: Bootstrap install MUST download installer and session by local architecture

用户通过 curl/bootstrap 安装控制器时，系统必须先识别本机架构，并请求对应架构的 installer 与 installer session。

#### Scenario: bootstrap install on ARM64 Linux host
- **Given** 用户在 Linux ARM64 主机执行控制器安装命令
- **When** bootstrap 脚本探测到本机架构为 `arm64`
- **Then** 系统必须请求 `arm64` 对应的 installer download 与 installer session
- **And** installer 中的包信息必须与 `arm64` 控制器包匹配

### node-cpu-architecture

## ADDED Requirements

### Requirement: Nodes MUST persist normalized CPU architecture

系统必须接收并保存节点上报的 CPU 架构信息，且统一归一化为业务标准值。

#### Scenario: normalize sidecar-reported architecture
- **Given** sidecar 上报 `architecture = aarch64`
- **When** server 处理节点更新
- **Then** `Node.cpu_architecture` 必须被保存为 `arm64`

### Requirement: Historical nodes MUST support CPU architecture backfill

系统必须提供管理命令，允许对历史空架构节点按需执行远程探测与回填。

#### Scenario: backfill historical node architecture with reusable credentials
- **Given** 某节点 `cpu_architecture` 为空
- **And** 系统中存在该节点最近一次控制器安装的可复用 SSH 凭据
- **When** 执行 `backfill_node_cpu_architecture`
- **Then** 系统必须远程探测该节点 CPU 架构并写回 `Node.cpu_architecture`

### Requirement: Nodes SHOULD display CPU architecture in node management

节点管理页面应展示节点 CPU 架构属性。

#### Scenario: display node architecture in node list
- **Given** 节点 `cpu_architecture = x86_64`
- **When** 用户查看节点属性
- **Then** 页面应显示 CPU 架构为 `x86_64`

## Work Checklist

## 1. 数据模型与兼容

- [x] 1.1 为 `Node` 新增 `cpu_architecture`
- [x] 1.2 为 `Controller` 新增 `cpu_architecture`
- [x] 1.3 为 `PackageVersion` 新增 `cpu_architecture`
- [x] 1.4 为 `ControllerTaskNode` 新增 `cpu_architecture` 与 `resolved_package_version_id`
- [x] 1.5 历史 `Controller` / `PackageVersion` 数据回填 `x86_64`

## 2. 安装链路

- [x] 2.1 远程安装前按目标节点架构探测并解析实际包
- [x] 2.2 bootstrap/curl 安装按本机架构获取 installer 与 session
- [x] 2.3 installer metadata / manifest 支持按架构返回

## 3. 节点与版本发现

- [x] 3.1 sidecar 回调将 `architecture` 归一化并写入 `Node.cpu_architecture`
- [x] 3.2 节点属性展示 CPU 架构
- [x] 3.3 版本发现按架构优先匹配控制器定义与最新版本

## 4. 运维发布能力

- [x] 4.1 `installer_init` 支持 `--cpu_architecture`
- [x] 4.2 `controller_package_init` / `collector_package_init` 支持 `--cpu_architecture`
- [x] 4.3 sidecar-installer 构建支持 Linux x86_64 / ARM64 发布产物
- [x] 4.4 新增 `verify_architecture_rollout`
- [x] 4.5 新增 `backfill_node_cpu_architecture`
- [x] 4.6 补充 rollout checklist 与回填说明文档

## 5. 验证

- [x] 5.1 补充自动化测试：架构归一化、包解析、installer/session、remote install、sidecar 回调、view/open_api、发布命令、backfill 命令
- [x] 5.2 运行 `uv run pytest apps/node_mgmt/tests/test_architecture_support.py -q`
- [ ] 5.3 手动验证 Linux x86_64 curl 安装
- [ ] 5.4 手动验证 Linux ARM64 curl 安装
- [ ] 5.5 手动验证 Linux x86_64 远程安装
- [ ] 5.6 手动验证 Linux ARM64 远程安装
- [ ] 5.7 手动验证发布校验与历史节点回填在真实环境中的表现
