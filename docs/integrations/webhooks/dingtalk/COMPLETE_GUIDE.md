# DingTalk (钉钉) Webhook Bot API Documentation

## Overview

DingTalk (钉钉) is Alibaba's all-in-one mobile workplace platform that provides webhook bot capabilities for sending messages to group chats. This documentation covers the official webhook bot API format, including endpoint structure, payload formats, authentication, and implementation examples.

---

## 1. Webhook URL Format

### Basic URL Structure

```
https://oapi.dingtalk.com/robot/send?access_token=YOUR_ACCESS_TOKEN
```

### Components

| Component | Description | Example |
|-----------|-------------|---------|
| **Base URL** | DingTalk API endpoint | `https://oapi.dingtalk.com/robot/send` |
| **access_token** | Unique identifier for the bot | `a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6` |
| **timestamp** | (Optional) Milliseconds timestamp for signing | `1695283635765` |
| **sign** | (Optional) HMAC-SHA256 signature for security | Base64 + URL encoded string |

### URL Examples

**Without Signature (Keyword-based security):**
```
https://oapi.dingtalk.com/robot/send?access_token=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
```

**With Signature (Signing-based security):**
```
https://oapi.dingtalk.com/robot/send?access_token=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6&timestamp=1695283635765&sign=BASE64_ENCODED_SIGNATURE
```

### How to Get the Webhook URL

