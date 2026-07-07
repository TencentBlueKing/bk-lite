# 集成中心设计方案

## 1. 3 分钟摘要

### 1.1 业务目标

BK-Lite 需要一套统一的集成中心，用来管理外部系统类型、外部系统实例，以及这些实例向业务模块提供的能力。

当前第一批只聚焦三类 capability：

- 用户同步
- 登录认证
- 按用户 IM 通知

### 1.2 核心结论

1. 集成中心不是通用 iPaaS，而是面向 BK-Lite 业务域的集成底座。
2. 平台采用统一核心模型：**Provider -> IntegrationInstance -> Capability Binding -> Business Runtime Data**。
3. Provider 负责静态声明与页面渲染；Adapter 以代码级插件方式负责执行与外部系统兼容。
4. 页面渲染与运行时执行由同一份 provider manifest 驱动，避免页面模型和执行模型分裂。
5. 当前实现仍保留既有统一 HTTP 登录入口和既有 Channel 体系：登录认证已经切换到新的 binding 驱动流程，IM 应用通知作为独立能力并列接入，而不是一次性替换旧通知链路。

### 1.3 当前明确不做

- 任意跨系统流程编排
- 让用户自由拼装自动化流程
- 运行时热插拔、远程安装或插件市场
- 过早引入 manifest 多版本治理

### 1.4 关键风险与注意事项

1. 实例级状态和能力级状态必须分开，否则“可配置”“可执行”“已失效”会混在一起。
2. 凭证、token、secret、webhook 等敏感字段必须统一走后端加密、脱敏、旧值保留策略。
3. 编辑核心连接字段后，关联 capability 必须统一回退到待校验状态。
4. Loader 对 manifest 和 adapter 装配失败应尽早失败，避免页面和运行时带错启动。

---

## 2. 背景与业务目标

BK-Lite 的集成中心要解决的不是“集成任何系统并自由编排流程”，而是为平台业务提供一套可持续扩展的接入基础设施。

它负责：

- 统一管理外部系统类型
- 统一管理外部系统实例
- 统一向业务模块供给能力

它不负责：

- 做任意跨系统流程编排
- 让用户自由拼装自动化流程

当前设计的核心诉求有三类：

1. 用统一模型承接不同外部系统的接入差异。
2. 让页面渲染、连接配置、运行时执行基于同一份声明收口。
3. 在不打断现有登录与通知链路的前提下，完成登录流程切换，并让 IM 应用通知以独立能力接入。

---

## 3. 关键业务场景与需求

### 3.1 用户同步

业务需要把外部目录或平台中的组织、用户同步进 BK-Lite，并保留同步范围、根组织、字段映射等业务参数。

当前范围：

- AD、Ldap、企业微信、钉钉、飞书、WeLink、Teams

关键要求：

- 集成中心只提供连接基础和能力入口
- 同步范围、字段映射、根组织等业务参数放在业务绑定对象中
- 同步结果、执行记录不放在集成中心中

### 3.2 登录认证

业务需要支持多个认证源并存，让登录页能按顺序展示可用认证方式，同时保留现有统一登录入口。

当前范围：

- AD、Ldap、微信、企业微信、钉钉、飞书、WeLink、Teams

关键要求：

- 目标态下，登录页不再依赖用户手工选择域
- `/api/v1/core/api/login/` 继续作为统一 HTTP 登录入口
- 兼容期内 `domain` 仍可保留在接口层，但不再作为长期主模型
- `LoginAuthBinding` 承载账号匹配字段规则与未匹配用户处理策略
- 认证方式最终由 `LoginAuthBinding + IntegrationInstance + 登录认证 adapter 实现` 共同决定

### 3.3 按用户 IM 通知

业务需要面向单个用户发送 IM 通知，而不是简单复用现有群聊通知模型。

当前范围：

- 企业微信、钉钉、飞书、WeLink、Teams

关键要求：

- 单独承载通知渠道名称、IM 用户匹配方式、导入/同步/校验入口
- 保存平台用户与外部 IM 用户的映射结果
- 第一阶段先形成独立闭环，与现有通知方式并列存在，不直接接管旧的 `system_mgmt.Channel` 发送链路

