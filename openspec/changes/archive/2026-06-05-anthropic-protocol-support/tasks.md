## 1. 后端依赖与数据模型

- [x] 1.1 在 `server/pyproject.toml` 中添加 `langchain-anthropic` 依赖
- [x] 1.2 在 `server/apps/opspilot/models/model_provider_mgmt.py` 中添加 `PROTOCOL_TYPE_CHOICES` 常量和 `ModelVendor.protocol_type` 字段
- [x] 1.3 生成并应用数据库迁移文件，确保 `protocol_type` 字段默认值为 `"openai"`

## 2. 协议类型推导与传递

- [x] 2.1 在 `server/apps/opspilot/models/model_provider_mgmt.py` 的 `LLMModel` 中添加 `protocol_type` 属性，根据 `vendor.vendor_type` 和 `vendor.protocol_type` 推导协议类型
- [x] 2.2 在 `server/apps/opspilot/metis/llm/chain/entity.py` 的 `BasicLLMRequest` 中添加 `protocol_type` 字段
- [x] 2.3 更新所有构造 `BasicLLMRequest` 的调用点，传递 `protocol_type` 参数

## 3. LLM 客户端工厂改造

- [x] 3.1 在 `server/apps/opspilot/metis/llm/common/llm_client_factory.py` 中导入 `ChatAnthropic`
- [x] 3.2 修改 `LLMClientFactory.create_client()` 方法，根据 `protocol_type` 创建 `ChatAnthropic` 或 `ChatOpenAI` 客户端
- [x] 3.3 修改 `LLMClientFactory.create_isolated_client()` 方法，支持 Anthropic 原生客户端创建

## 4. 模型同步服务适配

- [x] 4.1 在 `server/apps/opspilot/services/model_vendor_sync_service.py` 中添加 `ANTHROPIC_COMPATIBLE_VENDOR_TYPES` 常量
- [x] 4.2 实现 `fetch_anthropic_models()` 方法，尝试调用 Anthropic `/v1/models` API
- [x] 4.3 修改 `sync_vendor_models()` 方法，根据协议类型选择对应的模型获取逻辑
- [x] 4.4 当 Anthropic API 不可用时，返回友好提示而非抛出异常

## 5. 序列化器与视图适配

- [x] 5.1 在 `server/apps/opspilot/serializers/model_vendor_serializer.py` 的 `ModelVendorSerializer` 中添加 `protocol_type` 字段
- [x] 5.2 更新 `ModelVendorTestConnectionSerializer`，支持 Anthropic 协议的连接测试
- [x] 5.3 修改 `server/apps/opspilot/viewsets/model_vendor_view.py` 的 `test_connection` 方法，根据协议类型选择测试逻辑

## 6. 错误处理适配

- [x] 6.1 在 `server/apps/opspilot/utils/agent_factory.py` 的 `normalize_llm_error_message()` 中添加 Anthropic 错误码映射

## 7. 前端类型定义

- [x] 7.1 在 `web/src/app/opspilot/types/provider.ts` 中添加 `ProtocolType` 类型定义
- [x] 7.2 在 `ModelVendor` 和 `ModelVendorPayload` 接口中添加 `protocol_type` 字段

## 8. 前端常量与配置

- [x] 8.1 在 `web/src/app/opspilot/constants/provider.ts` 中添加 `PROTOCOL_TYPE_OPTIONS` 常量
- [x] 8.2 添加 `getDefaultProtocolType(vendorType)` 辅助函数，返回供应商类型对应的默认协议

## 9. 前端 UI 改造

- [x] 9.1 在 `web/src/app/opspilot/components/provider/vendorModal.tsx` 中添加协议类型选择 UI
- [x] 9.2 实现协议选择仅在 `vendor_type === 'other'` 时显示的逻辑
- [x] 9.3 当协议类型切换时，自动更新默认 API 地址（OpenAI 清空，Anthropic 填充官方地址）

## 10. 国际化

- [x] 10.1 在 `web/src/app/opspilot/locales/zh.json` 中添加协议相关的中文翻译（`provider.vendor.protocolType`, `provider.vendor.protocolTypeRequired`）
- [x] 10.2 在 `web/src/app/opspilot/locales/en.json` 中添加协议相关的英文翻译（`provider.vendor.protocolType`, `provider.vendor.protocolTypeRequired`）

## 11. 验证

- [x] 11.1 执行 `cd server && make test` 确认后端测试通过
- [x] 11.2 执行 `cd web && pnpm lint && pnpm type-check` 确认前端静态检查通过
- [x] 11.3 手动测试：创建 Anthropic 供应商，验证连接测试和模型调用正常
- [x] 11.4 手动测试：创建 "其他" 供应商并选择 Anthropic 协议，验证调用正常
