## Why

当前节点管理已经具备 controller / installer / package 的基础多架构能力，但 builtin controller 仍由 Python 常量初始化，collector definition 也还没有把 CPU 架构作为正式维度接入运行时解析。与此同时，仓库已经存在 community + optional enterprise 的内容覆盖模式，适合把多架构“机制”保留在社区版，把 ARM64 等额外 definition / artifact 内容放到 enterprise overlay 中。

如果不继续补上这一层，会出现几个问题：

- controller 与 collector 的 builtin 内容来源不一致，难以扩展 enterprise overlay
- collector 仍按 `os + name` 查找，无法稳定支持架构专属 definition
- ARM64 collector 只能依赖 package 命名约定，无法通过 definition/routing 正式表达
- 社区版与商业版的职责边界不清晰

## What Changes

- 新增共享 JSON definition loader，统一加载 community + optional enterprise 内容，并允许 enterprise 覆盖同 ID 定义
- controller builtin 初始化从 Python 常量迁移到 JSON definition 文件
- collector definition 正式引入 `cpu_architecture` 维度，并支持 generic fallback
- collector 运行时解析升级为优先 `(os, arch, name)`，再回退 `(os, "", name)`
- community 默认仅内置 Windows x86_64 / Linux x86_64 controller definitions；enterprise 可补充 ARM64 或覆盖已有定义
- 为 node_mgmt 建立 server 侧 enterprise support-files 目录约定

## Capabilities

### New Capabilities
- `node-definition-enterprise-overlay`: builtin controller / collector definitions 支持 community + enterprise JSON overlay
- `collector-architecture-resolution`: collector definition、初始化与运行时解析支持 CPU 架构与 generic fallback

## Impact

- **Initialization**: `server/apps/node_mgmt/management/services/node_init/*`
- **Models**: `server/apps/node_mgmt/models/sidecar.py`
- **Runtime services/tasks**: `server/apps/node_mgmt/services/{package,sidecar,node}.py`, `server/apps/node_mgmt/tasks/installer.py`, `server/apps/node_mgmt/nats/node.py`
- **Support files**: `server/apps/node_mgmt/support-files/{controllers,collectors}`
- **Enterprise overlay**: `server/apps/node_mgmt/enterprise/support-files/{controllers,collectors}`
