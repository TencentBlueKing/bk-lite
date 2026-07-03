# OpsPilot 企微智能机器人短连接入口设计

- 日期：2026-06-30
- 状态：设计已确认，待实现计划
- 范围：OpsPilot workflow 新增企业微信智能机器人短连接 Webhook 入口

## 背景

OpsPilot workflow 已支持多类入口节点，包括 REST、OpenAI、WebChat、Mobile、企业微信应用、微信公众号、钉钉等。现有企业微信入口 `enterprise_wechat` 面向企业微信应用回调，使用 `corp_id`、`agent_id`、`secret`、`token`、`aes_key` 等应用凭据。

本次要接入的是企业微信工作台中的“智能机器人”API 模式，并选择“使用 URL 回调”的短连接方式。该模式与长连接 WebSocket 使用的凭据不同：

- 短连接 Webhook 使用 `URL`、`Token`、`EncodingAESKey`，回调消息需要验签和加解密。
- 长连接 WebSocket 使用 `BotID`、`Secret` 建立 `aibot_subscribe` 长连接，无需回调加解密，但需要心跳、重连和单连接约束。

本设计只实现短连接 Webhook，但在节点配置中预留连接模式与长连接凭据结构，避免未来接入长连接时迁移节点类型和历史配置。

## 目标

1. 新增 workflow 入口节点 `enterprise_wechat_aibot`，用于接收企业微信智能机器人短连接 URL 回调。
2. 支持企微 URL 校验、消息验签解密、文本消息转 workflow 输入、workflow 执行后主动回复。
3. 使用现有外部渠道可靠性模式：快速 ACK、Celery 异步执行、`msgid` 两阶段去重。
4. 默认且仅实现短连接；新增内部连接模式字段，默认为短连接，暂不对外开放长连接切换。
5. 保留长连接凭据结构，但当前不展示、不校验、不执行。

## 非目标

1. 不实现长连接 WebSocket、心跳、断线重连、连接抢占处理。
2. 不实现图片、语音、文件、视频、图文混排进入 workflow。
3. 不实现企微加密 userid 转明文 userid。
4. 不实现模板卡片、按钮交互、反馈事件。
5. 不改造现有 `enterprise_wechat` 企业微信应用入口。

## 仓库事实

- 后端 `server/apps/opspilot/views.py` 已有 `execute_chat_flow_wechat`、`execute_chat_flow_wechat_official`、`execute_chat_flow_dingtalk` 外部入口。
- 后端已有 `BaseChatFlowUtils` 两阶段去重与 `process_wechat_message`、`process_wechat_official_message`、`process_dingtalk_message` Celery 模式。
- 前端 `web/src/app/opspilot/constants/chatflow.ts` 维护 `nodeConfig`、`TRIGGER_NODE_TYPES` 和默认节点配置。
- 前端 `web/src/app/opspilot/components/chatflow/components/nodeConfigs/` 已有企业微信、微信公众号、钉钉等入口节点配置组件。
- `WorkFlowExecuteType` 目前没有智能机器人短连接专用入口类型。

## 官方协议摘录

官方文档来源：

- 接收消息：https://developer.work.weixin.qq.com/document/path/100719
- 被动回复消息：https://developer.work.weixin.qq.com/document/path/101031
- 回调和回复加解密：https://developer.work.weixin.qq.com/document/path/101033
- 主动回复消息：https://developer.work.weixin.qq.com/document/path/101138
- 智能机器人长连接：https://developer.work.weixin.qq.com/document/path/101463

短连接 URL 校验：

- 企业微信使用 GET 请求访问配置 URL。
- 查询参数包括 `msg_signature`、`timestamp`、`nonce`、`echostr`。
- 服务端需 URLDecode 参数，使用 `Token` 校验签名，使用 `EncodingAESKey` 解密 `echostr`。
- 企业内部智能机器人场景 `ReceiveId` 为空字符串。
- 需要在 1 秒内返回解密后的明文，响应不能加引号、BOM 或换行。

短连接消息回调：

- POST body 是加密 JSON，形如 `{"encrypt": "msg_encrypt"}`。
- 解密后常用字段包括 `msgid`、`aibotid`、`chatid`、`chattype`、`from.userid`、`response_url`、`msgtype` 和消息内容结构体。
- `msgid` 是回调唯一标识，需要排重。
- `response_url` 是主动回复临时 URL，每个 URL 只能调用一次，有效期 1 小时。

主动回复：

- 使用 `response_url` 发起 HTTP POST。
- MVP 使用 `msgtype=markdown`。
- `markdown.content` 最长 20480 字节，UTF-8 编码。

长连接差异：

- 长连接使用 `BotID` 和 `Secret` 发起 `aibot_subscribe`。
- 长连接无需短连接加解密，但需要维护 WebSocket、心跳和重连。
- 同一个智能机器人同一时间只能保持一个有效长连接。

