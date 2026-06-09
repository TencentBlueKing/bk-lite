# Tech Debt Audit — OpsPilot (`server/apps/opspilot`)

Generated: 2026-06-09
Scope: the OpsPilot Django app only (93,228 LOC across 455 Python files). Audit performed by reading the high-churn × high-size hotspots and dispatching six parallel module audits (chain engine, tools/agent/rag, API layer, services/tasks, chat-flow engine, data layer + tooling). Every finding below was produced from reading the code; the top‑severity security findings were independently re-verified against source.

---

## Executive summary (ranked by impact)

1. **Unauthenticated file exfiltration.** `download_workflow_attachment` is `@api_exempt` and serves any file by a single `download_token` with no auth, ownership check, or expiry (`views.py:112`). A leaked/guessed token streams arbitrary uploaded attachments.
2. **Cross-tenant IDOR on the bespoke knowledge `@action` batch endpoints.** `batch_train`, `batch_delete`, and `delete_chunks` query `KnowledgeDocument`/`QAPairs`/ES directly by ids from `request.data`, bypassing the team-scoped `get_queryset()` the rest of the viewset relies on (`knowledge_document_view.py:108, 327, 298`). RBAC gates *that* the caller may train/delete, not *which* tenant's objects.
3. **Channel secrets stored in plaintext.** `Channel` inherits `EncryptMixin` but — unlike `BotChannel` (`bot_mgmt.py:130`) — has no `save()` override, so `channel_config` (tokens, AES keys) is written unencrypted (`channel_mgmt.py:10`), and `ChannelSerializer`/`BotSerializer` (`fields="__all__"`) return those secrets and `api_token` in responses.
4. **SQL tool guard is a bypassable blacklist.** postgres/mssql/mysql/oracle `dynamic.py` authorize LLM-generated SQL by keyword denylist over the raw string; MSSQL sets no read-only transaction at all, and `USE [{database}]` interpolates an unvalidated identifier (`postgres/dynamic.py:12`, `mssql/dynamic.py:24,684`). The real guard must be a least-privilege DB role.
5. **SSRF across multiple surfaces.** The headless browser tool has no SSRF guard (`browser_use/browser_tool.py:290`) while the fetch tool does; `get_mcp_tools` and the `test_*_connection` actions open connections to arbitrary host:port from the request body (`llm_view.py:635, 701`).
6. **Celery tasks report success while their work failed.** `general_embed`, `create_qa_pairs`, and the embed batch swallow per-item exceptions and never propagate aggregate failure, so a fully-failed training batch looks green to any task-state monitoring (`tasks.py:200, 480, 216`).
7. **Four god files concentrate the churn.** `metis/llm/chain/node.py` (3,777 LOC, 42 edits/6mo), `chat_flow_utils/engine/engine.py` (1,881 LOC, 28 edits), `tasks.py` (1,570 LOC), `tools/browser_use/browser_tool.py` (1,750 LOC). These are where every change lands and where bugs hide.
8. **Data races in the chat-flow engine.** `_execute_subsequent_nodes_async` spawns a detached daemon thread that mutates shared engine state with no lock while the SSE generator is still running (`engine.py:1074`); `_execute_parallel_nodes` shares one unlocked `variable_manager` dict across thread-pool branches (`engine.py:1703`).
9. **The runtime contract is untyped dicts everywhere.** The chat request (`chat_service.py:56`), the node I/O contract (`base_executor.py:40`), `extra_config` (`entity.py:335`), and tool_calls (17× dual dict/attr access in `node.py`) are all loose dicts with in-band success flags — unvalidatable and the source of deep KeyErrors.
10. **Hardcoded developer path in the hot agent loop.** `/Users/qiu/projects/bk-lite/logs/choice_debug.log` is opened for append on every agent step inside `agent_node`, guarded by bare `except` (`node.py:2451, 2806`) — leaks the author's username and does pointless blocking syscalls in production.

Counts: ~12 Critical, ~24 High, ~38 Medium, ~22 Low across the table below.

---

## Architectural mental model

OpsPilot is the AI-assistant app of BK-Lite: it manages knowledge bases (RAG), bots/skills, model providers, and visual "chat flows," and exposes both OpenAI-compatible completion endpoints and an AGUI streaming protocol. Four layers:

