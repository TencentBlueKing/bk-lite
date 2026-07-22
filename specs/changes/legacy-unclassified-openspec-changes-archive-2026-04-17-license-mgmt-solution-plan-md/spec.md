# 系统管理-许可管理 Solution Plan

Status: cancelled

## Migration Context

非标准旧 artifact，原路径为 `openspec/changes/archive/2026-04-17-license-mgmt/solution_plan.md`。完整内容保留如下。

版本：v2.0

日期：2026-04-08

需求文档：[20260407.许可管理.md](../../requirements/系统管理/20260407.许可管理.md)

---

## 1. 方案概览

本方案面向系统管理新增“许可管理”能力，目标是在现有系统管理设置体系中增加“许可”页签，并由企业版独立后端应用 `license_mgmt` 与前端企业版目录 `system-manager/enterprise` 共同承接许可主数据、提醒配置、模块授权摘要、节点额度提醒与日志容量提醒等业务能力。

该方案的核心设计原则不是把许可管理继续内聚进 `system_mgmt`，而是将其拆分为与 `system_mgmt` 平级的独立领域应用，以避免企业版独有模型和迁移文件污染社区版 `system_mgmt` 主干。

总体方案：

- 前端入口仍然保留在 `系统管理 > 设置 > 许可`，保证用户信息架构不变，但真实页面实现放在企业版前端目录中。
- 后端将许可管理设计为企业版独立 app：`license_mgmt`，与 `system_mgmt` 平级。
- 企业版接口统一走 `server_url/api/v1/license_mgmt/...`，接口风格与现有 `system_mgmt` 保持一致。
- `license_mgmt` 复用 `system_mgmt` 的菜单、权限、通知渠道、用户检索与消息发送能力，但 `system_mgmt` 不反向依赖 `license_mgmt`。
- 许可管理主体数据、全局默认提醒、单许可提醒覆盖、模块提醒、专用节点提醒覆盖均落在 `license_mgmt` 自有模型中。
- 许可覆盖模块、通知渠道、多选通知人员等配置型字段第一版统一使用 `JSONField` 存储，降低模型复杂度和迁移成本。

---

## 2. 范围定义

### 2.1 In Scope

- 系统管理“设置”下新增“许可”页签与页面。
- 许可列表、许可新增、许可停用、历史许可查看。
- 默认提醒策略、单许可提醒策略。
- 平台模块授权状态展示与数量汇总。
- 对象节点额度明细查看、节点提醒阈值配置。
- 日志中心容量信息展示、容量提醒配置。
- 复用系统管理通知渠道作为提醒通道来源。
- 许可管理页内的通知人员选择与多选维护。
- 基于菜单权限控制许可管理页可见性与操作权限。
- 企业版独立 app `license_mgmt` 的模型、接口、迁移与服务层建设。
- 企业版前端 `system-manager/enterprise` 下的许可页面、API、类型与组件建设。

### 2.2 Out of Scope

- 外部许可申请平台、许可购买与审批流。
- 自动续期、自动扩容、自动商业化闭环。
- 多租户差异化许可模型、组织级独立许可池。
- 复杂发布编排、灰度授权、历史版本回滚。
- 跨产品统一容量中心与全平台资源配额治理。
- 门户配置能力纳入当前方案范围。
- 将企业版 `license_mgmt` 反向接入社区版仓库主干。

---

## 3. 已确认决策

