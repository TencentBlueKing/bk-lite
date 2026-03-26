# CMDB 数据订阅技术解决方案

日期：2026-03-16

## 方案概览

本方案基于 PRD 与 Requirement，面向 CMDB 新增"数据订阅"能力，目标是在保持轻量架构的前提下，让用户能够按模型与规则订阅实例数据变化并接收通知。

总体策略：
- 使用 Celery Beat 定时任务，每 2 分钟周期检查一次订阅规则，不依赖 Django Signal。
- 检测流程：定时查询 SubscriptionRule → 根据条件查询实例并存储快照 → 对比 ChangeRecord 变更记录与 FalkorDB 当前数据 → 触发通知。
- 复用 system_mgmt 模块已有 Channel 通知渠道，不新增渠道类型。
- 1 分钟窗口聚合使用 Redis 实现防打扰，避免通知风暴。

## 范围与约束

### In Scope

- 订阅规则模型与 CRUD API。
- 三类触发类型：属性变化、关联变化（一跳）、临近到期（按自然日）。
- 四个快速订阅入口：实例列表多选、实例列表筛选、实例详情、管理侧边弹框。
- 1 分钟聚合窗口防打扰策略。
- 复用系统管理已有通知渠道发送消息。
- 所属组织维度的权限控制（仅所属组织可管理）。
- 规则仅对创建后触发生效，不追补历史变更通知。

### Out of Scope

- 跨组织/跨租户订阅。
- 多跳关联链路订阅（仅支持一跳关联）。
- 新增通知渠道类型（仅复用系统管理已有渠道）。
- 复杂流程能力（审批流、版本管理、订阅模板市场）。

## 已确认决策

- **触发机制**：采用 Celery Beat 定时任务（2 分钟周期）轮询检查，不依赖 Django Signal，便于调试与灵活控制检查频率。
- **快照存储**：每次检查时存储当前实例快照，用于下次对比（动态分组场景）。关联变化需额外存储关联实例快照。
- **数据对比**：通过 ChangeRecord 的 `before_data` / `after_data` + FalkorDB 当前数据进行变更检测。
- **聚合策略**：使用 Redis Set + TTL 实现 1 分钟窗口聚合，简单可靠，无需额外消息队列。
- **触发类型多选**：单条规则可同时配置多种触发类型，`trigger_config` 按类型分别存储配置。
- **实例筛选存储**：支持两种模式，通过 `filter_type` 区分：
  - `condition`（过滤条件）：复用现有 `query_list` 结构，最多 8 条件 AND 逻辑，动态查询实例
  - `instances`（实例选择）：直接存储用户选择的实例 ID 列表
- **接收对象存储**：直接存储用户名/用户组 ID 列表，发送时按渠道类型解析。
- **权限控制**：支持子组织可见，当前组织可管理。规则所属组织与当前用户组织精确匹配时才可管理，子组织规则仅可查看。

## 分阶段计划

### 阶段一：数据模型与核心接口

**里程碑目标**
- 建立订阅规则持久化模型。
- 完成规则 CRUD 接口与组织权限控制。

**交付内容**

1. 新增 `SubscriptionRule` 模型（`server/apps/cmdb/models/subscription_rule.py`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | CharField | 规则名称（必填） |
| `organization` | BigIntegerField | 所属组织 ID（必填） |
| `model_id` | CharField | 目标模型 ID |
| `filter_type` | CharField | 筛选类型：`condition`（过滤条件）/ `instances`（实例选择） |
| `instance_filter` | JSONField | 实例筛选数据（根据 filter_type 存储不同内容） |
| `trigger_types` | JSONField | 触发类型列表（多选）：`attribute_change` / `relation_change` / `expiration` |
| `trigger_config` | JSONField | 触发条件配置（按类型存储：监听字段/关联模型+字段/提前天数） |
| `recipients` | JSONField | 接收对象列表（用户名/用户组 ID） |
| `channel_id` | BigIntegerField | 通知渠道 ID |
| `is_enabled` | BooleanField | 启用状态（默认 True） |
| `last_triggered_at` | DateTimeField | 最近触发时间（可空） |
| `last_check_time` | DateTimeField | 上次检查时间（用于查询增量 ChangeRecord） |
| `snapshot_data` | JSONField | 实例快照数据（存储上次检查的实例列表与关联信息） |
| `created_by` | CharField | 创建人 |
| `created_at` | DateTimeField | 创建时间 |
| `updated_by` | CharField | 更新人 |
| `updated_at` | DateTimeField | 更新时间 |

