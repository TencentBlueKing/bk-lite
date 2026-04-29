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
