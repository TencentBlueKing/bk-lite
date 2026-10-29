# 编排中心开放接口

供第三方（如 ITSM）选择并异步执行已发布流程。团队由 API 令牌绑定，请求体不得自报 `team`。

| 接口 | 方法 | 说明 |
|------|------|------|
| `/openapi/v1/workflow/workflows` | POST | 分页列出当前组织已发布且启用的流程（不含画布定义） |
| `/openapi/v1/workflow/execute-async` | POST | 按 `workflow_id` 启动流程；完成后经网关回调 |

## 列表

请求：`{ "name": "", "page": 1, "page_size": 20 }`

响应 `data`：

```json
{ "count": 1, "items": [{ "id": "12", "name": "巡检", "description": "", "current_version": 1, "enabled": true }] }
```

`id` 为字符串。ITSM 下拉的 `output_template.arr` 必须写 `data.items`（网关信封是 `{result, data}`）。

## 异步执行

请求：

```json
{
  "workflow_id": "12",
  "inputs": {},
  "callback_context": {
    "callback_url": "https://.../action_components/callback/",
    "callback_token": "...",
    "operator": "system",
    "timeout": 3600
  }
}
```

`callback_context` 由网关在 `is_callback=true` 时注入。响应 `{ "accepted": true, "execution_id": "<uuid>" }`。

流程进入终态后写入独立 outbox 再 HTTP 回调。回调失败只更新 outbox，不回写编排执行状态。含运行时主机目标字段的流程暂不支持该入口。
