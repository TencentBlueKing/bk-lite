# BK-Lite 原子标准包

每个受信任的研发原子使用独立目录：

```text
bk_atom_xxx/
├── bk-atom.json
├── schemas/
│   ├── input.schema.json
│   ├── output.schema.json
│   └── ui.schema.json
├── runtime/
│   ├── __init__.py
│   └── handler.py
├── icons/
├── README.md
└── CHANGELOG.md
```

`bk-atom.json` 声明稳定 key、展示信息、输入/输出 Schema、可选 UI Schema、安全/权限/资源边界、超时重试以及执行绑定。MVP 不管理原子版本，同一 key 的契约和 handler 随代码同步，后续扩展必须保持向后兼容。该目录只接受随代码发布的受信任包，MVP 不接收页面上传的代码。

WORKER 示例：

```json
{
  "key": "custom.health_inspection",
  "name": "健康巡检",
  "category": "巡检",
  "description": "执行受控的主机健康巡检",
  "driver": "WORKER",
  "trusted_context": false,
  "handler": "apps.workflow_orchestration.atom_packages.bk_atom_health_inspection.runtime.handler:execute",
  "input_schema": "schemas/input.schema.json",
  "output_schema": "schemas/output.schema.json",
  "ui_schema": "schemas/ui.schema.json",
  "timeout_seconds": 600,
  "retry_count": 0,
  "retry_delay_seconds": 5,
  "idempotent": false,
  "safety_level": "MUTATION",
  "resource_scope": "NODE_INPUT",
  "required_permissions": ["workflow-Execute"],
  "error_types": ["execution_failed"]
}
```

`trusted_context` 仅用于需要流程执行人和组织边界的受信任原子包。声明为
`true` 后，Workflow Worker 会在 handler 执行前注入 `__bklite_context`；该字段不来自用户输入，
也不写入原子执行输入快照。

目录名使用下划线，保证包内 Python handler 可被正常导入。HTTP 原子可将 `driver` 改为 `HTTP`，并通过 `http` 声明研发预置的绝对 `url` 与 `method`（含 PATCH）；运行时仍做 SSRF 与大小限制。