- **API layer** (`views.py`, `viewsets/`, `urls.py`, `nats_api.py`) — DRF viewsets for CRUD (Bot/LLM/Vendor/Knowledge) plus a set of hand-rolled function views and custom `@action`s for the chat/skill/approval entrypoints. Standard CRUD is team-scoped via `AuthViewSet`/`GenericViewSetFun`; the bespoke function views (`@api_exempt`) and batch `@action`s are where the access-control holes are.
- **Service layer** (`services/`, `tasks.py`) — `ChatService` orchestrates RAG + tools + the engine; `tasks.py` holds Celery jobs for embedding/training, channel message handling (DingTalk/WeChat/Enterprise WeChat), and a batch "memory write" subsystem. Business logic is split unevenly between services, views, and tasks.
- **Chat-flow engine** (`utils/chat_flow_utils/engine/`) — `ChatFlowEngine` parses a node/edge graph and executes it two ways: a synchronous recursive walker and an async SSE generator, with a third detached-thread "subsequent nodes" path. Nodes (agent, intent, http, branch, memory, action) implement an untyped dict→dict `execute`.
- **Metis LLM engine** (`metis/llm/`, 49k LOC, half the app) — the LangGraph/LangChain ReAct engine (`chain/node.py`, `chain/graph.py`), a large catalog of agent tools (kubernetes, postgres, mssql, mysql, oracle, redis, browser-use, python-exec, fetch), the RAG implementations (pgvector), and specialized agents (LATS, supervisor-multi-agent). The chain engine is heavily specialized toward a Kubernetes config-analysis/auto-repair use case, with K8s domain logic embedded throughout the "generic" ReAct nodes.

**Where the model contradicts appearances:** the project README frames metis as a generic LLM toolbox, but `chain/node.py` is shot through with hardcoded Kubernetes repair knowledge (kubectl command generation, YAML patches, issue-keyword ladders) that is bound to *every* agent regardless of whether it has K8s tools. The "generic ReAct engine" is really a K8s-remediation engine with a generic skin. That coupling — not file size alone — is the deepest architectural debt here.

---

## Findings

