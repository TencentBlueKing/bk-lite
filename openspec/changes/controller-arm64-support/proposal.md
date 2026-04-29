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