### 3.4 版本范围

- 社区版：AD、Ldap、微信、企业微信、飞书
- 商业版：钉钉、WeLink、Teams

---

## 4. 总体设计结论

### 4.1 一句话架构

**Provider 决定渲染与声明，IntegrationInstance 提供连接基础，Capability Binding 承载业务参数，Adapter 以代码级插件方式承接执行与兼容，Registry / Loader 负责装配。**

### 4.2 分层模型

系统分为三层：

1. **静态定义层**
   - Provider Manifest
2. **持久化配置层**
   - IntegrationInstance
   - Capability Binding
   - Business Runtime Data
3. **运行时层**
   - Capability Contract
   - Provider Implementation
   - Shared Helper / Client
   - Registry
   - Loader

### 4.3 核心对象一览

| 对象 | 角色 | 负责 | 不负责 |
|---|---|---|---|
| Provider | 静态系统类型定义（非数据库模型） | capability 声明、模板结构、adapter 引用、展示信息 | 用户填写值、实例状态、业务绑定、运行结果 |
| IntegrationInstance | 真实接入实例 | 基础连接配置、实例级状态、能力级状态 | 同步规则、登录匹配、通知映射、运行结果 |
| Capability Binding | 业务侧落地对象 | capability 专属业务参数、启停、业务语义 | 重复保存基础连接配置 |
| Business Runtime Data | 业务运行结果 | 执行记录、映射结果、发送结果、同步摘要 | 集成中心静态配置 |

---

## 5. 核心模型设计

### 5.1 Provider

Provider 是系统内置的接入类型定义，用于描述某类外部系统的静态结构。

这里的 Provider 指 **代码内置的静态声明对象**，通常以 provider manifest 形式随代码发布，并由 Loader / Registry 在启动时装配；它**不是数据库持久化模型**。

Provider 负责：

- 标识系统类型，例如 `wechat`、`wecom`、`ad`
- 声明支持哪些 capability
- 定义实例页的基础配置模板
- 定义业务页的业务参数模板
- 定义默认展示信息，例如名称、图标、说明

Provider 不负责：

- 保存用户填写的连接值
- 保存实例状态或能力状态
- 承载业务 binding 或运行结果

Provider 的主能力声明应统一收口在 `capabilities` 结构中，不在模型层写死 capability 种类。

### 5.2 IntegrationInstance

IntegrationInstance 表示“某个 Provider 静态定义”在系统中的一个真实接入实例，是连接基础的唯一事实源。

它通过 `provider_key` 关联到对应的 Provider manifest，而不是关联某条 Provider 数据库记录。

它承载：

- 来源于 `instance_templates` 的基础连接配置
- 实例级状态
- 能力级基础可用性状态

它不承载：

- 用户同步字段映射
- 登录展示与匹配规则
- IM 用户映射结果
- 同步结果、发送结果、认证过程结果

### 5.3 Capability Binding

Capability Binding 表示“某个实例在某个 capability 中的落地使用对象”。

统一特征：

- 强引用某个 IntegrationInstance
- 记录所属 capability
- 保存该 capability 的业务参数
- 可以独立启停
- 不重复保存基础连接配置

其中：

- `IntegrationInstance` 上的能力级状态，用于表达“该实例在某个 capability 维度上的基础连接是否已完成校验并可被业务模块选用”
- `Capability Binding` 的启停，用于表达“业务是否启用这一具体落地配置”
- binding 的启停不反向影响实例侧的基础可用性状态

当前第一批内置类型：

| 对象 | 归属业务 | 作用 |
|---|---|---|
| UserSyncSource | 用户同步 | 描述实例在用户同步中的使用方式 |
| LoginAuthBinding | 登录认证 | 描述实例在登录认证中的使用方式 |
| IMNotificationChannel | 按用户 IM 通知 | 描述实例在通知中的使用方式 |

### 5.4 Business Runtime Data

运行结果不放在集成中心，而放在各业务模块内，例如：

- 用户同步执行记录（由新的用户同步运行记录表存储）
- IM 用户映射结果
- 最近同步摘要

静态配置和运行结果分离，是后续扩展和排障的基础边界。

