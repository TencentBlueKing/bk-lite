# Feishu Webhook Bot - Quick Reference Card

## One-Page Reference for Developers

---

## 📋 Webhook URL Format
```
https://open.feishu.cn/open-apis/bot/v2/hook/{TOKEN}
```
- **Protocol**: HTTPS required
- **Method**: POST
- **Content-Type**: `application/json`

---

## 📨 Message Types

| Type | Use Case | Fields |
|------|----------|--------|
| `text` | Simple notification | `content.text` |
| `post` | Rich formatted text | `content.post.zh_cn` |
| `image` | Image messages | `content.image_key` |
| `interactive` | Buttons, forms, cards | `card` |

---

## 🔐 Signature Verification (HMAC-SHA256)

### Generate Signature
```python
import hmac, hashlib, base64, time

timestamp = str(int(time.time()))
string_to_sign = f"{timestamp}\n{secret}"
signature = base64.b64encode(
    hmac.new(string_to_sign.encode(), msg=b"", 
             digestmod=hashlib.sha256).digest()
).decode()
```

### Add Headers
```python
headers = {
    "X-Lark-Request-Timestamp": timestamp,
    "X-Lark-Request-Signature": signature
}
```

---

## 💬 Payload Examples

### Text Message
```json
{
  "msg_type": "text",
  "content": {"text": "Hello!"}
}
```

### Post (Markdown-style)
```json
{
  "msg_type": "post",
  "content": {
    "post": {
      "zh_cn": {
        "title": "Title",
        "content": [
          [{"tag": "text", "text": "Content"}],
          [{"tag": "a", "text": "Link", "href": "https://..."}]
        ]
      }
    }
  }
}
```

### Interactive Card
```json
{
  "msg_type": "interactive",
  "card": {
    "config": {"wide_screen_mode": true},
    "header": {"title": {"content": "Title", "tag": "plain_text"}},
    "elements": [
      {"tag": "div", "text": {"content": "**Bold** text", "tag": "lark_md"}},
      {
        "tag": "action",
        "actions": [{
          "tag": "button",
          "text": {"content": "Click", "tag": "plain_text"},
          "type": "primary",
          "multi_url": {"url": "https://..."}
        }]
      }
    ]
  }
}
```

---

## 🐍 Python Snippets

### Minimal
```python
import requests

response = requests.post(
    "https://open.feishu.cn/open-apis/bot/v2/hook/TOKEN",
    json={"msg_type": "text", "content": {"text": "Hi!"}}
)
```

### With Signature
```python
import hmac, hashlib, base64, time

def sign(secret):
    ts = str(int(time.time()))
    s2s = f"{ts}\n{secret}"
    sig = base64.b64encode(
        hmac.new(s2s.encode(), msg=b"", 
                 digestmod=hashlib.sha256).digest()
    ).decode()
    return {"X-Lark-Request-Timestamp": ts, 
            "X-Lark-Request-Signature": sig}

requests.post(webhook, json=payload, headers=sign(secret))
```

### With Retry & Rate Limit
```python
import time
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential())
def send_with_retry(webhook, payload):
    return requests.post(webhook, json=payload, timeout=10)

result = send_with_retry(webhook_url, message_payload)
```

---

## ⚡ Bash/curl Examples

### Simple
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"msg_type":"text","content":{"text":"Hi"}}' \
  https://open.feishu.cn/open-apis/bot/v2/hook/TOKEN
```

### With Signature
```bash
TS=$(date +%s)
STR="$TS\nSECRET"
SIG=$(printf "$STR" | openssl dgst -sha256 -hmac "$STR" -binary | base64)

curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-Lark-Request-Timestamp: $TS" \
  -H "X-Lark-Request-Signature: $SIG" \
  -d '{"msg_type":"text","content":{"text":"Hi"}}' \
  https://open.feishu.cn/open-apis/bot/v2/hook/TOKEN
```

---

## 🏷️ Rich Text Tags

| Tag | Syntax | Result |
|-----|--------|--------|
| Text | `{"tag": "text", "text": "..."}` | Plain text |
| Bold | `{"tag": "b", "text": "..."}` | **Bold** |
| Link | `{"tag": "a", "text": "...", "href": "..."}` | [Link] |
| Code | `{"tag": "code", "text": "..."}` | `code` |
| Mention | `{"tag": "at", "user_id": "..."}` | @user |
| Image | `{"tag": "img", "image_key": "..."}` | Image |

---

## 🔗 Card Template Colors

```json
"header": {
  "template": "blue"      // or: green, red, orange, purple
}
```

---

## 📍 Languages Supported in Post

```json
"post": {
  "zh_cn": {...},    // Simplified Chinese
  "zh_hk": {...},    // Traditional Chinese (HK)
  "zh_tw": {...},    // Traditional Chinese (TW)
  "en_us": {...},    // English
  "ja_jp": {...},    // Japanese
  "de_de": {...},    // German
  "fr_fr": {...}     // French
}
```

---

## 📊 Response Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success ✅ | Done |
| 9499 | Bad Request | Check JSON format |
| 10006 | Token invalid | Verify webhook URL |
| 10007 | Signature failed | Check signature generation |
| 10008 | Rate limited | Wait and retry |
| 10009 | Message too large | Reduce payload size |

---

## 🛡️ Security Checklist

- [ ] Use HTTPS only (not HTTP)
- [ ] Enable signature verification in bot settings
- [ ] Store webhook URL in environment variable (not hardcoded)
- [ ] Store secret in environment variable
- [ ] Implement request timeout (10s recommended)
- [ ] Add retry logic with exponential backoff
- [ ] Verify timestamp is recent (prevent replay attacks)
- [ ] Use constant-time comparison for signature verification
- [ ] Set IP whitelist if possible
- [ ] Monitor failed deliveries

---

## ⚙️ Configuration Template

```python
# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class FeishuConfig:
    WEBHOOK_URL = os.getenv('FEISHU_WEBHOOK_URL')
    WEBHOOK_SECRET = os.getenv('FEISHU_WEBHOOK_SECRET')
    BOT_NAME = os.getenv('FEISHU_BOT_NAME', 'NotificationBot')
    ENABLE_SIGNATURE = os.getenv('FEISHU_ENABLE_SIGNATURE', 'true').lower() == 'true'
    REQUEST_TIMEOUT = int(os.getenv('FEISHU_REQUEST_TIMEOUT', '10'))
    RETRY_COUNT = int(os.getenv('FEISHU_RETRY_COUNT', '3'))
