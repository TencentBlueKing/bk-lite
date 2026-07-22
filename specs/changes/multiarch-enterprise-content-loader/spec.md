# Multiarch Enterprise Content Loader

Status: done

## Migration Context

- Legacy source: `openspec/changes/multiarch-enterprise-content-loader/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-29
```

## Capability Deltas

### collector-architecture-resolution

## ADDED Requirements

### Requirement: collector definitions MUST support architecture-specific and generic records simultaneously

The system SHALL allow collector definitions to coexist for the same collector name and operating system across multiple CPU architectures.

#### Scenario: import generic and ARM64 collector definitions for the same collector name
- **GIVEN** a generic Linux `Telegraf` collector definition with `cpu_architecture = ""`
- **AND** an ARM64 Linux `Telegraf` collector definition with `cpu_architecture = "arm64"`
- **WHEN** the builtin collector import runs
- **THEN** both collector records MUST be stored successfully
- **AND** the two records MUST remain distinguishable by `(node_operating_system, cpu_architecture, name)`

### Requirement: runtime collector resolution MUST prefer exact architecture matches and fall back to generic definitions

The system SHALL resolve collector definitions by operating system, collector name, and normalized CPU architecture, and SHALL use generic definitions as a fallback when no architecture-specific definition exists.

#### Scenario: install or configure collector for an ARM64 node with a matching ARM64 definition
- **GIVEN** a Linux node reports `cpu_architecture = "arm64"`
- **AND** both generic and ARM64 collector definitions exist for the requested collector name
- **WHEN** the system resolves the collector during package installation or config creation
- **THEN** the ARM64 collector definition MUST be selected

#### Scenario: fall back to generic collector definition when no architecture-specific definition exists
- **GIVEN** a Linux node reports `cpu_architecture = "arm64"`
- **AND** only a generic collector definition exists for the requested collector name
- **WHEN** the system resolves the collector during package installation or config creation
- **THEN** the generic collector definition MUST be selected
- **AND** the operation MUST continue without requiring an ARM64-specific definition

### node-definition-enterprise-overlay

## ADDED Requirements

### Requirement: node_mgmt builtin definitions MUST support community and optional enterprise overlays

The system SHALL load builtin controller and collector definitions from community content first and SHALL then apply enterprise content when an enterprise definition directory exists.

#### Scenario: enterprise overlay overrides a community definition
- **GIVEN** a community definition file contains a builtin definition with ID `controller_linux`
- **AND** the enterprise definition directory exists and contains a definition with the same ID
- **WHEN** node_mgmt builtin definitions are loaded
- **THEN** the enterprise definition MUST override the community definition for that ID

#### Scenario: enterprise overlay adds new architecture-specific content
- **GIVEN** the community definitions contain only Windows x86_64 and Linux x86_64 controller definitions
- **AND** the enterprise definition directory contains a Linux ARM64 controller definition with a new ID
- **WHEN** node_mgmt builtin definitions are loaded
- **THEN** the Linux ARM64 definition MUST be included in the merged result
- **AND** the community definitions MUST remain available

### Requirement: controller builtin initialization MUST use JSON definitions without reusing definition IDs as model primary keys

The system SHALL initialize builtin `Controller` rows from JSON definitions while keeping Django model primary keys managed by the database.

#### Scenario: initialize controller from JSON definition with string ID
- **GIVEN** a controller JSON definition contains `id: "controller_linux"`
- **WHEN** the builtin controller initialization runs
- **THEN** the system MUST create or update the `Controller` row using `(os, cpu_architecture, name)` matching
- **AND** the JSON definition ID MUST NOT be written to the integer `Controller.id` database primary key

## Work Checklist

## 1. Definition loading foundation

- [x] 1.1 Add a shared JSON definition loader for community + optional enterprise directories
- [x] 1.2 Support merge-by-id semantics and allow enterprise definitions to override community definitions
- [x] 1.3 Add node_mgmt enterprise support-files placeholders for controllers and collectors

## 2. Controller definition migration

- [x] 2.1 Move builtin controller initialization from Python constants to JSON definitions
- [x] 2.2 Ensure definition IDs are used only for merge semantics and not written into the integer `Controller.id` primary key
- [x] 2.3 Seed community controller definitions with Windows x86_64 and Linux x86_64 defaults

## 3. Collector architecture modeling

- [x] 3.1 Add `Collector.cpu_architecture`
- [x] 3.2 Change collector uniqueness to `(node_operating_system, cpu_architecture, name)`
- [x] 3.3 Keep generic collectors compatible with empty architecture values and existing IDs

## 4. Runtime architecture-aware collector resolution

- [x] 4.1 Add a shared exact-then-generic collector resolution helper
- [x] 4.2 Update collector package resolution/install paths to use architecture-aware collector lookup
- [x] 4.3 Update default config creation to prefer exact-arch collectors and still allow generic fallback
- [x] 4.4 Update NATS config creation paths to resolve collectors/configurations with architecture awareness
- [x] 4.5 Audit remaining collector list/filter/display paths and implement minimal architecture-aware backend API exposure for filter/list/retrieve behavior

## 5. Verification

- [x] 5.1 Extend targeted architecture support tests for definition loader and collector architecture records
- [x] 5.2 Add targeted verification for NATS config creation exact-match and generic-fallback behavior
- [x] 5.3 Run `uv run pytest apps/node_mgmt/tests/test_architecture_support.py -q`
- [x] 5.4 Run `uv run python -m compileall apps/node_mgmt/nats/node.py apps/node_mgmt/tests/test_architecture_support.py`
- [x] 5.5 Add targeted verification for collector API filter/list/retrieve architecture exposure
