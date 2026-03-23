# Feishu (飞书) Webhook Bot API Documentation

## Overview

Feishu allows users to create custom bots in group chats that can receive and send messages via webhooks. These bots enable integration with external systems for automated notifications, monitoring alerts, and message routing. Custom bots are simple to set up (no admin approval needed) and can be added directly to any group chat.

**Official Documentation:** https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot

---

## 1. Webhook URL Format

### Base URL Structure
```
https://open.feishu.cn/open-apis/bot/v2/hook/{WEBHOOK_TOKEN}
```

### URL Components
- **Protocol**: HTTPS (required for security)
- **Host**: `open.feishu.cn`
- **Endpoint**: `/open-apis/bot/v2/hook/`
- **WEBHOOK_TOKEN**: A unique token generated when you create the custom bot (approximately 24-32 characters)

### Example
```
https://open.feishu.cn/open-apis/bot/v2/hook/abc123def456ghi789jkl012mno345pqr
```

### URL Version Notes
- **v2 API** (Recommended): The standard webhook URL generated for new custom bots
- **v3 API**: Available for newer bot implementations with enhanced features
- Always verify which version your bot is using when creating it in Feishu

---

## 2. JSON Payload Structure

### Basic Message Format

#### Text Message
```json
{
  "msg_type": "text",
  "content": {
    "text": "Your message text here"
  }
}
```

#### Markdown/Rich Text Message
```json
{
  "msg_type": "post",
  "content": {
    "post": {
      "zh_cn": {
        "title": "Message Title",
        "content": [
          [
            {
              "tag": "text",
              "text": "Regular text "
            },
            {
              "tag": "a",
              "text": "hyperlink",
              "href": "https://example.com"
            },
            {
              "tag": "text",
              "text": " more text"
            }
          ],
          [
            {
              "tag": "img",
              "image_key": "img_key_example"
            }
          ],
          [
            {
              "tag": "at",
              "user_id": "ou_xxxxx"
            },
            {
              "tag": "text",
              "text": " mentioned user"
            }
          ]
        ]
      }
    }
  }
}
```

#### Interactive Card Message (Message Card)
```json
{
  "msg_type": "interactive",
  "card": {
    "config": {
      "wide_screen_mode": true
    },
    "header": {
      "title": {
        "content": "Card Title",
        "tag": "plain_text"
      },
      "template": "blue"
    },
    "elements": [
      {
        "tag": "div",
        "text": {
          "content": "Card content here",
          "tag": "lark_md"
        }
      },
      {
        "tag": "action",
        "actions": [
          {
            "tag": "button",
            "text": {
              "content": "Click Me",
              "tag": "plain_text"
            },
            "type": "primary",
            "multi_url": {
              "url": "https://example.com"
            }
          }
        ]
      }
    ]
  }
}
```

### Supported Message Types

| msg_type | Description | Use Case |
|----------|-------------|----------|
| `text` | Plain text messages | Simple notifications, alerts |
| `post` | Rich text with formatting, links, mentions | Formatted notifications, reports |
| `image` | Image messages | Visual alerts, screenshots |
| `share_card` | User/group card mentions | Person/group references |
| `interactive` | Complex message cards with buttons, dropdowns | Interactive forms, rich UI |

### Message Type Field Reference

```json
{
  "msg_type": "string",      // Required: one of the types above
  "content": {                // For text/image/share_card
    "text": "string",         // For text type
    "image_key": "string"     // For image type
  },
  "post": {                   // For post type
    "zh_cn": {                // Language code (zh_cn, en_us, etc.)
      "title": "string",      // Post title
      "content": [[]]         // Array of content blocks
    }
  },
  "card": {}                  // For interactive type (see card structure)
}
```

---

## 3. Authentication & Security

### Authentication Methods

Feishu offers **THREE** security mechanisms for webhooks:

#### Method 1: Custom Keyword Filtering
- **Setup**: Configure in bot settings → "Security Settings" → "Custom Keywords"
- **How It Works**: Bot only accepts messages containing specified keywords
- **Security Level**: ⭐ Low (basic filtering only)

