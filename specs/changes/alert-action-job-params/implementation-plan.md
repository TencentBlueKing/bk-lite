# 告警处理作业参数 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 用户要求本轮**不提交 git**。下列任务没有 Commit 步骤；做完验证即可。

**Goal:** 告警处理规则可为每个作业参数选手动填写或告警变量，默认回写脚本明文默认值；规则可关闭自动执行；手动触发时仅允许改「可调」手填项。

**Architecture:** 告警中心继续调用现有 `job_script_execute`，自己按脚本参数顺序组装完整 `params`。`ActionRule.auto_execute` 控制引擎是否 dispatch。绑定存在 `action_config.param_bindings`。手动覆盖在创建执行记录前校验，合法后交给 job handler。前端用纯函数做选作业默认绑定、编辑时结构对齐和重新加载。

**Tech Stack:** Django / DRF、现有 alerts ActionEngine、Next.js + Ant Design、vitest / tsx 契约测试。

规格：`specs/changes/alert-action-job-params/spec.md`。

---

## File Structure

| 文件 | 职责 |
|---|---|
| `server/apps/alerts/models/action.py` | `ActionRule.auto_execute` |
| `server/apps/alerts/migrations/0035_actionrule_auto_execute.py` | 默认 `true`，存量视为开 |
| `server/apps/alerts/action/resolver.py` | 按脚本顺序解析；const 空值原样；覆盖值；脱敏默认值不当真实值 |
| `server/apps/alerts/action/overrides.py` | 手动覆盖校验（创建记录前） |
| `server/apps/alerts/action/engine.py` | `auto_execute=False` 不 dispatch |
| `server/apps/alerts/action/handlers/base.py` / `job.py` | `execute(..., param_overrides=None)`；结果写入 `params` |
| `server/apps/alerts/serializers/action.py` | 保存时校验绑定 |
| `server/apps/alerts/views/action.py` | 停用规则拒绝；覆盖校验；传入 handler |
| `web/src/app/alarm/types/settings.ts` | `auto_execute`、`allow_adjust` |
| `web/src/app/alarm/utils/actionParamBindings.ts` | 默认绑定、对齐、可改项、脱敏 |
| `web/src/app/alarm/(pages)/settings/actionRules/components/fieldBindingTable.tsx` | 手动/变量、可改开关 |
| `web/src/app/alarm/(pages)/settings/actionRules/components/operateModal.tsx` | 自动执行、选作业回写、打开对齐、重新加载 |
| `web/src/app/alarm/(pages)/alarms/components/manualActionExecuteModal.tsx` | 手动执行弹框 |
| `web/src/app/alarm/(pages)/alarms/components/alarmAction.tsx` | 走共享弹框 |
| `web/src/app/alarm/(pages)/alarms/components/actionTimeline.tsx` | 再次执行走共享弹框 |
| `web/src/app/alarm/locales/{zh,en}.json` | 文案 |
| `web/src/app/alarm/api/settings.ts` | `manualTriggerAction` 可带 `param_overrides` |

---

### Task 1: 参数解析按脚本顺序，支持 const 空值与覆盖

**Files:**
- Modify: `server/apps/alerts/action/resolver.py`
- Create: `server/apps/alerts/action/overrides.py`
- Test: `server/apps/alerts/tests/test_action_payload_pure.py`

- [ ] **Step 1: Write the failing tests**

在 `server/apps/alerts/tests/test_action_payload_pure.py` 追加：

