# Historical Superpowers change: 2026-07-10-alert-notification-tooltip

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-07-10-alert-notification-tooltip-design.md

## 目标

让告警处理人员在列表和详情页直接判断通知何时发送、通过什么渠道发送给哪些人、是否成功，以及新产生的失败通知为何失败，无需查询后台日志。

## 仓库现状

- `NotifyResult` 已保存通知时间、人员、渠道、通知对象和成功/失败状态。
- Alert 序列化目前只返回聚合后的 `notify_status`，没有返回明细。
- 下游响应通常包含 `message`、`errmsg` 或 `error`，但当前落库会丢弃失败原因。
- 通知调用抛异常时，当前任务可能在保存失败记录前中断。
- 渠道响应格式不统一：邮件使用 `result`，企业微信和钉钉常用 `errcode`，飞书常用 `code`。
- 详情页当前读取 `notification_status`，而后端实际字段为 `notify_status`。
- 线上单个 Alert 最多已有 78 条通知记录，Tooltip 不适合展示无上限历史。

## 已确认范围

- Tooltip 展示通知总次数和最近 5 条记录。
- 每条展示通知时间、渠道、接收人和本次结果。
- 失败记录额外展示脱敏后的失败原因。
- 失败原因只对功能上线后的新通知写入，不回填历史数据。
- 不新增通知记录表，不改变通知发送策略，不保存通知正文或完整下游响应。

## 方案选择

采用现有 Alert API 批量内嵌通知摘要和最近 5 条记录。当前 Alert 序列化已经批量查询 `NotifyResult` 来计算状态，扩展同一查询可以避免悬停时额外请求和 N+1。

不采用悬停懒加载接口，因为它会引入加载闪烁、失败状态和多次请求；不把通知摘要冗余到 Alert，因为这会引入双写和一致性问题。

## 后端设计

### 数据模型

在 `NotifyResult` 增加可空字段：

```python
failure_reason = models.TextField(null=True, blank=True, help_text="通知失败原因")
```

只生成数据库结构迁移，不编写数据迁移。历史行保持 `NULL`；上线后的失败通知写入原因，成功通知保持空值。

### 结果规范化

`NotifyResultService` 将渠道响应归一化为状态和失败原因：

1. 有布尔 `result` 时以它为准。
2. 有 `errcode` 时，`0` 为成功，非 `0` 为失败。
3. 有 `code` 时，`0` 为成功，非 `0` 为失败。
4. 没有已知状态字段时保留现有兼容语义，默认成功。
5. 通知调用抛异常时转为失败结果，并继续处理后续通知参数。

失败原因依次从 `message`、`errmsg`、`error`、`detail` 提取；没有原因时写入“通知失败，渠道未返回具体原因”。原因最多保存 500 个字符，并移除 URL 查询参数及 token、key、secret、password 等敏感值。完整异常只进入服务端日志，不进入 API。

### Alert API

保留现有 `notify_status`，新增：

```json
{
  "notify_status": "partial_success",
  "notify_total": 78,
  "notify_records": [
    {
      "notify_time": "2026-07-10 19:48:00",
      "channel": "enterprise_wechat_bot",
      "channel_name": "企业微信机器人",
      "recipients": [
        {"username": "admin", "display_name": "管理员"}
      ],
      "result": "failed",
      "failure_reason": "Webhook 地址无效"
    }
  ]
}
```

`notify_records` 按 `notify_time` 倒序，最多 5 条；`notify_total` 是该 Alert 的全部通知记录数。接收人批量查询显示名，用户不存在时使用用户名。列表、单对象序列化和事故下 Alert 列表使用同一数据契约。

## 前端设计

新增复用组件 `NotificationStatusTooltip`，同时用于：

- 告警表格“通知情况”列；
- 告警详情基础信息中的“通知情况”。

状态标签保持现有颜色：成功为绿色、失败为红色、部分成功为橙色、无记录为默认色。鼠标移入或键盘聚焦标签时显示 Tooltip。

Tooltip 宽度约 420px，最大高度 320px，内容过长时内部滚动。顶部显示“共通知 N 次，展示最近 5 次”。每条记录展示：

```text
2026-07-10 19:48:00｜企业微信机器人｜管理员（admin）｜失败
失败原因：Webhook 地址无效
```

成功记录不显示原因。失败记录没有原因时显示“未记录失败原因”。接收人过多时自动换行。无通知记录时标签和 Tooltip 均显示“未通知/暂无通知记录”。

详情页字段统一改为 `notify_status`，不再读取不存在的 `notification_status`。

## 权限与安全

- 通知明细只随用户已有权限可见的 Alert 返回，不新增权限入口。
- 不返回通知正文、完整下游响应、Webhook 地址、凭据或堆栈。
- 失败原因在持久化前脱敏和截断，避免通过 Tooltip 暴露敏感信息。

## 降级行为

- 历史失败记录的 `failure_reason` 为 `NULL`，前端显示“未记录失败原因”。
- 接收用户已删除或无法查询时显示原用户名。
- 单条通知结果解析失败时记为失败并保存安全兜底原因，不阻断后续渠道通知。
- Alert 通知明细映射异常时保留现有 `notify_status` 降级行为，并返回空明细，不影响告警列表主链路。

## 测试与验收

后端采用 TDD 覆盖：

- `result`、`errcode`、`code` 三类成功/失败响应；
- 失败原因提取、脱敏、截断和无原因兜底；
- 调用异常仍保存失败记录并继续后续通知；
- Alert 批量序列化无 N+1，返回总数和倒序最近 5 条；
- 接收人显示名和用户名回退；
- 历史空原因兼容。

前端采用 TDD 覆盖：

- 成功、失败、部分成功和未通知状态；
- 最近 5 条、总次数、失败原因和接收人展示；
- 表格和详情复用同一组件；
- 键盘聚焦可打开 Tooltip。

验收时创建 6 条以上通知记录，确认 Tooltip 仅展示最近 5 条且总数正确；制造一次带原因的渠道失败，确认原因经过脱敏后可见，后续渠道仍继续执行。
