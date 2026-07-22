# 2026 04 14 Multi Redis Tool Config

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-04-14-multi-redis-tool-config/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

当前 OpsPilot 内置 Redis 工具的配置协议只支持一套扁平连接参数，例如 `url`、`username`、`password`、`cluster_mode`。虽然一个智能体可以挂多个工具，但 Redis 工具运行时最终只会读取这一套固定键，因此同一个智能体无法稳定管理多个 Redis 实例。

用户期望在智能体配置中直接维护多个 Redis 实例：左侧展示实例列表，可新增/删除；每个实例拥有独立名称和连接参数；可单独执行“测试连接”，并在右上角看到未测试/成功/失败状态。这一需求不仅是表单增强，还要求 Redis 工具的持久化结构与执行时取参方式升级为多实例协议。

## What Changes

- 将内置 Redis 工具的配置从“单实例扁平参数”升级为“多实例列表 + 默认实例”。
- 为 Redis 工具提供实例级配置 UI，支持新增、删除、编辑 Redis 实例，并为实例名称提供默认命名规则 `Redis - n`。
- 为每个 Redis 实例增加独立的测试连接能力和状态展示：未测试、测试成功、测试失败。
- 调整 Redis 工具运行时配置契约，使其读取 `redis_instances` 与 `redis_default_instance_id`，而不是直接依赖单套 `url` 等字段。
- 为 Redis 子工具增加实例选择能力：未显式指定时使用默认实例，显式指定时切换到对应实例执行。

## Capabilities

### New Capabilities
- `redis-tool-multi-instance`: 定义单个智能体内的 Redis 工具可配置并使用多个 Redis 实例。

### Modified Capabilities
- `redis-tool-multi-instance`: Redis 工具的前端编辑方式、持久化数据结构、测试连接行为与运行时连接解析整体更新。

## Impact

- Web OpsPilot 智能体配置：工具选择器、Redis 工具编辑弹窗、实例级测试状态与交互文案。
- Server OpsPilot 工具执行链路：技能工具参数持久化、Redis 连接配置解析、Redis 工具调用时的实例选择。
- Redis 内置工具集：连接构造函数、工具描述提示、实例切换与测试连接接口。

## Implementation Decisions

## Context

当前 Redis 内置工具的配置元数据来自 `CONSTRUCTOR_PARAMS`，最终在 `SkillTools.params.kwargs` 中表现为一组固定字段。技能保存时，所填值被写入 `LLMSkill.tools[].kwargs`；执行时 `chat_service` 会把这些键值对合并进 `extra_config`，再透传到 LangGraph `configurable`。Redis 连接层 `redis/connection.py` 只读取 `url`、`username`、`password`、`ssl`、`cluster_mode` 等单实例字段。

这条链路决定了当前能力上限：

- 同一个 Redis 工具只能表达一套连接参数。
- 如果尝试塞入两套同名字段，后写值会覆盖先写值。
- 现有技能工具编辑器对大多数内置工具是通用表单，不足以承载“左侧实例列表 + 右侧实例详情 + 单实例测试状态”的 Redis 专属交互。

## Goals / Non-Goals

**Goals:**
- 让单个智能体内的 Redis 工具支持维护多个 Redis 实例。
- 提供与产品草图一致的实例级配置体验，包括默认命名、新增/删除、实例级测试连接和状态展示。
- 将 Redis 运行时配置升级为多实例协议，避免同名参数互相覆盖。
- 保持 Redis 子工具默认可在未指定实例时使用默认实例，并在需要时切换到指定实例。

**Non-Goals:**
- 不重写所有内置工具的通用参数协议，仅收敛 Redis 工具的多实例场景。
- 不要求保存前必须测试成功，测试连接仅作为配置校验辅助。
- 不在本次变更中扩展 Redis 工具的权限模型或引入新的外部 Redis 管理服务。

## Decisions

### 1. Redis 工具以单个 tool 持有多个实例，而不是复制多个 Redis tool

技能中仍然只选择一次 Redis 工具，但该工具的配置值改为持有 `instances[]` 与 `default_instance_id`。

选择原因：用户心智是“给一个智能体配置多个 Redis 实例”，而不是“在智能体上挂多个外观相同的 Redis 工具”。保持单个工具入口也能避免工具列表、权限配置与模型理解上的重复噪音。

备选方案：
- 为每个 Redis 实例复制一个独立 tool。否决，因为当前执行链路仍会把 Redis 连接键拍平，且会让工具选择与展示变得混乱。

### 2. 多实例配置作为 Redis tool 自有契约存储为命名字段

Redis 工具不再依赖 `url`、`username`、`password` 等直接平铺到技能工具值中，而是将完整配置收敛为如下键：

- `redis_instances`
- `redis_default_instance_id`

其中 `redis_instances` 的值为 JSON 结构，包含多个实例及其连接属性。

选择原因：这样可以在不推翻通用 `kwargs -> extra_config` 合并流程的前提下，避免多实例字段覆盖问题，并把改动范围集中在 Redis 工具自身。

