# 节点管理 Agent 状态筛选与跨页勾选 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在节点清单组合筛选中按 Sidecar 在线/离线和托管组件状态圈节点，分页前过滤，并让勾选跨页保留后可批量处置。

**Architecture:** 状态命中口径抽成 `node_status_filter` 纯函数，供 `NodeFilterHandler` 在搜索分页前过滤；列表展示继续走 `NodeService.process_node_data`，但空跑错误改写必须调用同一函数以免漂移。前端只给 SearchCombination 加字段，并用节点快照 Map + `preserveSelectedRowKeys` 做跨页勾选。

**Tech Stack:** Django ORM / JSONField、现有 `POST /node_mgmt/api/node/search/`、`SearchCombination`、Ant Design Table `rowSelection`、pytest、vitest。

**规格:** `specs/changes/node-mgmt-agent-status-filter/spec.md`

---

## File structure

| 文件 | 职责 |
|---|---|
| `server/apps/node_mgmt/services/node_status_filter.py` | 在线窗口、组件状态码、合并托管清单、空跑改写、单节点是否命中 |
| `server/apps/node_mgmt/views/node.py` | `NodeFilterHandler` 增加 `active` / `collector_status`（`collector_name` 作为限定） |
| `server/apps/node_mgmt/services/node.py` | `process_node_data` 改用共享空跑改写，避免列表与筛选口径分裂 |
| `server/apps/node_mgmt/tests/test_node_status_filter.py` | 纯函数命中口径 |
| `server/apps/node_mgmt/tests/test_b75_node_filter_handler.py` | QuerySet 过滤 |
| `server/apps/node_mgmt/tests/test_node_viewset_search_update_enum.py` | 搜索分页前过滤 |
| `web/src/app/node-manager/utils/nodeListSelection.ts` | 跨页勾选快照 Map |
| `web/src/app/node-manager/hooks/node.tsx` | 组合筛选字段 |
| `web/src/app/node-manager/(pages)/cloudregion/node/page.tsx` | 接筛选、跨页勾选、已选计数、批量用全集 |
| `web/src/app/node-manager/locales/{zh,en}.json` | 文案 |
| `web/src/app/node-manager/utils/__tests__/nodeListSelection.test.ts` | 跨页勾选与清空 |
| `web/src/app/node-manager/hooks/__tests__/nodeFieldConfigs.test.ts` | 筛选项存在 |

不要改 SearchCombination 控件本身。不要新增 OpenAPI、导入导出、全选全部结果。

---

### Task 1: 组件状态命中纯函数

**Files:**
- Create: `server/apps/node_mgmt/services/node_status_filter.py`
- Test: `server/apps/node_mgmt/tests/test_node_status_filter.py`

- [ ] **Step 1: Write the failing tests**

```python
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.services.node_status_filter import (
    INSTALL_STATUS_ERROR,
    INSTALL_STATUS_RUNNING,
    INSTALL_STATUS_SUCCESS,
    collector_status_codes_from_filter_values,
    hosted_collectors_for_filter,
    node_matches_collector_filter,
)


def test_not_started_alias_expands_to_reported_and_installed():
    assert collector_status_codes_from_filter_values(["not_started"]) == {4, 11}


def test_unknown_status_values_are_dropped():
    assert collector_status_codes_from_filter_values(["2", "nope", 99]) == {2}


def test_empty_hosted_list_does_not_match():
    assert node_matches_collector_filter([], wanted_codes={2}, collector_name=None) is False


def test_any_collector_error_matches():
    hosted = hosted_collectors_for_filter(
        reported=[{"collector_id": "telegraf_linux", "status": 0}, {"collector_id": "vector_linux", "status": 2}],
        install_rows=[],
        collector_name_by_id={"telegraf_linux": "Telegraf", "vector_linux": "Vector"},
    )
    assert node_matches_collector_filter(hosted, wanted_codes={2}, collector_name=None) is True


def test_named_collector_ignores_other_component_error():
    hosted = hosted_collectors_for_filter(
        reported=[{"collector_id": "telegraf_linux", "status": 0}, {"collector_id": "vector_linux", "status": 2}],
        install_rows=[],
        collector_name_by_id={"telegraf_linux": "Telegraf", "vector_linux": "Vector"},
    )
    assert node_matches_collector_filter(hosted, wanted_codes={2}, collector_name="Telegraf") is False
    assert node_matches_collector_filter(hosted, wanted_codes={2}, collector_name="Vector") is True


def test_name_match_is_case_insensitive_and_ignores_os_suffix_id():
    hosted = hosted_collectors_for_filter(
        reported=[{"collector_id": "telegraf_windows", "status": 2}],
        install_rows=[],
        collector_name_by_id={"telegraf_windows": "Telegraf"},
    )
    assert node_matches_collector_filter(hosted, wanted_codes={2}, collector_name="telegraf") is True


def test_install_only_collector_is_merged_when_absent_from_reported():
    hosted = hosted_collectors_for_filter(
        reported=[{"collector_id": "telegraf_linux", "status": 0}],
        install_rows=[
            {"collector_id": "telegraf_linux", "status": INSTALL_STATUS_SUCCESS},
            {"collector_id": "vector_linux", "status": INSTALL_STATUS_ERROR},
        ],
        collector_name_by_id={"telegraf_linux": "Telegraf", "vector_linux": "Vector"},
    )
    ids = [item["collector_id"] for item in hosted]
    assert ids == ["telegraf_linux", "vector_linux"]
    assert node_matches_collector_filter(hosted, wanted_codes={12}, collector_name=None) is True


def test_ignore_error_empty_config_displays_as_normal():
    hosted = hosted_collectors_for_filter(
        reported=[
            {
                "collector_id": "filebeat_linux",
                "status": 2,
                "verbose_message": CollectorConstants.IGNORE_ERROR_EMPTY_CONFIG_MESSAGES[1],
            }
        ],
        install_rows=[],
        collector_name_by_id={"filebeat_linux": "Filebeat"},
    )
    assert hosted[0]["status"] == 0
    assert node_matches_collector_filter(hosted, wanted_codes={2}, collector_name=None) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/node_mgmt/tests/test_node_status_filter.py --no-cov -q
```

