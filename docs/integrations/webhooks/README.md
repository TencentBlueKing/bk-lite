# Webhook Integration Documentation

This directory contains comprehensive documentation and examples for integrating third-party webhook bots (Feishu and DingTalk) with the BlueKing Lite platform.

## 📁 Directory Structure

```
webhooks/
├── README.md                    # This file
├── COMPARISON.md               # Feishu vs DingTalk comparison guide
├── feishu/                      # Feishu (Lark) webhook documentation
│   ├── API_REFERENCE.txt       # Quick API reference
│   ├── COMPLETE_GUIDE.md       # Full technical guide (22 KB)
│   ├── QUICK_REFERENCE.md      # Quick start guide
│   └── IMPLEMENTATION_PATTERNS.md # Integration patterns
├── dingtalk/                    # DingTalk webhook documentation
│   ├── COMPLETE_GUIDE.md       # Full technical guide (25 KB)
│   ├── QUICK_REFERENCE.md      # Quick start guide
│   └── IMPLEMENTATION_INDEX.md  # Implementation checklist
└── examples/                    # Working code examples
    ├── feishu_examples.sh       # CURL examples for Feishu
    ├── dingtalk_examples.py     # Python examples for DingTalk
    └── dingtalk_test.sh         # Testing script for DingTalk
```

## 🚀 Quick Start

### For Feishu Integration

1. **Read first**: [`feishu/QUICK_REFERENCE.md`](feishu/QUICK_REFERENCE.md)
2. **Learn API**: [`feishu/API_REFERENCE.txt`](feishu/API_REFERENCE.txt)
3. **Deep dive**: [`feishu/COMPLETE_GUIDE.md`](feishu/COMPLETE_GUIDE.md)
4. **Test examples**: Run [`examples/feishu_examples.sh`](examples/feishu_examples.sh)

### For DingTalk Integration

1. **Read first**: [`dingtalk/QUICK_REFERENCE.md`](dingtalk/QUICK_REFERENCE.md)
2. **Learn implementation**: [`dingtalk/COMPLETE_GUIDE.md`](dingtalk/COMPLETE_GUIDE.md)
3. **See code examples**: Review [`examples/dingtalk_examples.py`](examples/dingtalk_examples.py)
4. **Test webhook**: Run [`examples/dingtalk_test.sh`](examples/dingtalk_test.sh)

### Compare Both Platforms

For detailed feature and API comparison: [`COMPARISON.md`](COMPARISON.md)

## 📚 Documentation Overview

### Feishu Documentation

| Document | Purpose | Audience |
|----------|---------|----------|
| `API_REFERENCE.txt` | Complete API reference (292 lines) | Developers needing quick lookups |
| `COMPLETE_GUIDE.md` | Full technical documentation (22 KB) | Implementation teams |
| `QUICK_REFERENCE.md` | Quick start and cheat sheet (10 KB) | New developers |
| `IMPLEMENTATION_PATTERNS.md` | Integration patterns (8 KB) | Architects & senior devs |

**Key Features Documented:**
- ✅ Webhook URL format and creation
- ✅ 5 message types (text, post, interactive, image, share_chat)
- ✅ HMAC-SHA256 signature verification
- ✅ Security settings and IP whitelist
- ✅ Rate limits (10 req/sec) and error codes
- ✅ Code examples in Python, JavaScript, Go, Shell

### DingTalk Documentation

| Document | Purpose | Audience |
|----------|---------|----------|
| `COMPLETE_GUIDE.md` | Full technical documentation (25 KB) | Implementation teams |
| `QUICK_REFERENCE.md` | Quick start guide (5.5 KB) | New developers |
| `IMPLEMENTATION_INDEX.md` | Implementation checklist (10 KB) | Project managers |

**Key Features Documented:**
- ✅ Webhook URL format and token management
- ✅ 8 message types (text, markdown, link, OA, action card, etc.)
- ✅ HmacSHA256 signature verification
- ✅ AT mentions and conversation support
- ✅ Error handling and retry logic
- ✅ Code examples in Python, Node.js, Go, Java

### Code Examples

All executable examples are in the `examples/` directory:

**Feishu Examples** (`feishu_examples.sh`):
```bash
./examples/feishu_examples.sh
```
Includes:
- Simple text messages
- Markdown/rich text messages
- Interactive cards with buttons
- Image messages
- Error handling
- Signature verification

**DingTalk Examples** (`dingtalk_examples.py`):
```bash
python3 ./examples/dingtalk_examples.py
```
Includes:
- Text messages
- Markdown messages
- AT mentions
- Action cards
- Signature verification
- Error handling

