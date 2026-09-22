# 智能体嵌入式对话接入说明

在智能体「发布」页添加并启用 **嵌入式对话** 渠道后，即可把该智能体以对话窗口的形式嵌入任意网页。渠道保存后，在列表中点击 **链接** 即可复制调用地址；对接步骤以本文为准。

## 1. 获取调用地址

发布并保存嵌入式对话渠道后，调用地址格式为：

`{控制台 origin}/api/v1/opspilot/skill_channel/embedded/{skill_id}/{channel_id}/`

- `skill_id`：当前智能体 ID（详情页地址栏 `id` 参数）
- `channel_id`：该嵌入式渠道 ID
- 完整 URL 请在发布列表点击 **链接** 复制，不要手写拼接以免 ID 出错

## 2. 鉴权

嵌入式对话不走控制台登录态，请求必须携带系统管理中的 **UserAPISecret**：

| 请求头 | 取值 |
|--------|------|
| `Api-Authorization` | 系统管理 → 平台管理 → API 令牌 中创建的明文令牌 |

令牌所属组织必须在该智能体的使用组织范围内，且渠道已启用，否则会返回未授权或无权使用。

## 3. 请求约定

- 方法：`POST`
- `Content-Type`：`application/json`
- 响应：SSE（`text/event-stream`）

Body 示例：

```json
{
  "message": "帮我检查下服务器状态",
  "session_id": "optional-session-id"
}
```

| 字段 | 是否必须 | 说明 |
|------|----------|------|
| `message` | 是 | 用户本轮输入，也兼容 `user_message` |
| `session_id` | 否 | 同一访客的会话 ID；不传则新建会话。WebChat 会自动带上 `sessionId` |

## 4. 网页嵌入代码示例

将以下代码添加到网页 HTML 中（建议放在 `</body>` 标签之前）。把 `sseUrl` 换成发布页复制的链接，把 `YOUR_USER_API_SECRET` 换成 API 令牌。样式与脚本可使用控制台同源的 `/webchat/` 静态资源。

```html
<script>
  !(function () {
    let e = document.createElement("link"),
      s = document.createElement("script"),
      t = document.head || document.getElementsByTagName("head")[0];

    (e.rel = "stylesheet"),
    (e.href = "/webchat/style.css"),
    t.appendChild(e);

    (s.src = "/webchat/webchat.js"),
    (s.async = !0),
    (s.onload = () => {
      if (window.WebChat && window.WebChat.default) {
        window.WebChat.default(
          {
            sseUrl: "https://your-console.example/api/v1/opspilot/skill_channel/embedded/${skill_id}/${channel_id}/",
            title: "智能助手",
            theme: "light",
            requestHeaders: {
              "Api-Authorization": "YOUR_USER_API_SECRET"
            }
          },
          null
        );
      }
    }),
    (s.onerror = () => {
      console.error("Failed to load WebChat");
    }),
    t.appendChild(s);
  })();
</script>
```

### 配置说明

- **sseUrl**：发布页复制的嵌入式对话地址
- **requestHeaders.Api-Authorization**：系统管理中的 UserAPISecret
- **title**：对话窗口标题
- **theme**：`light` 或 `dark`
- **第二个参数**：
  - `null`：页面右下角浮动按钮
  - DOM 元素：把对话窗口内联嵌入该元素

## 5. 使用场景

- 企业官网的在线客服
- 产品文档的智能问答
- 内部系统的操作引导
- SaaS 产品的用户支持