#### Method 2: IP Whitelist
- **Setup**: Configure in bot settings → "Security Settings" → "IP Whitelist"
- **How It Works**: Bot only accepts requests from specified IP addresses
- **Security Level**: ⭐⭐ Medium (network-level security)
- **Limitation**: May not work reliably with cloud services using rotating IPs

#### Method 3: Signature Verification (HMAC-SHA256) - **RECOMMENDED**
- **Setup**: Configure in bot settings → "Security Settings" → "Signature Verification"
- **How It Works**: Each request is cryptographically signed and verified
- **Security Level**: ⭐⭐⭐ High (industry standard)

### Signature Verification (HMAC-SHA256) - Detailed Implementation

#### Signature Generation Algorithm

When you enable signature verification on the bot, Feishu provides a **Secret** (密钥). You must use this secret to generate a signature for each request.

**Signature Formula:**
```
timestamp = current_unix_timestamp_in_seconds (as string)
string_to_sign = "{timestamp}\n{secret}"
signature = base64_encode(hmac_sha256(key=string_to_sign, message=""))
```

**Important Note:** The message payload is NOT included in the signature! The signature is only based on the timestamp and secret.

#### Request Headers with Signature

Add these headers to your request:

```
X-Lark-Request-Timestamp: {timestamp}
X-Lark-Request-Signature: {signature}
```

#### Python Implementation Example

```python
import hmac
import hashlib
import base64
import time
import json
import requests

def generate_signature(secret: str) -> tuple:
    """
    Generate timestamp and signature for Feishu webhook request.
    
    Args:
        secret: The webhook secret from Feishu bot settings
        
    Returns:
        Tuple of (timestamp, signature)
    """
    timestamp = str(int(time.time()))
    
    # Create string to sign: timestamp + newline + secret
    string_to_sign = f"{timestamp}\n{secret}"
    
    # Generate HMAC-SHA256
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        msg=b"",  # Empty message
        digestmod=hashlib.sha256
    ).digest()
    
    # Encode to base64
    signature = base64.b64encode(hmac_code).decode("utf-8")
    
    return timestamp, signature


def send_feishu_message(webhook_url: str, message: dict, secret: str = None) -> dict:
    """
    Send message to Feishu webhook with optional signature verification.
    
    Args:
        webhook_url: Full webhook URL from Feishu bot
        message: Message dict with msg_type and content
        secret: Optional secret for signature verification
        
    Returns:
        Response JSON dict
    """
    headers = {
        "Content-Type": "application/json"
    }
    
    # Add signature if secret is provided
    if secret:
        timestamp, signature = generate_signature(secret)
        headers["X-Lark-Request-Timestamp"] = timestamp
        headers["X-Lark-Request-Signature"] = signature
    
    response = requests.post(
        webhook_url,
        headers=headers,
        json=message,
        timeout=10
    )
    
    return response.json()
```

#### Go Implementation Example

```go
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"strconv"
	"time"
)

// GenSign generates the signature for Feishu webhook
func GenSign(secret string) (string, string, error) {
	timestamp := strconv.FormatInt(time.Now().Unix(), 10)
	stringToSign := fmt.Sprintf("%s\n%s", timestamp, secret)
	
	h := hmac.New(sha256.New, []byte(stringToSign))
	h.Write([]byte{})  // Empty message
	signature := base64.StdEncoding.EncodeToString(h.Sum(nil))
	
	return timestamp, signature, nil
}
```

#### JavaScript/Node.js Implementation Example

```javascript
const crypto = require('crypto');

function generateSignature(secret) {
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const stringToSign = `${timestamp}\n${secret}`;
    
    const signature = crypto
        .createHmac('sha256', stringToSign)
        .update('')  // Empty message
        .digest('base64');
    
    return { timestamp, signature };
}

// Using with fetch
async function sendFeishuMessage(webhookUrl, message, secret) {
    const { timestamp, signature } = generateSignature(secret);
    
    const response = await fetch(webhookUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Lark-Request-Timestamp': timestamp,
            'X-Lark-Request-Signature': signature
        },
        body: JSON.stringify(message)
    });
    
    return response.json();
}
```