### 5.5 对象关系

```text
Provider（静态 manifest / 非持久化对象）
  └─ 1:N IntegrationInstance

IntegrationInstance
  └─ 1:N CapabilityBinding（数据库对象）

CapabilityBinding
  ├─ type = login_auth      -> LoginAuthBinding
  ├─ type = user_sync       -> UserSyncSource
  └─ type = im_notification -> IMNotificationChannel

IMNotificationChannel
  └─ 1:N IMUserMapping
```

### 5.6 页面落点

| 页面 | 负责内容 |
|---|---|
| 集成中心 | 展示 provider 列表、创建实例、编辑基础连接、测试连接、启停实例和能力 |
| 用户同步页 | 从可用实例中选择用户同步能力，创建 UserSyncSource，补充同步参数 |
| 登录认证页 | 从可用实例中选择登录认证能力，创建 LoginAuthBinding，控制展示名称与顺序，并配置账号匹配字段规则与未匹配用户处理方式 |
| IM 通知页 | 从可用实例中选择 IM 通知能力，创建 IMNotificationChannel，配置用户映射并提供导入/同步入口 |

---

## 6. 运行时方案

### 6.1 运行时核心结论

Provider 不是完整 connector。这里的 Provider 指 provider manifest 对应的静态定义。完整 connector 由以下部分共同组成：

```text
Provider Manifest
  + IntegrationInstance
  + Capability Binding
  + Adapter（代码级插件）
  + Registry / Loader
```

结论：

- Provider Manifest 负责定义层
- Adapter + Registry / Loader 补齐执行层
- 页面渲染和运行时执行都依赖同一份 provider manifest

### 6.2 Manifest 最小结构

Provider 建议以 built-in manifest 形式随代码发布，统一放在：

- `server/apps/system_mgmt/providers/manifests/`

建议最小结构如下：

```json
{
  "provider_key": "provider_key",
  "label": "显示名称",
  "icon": "icon_key",
  "description": "描述信息",
  "capabilities": {
    "capability_key": {
      "enabled": true,
      "label": "能力名称",
      "business_template": "capability_form",
      "adapter_key": "provider_key.capability_key",
      "ui_meta": {},
      "runtime_meta": {}
    }
  },
  "instance_templates": {
    "base_connection": {
      "title": "基础连接",
      "groups": []
    }
  },
  "business_templates": {
    "capability_form": {
      "title": "业务参数",
      "groups": [],
      "available_external_fields": []
    }
  }
}
```

最小约束：

1. `business_template` 必须能在 `business_templates` 中找到。
2. `adapter_key` 必须能在 `CapabilityAdapterRegistry` 中找到。
3. `capabilities` 中的 key 不应在模型层写死。

### 6.3 模板结构

Provider 采用双模板结构：

```text
provider
  ├─ instance_templates
  └─ business_templates
```

含义：

- `instance_templates` 用于渲染实例侧基础配置
- `business_templates` 用于渲染业务侧参数配置
- `available_external_fields` 只提供可选字段名，不直接定义实际映射关系

### 6.4 Adapter 模型

平台核心不应只停留在一个过度泛化的 `BaseCapabilityAdapter`，而应采用“**capability 契约 + provider 薄实现**”的结构。

推荐分三层：

1. **Capability Contract**
   - 例如：`BaseLoginAuthAdapter`、`BaseUserSyncAdapter`、`BaseIMNotificationAdapter`
   - 用于定义某类 capability 的标准输入、标准输出和最小行为契约
2. **Provider Implementation**
   - 例如：`FeishuLoginAuthAdapter`、`FeishuUserSyncAdapter`、`FeishuIMNotificationAdapter`
   - 用于吸收具体 provider 的 API、协议、字段和认证差异
3. **Shared Helper / Client**
   - 用于沉淀稳定重复的 OAuth 流程、HTTP 调用、分页、签名、错误归一化等技术细节

Adapter 负责：

- 接收 provider manifest、integration instance、capability binding 和上下文
- 执行 capability 对应的外部系统交互
- 屏蔽第三方协议和响应差异
- 返回 capability 对应的标准结果对象

Adapter 不负责：