```python
from apps.alerts.action.exceptions import ConfigError
from apps.alerts.action.overrides import validate_manual_param_overrides
from apps.alerts.action.resolver import resolve_params
from apps.alerts.action.payload import build_match_payload


def test_resolve_params_uses_script_order_and_keeps_empty_const():
    payload = build_match_payload(FakeAlert())
    bindings = [
        {"name": "later", "from": "const", "value": "b"},
        {"name": "empty", "from": "const", "value": ""},
    ]
    script_params = [
        {"name": "empty", "default": "should-not-fill"},
        {"name": "later", "default": "x"},
        {"name": "added", "default": "from-script"},
    ]
    params = resolve_params(payload, bindings, script_params)
    assert params == [
        {"name": "empty", "value": ""},
        {"name": "later", "value": "b"},
        {"name": "added", "value": "from-script"},
    ]


def test_resolve_params_drops_removed_script_params_and_applies_overrides():
    payload = build_match_payload(FakeAlert())
    bindings = [
        {"name": "gone", "from": "const", "value": "old"},
        {"name": "keep", "from": "const", "value": "v1", "allow_adjust": True},
        {"name": "svc", "from": "field", "value": "labels.service"},
    ]
    script_params = [
        {"name": "keep", "default": "d"},
        {"name": "svc", "default": "nginx"},
    ]
    params = resolve_params(payload, bindings, script_params, overrides={"keep": "v2"})
    assert params == [
        {"name": "keep", "value": "v2"},
        {"name": "svc", "value": "nginx"},
    ]


def test_resolve_params_rejects_masked_default_as_real_value():
    payload = build_match_payload(FakeAlert())
    params = resolve_params(
        payload,
        [],
        [{"name": "token", "default": "******"}],
    )
    assert params == [{"name": "token", "value": ""}]


def test_field_missing_without_usable_default_is_config_error():
    payload = build_match_payload(FakeAlert())
    try:
        resolve_params(
            payload,
            [{"name": "origin", "from": "field", "value": "labels.missing"}],
            [{"name": "origin"}],
        )
    except ConfigError as exc:
        assert "origin" in str(exc)
    else:
        raise AssertionError("expected ConfigError")


def test_validate_manual_overrides_only_allows_adjustable_const():
    bindings = [
        {"name": "a", "from": "const", "value": "1", "allow_adjust": True},
        {"name": "b", "from": "const", "value": "2"},
        {"name": "c", "from": "field", "value": "title", "allow_adjust": True},
    ]
    validate_manual_param_overrides(bindings, {"a": "9"})
    try:
        validate_manual_param_overrides(bindings, {"b": "x"})
        raise AssertionError("b should be rejected")
    except ConfigError:
        pass
    try:
        validate_manual_param_overrides(bindings, {"c": "x"})
        raise AssertionError("field binding should be rejected")
    except ConfigError:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/alerts/tests/test_action_payload_pure.py --no-cov -q
```

Expected: 新用例 FAIL（`overrides` 参数不存在 / `validate_manual_param_overrides` 未定义）。已有 `test_action_parameters_keep_first_event_source_id` 仍应能收集。

- [ ] **Step 3: Implement resolver and overrides**

`server/apps/alerts/action/resolver.py` 替换为：

```python
from apps.alerts.action.payload import resolve_field
from apps.alerts.action.exceptions import ConfigError

MASKED_DEFAULTS = {"******", "***"}


def plain_script_default(param_def: dict) -> str:
    if "default" not in (param_def or {}):
        return ""
    value = param_def.get("default")
    if value in MASKED_DEFAULTS:
        return ""
    if value is None:
        return ""
    return value


def resolve_params(payload: dict, bindings: list, script_params: list, overrides: dict | None = None) -> list:
    """按脚本参数顺序解析。const 空值原样下发；field 缺失回退明文 default。"""
    overrides = overrides or {}
    by_name = {b["name"]: b for b in (bindings or []) if b.get("name")}
    defs = [p for p in (script_params or []) if p.get("name")]
    if not defs:
        defs = [{"name": b["name"]} for b in (bindings or []) if b.get("name")]
    out = []
    for param_def in defs:
        name = param_def["name"]
        if name in overrides:
            out.append({"name": name, "value": overrides[name]})
            continue
        binding = by_name.get(name)
        if binding is None:
            out.append({"name": name, "value": plain_script_default(param_def)})
            continue
        if binding.get("from") == "const":
            value = binding.get("value")
            out.append({"name": name, "value": "" if value is None else value})
            continue
        value = resolve_field(payload, binding.get("value"))
        if value is None:
            if "default" not in param_def:
                raise ConfigError(f"参数[{name}]字段[{binding.get('value')}]缺失且无默认值")
            value = plain_script_default(param_def)
            if value == "" and param_def.get("default") in MASKED_DEFAULTS:
                raise ConfigError(f"参数[{name}]字段[{binding.get('value')}]缺失且无默认值")
        out.append({"name": name, "value": value})
    return out
```

`server/apps/alerts/action/overrides.py`：

```python
from apps.alerts.action.exceptions import ConfigError


def validate_manual_param_overrides(bindings: list, overrides) -> dict:
    if not overrides:
        return {}
    if not isinstance(overrides, dict):
        raise ConfigError("param_overrides 必须是对象")
    allowed = {
        binding["name"]
        for binding in (bindings or [])
        if binding.get("name")
        and binding.get("from") == "const"
        and binding.get("allow_adjust") is True
    }
    extra = [key for key in overrides if key not in allowed]
    if extra:
        raise ConfigError(f"不允许覆盖参数: {', '.join(sorted(str(key) for key in extra))}")
    return {key: overrides[key] for key in overrides}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: 同 Step 2。

Expected: PASS。`test_action_parameters_keep_first_event_source_id` 仍通过。

---

### Task 2: 规则级自动执行开关与引擎跳过

**Files:**
- Modify: `server/apps/alerts/models/action.py`
- Create: `server/apps/alerts/migrations/0035_actionrule_auto_execute.py`
- Modify: `server/apps/alerts/action/engine.py`
- Test: `server/apps/alerts/tests/test_action_engine_service.py`

- [ ] **Step 1: Write the failing tests**

在 `test_action_engine_service.py` 把 `_rule` 改为接受 `auto_execute=True`，并追加：

```python
def _rule(events, match_rules=None, team=[1], active=True, auto_execute=True):
    return ActionRule.objects.create(
        name="r",
        is_active=active,
        auto_execute=auto_execute,
        team=team,
        trigger_events=events,
        match_rules=match_rules or [],
        action_type="job",
        action_config={"script_id": 1},
    )


