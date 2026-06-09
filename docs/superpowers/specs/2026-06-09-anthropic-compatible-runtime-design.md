# Anthropic-Compatible Runtime Unification Design

## Background

OpsPilot currently supports `protocol_type=anthropic` in two different ways:

1. **Connection testing** uses `ModelVendorSyncService.test_anthropic_connection()` and sends a direct HTTP request to `POST /v1/messages`.
2. **Runtime chat** uses `LLMClientFactory` and routes Anthropically configured models through `ChatAnthropic` or the native `anthropic` SDK path.

For the active DeepSeek configuration in production-like data, the same stored credential succeeds through the direct HTTP test path but fails with `401 invalid api key` through the runtime SDK path. The same area also has a second compatibility gap: thinking-mode tool forcing in `node.py` only inspects `llm.extra_body`, while the Anthropic branch currently places DeepSeek thinking configuration in Anthropic-specific fields instead.

This creates a user-visible inconsistency: **test connection passes, real chat fails**.

## Problem Statement

The current implementation treats all `protocol_type=anthropic` vendors as if they were interchangeable at runtime, but they are not:

- **Native Anthropic vendors** can use `ChatAnthropic` semantics directly.
- **Anthropic-compatible vendors** such as DeepSeek expose a compatible messages endpoint but do not necessarily behave correctly through the same SDK path.

The codebase currently encodes compatibility through `protocol_type` alone. That is too coarse. The result is split request construction, split error behavior, and runtime-only regressions that the test-connection API cannot catch.

## Goals

1. Make test connection and runtime invocation use the same Anthropic-compatible request adaptation rules.
2. Restore DeepSeek Anthropic-compatible chat execution for the current runtime path.
3. Keep native Anthropic vendors supported without regressing the existing protocol abstraction.
4. Centralize capability decisions for thinking mode, tool choice, request shaping, and endpoint normalization.
5. Make future Anthropic-compatible vendors easier to add without repeating vendor-specific fixes in multiple places.

## Non-Goals

1. Reworking the entire OpenAI-compatible runtime path.
2. Refactoring unrelated tool orchestration logic.
3. Introducing a universal provider abstraction across every model type in this change.
4. Solving every future vendor incompatibility in phase one. The first implementation target is DeepSeek under Anthropic-compatible mode.

## Options Considered

### Option 1: Unified Anthropic-compatible adapter layer

Introduce a dedicated adapter layer for Anthropic-compatible message requests. Connection testing and runtime chat both depend on the same adapter. Native Anthropic vendors may still use `ChatAnthropic`, but Anthropic-compatible vendors such as DeepSeek use the shared adapter-backed runtime path.

**Pros**

- Fixes the root inconsistency between test and runtime.
- Creates one place for base URL normalization, headers, thinking compatibility, and error mapping.
- Gives a safe extension point for future compatible vendors.

**Cons**

- Requires moderate refactoring in the runtime path.
- Introduces one more internal abstraction.

### Option 2: Keep `ChatAnthropic`, patch parameters around it

Retain the current runtime architecture and add vendor-specific parameter tweaks around `ChatAnthropic`, `anthropic.Anthropic`, and `node.py`.

**Pros**

- Smallest code change.
- Fastest short-term recovery if the incompatibility is narrow.

**Cons**

- Keeps test and runtime split.
- Vendor-specific fixes remain scattered.
- High chance of another regression when SDK versions change again.

### Option 3: Replace Anthropic runtime with custom raw HTTP end-to-end

Bypass `ChatAnthropic` entirely for all Anthropic protocol traffic and implement runtime requests directly over HTTP.

**Pros**

- Maximum control over payloads and headers.
- Removes SDK ambiguity.

**Cons**

- Highest implementation cost.
- Requires rebuilding streaming and tool-calling integration details.
- Larger regression surface than needed for this issue.

## Decision

Adopt **Option 1**.

Phase one will introduce a **unified Anthropic-compatible adapter** and use it for DeepSeek Anthropic-compatible runtime traffic plus connection testing. Native Anthropic vendors will remain on the native path unless evidence shows they should also move behind the adapter.

This keeps the scope tight while addressing the architectural cause of the regression.

## Proposed Design

### 1. Runtime capability model

Add an internal capability model for Anthropic-family vendors. The capability model is derived from vendor type plus protocol type, not protocol type alone.

Initial capabilities:

- `use_native_anthropic_sdk`
- `use_anthropic_compatible_adapter`
- `thinking_requires_auto_tool_choice`
- `supports_direct_messages_api`
- `requires_normalized_base_url`

Phase one mapping:

- `vendor_type=anthropic` -> native Anthropic SDK path
- `vendor_type=deepseek` + `protocol_type=anthropic` -> Anthropic-compatible adapter path
- other compatible vendors remain unchanged until explicitly added

This avoids embedding DeepSeek-specific branching in every runtime call site.

### 2. Anthropic-compatible adapter

Introduce a dedicated adapter module responsible for:

- normalizing the base URL
- building request headers
- constructing messages payloads
- applying thinking-related request options
- translating API failures into normalized runtime errors

The adapter is not a global provider framework. It is a focused internal component for Anthropic-compatible request construction.

Core responsibilities:

1. `normalize_base_url(api_base)`
2. `build_headers(api_key)`
3. `build_messages_payload(model, messages, system, temperature, max_tokens, thinking, tools, tool_choice)`
4. `invoke()` and `ainvoke()` for non-streaming and async runtime usage
5. optional streaming helper if the existing runtime path requires streamed message handling in the same phase