Expected: FAIL with import error (`node_status_filter` does not exist).

- [ ] **Step 3: Write minimal implementation**

Create `server/apps/node_mgmt/services/node_status_filter.py`:

```python
from apps.node_mgmt.constants.collector import CollectorConstants

ACTIVE_WINDOW_SECONDS = 60

COLLECTOR_STATUS_NORMAL = 0
COLLECTOR_STATUS_UNKNOWN = 1
COLLECTOR_STATUS_ERROR = 2
COLLECTOR_STATUS_STOPPED = 3
COLLECTOR_STATUS_NOT_STARTED = 4
COLLECTOR_STATUS_INSTALLING = 10
COLLECTOR_STATUS_INSTALLED_NOT_STARTED = 11
COLLECTOR_STATUS_FAIL_INSTALL = 12

INSTALL_STATUS_SUCCESS = "success"
INSTALL_STATUS_ERROR = "error"
INSTALL_STATUS_RUNNING = "running"

ALLOWED_COLLECTOR_STATUS_CODES = {
    COLLECTOR_STATUS_NORMAL,
    COLLECTOR_STATUS_UNKNOWN,
    COLLECTOR_STATUS_ERROR,
    COLLECTOR_STATUS_STOPPED,
    COLLECTOR_STATUS_NOT_STARTED,
    COLLECTOR_STATUS_INSTALLING,
    COLLECTOR_STATUS_INSTALLED_NOT_STARTED,
    COLLECTOR_STATUS_FAIL_INSTALL,
}

STATUS_FILTER_ALIASES = {
    "not_started": {COLLECTOR_STATUS_NOT_STARTED, COLLECTOR_STATUS_INSTALLED_NOT_STARTED},
}


def collector_status_codes_from_filter_values(values):
    codes = set()
    if not values:
        return codes
    if not isinstance(values, (list, tuple, set)):
        values = [values]
    for raw in values:
        if raw is None or raw == "":
            continue
        key = str(raw).strip().lower()
        if key in STATUS_FILTER_ALIASES:
            codes.update(STATUS_FILTER_ALIASES[key])
            continue
        try:
            code = int(raw)
        except (TypeError, ValueError):
            continue
        if code in ALLOWED_COLLECTOR_STATUS_CODES:
            codes.add(code)
    return codes


def install_row_display_status(install_status):
    if install_status == INSTALL_STATUS_SUCCESS:
        return COLLECTOR_STATUS_INSTALLED_NOT_STARTED
    if install_status == INSTALL_STATUS_ERROR:
        return COLLECTOR_STATUS_FAIL_INSTALL
    return COLLECTOR_STATUS_INSTALLING


def apply_display_collector_status(status, collector_name, verbose_message=""):
    try:
        display_status = int(status)
    except (TypeError, ValueError):
        return COLLECTOR_STATUS_UNKNOWN
    if display_status == COLLECTOR_STATUS_ERROR and collector_name in CollectorConstants.IGNORE_ERROR_COLLECTORS:
        message = verbose_message or ""
        if any(token in message for token in CollectorConstants.IGNORE_ERROR_COLLECTORS_MESSAGES):
            return COLLECTOR_STATUS_NORMAL
    return display_status


def _normalize_name(value):
    return str(value or "").strip().lower()


def collector_name_matches(collector_name, wanted_name):
    if not wanted_name:
        return True
    return _normalize_name(collector_name) == _normalize_name(wanted_name)


def hosted_collectors_for_filter(reported, install_rows, collector_name_by_id):
    hosted = []
    seen_ids = set()
    for item in reported or []:
        if not isinstance(item, dict):
            continue
        collector_id = item.get("collector_id")
        if collector_id in (None, ""):
            continue
        collector_id = str(collector_id)
        seen_ids.add(collector_id)
        name = collector_name_by_id.get(collector_id) or item.get("collector_name")
        hosted.append(
            {
                "collector_id": collector_id,
                "collector_name": name,
                "status": apply_display_collector_status(
                    item.get("status"),
                    name,
                    item.get("verbose_message") or "",
                ),
            }
        )
    for row in install_rows or []:
        if not isinstance(row, dict):
            continue
        collector_id = row.get("collector_id")
        if collector_id in (None, "") or str(collector_id) in seen_ids:
            continue
        collector_id = str(collector_id)
        name = collector_name_by_id.get(collector_id) or row.get("collector_name")
        hosted.append(
            {
                "collector_id": collector_id,
                "collector_name": name,
                "status": install_row_display_status(row.get("status")),
            }
        )
    return hosted


def node_matches_collector_filter(hosted, wanted_codes, collector_name=None):
    if not wanted_codes:
        return True
    wanted_name = (collector_name or "").strip() or None
    for item in hosted or []:
        if wanted_name and not collector_name_matches(item.get("collector_name"), wanted_name):
            continue
        try:
            status = int(item.get("status"))
        except (TypeError, ValueError):
            continue
        if status in wanted_codes:
            return True
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run the same pytest command as Step 2.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/apps/node_mgmt/services/node_status_filter.py server/apps/node_mgmt/tests/test_node_status_filter.py
git commit -m "$(cat <<'EOF'
feat(node-mgmt): 抽出节点组件状态筛选口径

列表与搜索必须共用托管组件合并和空跑错误改写，避免筛到的集合和表格不一致。
EOF
)"
```