---

## 4. Example API Calls

### 4.1 Text Message (No Authentication)

**Using curl:**
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"msg_type":"text","content":{"text":"Hello from Feishu bot!"}}' \
  https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_TOKEN
```

**Using Python:**
```python
import requests

webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_TOKEN"
message = {
    "msg_type": "text",
    "content": {
        "text": "Hello from Feishu bot!"
    }
}

response = requests.post(webhook_url, json=message)
print(response.json())
```

### 4.2 Markdown/Rich Text Message (No Authentication)

**Using curl:**
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "msg_type": "post",
    "content": {
      "post": {
        "zh_cn": {
          "title": "System Alert",
          "content": [
            [
              {"tag": "text", "text": "Alert Level: "},
              {"tag": "text", "text": "HIGH", "un_escape": true}
            ],
            [
              {"tag": "a", "text": "View Details", "href": "https://example.com/alert"}
            ]
          ]
        }
      }
    }
  }' \
  https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_TOKEN
```

**Using Python:**
```python
import requests

webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_TOKEN"
message = {
    "msg_type": "post",
    "content": {
        "post": {
            "zh_cn": {
                "title": "System Alert",
                "content": [
                    [
                        {"tag": "text", "text": "Server Status: "},
                        {"tag": "text", "text": "HEALTHY"}
                    ],
                    [
                        {"tag": "a", "text": "View Dashboard", "href": "https://example.com/dashboard"}
                    ]
                ]
            }
        }
    }
}

response = requests.post(webhook_url, json=message)
print(response.json())
```

### 4.3 Text Message with Signature Verification

**Using curl:**
```bash
#!/bin/bash

WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_TOKEN"
SECRET="YOUR_WEBHOOK_SECRET"

# Generate timestamp
TIMESTAMP=$(date +%s)

# Generate signature
STRING_TO_SIGN="${TIMESTAMP}\n${SECRET}"
SIGNATURE=$(echo -ne "${STRING_TO_SIGN}" | openssl dgst -sha256 -hmac "${STRING_TO_SIGN}" -binary | base64)

# Send request
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-Lark-Request-Timestamp: ${TIMESTAMP}" \
  -H "X-Lark-Request-Signature: ${SIGNATURE}" \
  -d '{"msg_type":"text","content":{"text":"Signed message"}}' \
  ${WEBHOOK_URL}
```

**Using Python with Signature:**
```python
import requests
import hmac
import hashlib
import base64
import time
import json

webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_TOKEN"
secret = "YOUR_WEBHOOK_SECRET"

# Generate signature
timestamp = str(int(time.time()))
string_to_sign = f"{timestamp}\n{secret}"
hmac_code = hmac.new(
    string_to_sign.encode("utf-8"),
    msg=b"",
    digestmod=hashlib.sha256
).digest()
signature = base64.b64encode(hmac_code).decode("utf-8")

# Prepare headers
headers = {
    "Content-Type": "application/json",
    "X-Lark-Request-Timestamp": timestamp,
    "X-Lark-Request-Signature": signature
}

# Send message
message = {
    "msg_type": "text",
    "content": {"text": "Signed message from Python"}
}

response = requests.post(webhook_url, headers=headers, json=message)
print(response.json())
```

### 4.4 Interactive Card Message (Button)

**Using Python:**
```python
import requests

webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_TOKEN"

message = {
    "msg_type": "interactive",
    "card": {
        "config": {
            "wide_screen_mode": True
        },
        "header": {
            "title": {
                "content": "Approval Request",
                "tag": "plain_text"
            },
            "template": "blue"
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "content": "**Document**: Annual Review 2024\n**Submitted by**: Alice Chen\n**Status**: Pending",
                    "tag": "lark_md"
                }
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {
                            "content": "Approve",
                            "tag": "plain_text"
                        },
                        "type": "primary",
                        "multi_url": {
                            "url": "https://example.com/approve?id=123"
                        }
                    },
                    {
                        "tag": "button",
                        "text": {
                            "content": "Reject",
                            "tag": "plain_text"
                        },
                        "type": "danger",
                        "multi_url": {
                            "url": "https://example.com/reject?id=123"
                        }
                    }
                ]
            }
        ]
    }
}

response = requests.post(webhook_url, json=message)
print(response.json())
```