1. Open DingTalk App or Web (https://im.dingtalk.com)
2. Navigate to the group chat where you want to add the bot
3. Click **Settings** (right upper area)
4. Select **Group Settings** → **Smart Group Assistant** → **Add Bot**
5. Choose **Custom Bot** and click **Add**
6. Configure security:
   - **Custom Keywords**: Simple but less secure
   - **Signing** (Recommended): More secure with HMAC-SHA256
7. Copy the Webhook URL
8. Save the settings

---

## 2. JSON Payload Structure for Message Types

### General Message Payload Structure

```json
{
  "msgtype": "MESSAGE_TYPE",
  "MESSAGE_TYPE_OBJECT": {
    // Type-specific fields
  },
  "at": {
    "atMobiles": ["13900000000", "13900000001"],
    "atUserIds": ["user_id_1", "user_id_2"],
    "isAtAll": false
  }
}
```

### Supported Message Types

1. **text** - Plain text message
2. **markdown** - Markdown formatted message
3. **link** - Link preview message
4. **actionCard** - Interactive action card
5. **feedCard** - Feed card (multiple links)
6. **image** - Image message
7. **file** - File message
8. **richText** - Rich text message (interactive cards)

---

## 3. Markdown Message Format

### Payload Structure

```json
{
  "msgtype": "markdown",
  "markdown": {
    "title": "Message Title",
    "text": "Markdown formatted content here"
  },
  "at": {
    "atMobiles": ["phone_number_1", "phone_number_2"],
    "isAtAll": false
  }
}
```

### Markdown Fields

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| **msgtype** | string | Must be `"markdown"` | ✓ |
| **markdown.title** | string | Title of the message (displayed in card header) | ✓ |
| **markdown.text** | string | Markdown-formatted text content | ✓ |
| **at.atMobiles** | array | Phone numbers to @mention | ✗ |
| **at.isAtAll** | boolean | Whether to @all users in group | ✗ |

### Markdown Text Formatting

DingTalk supports standard Markdown syntax:

```markdown
# Heading Level 1
## Heading Level 2
### Heading Level 3

**Bold text**
*Italic text*

> Blockquote text

- Unordered list item 1
- Unordered list item 2

1. Ordered list item 1
2. Ordered list item 2

[Link Text](https://example.com)
![Image Alt](https://example.com/image.png)

| Header 1 | Header 2 |
|----------|----------|
| Cell 1   | Cell 2   |
```

### Markdown Example

```json
{
  "msgtype": "markdown",
  "markdown": {
    "title": "Weather Report - Xi'an",
    "text": "#### Xi'an Weather\n\n> Good morning everyone,\n> \n> Today's weather: 20℃ Clear\n> \n> Please remember to stay warm!\n> \n> ![Weather Icon](https://example.com/weather.png)\n> \n> [View detailed weather forecast](https://weather.example.com)"
  },
  "at": {
    "atMobiles": ["13900000000"],
    "isAtAll": false
  }
}
```

---

## 4. Other Message Types

### Text Message

```json
{
  "msgtype": "text",
  "text": {
    "content": "Hello DingTalk! This is a plain text message."
  },
  "at": {
    "atMobiles": ["13900000000"],
    "isAtAll": false
  }
}
```

### Link Message

```json
{
  "msgtype": "link",
  "link": {
    "messageUrl": "https://example.com",
    "picUrl": "https://example.com/image.png",
    "title": "Link Title",
    "text": "Link description text"
  }
}
```

### Action Card (Interactive Buttons)

```json
{
  "msgtype": "actionCard",
  "actionCard": {
    "title": "Card Title",
    "text": "Card content text",
    "hideAvatar": "0",
    "btnOrientation": "0",
    "singleTitle": "Click Here",
    "singleURL": "https://example.com",
    "btns": [
      {
        "title": "Button 1",
        "actionURL": "https://example.com/action1"
      },
      {
        "title": "Button 2",
        "actionURL": "https://example.com/action2"
      }
    ]
  }
}
```

### Feed Card (Multiple Links)

```json
{
  "msgtype": "feedCard",
  "feedCard": {
    "links": [
      {
        "title": "Article 1 Title",
        "messageURL": "https://example.com/article1",
        "picURL": "https://example.com/image1.png"
      },
      {
        "title": "Article 2 Title",
        "messageURL": "https://example.com/article2",
        "picURL": "https://example.com/image2.png"
      }
    ]
  }
}
```

---

## 5. Authentication & Security

### Authentication Methods

DingTalk provides two security mechanisms:

#### Method 1: Custom Keywords (Simple)
- Messages must contain specific keywords configured in the bot settings
- Less secure but simpler to implement
- No additional authentication required in API calls

#### Method 2: Signing/HMAC-SHA256 (Recommended)
- Uses HMAC-SHA256 signature verification
- Requires both timestamp and signature in the webhook URL
- More secure for production environments

### Signing Method (HMAC-SHA256)

#### Step 1: Prepare the Signing String

```
stringToSign = timestamp + "\n" + secret
```

Where:
- **timestamp**: Current time in milliseconds (e.g., `1695283635765`)
- **secret**: The SEC-prefixed string from bot security settings (e.g., `SECc3b8c9e8d1a2b3c4e5f6g7h8i9j0k1l`)

#### Step 2: Calculate HMAC-SHA256

```
signature = HMAC-SHA256(stringToSign, secret.getBytes("UTF-8"))
```

#### Step 3: Base64 Encode

```
encodedSignature = Base64.encode(signature)
```

#### Step 4: URL Encode

```
finalSignature = URLEncode(encodedSignature, "UTF-8")
```

#### Step 5: Construct Final URL

```
finalURL = webhookURL + "&timestamp=" + timestamp + "&sign=" + finalSignature
```

### Important Notes

1. **Timestamp Validation**: The timestamp must be within 1 hour of DingTalk server time
2. **Milliseconds**: Timestamp must be in milliseconds, not seconds
3. **Character Set**: Always use UTF-8 encoding
4. **Rate Limiting**: DingTalk enforces a rate limit (approximately 20 messages per minute per bot)

---

## 6. Implementation Examples

### Python Example

```python
import requests
import json
import time
import hmac
import hashlib
import base64
import urllib.parse

class DingTalkBot:
    def __init__(self, webhook_url, secret=None):
        """
        Initialize DingTalk bot
        
        Args:
            webhook_url: The base webhook URL from DingTalk bot settings
            secret: The SEC-prefixed secret (only needed for signing method)
        """
        self.webhook_url = webhook_url
        self.secret = secret
        self.headers = {'Content-Type': 'application/json;charset=utf-8'}
    
    def generate_sign(self):
        """Generate HMAC-SHA256 signature"""
        if not self.secret:
            return None, None
        
        # Get current timestamp in milliseconds
        timestamp = str(int(time.time() * 1000))
        
        # Create string to sign
        string_to_sign = f'{timestamp}\n{self.secret}'
        
        # Calculate HMAC-SHA256
        hmac_code = hmac.new(
            self.secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        
        # Base64 encode
        sign = base64.b64encode(hmac_code).decode('utf-8')
        
        # URL encode
        sign = urllib.parse.quote(sign)
        
        return timestamp, sign
    
    def get_final_url(self):
        """Get the final URL with signature if secret is provided"""
        if self.secret:
            timestamp, sign = self.generate_sign()
            return f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"
        return self.webhook_url
    
    def send_text_message(self, content, at_mobiles=None, at_all=False):
        """Send plain text message"""
        payload = {
            "msgtype": "text",
            "text": {
                "content": content
            },
            "at": {
                "atMobiles": at_mobiles or [],
                "isAtAll": at_all
            }
        }
        return self._send(payload)
    
    def send_markdown_message(self, title, text, at_mobiles=None, at_all=False):
        """Send markdown message"""
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": text
            },
            "at": {
                "atMobiles": at_mobiles or [],
                "isAtAll": at_all
            }
        }
        return self._send(payload)
    
    def send_link_message(self, message_url, title, text, pic_url=None):
        """Send link message"""
        payload = {
            "msgtype": "link",
            "link": {
                "messageUrl": message_url,
                "title": title,
                "text": text
            }
        }
        if pic_url:
            payload["link"]["picUrl"] = pic_url
        return self._send(payload)
    
    def _send(self, payload):
        """Send message payload"""
        url = self.get_final_url()
        try:
            response = requests.post(
                url,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            return {
                "success": result.get("errcode") == 0,
                "response": result
            }
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": str(e)
            }

# Usage Example
if __name__ == "__main__":
    # Without signature (keyword-based)
    bot = DingTalkBot("https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN")
    
    # Or with signature (recommended)
    # bot = DingTalkBot(
    #     "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN",
    #     secret="SECc3b8c9e8d1a2b3c4e5f6g7h8i9j0k1l"
    # )
    
    # Send text message
    response = bot.send_text_message("Hello DingTalk!")
    print(response)
    
    # Send markdown message
    markdown_text = """#### Project Status Report
    
> **Sprint**: Week 42
> **Status**: In Progress
> **Completion**: 75%
> 
> **Tasks Completed**:
> - API development
> - Database migration
> 
> **Pending**:
> - Testing
> - Documentation"""
    
    response = bot.send_markdown_message(
        title="Sprint Status Update",
        text=markdown_text,
        at_mobiles=["13900000000"],
        at_all=False
    )
    print(response)
```

### JavaScript/Node.js Example

```javascript
const crypto = require('crypto');
const axios = require('axios');

class DingTalkBot {
    constructor(webhookUrl, secret = null) {
        this.webhookUrl = webhookUrl;
        this.secret = secret;
        this.headers = {
            'Content-Type': 'application/json;charset=utf-8'
        };
    }

    generateSign() {
        if (!this.secret) {
            return { timestamp: null, sign: null };
        }

        // Get current timestamp in milliseconds
        const timestamp = Date.now().toString();

        // Create string to sign
        const stringToSign = `${timestamp}\n${this.secret}`;

        // Calculate HMAC-SHA256
        const hmac = crypto.createHmac('sha256', this.secret);
        hmac.update(stringToSign);
        const digest = hmac.digest('base64');

        // URL encode
        const sign = encodeURIComponent(digest);

        return { timestamp, sign };
    }

    getFinalUrl() {
        if (this.secret) {
            const { timestamp, sign } = this.generateSign();
            return `${this.webhookUrl}&timestamp=${timestamp}&sign=${sign}`;
        }
        return this.webhookUrl;
    }

    async sendTextMessage(content, atMobiles = [], atAll = false) {
        const payload = {
            msgtype: "text",
            text: {
                content: content
            },
            at: {
                atMobiles: atMobiles,
                isAtAll: atAll
            }
        };
        return this.send(payload);
    }

    async sendMarkdownMessage(title, text, atMobiles = [], atAll = false) {
        const payload = {
            msgtype: "markdown",
            markdown: {
                title: title,
                text: text
            },
            at: {
                atMobiles: atMobiles,
                isAtAll: atAll
            }
        };
        return this.send(payload);
    }

    async sendLinkMessage(messageUrl, title, text, picUrl = null) {
        const payload = {
            msgtype: "link",
            link: {
                messageUrl: messageUrl,
                title: title,
                text: text
            }
        };
        if (picUrl) {
            payload.link.picUrl = picUrl;
        }
        return this.send(payload);
    }

    async send(payload) {
        try {
            const url = this.getFinalUrl();
            const response = await axios.post(url, payload, {
                headers: this.headers,
                timeout: 10000
            });
            return {
                success: response.data.errcode === 0,
                response: response.data
            };
        } catch (error) {
            return {
                success: false,
                error: error.message
            };
        }
    }
}

// Usage Example
(async () => {
    // Without signature
    const bot = new DingTalkBot("https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN");

    // Or with signature
    // const bot = new DingTalkBot(
    //     "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN",
    //     "SECc3b8c9e8d1a2b3c4e5f6g7h8i9j0k1l"
    // );

    // Send text message
    let result = await bot.sendTextMessage("Hello DingTalk!");
    console.log(result);

    // Send markdown message
    const markdownText = `#### Weather Report
    
> **City**: Xi'an
> **Temperature**: 20℃
> **Condition**: Clear
> 
> Please stay warm!`;

    result = await bot.sendMarkdownMessage(
        "Weather Update",
        markdownText,
        ["13900000000"],
        false
    );
    console.log(result);
})();
```

### Go Example

```go
package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

type DingTalkBot struct {
	WebhookURL string
	Secret     string
	Client     *http.Client
}

type TextMessage struct {
	MsgType string `json:"msgtype"`
	Text    struct {
		Content string `json:"content"`
	} `json:"text"`
	At struct {
		AtMobiles []string `json:"atMobiles"`
		IsAtAll   bool     `json:"isAtAll"`
	} `json:"at"`
}

type MarkdownMessage struct {
	MsgType  string `json:"msgtype"`
	Markdown struct {
		Title string `json:"title"`
		Text  string `json:"text"`
	} `json:"markdown"`
	At struct {
		AtMobiles []string `json:"atMobiles"`
		IsAtAll   bool     `json:"isAtAll"`
	} `json:"at"`
}

func NewDingTalkBot(webhookURL, secret string) *DingTalkBot {
	return &DingTalkBot{
		WebhookURL: webhookURL,
		Secret:     secret,
		Client:     &http.Client{Timeout: 10 * time.Second},
	}
}

func (bot *DingTalkBot) GenerateSign() (string, int64) {
	timestamp := time.Now().UnixMilli()
	stringToSign := fmt.Sprintf("%d\n%s", timestamp, bot.Secret)

	h := hmac.New(sha256.New, []byte(bot.Secret))
	h.Write([]byte(stringToSign))
	signature := base64.StdEncoding.EncodeToString(h.Sum(nil))

	// URL encode
	signature = url.QueryEscape(signature)

	return signature, timestamp
}

func (bot *DingTalkBot) GetFinalURL() string {
	if bot.Secret == "" {
		return bot.WebhookURL
	}

	signature, timestamp := bot.GenerateSign()
	return fmt.Sprintf("%s&timestamp=%d&sign=%s", bot.WebhookURL, timestamp, signature)
}

func (bot *DingTalkBot) SendTextMessage(content string, atMobiles []string, atAll bool) (map[string]interface{}, error) {
	msg := TextMessage{
		MsgType: "text",
	}
	msg.Text.Content = content
	msg.At.AtMobiles = atMobiles
	msg.At.IsAtAll = atAll

	return bot.send(msg)
}

func (bot *DingTalkBot) SendMarkdownMessage(title, text string, atMobiles []string, atAll bool) (map[string]interface{}, error) {
	msg := MarkdownMessage{
		MsgType: "markdown",
	}
	msg.Markdown.Title = title
	msg.Markdown.Text = text
	msg.At.AtMobiles = atMobiles
	msg.At.IsAtAll = atAll

	return bot.send(msg)
}

func (bot *DingTalkBot) send(message interface{}) (map[string]interface{}, error) {
	payload, err := json.Marshal(message)
	if err != nil {
		return nil, err
	}

	finalURL := bot.GetFinalURL()
	resp, err := bot.Client.Post(
		finalURL,
		"application/json;charset=utf-8",
		strings.NewReader(string(payload)),
	)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	var result map[string]interface{}
	err = json.Unmarshal(body, &result)
	if err != nil {
		return nil, err
	}

	return result, nil
}

func main() {
	// Without signature
	bot := NewDingTalkBot(
		"https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN",
		"",
	)

	// Or with signature
	// bot := NewDingTalkBot(
	//     "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN",
	//     "SECc3b8c9e8d1a2b3c4e5f6g7h8i9j0k1l",
	// )

	// Send text message
	result, err := bot.SendTextMessage("Hello DingTalk!", []string{}, false)
	if err != nil {
		fmt.Println("Error:", err)
		return
	}
	fmt.Println("Result:", result)

	// Send markdown message
	markdownText := `#### Project Update

> **Status**: In Progress
> **Completion**: 80%
> 
> Recent changes:
> - Implemented new features
> - Fixed bugs`

	result, err = bot.SendMarkdownMessage(
		"Project Status",
		markdownText,
		[]string{"13900000000"},
		false,
	)
	if err != nil {
		fmt.Println("Error:", err)
		return
	}
	fmt.Println("Result:", result)
}
```

### Shell/Bash Example

```bash
#!/bin/bash

# DingTalk Webhook Bot Sending Script

WEBHOOK_URL="https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
SECRET="SECc3b8c9e8d1a2b3c4e5f6g7h8i9j0k1l"  # Optional, for signing

# Function to generate signature
generate_sign() {
    local timestamp=$1
    local secret=$2
    
    # Create string to sign
    local string_to_sign="${timestamp}\n${secret}"
    
    # Use openssl for HMAC-SHA256
    local sign=$(echo -ne "$string_to_sign" | openssl dgst -sha256 -hmac "$secret" -binary | base64)
    
    # URL encode
    sign=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$sign'))")
    
    echo "$sign"
}

# Function to send text message
send_text_message() {
    local content=$1
    local at_mobiles=${2:-"[]"}
    local at_all=${3:-"false"}
    
    local url="$WEBHOOK_URL"
    
    # Add signature if secret is provided
    if [ -n "$SECRET" ]; then
        local timestamp=$(date +%s%N | cut -b1-13)
        local sign=$(generate_sign "$timestamp" "$SECRET")
        url="${url}&timestamp=${timestamp}&sign=${sign}"
    fi
    
    local payload=$(cat <<EOF
{
  "msgtype": "text",
  "text": {
    "content": "$content"
  },
  "at": {
    "atMobiles": $at_mobiles,
    "isAtAll": $at_all
  }
}
EOF
    )
    
    curl -X POST "$url" \
        -H 'Content-Type: application/json;charset=utf-8' \
        -d "$payload"
}

# Function to send markdown message
send_markdown_message() {
    local title=$1
    local text=$2
    local at_mobiles=${3:-"[]"}
    local at_all=${4:-"false"}
    
    local url="$WEBHOOK_URL"
    
    # Add signature if secret is provided
    if [ -n "$SECRET" ]; then
        local timestamp=$(date +%s%N | cut -b1-13)
        local sign=$(generate_sign "$timestamp" "$SECRET")
        url="${url}&timestamp=${timestamp}&sign=${sign}"
    fi
    
    # Escape newlines in text for JSON
    text=$(echo "$text" | sed 's/$/\\n/g')
    
    local payload=$(cat <<EOF
{
  "msgtype": "markdown",
  "markdown": {
    "title": "$title",
    "text": "$text"
  },
  "at": {
    "atMobiles": $at_mobiles,
    "isAtAll": $at_all
  }
}
EOF
    )
    
    curl -X POST "$url" \
        -H 'Content-Type: application/json;charset=utf-8' \
        -d "$payload"
}

# Usage Examples
echo "Sending text message..."
send_text_message "Hello DingTalk!"

echo -e "\nSending markdown message..."
markdown_text="#### Alert Report
> **Level**: INFO
> **Time**: $(date)
> **Status**: Normal Operation"

send_markdown_message "System Alert" "$markdown_text" '["13900000000"]' "false"
```

---

## 7. API Response Format

### Successful Response (200 OK)

```json
{
  "errcode": 0,
  "errmsg": "ok",
  "data": {}
}
```

### Error Response

```json
{
  "errcode": 130101,
  "errmsg": "send too fast, exceed 20 times per minute"
}
```

### Common Error Codes

| Error Code | Message | Description |
|-----------|---------|-------------|
| 0 | ok | Message sent successfully |
| 130101 | send too fast, exceed 20 times per minute | Rate limit exceeded |
| 400 | invalid access_token | Invalid or missing access token |
| 403 | forbidden | Access denied (keyword/signature verification failed) |
| 500 | Internal Server Error | DingTalk server error |

---

## 8. Best Practices & Security

### Security Recommendations

1. **Use Signing Method**: Always use HMAC-SHA256 signing for production environments
2. **Protect Secrets**: Never commit `access_token` or `secret` to version control
3. **Use Environment Variables**: Store credentials in environment variables
4. **HTTPS Only**: Always use HTTPS (not HTTP)
5. **Validate Timestamps**: Ensure timestamp is within 1 hour of current time
6. **Rate Limiting**: Be aware of the 20 messages/minute limit per bot

### Implementation Best Practices

```python
# ✅ Good: Using environment variables
import os

webhook_url = os.environ.get('DINGTALK_WEBHOOK_URL')
secret = os.environ.get('DINGTALK_SECRET')

# ❌ Bad: Hardcoding credentials
webhook_url = "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
secret = "SECc3b8c9e8d1a2b3c4e5f6g7h8i9j0k1l"
```

### Message Best Practices

1. **Keep messages concise**: Avoid overly long messages
2. **Use markdown effectively**: Utilize formatting for clarity
3. **Include timestamps**: Add timestamps for time-sensitive information
4. **Handle rate limits**: Implement retry logic with exponential backoff
5. **Error handling**: Always handle HTTP errors gracefully

---

## 9. Common Issues & Troubleshooting

### Issue 1: "Invalid access_token"
- **Cause**: Token is incorrect or bot was deleted
- **Solution**: Regenerate webhook URL from bot settings

### Issue 2: "send too fast, exceed 20 times per minute"
- **Cause**: Exceeded rate limit
- **Solution**: Implement rate limiting in your code

### Issue 3: "forbidden" error with signature
- **Cause**: Signature validation failed
- **Solution**: 
  - Verify timestamp is within 1 hour of DingTalk server time
  - Ensure secret matches exactly
  - Check timestamp is in milliseconds, not seconds
  - Verify URL encoding is correct

### Issue 4: Message not displayed
- **Cause**: Keyword filtering failed (if using keyword method)
- **Solution**: Ensure message contains configured keywords

### Issue 5: "Timestamp out of range"
- **Cause**: System time is not synchronized
- **Solution**: Synchronize system clock with NTP server

---

## 10. References

### Official Documentation
- **Webhook Robot**: https://open.dingtalk.com/document/dingstart/webhook-robot
- **Message Types**: https://open.dingtalk.com/document/group/message-types-and-data-format
- **Webhook Signature**: https://open.dingtalk.com/document/connection-platform-faq/webhook-signature-tutorial
- **Custom Bot Security**: https://open.dingtalk.com/document/robots/customize-robot-security-settings
- **Enterprise Internal Robots**: https://open.dingtalk.com/document/group/assign-a-webhook-url-to-an-internal-chatbot

### Developer Resources
- **Developer Center**: https://developers.dingtalk.com
- **API Reference**: https://open.dingtalk.com/document/group/custom-robot-access
- **Message Examples**: https://open-dingtalk.github.io/developerpedia/docs/learn/bot/message/

---

## Document Version

- **Version**: 1.0
- **Last Updated**: 2025
- **Status**: Official DingTalk Documentation Reference
- **Compatibility**: Works with DingTalk API v1.0 and later

---

## License & Attribution

This documentation is based on official DingTalk (钉钉) API documentation available at https://open.dingtalk.com/document/. The examples and code snippets are provided for educational purposes.

For the most up-to-date information, please refer to the official DingTalk developer documentation.