## 推荐方案

采用“单节点 + 内部连接模式字段 + 模式化凭据”的方案。

新增入口节点类型：

```json
{
  "type": "enterprise_wechat_aibot",
  "data": {
    "config": {
      "connectionMode": "webhook",
      "webhook": {
        "token": "",
        "encodingAESKey": "",
        "aibotid": ""
      },
      "websocket": {
        "botId": "",
        "secret": ""
      },
      "inputParams": "last_message",
      "outputParams": "last_message"
    }
  }
}
```

设计取舍：

- `connectionMode` 暂不在 UI 展示，默认 `webhook`。
- `webhook` 是当前实际执行凭据。
- `websocket` 只做结构预留，当前不展示、不校验、不执行。
- 未来支持长连接时，可以在同一节点类型上开放 `connectionMode=websocket`，并接入独立 worker 或服务，不需要新增节点类型或迁移历史 workflow。

## 前端设计

### 节点注册

在 `chatflow.ts` 中新增：

- `nodeConfig.enterprise_wechat_aibot`
- `TRIGGER_NODE_TYPES` 增加 `enterprise_wechat_aibot`
- `getDefaultConfig("enterprise_wechat_aibot")` 返回模式化默认配置

展示名称建议：

- 中文：企微智能机器人
- 英文：WeCom AI Bot

图标和颜色：

- 复用企业微信图标 `qiwei2`
- 颜色使用 `green`

### 配置表单

新增 `EnterpriseWechatAibotNodeConfig`。

当前 UI 只展示短连接字段：

- `Token`
- `EncodingAESKey`
- `智能机器人 ID`，可选但建议填写

不展示：

- `connectionMode`
- `websocket.botId`
- `websocket.secret`

表单保存时仍保留完整结构，避免后续升级时覆盖长连接预留字段。

### 回调 URL 展示

节点配置中应展示只读回调地址，便于复制到企业微信后台：

```text
/api/opspilot/bot_mgmt/execute_chat_flow_enterprise_wechat_aibot/{bot_id}/
```

前端可使用当前站点 origin 拼出完整 URL。若现有页面没有可靠 origin 获取能力，可先展示相对路径和说明。

## 后端设计

### 枚举

新增 workflow 执行入口类型：

```python
ENTERPRISE_WECHAT_AIBOT = "enterprise_wechat_aibot"
```

用于：

- `WorkFlowConversationHistory.entry_type`
- workflow task result 的 `execute_type`
- 统计图中的渠道区分

### URL

新增路由：

```text
bot_mgmt/execute_chat_flow_enterprise_wechat_aibot/<int:bot_id>/
```

对应视图：

```python
execute_chat_flow_enterprise_wechat_aibot(request, bot_id)
```

### 工具类

新增 `EnterpriseWechatAibotChatFlowUtils`，继承 `BaseChatFlowUtils`。

职责：

1. 查找 workflow 中的 `enterprise_wechat_aibot` 节点。
2. 读取 `connectionMode`，当前只允许 `webhook`。
3. 读取并校验 `webhook.token`、`webhook.encodingAESKey`。
4. 处理 GET URL 校验。
5. 处理 POST 消息解密、解析、去重、投递 Celery。
6. 使用 `response_url` 主动回复 markdown。

### 加解密

短连接使用企业微信智能机器人加解密规则：

- GET 参数：`msg_signature`、`timestamp`、`nonce`、`echostr`
- POST 参数：`msg_signature`、`timestamp`、`nonce`
- POST body：`{"encrypt": "..."}`
- `receive_id` 固定为空字符串

实现优先复用已有企业微信加解密库能力；若现有 `wechatpy.enterprise.WeChatCrypto` 无法直接以空 `receive_id` 完成智能机器人协议，应封装独立加解密适配器，并用官方示例测试数据或本地构造用例覆盖。

### 消息处理

支持的 MVP 输入：

- `msgtype=text`
- 读取 `text.content`
- 群聊中保守移除开头的 `@机器人名`，只把真实问题传入 workflow

输入映射：

```python
{
    "last_message": clean_text,
    "user_id": from_userid,
    "bot_id": bot_id,
    "node_id": node_id,
    "channel": "enterprise_wechat_aibot",
    "is_third_party": True,
    "session_id": chatid or from_userid,
    "response_url": response_url,
}
```

若配置了 `webhook.aibotid`，必须与回调 `aibotid` 一致；不一致时记录告警并快速返回成功，不进入 workflow。

### 去重与任务

缓存 key 前缀：

```text
enterprise_wechat_aibot_msg:{bot_id}:{msgid}
```

状态沿用：

- `processing`：处理中，短 TTL
- `completed`：已完成，长 TTL
- 失败清除标记，允许重试

新增 Celery 任务：

```python
process_enterprise_wechat_aibot_message(bot_id, msg_id, message, sender_id, config)
```