---

### Task 2: NodeFilterHandler 接入在线状态和组件状态

**Files:**
- Modify: `server/apps/node_mgmt/views/node.py`
- Modify: `server/apps/node_mgmt/tests/test_b75_node_filter_handler.py`
- Modify: `server/apps/node_mgmt/models/installer.py` 仅当测试需要导入 `NodeCollectorInstallStatus`（已存在，不改模型）

- [ ] **Step 1: Write failing QuerySet tests**

Append to `server/apps/node_mgmt/tests/test_b75_node_filter_handler.py`:

```python
from datetime import timedelta

from django.utils import timezone as dj_timezone

from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.models.installer import NodeCollectorInstallStatus
from apps.node_mgmt.models.sidecar import Collector


def _set_updated_at(node, *, seconds_ago):
    Node.objects.filter(id=node.id).update(
        updated_at=dj_timezone.now() - timedelta(seconds=seconds_ago)
    )
    node.refresh_from_db()


@pytest.mark.django_db
def test_handle_active_true_keeps_recent_heartbeat(nodes):
    region, n1, n2 = nodes
    _set_updated_at(n1, seconds_ago=10)
    _set_updated_at(n2, seconds_ago=120)
    result = H.handle_active_filter(Node.objects.all(), [{"lookup_expr": "in", "value": ["true"]}])
    assert list(result) == [n1]


@pytest.mark.django_db
def test_handle_active_both_values_does_not_restrict(nodes):
    region, n1, n2 = nodes
    result = H.handle_active_filter(
        Node.objects.all(),
        [{"lookup_expr": "in", "value": ["true", "false"]}],
    )
    assert result.count() == 2


@pytest.mark.django_db
def test_handle_collector_status_any_error(nodes):
    region, n1, n2 = nodes
    n1.status = {"collectors": [{"collector_id": "telegraf_linux", "status": 2}]}
    n1.save(update_fields=["status"])
    Collector.objects.create(
        id="telegraf_linux",
        name="Telegraf",
        service_type="exec",
        node_operating_system="linux",
        executable_path="/bin/telegraf",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
    )
    result = H.handle_collector_status_filter(
        Node.objects.all(),
        [{"lookup_expr": "in", "value": ["2"]}],
        collector_name_conditions=None,
    )
    assert list(result) == [n1]


@pytest.mark.django_db
def test_handle_collector_status_named_and_install_overlay(nodes):
    region, n1, n2 = nodes
    n1.status = {"collectors": [{"collector_id": "telegraf_linux", "status": 0}]}
    n1.save(update_fields=["status"])
    Collector.objects.create(
        id="telegraf_linux",
        name="Telegraf",
        service_type="exec",
        node_operating_system="linux",
        executable_path="/bin/telegraf",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
    )
    vector = Collector.objects.create(
        id="vector_linux",
        name="Vector",
        service_type="exec",
        node_operating_system="linux",
        executable_path="/bin/vector",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
    )
    NodeCollectorInstallStatus.objects.create(
        node=n1, collector=vector, status="error", result={}
    )
    named_miss = H.handle_collector_status_filter(
        Node.objects.all(),
        [{"lookup_expr": "in", "value": ["12"]}],
        collector_name_conditions=[{"lookup_expr": "in", "value": ["Telegraf"]}],
    )
    assert named_miss.count() == 0
    named_hit = H.handle_collector_status_filter(
        Node.objects.all(),
        [{"lookup_expr": "in", "value": ["12"]}],
        collector_name_conditions=[{"lookup_expr": "in", "value": ["Vector"]}],
    )
    assert list(named_hit) == [n1]


@pytest.mark.django_db
def test_apply_filters_ands_active_and_os(nodes):
    region, n1, n2 = nodes
    _set_updated_at(n1, seconds_ago=10)
    _set_updated_at(n2, seconds_ago=10)
    result = H.apply_filters(
        Node.objects.all(),
        {
            "operating_system": [{"value": "linux", "lookup_expr": "exact"}],
            "active": [{"lookup_expr": "in", "value": ["true"]}],
        },
    )
    assert list(result) == [n1]


@pytest.mark.django_db
def test_collector_name_without_status_is_ignored(nodes):
    region, n1, n2 = nodes
    result = H.apply_filters(
        Node.objects.all(),
        {"collector_name": [{"lookup_expr": "in", "value": ["Telegraf"]}]},
    )
    assert result.count() == 2


@pytest.mark.django_db
def test_invalid_collector_status_is_ignored(nodes):
    result = H.apply_filters(
        Node.objects.all(),
        {"collector_status": [{"lookup_expr": "in", "value": ["nope"]}]},
    )
    assert result.count() == 2
```

Collector 创建字段与 `test_current_team_data_scope.py` 保持一致。

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/node_mgmt/tests/test_b75_node_filter_handler.py --no-cov -q
```

Expected: FAIL (`handle_active_filter` missing).

- [ ] **Step 3: Implement handlers**

In `NodeFilterHandler` (`server/apps/node_mgmt/views/node.py`):

1. Import:

```python
from datetime import timedelta