- **命名口径**：页面标题使用“许可管理”，设置页签与页面内操作展示使用“许可”。
- **刷新策略**：新增、修改、删除许可后，需要刷新许可列表；模块授权状态和生效许可数不要求单次操作后实时联动，可按页面刷新结果更新。
- **停用影响**：停用许可后仅限制继续新增节点或新增授权资源，不影响已存在节点使用。
- **历史许可口径**：仅包含手动停用和已到期许可，不包含“失效但未停用”的额外状态。
- **提醒配置口径**：许可提醒、节点提醒、日志容量提醒统一采用“通知渠道 + 通知人员 + 提醒时间/阈值”的配置结构。
- **提醒通道来源**：许可提醒、节点提醒、日志容量提醒统一复用系统管理通知渠道能力，支持全局默认和单项覆盖，且支持多选。
- **阈值单位**：节点提醒阈值按“个”，日志容量提醒阈值按 `GB`。
- **设置口径**：系统管理“设置”从旧版仅“密钥”扩展为至少包含“密钥”“许可”。
- **权限口径**：许可管理页基于菜单权限控制，首期仅内置超管角色可查看和操作，普通用户不可见。
- **后端边界**：`license_mgmt` 为企业版独立 app，与 `system_mgmt` 平级，社区版不包含该 app。
- **前端边界**：许可管理前端真实实现位于 `web/src/app/system-manager/enterprise/...`，社区版不提交许可页面业务代码。
- **接口前缀**：许可管理接口统一使用 `server_url/api/v1/license_mgmt/...`。
- **菜单注册方式**：菜单与权限资源仍注册到 `system_mgmt` 菜单体系中，但相关命令行或初始化逻辑必须先判断 `apps` 下是否存在 `license_mgmt`。
- **通知人员存储口径**：通知人员统一存用户 ID。
- **许可模块存储口径**：许可覆盖模块第一版使用 `JSONField` 保存模块 code 列表。
- **全局默认提醒存储口径**：全局默认提醒配置放在 `license_mgmt` 独立表中，不复用 `system_mgmt.SystemSettings`。
- **系统注册码存储口径**：系统注册码不落库，运行时统一从 `server/apps/license_mgmt/registration_code.py` 读取。
- **许可公钥配置口径**：验签公钥统一放在 settings 中，采用 `LICENSE_PUBLIC_KEYS={kv: base64_public_key}` 的字典结构，并通过 `LICENSE_DEFAULT_PUBLIC_KEY_VERSION` 处理未携带 `kv` 的许可。
- **停用拦截范围**：停用许可后的新增资源限制需要覆盖 `node_mgmt`、`cmdb`、`monitor`、`log` 四类入口。
- **通知人员查询范围**：通知人员范围限定为当前用户拥有权限的组下的全部人员。
- **通知渠道查询范围**：通知渠道范围限定为当前用户拥有权限组下可见的渠道。
- **发布策略**：企业版直接上线，不增加灰度菜单开关。

---

## 4. 架构设计

### 4.1 领域边界

本期采用“前端仍属于系统管理信息架构，但企业版前端实现独立；后端独立领域拆分”的方式：

- 前端：许可页路由归属 `system-manager/settings/license`，但真实实现位于 `system-manager/enterprise`
- 后端：许可业务域归属 `license_mgmt`

依赖方向固定为：

```text
license_mgmt -> system_mgmt
license_mgmt -> core
license_mgmt -> rpc（如需要）
```

禁止出现：

```text
system_mgmt -> license_mgmt
```

即：

- `license_mgmt` 可以复用 `system_mgmt` 的菜单、权限、渠道、用户和消息发送能力
- `system_mgmt` 不应 import `license_mgmt` 的模型、服务或路由

### 4.2 企业版代码组织

后端建议目录：

```text
server/apps/license_mgmt/
  __init__.py
  apps.py
  urls.py
  migrations/
  models/
  serializers/
  viewset/
  services/
  constants/
```

前端建议采用企业版独立目录：

```text
web/src/app/system-manager/enterprise/
  api/license_mgmt/
  types/license.ts
  (pages)/settings/license/page.tsx
  components/settings/license/*
```

社区版前端仅保留系统管理公共设置壳与企业版扩展加载点，不承载许可管理页面业务实现。

### 4.3 Django 注册策略

- 企业版在 `INSTALLED_APPS` 中注册 `apps.license_mgmt`
- 社区版不注册 `apps.license_mgmt`
- `license_mgmt` 使用自己独立的 `AppConfig`
- `license_mgmt` 拥有自己独立的 migration 链

### 4.4 路由策略

- 许可管理接口不挂入 `system_mgmt/urls.py`
- `license_mgmt` 自己维护独立 router 和 `urls.py`
- 企业版总路由统一 include 到 `api/v1/license_mgmt/`

建议接口按能力分组：

- `/api/v1/license_mgmt/license/`
- `/api/v1/license_mgmt/license-reminder/`
- `/api/v1/license_mgmt/module-summary/`
- `/api/v1/license_mgmt/node-reminder/`
- `/api/v1/license_mgmt/log-memory-reminder/`

### 4.5 注册码策略

- 系统注册码不落库。
- 系统注册码统一定义在 `server/apps/license_mgmt/registration_code.py`。
- 许可添加页通过服务端接口读取注册码展示值，不直接暴露实现细节。
- `.lic` 文件内容的外层解密使用该注册码作为解密参数。