**`snapshot_data` 数据结构示例**：
```json
{
  "instances": [1, 2, 3],
  "relations": {
    "1": {"disk": [33, 44], "network": [55]},
    "2": {"disk": [33]},
    "3": {}
  }
}
```

**`instance_filter` 数据结构说明**：

当 `filter_type = "condition"`（过滤条件模式）：
```json
{
  "query_list": [
    {"field": "status", "type": "str=", "value": "running"},
    {"field": "organization", "type": "list[]", "value": [1, 2]}
  ]
}
```
- 复用现有 `query_list` 结构，最多 8 条件，多条件之间为 AND 逻辑
- 每次检查时根据条件动态查询实例

当 `filter_type = "instances"`（实例选择模式）：
```json
{
  "instance_ids": [1, 2, 3, 4, 5]
}
```
- 直接存储用户选择的实例 ID 列表
- 检查时直接使用这些 ID 查询实例

2. 新增 `SubscriptionViewSet`（`server/apps/cmdb/views/subscription.py`），继承 `ModelViewSet`：
   - `POST /api/cmdb/subscription/` — 创建规则
   - `GET /api/cmdb/subscription/` — 查询规则列表（按组织权限过滤）
   - `GET /api/cmdb/subscription/{id}/` — 查询规则详情
   - `PUT /api/cmdb/subscription/{id}/` — 更新规则
   - `PATCH /api/cmdb/subscription/{id}/` — 部分更新规则
   - `DELETE /api/cmdb/subscription/{id}/` — 删除规则
   - `POST /api/cmdb/subscription/{id}/toggle/` — 启停规则（自定义 action）

3. 权限控制逻辑（包含子组织）：
   - 列表查询：返回当前用户组织及其子组织可见的规则（`organization IN current_team_with_children`）。
   - 管理操作：仅当 `rule.organization == request.user.current_team`（精确匹配当前组织）时允许编辑/启停/删除。
   - 子组织规则：当前用户可查看子组织创建的规则，但不可管理（编辑/启停/删除按钮置灰）。
   - 权限判断方法：复用 `system_mgmt` 的 `get_group_with_children()` 获取组织树。

**阶段验收**
- 可通过 API 创建/查询/编辑/删除订阅规则。
- 规则列表展示当前组织及子组织的规则。
- 子组织规则可查看但管理操作返回 403。
- 触发类型支持多选，配置保存正确。

### 阶段二：触发机制实现

**里程碑目标**
- 实现 Celery Beat 定时任务（2 分钟周期）检查订阅规则。
- 完成属性变化、关联变化、临近到期三种触发类型的检测逻辑。

**交付内容**

1. 新增 Celery Beat 定时任务（`server/apps/cmdb/tasks/celery_tasks.py`）：
   ```python
   @shared_task
   def check_subscription_rules():
       """每 2 分钟执行，检查所有启用的订阅规则"""
   ```

2. 新增订阅触发服务（`server/apps/cmdb/services/subscription_trigger.py`）：
   - `process_rule(rule)` — 处理单条订阅规则的检测逻辑
   - `check_attribute_change(rule, instances, change_records)` — 检查属性变化
   - `check_relation_change(rule, current_snapshot, previous_snapshot)` — 检查关联变化
   - `check_expiration(rule, instances)` — 检查临近到期
   - `update_snapshot(rule, instances, relations)` — 更新规则快照数据