from django.utils import timezone as dj_timezone

from apps.node_mgmt.models.installer import NodeCollectorInstallStatus
from apps.node_mgmt.models.sidecar import Collector
from apps.node_mgmt.services.node_status_filter import (
    ACTIVE_WINDOW_SECONDS,
    collector_status_codes_from_filter_values,
    hosted_collectors_for_filter,
    node_matches_collector_filter,
)
```

2. Add helpers on the class (keep next to `handle_upgradeable_filter`):

```python
    @staticmethod
    def _condition_values(conditions):
        values = []
        if not conditions or not isinstance(conditions, list):
            return values
        for condition in conditions:
            if not isinstance(condition, dict):
                continue
            value = condition.get("value")
            if value is None or value == "":
                continue
            if isinstance(value, (list, tuple)):
                values.extend(value)
            else:
                values.append(value)
        return values

    @staticmethod
    def handle_active_filter(queryset, conditions):
        values = NodeFilterHandler._condition_values(conditions)
        wanted = set()
        for value in values:
            normalized = NodeFilterHandler.normalize_bool_value(value)
            if normalized is not None:
                wanted.add(normalized)
        if not wanted or (True in wanted and False in wanted):
            return queryset
        cutoff = dj_timezone.now() - timedelta(seconds=ACTIVE_WINDOW_SECONDS)
        if True in wanted:
            return queryset.filter(updated_at__gte=cutoff)
        return queryset.filter(updated_at__lt=cutoff)

    @staticmethod
    def handle_collector_status_filter(queryset, conditions, collector_name_conditions=None):
        wanted_codes = collector_status_codes_from_filter_values(
            NodeFilterHandler._condition_values(conditions)
        )
        if not wanted_codes:
            return queryset
        name_values = [
            str(item).strip()
            for item in NodeFilterHandler._condition_values(collector_name_conditions)
            if str(item).strip()
        ]
        collector_name = name_values[-1] if len(name_values) == 1 else None
        if len(name_values) > 1:
            # 多选组件名：任一名称命中即可，在循环里 OR
            collector_name = name_values

        node_ids = list(queryset.values_list("id", flat=True))
        if not node_ids:
            return queryset.none()

        collector_name_by_id = dict(Collector.objects.values_list("id", "name"))
        install_by_node = {}
        for row in NodeCollectorInstallStatus.objects.filter(node_id__in=node_ids).values(
            "node_id", "collector_id", "status"
        ):
            install_by_node.setdefault(row["node_id"], []).append(row)

        matched_ids = []
        for node_id, status in queryset.filter(id__in=node_ids).values_list("id", "status"):
            hosted = hosted_collectors_for_filter(
                (status or {}).get("collectors"),
                install_by_node.get(node_id, []),
                collector_name_by_id,
            )
            if isinstance(collector_name, list):
                if any(
                    node_matches_collector_filter(hosted, wanted_codes, name)
                    for name in collector_name
                ):
                    matched_ids.append(node_id)
            elif node_matches_collector_filter(hosted, wanted_codes, collector_name):
                matched_ids.append(node_id)
        return queryset.filter(id__in=matched_ids)
```

多选组件名用 OR 与规格一致（同一字段多选 OR）。若 `name_values` 为空则 `collector_name=None`（任意组件）。

3. Update `apply_filters` `SPECIAL_FIELDS`:

```python
        SPECIAL_FIELDS = {
            "upgradeable": cls.handle_upgradeable_filter,
            "active": cls.handle_active_filter,
            "collector_status": None,
        }
```

`collector_status` 不能直接塞单参数 handler。改成：

```python
        if not filters:
            return queryset

        special_order = []
        standard_filters = {}
        collector_status_conditions = None
        collector_name_conditions = filters.get("collector_name")

        for field_name, conditions in filters.items():
            if field_name == "collector_name":
                continue
            if field_name == "upgradeable":
                special_order.append(("upgradeable", conditions))
            elif field_name == "active":
                special_order.append(("active", conditions))
            elif field_name == "collector_status":
                collector_status_conditions = conditions
            else:
                standard_filters[field_name] = conditions

        if standard_filters:
            q_filters = cls.build_standard_filters(standard_filters)
            if q_filters:
                queryset = queryset.filter(q_filters).distinct()

        for field_name, conditions in special_order:
            if field_name == "upgradeable":
                queryset = cls.handle_upgradeable_filter(queryset, conditions)
            elif field_name == "active":
                queryset = cls.handle_active_filter(queryset, conditions)

        if collector_status_conditions is not None:
            queryset = cls.handle_collector_status_filter(
                queryset,
                collector_status_conditions,
                collector_name_conditions=collector_name_conditions,
            )

        return queryset
```

`collector_name` 单独出现时被 skip，queryset 不变。

- [ ] **Step 4: Run tests to verify they pass**

Same pytest command as Step 2.

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add server/apps/node_mgmt/views/node.py server/apps/node_mgmt/tests/test_b75_node_filter_handler.py
git commit -m "$(cat <<'EOF'
feat(node-mgmt): 节点搜索支持在线状态和组件状态过滤

过滤在分页前完成，组件状态与列表同一套合并口径，避免只筛当前页。
EOF
)"
```

---

### Task 3: 搜索接口分页前过滤