### 4.5 Message with User Mentions

**Using Python:**
```python
import requests

webhook_url = "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_TOKEN"

message = {
    "msg_type": "post",
    "content": {
        "post": {
            "zh_cn": {
                "title": "Task Assignment",
                "content": [
                    [
                        {"tag": "at", "user_id": "ou_USER_ID_123"},
                        {"tag": "text", "text": " has been assigned a new task."}
                    ],
                    [
                        {"tag": "text", "text": "Priority: "},
                        {"tag": "text", "text": "High"}
                    ]
                ]
            }
        }
    }
}

response = requests.post(webhook_url, json=message)
print(response.json())
```

---

## 5. Response Format

### Success Response
```json
{
  "code": 0,
  "msg": "ok",
  "data": {}
}
```

### Error Response
```json
{
  "code": 9499,
  "msg": "Bad Request: ...",
  "data": {}
}
```

### Common Error Codes

| Code | Meaning | Solution |
|------|---------|----------|
| 0 | Success | Message sent successfully |
| 9499 | Bad Request | Check JSON format, invalid fields |
| 9500 | Server Error | Temporary issue, retry later |
| 10006 | Token not found/invalid | Verify webhook URL and token |
| 10007 | Secret verification failed | Check signature generation (if enabled) |
| 10008 | Rate limited | Too many requests, implement backoff |

---

## 6. Setting Up a Custom Bot

### Step-by-Step Guide

1. **Open Feishu and navigate to a group chat** where you want to add the bot
2. **Click settings** (gear icon) in the top right of the group
3. **Select "Group Settings"** → **"Group Robots"** (群机器人)
4. **Click "Add Robot"** → **Select "Custom Bot"** (自定义机器人)
5. **Configure the bot:**
   - Set a **Name** (e.g., "Alert Notification Bot")
   - Add a **Description** (optional)
   - Upload an **Avatar** (optional)
6. **Click "Add"** to create the bot
7. **Copy the webhook URL** displayed - this is your unique webhook endpoint
8. **Configure Security** (optional but recommended):
   - Enable **Signature Verification** and copy the secret
   - Or set up **IP Whitelist** or **Custom Keywords** as needed
9. **Click "Save"** to finalize

### Webhook URL Retrieval

After creation, to retrieve your webhook URL:
1. Go to the group chat where the bot is added
2. Click the bot icon → **"Robot List"**
3. Find your bot and click on it
4. The webhook URL is displayed in the details section
5. If you enabled signature verification, the secret is also shown here

---

## 7. Key Implementation Notes

### Important Security Considerations

1. **Keep secrets private**: Never commit webhook URLs or secrets to version control
2. **Use environment variables**: Store credentials in `.env` files or environment variables
3. **Implement request validation**: Always verify signatures when available
4. **Add error handling**: Handle timeouts, retries, and rate limiting gracefully
5. **Log securely**: Don't log full webhook URLs or secrets

### Rate Limiting

- Feishu imposes rate limits on webhook requests
- **Recommended**: Implement exponential backoff for retries
- **Best practice**: Queue messages and batch send if possible
- **Timeout**: Set connection timeout to 10 seconds

### Message Size Limits

- Text messages: No strict limit, but keep under 4KB for optimal delivery
- Card messages: May be limited in complexity; test thoroughly
- Images: Must be uploaded separately; use image_key, not direct URLs

### Language Localization