---

## 5. 数据模型设计

### 5.1 设计原则

- 许可管理主体数据不落入 `system_mgmt.SystemSettings`
- 企业版独有模型全部定义在 `license_mgmt`
- 配置类多选字段优先使用 `JSONField`
- 历史许可不单独建表，优先通过状态字段区分

### 5.2 核心模型建议

#### 1. `LicenseRecord`

表示一张许可记录。

建议字段：

- `license_no`
- `license_key`
- `registration_code_snapshot`
- `valid_from`
- `valid_until`
- `status`：`active / disabled / expired`
- `disabled_reason`
- `disabled_at`
- `module_codes`：`JSONField`
- `created_by`
- `updated_by`
- `created_at`
- `updated_at`

用途：

- 当前生效许可列表
- 历史许可列表
- 模块授权基础来源

说明：

- `registration_code_snapshot` 仅作为许可导入时的快照或审计辅助字段，真实注册码来源仍以 `registration_code.py` 为准。

#### 2. `LicenseGlobalReminderConfig`

表示许可管理全局默认提醒配置。

建议字段：

- `default_channel_ids`：`JSONField`
- `default_user_ids`：`JSONField`
- `default_remind_days`
- `updated_by`
- `updated_at`

用途：

- 默认提醒面板配置来源
- 单许可跟随默认摘要来源
- 节点提醒默认摘要来源
- 日志容量提醒跟随默认摘要来源

#### 3. `LicenseReminderOverride`

表示单许可提醒覆盖配置。

建议字段：

- `license`：FK -> `LicenseRecord`
- `mode`：`follow / custom`
- `channel_ids`：`JSONField`
- `user_ids`：`JSONField`
- `remind_days`
- `updated_by`
- `updated_at`

#### 4. `ModuleReminderConfig`

表示模块级提醒配置。

建议字段：

- `module_code`
- `reminder_type`：`node / log_memory`
- `mode`：`follow / custom`
- `threshold_value`
- `channel_ids`：`JSONField`
- `user_ids`：`JSONField`
- `updated_by`
- `updated_at`

用途：

- 节点提醒的模块级默认阈值
- 日志容量提醒的模式与独立配置

#### 5. `NodeReminderOverride`

表示专用节点类型级提醒覆盖配置。

建议字段：

- `module_code`
- `object_type`
- `threshold_value`
- `channel_ids`：`JSONField`
- `user_ids`：`JSONField`
- `updated_by`
- `updated_at`

唯一约束建议：

- `unique(module_code, object_type)`

对应原型约束：

- 同一模块下同一专用节点类型不可重复配置

---

## 6. 分阶段计划

### Phase 1：应用骨架与菜单权限接入

**里程碑目标**

- 建立企业版独立 app `license_mgmt`
- 打通系统管理中的前端入口与菜单权限基线

**交付内容**

1. 新建企业版独立 app：
   - 新增 `server/apps/license_mgmt/`
   - 新增 `apps.py`、`urls.py`、`models/`、`serializers/`、`viewset/`、`services/`、`migrations/`

2. 企业版应用注册：
   - 企业版 `INSTALLED_APPS` 注册 `apps.license_mgmt`
   - 社区版不注册该 app

3. 菜单接入：
    - 前端系统管理设置菜单增加“许可”页签
    - 菜单资源和权限资源仍接入 `system_mgmt` 体系
    - 初始化命令或数据加载逻辑中增加前置判断：仅当 `apps` 下存在 `license_mgmt` 时才注册许可菜单及权限资源
    - 社区版前端仅保留系统管理公共壳与企业版扩展加载点，企业版在 `system-manager/enterprise` 下提供许可页面实现

4. 权限基线：
   - 页面仅内置超管可见
   - 页面按钮权限与后端接口权限保持一致

5. 注册码接入：
   - 约定 `registration_code.py` 为统一注册码来源
   - 页面读取时通过服务端接口返回注册码展示值

**涉及文件（预期）**

- 后端：
  - `server/apps/license_mgmt/apps.py`
  - `server/apps/license_mgmt/urls.py`
  - 企业版 `INSTALLED_APPS` 配置文件
  - `server/apps/system_mgmt/models/menu.py`
  - 菜单/权限初始化相关命令或脚本