3. **检测流程（核心逻辑）**：

   ```
   定时任务启动
       ↓
   查询所有启用的 SubscriptionRule
       ↓
   遍历每条规则：
       ↓
   ┌─ 1. 根据 filter_type 获取当前符合条件的实例列表（从 FalkorDB）：
   │      - filter_type="condition": 根据 instance_filter.query_list 动态查询
   │      - filter_type="instances": 直接使用 instance_filter.instance_ids
   │
   ├─ 2. 如果 trigger_types 包含 relation_change：
   │      查询每个实例的一跳关联实例（按 trigger_config.relation_change.related_model）
   │
   ├─ 3. 构建当前快照数据：
   │      {
   │        "instances": [1, 2, 3],
   │        "relations": {
   │          "1": {"disk": [33, 44]},
   │          "2": {"disk": [33]}
   │        }
   │      }
   │
   ├─ 4. 检测变化：
   │      ├─ attribute_change: 查询 ChangeRecord（last_check_time 之后的 UPDATE_INST 记录）
   │      │                    对比 before_data 与 after_data，检查监听字段是否变化
   │      ├─ relation_change:  对比 previous_snapshot.relations 与 current_snapshot.relations
   │      │                    检测关联实例的新增/删除
   │      └─ expiration:       查询 FalkorDB 中时间字段落入「当前日期 + days_before」范围的实例
   │
   ├─ 5. 若检测到变化，写入 Redis 聚合队列
   │
   └─ 6. 更新规则的 snapshot_data 和 last_check_time
   ```

4. **属性变化检测逻辑**（`trigger_types` 包含 `attribute_change`）：
   - 查询 ChangeRecord：`type=UPDATE_INST`，`model_id=规则目标模型`，`created_at > last_check_time`
   - 过滤：`inst_id` 在当前实例列表中
   - 对比 `before_data` 与 `after_data`，提取变化字段
   - 检查变化字段是否在 `trigger_config.attribute_change.fields` 中
   - 命中则记录触发事件

5. **关联变化检测逻辑**（`trigger_types` 包含 `relation_change`）：
   - 从 `snapshot_data.relations` 获取上次快照
   - 对比当前关联实例与上次快照：
     - 新增关联：当前存在但上次不存在
     - 删除关联：上次存在但当前不存在
   - 命中则记录触发事件（包含关联模型、变化类型、实例信息）

6. **临近到期检测逻辑**（`trigger_types` 包含 `expiration`）：
   - 从 `trigger_config.expiration` 获取 `time_field` 和 `days_before`
   - 计算目标日期范围：`[当前日期, 当前日期 + days_before]`
   - 查询 FalkorDB：实例的 `time_field` 值落入范围
   - 命中则记录触发事件（包含到期字段、到期日期）

7. **配置 Celery Beat**（`server/config/components/celery.py`）：
   ```python
   CELERY_BEAT_SCHEDULE = {
       'check-subscription-rules': {
           'task': 'apps.cmdb.tasks.celery_tasks.check_subscription_rules',
           'schedule': crontab(minute='*/2'),  # 每 2 分钟执行
       },
   }
   ```

**阶段验收**
- Celery Beat 定时任务每 2 分钟正常执行。
- 属性变化：修改实例后，下次检查时能检测到变化。
- 关联变化：新建/删除关联后，下次检查时能通过快照对比检测到变化。
- 临近到期：时间字段落入范围的实例能被检测到。
- 快照数据正确更新并持久化。

### 阶段三：聚合发送与通知

**里程碑目标**
- 实现 1 分钟窗口聚合防打扰。
- 复用 Channel 发送通知。
- 按触发类型拆分通知，避免混合展示。

**交付内容**

1. 聚合窗口实现（使用 Redis）：
   - Key 格式：`cmdb:sub_agg:{rule_id}:{trigger_type}:{window_minute}`（按触发类型分别聚合）
   - 触发时将事件摘要（JSON）写入 Redis Set
   - 设置 TTL = 120 秒

2. 新增 Celery 任务（`server/apps/cmdb/tasks/celery_tasks.py`）：
   ```python
   @shared_task
   def send_subscription_notification():
       """每分钟执行，扫描上一窗口的聚合事件并发送通知"""
   ```

3. 通知发送逻辑：
   - 扫描上一分钟窗口的聚合 Key
   - **按触发类型分别聚合并发送**，不将不同类型变化合并为同一条通知
   - 调用 `system_mgmt.nats_api.send_msg_with_channel()` 发送

