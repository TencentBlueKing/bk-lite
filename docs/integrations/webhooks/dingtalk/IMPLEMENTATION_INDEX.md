# DingTalk Webhook Bot API - Complete Documentation Index

## 📚 Overview

This is a comprehensive research and documentation package for the **DingTalk (钉钉) Webhook Bot API**. It includes official specifications, practical guides, working code examples, and security best practices.

**Research Date**: February 2025  
**Source**: Official DingTalk Developer Documentation  
**API Version**: v1.0+  

---

## 📄 Documentation Files

### 1. **DINGTALK_WEBHOOK_API_DOCUMENTATION.md** (25 KB)
**Complete Technical Reference**

The main comprehensive documentation covering:
- ✅ Webhook URL format and structure
- ✅ JSON payload format for all message types (text, markdown, link, actionCard, feedCard, image, file)
- ✅ HMAC-SHA256 signature authentication method
- ✅ Complete implementation examples in Python, JavaScript, Go, and Bash
- ✅ API response codes and error handling
- ✅ Security recommendations and best practices
- ✅ Troubleshooting guide
- ✅ Official references and links

**When to use**: Full technical reference, security implementation, production deployment

---

### 2. **DINGTALK_WEBHOOK_QUICK_REFERENCE.md** (5.5 KB)
**Quick Start & Cheat Sheet**

Quick reference guide with:
- ⚡ Quick start steps (getting webhook URL)
- ⚡ Common payload examples (copy-paste ready)
- ⚡ Signature generation formulas in multiple languages
- ⚡ Common message types table
- ⚡ Markdown syntax reference
- ⚡ HTTP request examples (cURL, Python)
- ⚡ Response codes
- ⚡ Rate limits and important notes

**When to use**: Quick lookups, development, debugging, code snippets

---

### 3. **dingtalk_bot_examples.py** (16 KB)
**Working Python Implementation**

Production-ready Python script with:
- 🐍 Complete `DingTalkBot` class implementation
- 🐍 HMAC-SHA256 signature generation
- 🐍 Methods for all message types
- 🐍 8 practical examples (text, markdown, links, mentions, alerts, weather, etc.)
- 🐍 CLI interface for easy testing
- 🐍 Full error handling and logging
- 🐍 Environment variable support

**When to use**: Python development, testing, integration, automation

---

## 🚀 Quick Start

### 1. Get Your Webhook URL

```bash
# 1. Open DingTalk App
# 2. Go to Group Settings → Smart Group Assistant → Add Custom Bot
# 3. Choose "Signing" (recommended for security)
# 4. Copy the webhook URL and save the secret key
```

### 2. Set Environment Variables

```bash
export DINGTALK_WEBHOOK_URL="https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"
export DINGTALK_SECRET="SECc3b8c9e8d1a2b3c4e5f6g7h8i9j0k1l"
```

### 3. Send Your First Message

**Using Python:**
```bash
python3 dingtalk_bot_examples.py --text "Hello DingTalk!"
```

**Using cURL:**
```bash
curl -X POST "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"msgtype":"text","text":{"content":"Hello DingTalk!"}}'
```

---

## 📋 Key API Information

### Webhook URL Format
```
https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN
```

### With Signature (Recommended)
```
https://oapi.dingtalk.com/robot/send?access_token=TOKEN&timestamp=TIMESTAMP&sign=SIGNATURE
```

### Signature Method (HMAC-SHA256)
```
1. string_to_sign = timestamp + "\n" + secret
2. signature = Base64(HMAC-SHA256(string_to_sign, secret))
3. signature = URLEncode(signature)
4. final_url = webhook_url + "&timestamp=" + timestamp + "&sign=" + signature
```

### Supported Message Types
| Type | Use Case |
|------|----------|
| **text** | Simple plain text messages |
| **markdown** | Rich formatted content with markdown |
| **link** | Share links with previews |
| **actionCard** | Interactive buttons/actions |
| **feedCard** | Multiple links/articles |
| **image** | Send images |
| **file** | Send files |

### Rate Limits
- ⚠️ **Maximum**: ~20 messages per minute per bot
- ⚠️ **Timestamp**: Must be within ±1 hour of server time
- ⚠️ **Milliseconds**: Timestamp in milliseconds (not seconds)

---

## 🔐 Security Features

### Two Authentication Methods

**1. Custom Keywords (Simple)**
- Configure keywords in bot settings
- Message must contain keywords
- Less secure but simpler

**2. Signing - HMAC-SHA256 (Recommended)**
- Uses timestamp + secret signature
- Secure two-way validation
- Timestamp validation prevents replay attacks
- Recommended for production

---

## 📚 Implementation Guides

### Python
```python
from dingtalk_bot_examples import DingTalkBot

bot = DingTalkBot()
bot.send_markdown(
    title="Alert",
    text="## System Status\n\n**Status**: OK"
)
```

### JavaScript/Node.js
```javascript
const crypto = require('crypto');
const timestamp = Date.now().toString();
// ... signature generation
```

### Go
```go
import "crypto/hmac"
import "crypto/sha256"
// ... signature generation
```

### Shell/Bash
```bash
TIMESTAMP=$(date +%s%N | cut -b1-13)
# ... signature generation with openssl
```

---

## 🎯 Common Use Cases

