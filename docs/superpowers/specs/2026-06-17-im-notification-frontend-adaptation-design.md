# IM 应用通知前端适配设计

> 说明：本文档保留设计阶段的过程记录。当前仓库实现已经在此基础上继续演进，凡与现状不一致之处，以当前代码实现为准。

## 背景

IM 应用通知后端底座已经完成重构，前端当前页面仍基于旧语义实现，存在以下错位：

- 页面表单仍使用 `mapping_strategy`、`external_field`、`message_type`
- 列表和抽屉仍把“映射关系”和“同步诊断结果”混合展示
- `sync_mappings` 仍被前端当作同步立即完成动作处理
- 页面没有接入新的 run 状态、展示状态和 provider manifest 字段语义

本次设计仅覆盖前端适配，目标是在不改变当前 IM 应用通知页面整体布局的前提下，对齐新的后端接口和业务语义。

## 目标

- 保持当前 `/system-manager/channel/im-notification` 页面的整体布局与主交互结构
- 将页面字段、列表列和抽屉内容切换到新的后端模型语义
- 将“正式映射关系”和“同步运行记录”拆开展示
- 将“同步映射”改为异步任务启动语义
- 接入 provider manifest 的匹配字段、发送字段和默认值语义

## 非目标

- 不改为 `user_sync` 的卡片式页面
- 不新增独立路由或全局记录页
- 不引入自动轮询或复杂的运行态订阅
- 不扩展文本消息之外的消息类型
- 首版不强制实现同步记录 `payload` 详情展开

## 现状

当前前端入口集中在：

- `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`
- `web/src/app/system-manager/types/im-notification.ts`
- `web/src/app/system-manager/api/im-notification/index.ts`
- `web/src/app/system-manager/utils/imNotificationUtils.ts`

当前页面布局为：

- 顶部说明区
- 搜索与新增操作区
- 渠道列表表格
- 新增/编辑弹层
- 查看映射抽屉
- 测试发送弹层

本次适配保持这套布局不变，只调整语义与字段。

## 设计原则

### 1. 布局保持稳定，语义对齐后端

用户已有页面使用心智不变，不在本轮改变主布局、主路由、动作位置和弹层组织方式。

### 2. 映射关系与运行记录明确拆分

正式映射只展示可用关系；未匹配、冲突、失败等诊断信息只属于同步运行记录，不再混入“查看映射”。

### 3. 状态展示以后端聚合字段为准

前端不自行推导 channel 运行状态，只使用后端返回的：

- `display_status`
- `latest_sync_status`
- `latest_sync_started_at`
- `latest_sync_finished_at`
- `latest_sync_summary`

### 4. 保持现有字段映射视觉表达

编辑弹层中“平台字段 = 外部字段”的表达保留，用于表示匹配字段等价关系；发送字段作为独立配置单独展示。

## 页面信息架构

页面整体结构保持不变：

1. 顶部说明区
2. 搜索框与新增按钮
3. 渠道列表表格
4. 新增/编辑弹层
5. 正式映射抽屉
6. 同步记录抽屉
7. 测试发送弹层

不新增新的主区域，不拆分新页面。

## 列表设计

列表继续使用当前表格结构，但列语义调整如下：

- `名称`
- `集成实例`
- `匹配关系`
- `发送字段`
- `状态`
- `最近同步`
- `启用`
- `操作`

### 列字段说明

#### 匹配关系

由 `platform_match_field = external_match_field` 组成，用于直接表达同步映射时的字段等价关系。

示例：

- `用户名 = user_id`
- `邮箱 = email`
- `手机号 = mobile`

#### 发送字段

展示 `external_receive_field`，用于表达发送消息时使用哪个外部字段作为接收标识。

#### 状态

使用 `display_status` 做主状态展示，前端只负责文案和颜色映射，不负责业务推导。

建议文案：

- `pending_sync` -> `待同步`
- `syncing` -> `同步中`
- `ready` -> `可用`
- `needs_resync` -> `需重新同步`
- `disabled` -> `已停用`

#### 最近同步

优先展示 `latest_sync_status`，并辅以最近开始时间或摘要。

建议文案：

- `running` -> `运行中`
- `success` -> `成功`
- `partial` -> `部分成功`
- `failed` -> `失败`

若没有运行记录，则显示空态文案。

## 操作设计

列表操作区保留当前密度与顺序风格，调整为：

- `编辑`
- `同步映射`
- `查看映射`
- `查看记录`
- `测试发送`
- `删除`

### 同步映射

- 点击后调用 `POST sync_mappings`
- 前端将其视为“启动同步任务”，而不是“同步立即完成”
- 成功后提示“同步已启动”
- 如果返回 `run_id`，首版只做轻量刷新，不做自动轮询
- 如果后端返回“已有同步进行中”，前端直接展示后端错误提示

### 查看映射

- 调用 `GET mappings`
- 只展示正式映射关系
- 不再展示 `matched/unmatched/error`

### 查看记录

- 新增动作
- 调用 `GET records`
- 展示当前 channel 的同步运行记录

### 测试发送

- 继续保留当前弹层
- 输入的“接收人”语义明确为平台用户名列表
- 渠道未进入可发送状态时禁止发起

## 新增/编辑弹层设计

继续保留当前弹层的两段结构：

- 基础信息
- 字段映射