@pytest.mark.django_db
@patch("apps.alerts.action.engine.get_handler")
def test_auto_execute_false_matches_but_does_not_dispatch(mock_get):
    alert = _alert()
    _rule(events=["created"], auto_execute=False)
    ActionEngine().evaluate(alert, "created")
    assert ActionExecution.objects.count() == 0
    mock_get.return_value.execute.assert_not_called()


@pytest.mark.django_db
@patch("apps.alerts.action.engine.get_handler")
def test_auto_execute_default_true_still_dispatches(mock_get):
    alert = _alert()
    rule = ActionRule.objects.create(
        name="legacy", is_active=True, team=[1], trigger_events=["created"], action_type="job", action_config={"script_id": 1}
    )
    assert rule.auto_execute is True
    ActionEngine().evaluate(alert, "created")
    assert ActionExecution.objects.filter(alert=alert, trigger_type="auto").count() == 1
    mock_get.return_value.execute.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/alerts/tests/test_action_engine_service.py --no-cov -q
```

Expected: FAIL（`auto_execute` 不是模型字段）。

- [ ] **Step 3: Add field, migration, engine guard**

`ActionRule` 在 `is_active` 后增加：

```python
auto_execute = models.BooleanField(default=True, verbose_name="是否自动执行")
```

生成迁移 `0035_actionrule_auto_execute.py`，`dependencies = [("alerts", "0034_event_node_id")]`，`AddField(..., default=True)`。不要写数据回填；默认值即存量视为开。

`engine.py` 的 `evaluate` 循环里，在 `event_name not in trigger_events` 判断之后、match 之前加入：

```python
if not getattr(rule, "auto_execute", True):
    continue
```

必须在创建 `ActionExecution` 之前跳过。停用规则仍由现有 `is_active=True` 过滤覆盖。

- [ ] **Step 4: Run tests to verify they pass**

Run: 同 Step 2。Expected: PASS（含原有命中/幂等/组织隔离用例）。

---

### Task 3: 保存规则时校验 param_bindings

**Files:**
- Modify: `server/apps/alerts/serializers/action.py`
- Test: `server/apps/alerts/tests/test_action_rule_views.py`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.django_db
def test_create_rule_rejects_field_binding_without_value(superuser_client):
    superuser_client.cookies["current_team"] = "1"
    payload = {
        "name": "缺字段",
        "team": [1],
        "trigger_events": ["created"],
        "match_rules": [[{"key": "level", "operator": "any_of", "value": ["1"]}]],
        "action_type": "job",
        "auto_execute": False,
        "action_config": {
            "script_id": 1,
            "target_binding": {"source": "node_mgmt", "host_field": "labels.ip"},
            "param_bindings": [{"name": "svc", "from": "field", "value": ""}],
        },
    }
    resp = superuser_client.post("/api/v1/alerts/api/action_rule/", data=payload, format="json")
    assert resp.status_code == 400
    assert not ActionRule.objects.filter(name="缺字段").exists()


@pytest.mark.django_db
def test_create_rule_strips_allow_adjust_on_field_binding(superuser_client):
    superuser_client.cookies["current_team"] = "1"
    payload = {
        "name": "可调手填",
        "team": [1],
        "trigger_events": ["created"],
        "match_rules": [[{"key": "level", "operator": "any_of", "value": ["1"]}]],
        "action_type": "job",
        "auto_execute": True,
        "action_config": {
            "script_id": 1,
            "target_binding": {"source": "node_mgmt", "host_field": "labels.ip"},
            "param_bindings": [
                {"name": "svc", "from": "const", "value": "nginx", "allow_adjust": True},
                {"name": "title", "from": "field", "value": "title", "allow_adjust": True},
            ],
        },
    }
    resp = superuser_client.post("/api/v1/alerts/api/action_rule/", data=payload, format="json")
    assert resp.status_code in (200, 201)
    rule = ActionRule.objects.get(name="可调手填")
    assert rule.auto_execute is True
    bindings = {item["name"]: item for item in rule.action_config["param_bindings"]}
    assert bindings["svc"]["allow_adjust"] is True
    assert bindings["title"].get("allow_adjust") is not True
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/alerts/tests/test_action_rule_views.py --no-cov -q
```

