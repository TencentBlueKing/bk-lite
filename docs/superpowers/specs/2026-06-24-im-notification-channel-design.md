# IM 应用通知渠道改进设计

## 背景

当前 IM 应用通知（IM Notification Channel）页面存在以下问题：

1. 列表页“同步状态”列混合了“频道可用性”和“最近一次同步结果”两层语义，表达不直观。
2. 弹窗中“发送字段”缺少业务说明，用户不理解该字段用途。
3. 频道可用状态与“最近同步部分成功”语义不一致：部分成功时频道状态仍显示可用。
4. `IMNotificationChannel` 已按组织型资源建模（有 `team` 字段），但接口层未完整落实组织隔离。
5. 操作列交互不合理：测试发送入口隐藏在每行操作中，查看映射对用户暴露过多实现细节。

## 目标

在不破坏现有 IM 通知核心能力（同步、映射、发送）的前提下，一次性闭环以上问题：

- 列表“同步状态”列只表达“最近一次同步结果”。
- 发送字段提供默认选中 + 统一底部提示。
- 保持“有匹配即可发送”的宽松策略，但列表明确展示“部分成功”。
- `IMNotificationChannelViewSet` 补齐 team 隔离。
- 改造测试发送为统一发送入口，调整操作列按钮。

## 设计原则

1. **后端收口状态语义**：新增 `display_sync_status` 等展示字段，前端直接消费。
2. **`channel.status` 职责不变**：继续作为“频道是否可发送”的内部状态，但不在列表状态列直接展示。
3. **team 隔离粒度最小化**：只补 `IMNotificationChannel` 自身的权限校验，不动 `available_instances` 全局逻辑。
4. **文案/提示前端补**：发送字段说明、部分成功摘要等由前端表达。

## 详细设计

### 1. 后端：Team 隔离

`IMNotificationChannelViewSet` 继续保持继承 `MaintainerViewSet`，在内部增加 team 隔离逻辑，对齐 `ChannelViewSet` / `IntegrationInstanceViewSet` 模式。

新增私有方法：

- `_get_user_group_ids(user)`：取 `user.group_list` 中的组 ID 集合；superuser 返回 `None` 表示全可见。
- `_filter_by_accessible_teams(queryset, user)`：对非 superuser，用 `Q(team__contains=group_id)` 构造 OR 查询。
- `_validate_channel_permission(request, channel)`：对非 superuser，检查频道 `team` 与用户有权限组是否有交集；无交集返回 403。
- `_validate_team_in_user_scope(request, team_values)`：校验提交的组织值必须在用户可管理范围内，防止 API 绕过前端越权提交。

覆盖接口：

| 接口 | 处理 |
|---|---|
| `list` | `_filter_by_accessible_teams` |
| `retrieve` | `_validate_channel_permission` |
| `create` | `_validate_team_in_user_scope` |
| `update` | `_validate_channel_permission` + `_validate_team_in_user_scope`（针对新增 team） |
| `destroy` | `_validate_channel_permission` |
| `sync_mappings` | `_validate_channel_permission` |
| `mappings` | `_validate_channel_permission` |
| `records` | `_validate_channel_permission` |
| `test_send` | `_validate_channel_permission` |

### 2. 后端：Serializer 展示字段

在 `IMNotificationChannelSerializer` 中新增/调整：

```python
display_sync_status = serializers.SerializerMethodField()
display_sync_summary = serializers.SerializerMethodField()
```

`display_sync_status` 返回规则：

- 最近一次同步 run 存在且 `status == running` → `"running"`
- 最近一次同步 run 存在 → 返回 run.status（`success / partial / failed`）
- 不存在（从未同步）→ `"never_synced"`

`display_sync_summary` 保持现有 `latest_sync_summary` 逻辑，由前端消费时拼接展示。

`channel.status`（`pending_sync / ready / needs_resync / disabled`）继续保留在响应中，供前端判断发送按钮是否可用。

### 3. 后端：部分成功语义保持不变

`execute_im_notification_sync_run` 中的判断逻辑不动：

- `matched_count > 0` → `channel.status = ready`
- `matched_count == 0` → `channel.status = needs_resync`

发送接口继续检查 `channel.status == ready` 即可发送。

### 4. 后端：发送接口

新增通用发送接口：

```
POST /system_mgmt/im_notification_channel/send/
```

请求体：

```json
{
  "channel_id": 1,
  "user_ids": [10, 20],
  "title": "Test",
  "content": "Hello"
}
```

后端逻辑：

1. 校验 channel 存在、enabled=True、status == ready，且当前用户有 team 权限。
2. 根据 `user_ids` 查询 `IMNotificationUserMapping`，取出对应外部接收 ID。
3. 调用 provider `send_message` 操作发送。

保留现有 detail action `POST /system_mgmt/im_notification_channel/{id}/test_send/` 以保证兼容性，未来可逐步下线。

### 5. 前端：列表页

#### 顶部按钮区

参考 `web/src/app/system-manager/(pages)/user/login-auth/page.tsx:391` 刷新按钮风格：

```tsx
<Button type='text' icon={<ReloadOutlined />} onClick={handleRefresh} loading={refreshing} />
```

顶部右侧顺序：

```
[搜索框] [添加] [发送] [刷新]
```

#### 列表列

最终 6 列：

```
名称 | 集成实例 | 最近同步 | 同步周期 | 已启用 | 操作
```