- 业务编排
- 最终持久化
- 权限决策
- 页面渲染逻辑
- 把多个 capability 混进同一个实现类

当前第一批 capability 契约：

- `BaseLoginAuthAdapter`
- `BaseUserSyncAdapter`
- `BaseIMNotificationAdapter`

当前扩展原则：

- 新增 capability，优先新增 capability contract，再补对应运行时装配
- 新增 provider，通常新增 provider-specific 薄 adapter，允许数量随 `Provider × Capability` 线性增长
- 只有当多个 provider 出现稳定重复流程后，才下沉 shared helper / base adapter
- 禁止为了减少类数量而引入“万能 Adapter”或跨 capability 合并实现
- 所有扩展都属于代码级插件

### 6.5 Registry 与 Loader

Registry 至少拆成两类：

1. `ProviderRegistry`
   - `provider_key -> provider manifest`
2. `CapabilityAdapterRegistry`
   - `adapter_key -> adapter class`

Registry / Loader 只负责装配和校验，不应成为业务模块直接依赖的运行时入口。

Loader 负责启动时装配，最小流程如下：

1. 扫描 provider manifest 目录
2. 读取 manifest
3. 校验 manifest 结构
4. 解析 capability 引用的 `adapter_key`
5. 加载对应 adapter class
6. 校验 `business_template` 是否存在
7. 校验 adapter class 可注册
8. 注册 provider 与 adapter

### 6.6 页面渲染与执行链路

```text
Provider Manifest
    ├─ instance_templates                -> 集成中心页面渲染
    ├─ business_templates                -> 业务参数模板集合
    ├─ capabilities.*.business_template  -> 业务页模板查找
    └─ capabilities.*.adapter_key        -> 运行时执行器查找

Runtime Application Service
    └─ 根据 manifest 与 binding 查找 adapter 并执行
```

这里的 `Runtime Application Service` 指平台内部统一执行入口，不等于 Registry / Loader，也不等于某个 provider adapter 本身。

它负责：

1. 接收业务模块传入的 binding、operation 和运行上下文
2. 校验实例级状态、能力级基础可用性状态以及 binding 是否允许执行
3. 根据 binding 关联的 `IntegrationInstance` 与 provider manifest 解析 `adapter_key`
4. 从 Registry 中获取对应 adapter，并组装标准执行上下文后发起调用
5. 把 adapter 返回结果收口为统一结果对象，再交还业务模块处理

它不负责：

1. provider-specific 第三方协议细节
2. 业务模块内部的持久化模型与页面交互
3. 把多种 capability 混成一个大而全的业务编排器

含义：

1. 页面渲染基于模板声明完成。
2. 业务页保存业务对象后，不直接与外部系统耦合。
3. 真正执行请求时，应由业务模块调用运行时应用服务，再由该服务根据 manifest 找到对应 adapter。
4. `adapter_key`、Registry、Loader 等装配细节不直接暴露给业务模块。

### 6.7 统一结果口径

所有 capability adapter 都应返回统一壳结构：

```json
{
  "success": true,
  "summary": "简要结果说明",
  "request_id": "platform_request_id",
  "partial_success": false,
  "retryable": false,
  "payload": {},
  "errors": []
}
```

原则：

- 业务模块只消费统一结果
- 第三方原始字段和响应格式由 adapter 内部吸收
- `payload` 允许按 capability 扩展，但必须遵守该 capability 的标准结果 schema，而不是自由 JSON
- 壳结构统一用于调度与错误处理，业务语义统一由 capability contract 约束
- `success` 表示本次 capability 调用是否整体成功；允许在批量/同步类场景下通过 `partial_success` 表达“调用完成但存在部分失败”
- `retryable` 用于明确调用方是否可以对同一操作直接重试，不能让业务模块自行猜测
- `request_id` 由平台生成，用于贯通运行日志、审计与排障链路

`errors` 至少应提供以下标准字段：

```json
[
  {
    "code": "provider.auth_failed",
    "message": "认证失败",
    "retryable": false,
    "field": "client_secret",
    "external_code": "401",
    "external_request_id": "third_party_request_id"
  }
]
```

约束：