4. **通知消息设计**：

   **4.1 统一消息结构**
   - 标题：优先表达触发类型与影响范围
   - 正文：模型名称、实例标识、触发类型、变化摘要（或到期信息）
   - 触发时间：单条显示单一时间，聚合显示时间范围
   - 聚合说明：聚合通知展示实例总数

   **4.2 标题规则**

   | 场景 | 标题格式 |
   |------|----------|
   | 单实例属性变化 | `{模型名} {实例标识} 属性变化` |
   | 多实例属性变化 | `{模型名} {数量} 个实例属性变化` |
   | 单实例关联变化 | `{模型名} {实例标识} 关联对象变化` |
   | 多实例关联变化 | `{模型名} {数量} 个实例关联对象变化` |
   | 单实例临近到期 | `{模型名} {实例标识} 临近到期提醒` |
   | 多实例临近到期 | `{模型名} {数量} 个实例临近到期提醒` |
   | 实例新增 | `{模型名} 出现新增实例` |
   | 实例删除 | `{模型名} {实例标识} 已删除` |

   **4.3 变化摘要符号约定**

   | 变化类型 | 符号表达 |
   |----------|----------|
   | 属性变化 | `字段名: 旧值 -> 新值` |
   | 实例新增 | `+ 实例标识（匹配条件摘要）` |
   | 实例删除 | `- 实例标识（删除前关键标识）` |
   | 关联对象新增 | `+ 关联对象` |
   | 关联对象删除 | `- 关联对象` |
   | 关联对象属性变化 | `关联字段: 旧值 -> 新值` |
   | 临近到期 | `字段名: 到期日期（剩余 N 天）` |

   **4.4 实例数量级处理规则**

   | 数量 | 处理方式 |
   |------|----------|
   | 1 个 | 展示该实例的完整变化摘要或到期信息 |
   | 2-5 个 | 逐条列出每个实例的简要摘要 |
   | 超过 5 个 | 正文展示前 5 个实例摘要，补充"另有 N 个实例发生同类变化" |

   **4.5 触发类型拆分规则**
   - 同一规则在同一 1 分钟窗口内若同时出现多种类型变化，需拆分为多条通知
   - 属性变化仅与属性变化聚合
   - 关联变化仅与关联变化聚合
   - 临近到期仅与临近到期聚合
   - 实例新增/删除仅与同类聚合，不与普通字段变化混合

   **4.6 场景示例**

   **场景一：单实例属性变化**
   ```
   标题：物理服务器 srv-prod-01 属性变化
   正文：
   模型：物理服务器
   实例：srv-prod-01
   触发类型：属性变化
   变化摘要：内存容量: 64GB -> 128GB
   触发时间：2026-03-18 10:15:00
   ```

   **场景二：同一实例多字段变化（1分钟内）**
   ```
   标题：物理服务器 srv-prod-01 属性变化
   正文：
   模型：物理服务器
   实例：srv-prod-01
   触发类型：属性变化
   变化摘要：CPU 核数: 16 -> 32，内存容量: 64GB -> 128GB
   触发时间范围：2026-03-18 10:15:00 至 2026-03-18 10:15:42
   ```

   **场景三：3 个实例属性变化**
   ```
   标题：物理服务器 3 个实例属性变化
   正文：
   模型：物理服务器
   触发类型：属性变化
   变化摘要：
   1）srv-prod-01：内存容量: 64GB -> 128GB
   2）srv-prod-02：内存容量: 64GB -> 128GB
   3）srv-prod-03：内存容量: 64GB -> 128GB
   触发时间范围：2026-03-18 10:15:00 至 2026-03-18 10:15:58
   ```

   **场景四：8 个实例属性变化（超过5个）**
   ```
   标题：物理服务器 8 个实例属性变化
   正文：
   模型：物理服务器
   触发类型：属性变化
   变化摘要：
   1）srv-prod-01：内存容量: 64GB -> 128GB
   2）srv-prod-02：内存容量: 64GB -> 128GB
   3）srv-prod-03：内存容量: 64GB -> 128GB
   4）srv-prod-04：内存容量: 64GB -> 128GB
   5）srv-prod-05：内存容量: 64GB -> 128GB
   另有 3 个实例发生同类变化
   触发时间范围：2026-03-18 10:15:00 至 2026-03-18 10:15:59
   ```

   **场景五：关联变化**
   ```
   标题：物理服务器 srv-prod-01 关联对象变化
   正文：
   模型：物理服务器
   实例：srv-prod-01
   触发类型：关联变化
   变化摘要：disk-data-01 容量: 500GB -> 1000GB
   触发时间：2026-03-18 11:20:00
   ```

   **场景六：临近到期**
   ```
   标题：物理服务器 srv-prod-01 临近到期提醒
   正文：
   模型：物理服务器
   实例：srv-prod-01
   触发类型：临近到期
   到期信息：维保到期时间: 2026-03-25（剩余 7 天）
   触发时间：2026-03-18 09:00:00
   ```

   **场景七：实例新增（筛选订阅）**
   ```
   标题：物理服务器出现新增实例
   正文：
   模型：物理服务器
   实例：srv-prod-09
   触发类型：属性变化
   变化摘要：+ srv-prod-09（机房=广州，状态=运行中）
   触发时间：2026-03-18 13:05:00
   ```

   **场景八：实例删除**
   ```
   标题：物理服务器 srv-prod-03 已删除
   正文：
   模型：物理服务器
   实例：srv-prod-03
   触发类型：属性变化
   变化摘要：- srv-prod-03（主机名=srv-prod-03，IP=10.0.0.23）
   触发时间：2026-03-18 13:20:00
   ```

   **场景九：同一规则同时出现属性变化和关联变化（拆分为两条通知）**
   - 通知1：标题"物理服务器 2 个实例属性变化"，正文仅包含字段变化摘要
   - 通知2：标题"物理服务器 1 个实例关联对象变化"，正文仅包含关联对象变化摘要