“最近同步”列渲染：

```tsx
<Tag color={getSyncRunStatusColor(status)}>
  {getSyncRunStatusText(status, t)}
</Tag>
<span>{time}</span>
<div>{summary}</div>
```

状态枚举扩展：

```ts
const statusMap = {
  running: 'processing',
  success: 'success',
  partial: 'warning',
  failed: 'error',
  never_synced: 'default',
};
```

文案：

```json
"syncRunStatus": {
  "running": "同步中",
  "success": "成功",
  "partial": "部分成功",
  "failed": "失败",
  "never_synced": "待同步"
}
```

#### 操作列

原操作列：

```
编辑 | 同步映射 | 查看映射 | 查看记录 | 测试发送 | 删除
```

修改后：

```
编辑 | 手动同步 | 同步记录 | 删除
```

文案 key 调整：

```json
"syncMappings": "手动同步",
"viewRecords": "同步记录"
```

去掉“查看映射”按钮和对应的映射 Drawer。

### 6. 前端：统一发送弹窗

弹窗表单字段：

1. **IM 同步项**：Select，选项为当前列表中 `channel.status == ready` 的频道。
2. **接收人**：多选 Select，选择 channel 后动态加载该 channel 的 `mappings`，只展示有映射关系的平台用户。
3. **标题**：Input。
4. **内容**：TextArea。

数据流：

```
用户打开发送弹窗
  → 选择 channel
  → 前端调用 GET /system_mgmt/im_notification_channel/{id}/mappings/
  → 用户多选接收人（从 mappings 中过滤出平台用户）
  → 提交 POST /system_mgmt/im_notification_channel/send/
  → 后端根据 channel + user_ids 找到 mappings，调用 provider 发送
```

### 7. 前端：添加/编辑弹窗

- 发送字段默认选中 provider 推荐值（复用现有 `default_external_receive_field` 逻辑）。
- Select 下方增加统一提示：

```tsx
<div className="mt-3 text-[12px] text-[var(--color-text-3)]">
  {t('system.channel.imNotificationPage.receiveFieldHint')}
</div>
```

文案：

```json
"receiveFieldHint": "用于将消息发送到指定用户的凭证，若无其它需求，保持默认即可。"
```

## 数据流

### 同步执行后状态更新

```python
status = SYNC_RUN_STATUS_SUCCESS if unmatched == 0 and conflict == 0 else SYNC_RUN_STATUS_PARTIAL
run.channel.status = CHANNEL_STATUS_READY if matched_count > 0 else CHANNEL_STATUS_NEEDS_RESYNC
```

- `run.status`：最近一次同步任务结果。
- `channel.status`：频道是否可发送。

### 列表展示数据流

```
channel.status          → 控制发送/测试发送按钮是否可用
channel.latest_run      → 生成 display_sync_status
channel.latest_run      → 生成 display_sync_summary
```

## 接口变更汇总

| 接口 | 变更 |
|---|---|
| `GET /system_mgmt/im_notification_channel/` | 增加 team 过滤 |
| `GET /system_mgmt/im_notification_channel/{id}/` | 增加 team 访问校验 |
| `POST /system_mgmt/im_notification_channel/` | 增加 team 范围校验 |
| `PUT /system_mgmt/im_notification_channel/{id}/` | 增加 team 访问校验 + 新增 team 范围校验 |
| `DELETE /system_mgmt/im_notification_channel/{id}/` | 增加 team 访问校验 |
| `POST /system_mgmt/im_notification_channel/{id}/sync_mappings/` | 增加 team 访问校验 |
| `GET /system_mgmt/im_notification_channel/{id}/mappings/` | 增加 team 访问校验 |
| `GET /system_mgmt/im_notification_channel/{id}/records/` | 增加 team 访问校验 |
| `POST /system_mgmt/im_notification_channel/{id}/test_send/` | 增加 team 访问校验 |
| `POST /system_mgmt/im_notification_channel/send/` | **新增**：通用发送接口 |

## 测试计划

### 后端测试

1. **team 隔离测试**
   - superuser 可查看所有频道。
   - 普通用户只能查看 team 与自己 `group_list` 有交集的频道。
   - 越权访问 retrieve/update/destroy/actions 返回 403。
2. **serializer 展示字段测试**
   - 从未同步 → `display_sync_status = never_synced`。
   - 同步成功 → `display_sync_status = success`。
   - 部分成功 → `display_sync_status = partial`。
   - 同步失败 → `display_sync_status = failed`。
3. **发送接口测试**
   - 正常发送。
   - channel 不存在/不可用返回错误。
   - user_ids 与 mappings 不匹配返回错误。

### 前端测试

1. 列表列正确合并展示。
2. 操作列按钮文案正确。
3. 发送弹窗 channel 选择、用户多选、提交正常。
4. 刷新按钮加载状态正常。

## 依赖与风险

- **依赖**：无新增外部依赖，复用现有 `ChannelViewSet` / `IntegrationInstanceViewSet` 的 team 隔离模式。
- **风险**：`IMNotificationChannelViewSet` 从 `MaintainerViewSet` 扩展 team 校验，需确保现有测试中的 `authenticated_user` 具备合适的 `group_list` 或 superuser 身份，避免测试批量失败。
- **兼容性**：保留现有 `test_send` detail action，新增 `send` action，不影响现有 API 消费者。