### 3. Redis 工具编辑器采用专属 UI，而不是复用通用 kwargs 表单

前端对 Redis 内置工具增加专属编辑器：

- 左侧：实例列表，支持新增/删除与选中
- 右侧：当前实例详情表单
- 右上角：当前实例测试状态
- 底部：测试连接 / 取消 / 保存

实例名称默认按 `Redis - n` 生成；当用户修改实例任一连接字段后，该实例状态立即回到“未测试”。

选择原因：截图中的交互是面向实例集合的编辑模型，通用 `Form.List(kwargs)` 无法自然表达实例列表、选中态和局部状态复位。

### 4. 测试连接为实例级后端接口，状态只针对当前编辑数据

后端提供 Redis 实例测试连接接口，输入为单个实例的当前表单值，输出为 `success/failure` 及错误信息。前端根据返回结果将该实例状态显示为：

- `untested`
- `success`
- `failed`

状态用于当前编辑会话中的反馈，不作为长期事实写入技能配置；当实例字段变更后状态重置为 `untested`。

选择原因：测试状态的意义是“当前配置是否可连通”，而不是一条可长期持久化的资产健康记录。持久化最后一次结果既容易过期，也会让编辑回显产生误导。

### 5. Redis 运行时增加“默认实例 + 显式实例”两级选择

Redis 连接层新增如下行为：

- 若工具调用未提供实例标识，则使用 `redis_default_instance_id`
- 若提供 `instance_id` 或 `instance_name`，则解析到对应实例后建立连接
- 若指定实例不存在，则返回明确错误

Redis 各子工具共享同一套实例解析逻辑。

选择原因：默认实例保证简单请求不增加负担，显式实例则满足多 Redis 管理的核心场景。

### 6. Redis 工具提示中展示可用实例名称

在 Redis 工具装载时，系统应把当前已配置的实例名称列表加入工具描述或附加提示，帮助模型在需要跨实例操作时显式选择正确实例。

选择原因：即便后端支持 `instance_name`，模型也需要知道有哪些可选实例名，才能稳定地产生正确调用。

## Data Shape

### Skill tool kwargs

```json
[
  {
    "key": "redis_instances",
    "value": "[{\"id\":\"redis-1\",\"name\":\"redis-prod-01\",\"url\":\"redis://10.0.1.15:6379/0\",\"username\":\"\",\"password\":\"\",\"ssl\":false,\"ssl_ca_path\":\"\",\"ssl_keyfile\":\"\",\"ssl_certfile\":\"\",\"ssl_cert_reqs\":\"\",\"ssl_ca_certs\":\"\",\"cluster_mode\":false}]"
  },
  {
    "key": "redis_default_instance_id",
    "value": "redis-1"
  }
]
```

### Parsed runtime config

```json
{
  "redis_instances": [
    {
      "id": "redis-1",
      "name": "redis-prod-01",
      "url": "redis://10.0.1.15:6379/0",
      "username": "",
      "password": "",
      "ssl": false,
      "ssl_ca_path": "",
      "ssl_keyfile": "",
      "ssl_certfile": "",
      "ssl_cert_reqs": "",
      "ssl_ca_certs": "",
      "cluster_mode": false
    },
    {
      "id": "redis-2",
      "name": "Redis - 2",
      "url": "",
      "username": "",
      "password": "",
      "ssl": false,
      "ssl_ca_path": "",
      "ssl_keyfile": "",
      "ssl_certfile": "",
      "ssl_cert_reqs": "",
      "ssl_ca_certs": "",
      "cluster_mode": false
    }
  ],
  "redis_default_instance_id": "redis-1"
}
```

### Tool call shape

```json
{
  "instance_name": "redis-prod-01",
  "key": "user:1"
}
```

`instance_name` / `instance_id` 为可选字段；未提供时走默认实例。

## Risks / Trade-offs

- Redis 工具将成为第一个需要专属编辑器的内置工具，前端工具编辑流程会出现“通用表单 + 特殊工具表单”双路径。
- `redis_instances` 若以 JSON 字符串保存在 kwargs 中，前后端都需要处理解析与校验错误，但这是换取最小通用协议改动的结果。
- 若模型不显式指定实例，所有操作都会落到默认实例，因此默认实例的设置与提示文案必须足够清晰。
- 旧的单实例 Redis 配置需要迁移或兼容读取，否则已有技能中的 Redis 工具可能需要重新保存。

## Migration Plan

1. 前端先支持读取旧单实例 Redis 配置，并在编辑时转换为单元素 `instances[]`。
2. 保存后统一写入新协议：`redis_instances` + `redis_default_instance_id`。
3. 后端 Redis 连接层优先读取新协议；若未发现新协议，可临时回退读取旧单实例键，保证已存在技能不中断。
4. 发布说明中明确：Redis 工具已支持多实例，重新编辑并保存可完成配置协议升级。

## Open Questions