**Files:**
- Modify: `server/apps/node_mgmt/tests/test_node_viewset_search_update_enum.py`

不要 mock 掉 `NodeFilterHandler.apply_filters`。现有测试 mock 了 `process_node_data`，本任务新增的用例可以继续 mock 展示 enrich，但必须走真实 `apply_filters`。

- [ ] **Step 1: Write failing search pagination test**

Append:

```python
from datetime import timedelta

from django.utils import timezone as dj_timezone

from apps.node_mgmt.models.sidecar import Collector


def test_search_filters_collector_status_before_pagination(monkeypatch):
    region, keep, other = _region_and_nodes()
    Collector.objects.create(
        id="telegraf_linux",
        name="Telegraf",
        service_type="exec",
        node_operating_system="linux",
        executable_path="/bin/telegraf",
        execute_parameters="",
        created_by="tester",
        updated_by="tester",
    )
    keep.status = {"collectors": [{"collector_id": "telegraf_linux", "status": 2}]}
    keep.save(update_fields=["status"])
    other.status = {"collectors": [{"collector_id": "telegraf_linux", "status": 0}]}
    other.save(update_fields=["status"])
    monkeypatch.setattr(node_view, "get_node_permission", lambda request: {})
    monkeypatch.setattr(
        node_view,
        "get_catalog_node_queryset",
        lambda request, permission=None: Node.objects.filter(id__in=[keep.id, other.id]),
    )
    monkeypatch.setattr(node_view.NodeService, "process_node_data", staticmethod(lambda data: data))
    request = factory.post(
        "/node/search/?page=1&page_size=1",
        {"filters": {"collector_status": [{"lookup_expr": "in", "value": ["2"]}]}},
        format="json",
    )
    _auth(request)
    resp = node_view.NodeViewSet.as_view({"post": "search"})(request)
    resp.render()
    body = json.loads(resp.content)
    assert body["data"]["count"] == 1
    assert body["data"]["items"][0]["id"] == keep.id
```

- [ ] **Step 2: Run test**

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/node_mgmt/tests/test_node_viewset_search_update_enum.py::test_search_filters_collector_status_before_pagination --no-cov -q
```

若 Task 2 已接好，此测试应直接 PASS。若 FAIL，检查 `search()` 是否在 `paginate_queryset` 之前调用了 `apply_filters`（现网已是这个顺序，不要改成先分页）。

- [ ] **Step 3: Commit if new test was added**

```bash
git add server/apps/node_mgmt/tests/test_node_viewset_search_update_enum.py
git commit -m "$(cat <<'EOF'
test(node-mgmt): 锁定组件状态过滤发生在分页前

防止搜索接口先取一页再在内存里筛，把异常节点漏出第一页。
EOF
)"
```

---

### Task 4: 列表展示改用同一套空跑改写

**Files:**
- Modify: `server/apps/node_mgmt/services/node.py`（`process_node_data` 中 status==2 改写那段）
- Test: 若已有 `test_b75_node_service.py` 覆盖 Filebeat 空跑，跑它确认不回退；没有则在 `test_node_status_filter.py` 不必重复。

- [ ] **Step 1: Replace the inline rewrite**

把 `process_node_data` 里：

```python
                if collector["status"] == 2 and collector_obj:
                    if collector_obj.name in CollectorConstants.IGNORE_ERROR_COLLECTORS:
                        verbose_msg = collector.get("verbose_message", "")
                        if any(msg in verbose_msg for msg in CollectorConstants.IGNORE_ERROR_COLLECTORS_MESSAGES):
                            collector["status"] = 0
                            collector["message"] = "Running"
```

改成调用 `apply_display_collector_status`。改写后若状态变为 0，保持现有 `message = "Running"` 与 debug 日志模板（日志仍走 `from apps.core.logger import node_mgmt_logger as logger`，不要新加 traceback ERROR）。

```python
from apps.node_mgmt.services.node_status_filter import apply_display_collector_status

                previous_status = collector.get("status")
                collector["status"] = apply_display_collector_status(
                    previous_status,
                    collector_obj.name if collector_obj else None,
                    collector.get("verbose_message") or "",
                )
                if previous_status == 2 and collector["status"] == 0:
                    collector["message"] = "Running"
                    logger.debug(
                        "Changed status to Running for collector %s on node %s: %s",
                        collector_obj.name,
                        node.get("name", node["id"]),
                        (collector.get("verbose_message") or "").strip(),
                    )
```

注意：原先 debug 用了 f-string。仓库要求惰性参数，改成 `%s` 占位。这是这次改到该日志行时必须一起做的。

- [ ] **Step 2: Run related tests**

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/node_mgmt/tests/test_node_status_filter.py apps/node_mgmt/tests/test_b75_node_service.py apps/node_mgmt/tests/test_b75_node_filter_handler.py --no-cov -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add server/apps/node_mgmt/services/node.py
git commit -m "$(cat <<'EOF'
fix(node-mgmt): 列表组件状态改写与筛选共用函数

避免空跑错误在表格显示正常、筛选异常却仍命中。
EOF
)"
```

---

### Task 5: 组合筛选字段与文案

**Files:**
- Modify: `web/src/app/node-manager/hooks/node.tsx`
- Create: `web/src/app/node-manager/hooks/__tests__/nodeFieldConfigs.test.ts`
- Modify: `web/src/app/node-manager/locales/zh.json`
- Modify: `web/src/app/node-manager/locales/en.json`
- Modify: `web/src/app/node-manager/constants/collector.ts` 仅当需要导出扁平名称列表；优先在 hook 内 `Object.values(COLLECTOR_LABEL).flat()` 去重。

