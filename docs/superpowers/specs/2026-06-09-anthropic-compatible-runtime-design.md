# Anthropic 兼容运行时统一设计

## 背景

当前 OpsPilot 对 `protocol_type=anthropic` 的支持实际上走了两条不同链路：

1. **测试连接**：通过 `ModelVendorSyncService.test_anthropic_connection()` 直接向 `POST /v1/messages` 发起 HTTP 请求。
2. **运行时对话**：通过 `LLMClientFactory` 将 Anthropic 协议模型路由到 `ChatAnthropic` 或原生 `anthropic` SDK。

在当前实际使用的 DeepSeek Anthropic 兼容配置上，同一份已落库凭据通过“测试连接”可以成功，但进入真实对话链路后会报 `401 invalid api key`。同一区域还存在第二个兼容性缺口：`node.py` 中 thinking 模式下的工具强制逻辑只检查 `llm.extra_body`，而 Anthropic 分支里的 DeepSeek thinking 配置并不放在这里。

这导致用户侧出现明显不一致：**测试连接通过，但真实对话失败**。

## 问题定义

当前实现默认把所有 `protocol_type=anthropic` 的供应商都当成同一类运行时目标，但实际上并不是：

- **原生 Anthropic 供应商** 可以直接使用 `ChatAnthropic` 的语义和调用方式。
- **Anthropic 兼容供应商**（例如 DeepSeek）虽然暴露了兼容的 messages 接口，但不一定能正确通过同一套 SDK 运行时路径工作。

目前代码仅通过 `protocol_type` 来表达兼容性，这个粒度过粗，结果是请求构造分叉、错误处理分叉，以及只有运行时才会暴露的问题，而测试连接接口无法提前发现。

## 目标

1. 让测试连接与运行时调用复用同一套 Anthropic 兼容请求适配规则。
2. 恢复当前 DeepSeek Anthropic 兼容模式下的真实对话能力。
3. 保留原生 Anthropic 供应商支持，不破坏现有协议抽象。
4. 集中管理 thinking、tool choice、请求组装、endpoint 规范化等兼容能力判断。
5. 为后续新增 Anthropic 兼容供应商提供清晰扩展点，避免重复在多个位置打补丁。

## 非目标

1. 不重构整个 OpenAI 兼容运行时链路。
2. 不改造与本问题无关的工具编排逻辑。
3. 不在本次变更里引入面向所有模型类型的通用 provider 框架。
4. 不在第一阶段解决所有未来可能出现的兼容厂商问题，首阶段只覆盖 DeepSeek 的 Anthropic 兼容场景。

## 方案选型

### 方案一：统一 Anthropic 兼容适配层

引入一个专门的 Anthropic 兼容请求适配层，让测试连接和运行时对话都依赖这层。原生 Anthropic 供应商仍可继续走 `ChatAnthropic`，而 DeepSeek 这类 Anthropic 兼容供应商改走共享适配层支撑的运行时路径。

**优点**

- 能从根上消除“测试通过、运行失败”的链路分叉。
- `base_url` 规范化、请求头组装、thinking 兼容、错误归一都可以集中处理。
- 为后续兼容厂商接入提供稳定扩展点。

**缺点**

- 需要对现有运行时路径做中等规模调整。
- 会新增一层内部抽象。

### 方案二：保留 `ChatAnthropic`，只在外围补参数

保留当前运行时结构，仅围绕 `ChatAnthropic`、`anthropic.Anthropic` 和 `node.py` 增加 DeepSeek 相关参数兼容。

**优点**

- 改动最小。
- 如果兼容问题非常集中，恢复速度最快。

**缺点**

- 测试链路和运行时链路仍然分裂。
- 厂商特例会继续散落在多个位置。
- 后续 SDK 升级时很容易再次回归。

### 方案三：Anthropic 运行时全部改为自定义原始 HTTP

完全绕过 `ChatAnthropic`，所有 Anthropic 协议相关调用都通过自定义 HTTP 请求完成。

**优点**

- 对请求头、payload、错误处理有最高控制力。
- 可以彻底规避 SDK 语义差异。

**缺点**