1. `code` 必须是平台统一错误码，而不是直接透传第三方原始错误文案。
2. `message` 用于面向调用方展示可理解的错误摘要。
3. `retryable` 必须明确，便于业务模块决定是否允许重试或进入降级。
4. `field` 用于指向配置或参数层面的定位信息；无对应字段时可为空。
5. `external_code`、`external_request_id` 用于排障，可选但建议在有值时返回。

各 capability 的 `payload` 还应满足最小语义约束：

1. `login_auth`
   - 返回标准化外部身份结果，以及登录入口/回调处理所需的标准字段。
2. `user_sync`
   - 返回本次同步的处理统计，例如总量、成功数、失败数，以及继续增量同步所需的 cursor / checkpoint。
3. `im_notification`
   - 返回发送目标统计、发送结果摘要，以及第三方消息回执或请求标识（若外部系统可提供）。

---

## 7. 兼容与迁移策略

### 7.1 登录认证兼容口径

当前实现采用“去 domain 概念、保兼容字段、保 HTTP 入口”的迁移方式：

- 当前仓库仍保留 `/api/v1/core/api/login/` 作为统一 HTTP 登录入口
- 目标态下，新登录认证不再向用户暴露或依赖 `domain` 概念
- 前端已经收敛为默认使用 `domain.com`，后端继续兼容 `domain` 字段
- `domain` 当前阶段不直接删除，仅保留兼容入参语义，不再作为长期主模型
- 对外不改入口，只在入口内部逐步切换为：
  - `LoginAuthBinding` 决定登录方式
  - `LoginAuthBinding` 承载账号匹配字段规则与未匹配用户处理策略
  - `IntegrationInstance` 提供连接配置
  - 登录认证 adapter 实现承接实际认证

### 7.2 IM 应用通知兼容口径

当前阶段采用“新能力独立接入、旧链路继续服务”的方式：

- 现有 `system_mgmt.Channel` 继续服务历史通知链路
- `IMNotificationChannel` 不直接等同于现有 `Channel`
- 第一阶段先完成 IM 应用通知自身的配置、映射、发送闭环
- IM 应用通知与现有通知方式并列存在，不构成替代关系，用户可按场景自行选择
- IM 应用通知对业务侧通过服务接口提供能力，不直接暴露 `IMNotificationChannel` 等底层 binding 模型

---

## 8. 关键约束与注意事项

### 8.1 状态口径

当前实现中的状态分两层，但实际状态集合较设计稿更收敛：

1. **实例级状态**
   - `pending_verification` / `ready` / `verification_failed`
2. **能力级状态**
   - 当前以 capability 对应的 `capability_status` JSON 值表达，主要围绕 `pending_verification` / `ready` / `verification_failed` 的可用性语义使用

这里的“能力级状态”特指实例在某个 capability 维度上的**基础可用性状态**，用于判断该实例是否可以进入业务模块的可选池，不等同于业务侧 binding 的启停状态。

统一规则：

- 编辑核心连接字段后，关联 capability 回退到 `pending_verification`
- 只有 `instance_status = ready` 且 `capability_status = ready` 的能力，才能进入业务页可选池
- 业务侧是否实际生效，还需结合具体 binding 的启停状态判断；binding 停用不会改变实例侧 `capability_status`

### 8.2 敏感字段治理

Manifest 中的 `secret`、`write_only`、`mask_strategy`、`input_type` 用于声明字段特征。

统一规则：

1. 后端统一负责加密存储、脱敏回显、更新时旧值保留。
2. 前端只根据 manifest 决定输入与展示形态，不负责持久化策略。
3. Adapter 只消费运行时配置，不承担敏感字段持久化与回显治理。
4. 日志、审计、异常信息中不得输出敏感字段明文。

### 8.3 多实例与 binding 约束

1. 同一 provider 类型允许存在多个实例。
2. 是否允许同一实例在同一 capability 下存在多个 binding，由 capability 自身决定。
3. 当前阶段：
   - `user_sync`：一个实例可对应多个 `UserSyncSource`
   - `login_auth`：一个实例最多一个 `LoginAuthBinding`
   - `im_notification`：一个实例最多一个 `IMNotificationChannel`

### 8.4 删除与修改约束