### 1. **System Alerts & Monitoring**
Send critical alerts, error notifications, and system status updates.
- Example: System down, disk full, service failed

### 2. **Scheduled Notifications**
Daily reports, weather forecasts, task reminders.
- Example: Weather report, daily standup summary

### 3. **Approval Workflows**
Interactive action cards for approvals and decisions.
- Example: Leave request approval, document review

### 4. **Integration Notifications**
Git commits, CI/CD pipeline status, deployment notifications.
- Example: GitHub commits, Jenkins build status

### 5. **Data Reports**
Visual reports with markdown formatting and tables.
- Example: Sales report, performance metrics

---

## ✅ Best Practices

### Security
- ✅ Always use HMAC-SHA256 signing in production
- ✅ Store secrets in environment variables (never hardcode)
- ✅ Use HTTPS only (not HTTP)
- ✅ Validate timestamps to prevent replay attacks

### Implementation
- ✅ Implement rate limiting to avoid hitting limits
- ✅ Add exponential backoff for retries
- ✅ Keep messages concise and clear
- ✅ Use markdown formatting for readability
- ✅ Handle errors gracefully

### Performance
- ✅ Batch messages if sending multiple
- ✅ Use appropriate message types for content
- ✅ Don't send duplicate messages
- ✅ Monitor API response times

---

## 🔧 Testing

### Test with Python Script
```bash
# Send text message
python3 dingtalk_bot_examples.py --text "Test message"

# Send markdown
python3 dingtalk_bot_examples.py --markdown

# Send with signature verification
python3 dingtalk_bot_examples.py --signature

# Run all examples
python3 dingtalk_bot_examples.py --all
```

### Test with cURL
```bash
curl -X POST \
  "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"msgtype":"text","text":{"content":"Hello!"}}'
```

### Expected Response
```json
{
  "errcode": 0,
  "errmsg": "ok"
}
```

---

## 📚 Reference Documentation

### Official Sources
- **Webhook Robot**: https://open.dingtalk.com/document/dingstart/webhook-robot
- **Message Types**: https://open.dingtalk.com/document/group/message-types-and-data-format
- **Webhook Signature**: https://open.dingtalk.com/document/connection-platform-faq/webhook-signature-tutorial
- **Security Settings**: https://open.dingtalk.com/document/robots/customize-robot-security-settings
- **Developer Center**: https://developers.dingtalk.com

### Related Resources
- **Developer Pedia**: https://open-dingtalk.github.io/developerpedia/
- **GitHub Integrations**: Various community libraries and examples
- **Community Forums**: DingTalk developer communities and Slack/Discord groups

---

## 🚨 Common Issues & Solutions

### Issue: "Invalid access_token"
**Cause**: Token is incorrect or bot deleted  
**Solution**: Regenerate webhook URL from bot settings

### Issue: "send too fast, exceed 20 times per minute"
**Cause**: Rate limit exceeded  
**Solution**: Implement rate limiting (max 20/minute)

### Issue: "forbidden" error
**Cause**: Signature validation failed  
**Solution**: Verify timestamp is within 1 hour, check secret matches

### Issue: Message not displayed
**Cause**: Keyword filtering failed (if using keyword method)  
**Solution**: Add required keywords to message

### Issue: "Timestamp out of range"
**Cause**: System clock not synchronized  
**Solution**: Sync system clock with NTP

---

## 📝 Example Payloads

### Text Message
```json
{
  "msgtype": "text",
  "text": {
    "content": "Hello DingTalk!"
  }
}
```

### Markdown with @Mention
```json
{
  "msgtype": "markdown",
  "markdown": {
    "title": "Alert",
    "text": "## System Alert\n\nStatus: Critical"
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
    "title": "Link Title",
    "text": "Description",
    "picUrl": "https://example.com/image.png"
  }
}
```

---

## 🤝 Contributing

This documentation is based on official DingTalk API documentation as of February 2025. For the latest updates:

1. Check official DingTalk Developer Documentation
2. Review API changelogs
3. Test with latest API versions

---

## 📄 License & Attribution

This documentation references and is based on:
- Official DingTalk (钉钉) API Documentation: https://open.dingtalk.com/
- DingTalk Developer Pedia: https://open-dingtalk.github.io/developerpedia/

All code examples are provided for educational and integration purposes.

---

## 📞 Support & Resources

- **Official Docs**: https://open.dingtalk.com/document/
- **Developer Center**: https://developers.dingtalk.com
- **API Status**: https://status.dingtalk.com
- **Community**: DingTalk Developer Community (钉钉开发者社区)

---

## Document Information

- **Version**: 1.0
- **Last Updated**: February 2025
- **Status**: Complete Research & Documentation
- **Files**: 3 markdown/Python files
- **Total Content**: ~46 KB

**Created**: Comprehensive research from official DingTalk documentation and reliable sources

---

### 🎓 How to Use This Package

1. **Getting Started**: Start with `DINGTALK_WEBHOOK_QUICK_REFERENCE.md`
2. **Deep Dive**: Read `DINGTALK_WEBHOOK_API_DOCUMENTATION.md` for full details
3. **Implementation**: Use `dingtalk_bot_examples.py` for practical examples
4. **Reference**: Keep this index document for quick navigation

---

**Happy messaging with DingTalk! 🚀**