**阶段验收**
- 同一规则 1 分钟内同类型多次触发只发送一条聚合通知。
- 不同触发类型拆分为独立通知，不混合展示。
- 通知标题正确反映实例数量（单实例显示标识，多实例显示数量）。
- 超过 5 个实例时正确截断并显示剩余数量。
- 停用规则后不再触发通知，重新启用后恢复。

### 阶段四：前端实现

**里程碑目标**
- 完成资产页面“数据订阅”入口与规则管理抽屉。
- 完成四个快速订阅入口与表单默认值逻辑。
- 完成规则创建/编辑表单与权限态展示。

**交付内容**

#### 1. 前端文件结构

```text
web/src/app/cmdb/
├─ api/
│  └─ subscription.ts                    (A) 订阅规则 API 调用
├─ types/
│  └─ subscription.ts                    (A) 订阅相关类型定义
├─ hooks/
│  └─ useSubscription.ts                 (A) 订阅相关 Hooks
├─ components/
│  └─ subscription/
│     ├─ SubscriptionDrawer.tsx          (A) 规则管理抽屉（主入口）
│     ├─ SubscriptionRuleList.tsx        (A) 规则列表组件
│     ├─ SubscriptionRuleForm.tsx        (A) 规则创建/编辑表单
│     ├─ TriggerTypeConfig.tsx           (A) 触发类型配置区（三种卡片）
│     ├─ InstanceSelector.tsx            (A) 实例选择器（勾选/条件）
│     └─ RecipientSelector.tsx           (A) 接收对象选择器
├─ (pages)/
│  └─ assetData/
│     ├─ list/
│     │  ├─ page.tsx                       (M) 添加“数据订阅”按钮 + 多选/筛选后“订阅”按钮
│     │  └─ components/
│     │     └─ ActionBar.tsx               (M) 添加“订阅”按钮
│     └─ detail/
│        └─ page.tsx                       (M) 添加实例详情页“订阅”按钮
└─ locales/
   ├─ zh.json                             (M) 中文文案
   └─ en.json                             (M) 英文文案
```

#### 2. 页面与组件设计

**2.1 规则管理抽屉（SubscriptionDrawer）**

- 入口：资产页面右上角“数据订阅”按钮
- 布局：右侧抽屉（Drawer），宽度 720px
- 内容：
  - 标题栏：“数据订阅规则” + 关闭按钮
  - 工具栏：“新建规则”按钮 + 搜索框
  - 规则列表：表格展示

**2.2 规则列表（SubscriptionRuleList）**

| 列名 | 字段 | 说明 |
|------|------|------|
| 规则名称 | `name` | 点击进入查看/编辑 |
| 所属组织 | `organization` | 展示组织名称 |
| 目标模型 | `model_id` | 展示模型名称 |
| 状态 | `is_enabled` | 开关样式（启用/停用） |
| 最近触发时间 | `last_triggered_at` | 日期时间格式 |
| 操作 | - | 查看、编辑、启停、删除 |

**2.3 规则表单（SubscriptionRuleForm）**

