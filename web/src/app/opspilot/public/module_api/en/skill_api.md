# Skill Embedded Chat Integration

After you add and enable an **Embedded Chat** channel on the skill Publish page, you can embed this skill as a chat window on any website. Click **Link** in the channel list to copy the endpoint. Follow this page for the integration steps.

## 1. Endpoint

After the embedded channel is saved, the URL is:

`{console origin}/api/v1/opspilot/skill_channel/embedded/{skill_id}/{channel_id}/`

- `skill_id`: the current skill ID (`id` query on the detail page)
- `channel_id`: this embedded channel ID
- Copy the full URL with **Link** on the Publish page instead of assembling it by hand

## 2. Authentication

Embedded chat does not use the console login session. Every request must send a **UserAPISecret** from System Management:

| Header | Value |
|--------|------|
| `Api-Authorization` | The plaintext token created under System Management → Platform Management → API Token |

The token's organization must be in the skill's usage organizations, and the channel must be enabled.

## 3. Request contract

- Method: `POST`
- `Content-Type`: `application/json`
- Response: SSE (`text/event-stream`)

Body example:

```json
{
  "message": "Help me check the server status",
  "session_id": "optional-session-id"
}
```

| Field | Required | Description |
|------|----------|------|
| `message` | Yes | Current user input. `user_message` is also accepted |
| `session_id` | No | Conversation id for the same visitor. Omit to start a new session. WebChat sends `sessionId` automatically |

## 4. Embed snippet

Add the following before `</body>`. Replace `sseUrl` with the copied Publish URL and `YOUR_USER_API_SECRET` with the API token. Styles and scripts can use the console-origin `/webchat/` static files.

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
            title: "Smart Assistant",
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

### Parameters

- **sseUrl**: the embedded-chat URL copied from Publish
- **requestHeaders.Api-Authorization**: UserAPISecret from System Management
- **title**: chat window title
- **theme**: `light` or `dark`
- **second argument**:
  - `null`: floating button at the bottom-right
  - a DOM element: inline embed

## 5. Typical uses

- Website customer support
- Product documentation Q&A
- Internal system guidance
- SaaS in-product help