- 实现成本最高。
- 需要自行补齐流式、工具调用、消息转换等细节。
- 相比当前问题的范围，改动面过大。

## 决策

采用 **方案一**。

第一阶段引入 **Anthropic 兼容适配层**，并优先用于 DeepSeek Anthropic 兼容模式下的运行时对话与测试连接。原生 Anthropic 供应商暂时保留原生路径，除非后续证据表明也需要统一迁移。

这样既能控制改动范围，又能解决当前回归的根因。

## 设计方案

### 1. 运行时能力模型

新增一套针对 Anthropic 家族供应商的内部能力模型。能力判断不再只依赖 `protocol_type`，而是基于 `vendor_type + protocol_type` 共同推导。

首批能力项：

- `use_native_anthropic_sdk`
- `use_anthropic_compatible_adapter`
- `thinking_requires_auto_tool_choice`
- `supports_direct_messages_api`
- `requires_normalized_base_url`

第一阶段映射规则：

- `vendor_type=anthropic` -> 走原生 Anthropic SDK 路径
- `vendor_type=deepseek` 且 `protocol_type=anthropic` -> 走 Anthropic 兼容适配层路径
- 其他兼容厂商暂不调整，后续按明确需求扩展

这样可以避免在多个运行时调用点重复写 DeepSeek 特判。

### 2. Anthropic 兼容适配层

引入一个专门模块，负责：

- 规范化 `base_url`
- 组装鉴权请求头
- 构造 messages 请求体
- 应用 thinking 相关请求参数
- 将上游 API 错误映射为统一的运行时错误

这不是一个面向全局的 provider 框架，而是针对 Anthropic 兼容请求构造的聚焦型内部组件。

核心职责：

1. `normalize_base_url(api_base)`
2. `build_headers(api_key)`
3. `build_messages_payload(model, messages, system, temperature, max_tokens, thinking, tools, tool_choice)`
4. `invoke()` 与 `ainvoke()`，用于非流式与异步运行时调用
5. 如当前运行时需要，同阶段补充流式辅助能力

### 3. `ModelVendorSyncService` 统一

`test_anthropic_connection()` 不应继续手写自己的请求格式，而应改为调用新的适配层，以轻量校验模式复用与运行时一致的 URL 规范化、请求头与请求体构造逻辑。

这样可以保证：**测试连接成功，就代表同一供应商族在运行时链路上的最小消息请求形态也是成立的。**

期望行为：

- 测试连接成功，意味着同一适配器路径能够认证成功并发送合法的最小消息请求
- 测试连接失败时，返回统一、可读的用户错误，而不是暴露 SDK 私有异常细节

### 4. `LLMClientFactory` 路由调整

`LLMClientFactory` 不能再把所有 `protocol_type=anthropic` 的模型都统一交给 `ChatAnthropic`。

新的路由规则：

1. `protocol_type != anthropic` -> 维持现有 OpenAI 兼容路径
2. 原生 Anthropic 供应商 -> 维持 `ChatAnthropic` / 原生 Anthropic 路径
3. Anthropic 兼容供应商 -> 走适配层支撑的运行时客户端

适配层支撑的运行时客户端可以是一个很薄的包装类，只暴露当前 graph/runtime 真正需要的最小接口，不做过度抽象。它的目标是兼容当前对话执行流程，而不是变成一个通用框架。

### 5. Thinking 模式与 tool choice 兼容

`node.py` 当前只通过 `llm.extra_body` 判断是否需要把 `tool_choice=any|required` 降级成 `auto`。这对现有 OpenAI 兼容 DeepSeek/Qwen 逻辑成立，但对 Anthropic 兼容客户端无效。

这里需要改为读取运行时能力模型，而不是只看 `llm.extra_body`。

期望结果：

- 当当前运行时客户端声明 `thinking_requires_auto_tool_choice=True` 时，强制工具选择自动降级为 `auto`
- 无论底层客户端是 `ChatOpenAI`、`ChatAnthropic`，还是新的适配层客户端，逻辑都能成立

这样可以把 provider 兼容判断从响应体私有结构中抽出来。

### 6. 错误归一

Anthropic 系列运行时错误需要统一归类为少量内部错误类型：