| 字段 | 组件 | 说明 |
|------|------|------|
| 规则名称 | Input | 必填，最大 128 字符 |
| 所属组织 | Select | 必填，默认当前组织，不可修改 |
| 目标模型 | Select | 必选，下拉选择模型 |
| 筛选类型 | Radio | “过滤条件” / “实例选择” |
| 选择实例 | InstanceSelector | 根据筛选类型切换不同 UI |
| 触发类型 | TriggerTypeConfig | 多选卡片，切换配置表单 |
| 接收对象 | RecipientSelector | 用户/用户组多选 |
| 通知渠道 | Select | 必选，下拉选择已配置渠道（多选） |
| 操作按钮 | - | “保存并启用” / “仅保存” / “取消” |

**2.4 触发类型配置区（TriggerTypeConfig）**

使用卡片多选组件，选中后展示对应配置表单：

| 触发类型 | 配置表单 |
|----------|----------|
| 属性变化 | 字段多选（下拉多选，数据源为目标模型属性） |
| 关联变化 | 关联模型下拉 + 关联字段多选（可选） |
| 临近到期 | 时间字段下拉 + 提前天数输入框（标注“自然日”） |

**2.5 实例选择器（InstanceSelector）**

- **过滤条件模式**：
  - 显示条件构建器（复用现有 FilterBuilder 组件）
  - 最多 8 个条件，显示“最多 8 个条件”提示
  - 条件之间展示“且（AND）”标签

- **实例选择模式**：
  - 显示实例列表表格（带复选框）
  - 支持搜索与分页
  - 已选实例以 Tag 形式展示

#### 3. 四个快速订阅入口与默认值

| 入口 | filter_type | instance_filter 默认值 | 规则名称默认值 |
|------|-------------|------------------------|------------------|
| 实例列表多选 | `instances` | `{instance_ids: [已勾选ID]}` | `{模型名}{时间戳}` |
| 实例列表筛选 | `condition` | `{query_list: [当前筛选条件]}` | `{模型名}{时间戳}` |
| 实例详情页 | `instances` | `{instance_ids: [当前ID]}` | `{实例名}{时间戳}` |
| 管理弹框新建 | - | 空 | 空 |

**通用默认值**：
- `organization`：当前组织
- `recipients`：`{users: [当前用户名], groups: []}`
- `is_enabled`：`true`

#### 4. API 调用（api/subscription.ts）

```typescript
// 获取订阅规则列表
function getSubscriptionRules(params: {
  search?: string;
  page?: number;
  page_size?: number;
}): Promise<PageResult<SubscriptionRule>>;

// 创建订阅规则
function createSubscriptionRule(data: SubscriptionRuleCreate): Promise<SubscriptionRule>;

// 更新订阅规则
function updateSubscriptionRule(id: number, data: SubscriptionRuleUpdate): Promise<SubscriptionRule>;

// 删除订阅规则
function deleteSubscriptionRule(id: number): Promise<void>;

// 启停订阅规则
function toggleSubscriptionRule(id: number): Promise<SubscriptionRule>;
```

#### 5. 类型定义（types/subscription.ts）

```typescript
// 筛选类型
type FilterType = 'condition' | 'instances';

// 触发类型
type TriggerType = 'attribute_change' | 'relation_change' | 'expiration';

// 订阅规则
interface SubscriptionRule {
  id: number;
  name: string;
  organization: number;
  model_id: string;
  filter_type: FilterType;
  instance_filter: ConditionFilter | InstancesFilter;
  trigger_types: TriggerType[];
  trigger_config: TriggerConfig;
  recipients: Recipients;
  channel_ids: number[];
  is_enabled: boolean;
  last_triggered_at: string | null;
  created_by: string;
  created_at: string;
  updated_by: string;
  updated_at: string;
  can_manage: boolean;  // 只读，由后端计算
}

// 过滤条件模式
interface ConditionFilter {
  query_list: QueryCondition[];
}

// 实例选择模式
interface InstancesFilter {
  instance_ids: number[];
}

// 触发配置
interface TriggerConfig {
  attribute_change?: { fields: string[] };
  relation_change?: { related_model: string; fields?: string[] };
  expiration?: { time_field: string; days_before: number };
}

// 接收对象
interface Recipients {
  users: string[];
  groups: number[];
}
```

#### 6. 国际化文案

按 Requirement 定义的中英文对照添加到 `locales/zh.json` 和 `locales/en.json`。

