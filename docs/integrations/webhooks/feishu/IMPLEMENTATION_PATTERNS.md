# Feishu Integration Analysis - bk-lite Codebase

## Summary
This document analyzes the bk-lite codebase to identify existing patterns for multiple bot/channel types and webhook handling, specifically to inform Feishu integration.

---

## 1. Bot Type & Channel Type Definition

### Bot Types (in `opspilot/enum.py`)
```python
class BotTypeChoice(models.IntegerChoices):
    PILOT = (1, _("Pilot"))
    LOBE = (2, _("LobeChat"))
    CHAT_FLOW = (3, _("ChatFlow"))
```

### Channel Types (Multiple Locations)

**opspilot/enum.py:**
```python
class ChannelChoices(models.TextChoices):
    ENTERPRISE_WECHAT = ("enterprise_wechat", _("Enterprise WeChat"))
    ENTERPRISE_WECHAT_BOT = ("enterprise_wechat_bot", _("Enterprise WeChat Bot"))
    WECHAT_OFFICIAL_ACCOUNT = ("wechat_official_account", _("WeChat Official Account"))
    DING_TALK = ("ding_talk", _("Ding Talk"))
    WEB = ("web", _("Web"))
    GITLAB = ("gitlab", _("GitLab"))
```

**system_mgmt/models/channel.py:**
```python
class ChannelChoices(models.TextChoices):
    EMAIL = "email", "Email"
    ENTERPRISE_WECHAT = "enterprise_wechat", "Enterprise Wechat"
    ENTERPRISE_WECHAT_BOT = "enterprise_wechat_bot", "Enterprise Wechat Bot"
    NATS = "nats", "NATS"
```

**Observation:** There are TWO separate `ChannelChoices` enums in different apps. The opspilot version is more comprehensive and includes DingTalk support.

### Workflow Execution Types (in `opspilot/enum.py`)
```python
class WorkFlowExecuteType(models.TextChoices):
    OPENAI = "openai", _("OpenAI")
    RESTFUL = "restful", _("RESTful")
    CELERY = "celery", _("Celery")
    ENTERPRISE_WECHAT = "enterprise_wechat", _("Enterprise WeChat")
    WECHAT_OFFICIAL_ACCOUNT = "wechat_official", _("WeChat Official Account")
    DINGTALK = "dingtalk", _("Ding Talk")
    EMBEDDED_CHAT = "embedded_chat", _("Embedded Chat")
    WEB_CHAT = "web_chat", _("Web Chat")
    MOBILE = "mobile", _("Mobile")
    AGUI = "agui", _("AG-UI")
```

---

## 2. Feishu/DingTalk References

### DingTalk Integration (Already Implemented)
The codebase shows comprehensive DingTalk support:

1. **Enum references:**
   - `opspilot/enum.py`: `DING_TALK` in `ChannelChoices` and `DINGTALK` in `WorkFlowExecuteType`

2. **Model encryption config** (`opspilot/models/bot_mgmt.py` - BotChannel class):
   ```python
   CHANNEL_ENCRYPT_CONFIG = {
       ChannelChoices.DING_TALK: {
           "key": "channels.dingtalk_channel.DingTalkChannel",
           "fields": ["client_secret"],
       },
       # ... other channels
   }
   ```

3. **Chat Flow utilities:**
   - `opspilot/utils/dingtalk_chat_flow_utils.py` - DingTalk-specific message handling
   - Functions: `handle_dingtalk_message()`, `_async_process_and_reply()`, signature verification

4. **Services:**
   - `opspilot/services/ding_talk_client.py` - DingTalk API client
   - `opspilot/services/channel_init_service.py` - Channel initialization with DingTalk defaults

5. **URL routing:**
   - `opspilot/urls.py`: endpoints for `/bot_mgmt/execute_chat_flow_dingtalk/<int:bot_id>/`

6. **Stream client support:**
   - DingTalk stream event handlers implemented
   - `dingtalk_stream` library integrated

### No Feishu/Lark References Found
- No existing Feishu implementation
- No Lark integration code

---

## 3. Channel Model Structure & Config Storage

### opspilot/models/bot_mgmt.py - BotChannel Model
```python
class BotChannel(models.Model, EncryptMixin):
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, verbose_name="机器人")
    name = models.CharField(max_length=100, verbose_name=_("name"))
    channel_type = models.CharField(max_length=100, choices=ChannelChoices.choices, 
                                   verbose_name=_("channel type"))
    channel_config = YAMLField(verbose_name=_("channel config"), blank=True, null=True)
    enabled = models.BooleanField(default=False, verbose_name=_("enabled"))
```