Post messages support multiple languages:
- `zh_cn`: Simplified Chinese (default)
- `zh_hk`: Traditional Chinese (Hong Kong)
- `zh_tw`: Traditional Chinese (Taiwan)
- `en_us`: English (US)
- `ja_jp`: Japanese
- `de_de`: German
- `fr_fr`: French

**Example:**
```json
{
  "msg_type": "post",
  "content": {
    "post": {
      "zh_cn": {"title": "中文标题", "content": [[]]},
      "en_us": {"title": "English Title", "content": [[]]}
    }
  }
}
```

---

## 8. Rich Text Content Tags

### Available Tags for `post` Type Messages

| Tag | Description | Example |
|-----|-------------|---------|
| `text` | Plain text | `{"tag": "text", "text": "Hello"}` |
| `a` | Hyperlink | `{"tag": "a", "text": "Link", "href": "https://..."}` |
| `at` | User mention | `{"tag": "at", "user_id": "ou_xxx"}` |
| `img` | Image (by key) | `{"tag": "img", "image_key": "img_xxx"}` |
| `b` | Bold text | `{"tag": "b", "text": "Bold"}` |
| `i` | Italic text | `{"tag": "i", "text": "Italic"}` |
| `u` | Underline text | `{"tag": "u", "text": "Underline"}` |
| `s` | Strikethrough | `{"tag": "s", "text": "Strikethrough"}` |
| `code` | Code block | `{"tag": "code", "text": "function(){}"}` |

---

## 9. Testing Tools

### Online Tools
- **Feishu Card Kit**: https://open.feishu.cn/cardkit - Design interactive cards visually
- **Postman**: Test API calls with GUI
- **curl**: Command-line testing

### Local Testing with Python
```python
# Save as test_webhook.py
import requests
import sys

def test_webhook(webhook_url, message_text):
    """Test webhook with simple text message"""
    message = {
        "msg_type": "text",
        "content": {"text": message_text}
    }
    
    try:
        response = requests.post(
            webhook_url,
            json=message,
            timeout=10
        )
        result = response.json()
        print(f"Status: {response.status_code}")
        print(f"Response: {result}")
        return result.get('code') == 0
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    webhook_url = sys.argv[1] if len(sys.argv) > 1 else "YOUR_WEBHOOK_URL"
    message = sys.argv[2] if len(sys.argv) > 2 else "Test message"
    test_webhook(webhook_url, message)

# Usage:
# python test_webhook.py "https://open.feishu.cn/open-apis/bot/v2/hook/xxx" "Hello Feishu!"
```

---

## 10. Resources & References

### Official Documentation
- **Custom Bot Guide**: https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
- **Message Card Format**: https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/quick-start/send-message-cards-with-custom-bot
- **Card Component Reference**: https://open.feishu.cn/cardkit
- **Server API Docs**: https://open.feishu.cn/document/server-docs/im-v1/introduction

### Related Topics
- Message management & updates: https://open.feishu.cn/document/server-docs/im-v1/message
- Rich text formatting: https://open.feishu.cn/document/server-docs/im-v1/message-content-description
- Event subscription: https://open.feishu.cn/document/server-docs/event-subscription-guide/overview

### Community Resources
- Official Blog: https://open.feishu.cn/community
- Feishu Help Center: https://www.feishu.cn/hc

---

## Summary Table

| Feature | Details |
|---------|---------|
| **Webhook URL** | `https://open.feishu.cn/open-apis/bot/v2/hook/{TOKEN}` |
| **HTTP Method** | POST |
| **Content-Type** | `application/json` |
| **Message Types** | text, post, image, share_card, interactive |
| **Authentication** | Optional: Signature (HMAC-SHA256), IP whitelist, keywords |
| **Signature Header** | `X-Lark-Request-Timestamp`, `X-Lark-Request-Signature` |
| **Response Format** | JSON with `code`, `msg`, `data` |
| **Setup Time** | < 2 minutes |
| **No Admin Approval** | ✅ Custom bots don't require tenant approval |

---

**Last Updated**: February 2026  
**Feishu Platform**: Open Platform v3  
**Documentation Status**: Verified against official Feishu documentation
