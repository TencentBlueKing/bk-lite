# Feishu vs DingTalk Webhook API Comparison

A comprehensive technical comparison of Feishu (Lark) and DingTalk webhook integration capabilities for developers choosing between the two platforms.

## 📊 Feature Comparison Overview

| Feature | Feishu | DingTalk | Winner |
|---------|--------|----------|--------|
| **API Maturity** | v3 (Stable) | v1.0 (Stable) | Tie |
| **Message Types** | 5 types | 8 types | DingTalk |
| **Message Formatting** | Rich markdown | Limited markdown | Feishu |
| **Interactive Cards** | Full support | Action cards only | Feishu |
| **Rate Limit** | 10 req/sec | 20 msg/min | Depends¹ |
| **Max Payload Size** | ~20 KB | Varies | DingTalk |
| **Auth Complexity** | HMAC-SHA256 | HmacSHA256 | Tie |
| **IP Whitelist** | ✅ | ✅ | Tie |
| **AT Mentions** | ✅ | ✅ | Tie |
| **Threading/Replies** | ✅ | Limited | Feishu |
| **Image Upload** | ✅ | ✅ | Tie |
| **File Attachment** | ✅ | ✅ | Tie |
| **Webhooks** | Outbound only | Outbound + Inbound | DingTalk |

¹ **Rate Limit Analysis:**
- Feishu: 10 requests per second (burst capability)
- DingTalk: 20 messages per minute (continuous load)
- **Best for burst**: Feishu
- **Best for continuous**: DingTalk (roughly 0.33 req/sec sustained)

## 🔐 Authentication & Security

### Feishu Authentication

```
Method: HMAC-SHA256 with Base64 encoding

Headers:
- X-Lark-Request-Timestamp: <Unix timestamp in seconds>
- X-Lark-Request-Signature: <Base64(HMAC-SHA256(timestamp + secret))>

Signature Format: {timestamp}\n{secret_key}

Verification Window: ±5 minutes
```

**Strengths:**
- Standard HMAC-SHA256 algorithm
- Base64 encoding for readability
- Clear timestamp validation

**Implementation Complexity:** ⭐ Medium

### DingTalk Authentication

```
Method: HmacSHA256 with Base64 encoding

Headers:
- X-Dingtalk-Signature: <Base64(HmacSHA256(timestamp, secret))>
- X-Dingtalk-Timestamp: <Millisecond timestamp>

Signature Format: {timestamp}\n{secret}

Verification Window: ±5 minutes
```

**Strengths:**
- Similar to Feishu's approach
- Millisecond timestamp precision
- Well-documented

**Implementation Complexity:** ⭐ Medium

**Key Difference:** DingTalk uses millisecond timestamps vs Feishu's seconds

## 📨 Message Types Supported

### Feishu Message Types (5 Total)

| Type | Use Case | Format | Max Size |
|------|----------|--------|----------|
| **text** | Plain text messages | UTF-8 text | 4000 chars |
| **post** | Rich text with formatting | Markdown + tags | 20 KB |
| **interactive** | Buttons, dropdowns, forms | JSON card | 20 KB |
| **image** | Image display | Image key/URL | - |
| **share_chat** | Forward chat messages | Chat reference | - |

### DingTalk Message Types (8 Total)

| Type | Use Case | Format | Max Size |
|------|----------|--------|----------|
| **text** | Plain text messages | UTF-8 text | Variable |
| **markdown** | Rich text formatting | Markdown | Variable |
| **link** | Link preview cards | JSON | - |
| **OA** | OA card template | JSON | Large |
| **actionCard** | Interactive buttons | JSON | - |
| **feedCard** | News feed format | JSON | - |
| **voice** | Audio message | Audio URL | - |
| **file** | File attachment | File reference | - |

## 📝 Message Format Examples

### Text Message

**Feishu:**
```json
{
  "msg_type": "text",
  "content": {
    "text": "Hello World!"
  }
}
```

**DingTalk:**
```json
{
  "msgtype": "text",
  "text": {
    "content": "Hello World!"
  }
}
```

**Key Differences:**
- Feishu uses `msg_type`, DingTalk uses `msgtype`
- Different nesting structure
- DingTalk fields: `text.content`
- Feishu fields: `content.text`

### Markdown Message

**Feishu (Rich Text):**
```json
{
  "msg_type": "post",
  "content": {
    "post": {
      "zh_cn": {
        "title": "Notification",
        "content": [
          [
            {"tag": "text", "text": "Click "},
            {"tag": "a", "text": "here", "href": "https://example.com"}
          ]
        ]
      }
    }
  }
}
```

**DingTalk (Markdown):**
```json
{
  "msgtype": "markdown",
  "markdown": {
    "title": "Notification",
    "text": "Click [here](https://example.com)"
  }
}
```