- 前端：
  - `web/src/app/system-manager/constants/menu.json`
  - `web/src/app/system-manager/(pages)/settings/page.tsx`
  - `web/src/app/system-manager/enterprise/(pages)/settings/license/page.tsx`
  - `web/src/app/system-manager/enterprise/api/license_mgmt/index.ts`
  - `web/src/app/system-manager/enterprise/types/license.ts`
  - `web/src/app/system-manager/enterprise/components/settings/license/*`

**阶段验收**

- 企业版可识别 `license_mgmt` app
- 系统管理“设置”中出现“许可”页签
- 普通用户不可见，超管可访问
- 注册码可通过接口读取展示

### Phase 2：许可主数据与基础接口建设

**里程碑目标**

- 建立 `license_mgmt` 核心数据模型与基础查询/写入接口
- 打通许可列表、历史许可、模块授权摘要主链路

**交付内容**

1. 核心模型建设：
   - `LicenseRecord`
   - `LicenseGlobalReminderConfig`
   - `LicenseReminderOverride`
   - `ModuleReminderConfig`
   - `NodeReminderOverride`

2. 主接口建设：
   - 生效许可列表查询
   - 历史许可列表查询
   - 添加许可
   - 停用许可
   - 模块授权摘要查询
   - 注册码读取接口

3. 接口前缀：
   - 所有接口统一暴露到 `api/v1/license_mgmt/...`

4. 刷新策略：
   - 新增、停用、修改后前端主动刷新许可列表
   - 模块授权状态和汇总优先由服务端聚合返回

5. 停用影响对接：
   - 在许可状态变更后，为 `node_mgmt`、`cmdb`、`monitor`、`log` 的新增资源校验提供统一判定来源

**涉及文件（预期）**

- `server/apps/license_mgmt/models/license.py`
- `server/apps/license_mgmt/models/reminder.py`
- `server/apps/license_mgmt/models/__init__.py`
- `server/apps/license_mgmt/serializers/license_serializer.py`
- `server/apps/license_mgmt/serializers/reminder_serializer.py`
- `server/apps/license_mgmt/viewset/license_viewset.py`
- `server/apps/license_mgmt/urls.py`
- `server/apps/license_mgmt/migrations/*.py`

**阶段验收**

- 可返回生效许可列表与历史许可列表
- 可新增许可与停用许可
- 可返回模块授权摘要与数量汇总
- 可返回注册码展示内容

### Phase 3：提醒配置模型与通知能力接入

**里程碑目标**

- 打通默认提醒、单许可提醒、节点提醒、日志容量提醒的数据结构和读写接口
- 形成统一的“通知渠道 + 通知人员 + 提醒时间/阈值”配置口径

**交付内容**

1. 默认提醒配置：
   - 基于 `LicenseGlobalReminderConfig` 管理默认通知渠道、多选通知人员和默认提醒时间

2. 单许可提醒：
   - 基于 `LicenseReminderOverride` 管理 `follow / custom`
   - 支持默认摘要回显

3. 节点提醒：
   - `ModuleReminderConfig(reminder_type=node)` 保存模块级默认阈值
   - `NodeReminderOverride` 保存专用节点类型覆盖项
   - 默认通知渠道和默认通知人员继承全局默认提醒配置

4. 日志容量提醒：
   - `ModuleReminderConfig(reminder_type=log_memory)` 保存日志容量提醒模式和阈值
   - 支持 `follow / custom`

5. 通知能力复用：
    - 通知渠道继续复用 `system_mgmt.Channel` 相关能力
    - 通知渠道范围限定为当前用户拥有权限组下可见的渠道
    - 通知人员继续复用系统内用户检索能力
    - 通知人员范围限定为当前用户拥有权限的组下全部人员
    - 消息发送继续复用已有 `send_msg_with_channel`

6. 参数校验：
   - 提醒天数为正整数
   - 节点阈值需在可用额度边界内
   - 日志容量阈值需小于总容量
   - 自定义配置至少应选择一个通知渠道

**涉及文件（预期）**

- `server/apps/license_mgmt/models/reminder.py`
- `server/apps/license_mgmt/serializers/reminder_serializer.py`
- `server/apps/license_mgmt/viewset/reminder_viewset.py`
- `server/apps/license_mgmt/services/reminder_service.py`