**阶段验收**
- 资产页面“数据订阅”按钮可打开规则管理抽屉。
- 规则列表正确展示，权限态按钮置灰生效。
- 四个快速入口默认值正确填充。
- 规则创建/编辑表单完整可用。
- 国际化文案与 Requirement 一致。

### 阶段五：前后端联调与验收

**里程碑目标**
- 完成前后端联调。
- 按 Requirement 验收标准逐条验证。

**交付内容**

1. 提供 API 文档与接口契约给前端。
2. 联调四个快速订阅入口：
   - 实例列表多选后"订阅"按钮
   - 实例列表筛选后"订阅"按钮
   - 实例详情页"订阅"按钮
   - 资产页"数据订阅"侧边弹框
3. 验证快速入口默认值：
   - 实例范围符合预期
   - 规则名称默认 `{模型/实例名称}{时间戳}`
   - 通知对象默认当前用户
   - 所属组织默认当前组织
4. 按 Requirement 验收标准逐条回归测试。

**阶段验收**
- 资产页"数据订阅"按钮可打开规则管理侧边弹框。
- 四个快速入口默认值正确生效。
- 国际化文案与 Requirement 一致。
- 所有验收标准通过。

## 相关文件

| 文件路径 | 说明 |
|----------|------|
| `server/apps/cmdb/models/subscription_rule.py` | 新增：订阅规则模型（含 snapshot_data） |
| `server/apps/cmdb/views/subscription.py` | 新增：订阅规则视图（ModelViewSet） |
| `server/apps/cmdb/services/subscription_trigger.py` | 新增：触发检测服务（属性/关联/到期检测逻辑） |
| `server/apps/cmdb/tasks/celery_tasks.py` | 修改：新增 `check_subscription_rules` 定时任务与聚合发送任务 |
| `server/config/components/celery.py` | 修改：配置 Beat 定时任务（2 分钟周期） |
| `server/apps/system_mgmt/nats_api.py` | 复用：`send_msg_with_channel()` 发送通知 |
| `web/src/app/cmdb/api/subscription.ts` | 新增：订阅规则 API 调用 |
| `web/src/app/cmdb/types/subscription.ts` | 新增：订阅相关类型定义 |
| `web/src/app/cmdb/components/subscription/` | 新增：订阅相关组件（抽屉、列表、表单等） |
| `web/src/app/cmdb/(pages)/assetData/list/page.tsx` | 修改：添加“数据订阅”入口与快速订阅按钮 |
| `web/src/app/cmdb/(pages)/assetData/detail/page.tsx` | 修改：添加实例详情页“订阅”按钮 |
| `web/src/app/cmdb/locales/*.json` | 修改：添加国际化文案 |

## 验证方案

1. **单元测试**：
   - SubscriptionRule 模型 CRUD 测试
   - 触发检测服务逻辑测试
   - 聚合窗口逻辑测试

2. **集成测试**：
   - 创建属性变化规则 → 修改实例 → 验证触发
   - 创建关联变化规则 → 新建/删除关联 → 验证触发
   - 创建临近到期规则 → 执行定时任务 → 验证触发

3. **防打扰测试**：
   - 1 分钟内连续触发 5 次 → 只收到 1 条聚合通知

4. **权限测试**：
   - 当前组织用户可管理当前组织规则
   - 当前组织用户可查看子组织规则但无法管理
   - 跨组织（非子组织）用户无法查看其他组织规则

## 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 高频变更导致触发风暴 | 系统负载上升 | 1 分钟聚合窗口 + 单规则触发频率限流 |
| 临近到期扫描大量数据 | 定时任务超时 | 分批扫描 + 游标分页，单批次限制 1000 条 |
| 通知渠道不可用 | 用户无法收到提醒 | 发送失败记录错误日志并支持重试（最多 3 次） |
| 规则配置错误导致误触发 | 用户体验下降 | 规则保存时校验表单完整性，提供测试触发功能 |

## 待确认项（TODO）

- **需人工确认**：临近到期定时任务执行时间（建议凌晨 2:00，避开业务高峰）。
- **需人工确认**：聚合通知是否需要展示全部触发详情还是仅展示计数与代表性摘要。
- **需人工确认**：接收对象选择器是否需要支持自定义外部邮箱（当前设计仅支持系统内用户/组）。
- **需人工确认**：规则数量上限（建议单组织最多 100 条规则，避免扫描压力）。