Expected: 缺字段用例 FAIL（当前会 201）。

- [ ] **Step 3: Validate action_config in serializer**

在 `ActionRuleSerializer` 增加：

```python
def validate_action_config(self, value):
    if not isinstance(value, dict):
        raise serializers.ValidationError("action_config 必须是对象")
    bindings = value.get("param_bindings") or []
    if not isinstance(bindings, list):
        raise serializers.ValidationError("param_bindings 必须是列表")
    cleaned = []
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict) or not binding.get("name"):
            raise serializers.ValidationError(f"param_bindings[{index}] 缺少 name")
        source = binding.get("from") or "field"
        if source not in {"const", "field"}:
            raise serializers.ValidationError(f"参数[{binding['name']}] from 只能是 const 或 field")
        field_value = binding.get("value")
        if source == "field" and not str(field_value or "").strip():
            raise serializers.ValidationError(f"参数[{binding['name']}] 变量传递必须选择告警字段")
        item = {
            "name": binding["name"],
            "from": source,
            "value": "" if field_value is None else field_value,
        }
        if source == "const" and binding.get("allow_adjust") is True:
            item["allow_adjust"] = True
        cleaned.append(item)
    value = dict(value)
    value["param_bindings"] = cleaned
    return value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: 同 Step 2。Expected: PASS。`test_create_and_list_rule` 的空 `param_bindings` 仍可通过。

---

### Task 4: Job handler 按下发列表执行并记录实际参数

**Files:**
- Modify: `server/apps/alerts/action/handlers/base.py`
- Modify: `server/apps/alerts/action/handlers/job.py`
- Test: `server/apps/alerts/tests/test_job_handler_service.py`

- [ ] **Step 1: Write the failing tests**

```python
@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_const_empty_is_sent_and_overrides_apply(mock_target, mock_job):
    mock_target.return_value = {"node_id": "n1", "name": "h", "ip": "10.0.0.5",
                                "os": "linux", "cloud_region_id": 1}
    mock_job.return_value.get_script.return_value = {
        **SCRIPT,
        "params": [
            {"name": "service", "default": "nginx"},
            {"name": "flag", "default": "off"},
        ],
    }
    mock_job.return_value.job_script_execute.return_value = {"result": True, "data": {"task_id": 1}}
    rule = _rule()
    rule.action_config["param_bindings"] = [
        {"name": "service", "from": "const", "value": "", "allow_adjust": True},
        {"name": "flag", "from": "const", "value": "off"},
    ]
    execution = MagicMock()
    execution.result = {}
    JobActionHandler().execute(rule, _alert(), execution, param_overrides={"service": "redis"})
    payload = mock_job.return_value.job_script_execute.call_args[0][0]
    assert payload["params"] == [
        {"name": "service", "value": "redis"},
        {"name": "flag", "value": "off"},
    ]
    assert execution.result["params"] == payload["params"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/alerts/tests/test_job_handler_service.py::test_const_empty_is_sent_and_overrides_apply --no-cov -q
```

Expected: FAIL（`execute` 不接受 `param_overrides`）。

- [ ] **Step 3: Extend handler signature**

`base.py`：

```python
def execute(self, rule, alert, execution, param_overrides=None) -> None:
```

`job.py` 的 `execute` 同样增加 `param_overrides=None`。解析改为：

```python
params = resolve_params(
    payload,
    cfg.get("param_bindings", []),
    script.get("params", []),
    overrides=param_overrides,
)
```

在调用 `job_script_execute` 之前把 `execution.result` 写成包含已有 `target_ip` / `mode` 以及 `"params": params`。失败分支继续保留 `target_ip`，并保留已写入的 `params`。

引擎调用仍是 `execute(rule, alert, execution)`，覆盖默认为 `None`。

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/alerts/tests/test_job_handler_service.py --no-cov -q
```

Expected: PASS。原有 from_alert / fixed / callback 用例不回退。

---

### Task 5: 手动触发校验覆盖值，停用规则不可跑

**Files:**
- Modify: `server/apps/alerts/views/action.py`
- Test: `server/apps/alerts/tests/test_manual_trigger_views.py`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.django_db
@patch("apps.alerts.views.action.get_handler")
def test_manual_trigger_rejects_inactive_rule(mock_get, superuser_client):
    alert = Alert.objects.create(alert_id="A-OFF", fingerprint="f-off", title="t", content="c",
                                 level="0", team=[1])
    rule = ActionRule.objects.create(name="off", team=[1], is_active=False, action_config={"script_id": 1})
    resp = superuser_client.post(
        "/api/v1/alerts/api/action_execution/manual_trigger/",
        data={"alert_id": alert.alert_id, "rule_id": rule.id},
        format="json",
        HTTP_IDEMPOTENCY_KEY="manual-inactive",
    )
    assert resp.status_code == 400
    assert ActionExecution.objects.count() == 0
    mock_get.assert_not_called()


@pytest.mark.django_db
@patch("apps.alerts.views.action.get_handler")
def test_manual_trigger_rejects_illegal_overrides_before_create(mock_get, superuser_client):
    alert = Alert.objects.create(alert_id="A-OV", fingerprint="f-ov", title="t", content="c",
                                 level="0", team=[1])
    rule = ActionRule.objects.create(
        name="ov",
        team=[1],
        is_active=True,
        auto_execute=False,
        action_config={
            "script_id": 1,
            "param_bindings": [{"name": "svc", "from": "const", "value": "nginx"}],
        },
    )
    resp = superuser_client.post(
        "/api/v1/alerts/api/action_execution/manual_trigger/",
        data={"alert_id": alert.alert_id, "rule_id": rule.id, "param_overrides": {"svc": "redis"}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="manual-bad-override",
    )
    assert resp.status_code == 400
    assert ActionExecution.objects.count() == 0
    mock_get.assert_not_called()


@pytest.mark.django_db
@patch("apps.alerts.views.action.get_handler")
def test_manual_trigger_passes_legal_overrides(mock_get, superuser_client):
    mock_get.return_value.execute.return_value = None
    alert = Alert.objects.create(alert_id="A-OK", fingerprint="f-ok", title="t", content="c",
                                 level="0", team=[1])
    rule = ActionRule.objects.create(
        name="ok",
        team=[1],
        is_active=True,
        action_config={
            "script_id": 1,
            "param_bindings": [{"name": "svc", "from": "const", "value": "nginx", "allow_adjust": True}],
        },
    )
    resp = superuser_client.post(
        "/api/v1/alerts/api/action_execution/manual_trigger/",
        data={"alert_id": alert.alert_id, "rule_id": rule.id, "param_overrides": {"svc": "redis"}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="manual-ok-override",
    )
    assert resp.status_code == 200
    kwargs = mock_get.return_value.execute.call_args.kwargs
    assert kwargs["param_overrides"] == {"svc": "redis"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/alerts/tests/test_manual_trigger_views.py --no-cov -q
```

Expected: 停用规则当前会执行（FAIL）；非法覆盖会建记录（FAIL）。

- [ ] **Step 3: Guard manual_trigger**

在 `manual_trigger` 找到 `alert`/`rule` 且组织校验通过之后、`get_or_create` 之前：

```python
if not rule.is_active:
    return Response({"detail": "alert/rule 不存在或无权访问"}, status=status.HTTP_400_BAD_REQUEST)

from apps.alerts.action.exceptions import ConfigError
from apps.alerts.action.overrides import validate_manual_param_overrides

try:
    param_overrides = validate_manual_param_overrides(
        (rule.action_config or {}).get("param_bindings") or [],
        request.data.get("param_overrides"),
    )
except ConfigError as exc:
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
```

`execute` 改为：

```python
get_handler(rule.action_type).execute(rule, alert, execution, param_overrides=param_overrides)
```

无覆盖时 `param_overrides` 为 `{}`，handler 视为未覆盖。幂等重放仍不二次 execute。

- [ ] **Step 4: Run tests to verify they pass**

Run: 同 Step 2。Expected: PASS。原有幂等、跨组织、子组织用例不回退。

---

### Task 6: 前端绑定纯函数（默认值、对齐、重新加载）

**Files:**
- Create: `web/src/app/alarm/utils/actionParamBindings.ts`
- Test: `web/src/app/alarm/utils/__tests__/actionParamBindings.test.ts`

- [ ] **Step 1: Write the failing tests**

```typescript
import { describe, expect, it } from 'vitest';
import {
  adjustableConstBindings,
  alignParamBindings,
  defaultBindingsFromScript,
  fieldBindingsIncomplete,
} from '../actionParamBindings';

const script = [
  { name: 'pkg', label: '包', default: 'openssl' },
  { name: 'token', label: '令牌', default: '******' },
  { name: 'empty', label: '空' },
];

describe('defaultBindingsFromScript', () => {
  it('writes plaintext defaults as const and treats masked defaults as empty', () => {
    expect(defaultBindingsFromScript(script)).toEqual([
      { name: 'pkg', from: 'const', value: 'openssl', allow_adjust: false },
      { name: 'token', from: 'const', value: '', allow_adjust: false },
      { name: 'empty', from: 'const', value: '', allow_adjust: false },
    ]);
  });
});

describe('alignParamBindings', () => {
  it('adds new params, drops removed ones, and keeps existing bindings', () => {
    const existing = [
      { name: 'pkg', from: 'field' as const, value: 'title', allow_adjust: true },
      { name: 'gone', from: 'const' as const, value: 'old' },
    ];
    expect(
      alignParamBindings(
        [
          { name: 'pkg', default: 'openssl' },
          { name: 'new', default: 'n1' },
        ],
        existing
      )
    ).toEqual([
      { name: 'pkg', from: 'field', value: 'title', allow_adjust: false },
      { name: 'new', from: 'const', value: 'n1', allow_adjust: false },
    ]);
  });

  it('reload overwrites const values but keeps field mappings and allow_adjust', () => {
    const existing = [
      { name: 'pkg', from: 'const' as const, value: 'custom', allow_adjust: true },
      { name: 'title', from: 'field' as const, value: 'title' },
    ];
    expect(
      alignParamBindings(
        [
          { name: 'pkg', default: 'openssl' },
          { name: 'title', default: 'x' },
        ],
        existing,
        { reloadConstDefaults: true }
      )
    ).toEqual([
      { name: 'pkg', from: 'const', value: 'openssl', allow_adjust: true },
      { name: 'title', from: 'field', value: 'title', allow_adjust: false },
    ]);
  });
});

describe('adjustableConstBindings', () => {
  it('only returns const params with allow_adjust', () => {
    expect(
      adjustableConstBindings([
        { name: 'a', from: 'const', value: '1', allow_adjust: true },
        { name: 'b', from: 'const', value: '2' },
        { name: 'c', from: 'field', value: 'title', allow_adjust: true },
      ])
    ).toEqual([{ name: 'a', from: 'const', value: '1', allow_adjust: true }]);
  });
});

describe('fieldBindingsIncomplete', () => {
  it('is true when a field binding has no path', () => {
    expect(
      fieldBindingsIncomplete([{ name: 'a', from: 'field', value: '' }])
    ).toBe(true);
    expect(
      fieldBindingsIncomplete([{ name: 'a', from: 'const', value: '' }])
    ).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd web && pnpm exec vitest run src/app/alarm/utils/__tests__/actionParamBindings.test.ts
```

Expected: FAIL（模块不存在）。

- [ ] **Step 3: Implement the util**

```typescript
import { ActionConfig } from '@/app/alarm/types/settings';

export type ParamBinding = ActionConfig['param_bindings'][number];

export interface ScriptParam {
  name: string;
  label?: string;
  default?: string;
}

const MASKED_DEFAULTS = new Set(['******', '***']);

export function plainScriptDefault(param: ScriptParam): string {
  const raw = param.default;
  if (raw == null || MASKED_DEFAULTS.has(String(raw))) return '';
  return String(raw);
}

export function defaultBindingsFromScript(params: ScriptParam[]): ParamBinding[] {
  return params.map((param) => ({
    name: param.name,
    from: 'const',
    value: plainScriptDefault(param),
    allow_adjust: false,
  }));
}

export function alignParamBindings(
  params: ScriptParam[],
  existing: ParamBinding[] = [],
  options?: { reloadConstDefaults?: boolean }
): ParamBinding[] {
  const byName = new Map(existing.map((item) => [item.name, item]));
  return params.map((param) => {
    const prev = byName.get(param.name);
    if (!prev) {
      return {
        name: param.name,
        from: 'const',
        value: plainScriptDefault(param),
        allow_adjust: false,
      };
    }
    if (prev.from === 'field') {
      return {
        name: param.name,
        from: 'field',
        value: prev.value,
        allow_adjust: false,
      };
    }
    return {
      name: param.name,
      from: 'const',
      value: options?.reloadConstDefaults ? plainScriptDefault(param) : prev.value,
      allow_adjust: prev.allow_adjust === true,
    };
  });
}

export function adjustableConstBindings(bindings: ParamBinding[] = []): ParamBinding[] {
  return bindings.filter((item) => item.from === 'const' && item.allow_adjust === true);
}

export function fieldBindingsIncomplete(bindings: ParamBinding[] = []): boolean {
  return bindings.some((item) => item.from === 'field' && !String(item.value || '').trim());
}
```

同时把 `web/src/app/alarm/types/settings.ts` 的绑定类型改为：

```typescript
param_bindings: Array<{
  name: string;
  from: 'field' | 'const';
  value: string;
  allow_adjust?: boolean;
}>;
```

`ActionRuleListItem` 增加 `auto_execute?: boolean`（缺省按开）。

- [ ] **Step 4: Run tests to verify they pass**

Run: 同 Step 2。Expected: PASS。

---

### Task 7: 参数表支持手动填写 / 变量传递 / 执行时可改

**Files:**
- Modify: `web/src/app/alarm/(pages)/settings/actionRules/components/fieldBindingTable.tsx`
- Modify: `web/src/app/alarm/locales/zh.json`
- Modify: `web/src/app/alarm/locales/en.json`
- Test: `web/scripts/alarm-job-binding-alert-id-test.ts`（保持告警 ID 选项仍在变量下拉里）

- [ ] **Step 1: Extend contract test and locales**

`zh.json` / `en.json` 的 `settings` 增加（已有 `actionParamFrom` / `actionParamField` / `actionParamConst` 则复用，不要重复 key）：

```json
"actionAutoExecute": "自动执行",
"actionAutoExecuteTip": "关闭后告警命中不自动跑，仍可手动执行",
"actionParamValue": "参数值",
"actionParamAllowAdjust": "执行时可改",
"actionReloadParams": "从作业模板重新加载",
"actionExecuteParams": "执行参数",
"actionExecuteParamsTip": "以下为允许手动调整的参数，确认后执行"
```

英文对应：`Auto Execute`、`When off, matching alerts do not run automatically; manual run remains available.`、`Value`、`Editable at run`、`Reload from job template`、`Execution parameters`、`Only adjustable constants are shown. Confirm to run.`

- [ ] **Step 2: Rewrite FieldBindingTable**

三列：参数名、取值方式（手动填写=`const` / 变量传递=`field`）、值、执行时可改。

- `from=const`：`Input`，值为绑定 `value`；`Switch` 控制 `allow_adjust`，默认关。
- `from=field`：现有告警字段 `Select`（继续含 `alert_id`，不含 `source_id`）；不渲染可改开关，更新时去掉 `allow_adjust`。
- 切到 `const` 时 `allow_adjust` 置 `false`，`value` 若原是字段路径则改为该行 `record.default` 的明文（脱敏则空）。
- 切到 `field` 时 `value` 置空，等待选择。
- 变量列继续 `allowClear`。
- 不要把 `from` 写死为 `field`。

`alert_id` 选项契约测试仍应对 `fieldBindingTable.tsx` 匹配 `label: '告警ID'` 与 `value: 'alert_id'`。

- [ ] **Step 3: Run contract test**

```bash
cd web && pnpm exec tsx scripts/alarm-job-binding-alert-id-test.ts
```

Expected: PASS。

---

### Task 8: 规则抽屉：自动执行、选作业回写、打开对齐、重新加载

**Files:**
- Modify: `web/src/app/alarm/(pages)/settings/actionRules/components/operateModal.tsx`
- Test: `web/src/app/alarm/components/__tests__/monitor-source-settings-chain.test.tsx`（现有 ActionModal 提交 fixture 补 `auto_execute: true`，避免回归）

- [ ] **Step 1: Wire form fields**

- `is_active` 旁增加 `auto_execute` Switch，`valuePropName="checked"`，新建默认 `true`，编辑缺省也当 `true`。
- `handleScriptChange`：`form.setFieldValue('param_bindings', defaultBindingsFromScript(params))`，不要清空成 `[]`。
- 编辑打开且已有 `script_id`：`fetchScriptDetail` 后 `alignParamBindings(params, config.param_bindings || [])` 再 `setFieldsValue`。不要用 `reloadConstDefaults`。
- 参数表上方放「从作业模板重新加载」按钮：再拉脚本详情，`alignParamBindings(..., { reloadConstDefaults: true })`。失败 `message.error`，表不动。
- `onFinish`：若 `fieldBindingsIncomplete(paramBindings)` 则 `message.error` 并 return。payload 顶层带 `auto_execute`。`from=field` 不要把 `allow_adjust: true` 提交上去（后端也会剥掉）。
- `FieldBindingTable` 继续吃 `scriptParams`，以便切到 const 时能读 `default`。

- [ ] **Step 2: Keep settings chain fixture valid**

`monitor-source-settings-chain.test.tsx` 里 ActionModal extra 增加 `auto_execute: true`。若该测试只断言 create/update 被调用，不要改交互语义。

- [ ] **Step 3: Run focused frontend tests**

```bash
cd web && pnpm exec vitest run src/app/alarm/utils/__tests__/actionParamBindings.test.ts src/app/alarm/components/__tests__/monitor-source-settings-chain.test.tsx
```

Expected: PASS。

---

### Task 9: 手动执行弹框（告警下拉 + 再次执行）

**Files:**
- Create: `web/src/app/alarm/(pages)/alarms/components/manualActionExecuteModal.tsx`
- Modify: `web/src/app/alarm/(pages)/alarms/components/alarmAction.tsx`
- Modify: `web/src/app/alarm/(pages)/alarms/components/actionTimeline.tsx`
- Modify: `web/src/app/alarm/api/settings.ts`
- Modify: `web/scripts/alarm-manual-trigger-idempotency-test.ts`

- [ ] **Step 1: Update API and contract test first**

`manualTriggerAction` 保持 `Idempotency-Key: crypto.randomUUID()`，body 允许：

```typescript
post('/alerts/api/action_execution/manual_trigger/', params, {
  headers: { 'Idempotency-Key': crypto.randomUUID() },
});
```

`params` 可为 `{ alert_id, rule_id, param_overrides? }`。

把 `alarm-manual-trigger-idempotency-test.ts` 从断言「两个组件直接 `manualTriggerAction({ alert_id, rule_id })`」改为：

- `settings.ts` 仍打 `manual_trigger` 且带 `Idempotency-Key`
- `alarmAction.tsx` 与 `actionTimeline.tsx` **都不** 直接出现 `/action_execution/manual_trigger/`
- 两文件都引用 `manualActionExecuteModal` 或调用共享函数 `runManualActionTrigger`
- 弹框组件源码包含 `manualTriggerAction(`，且在有 `adjustableConstBindings` 时先开 Modal，取消路径不调用 API

- [ ] **Step 2: Implement modal**

`manualActionExecuteModal.tsx` 导出：

```typescript
export async function runManualActionTrigger(options: {
  alertId: string;
  rule: Pick<ActionRuleListItem, 'id' | 'action_config' | 'name'>;
  trigger: (body: { alert_id: string; rule_id: number; param_overrides?: Record<string, string> }) => Promise<unknown>;
}): Promise<'cancelled' | 'triggered'>
```

逻辑：

1. `const adjustable = adjustableConstBindings(rule.action_config?.param_bindings || [])`
2. 若长度为 0：直接 `trigger({ alert_id, rule_id: rule.id })`，返回 `'triggered'`
3. 否则 `Modal.confirm`，`content` 为各可改项的 `Input`，初始值为绑定 `value`。用一个可变对象收集编辑结果。
4. 点确定：`trigger({ alert_id, rule_id, param_overrides: edited })`
5. 点取消 / 关闭：不调用 `trigger`，返回 `'cancelled'`

`alarmAction.handleManualTrigger` 与 `actionTimeline.handleRerun` 都改为调用该函数；成功再 `message.success` 并刷新。`rule` 必须带 `action_config`（列表接口已返回）。时间线只有 `item.rule` id 时，用当前页已加载的 execution 不够，则 `getActionRule(item.rule)` 再弹；若不想多一次请求，执行记录 serializer 不扩范围——计划采用 **再次执行时用 `getActionRule(ruleId)` 取最新绑定**，避免用过期执行记录当配置。

- [ ] **Step 3: Run contract test**

```bash
cd web && pnpm exec tsx scripts/alarm-manual-trigger-idempotency-test.ts
```

Expected: PASS。

---

### Task 10: 回归验证

- [ ] **Step 1: Backend focused tests**

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest \
  apps/alerts/tests/test_action_payload_pure.py \
  apps/alerts/tests/test_action_engine_service.py \
  apps/alerts/tests/test_action_rule_views.py \
  apps/alerts/tests/test_job_handler_service.py \
  apps/alerts/tests/test_manual_trigger_views.py \
  apps/alerts/tests/bdd/test_action_engine_bdd.py \
  --no-cov
```

Expected: 全部 PASS。

- [ ] **Step 2: Frontend focused tests**

```bash
cd web && pnpm exec vitest run src/app/alarm/utils/__tests__/actionParamBindings.test.ts \
  && pnpm exec tsx scripts/alarm-job-binding-alert-id-test.ts \
  && pnpm exec tsx scripts/alarm-manual-trigger-idempotency-test.ts
```

若改了 `operateModal` 类型，再跑 `cd web && pnpm type-check`。Expected: PASS。

---

## Spec coverage

| 规格条目 | 任务 |
|---|---|
| 选作业回写明文默认值 / 脱敏为空 | Task 6, 8 |
| 每项手动或变量；变量必须选字段才能保存 | Task 3, 7, 8 |
| 仅 const 可 `allow_adjust`，默认关 | Task 3, 6, 7 |
| 自动执行默认开，存量开，关掉不自动跑 | Task 2 |
| 停用规则手动也不可跑 | Task 5 |
| 手动覆盖非法不建记录；合法传入 handler | Task 5, 4 |
| 弹框只展示可改手填；无可改不弹；取消不请求 | Task 9 |
| 打开编辑结构对齐；重新加载覆盖 const | Task 6, 8 |
| 下发顺序跟脚本；删除的参数不下发 | Task 1, 4 |
| 不改作业执行接口 | 全任务不碰 `job_mgmt` |

## 明确不做（计划内也不做）

- 提交 git
- 改 `job_script_execute` / `ScriptParamsService`
- Playbook / ITSM / Webhook
- 主机绑定改造成参数表
- 规则内存加密手填值