**Key Differences:**
- **Feishu**: Tag-based HTML-like system (more verbose but precise)
- **DingTalk**: Standard Markdown (simpler but less flexible)
- **Formatting power**: Feishu > DingTalk
- **Learning curve**: DingTalk < Feishu

### Interactive Card

**Feishu (Full Interactive):**
```json
{
  "msg_type": "interactive",
  "card": {
    "config": {
      "wide_screen_mode": true
    },
    "header": {
      "title": {
        "content": "Title",
        "tag": "plain_text"
      }
    },
    "elements": [
      {
        "tag": "button",
        "text": {
          "content": "Click Me",
          "tag": "plain_text"
        },
        "type": "primary",
        "action": {
          "type": "request",
          "url": "https://api.example.com/action"
        }
      }
    ]
  }
}
```

**DingTalk (Action Card):**
```json
{
  "msgtype": "actionCard",
  "actionCard": {
    "title": "Title",
    "text": "Click the button",
    "singleTitle": "Click Me",
    "singleURL": "https://api.example.com/action",
    "btns": [
      {
        "title": "Button 1",
        "actionURL": "https://api.example.com/action1"
      },
      {
        "title": "Button 2",
        "actionURL": "https://api.example.com/action2"
      }
    ]
  }
}
```

**Key Differences:**
- **Feishu**: Complex card system with multiple elements, rich configuration
- **DingTalk**: Simple button-based cards
- **Capability**: Feishu >> DingTalk
- **Complexity**: Feishu > DingTalk

## 🎯 Use Case Recommendations

### Choose Feishu if you need:

✅ **Rich Interactive Cards**
- Complex UI with buttons, dropdowns, date pickers
- Multi-field forms
- Custom styling and colors

✅ **Advanced Formatting**
- Precise control over text styling
- Complex layouts with multiple sections
- Image embedding within messages

✅ **Higher Throughput**
- Burst capability (10 req/sec)
- Trading off for lower sustained load

✅ **Threading & Conversations**
- Building threaded notification chains
- Reply functionality

✅ **Global Teams**
- Multi-language support (zh_cn, en_us, ja_jp, etc.)
- International companies

### Choose DingTalk if you need:

✅ **Simplicity**
- Quick integration with minimal code
- Standard markdown formatting
- Straightforward APIs

✅ **Chinese Market Focus**
- Native support for Chinese enterprises
- Built-in AT mention system
- Popular in mainland China

✅ **Multiple Message Types**
- Voice messages
- OA templates
- Feed cards
- More variety of formats

✅ **Sustained High Volume**
- 20 messages per minute capacity
- Better for continuous monitoring streams

✅ **Multi-Bot Coordination**
- Inbound webhooks for bot-to-bot communication
- More flexible bot ecosystem

## 🔧 Integration Complexity Comparison

### Setup Complexity

| Step | Feishu | DingTalk |
|------|--------|----------|
| **Create Bot** | ⭐⭐ | ⭐⭐ |
| **Get Credentials** | ⭐⭐ | ⭐⭐ |
| **Auth Implementation** | ⭐⭐⭐ | ⭐⭐⭐ |
| **Send Simple Message** | ⭐⭐ | ⭐⭐ |
| **Send Interactive Card** | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| **Handle Webhooks** | ⭐⭐⭐ | ⭐⭐⭐ |
| **Error Handling** | ⭐⭐⭐ | ⭐⭐⭐ |

**Average Complexity:**
- Feishu: ⭐⭐⭐ (Slightly higher due to card system)
- DingTalk: ⭐⭐ (Simpler and more straightforward)

### Code Size Comparison

**Signature Verification:**
- Feishu: ~20-30 lines
- DingTalk: ~20-30 lines
- **Winner**: Tie

**Simple Message Send:**
- Feishu: ~10-15 lines
- DingTalk: ~10-15 lines
- **Winner**: Tie

**Interactive Card:**
- Feishu: ~50-100 lines (complex object)
- DingTalk: ~20-40 lines (simpler structure)
- **Winner**: DingTalk

**Webhook Handler:**
- Feishu: ~30-50 lines
- DingTalk: ~30-50 lines
- **Winner**: Tie

## 📊 Performance Characteristics

### Latency

| Metric | Feishu | DingTalk | Notes |
|--------|--------|----------|-------|
| **API Response Time** | 200-500ms | 200-500ms | Varies by region |
| **Message Delivery** | <1 second | <1 second | To recipient's client |
| **Webhook Timeout** | 3-5 seconds | 5 seconds | Server max wait |

### Throughput

| Scenario | Feishu | DingTalk | Notes |
|----------|--------|---------