**DingTalk Testing** (`dingtalk_test.sh`):
```bash
./examples/dingtalk_test.sh
```
Complete testing and validation script

## 🔑 Key Credentials & Configuration

### Feishu Setup

1. **Get Webhook URL**:
   - Open group chat in Feishu
   - Click "..." → "Add Bot" → "Custom Bot"
   - Copy webhook URL (contains token)

2. **Enable Security**:
   - Bot settings → Security Settings
   - Enable "Signature Verification"
   - Copy secret key
   - Add IP whitelist (optional)

### DingTalk Setup

1. **Get Webhook URL**:
   - Open DingTalk desktop client
   - Create/open group chat
   - Right-click → "Group Settings" → "Bot"
   - Add custom bot and get webhook URL

2. **Enable Security**:
   - Set signature secret
   - Configure IP whitelist (if needed)
   - Enable encrypted messages (optional)

## 🔐 Security Best Practices

### Signature Verification

Both platforms use HMAC-SHA256 for request verification:

**Feishu**:
- Header: `X-Lark-Request-Signature`, `X-Lark-Request-Timestamp`
- Verification string: `{timestamp}\n{secret_key}`

**DingTalk**:
- Headers: `X-Dingtalk-Signature`, `X-Dingtalk-Timestamp`
- Verification string: `{timestamp}\n{secret}`

### Always Implement

- ✅ Signature verification on webhook endpoint
- ✅ IP whitelist filtering
- ✅ HTTPS-only communication
- ✅ Rate limiting on incoming webhooks
- ✅ Logging for audit trails
- ✅ Secret key rotation (recommended quarterly)

## 📊 API Comparison at a Glance

| Feature | Feishu | DingTalk |
|---------|--------|----------|
| **Message Types** | 5 | 8 |
| **Max Payload** | ~20 KB | Varies |
| **Rate Limit** | 10 req/sec | 20 msg/min (standard) |
| **Auth Method** | HMAC-SHA256 | HmacSHA256 |
| **Interactive Cards** | ✅ (Full support) | ✅ (Action cards) |
| **AT Mentions** | ✅ | ✅ |
| **Threading/Replies** | ✅ | ✅ (Limited) |
| **Image Upload** | ✅ | ✅ |

For detailed comparison: See [`COMPARISON.md`](COMPARISON.md)

## 🧪 Testing Your Integration

### Test Feishu Webhook

```bash
# Edit feishu_examples.sh with your webhook token
export WEBHOOK_URL="https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN"

# Run test
./examples/feishu_examples.sh
```

### Test DingTalk Webhook

```bash
# Edit dingtalk_examples.py with your webhook URL
WEBHOOK_URL = "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN"

# Run test
python3 ./examples/dingtalk_examples.py

# Or use the test script
./examples/dingtalk_test.sh --token YOUR_TOKEN --secret YOUR_SECRET
```

## 🚨 Common Issues & Troubleshooting

### Signature Verification Failed

1. **Check timestamp**: Ensure system clock is synchronized
2. **Verify secret**: Confirm secret key matches webhook settings
3. **Check encoding**: Signature must be base64-encoded
4. **Inspect headers**: Print received headers for debugging

See detailed troubleshooting in each platform's guide.

### Message Not Delivered

1. **Verify webhook URL**: Test with curl first
2. **Check rate limits**: Wait between requests if hitting limits
3. **Validate JSON**: Use `jq` to validate payload format
4. **Review logs**: Check application logs for delivery status

### Authentication Issues

1. **Token/Secret mismatch**: Regenerate from bot settings
2. **Expired credentials**: Re-create bot if settings lost
3. **IP whitelist**: Add your server's IP if configured
4. **Timestamp drift**: Sync server time (NTP)

## 📖 Additional Resources

### Official Documentation
- **Feishu**: https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot
- **DingTalk**: https://developers.dingtalk.com/document/robots

### Related BlueKing Documentation
- [Integration Guide](../README.md)
- [Webhook Receiver Setup](./webhook-receiver.md)
- [Bot Configuration](../bots/README.md)

## 🤝 Contributing

To improve this documentation:

1. Test examples with your configuration
2. Report issues or clarifications needed
3. Submit documentation improvements
4. Share integration patterns and best practices

## 📝 License

This documentation is part of BlueKing Lite and follows the same MIT license.

---

**Last Updated**: February 2025  
**Status**: Production-Ready  
**Tested Against**: Feishu Open Platform v3, DingTalk v1.0