- [ ] **Step 1: Add i18n keys**

In both locale files under `node-manager.cloudregion.node`，紧挨 `controllerUpgradeable`：

zh:

```json
        "nodeActive": "在线状态",
        "collectorStatus": "组件状态",
        "collectorName": "组件名称",
        "selectedNodeCount": "已选 {count} 台"
```

en:

```json
        "nodeActive": "Agent Status",
        "collectorStatus": "Component Status",
        "collectorName": "Component",
        "selectedNodeCount": "{count} selected"
```

复用已有 `online` / `offline` / `normal` / `unknown` / `error` / `stopped` / `notStarted` / `installing` / `failInstall` 做选项文案。

- [ ] **Step 2: Write failing field-config test**

`useFieldConfigs` 是 hook。抽出纯函数 `buildNodeSearchFieldConfigs` 再让 hook 调用，测试纯函数。

Create `web/src/app/node-manager/hooks/__tests__/nodeFieldConfigs.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { buildNodeSearchFieldConfigs } from '../node';

const t = (key: string) => key;

describe('buildNodeSearchFieldConfigs', () => {
  it('adds active, collector status, and collector name fields', () => {
    const fields = buildNodeSearchFieldConfigs({
      t,
      installMethodMap: {
        auto: { text: 'Auto' },
        manual: { text: 'Manual' }
      }
    });
    const names = fields.map((item) => item.name);
    expect(names).toEqual(
      expect.arrayContaining(['active', 'collector_status', 'collector_name'])
    );
    const active = fields.find((item) => item.name === 'active');
    expect(active?.lookup_expr).toBe('in');
    expect(active?.options?.map((item) => item.id)).toEqual(['true', 'false']);
    const status = fields.find((item) => item.name === 'collector_status');
    expect(status?.options?.map((item) => item.id)).toEqual([
      '0',
      '1',
      '2',
      '3',
      'not_started',
      '10',
      '12'
    ]);
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd web && pnpm exec vitest run src/app/node-manager/hooks/__tests__/nodeFieldConfigs.test.ts
```

Expected: FAIL（`buildNodeSearchFieldConfigs` 未导出）。

- [ ] **Step 4: Implement `buildNodeSearchFieldConfigs` and use it in `useFieldConfigs`**

在 `web/src/app/node-manager/hooks/node.tsx` 增加：

```typescript
import { COLLECTOR_LABEL } from '@/app/node-manager/constants/collector';

export const buildNodeSearchFieldConfigs = ({
  t,
  installMethodMap
}: {
  t: (key: string, fallback?: string) => string;
  installMethodMap: Record<string, { text?: string }>;
}): FieldConfig[] => {
  const collectorNames = Array.from(
    new Set(Object.values(COLLECTOR_LABEL).flat())
  ).map((name) => ({ id: name, name }));

  return [
    {
      name: 'name',
      label: t('node-manager.cloudregion.node.nodeName'),
      lookup_expr: 'icontains'
    },
    {
      name: 'ip',
      label: t('node-manager.cloudregion.node.ip'),
      lookup_expr: 'icontains'
    },
    {
      name: 'operating_system',
      label: t('node-manager.cloudregion.node.system'),
      lookup_expr: 'in',
      options: OPERATE_SYSTEMS.map((item) => ({
        id: item.value,
        name: item.label
      }))
    },
    {
      name: 'install_method',
      label: t('node-manager.cloudregion.node.installMethod'),
      lookup_expr: 'in',
      options: [
        { id: 'auto', name: installMethodMap['auto']?.text || 'Auto' },
        { id: 'manual', name: installMethodMap['manual']?.text || 'Manual' }
      ]
    },
    {
      name: 'upgradeable',
      label: t('node-manager.cloudregion.node.controllerUpgradeable'),
      lookup_expr: 'bool',
      options: [
        { id: 'true', name: t('common.yes') },
        { id: 'false', name: t('common.no') }
      ]
    },
    {
      name: 'cpu_architecture',
      label: t('node-manager.cloudregion.node.cpuArchitecture'),
      lookup_expr: 'in',
      options: [
        { id: 'x86_64', name: 'X86_64' },
        { id: 'arm64', name: 'ARM64' }
      ]
    },
    {
      name: 'active',
      label: t('node-manager.cloudregion.node.nodeActive'),
      lookup_expr: 'in',
      options: [
        { id: 'true', name: t('node-manager.cloudregion.node.online') },
        { id: 'false', name: t('node-manager.cloudregion.node.offline') }
      ]
    },
    {
      name: 'collector_status',
      label: t('node-manager.cloudregion.node.collectorStatus'),
      lookup_expr: 'in',
      options: [
        { id: '0', name: t('node-manager.cloudregion.node.normal') },
        { id: '1', name: t('node-manager.cloudregion.node.unknown') },
        { id: '2', name: t('node-manager.cloudregion.node.error') },
        { id: '3', name: t('node-manager.cloudregion.node.stopped') },
        { id: 'not_started', name: t('node-manager.cloudregion.node.notStarted') },
        { id: '10', name: t('node-manager.cloudregion.node.installing') },
        { id: '12', name: t('node-manager.cloudregion.node.failInstall') }
      ]
    },
    {
      name: 'collector_name',
      label: t('node-manager.cloudregion.node.collectorName'),
      lookup_expr: 'in',
      options: collectorNames
    }
  ];
};
```