1. 被业务绑定引用的实例不能删除。
2. 可以编辑实例基础连接配置。
3. 编辑核心连接字段后，相关能力必须重新校验。

### 8.5 Manifest 演进策略

当前阶段 provider manifest 先按单版本内置配置推进：

- 暂不增加 `manifest_version`
- 结构演进通过代码发布和 Loader 校验统一控制
- manifest 字段变更不视为独立配置变更，而视为代码发布级联动变更
- 一旦调整 manifest，必须同步检查集成中心实例页、业务模块参数渲染、Runtime Application Service 装配逻辑以及 adapter 入参契约是否仍然一致
- 同时必须评估已有 `IntegrationInstance` 与已有 binding 数据是否还能被当前 manifest 正确解释
- 若后续确实出现破坏性演进需求，再补充版本化与升级策略

当前阶段建议区分两类变更：

1. **低风险变更**
   - 新增非必填字段
   - 补充 `ui_meta`
   - 补充不影响既有保存语义的模板展示信息
2. **高风险变更**
   - 删除既有字段
   - 修改字段 key
   - 调整必填规则
   - 调整 capability 使用的模板结构

高风险变更不应被视为普通配置调整，而应视为联动改造；发布前至少要确认：

1. 集成中心页面仍可正确渲染、保存和回显
2. 业务模块仍能从实例与 `business_templates` 中拿到所需参数信息
3. Runtime Application Service 仍能完成 adapter 查找、上下文组装与结果收口
4. 现有实例与 binding 数据具备明确兼容策略；若不兼容，应在发布时一并完成迁移或限制升级

### 8.6 Loader 失败口径

以下情况建议直接视为启动失败：

1. `provider_key` 重复
2. `capability_key` 结构非法
3. `business_template` 缺失
4. `adapter_key` 缺失
5. `adapter_key` 找不到对应实现
6. adapter class 不可注册

这些问题都属于配置与代码装配错误，应在启动期暴露，而不是带错运行。

---

## 9. 落地分期

### 9.1 Phase 1 范围

当前实现最初以 **Feishu** 作为样板 provider 推进，但代码已经扩展到不止一个 provider：

- `login_auth`
- `user_sync`
- `im_notification`

样板目标不是分别做三套飞书能力，而是验证以下核心命题；在当前代码中，这些能力已经不再局限于 Feishu：

1. 同一个 Provider manifest 是否能同时承载三类 capability。
2. 同一个 `IntegrationInstance` 是否能复用基础连接配置，并被多个 capability binding 消费。
3. 不同 capability 是否能各自独立保存业务参数、运行结果和状态，而不污染集成中心核心模型。

### 9.2 Phase 1 内部实施顺序

建议按以下顺序推进：

1. **先完成样板 `IntegrationInstance` 基础能力**
   - 完成 provider manifest、实例基础配置页、实例保存、测试连接、实例状态流转。
2. **再完成 `login_auth`**
   - 先打通登录入口、回调处理、标准化身份结果返回，验证“统一入口 + adapter 执行”链路。
3. **再完成 `user_sync`**
   - 在已可用实例上创建 `UserSyncSource`，验证业务参数模板、同步入口，以及同步记录写入新的业务运行表。
4. **最后完成 `im_notification`**
   - 创建 `IMNotificationChannel`，验证用户映射、发送入口和通知闭环；运行期数据先只落用户映射表。

原因：

- `login_auth` 最容易验证端到端链路是否跑通。
- `user_sync` 更能验证“业务参数与运行结果不进入集成中心”的边界。
- `im_notification` 最适合验证同一实例被另一类 capability 复用时，binding 与运行数据是否还能保持独立。

### 9.3 Phase 1 验收标准

样板阶段的最小验收口径如下；当前代码已超出只验证 Feishu 的范围：

1. **样板实例层**
   - 能创建、编辑、测试连接、启停 `IntegrationInstance`。
   - 编辑核心连接字段后，三个 capability 状态都会回退到 `pending_verification`。
2. **`login_auth`**
   - 能创建 `LoginAuthBinding`。
   - 登录页能展示 binding 驱动的登录入口。
   - 能保存账号匹配字段规则与未匹配用户处理方式，并在登录时生效。
   - 登录请求最终通过对应的登录认证 adapter 实现完成认证并返回标准化身份结果。