| ID | Category | File:Line | Severity | Effort | Description | Recommendation |
|----|----------|-----------|----------|--------|-------------|----------------|
| F001 | Security/Auth | views.py:112 | Critical | S | `download_workflow_attachment` is `@api_exempt`, serves any file by `download_token` with no auth/ownership/expiry | Require auth or a signed, expiring token bound to the requesting user/bot |
| F002 | Security/IDOR | knowledge_document_view.py:108 | Critical | M | `batch_train` does `KnowledgeDocument.objects.filter(id__in=...)` from `request.data`, bypassing team-scoped `get_queryset()` | Resolve ids through `self.get_queryset()` before update/embed |
| F003 | Security/IDOR | knowledge_document_view.py:327 | Critical | M | `batch_delete` deletes documents/QAPairs/ES content by raw `doc_ids`+`knowledge_base_id`, no ownership validation | Verify each id belongs to the user's `current_team` before delete |
| F004 | Security/IDOR | knowledge_document_view.py:298 | Critical | M | `delete_chunks` deletes ES chunks by arbitrary `params["ids"]` with no scoping to an owned document | Resolve chunk ids to documents, verify team ownership first |
| F005 | Security/Secrets | channel_mgmt.py:10 | Critical | S | `Channel` inherits `EncryptMixin` but has no `save()` override (unlike `BotChannel`), so `channel_config` secrets are stored plaintext | Add the same encrypt-on-save logic as `BotChannel`, or share a base mixin |
| F006 | Security/Secrets | channel_serializer.py:5 | Critical | S | `ChannelSerializer` `fields="__all__"` returns raw `channel_config` (secrets) in API responses, no masking | Make `channel_config` write-only or mask in `to_representation` |
| F007 | Security/SQLi-authz | postgres/dynamic.py:12 / mssql/dynamic.py:24 | Critical | M | LLM-SQL safety is a bypassable keyword blacklist over the raw string; the real protection should be the DB role | Enforce a least-privilege read-only DB login; treat blacklist as defense-in-depth only |
| F008 | Security/SQLi | mssql/dynamic.py:684 / mssql/utils.py:185 | Critical | S | `conn.execute(f"USE [{database}]")` interpolates LLM-supplied `database`; a `]` breaks out of bracket quoting | Validate `database` against `^[A-Za-z0-9_]+$` or escape `]`→`]]` |
| F009 | Security/SSRF | browser_use/browser_tool.py:290 | Critical | M | `_validate_url` checks only scheme/netloc — no SSRF guard, unlike the fetch tool's `SSRFValidator`; reaches cloud metadata (169.254.169.254) | Route browser URLs through the same `SSRFValidator`, blocking private/link-local/metadata IPs incl. post-redirect |
| F010 | Error handling | tasks.py:216 / tasks.py:200 | Critical | M | `general_embed_by_document_list` swallows per-doc exceptions; wrapping tasks have no retry and always return success even when `has_failure` | Propagate aggregate failure (raise/ set FAILURE state) so retries/alerting fire |
| F011 | Error handling | tasks.py:480 | Critical | M | `create_qa_pairs` marks items failed but never re-raises and always runs `task_obj.delete()`, so a fully-failed task reports success | Track failure count; mark task FAILURE and don't delete tracking on failure |
| F012 | Security/Observability | node.py:2451 | Critical | S | Hardcoded `/Users/qiu/projects/...choice_debug.log` opened for append every agent step, bare `except`; leaks username, blocking syscalls in prod (also 2806, 2814, 2823) | Delete all four debug-file blocks; use `logger.debug` if tracing is needed |
| F013 | Concurrency | chat_flow_utils/engine/engine.py:1074 | Critical | M | `_execute_subsequent_nodes_async` spawns a detached daemon thread mutating shared `variable_manager`/`execution_contexts` while the SSE generator still runs — data race | Await subsequent nodes inside the generator, or isolate state + add a lock |
| F014 | Security/Auth | views.py:436 / views.py:675 | High | S | `skill_execute` `@api_exempt` and `interrupt_chat_flow_execution` mutate `WorkFlowTaskResult` after only token validation, no team scoping on `execution_id` | Bind `execution_id` to the user/team before mutating |
| F015 | Security/SSRF | llm_view.py:635 | High | S | `get_mcp_tools` fetches an arbitrary user-supplied `server_url` server-side, no allowlist | Validate/allowlist target hosts; block private ranges |
| F016 | Security/SSRF | llm_view.py:701 | High | S | `test_*_connection` actions open connections to arbitrary host:port from `request.data` — internal port scanning | Restrict to configured instances or allowlist hosts |
| F017 | Security/Mass-assign | llm_view.py:99 | High | M | `LLMViewSet.create/update` do `setattr(instance, key, params[key])` over raw `request.data` — mass-assignment | Write through serializer `validated_data`, whitelist fields |
| F018 | Security/Mass-assign | bot_view.py:127 | High | M | `BotViewSet.update` does `for key in data: setattr(obj, key, data[key])` — can set `team`/`created_by`/`api_token` | Use the serializer; whitelist updatable fields |
| F019 | Security/Secrets | bot_serializer.py:26 | High | S | `BotSerializer` `fields="__all__"` exposes `Bot.api_token` in responses | Mark `api_token` write-only or mask |
| F020 | Security/Auth | views.py:89 | High | S | `get_bot_detail` `@api_exempt` returns `decrypted_channel_config` for any matching `api_token`, no rate limit — brute-force exposes channel creds | Add throttling; avoid returning decrypted secrets over this endpoint |
| F021 | Security/Auth | views.py:592 | High | M | `execute_chat_flow` mobile branch drops `team__contains`, scoping a bot by `id` only — UA-string is trivially spoofable tenant bypass | Scope mobile requests by verified user team, not UA |
| F022 | Security | kubernetes/remediation.py:518 | High | M | `delete_kubernetes_resource`/`scale_deployment`/`restart_pod`/`rollback_deployment` mutate the cluster with no human-approval gate; prompt injection can delete Deployments/Secrets | Gate write/delete K8s tools behind explicit approval + namespace allow-list |
| F023 | Security | redis/server_management.py:330 | High | M | `redis_flushdb` exposes a whole-DB wipe gated only by a `confirm: bool` the LLM itself supplies | Require out-of-band human confirmation; disable destructive ops by default |
| F024 | Architecture | metis/llm/chain/node.py:1 | High | L | 3,777-LOC god file mixing LC monkey-patches, RAG nodes, K8s HTML/YAML report generation, and the generic ReAct engine (`build_react_nodes` ~1,400 LOC) | Split into `react_engine.py`, `k8s_report_tools.py`, `lc_patches.py`, `rag_nodes.py` |
| F025 | Architecture | metis/llm/chain/node.py:2613 | High | M | Hardcoded K8s-domain prompt-steering (keyword sets, synthesized tool_calls) embedded in the "generic" ReAct engine and bound to every agent | Extract a pluggable `ChoiceContinuationPolicy` strategy injected via config |
| F026 | Architecture | utils/chat_flow_utils/engine/engine.py:1 | High | L | `ChatFlowEngine` is an 1,881-LOC god class: parse, topology, two exec models, DB persistence, history, SSE building, ~40 methods | Split into FlowGraph / NodeRunner / ExecutionRecorder / SSEResponder |
| F027 | Architecture | tasks.py:1351 | High | M | `process_memory_write` ~210-line god function; create-or-append block copy-pasted twice (1411-1439) | Extract `_find_existing_memory`/`_create_or_append`/`_llm_merge` |
| F028 | Architecture | postgres/dynamic.py + mssql/dynamic.py | High | M | `validate_sql_safety`, sensitive-column lists, `execute_safe_select*` near-duplicated across 4 SQL dialects with divergent keyword lists — one dialect gets a fix the others miss | Extract a shared dialect-parameterized SQL-guard module |
| F029 | Concurrency | engine.py:1703 | High | S | `_execute_parallel_nodes` shares one unlocked `variable_manager` dict across thread-pool branches; parallel nodes clobber `last_message`/`memory_context` | Per-branch variable scope, or lock `set_variable` |
| F030 | Type/Contract | chat_service.py:56 | High | M | `ChatService.chat/invoke_chat` take untyped `kwargs: Dict[str,Any]`, ~20 keys via mixed `[]`/`.get()`; missing key raises KeyError deep in the stack | Introduce a typed pydantic/dataclass chat-request object |
| F031 | Type/Contract | engine/core/base_executor.py:40 | High | M | Node I/O contract is untyped `Dict[str,Any]` with in-band `{"success": False}` checked inconsistently (`engine.py:1558` vs `1487`) | Define a `NodeResult` dataclass with `ok`/`output`/`error`/`route` |
| F032 | Error handling | graph.py:1202 | High | M | `execute()` catches `BaseException` and re-wraps as `RuntimeError`, swallowing `CancelledError`/`KeyboardInterrupt` — breaks task cancellation/timeout | Catch `Exception`; re-raise `CancelledError` untouched |
| F033 | Error handling | engine.py:1051 / engine.py:1027 | High | S | Background subsequent-node loop `continue`s past any node exception; failure never reaches the already-closed SSE stream — client thinks it succeeded | Emit a terminal error event before closing, or block finalization on completion |
| F034 | Performance | node.py:635 / node.py:1011 | High | S | `naive_rag_node`/`user_message_node` are async but call synchronous blocking `PgvectorRag().search()` and `invoke_isolated` (LLM HTTP) — blocks the event loop | Wrap in `asyncio.to_thread` or use async variants |
| F035 | Performance | tasks.py:235 | High | M | `general_embed_by_document_list` calls `refresh_from_db()` + `task_obj.save()` per item and re-queries knowledge subtype per doc — N+1 | Batch progress updates; prefetch knowledge subtype records |
| F036 | Performance | tasks.py:803 / tasks.py:764 | High | M | `_ingest_qa_with_retry` does `time.sleep(5)` inside a per-QA loop, serializing/stalling the worker on transient failures | Use Celery `self.retry`/backoff; never sleep in a tight per-item loop |
| F037 | Performance | browser_use/browser_tool.py:1009 | High | S | tenacity `retry` re-runs side-effecting browser automation (form submits/clicks) up to MAX_RETRIES on generic `Exception` | Restrict retry to transient connection errors |
| F038 | Performance | postgres/dynamic.py:754 / mssql/dynamic.py:680 | High | M | Synchronous psycopg2/pyodbc connect+query+close run from async agent graphs, new connection per query, no pooling | Wrap in `asyncio.to_thread`; reuse a pooled connection across the batch |
| F039 | Architecture | node.py:1697 / node.py:248 / node.py:2069 | High | M | K8s "fix command" knowledge triplicated across 3 functions, each string-matching the same Chinese issue keywords; adding an issue means editing 6+ ladders | Build one issue-type registry; renderers read from it |
| F040 | Test debt | views.py (915 LOC) | High | M | No tests cover `openai_completions`/`skill_execute`/`execute_chat_flow`/`submit_approval`/`get_bot_detail`/`download_workflow_attachment` — high-churn auth-bearing entrypoints | Add request-level tests for token validation, scoping, stream/non-stream |
| F041 | Test debt | viewsets/llm_view.py:99 | High | M | `LLMViewSet` create/update/execute (heavy churn, mass-assignment, permission branches) have no direct viewset tests | Add tests for permission denial, name-uniqueness, password masking, skill scoping |
| F042 | Error handling | nats_api.py:118 | High | S | `consume_bot_event` wraps the whole body in `try/except Exception` and only logs — silent loss of conversation history | Narrow the except or return an error so the NATS caller can react |
| F043 | Security/Auth | model_provider_mgmt.py:32 | High | M | `ModelVendor.api_key` encrypted only via `save()` round-trip; `.update()`/bulk writes persist plaintext | Use a dedicated encrypted-field type or add an `_is_encrypted` guard like `MemorySpace` |
| F044 | Performance | engine.py:511 / engine.py:380 | High | M | Async SSE path runs synchronous prerequisite-node execution + ORM on the request thread before first flush — delays TTFB | Move prerequisite execution inside the generator or `sync_to_async` |
| F045 | Correctness | engine/node_registry.py:43 / nodes/agent/agent.py:20 | High | S | `AgentNode`/`IntentClassifierNode` accept `workflow_instance`, but the factory (`engine.py:1758`) never passes it, so it's always `None` — dead, unwired dependency | Wire it through or delete the parameter |
| F046 | Error handling | postgres/dynamic.py:771 / mssql/dynamic.py:695 | High | S | Per-query `except Exception` returns `{"error": str(e)}`; raw DB error strings (can include host/params) surfaced to the LLM/user | Catch specific errors, log server-side, return sanitized message |
| F047 | Security/Auth | views.py:493 | Medium | S | Analytics views have `@HasRole("admin")` commented out and no team scoping on `bot_id` — any session user reads any bot's analytics | Restore the decorator and scope `bot_id` to the team |
| F048 | Dead code | views.py:493 | Medium | S | `get_total_token_consumption`/`get_token_consumption_overview` are hardcoded stubs returning `0`/`[]` still routed in URLs | Remove or implement |
| F049 | Security | views.py:710 / views.py:749 | Medium | S | `submit_approval`/`submit_choice` `@api_exempt`, apply decisions keyed only by guessable ids, no approver binding | Authenticate and verify the user may approve that execution |
| F050 | Type/Contract | serializers/*.py | Medium | M | ~20 serializers use `fields="__all__"` (bot, llm, knowledge_document…) — mass-assignment on write, leaks internal columns on read | Replace with explicit field lists, especially writable serializers |
| F051 | Consistency | views.py + viewsets/* | Medium | S | ≥4 distinct error contracts: `JsonResponse({"result":...})`, OpenAI `{"choices":[]}`, DRF `Response`, raw `StreamingHttpResponse`; business failures return HTTP 200 | Standardize one error envelope; reserve OpenAI shape for completion routes; return 4xx |
| F052 | Architecture | views.py:317 / views.py:466 | Medium | M | `openai_completions` and `lobe_skill_execute` are ~80% identical; chat/skill business logic lives in module-level functions in `views.py` | Extract a `ChatCompletionService`; both endpoints become thin adapters |
| F053 | Consistency | node.py:46 / compaction.py:46 / message_trim.py:27 / graph.py:280 | Medium | S | tiktoken setup + token-counting duplicated across 3-4 files with copy-paste fallbacks | Extract a shared `token_utils.py` |
| F054 | Consistency | compaction.py:19 / model_vendor_sync_service.py:11 / llm_view.py:399 | Medium | S | Logging drift: `loguru.logger` and `logging.getLogger(__name__)` used in places where the rest uses `opspilot_logger` | Standardize on `opspilot_logger` everywhere |
| F055 | Error handling | engine.py:179/596/1402/1679 + tasks.py:968 | Medium | S | Four idioms for logging caught exceptions; several `logger.error(str(e))` with no `exc_info` lose stack traces in async contexts | Adopt `logger.exception` inside `except` project-wide |
| F056 | Consistency | engine/engine.py vs utils/sse_chat.py vs utils/agui_chat.py | Medium | M | Two parallel streaming stacks (OpenAI chunks vs AGUI events) duplicate think-tag handling, interrupt checks, token logging; 3 different error-event shapes | Factor a shared `StreamPipeline`; protocols provide only frame encoders |
| F057 | Type/Contract | node.py:3135 | Medium | M | `tc.get(...) if isinstance(tc, dict) else getattr(...)` appears 17× because tool_calls are sometimes dict, sometimes objects | Normalize to a typed dataclass once at the top of the node |
| F058 | Architecture | node.py:1289 / node.py:2301 | Medium | M | Six K8s-specific tools (`generate_repair_report`, `report_config_diff`…) bound to every agent that has any tools, polluting a MySQL/browser agent's tool space | Gate K8s tools behind `_is_k8s_tool_server` detection (helper exists at 1083) |
| F059 | Architecture | utils/ (31 entries) | Medium | M | `utils/` is a dumping ground: `dingtalk_chat_flow_utils.py` (464 LOC, streaming client + signature verify), `wechat_official_*`, `mcp_client.py`, `approval.py` are services, not helpers | Relocate channel/integration logic to `services/` |
| F060 | Architecture | tasks.py:1041 | Medium | M | The three channel tasks (DingTalk/WeChat/EnterpriseWeChat, 1056-1194) are near-identical copies differing only by handler class | Extract one `_run_channel_message(handler_cls, ...)` helper |
| F061 | Performance | rag_service.py:34 / knowledge_search_service.py:57 | Medium | S | `format_naive_rag_kwargs` reads `embed_model`/`rerank_model` per KB and does `EmbedProvider.objects.get`/`RerankProvider.objects.get` per call — N+1 on the hot chat path | `select_related("embed_model","rerank_model")` on the KB queryset |
| F062 | Performance | tasks.py:1319 | Medium | S | `flush_all_pending_memory_write_cache` does `.first()` per workflow_id then per-node fetches — O(workflows×nodes) in a beat task | Bulk-fetch and group pending caches in one query |
| F063 | Security/Info-leak | engine.py:607 / engine.py:1416 | Medium | S | Raw `str(e)` and the full `variable_manager.get_all_variables()` (prompts, user data, memory) serialized into `output_data` and streamed to clients | Persist a redacted summary; never echo full variable state |
| F064 | Security | browser_use/browser_tool.py:408 | Medium | S | `_apply_secret_placeholders` masks via `str.replace(value, placeholder)`; short/common values (`admin`,`123`) over-replace or silently aren't masked | Inject only via the structured `sensitive_data` map; reject short values |
| F065 | Performance | browser_use/browser_tool.py:247 | Medium | S | `_get_or_create_user_data_dir` only cleans temp Chrome profiles on a TTL sweep; on process churn / missing trace_id they leak on disk | Clean up in a request `finally`; use context-managed TemporaryDirectory when no session key |
| F066 | Consistency | mssql/utils.py:215 vs postgres/utils.py:97 | Medium | S | MSSQL `execute_readonly_query` does NOT open a read-only transaction (postgres does); its only write-guard is the bypassable blacklist | Use a read-only login / read-intent connection string |
| F067 | Type/Contract | knowledge_document_view.py:104 | Medium | S | Raw `request.data` access (`params["ids"]`, `kwargs["delete_qa_pairs"]`) with no request serializer → KeyError→500 | Define request serializers for the action bodies |
| F068 | Error handling | knowledge_document_view.py:121 | Medium | S | `KnowledgeBase.objects.get(...)`/`QAPairs.objects.get(...)` on user ids without try/except → unhandled `DoesNotExist` 500 | `.filter().first()` with explicit 404 |
| F069 | Consistency | node.py:2779 + node.py:2395/2407/3274 | Medium | M | Four overlapping context-shrinking mechanisms run per step (trim, compact, two inline truncation loops with magic constants) and mutate message objects in place | Consolidate into one message-budget pipeline; don't mutate shared messages |
| F070 | Type/Contract | entity.py:335 | Medium | S | `extra_config: Optional[dict]` is a free-form dict read via `.get("_require_choice_before_tools")` etc. — no schema for the engine↔service contract | Define a typed `ExtraConfig` model for the known keys |
| F071 | Performance | node.py:821 | Medium | S | `hash(relation_content) % 100000` builds chunk/segment ids — Python str `hash()` is per-process salted and collision-prone | Use a stable hash (`hashlib.md5(...).hexdigest()[:8]`) |
| F072 | Type/Contract | model_provider_mgmt.py:66 | Medium | S | `LLMModel`/`Embed`/`Rerank`/`OCRProvider.vendor` use `on_delete=SET_NULL`; deleting a vendor silently orphans models | Consider `PROTECT` to block deleting in-use vendors |
| F073 | Data model | knowledge_mgmt.py:234 | Medium | S | `KnowledgeTask.knowledge_base_id` is an untyped `IntegerField` (not FK), `is_qa_task`/`domain`/`created_by` queried with no `db_index` | Convert to FK or add `db_index=True` |
| F074 | Error handling | tasks.py:461 | Medium | S | `delete_and_update_old_data` catches all exceptions; `sync_web_page_knowledge` then re-embeds even if cleanup silently failed → stale/dup chunks | Distinguish recoverable vs fatal; don't continue on cleanup failure |
| F075 | Observability | nodes/memory/memory_read.py:60 | Medium | S | ~12 `logger.info` lines per execution incl. message previews — log spam + leaks user message snippets at INFO | Drop to DEBUG, collapse to one structured line |
| F076 | Correctness | engine.py:1837 | Medium | S | `_should_follow_edge` routes on `sourceHandle.lower() in ["true","false"]`; an intent label named "true"/"false" is misrouted | Disambiguate by node type, not handle string |
| F077 | Security | redis/postgres/mssql tool logging | Medium | S | `logger.info` dumps tool args / argv that may include credentials or task text (node.py:2857, agent_browser/browser_tool.py:208) | Mask credential args before logging; redact argv |
| F078 | Dead code | graph.py:984 | Medium | S | `_handle_ai_message_chunk`, `_handle_tool_calls_sync` (dup of `_handle_tool_calls`), `print_chunk`, `aprint_chunk`, `filter_messages` have no callers | Delete |
| F079 | Dead code | node.py:2238 | Medium | S | Unreachable lines 2238-2249 after `return bulk_repair_tool_instance` (2237) — leftover from a deleted method | Delete |
| F080 | Maintainability | utils/agui_chat.py:173 | Medium | M | AGUI think/tool state machine over a 12-key mutable dict, deeply nested, untyped, no tests on pre_think/post_tool branches — high churn risk | Model as an explicit FSM class with characterization tests |
| F081 | Type/Contract | kubernetes/remediation.py:31 + postgres/dynamic.py:722 | Medium | S | Many `@tool` fns have untyped params (`replicas`, `grace_period`) so LangChain's arg schema is loose — no LLM-side validation | Add type annotations + `Optional`/pydantic bounds |
| F082 | Data model | bot_mgmt.py:36 | Medium | S | `Bot.api_token = CharField(default="", blank=True, null=True)` — `null=True` on CharField with `default=""` is the two-empty-states anti-pattern | Drop `null=True` |
| F083 | Observability | node.py:1316 | Medium | S | `dispatch_custom_event("approval_request"...)` wrapped in `except Exception: pass`; if dispatch fails the UI never appears yet `wait_for_approval` blocks 300s | At least `logger.warning` on dispatch failure |
| F084 | Error handling | knowledge_search_service.py:91 | Low | S | `search` catches all exceptions and returns `[]` — a backend outage is indistinguishable from "no results" | Surface a distinguishable error signal/flag |
| F085 | Consistency | node.py:1353 | Low | S | Function-local re-imports of module-level names with aliased shadows (`import asyncio as _asyncio_force`, etc.) at many sites | Move to module top |
| F086 | Performance | node.py:3340 | Low | S | Adaptive retry re-invokes the entire `tool_node.ainvoke(state)`, re-running already-successful side-effecting tools to retry one | Retry only the failed tool_call |
| F087 | Correctness | nodes/agent/agent.py:124 | Low | S | `_truncate_memory_context`: line 125 sets `mem_with_prefix`, line 127 `if i==0:` overwrites with identical expression — botched-edit dead branch | Delete the redundant branch |
| F088 | Security | tasks.py / services/ DingTalk | Low | S | `ding_talk_client.py` calls `get_access_token()` per request (no cache), no `timeout=` on any request — a hung endpoint blocks the worker | Add `timeout=`, cache the token, reuse a session |
| F089 | Data model | knowledge_mgmt.py:218 | Low | S | `KnowledgeGraph` FKs all `CASCADE` incl. `llm_model` — deleting an LLMModel destroys KnowledgeGraphs | Use `PROTECT`/`SET_NULL` on `llm_model` |
| F090 | Dead code | views.py:30 / urls.py:79 | Low | S | `views.py` imports `LLMViewSet` only for a static helper; two URL patterns share `name="openai_completions"` (breaks `reverse()`) | Move helper to `utils/sse_chat.py`; give routes unique names |
| F091 | Type/Contract | tools_loader.py:91 | Low | S | Tool discovery matches `obj.__class__.__name__ == "StructuredTool"` instead of `isinstance` — a renamed/subclassed tool silently yields zero tools | Use `isinstance(obj, StructuredTool)` |
| F092 | Observability | node.py:69 | Low | S | `_safe_log_preview` does a GBK encode/decode round-trip on every preview, corrupting emoji/Unicode in logs even on Linux | Configure UTF-8 handler encoding once instead |
| F093 | Error handling | management/commands/parse_tools_yml.py:29 | Low | S | Catches all exceptions, prints, returns exit 0 — a failed tool sync looks successful to CI | Raise `CommandError` for non-zero exit |
| F094 | Dead code | node.py:2770 / signals/user_create_signal.py:5 | Low | S | Stale commented-out blocks (`tool_choice="any"`, `ModelProviderInitService` import) left inline | Remove; rely on git history |

---

## Top 5 — if you fix nothing else, fix these

### 1. Close the unauthenticated / cross-tenant data paths (F001–F004)
Four endpoints let a caller reach data that isn't theirs. Sketch:
```python
# F001 views.py:112 — bind the token to a session and expire it
@require_auth          # drop @api_exempt
def download_workflow_attachment(request, download_token):
    asset = WorkflowAttachmentAsset.objects.filter(
        download_token=download_token,
        bot__in=bots_for(request.user),         # ownership
        expires_at__gt=now(),                   # expiry
    ).select_related("file_knowledge").first()
    ...

# F002 knowledge_document_view.py:108 — go through the scoped queryset
docs = self.get_queryset().filter(id__in=knowledge_document_ids)   # team-scoped
docs.update(train_status=DocumentStatus.TRAINING)
general_embed(list(docs.values_list("id", flat=True)), ...)
```
Apply the same `get_queryset()` funnel to `batch_delete` and `delete_chunks`. These bespoke `@action`s are the exception to the otherwise-scoped viewsets — the fix is to make them obey the same rule.

### 2. Encrypt channel secrets and stop serializing them (F005, F006, F019, F050)
`Channel` silently skips the encryption `BotChannel` performs. Give it the same `save()` path (or extract a shared base that both inherit), then replace `fields="__all__"` on the secret-bearing serializers with explicit lists and make `channel_config`/`api_token` write-only or masked. This is a one-file model change plus two serializer edits, and it stops plaintext secrets at rest *and* in API responses.

### 3. Make SQL-tool authorization a DB role, not a regex (F007, F008, F028, F066)
The keyword blacklist cannot be made correct — `pg_sleep`, dollar-quoting, `format()`, bracket-identifier tricks all slip past it, and MSSQL doesn't even open a read-only transaction. Provision a dedicated least-privilege read-only login per data source, set `default_transaction_read_only`, and keep the blacklist only as a defense-in-depth speed bump. Then factor the four duplicated dialect guards into one parameterized module so a fix lands everywhere.

### 4. Fail loudly in Celery (F010, F011, F042)
Training/embedding tasks currently swallow per-item failures and `delete()` the tracking row, so a fully-failed batch is indistinguishable from success.
```python
# tasks.py:216 pattern
failures = []
for doc in docs:
    try: invoke_one_document(doc)
    except Exception as e:
        failures.append(doc.id); logger.exception(...)
if failures:
    # don't delete the tracking object; surface the failure
    raise EmbedBatchError(f"{len(failures)}/{len(docs)} failed: {failures}")
```
Adopt one documented convention (idempotent+retry vs terminal) and apply it across `tasks.py` — today three conventions coexist (F007/consistency).

### 5. Decompose `node.py` and decouple K8s from the generic engine (F024, F025, F039, F058)
This single 3,777-LOC file absorbs 42 edits in 6 months because it's four files wearing a trench coat. The highest-leverage extraction is the Kubernetes layer: pull the report/repair/issue-keyword logic into `k8s_report_tools.py` and gate it behind the existing `_is_k8s_tool_server` detection so non-K8s agents stop carrying K8s tools and prompts. Do the monkey-patches (`lc_patches.py`) and RAG nodes (`rag_nodes.py`) next. No behavior change — pure module boundaries — so it's reviewable.

---

## Quick wins (Low effort × Medium+ severity)

- [ ] F012 — Delete the four `/Users/qiu/...choice_debug.log` blocks in `node.py`.
- [ ] F005/F006 — Add `Channel.save()` encryption + mask `channel_serializer`.
- [ ] F008 — Validate `database` identifier before `USE [{database}]`.
- [ ] F019 — Mark `Bot.api_token` write-only in `bot_serializer`.
- [ ] F047/F048 — Restore the analytics `@HasRole("admin")` decorator; remove the two stub endpoints.
- [ ] F032 — Stop catching `BaseException` in `graph.execute()`; re-raise `CancelledError`.
- [ ] F078/F079/F094 — Delete confirmed dead code (graph.py helpers, node.py:2238-2249, stale comments).
- [ ] F090 — Fix the duplicate `name="openai_completions"` URL collision.
- [ ] F091 — `isinstance(obj, StructuredTool)` in `tools_loader.py`.
- [ ] F088 — Add `timeout=` to DingTalk client requests.
- [ ] F061 — `select_related("embed_model","rerank_model")` on the RAG KB queryset.

---

## Things that look bad but are actually fine

- **`metis/llm/tools/python/executor.py:93` `exec(...)`** — this is a deliberate sandboxed Python-interpreter tool: code is AST-validated and run with `__builtins__: SAFE_BUILTINS`. High blast radius by nature, but not an injection bug. Keep the allowlist tight; don't "fix" it as if it were accidental.
- **Chat-flow template rendering is not SSTI.** Every node renders via `safe_render`/`StrictSandboxedEnvironment` with a dangerous-pattern denylist, and `VariableManager.resolve_template` re-raises `TemplateSecurityError` rather than swallowing it. `safe_eval.py` is a genuine AST-whitelist evaluator (no `eval`/`exec`, no attribute access). HTTP action nodes route through `safe_get/safe_post` (SSRF-guarded). Don't flag these.
- **The langchain-openai monkey-patches (`node.py:477-561`)** look hacky but are load-bearing: they preserve `reasoning_content` for DeepSeek/Qwen thinking-mode multi-turn (HTTP 400 otherwise). Isolate them into `lc_patches.py`, but keep them.
- **`_run_in_native_thread` / new-event-loop-in-threadpool (`tasks.py:42`, `chat_service.py:113`)** — ugly but a deliberate, documented workaround for running Django ORM + async agents under ASGI; the `DJANGO_ALLOW_ASYNC_UNSAFE` fallback is intentional.
- **The default DRF config** sets `DEFAULT_PERMISSION_CLASSES = IsAuthenticated`, so class-based viewsets without explicit `permission_classes` are still authenticated. The real exposure is specifically the `@api_exempt` function views and the batch `@action`s that bypass `get_queryset()` — not the standard CRUD viewsets.
- **`api_key or " "` sprinkled through RAG services** looks like a placeholder leak but is a known requirement of the downstream RAG client, which rejects empty keys.
- **The parameterized `%s`/`%(name)s` SQL in `pgvector_rag.py` and `get_table_schema_details`** is correctly parameterized against system catalogs with white-listed sort fields — not injectable. The injection risk is specifically the *identifier* interpolation (`USE [{database}]`, `EXPLAIN PLAN FOR {query}`), not these.
- **`select_for_update` + status transitions in `_flush_memory_write_cache_group` (`tasks.py:151`)** — the batch memory-write concurrency handling is actually careful (row locking, processing-state guard, re-pending on failure). Don't refactor it casually.

---

## Open questions for the maintainer

1. **Is the generic-vs-K8s coupling intentional?** `chain/node.py` binds K8s repair tools/prompts to *every* agent. Is OpsPilot effectively a K8s-remediation product (so this is fine), or is generic tool-use a real goal (so F025/F058 matter)?
2. **RBAC scoping model.** Do `@HasPermission`/`@HasRole` decorators already enforce *team/object* scoping somewhere upstream, or are they purely role-based? F002–F004/F047 severity hinges on this — if permissions aren't team-scoped, those are genuine cross-tenant holes.
3. **Are the `@api_exempt` chat/skill/approval endpoints (F001, F014, F020, F049) protected by an upstream gateway** (mTLS, network policy, API-gateway auth) that isn't visible in this app? If so, severity drops; if they're internet-facing, they're Critical as written.
4. **Memory-write subsystem ownership.** `process_memory_write` + the flush beat tasks are complex and high-churn — is this a stable feature or an in-flight experiment? That changes whether F027 (decompose) is worth it now.
5. **Are the stub analytics endpoints (F048) placeholders for in-progress work**, or abandoned? They're routed and returning zeros today.
6. **Static tooling could not run** — `ruff`, `vulture`, `pip-audit` are not installed in the uv environment, so there is no CVE/dead-code/lint baseline. Should these be added to the dev toolchain + CI? Several findings (dead code, broad excepts) would be caught automatically.
