# Stargazer 采集 · 重构后层级与配置采集代码流程图

在 IDE 中打开本文件并用 **Markdown Preview** 查看 Mermaid 图。

---

## 1. 代码层级（重构后 · 包分类）

```text
core/
  logger.py / config.py / decorator.py   # 共享入口
  collection/                            # 统一异步采集运行时
    application.py · runtime.py · executor.py
    contracts.py · enums.py · constants.py
    plugins.py · request_builder.py · result_publisher.py
    preflight.py · credential_policy.py · metrics.py · redis_state.py
    host_remote/{adapter,callback,runtime}.py
  plugin/                                # YAML 插件加载执行
    executor.py · source_resolver.py · yaml_reader.py
  infra/                                 # Redis / NATS / SSH / 出站等
    redis_*.py · nats*.py · ansible_rpc.py · ssh_client.py …
  monitor/                               # 既有监控驱动（保留）
```

旧平铺路径（如 `core.collection_application`）已删除，统一使用上表包路径。

---

## 2. 服务启动（before_server_start）

```mermaid
flowchart TD
  A["server.py 加载"] --> B["register_redis_lifecycle"]
  B --> C["initialize_collection_application"]
  C --> D["before_server_start:<br/>ping Redis"]
  D --> E["new CollectionApplication<br/>注入 CollectionService 工厂<br/>RedisRun/CredentialStore<br/>Preflight · Publisher · Budget"]
  E --> F["CollectionRuntime<br/>execute=Application._execute"]
  F --> G["监听 :8083<br/>可接 /collect/collect_info"]
```

---

## 3. 一次配置采集 · 代码执行流程图

以 `GET /collect/collect_info`（`model_id=mysql` 等）为例。函数名为当前代码真实符号。

```mermaid
flowchart TD
  H1["api.collect.collect()<br/>解析 cmdb* headers"] --> H2["_submit_collection_run()"]
  H2 --> H3["parse_credentials_pool()<br/>collection_request_builder"]
  H3 --> H4["build_collection_request()<br/>→ CollectionRequest"]
  H4 --> H5["get_collection_application()<br/>.submit(request)"]

  H5 --> R1["CollectionRuntime.submit()"]
  R1 --> R2{"RedisRunStateStore.acquire<br/>同 task_id running?"}
  R2 -->|是| R3["Submission DUPLICATE_ACTIVE<br/>HTTP 202"]
  R2 -->|容量满| R4["Submission BUSY<br/>HTTP 429"]
  R2 -->|取得租约 fence=1| R5["Sanic schedule<br/>→ Runtime._run"]
  R5 --> R6["HTTP 202 ACCEPTED<br/>立即返回 Prometheus 接纳指标"]

  R5 --> E1["CollectionApplication._execute"]
  E1 --> E2["UnifiedPluginFactory.resolve<br/>→ ConfigurationCollectionPlugin"]
  E2 --> E3["TargetCollectionExecutor.execute"]

  E3 --> W1["worker 循环取 target"]
  W1 --> T1["_execute_target"]
  T1 --> T2["_run_preflight<br/>AsyncProtocolPreflight.check"]
  T2 --> T3{"UNREACHABLE?"}
  T3 -->|是| T4["TargetCollectionResult<br/>unreachable"]
  T3 -->|否| T5["CredentialPolicy<br/>.eligible_credentials"]
  T5 --> T6{"有可用凭据?"}
  T6 -->|否| T7["failed<br/>no_matching/no_valid"]
  T6 -->|是| T8["_run_credential_attempts<br/>串行 for credential"]

  T8 --> A1["_run_access_probe<br/>plugin.probe"]
  A1 --> A2["ConfigurationCollectionPlugin.probe<br/>→ CollectionService.probe<br/>→ PluginExecutor.probe"]
  A2 --> A3{"AccessProbeStatus"}
  A3 -->|AUTH / CAPABILITY| A4["record_auth_failure · continue"]
  A3 -->|NO_RESPONSE 达上限| A5["failed<br/>no_response_attempt_limit"]
  A3 -->|READY / NOT_SUPPORTED| A6["_run_collect<br/>plugin.collect"]

  A6 --> C1["ConfigurationCollectionPlugin.collect"]
  C1 --> C2["CollectionService.collect"]
  C2 --> C3["PluginExecutor.execute<br/>_prepare_collector"]
  C3 --> C4["collector.list_all_resources<br/>插件内 to_thread"]
  C4 --> C5["Prometheus / 结构化结果"]
  C5 --> C6{"CollectOutcome"}
  C6 -->|SUCCESS| C7["record_success<br/>status=success"]
  C6 -->|AUTH_FAILED| A4
  C6 -->|其他| C8["failed / unreachable / …"]

  C7 --> P1["NatsResultPublisher.publish<br/>build_collection_result_id"]
  P1 --> P2["publish_metrics_to_nats<br/>失败再试 1 次"]
  P2 --> P3["CredentialStateCache<br/>.append_result_event"]

  T4 --> P1
  T7 --> P1
  A5 --> P1
  C8 --> P1

  W1 -->|下一目标| W1
  W1 -->|全部完成| F1["RunSummary<br/>Runtime.finish DEL 租约"]
```