3. **`user_sync`**
   - 能创建 `UserSyncSource`。
   - 能保存同步范围、根组织、字段映射等业务参数。
   - 能触发同步执行，并把执行结果、摘要和历史记录保存到新的用户同步运行记录表，而不是集成中心。
4. **`im_notification`**
   - 能创建 `IMNotificationChannel`。
   - 能配置 IM 用户匹配方式，并形成用户映射结果。
   - 能完成一次按用户发送通知的闭环。
5. **统一模型验证**
   - 三类 capability 都基于同一类 provider manifest 渲染与执行。
   - 三类 binding 都引用同一个 `IntegrationInstance`，但业务参数和运行结果彼此隔离。
   - 各 provider adapter 允许分别实现，但职责保持“薄适配”，不承载业务编排。
6. **真实环境联调边界**
   - 样板阶段的最终联调验收基于真实 provider 测试租户/应用完成。
   - 真实外部环境的申请、搭建与维护由使用方负责，不纳入本次研发实现任务。

---

## 10. 样板链路

样板链路不是“只验证飞书登录”，而是“验证同一个样板实例同时服务三类 capability”；当前代码中这一模式已经扩展到多个 provider：

```text
Provider Manifest(feishu)
    ↓
创建样板 IntegrationInstance
    ├─ 登录认证页创建 LoginAuthBinding
    │     ↓
    │   Runtime Application Service 根据 manifest 找到对应 Provider 的 LoginAuthAdapter
    │     ↓
    │   Adapter 生成登录入口并处理回调
    │     ↓
    │   返回标准化身份结果
    │
    ├─ 用户同步页创建 UserSyncSource
    │     ↓
    │   Runtime Application Service 根据 manifest 找到对应 Provider 的 UserSyncAdapter
    │     ↓
    │   Adapter 拉取外部用户/组织数据
    │     ↓
    │   业务模块写入新的用户同步运行记录表并保存同步结果与执行记录
    │
    └─ IM 通知页创建 IMNotificationChannel
          ↓
        Runtime Application Service 根据 manifest 找到对应 Provider 的 IMNotificationAdapter
          ↓
        Adapter 完成用户映射查询与消息发送
          ↓
        IM 应用通知服务保存映射结果与发送结果
```

该样板主要用于验证：

1. `instance_templates` 是否足以承载样板 provider 的共用连接配置。
2. `business_template` 是否足以分别承载登录、同步、通知三类业务参数。
3. 同一个 `IntegrationInstance` 是否能被多个 capability binding 安全复用。
4. `ui_meta` / `runtime_meta` 是否足以表达同一 provider 在不同 capability 下的差异。
5. 页面渲染和运行时查找是否真正由同一份 manifest 驱动。
6. Adapter、binding、业务模块之间的职责边界是否清晰。

---

## 11. 已收敛结论

1. **社区版 / 商业版 provider 装配边界**
   - 当前阶段只通过代码装配控制社区版 / 商业版 provider 的边界。
   - 社区版不装配商业版 provider 的 manifest / adapter。
   - 当前不额外引入产品层显式开关、edition flag 或 license 开关。
2. **`available_external_fields` 策略**
   - 当前阶段 `available_external_fields` 不强制预置，可留空。
   - 由用户自行填写字段映射，暂不引入统一字段字典层或默认填充机制。
   - 后续若出现明确需求，再补默认字段建议或标准字段映射层。
3. **登录认证的平台用户匹配策略**
   - 平台用户最终匹配策略由 `LoginAuthBinding` 承载。
   - `LoginAuthBinding` 负责保存账号匹配字段规则与未匹配用户处理方式。
   - 登录认证 adapter 实现只负责输出标准化外部身份，不承担平台用户匹配决策。
4. **IM 应用通知的对外暴露边界**
   - IM 应用通知是独立于现有通知方式的新通知类型，不替代旧链路。
   - 对业务侧以服务接口形式提供能力。
   - 不直接暴露 `IMNotificationChannel`、`adapter_key` 或 Registry 等底层实现细节。