`useFieldConfigs` 改为 `return useMemo(() => buildNodeSearchFieldConfigs({ t, installMethodMap }), [t, installMethodMap]);`

从 `export { ... }` 增加 `buildNodeSearchFieldConfigs`。

- [ ] **Step 5: Re-run vitest**

Same command as Step 3. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/app/node-manager/hooks/node.tsx web/src/app/node-manager/hooks/__tests__/nodeFieldConfigs.test.ts web/src/app/node-manager/locales/zh.json web/src/app/node-manager/locales/en.json
git commit -m "$(cat <<'EOF'
feat(node-manager): 节点组合筛选增加在线和组件状态

运维要在现有筛选入口圈 Sidecar 与托管组件，不另开一条筛选栏。
EOF
)"
```

---

### Task 6: 跨页勾选快照

**Files:**
- Create: `web/src/app/node-manager/utils/nodeListSelection.ts`
- Test: `web/src/app/node-manager/utils/__tests__/nodeListSelection.test.ts`

- [ ] **Step 1: Write failing tests**

```typescript
import { describe, expect, it } from 'vitest';
import {
  nextSelectedNodeMap,
  shouldClearNodeSelection
} from '../nodeListSelection';

const page1 = [
  { key: 'a', id: 'a', operating_system: 'linux', cpu_architecture: 'x86_64' },
  { key: 'b', id: 'b', operating_system: 'linux', cpu_architecture: 'x86_64' }
];
const page2 = [
  { key: 'c', id: 'c', operating_system: 'windows', cpu_architecture: 'x86_64' }
];

describe('nextSelectedNodeMap', () => {
  it('keeps previous page snapshots when selecting more keys', () => {
    const afterPage1 = nextSelectedNodeMap({
      previous: new Map(),
      selectedKeys: ['a'],
      currentPageRows: page1
    });
    const afterPage2 = nextSelectedNodeMap({
      previous: afterPage1,
      selectedKeys: ['a', 'c'],
      currentPageRows: page2
    });
    expect(afterPage2.get('a')?.operating_system).toBe('linux');
    expect(afterPage2.get('c')?.operating_system).toBe('windows');
  });

  it('drops snapshots for unselected keys', () => {
    const previous = nextSelectedNodeMap({
      previous: new Map(),
      selectedKeys: ['a', 'b'],
      currentPageRows: page1
    });
    const next = nextSelectedNodeMap({
      previous,
      selectedKeys: ['b'],
      currentPageRows: page1
    });
    expect([...next.keys()]).toEqual(['b']);
  });
});