HTTP 与后台采集的时序：

```mermaid
sequenceDiagram
  participant Client as Telegraf/CMDB
  participant HTTP as api.collect
  participant App as CollectionApplication
  participant RT as CollectionRuntime
  participant Redis as RedisRunStateStore
  participant EX as TargetCollectionExecutor
  participant Plug as ConfigurationCollectionPlugin
  participant Svc as CollectionService/PluginExecutor
  participant NATS as NatsResultPublisher

  Client->>HTTP: GET /collect/collect_info
  HTTP->>App: submit(CollectionRequest)
  App->>RT: submit
  RT->>Redis: acquire(task_id)
  Redis-->>RT: lease fence=1
  RT-->>HTTP: ACCEPTED
  HTTP-->>Client: 202 + monitor_request_accepted 指标

  RT->>App: _execute(request, lease)
  App->>EX: execute
  loop 每个 target（有界并发）
    EX->>EX: preflight → credentials
    EX->>Plug: probe / collect
    Plug->>Svc: probe/collect
    Svc-->>Plug: metrics / AccessProbe
    EX->>NATS: publish(result)
  end
  EX-->>RT: RunSummary
  RT->>Redis: finish → DEL lease
```

---

## 4. 关键调用栈（配置采集成功路径）

```
server.py
└─ api/collect.py::collect
   └─ _submit_collection_run
      ├─ parse_credentials_pool          # collection_request_builder
      ├─ build_collection_request
      └─ CollectionApplication.submit
         └─ CollectionRuntime.submit
            ├─ RedisRunStateStore.acquire
            └─ schedule → _run → CollectionApplication._execute
               ├─ UnifiedPluginFactory.resolve → ConfigurationCollectionPlugin
               └─ TargetCollectionExecutor.execute
                  └─ _execute_target
                     ├─ _run_preflight → AsyncProtocolPreflight.check
                     ├─ CredentialPolicy.eligible_credentials
                     └─ _run_credential_attempts
                        ├─ _run_access_probe → plugin.probe
                        │     → CollectionService.probe → PluginExecutor.probe
                        ├─ _run_collect → plugin.collect
                        │     → CollectionService.collect → PluginExecutor.execute
                        │           → collector.list_all_resources()
                        └─ NatsResultPublisher.publish
                              → build_collection_result_id
                              → publish_metrics_to_nats
```

---

## 5. 与「监控 / 主机 remote」的分叉（对照）

| 步骤 | 配置采集 | 主机监控 `/monitor/host` |
|------|----------|--------------------------|
| Factory | `ConfigurationCollectionPlugin` | `MonitorCollectionPlugin` |
| probe | `CollectionService.probe` | `NOT_SUPPORTED`（跳过） |
| collect | `PluginExecutor` → 插件 | `host_remote_adapter.submit_host_remote_collection` |
| 发布 | 即时 NATS metrics | `DEFERRED` → Ansible 回调后再发 |

---

Source: 当前 `agents/stargazer` 重构后代码（薄租约 · contracts · 无 checkpoint）。