### 3. `ModelVendorSyncService` unification

`test_anthropic_connection()` must stop hand-authoring its own request shape. Instead, it should call the new adapter in a lightweight validation mode using the same normalized URL, headers, and model request path that runtime invocation uses.

This guarantees that a passing connection test proves the runtime request shape is valid for the same vendor family.

Expected behavior:

- connection test success means the same adapter path can authenticate and send a valid minimal message request
- connection test failure returns a normalized, user-facing error instead of leaking raw SDK-specific behavior

### 4. `LLMClientFactory` routing changes

`LLMClientFactory` must stop routing all Anthropically configured models through `ChatAnthropic`.

New routing rules:

1. `protocol_type != anthropic` -> existing OpenAI-compatible path unchanged
2. native Anthropic vendor -> existing `ChatAnthropic` / native Anthropic path
3. Anthropic-compatible vendor -> adapter-backed runtime client

The adapter-backed runtime client can be a thin class that exposes the minimum interface required by the current graph/runtime integration. The class should focus on compatibility with the existing chat execution flow rather than broad reuse.

### 5. Thinking-mode and tool-choice compatibility

`node.py` currently converts forced `tool_choice=any|required` to `auto` only by checking `llm.extra_body`. That is correct for current OpenAI-compatible DeepSeek/Qwen handling, but it misses Anthropic-compatible clients.

Update the logic to consult the runtime capability model instead of only `llm.extra_body`.

Required result:

- if the active runtime client reports `thinking_requires_auto_tool_choice=True`, forced tool choice is downgraded to `auto`
- this works regardless of whether the underlying client is `ChatOpenAI`, `ChatAnthropic`, or the new adapter-backed client

This keeps provider compatibility logic out of response-body internals.

### 6. Error normalization

Anthropic-family runtime failures should be normalized into a small set of internal categories:

- authentication failure
- endpoint configuration failure
- invalid request / incompatible payload
- upstream service error

Logging should still preserve detailed upstream context, including:

- vendor type
- protocol type
- normalized base URL
- runtime path selected
- capability flags

User-facing error messages should remain concise and actionable.

## Data Flow

### Connection test flow

1. Viewset validates payload and resolves stored or submitted API key.
2. Service resolves vendor capability profile.
3. Anthropic-compatible adapter builds normalized request.
4. Minimal messages request is sent through the same path runtime would use.
5. Result is mapped to normalized success or error.

### Runtime chat flow

1. `ChatService` builds the graph request from the selected `LLMModel`.
2. `LLMClientFactory` resolves capability profile from model vendor.
3. Runtime path is chosen:
   - native Anthropic path for real Anthropic vendors
   - adapter-backed path for DeepSeek Anthropic-compatible vendors
4. `node.py` applies tool-choice compatibility using capability flags.
5. Message invocation uses the same normalized request construction rules as the connection test flow.

## Testing Strategy

This change should be implemented with TDD.

The first failing tests should cover the regression boundary, not just helper methods.

### Required test cases

1. **Connection test and runtime share the same adapter path**
   - prove that DeepSeek Anthropic-compatible connection testing no longer uses a separate handwritten HTTP shape

2. **DeepSeek Anthropic-compatible runtime avoids `ChatAnthropic`**
   - prove that `LLMClientFactory` routes DeepSeek Anthropic-compatible models to the adapter-backed client

3. **Native Anthropic vendors still use the native path**
   - protect existing Anthropic behavior from regression

4. **Thinking mode downgrades forced tool choice through capability flags**
   - prove that `tool_choice=any` becomes `auto` for adapter-backed thinking clients

5. **Authentication failures are normalized**
   - prove that the runtime path returns normalized authentication errors instead of raw client-specific exceptions

6. **Minimal live request construction is consistent**
   - unit-test normalized URL, headers, and payload shape for DeepSeek Anthropic-compatible vendors

### Test location

Extend existing Anthropic protocol coverage in:

- `server/apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py`

Add focused tests near runtime/node behavior only if the existing file becomes overloaded. Do not spread the regression across unrelated suites unless a specific call site requires it.

## Rollout Plan

### Phase 1

- Introduce capability model
- Introduce Anthropic-compatible adapter
- Route DeepSeek Anthropic-compatible runtime and connection testing through the adapter
- Update tool-choice compatibility logic to use capabilities
- Add regression tests

### Phase 2

- Evaluate whether other Anthropic-compatible vendors should also move behind the adapter
- Expand capability mapping only with proven runtime requirements

## Risks and Mitigations

### Risk: adapter-backed runtime does not match the interface expected by the graph layer

**Mitigation:** keep the adapter-backed client narrow and shaped around the specific methods currently used by the graph execution path.

### Risk: native Anthropic behavior regresses while fixing DeepSeek

**Mitigation:** retain native Anthropic routing and add explicit tests proving it remains on the native path.

### Risk: another split path remains hidden

**Mitigation:** make connection testing and runtime invocation depend on the same request-construction component, and add tests that assert the routing behavior.

## Success Criteria

This design is successful when all of the following are true:

1. A DeepSeek Anthropic-compatible vendor that passes connection testing can also execute runtime chat through the same stored credentials.
2. The runtime path no longer depends on `ChatAnthropic` for DeepSeek Anthropic-compatible vendors.
3. Thinking-mode tool forcing no longer causes compatibility failures for the Anthropic-compatible DeepSeek path.
4. Native Anthropic vendors remain supported.
5. Regression tests cover both routing and request normalization behavior.