describe('shouldClearNodeSelection', () => {
  it('clears when filters, unassigned scope, or cloud region change', () => {
    expect(shouldClearNodeSelection({ reason: 'filters' })).toBe(true);
    expect(shouldClearNodeSelection({ reason: 'unassigned' })).toBe(true);
    expect(shouldClearNodeSelection({ reason: 'cloudRegion' })).toBe(true);
    expect(shouldClearNodeSelection({ reason: 'pagination' })).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd web && pnpm exec vitest run src/app/node-manager/utils/__tests__/nodeListSelection.test.ts
```

Expected: FAIL.

- [ ] **Step 3: Implement**

```typescript
import type { TableDataItem } from '@/app/node-manager/types';

export type NodeSelectionClearReason =
  | 'filters'
  | 'unassigned'
  | 'cloudRegion'
  | 'pagination';

export function nextSelectedNodeMap({
  previous,
  selectedKeys,
  currentPageRows
}: {
  previous: Map<React.Key, TableDataItem>;
  selectedKeys: React.Key[];
  currentPageRows: TableDataItem[];
}): Map<React.Key, TableDataItem> {
  const pageByKey = new Map(
    currentPageRows.map((row) => [row.key ?? row.id, row] as const)
  );
  const next = new Map<React.Key, TableDataItem>();
  for (const key of selectedKeys) {
    const row = pageByKey.get(key) || previous.get(key);
    if (row) {
      next.set(key, row);
    }
  }
  return next;
}

export function shouldClearNodeSelection({
  reason
}: {
  reason: NodeSelectionClearReason;
}): boolean {
  return reason !== 'pagination';
}

export function selectedNodesFromMap(
  selectedKeys: React.Key[],
  selectedMap: Map<React.Key, TableDataItem>
): TableDataItem[] {
  return selectedKeys
    .map((key) => selectedMap.get(key))
    .filter((item): item is TableDataItem => Boolean(item));
}
```

若 `React.Key` 在非 tsx 文件报未导入，改用 `import type { Key } from 'react'`。

- [ ] **Step 4: Re-run vitest**

Same command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/node-manager/utils/nodeListSelection.ts web/src/app/node-manager/utils/__tests__/nodeListSelection.test.ts
git commit -m "$(cat <<'EOF'
feat(node-manager): 节点列表跨页勾选保留行快照

批量启停要校验全部已选节点的系统与架构，不能只看当前页。
EOF
)"
```

---

### Task 7: 接到节点清单页

**Files:**
- Modify: `web/src/app/node-manager/(pages)/cloudregion/node/page.tsx`

- [ ] **Step 1: Wire selection state**

1. `import` `nextSelectedNodeMap`、`selectedNodesFromMap`、`shouldClearNodeSelection`。
2. 增加 `const [selectedNodeMap, setSelectedNodeMap] = useState<Map<React.Key, TableDataItem>>(new Map());`
3. 抽 `clearNodeSelection`：`setSelectedRowKeys([]); setSelectedNodeMap(new Map());`
4. `onSelectChange` 改为：

```typescript
  const onSelectChange = (newSelectedRowKeys: React.Key[]) => {
    setSelectedRowKeys(newSelectedRowKeys);
    setSelectedNodeMap((previous) =>
      nextSelectedNodeMap({
        previous,
        selectedKeys: newSelectedRowKeys,
        currentPageRows: nodeList || []
      })
    );
  };
```

5. `rowSelection` 增加 `preserveSelectedRowKeys: true`。

6. 所有 `(nodeList || []).filter((item) => selectedRowKeys.includes(item.key))` 改为 `selectedNodesFromMap(selectedRowKeys, selectedNodeMap)`，包括：
   - `enableOperateCollecter`
   - `enableOperateController`
   - `getFirstSelectedNodeOS`
   - `handleSidecarMenuClick` 的 `list`
   - `handleCollectorMenuClick` 的 `selectedNodes`

7. `handleSearchChange`：若 `shouldClearNodeSelection({ reason: 'filters' })` 则 `clearNodeSelection()`，并把 pagination `current` 置 1。

8. `CatalogScopeSegmented` `onChange`：clear selection（reason `unassigned`）。

9. `useEffect` 依赖 `cloudId`：cloud 变化时 clear（reason `cloudRegion`）。翻页 effect 不要 clear。

10. 工具栏刷新按钮左侧或已选按钮旁展示：

```tsx
{selectedRowKeys.length > 0 ? (
  <span className="mr-[8px] text-[var(--color-text-3)]">
    {t('node-manager.cloudregion.node.selectedNodeCount', '', {
      count: selectedRowKeys.length
    })}
  </span>
) : null}
```

不要做「全选当前筛选结果」按钮。

- [ ] **Step 2: Type-check the touched files**

```bash
cd web && pnpm exec vitest run src/app/node-manager/utils/__tests__/nodeListSelection.test.ts src/app/node-manager/hooks/__tests__/nodeFieldConfigs.test.ts src/app/node-manager/utils/__tests__/nodeOperation.test.ts
```

然后：

```bash
cd web && pnpm type-check
```

Expected: 两步都 PASS。

- [ ] **Step 3: Commit**

```bash
git add web/src/app/node-manager/\(pages\)/cloudregion/node/page.tsx
git commit -m "$(cat <<'EOF'
feat(node-manager): 节点清单跨页勾选并按全集批量操作

翻页不再丢掉已选 Agent，系统架构校验和批量入口改为使用全部快照。
EOF
)"
```

---

### Task 8: 回归与规格状态

- [ ] **Step 1: Run backend slice**

```bash
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest \
  apps/node_mgmt/tests/test_node_status_filter.py \
  apps/node_mgmt/tests/test_b75_node_filter_handler.py \
  apps/node_mgmt/tests/test_node_viewset_search_update_enum.py \
  apps/node_mgmt/tests/test_b75_node_service.py \
  --no-cov
```

Expected: 全部 PASS。

- [ ] **Step 2: Run frontend slice**

```bash
cd web && pnpm exec vitest run src/app/node-manager/utils/__tests__/nodeListSelection.test.ts src/app/node-manager/hooks/__tests__/nodeFieldConfigs.test.ts src/app/node-manager/utils/__tests__/collectorStatusList.test.ts src/app/node-manager/utils/__tests__/nodeOperation.test.ts
```

Expected: 全部 PASS。

- [ ] **Step 3: Update spec status**

将 `specs/changes/node-mgmt-agent-status-filter/spec.md` 的 `Status: ready` 改为 `Status: implemented`，并在文末加一行验证命令与结果日期。不要归档或移动该文件。

- [ ] **Step 4: Commit spec status**

```bash
git add specs/changes/node-mgmt-agent-status-filter/spec.md
git commit -m "$(cat <<'EOF'
docs(node-mgmt): 标记 Agent 状态筛选规格已实现

与验证命令对齐，避免后续会话把已交付能力当成待做。
EOF
)"
```

---

## Spec coverage

| 规格点 | 任务 |
|---|---|
| 在线/离线 60 秒 | Task 2 `handle_active_filter` |
| 组件状态与列表同一口径 | Task 1 + Task 4 |
| 任意组件 / 指定组件名 | Task 1–2 |
| 未启动含 4 和 11 | Task 1 alias + Task 5 `not_started` |
| 状态多选 OR、与其它字段 AND | Task 2 `apply_filters` |
| 无组件不命中 | Task 1 |
| 空跑错误筛异常不中 | Task 1 + Task 4 |
| 非法条件忽略 | Task 2 |
| 分页前过滤 | Task 3 |
| 不新增权限 / OpenAPI | 未改权限装饰器 |
| 跨页勾选 + 快照 + 批量看全集 | Task 6–7 |
| 改筛选/未归属/云区域清空 | Task 6–7 |
| 已选台数 | Task 7 |
| 不做导入导出/全选全部 | 未列入任务 |

## 实现时注意

- `Node.updated_at` 带 `auto_now=True`，测试里必须用 `QuerySet.update` 改心跳时间。
- 组件过滤会读取已收窄 queryset 的 `id`/`status` 和一次安装状态查询；不要先 `list(Node.objects.all())`。
- 前端 `t` 的第二参数在本仓库部分调用是 fallback 字符串，`selectedNodeCount` 用 `t(key, '', { count })` 与现页其它带参文案一致。