```

---

## 🧪 Testing Endpoints

### Feishu Card Kit (Visual Editor)
https://open.feishu.cn/cardkit

### Bot Settings URL Pattern
In Feishu group → Click bot icon → Find your bot → Settings

### Manual Testing
```bash
# Test connectivity
ping -c 3 open.feishu.cn

# Test DNS
nslookup open.feishu.cn

# Test webhook (basic)
curl -v https://open.feishu.cn/open-apis/bot/v2/hook/TOKEN \
  -H "Content-Type: application/json" \
  -d '{"msg_type":"text","content":{"text":"test"}}'
```

---

## 📚 Common Content Structures

### Alert Format
```python
{
    "msg_type": "post",
    "content": {
        "post": {
            "zh_cn": {
                "title": f"Alert: {severity}",
                "content": [
                    [{"tag": "text", "text": f"🚨 {message}"}],
                    [{"tag": "text", "text": f"Time: {timestamp}"}]
                ]
            }
        }
    }
}
```

### Approval Flow
```python
{
    "msg_type": "interactive",
    "card": {
        "elements": [{
            "tag": "action",
            "actions": [
                {"tag": "button", "text": {"content": "Approve", "tag": "plain_text"}, 
                 "type": "primary", "multi_url": {"url": "approve_link"}},
                {"tag": "button", "text": {"content": "Reject", "tag": "plain_text"}, 
                 "type": "danger", "multi_url": {"url": "reject_link"}}
            ]
        }]
    }
}
```

### Report/Status
```python
{
    "msg_type": "post",
    "content": {
        "post": {
            "zh_cn": {
                "title": "Daily Status Report",
                "content": [
                    [{"tag": "text", "text": f"✅ Metric 1: {value}"}],
                    [{"tag": "text", "text": f"⚠️ Metric 2: {value}"}],
                    [{"tag": "text", "text": f"❌ Metric 3: {value}"}]
                ]
            }
        }
    }
}
```

---

## 🔄 Workflow Integration

### GitHub Actions
```yaml
- name: Notify Feishu
  run: |
    curl -X POST -H "Content-Type: application/json" \
      -d '{"msg_type":"text","content":{"text":"CI/CD: Success"}}' \
      ${{ secrets.FEISHU_WEBHOOK }}
```

### Jenkins
```groovy
def notifyFeishu(message) {
    sh '''
        curl -X POST -H "Content-Type: application/json" \
          -d '{"msg_type":"text","content":{"text":"''' + message + '''"}}' \
          ${FEISHU_WEBHOOK_URL}
    '''
}

post {
    success { notifyFeishu("Build succeeded") }
    failure { notifyFeishu("Build failed") }
}
```

### Python Logging Handler
```python
import logging
import requests

class FeishuHandler(logging.Handler):
    def __init__(self, webhook_url):
        super().__init__()
        self.webhook_url = webhook_url
    
    def emit(self, record):
        msg = self.format(record)
        payload = {"msg_type": "text", "content": {"text": msg}}
        requests.post(self.webhook_url, json=payload)

logging.getLogger().addHandler(
    FeishuHandler(os.getenv('FEISHU_WEBHOOK_URL'))
)
```

---

## 🐛 Troubleshooting

**Message not sent?**
- ✓ Check webhook URL is correct
- ✓ Verify bot still in group (not removed)
- ✓ Check signature if enabled
- ✓ Verify JSON format
- ✓ Check security settings (keywords/IP)

**Signature verification failed?**
- ✓ Verify secret is correct
- ✓ Use HMAC-SHA256, not SHA1
- ✓ String to sign is: `{timestamp}\n{secret}` (message=empty)
- ✓ Use constant-time comparison

**Rate limited?**
- ✓ Implement exponential backoff
- ✓ Queue messages if sending many
- ✓ Typical limit: ~5 req/sec

---

## 📖 Resources

- **Official Docs**: https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
- **Card Editor**: https://open.feishu.cn/cardkit
- **Message Format**: https://open.feishu.cn/document/server-docs/im-v1/message
- **Community**: https://open.feishu.cn/community

---

**Quick Link Generator**: For your webhook URL:
```
https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN
                                              ↑
                              Replace with your actual token
```

**Created**: February 2026  
**Version**: 1.0  
**Status**: Verified against official Feishu API