### Configuration Pattern
The `channel_config` is a YAMLField that stores nested configuration:

**Example from `channel_init_service.py`:**
```python
Channel.objects.get_or_create(
    name=ChannelChoices.DING_TALK.value,
    channel_type=ChannelChoices.DING_TALK,
    created_by=self.owner,
    defaults={
        "channel_config": {
            "channels.dingtalk_channel.DingTalkChannel": {
                "client_id": "",
                "client_secret": "",  # 加密 (encrypted)
                "enable_eventbus": False,
            }
        }
    },
)
```

### Configuration Storage Principle
1. **Nested structure:** Uses fully-qualified channel class path as the key
   - Pattern: `"channels.{platform}_channel.{ChannelClass}"`
   - Example: `"channels.dingtalk_channel.DingTalkChannel"`

2. **Encryption:** Sensitive fields (secrets, tokens) are automatically encrypted via `EncryptMixin`
   - Encrypted fields are configured per channel type in `CHANNEL_ENCRYPT_CONFIG`
   - `.decrypt_field()` and `.encrypt_field()` methods handle encryption/decryption

3. **YAML storage:** Uses `YAMLField` for flexible schema

---

## 4. Multiple Webhook/Channel Handling Patterns

### Pattern 1: Factory-Based Channel Initialization
**Location:** `opspilot/services/channel_init_service.py`

```python
class ChannelInitService:
    def __init__(self, owner):
        self.owner = owner
    
    def init(self):
        # For each channel type, create defaults with specific structure
        Channel.objects.get_or_create(
            name=ChannelChoices.ENTERPRISE_WECHAT.value,
            channel_type=ChannelChoices.ENTERPRISE_WECHAT,
            created_by=self.owner,
            defaults={
                "channel_config": {
                    "channels.enterprise_wechat_channel.EnterpriseWechatChannel": {
                        # channel-specific fields
                    }
                },
            },
        )
```

**Key principle:** Each channel type has:
- Unique enum value
- Unique config structure
- Unique fully-qualified class path in config

### Pattern 2: Abstraction-Based ChatFlow Utils
**Location:** `opspilot/utils/base_chat_flow_utils.py`

Abstract base class for all third-party channel ChatFlow execution:

```python
class BaseChatFlowUtils(ABC):
    """第三方渠道 ChatFlow 工具基类"""
    
    # Subclass-defined attributes
    channel_name: str = ""        # for logging
    channel_code: str = ""        # for input_data
    cache_key_prefix: str = ""    # for message deduplication
    
    def __init__(self, bot_id):
        self.bot_id = bot_id
    
    def validate_bot_and_workflow(self):
        """共通的验证逻辑"""
        # Bot validation
        # Workflow validation
        # Config validation
        return bot_chat_flow, error_response
    
    def execute_chatflow_with_message(self, bot_chat_flow, node_id, message, sender_id):
        """Execute ChatFlow with standardized input format"""
        engine = create_chat_flow_engine(bot_chat_flow, node_id)
        input_data = {
            "last_message": message,
            "user_id": sender_id,
            "bot_id": self.bot_id,
            "node_id": node_id,
            "channel": self.channel_code,
            "is_third_party": True,
        }
        return engine.execute(input_data)
```

### Concrete Implementations

**DingTalk (`opspilot/utils/dingtalk_chat_flow_utils.py`):**
```python
class DingTalkChatFlowUtils(object):  # Note: Does NOT inherit from BaseChatFlowUtils
    channel_name = "钉钉"
    
    def get_dingtalk_node_config(self, bot_chat_flow):
        """Extract DingTalk node config from flow"""
        # Find node type == "dingtalk"
        # Extract client_id, client_secret, etc.
        
    def verify_signature(self, timestamp, sign, app_secret):
        """Verify DingTalk signature (HMAC-SHA256)"""
        # DingTalk-specific signature validation
        
    def handle_dingtalk_message(self, request, bot_chat_flow, dingtalk_config):
        """Handle incoming DingTalk message"""
        # Verify signature
        # Deduplicate message
        # Execute ChatFlow asynchronously
```

**WeChat (`opspilot/utils/wechat_chat_flow_utils.py`):**
```python
class WechatChatFlowUtils(BaseChatFlowUt