**阶段验收**

- 默认提醒、单许可提醒、节点提醒、日志容量提醒配置可保存并回显
- 通知人员按用户 ID 存储并可正确回显
- 日志容量提醒支持 `跟随默认 / 单独配置` 切换

### Phase 4：许可管理页完整前端交付

**里程碑目标**

- 完成与原型一致的许可管理前端页面和交互闭环

**交付内容**

1. 页面结构：
   - 顶部说明区
   - 许可列表区
   - 默认提醒配置区
   - 历史许可抽屉
   - 平台模块授权区
   - 对象节点额度明细抽屉
   - 节点提醒弹窗
   - 日志容量提醒弹窗

2. 页面交互：
   - 添加许可、停用许可、刷新许可列表
   - 默认提醒展开/收起
   - 默认提醒中的通知渠道卡片多选、通知人员多选、提醒时间编辑
   - 单许可中的 `跟随默认 / 单独配置`
   - 节点提醒默认摘要展示与专用节点单独配置
   - 日志容量提醒的 `跟随默认 / 单独配置` 切换

3. API 接入：
   - 企业版前端统一请求 `api/v1/license_mgmt/...`
   - 社区版前端不承载许可管理业务 API 封装
   - 系统管理页面层不直接依赖 `system_mgmt/system_settings` 提供许可数据

**涉及文件（预期）**

 - `web/src/app/system-manager/enterprise/(pages)/settings/license/page.tsx`
 - `web/src/app/system-manager/enterprise/api/license_mgmt/index.ts`
 - 如页面复杂度较高，可拆分：
   - `web/src/app/system-manager/enterprise/components/settings/license/*`
   - `web/src/app/system-manager/enterprise/types/license.ts`
   - 企业版独立 locale 扩展或复用现有 enterprise 扩展机制

**阶段验收**

- 页面结构覆盖 requirements 所列区域
- 页面关键交互均可完成
- 新增、停用、修改后许可列表刷新行为符合口径

### Phase 5：联调、测试与发布准备

**里程碑目标**

- 完成企业版独立 app 与系统管理基础能力的联调
- 完成测试门禁与回滚准备

**交付内容**

1. 后端验证：
   - 许可 CRUD 与状态流转测试
   - 历史许可归档测试
   - 通知人员与通知渠道组合配置测试
   - JSONField 存储与读取测试
   - 权限校验测试

2. 前端验证：
   - 菜单可见性验证
   - 列表刷新验证
   - 多渠道、多通知人员回显验证
   - 日志容量提醒模式切换验证

3. 最小门禁：
   - `cd server && make test`
   - `cd web && pnpm lint && pnpm type-check`

4. 发布准备：
   - 企业版 app 注册校验
   - 菜单初始化命令存在 `license_mgmt` 检查
   - 迁移顺序校验
   - 超管可见性与普通用户不可见验证
   - 企业版直接上线发布校验

---

## 7. 验收清单

### A1. 应用与迁移隔离验收

- [ ] `license_mgmt` 为独立 app，与 `system_mgmt` 平级
- [ ] 社区版不包含 `license_mgmt` app 注册
- [ ] `license_mgmt` 拥有独立 migration 链，不污染 `system_mgmt/migrations`

### A2. 入口与权限验收

- [ ] 系统管理“设置”下新增“许可”页签
- [ ] 菜单资源仍接入 `system_mgmt` 体系
- [ ] 仅内置超管角色可见并可操作
- [ ] 普通用户不可见且无法访问许可管理页面

### A3. 许可主链路验收

- [ ] 可查看生效许可列表与生效许可数量
- [ ] 可展示并复制系统注册码
- [ ] 可新增许可并在操作后刷新许可列表
- [ ] 可停用许可并进入历史许可视图
- [ ] 历史许可仅包含手动停用和已到期许可
- [ ] 许可覆盖模块以 `JSONField` 方式存储并可正确回显

### A4. 提醒配置验收

- [ ] 默认提醒支持配置多选通知渠道、多选通知人员和提醒时间
- [ ] 单许可提醒支持跟随默认与单独配置切换，且单独配置中可维护通知渠道、通知人员和提醒时间
- [ ] 节点提醒支持默认摘要展示与专用节点类型覆盖，覆盖项中可维护通知渠道、通知人员和阈值
- [ ] 日志容量提醒支持跟随默认与单独配置切换，单独配置中可维护通知渠道、通知人员和阈值
- [ ] 通知人员以用户 ID 存储并可正确保存、读取和回显

