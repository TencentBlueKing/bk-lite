# DingTalk Webhook Bot - Quick Reference Guide

## Quick Start

### 1. Get Your Webhook URL
1. Open DingTalk → Group Settings → Smart Group Assistant → Add Custom Bot
2. Choose "Signing" for security (recommended)
3. Copy the webhook URL and save the secret

### 2. Basic Webhook URL Format
```
https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN
```

### 3. With Signature (Recommended)
```
https://oapi.dingtalk.com/robot/send?access_token=TOKEN&timestamp=TIMESTAMP&sign=SIGNATURE
```

---

## Quick Payload Examples

### Text Message
```json
{
  "msgtype": "text",
  "text": {
    "content": "Hello World!"
  }
}
```

### Markdown Message
```json
{
  "msgtype": "markdown",
  "markdown": {
    "title": "Message Title",
    "text": "## Heading\n\n**Bold text**\n\n- List item"
  }
}
```

### Link Message
```json
{
  "msgtype": "link",
  "link": {
    "messageUrl": "https://example.com",
    "title": "Link Title",
    "text": "Link description"
  }
}
```

### @Mention Users
```json
{
  "msgtype": "text",
  "text": {
    "content": "Hello!"
  },
  "at": {
    "atMobiles": ["13900000000"],
    "isAtAll": false
  }
}
```

---

## Signature Generation (HMAC-SHA256)

### Formula
```
timestamp = current_time_in_milliseconds
string_to_sign = timestamp + "\n" + secret
signature = HMAC-SHA256(string_to_sign, secret)
signature = Base64(signature)
signature = URLEncode(signature)

final_url = webhook_url + "&timestamp=" + timestamp + "&sign=" + signature
```

### Python 3
```python
import time, hmac, hashlib, base64, urllib.parse

timestamp = str(int(time.time() * 1000))
string_to_sign = f'{timestamp}\n{secret}'
hmac_code = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
sign = urllib.parse.quote(base64.b64encode(hmac_code).decode())

final_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"
```

### JavaScript
```javascript
const crypto = require('crypto');

const timestamp = Date.now().toString();
const stringToSign = `${timestamp}\n${secret}`;
const hmac = crypto.createHmac('sha256', secret);
const sign = encodeURIComponent(
    Buffer.from(hmac.update(stringToSign).digest()).toString('base64')
);

const finalUrl = `${webhookUrl}&timestamp=${timestamp}&sign=${sign}`;
```

### Go
```go
import "crypto/hmac"
import "crypto/sha256"
import "encoding/base64"
import "net/url"

timestamp := time.Now().UnixMilli()
stringToSign := fmt.Sprintf("%d\n%s", timestamp, secret)
h := hmac.New(sha256.New, []byte(secret))
h.Write([]byte(stringToSign))
sign := url.QueryEscape(base64.StdEncoding.EncodeToString(h.Sum(nil)))

finalUrl := fmt.Sprintf("%s&timestamp=%d&sign=%s", webhookUrl, timestamp, sign)
```

### cURL
```bash
TIMESTAMP=$(date +%s%N | cut -b1-13)
SIGN=$(echo -ne "${TIMESTAMP}\n${SECRET}" | openssl dgst -sha256 -hmac "$SECRET" -binary | base64 | python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.stdin.read().strip()))")

curl -X POST "${WEBHOOK_URL}&timestamp=${TIMESTAMP}&sign=${SIGN}" \
  -H 'Content-Type: application/json' \
  -d '{"msgtype":"text","text":{"content":"Hello!"}}'
```

---

## Common Message Types

| Type | Use Case | Key Fields |
|------|----------|-----------|
| **text** | Simple text | `text.content` |
| **markdown** | Rich formatting | `markdown.title`, `markdown.text` |
| **link** | Share links | `link.messageUrl`, `link.title` |
| **actionCard** | Interactive buttons | `actionCard.btns` |
| **feedCard** | Multiple links | `feedCard.links` |

---

## Markdown Syntax Reference

```markdown
# H1 Heading
## H2 Heading
### H3 Heading

**Bold**
*Italic*

> Blockquote

- Bullet point 1
- Bullet point 2

1. Numbered item
2. Numbered item

[Link text](https://url.com)
![Image alt](https://url.com/image.png)

| Col 1 | Col 2 |
|-------|-------|
| Data  | Data  |
```

---

## HTTP Request Example

### cURL
```bash
curl -X POST "https://oapi.dingtalk.com/robot/send?access_token=TOKEN" \
  -H "Content-Type: application/json;charset=utf-8" \
  -d '{
    "msgtype": "markdown",
    "markdown": {
      "title": "Alert",
      "text": "## System Alert\n\n**Status**: Error"
    }
  }'
```

### Python requests
```python
import requests

payload = {
    "msgtype": "markdown",
    "markdown": {
        "title": "Alert",
        "text": "## System Alert\n\n**Status**: Error"
    }
}

response = requests.post(webhook_url, json=payload)
print(response.json())
```

---

## Response Codes

| Code | Status |
|------|--------|
| 0 | Success |
| 130101 | Rate limited (too fast) |
| 400 | Invalid token |
| 403 | Forbidden (signature/keyword failed) |
| 500 | Server error |

---

## Important Notes

⚠️ **Rate Limit**: ~20 messages/minute per bot

⚠️ **Timestamp**: Must be within ±1 hour of server time, in milliseconds

⚠️ **Encoding**: Always use UTF-8

⚠️ **Security**: Use signing method in production

---

## Environment Setup (Recommended)

```bash
export DINGTALK_WEBHOOK_URL="https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
export DINGTALK_SECRET="SECc3b8c9e8d1a2b3c4e5f6g7h8i9j0k1l"
```

---

## Useful Links

- 📚 [Official Documentation](https://open.dingtalk.com/document/dingstart/webhook-robot)
- 🔐 [Signature Tutorial](https://open.dingtalk.com/document/connection-platform-faq/webhook-signature-tutorial)
- 📝 [Message Types](https://open.dingtalk.com/document/group/message-types-and-data-format)
- 🛡️ [Security Settings](https://open.dingtalk.com/document/robots/customize-robot-security-settings)
- 👨‍💻 [Developer Center](https://developers.dingtalk.com)

---

**Last Updated**: 2025
