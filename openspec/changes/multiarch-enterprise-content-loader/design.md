## Context

现有多架构工作已经把 `cpu_architecture` 引入到节点、控制器包、安装器等核心链路，但 builtin definition 层仍不完整：

- `Controller` 仍靠 Python 常量初始化，不利于 enterprise 内容扩展
- `Collector` 已有 support-files 目录，但模型唯一键与运行时查找仍主要沿用 `os + name`
- 社区版仓库默认不存在 enterprise 目录，企业版部署时会把额外内容打入对应 app 目录

仓库中已有多处 server/web overlay 先加载 community、再加载 enterprise 覆盖的模式，因此 node_mgmt 也应复用这一思路，而不是把多架构逻辑分叉到 enterprise 代码中。

## Goals / Non-Goals

**Goals**
- 在社区版中实现 definition loader 与多架构解析逻辑
- 让 controller / collector 都支持 community + optional enterprise JSON 内容加载
- 让 collector 以 `cpu_architecture` 作为正式维度，但保留 generic fallback
- 保持旧 generic collector ID 可继续工作

**Non-Goals**
- 不要求社区版立即内置 ARM64 collector 内容
- 不强制把历史 generic collector 全量回填成 `x86_64`
- 不把 enterprise 逻辑代码落到社区版以外的位置
- 不在本次变更中引入新的前端安装交互

## Decisions

### 1. 使用共享 JSON definition loader

新增共享 loader，按以下顺序加载：

1. community definition 目录
2. enterprise definition 目录（若存在）

记录按 definition `id` merge；enterprise 在相同 `id` 下允许覆盖 community 定义。

### 2. Controller 改为 JSON definition 初始化

controller builtin 内容迁移到 JSON 文件中，但 `Controller` Django 模型仍保留整型主键；因此 JSON 中的 `id` 仅作为 definition merge key，创建数据库对象时不能直接写入模型主键。

### 3. Collector 唯一键升级为 `(node_operating_system, cpu_architecture, name)`

Collector 定义新增 `cpu_architecture` 字段，允许同一 OS/name 下同时存在：

- generic definition：`cpu_architecture = ""`
- arch-specific definition：如 `cpu_architecture = "arm64"`

这使 ARM64 definition 可以增量加入，而不破坏旧 generic collector。

### 4. 运行时解析采用 exact-first + generic-fallback

所有需要按名称解析 collector definition 的路径都应遵循：

1. 先查 `(os, normalized_arch, name)`
2. 若不存在，再查 `(os, "", name)`

这样可以兼容：

- 历史 generic collector
- 仅 enterprise 提供部分 ARM64 collector definition 的场景
- 节点仍未识别出 CPU 架构时的兼容行为

### 5. 不改旧 generic collector 的 ID

已有 generic collector ID 已广泛用于配置、任务状态和 sidecar 关联，不能为“补架构”而重写旧 ID。

策略：

- 旧 generic collector 保持原 ID
- 新增 ARM64 collector 时使用新 ID（如 `telegraf_linux_arm64`）

## Runtime Flow

### Builtin definition initialization
1. 读取 community definitions
2. 若 enterprise 目录存在，则继续读取并覆盖同 ID 项
3. controller 按 `(os, arch, name)` create/update
4. collector 按 definition ID create/update，并允许 generic 与 arch-specific 共存

### Collector resolution during runtime
1. 从节点或请求中获取 CPU 架构并归一化
2. 解析 collector definition 时优先 exact arch
3. exact 不存在时回退 generic
4. 继续使用解析后的 collector ID 驱动配置、安装状态和动作任务

## Risks / Trade-offs

- 若 enterprise 覆盖错误定义，community 内容会被替换；通过按 ID 覆盖和 JSON 审查控制风险
- 若某运行时路径遗漏 arch-aware lookup，ARM64 节点可能错误复用 generic collector；需补齐关键执行路径
- controller 改成 JSON 后，definition ID 与数据库 ID 含义不同，初始化代码必须显式忽略 definition ID 写库