### A5. 工程质量验收

- [ ] `cd server && make test` 通过
- [ ] `cd web && pnpm lint && pnpm type-check` 通过
- [ ] 核心操作存在失败反馈和取消回退表现
- [ ] 停用许可后，`node_mgmt`、`cmdb`、`monitor`、`log` 的新增资源入口可受到统一限制

---

## 8. 风险与应对

### 风险 1：前端入口在系统管理，后端实现独立为 `license_mgmt`，若边界不清晰容易出现错误依赖

- 影响：前端和后端边界混乱，后续又把许可逻辑反向塞回 `system_mgmt`。
- 应对：明确规定前端信息架构归 `system-manager`，但企业版许可实现必须位于 `system-manager/enterprise`；后端业务域归 `license_mgmt`，并保持依赖单向。

### 风险 2：菜单和权限资源仍归 `system_mgmt`，若初始化逻辑不判断 `license_mgmt` 是否存在，社区版可能报错

- 影响：社区版命令行初始化、菜单注册或权限同步失败。
- 应对：所有菜单、权限初始化逻辑增加 `license_mgmt` 存在性判断。

### 风险 3：通知渠道与通知人员的查询、展示、发送口径可能不一致

- 影响：页面展示正常，但实际发送对象或可选范围与页面预期不一致。
- 应对：沿用现有渠道能力，并补齐通知人员与通知渠道组合配置的端到端验证；通知渠道与通知人员范围统一按“当前用户拥有权限组下可见范围”实现。

### 风险 4：停用许可后的影响面若只在许可页生效，未同步到新增资源入口，规则可能失效

- 影响：用户仍可从其他模块继续新增节点或新增授权资源。
- 应对：实施阶段梳理并接入 `node_mgmt`、`cmdb`、`monitor`、`log` 的新增资源入口，补统一许可有效性校验。

### 风险 5：JSONField 第一版简化了设计，但后续如果查询维度增加，可能需要结构升级

- 影响：复杂筛选、统计和审计查询能力受限。
- 应对：第一版接受配置快照模型，后续如出现复杂查询再拆子表，不提前过度设计。

### 风险 6：注册码配置错误或部署未覆盖 `registration_code.py`，可能导致 `.lic` 解密失败

- 影响：许可添加页可展示错误注册码，或许可证文件无法成功解密导入。
- 应对：在部署阶段明确 `registration_code.py` 的覆盖方式，并增加发布前校验。

---

## 9. 回滚与降级策略

### 9.1 回滚原则

- 仅回滚企业版 `license_mgmt` 相关能力，不影响社区版和现有 `system_mgmt` 主链路。
- 若提醒发送链路不稳定，可先降级为“仅保存提醒配置，不实际发送提醒”。
- 若额度明细能力复杂度超预期，可先保留许可列表与基础提醒能力，将额度明细相关入口临时隐藏。

### 9.2 回滚方式

1. 前端回滚：移除企业版 `system-manager/enterprise` 下的许可页面实现与菜单入口接入。
2. 后端回滚：下线 `api/v1/license_mgmt/...` 路由。
3. 数据回滚：按 `license_mgmt` 自有 migration 链回退，不影响 `system_mgmt`。
4. 通知降级：保留配置数据，临时关闭实际发送调用。

---

## 10. 完整性检查

- 范围边界：已明确前端入口属于系统管理，后端业务域属于 `license_mgmt`。
- 前端隔离：已明确企业版前端实现位于 `system-manager/enterprise`，社区版不承载许可页面业务代码。
- 迁移隔离：已明确社区版不注册 `license_mgmt`，迁移不进入 `system_mgmt`。
- 数据模型：已明确全局提醒、单许可提醒、模块提醒、节点提醒分别建模。
- 技术口径：已明确接口前缀、菜单接入方式、用户 ID 存储方式、注册码文件来源和 JSONField 策略。
- 风险与回滚：已覆盖迁移污染、初始化判断、提醒口径、注册码配置和停用生效面问题。

---

## 11. 待确认项（TODO）

- TODO: `registration_code.py` 在部署环境中的覆盖方式、变更流程与发布校验需技术实现阶段确认。确认位置：部署配置、运维发布方案评审。
