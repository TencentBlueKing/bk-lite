## Why

LLMSkill 的 `skill_prompt` 中经常需要包含敏感信息（如 browser_use 工具登录网站的账号密码）。当前只能明文写在 prompt 里，存在泄露风险：API 返回、日志、前端展示都会暴露原始凭据。需要一种参数化机制，让用户定义变量并对敏感值加密存储，执行时再替换为真实值。

## What Changes

- LLMSkill 模型新增 `skill_params` JSONField，存储参数列表，每项包含 `key`、`value`、`type`（text/password）
- `type=password` 的参数值使用 `EncryptMixin` 加密存储
- API 读取时，`type=password` 的值返回 `"******"` 掩码，不暴露真实值和密文
- API 更新时，若 `type=password` 且 `value=="******"`，保留 DB 中原有加密值
- 执行时（直接调用 + 工作流 AgentNode），解密参数并将 `skill_prompt` 中的 `{{key}}` 替换为真实值，替换发生在 prompt 进入模板引擎之前
- 意图分类节点（IntentClassifierNode）不受影响——它不使用 LLMSkill，直接选模型和写 prompt

## Capabilities

### New Capabilities
- `skill-prompt-params`: LLMSkill 的 prompt 参数化能力——参数定义、加密存储、掩码读取、执行时替换

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

- **Model**: `server/apps/opspilot/models/model_provider_mgmt.py` — LLMSkill 新增字段 + migration
- **Serializer**: `server/apps/opspilot/serializers/llm_serializer.py` — 读取时掩码 password 值
- **View**: `server/apps/opspilot/viewsets/llm_view.py` — create/update 时加密处理 + "******" 保留逻辑
- **Execution (直接)**: `server/apps/opspilot/services/chat_service.py` — 解密 + `{{key}}` 替换
- **Execution (工作流)**: `server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py` — AgentNode 读取 skill_params 并替换
- **API**: LLMSkill 的 CRUD + execute 接口均受影响
- **DB**: 新增一次 Django migration