不引入步骤条，不拆成多个弹层。

### 基础信息区

保留字段：

- `name`
- `integration_instance`
- `description`

### 字段映射区

字段映射区保留现有“字段等价关系”表达：

- 左侧：`platform_match_field`
- 中间：`=`
- 右侧：`external_match_field`

在此基础上，新增独立的发送字段配置：

- `external_receive_field`

语义约束：

- `platform_match_field` 表示平台侧用于匹配的字段
- `external_match_field` 表示外部目录中参与匹配的字段
- `external_receive_field` 表示消息发送时使用的外部接收字段

### 字段来源

#### platform_match_field

前端使用固定平台字段集合：

- `username`
- `email`
- `phone`

#### external_match_field

来自 provider manifest 的：

- `matchable_fields`

#### external_receive_field

来自 provider manifest 的：

- `receivable_fields`

### 默认值行为

新建渠道时，若所选实例对应 manifest 提供默认值，则自动填充：

- `default_external_match_field`
- `default_external_receive_field`

当 `integration_instance` 切换时：

- 更新外部匹配字段选项
- 更新发送字段选项
- 必要时重新应用默认值

## 查看映射抽屉设计

“查看映射”抽屉继续保留，但内容改为正式映射表。

建议列：

- 平台用户名
- 外部显示名 `external_display_name`
- 外部身份 `external_identity_key / external_identity_value`
- 发送字段 `external_receive_key`
- 同步时间 `synced_at`

说明：

- 不再展示状态列
- 不再展示失败摘要
- 不再展示未匹配/冲突信息

空态文案建议为：

- `暂无正式映射`

## 查看记录抽屉设计

新增“查看记录”抽屉，展示同步运行记录。

建议列：

- 开始时间
- 结束时间
- 状态
- 外部用户总数
- 匹配数
- 未匹配数
- 冲突数
- 摘要

首版仅展示列表，不强制提供 `payload` 详情展开。

如后续需要补充，可在不改主布局的前提下加二级详情视图或记录详情弹层。

## 测试发送设计

继续保留当前测试发送弹层，字段保持：

- 标题
- 内容
- 接收人

但“接收人”字段提示语调整为平台用户名语义，例如：

- 输入平台用户名，使用逗号或换行分隔

原因：

- 后端会先解析平台用户，再查正式映射发送
- 前端不应再暗示这里输入外部 receive id

## 状态与禁用规则

### 同步映射

在以下情况下禁用：

- 当前 channel 最近一条 run 为 `running`

### 测试发送

在以下状态下禁用：

- `pending_sync`
- `syncing`
- `needs_resync`
- `disabled`

仅当渠道处于可发送态时允许执行。

### 查看映射

- 始终可点
- 无数据时展示空态

### 查看记录

- 始终可点
- 无记录时展示空态

## API 与类型调整

前端需要对齐新的接口返回结构和字段模型。

### 渠道模型

`IMNotificationChannel` 需要切换到以下核心字段：

- `status`
- `platform_match_field`
- `external_match_field`
- `external_receive_field`
- `display_status`
- `latest_sync_status`
- `latest_sync_started_at`
- `latest_sync_finished_at`
- `latest_sync_summary`

删除旧前端依赖：

- `mapping_strategy`
- `external_field`
- `message_type`

### 映射模型

`IMNotificationUserMapping` 需要切换到正式关系字段：

- `user`
- `username`
- `external_identity_key`
- `external_identity_value`
- `external_receive_key`
- `external_display_name`
- `match_context`
- `external_snapshot`
- `synced_at`

### 记录模型

新增 `IMNotificationSyncRun` 前端类型，至少包括：

- `id`
- `channel`
- `status`
- `summary`
- `total_external_user_count`
- `matched_count`
- `unmatched_count`
- `conflict_count`
- `payload`
- `started_at`
- `finished_at`

### 接口调整

- `sync_mappings`：返回 `run_id`
- `mappings`：只返回正式映射
- `records`：新增 per-channel 记录接口
- `test_send`：保留现有入口，调整前端文案和可用状态控制

## 首版范围边界

本轮前端适配严格限制在以下范围：

- 保持当前 IM 应用通知页面整体布局不变
- 只做后端新语义适配
- 只支持文本消息测试发送
- 不做自动轮询
- 不做记录详情展开的强制实现
- 不引入新的页面结构和路由

## 风险与注意事项

### 1. Manifest 语义缺失会直接影响表单联动

如果 provider 未返回 `matchable_fields`、`receivable_fields` 或默认字段，前端需要有空态/降级处理，避免直接渲染错误选项。

### 2. 状态文案必须统一走后端展示语义

若前端继续自行用 `status + latest_sync_status` 拼状态，容易再次偏离后端规则。

### 3. 映射与记录不能重新混用

“查看映射”必须保持正式关系视角；同步失败、未匹配、冲突等问题只能留在“查看记录”。

## 决策结论

本次前端适配采用以下结论：

- 保持当前 IM 应用通知页面布局不变
- 列表仍为表格，不切换到卡片式
- 编辑弹层继续使用“平台字段 = 外部字段”的映射表达
- 发送字段单独配置
- 正式映射与同步记录拆成两个独立入口
- 同步映射改为异步任务启动语义
- 前端状态展示以后端聚合字段为准