任务流程：

1. 获取 online bot 和 workflow。
2. 执行 workflow。
3. 将最终输出转成 markdown。
4. POST `response_url`。
5. 回复成功后标记 completed。
6. 失败时清理去重标记并触发 Celery 重试。

`response_url` 只允许调用一次。实现中需要保证只有最终一次发送；重试路径应避免在发送成功后再次发送。

### 回复格式

主动回复请求：

```json
{
  "msgtype": "markdown",
  "markdown": {
    "content": "workflow 最终输出"
  }
}
```

内容处理：

- 空输出：回复 `处理完成，但未产生可展示内容`
- 超过 20480 字节：截断并附加提示
- 异常失败：回复 `处理失败，请稍后重试`，并记录内部错误日志

### 不支持消息

对非文本消息：

1. 不进入 workflow。
2. 若存在 `response_url`，主动回复 `当前仅支持文本消息`。
3. 标记 completed，避免重复提示。

## 权限与审计

- 该入口属于外部回调，不依赖登录态。
- 服务端必须校验 bot 在线状态、workflow 存在、入口节点存在、短连接模式匹配和签名合法。
- 新增或修改 workflow 节点配置沿用现有 Bot/Workflow 编辑权限。
- 回调不写操作日志，避免外部用户消息刷操作日志；但 workflow 执行结果和对话历史应按现有 workflow 机制记录。
- 配置中的 Token 和 EncodingAESKey 属于敏感字段，前端回显应脱敏，后端存储应遵循现有渠道配置加密策略或 workflow 配置的敏感字段处理能力。

## 状态与失败语义

| 场景 | 行为 |
|---|---|
| URL 校验成功 | 返回解密明文 |
| URL 校验失败 | 返回 fail，并记录错误 |
| 签名非法 | 快速返回成功或失败响应，不进入 workflow，记录告警 |
| bot 未上线 | 快速返回成功，不进入 workflow |
| workflow 缺失 | 快速返回成功，不进入 workflow |
| 节点不是 webhook 模式 | 快速返回成功，不进入 workflow |
| aibotid 不匹配 | 快速返回成功，不进入 workflow |
| 重复 msgid | 快速返回成功，不重复处理 |
| 非文本消息 | 主动回复不支持提示，标记 completed |
| workflow 执行失败 | 主动回复失败提示，任务失败可追踪 |
| response_url 调用失败 | 任务重试，最终失败记录日志 |

## 测试策略

后端测试：

1. GET URL 校验成功，返回解密明文。
2. GET URL 校验签名失败，返回失败响应。
3. POST 解密文本消息后投递 Celery。
4. `msgid` 重复时不重复投递 Celery。
5. `aibotid` 配置不匹配时不进入 workflow。
6. 非文本消息使用 `response_url` 回复不支持提示。
7. Celery 成功执行后调用 `response_url` 并标记 completed。
8. `response_url` 调用失败时清理去重标记并触发重试。
9. `connectionMode=websocket` 时当前返回未启用，不执行短连接逻辑。

前端测试：

1. 节点面板出现“企微智能机器人”入口。
2. 新节点默认配置包含 `connectionMode=webhook`、`webhook` 和 `websocket` 结构。
3. UI 只展示短连接字段。
4. 保存后不丢失未展示的 `websocket` 预留结构。
5. 回调 URL 展示正确。

最小验证命令：

- 后端：`cd server && make test`
- 前端：`cd web && pnpm lint && pnpm type-check`

## 验收标准

1. 用户可以在 workflow 中添加“企微智能机器人”入口节点。
2. 用户能复制回调 URL，并在企业微信智能机器人短连接配置中完成 URL 校验。
3. 企微文本消息回调能触发 workflow 执行。
4. workflow 最终输出能通过 `response_url` 主动回复到企微。
5. 重复回调不会重复执行 workflow。
6. 非文本消息得到明确“不支持”提示。
7. 长连接字段已存在于配置结构，但当前不展示、不校验、不执行。

## 已确认决策

1. 当前实现短连接 Webhook，不实现长连接。
2. 短连接节点配置使用 `Token`、`EncodingAESKey` 和可选 `aibotid`。
3. 回复使用 `response_url` 主动回复 markdown。
4. MVP 只支持文本消息。
5. 群聊消息会去掉开头的 @ 机器人前缀。
6. `from.userid` 先原样作为 workflow `user_id`。
7. 新增内部字段 `connectionMode`，默认短连接，暂不对外开放。
8. 长连接凭据字段保留在配置结构中，但当前不展示、不校验、不执行。

## 后续实现计划入口

设计通过后，下一步应创建实现计划，拆分为：

1. 后端枚举、URL、工具类和 Celery 任务。
2. 加解密适配与测试。
3. 前端节点注册、默认配置和配置表单。
4. 回调 URL 展示和敏感字段脱敏。
5. 端到端最小验证。