- 鉴权失败
- endpoint 配置错误
- 请求参数不兼容 / 非法请求
- 上游服务异常

日志仍需保留足够上下文，包括：

- vendor type
- protocol type
- 规范化后的 base URL
- 实际选中的运行时路径
- capability flags

用户侧错误消息保持简洁且可执行。

## 数据流

### 测试连接链路

1. Viewset 校验请求参数，并解析提交的 API Key 或已保存的 API Key。
2. Service 计算供应商能力画像。
3. Anthropic 兼容适配层构造规范化请求。
4. 通过与运行时一致的路径发送最小 messages 请求。
5. 将结果映射为统一的成功或失败结果。

### 运行时对话链路

1. `ChatService` 根据选中的 `LLMModel` 构造 graph request。
2. `LLMClientFactory` 根据模型供应商解析能力画像。
3. 选择运行时路径：
   - 原生 Anthropic 供应商走原生路径
   - DeepSeek Anthropic 兼容供应商走适配层路径
4. `node.py` 基于能力标记应用 tool choice 兼容逻辑。
5. 实际消息调用与测试连接链路共用同一套规范化请求构造规则。

## 测试策略

本次变更必须使用 TDD 实施。

第一批 failing tests 应直接覆盖回归边界，而不是只验证零散 helper。

### 必须覆盖的测试场景

1. **测试连接与运行时共用同一适配层**
   - 证明 DeepSeek Anthropic 兼容模式下，测试连接不再走一套单独手写的 HTTP 请求形态

2. **DeepSeek Anthropic 兼容运行时不再使用 `ChatAnthropic`**
   - 证明 `LLMClientFactory` 会把 DeepSeek Anthropic 兼容模型路由到适配层客户端

3. **原生 Anthropic 供应商仍走原生路径**
   - 防止修复 DeepSeek 时误伤已有 Anthropic 能力

4. **Thinking 模式下强制 tool choice 会按能力标记降级**
   - 证明适配层客户端在 thinking 模式下会把 `tool_choice=any` 转成兼容值 `auto`

5. **鉴权失败会被统一映射**
   - 证明运行时返回的是统一的鉴权错误，而不是裸露的 client / SDK 异常

6. **最小请求构造一致**
   - 单测验证 DeepSeek Anthropic 兼容模式下的 URL、headers、payload 规范化结果

### 测试文件位置

优先扩展已有 Anthropic 协议测试文件：

- `server/apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py`

如果 runtime/node 相关测试继续堆叠会让该文件明显失焦，再按实际需要拆分，但不要为了“整洁”把本次回归拆散到很多无关测试集中。

## 推进计划

### 第一阶段

- 引入能力模型
- 引入 Anthropic 兼容适配层
- 将 DeepSeek Anthropic 兼容的运行时对话与测试连接切到适配层
- 将 tool choice 兼容逻辑改为读取能力标记
- 补齐回归测试

### 第二阶段

- 评估其他 Anthropic 兼容供应商是否也需要迁移到适配层
- 仅在有明确运行时证据时继续扩展能力映射

## 风险与缓解

### 风险一：适配层客户端与 graph 层期望接口不一致

**缓解措施：** 让适配层客户端保持最小接口面，只围绕当前 graph 执行路径真实使用的方法实现。

### 风险二：修复 DeepSeek 时影响原生 Anthropic

**缓解措施：** 保留原生 Anthropic 路由，并增加显式测试确保其继续走原生路径。

### 风险三：系统里仍残留其他隐性分叉链路

**缓解措施：** 让测试连接与运行时调用共同依赖同一个请求构造组件，并通过测试断言路由行为。

## 成功标准

当以下条件全部满足时，说明本设计达成目标：

1. DeepSeek Anthropic 兼容供应商在测试连接通过后，可以用同一份已保存凭据完成真实对话。
2. DeepSeek Anthropic 兼容运行时不再依赖 `ChatAnthropic`。
3. Anthropic 兼容 DeepSeek 路径在 thinking 模式下不会再因为 tool choice 强制策略导致兼容错误。
4. 原生 Anthropic 供应商能力保持可用。
5. 回归测试覆盖路由决策与请求规范化行为。