- 是否需要在 UI 中允许用户显式切换“默认实例”，还是默认取列表第一项并仅在删除/新增时自动维护。
- 旧单实例配置的兼容回退需要保留一个版本周期，还是允许只在编辑页做一次性转换。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-14
```

## Capability Deltas

### redis-tool-multi-instance

## ADDED Requirements

### Requirement: Redis 工具支持多个实例配置

单个智能体中的 Redis 工具 SHALL 允许用户配置多个 Redis 实例，而不是仅支持一套连接参数。

#### Scenario: 新增 Redis 实例

- **WHEN** 用户在 Redis 工具编辑器中点击“新增”
- **THEN** 系统 SHALL 新建一个 Redis 实例配置项
- **AND** 新实例 SHALL 获得默认名称 `Redis - n`
- **AND** 用户 SHALL 可以继续编辑该实例的连接字段

#### Scenario: 保存多个 Redis 实例

- **WHEN** 用户为同一个 Redis 工具配置多个 Redis 实例并保存
- **THEN** 系统 SHALL 持久化这些实例及默认实例信息
- **AND** 后端 SHALL 不再只保留最后一套 Redis 连接参数

### Requirement: Redis 实例具有独立测试连接状态

Redis 工具编辑器 SHALL 为每个实例提供独立的测试连接能力与状态反馈。

#### Scenario: 初始或字段变更后的状态

- **WHEN** 用户新建一个 Redis 实例或修改该实例任一连接字段
- **THEN** 该实例状态 SHALL 显示为未测试

#### Scenario: 测试连接成功

- **WHEN** 用户对某个 Redis 实例执行测试连接且后端验证成功
- **THEN** 该实例状态 SHALL 显示为测试成功

#### Scenario: 测试连接失败

- **WHEN** 用户对某个 Redis 实例执行测试连接且后端验证失败
- **THEN** 该实例状态 SHALL 显示为测试失败
- **AND** 系统 SHALL 返回可用于提示用户的问题信息

### Requirement: Redis 工具支持默认实例与显式实例切换

Redis 工具运行时 SHALL 在多个已配置实例之间稳定选择连接目标。

#### Scenario: 未显式指定实例时执行

- **WHEN** Redis 子工具调用未提供实例标识
- **THEN** 系统 SHALL 使用 Redis 工具的默认实例建立连接

#### Scenario: 显式指定实例时执行

- **WHEN** Redis 子工具调用提供 `instance_id` 或 `instance_name`
- **THEN** 系统 SHALL 解析到对应 Redis 实例并使用该实例建立连接

#### Scenario: 指定实例不存在

- **WHEN** Redis 子工具调用指定的实例标识无法匹配到已配置实例
- **THEN** 系统 SHALL 返回明确错误
- **AND** 系统 SHALL 不得静默回退到其他 Redis 实例

### Requirement: 旧单实例 Redis 配置可被平滑升级

Redis 工具配置协议升级后 SHALL 允许已存在的单实例配置被读取并转换到多实例协议。

#### Scenario: 打开旧配置的 Redis 工具

- **WHEN** 用户编辑一个仍使用旧单实例字段保存的 Redis 工具
- **THEN** 系统 SHALL 能读取该配置
- **AND** 编辑器 SHALL 将其表现为仅包含一个实例的多实例列表

#### Scenario: 重新保存旧配置

- **WHEN** 用户重新保存一个旧单实例 Redis 配置
- **THEN** 系统 SHALL 按新的多实例协议持久化该工具配置

## Work Checklist

## 1. Web Redis tool editor

- [x] 1.1 在 OpsPilot 技能工具编辑流程中为内置 Redis 工具增加专属编辑器，支持实例列表、实例详情和新增/删除交互。
- [x] 1.2 为 Redis 实例实现默认名称 `Redis - n`、字段变更后状态重置、默认实例维护与保存前表单校验。
- [x] 1.3 增加实例级“测试连接”交互与三态状态展示：未测试、测试成功、测试失败。
- [x] 1.4 补齐 Redis 多实例编辑器相关中英文文案与状态文案，确保页面展示与产品草图一致。

## 2. Server Redis config protocol

- [x] 2.1 调整 Redis 工具配置读写协议，支持 `redis_instances` 与 `redis_default_instance_id`，并补齐旧单实例配置的读取兼容。
- [x] 2.2 新增 Redis 实例测试连接接口，按单实例输入返回成功或失败结果及错误信息。
- [x] 2.3 改造 Redis 连接解析逻辑，使其按默认实例或显式实例标识建立连接，并在实例不存在时返回明确错误。
- [x] 2.4 为 Redis 子工具补充可选的实例选择参数与提示信息，使模型可在多实例间切换执行。

## 3. Validation

- [x] 3.1 执行 `cd web && pnpm lint && pnpm type-check`，确认 Redis 工具编辑器变更无 lint 和类型问题。
- [x] 3.2 执行与 server Redis 工具相关的最小测试或验证命令，确认多实例配置解析、测试连接与实例切换逻辑正常。
- [ ] 3.3 手动验证智能体中的 Redis 工具：可新增多个实例、实例状态按测试结果变化、保存后默认实例可执行、显式指定实例可切换。
