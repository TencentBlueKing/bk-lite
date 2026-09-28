# 节点管理 Agent 清单导出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在云区域节点清单工具栏同步导出 Excel：导出下拉显式选择已选择 / 当前页 / 全部，列和状态口径与列表一致。

**Architecture:** 导出动作复用列表的授权查询、`NodeFilterHandler` 和 `NodeService.process_node_data`，不做分页。行文案和 xlsx 字节放在 `node_export` 服务里，避免在 ViewSet 里拼表格。前端按下拉范围组请求：已选择/当前页映射为 ID 列表，全部只带筛选。下载走 `responseType: 'blob'`。

**Tech Stack:** Django ViewSet action、openpyxl、现有 `POST /node_mgmt/api/node/search/` 过滤口径、Ant Design Button、pytest、vitest。

**规格:** `specs/changes/node-mgmt-agent-export/spec.md`

**约束:** 最小化修改，不要改 `search()` 行为。不要新增 OpenAPI、导入、异步任务、字段选择器。

---

## File structure

| 文件 | 职责 |
|---|---|
| `server/apps/node_mgmt/services/node_export.py` | 上限、文案、行、xlsx 字节、文件名 |
| `server/apps/node_mgmt/views/node.py` | 新增 `export_excel` action，不改 `search` |
| `server/apps/node_mgmt/tests/test_node_export.py` | 行口径与工作簿 |
| `server/apps/node_mgmt/tests/test_node_viewset_export.py` | HTTP 集合、空结果、超限、已选 ID |
| `web/src/app/node-manager/utils/nodeListExport.ts` | 导出请求体 / query |
| `web/src/app/node-manager/utils/__tests__/nodeListExport.test.ts` | 已选择 / 当前页 / 全部 payload |
| `web/src/app/node-manager/api/useNodeApi.ts` | `exportNodeList` blob POST |
| `web/src/app/node-manager/(pages)/cloudregion/node/page.tsx` | 工具栏导出下拉 |
| `web/src/app/node-manager/locales/{zh,en}.json` | 空结果/超限提示（若走后端 message 则前端只加按钮文案） |

不要改 SearchCombination。不要把导出放进 Sidecar / 托管程序下拉。

验证命令（sqlite，禁止 migrate）：

```
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest <paths> --no-cov --nomigrations
cd web && pnpm exec vitest run src/app/node-manager/utils/__tests__/nodeListExport.test.ts
```

---

### Task 1: 导出行口径纯函数

**Files:**
- Create: `server/apps/node_mgmt/services/node_export.py`
- Test: `server/apps/node_mgmt/tests/test_node_export.py`

- [ ] **Step 1: Write the failing tests**

```python
from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.services.node_export import (
    EXPORT_LIMIT,
    build_export_filename,
    build_export_row,
    format_hosted_collectors_cell,
    format_organization_cell,
)


def test_export_limit_is_5000():
    assert EXPORT_LIMIT == 5000


def test_organization_cell_uses_names_not_ids():
    assert format_organization_cell([7, 8], {7: "alpha", 8: "beta"}, unassigned_label="未归属") == "alpha,beta"


def test_organization_cell_empty_is_unassigned():
    assert format_organization_cell([], {}, unassigned_label="未归属") == "未归属"


def test_hosted_cell_joins_display_name_and_status():
    cell = format_hosted_collectors_cell(
        [
            {"collector_name": "Telegraf", "status": 2},
            {"collector_name": "Vector", "status": 0},
        ],
        status_labels={0: "正常", 2: "异常"},
    )
    assert cell == "Telegraf:异常；Vector:正常"


def test_hosted_cell_empty_when_no_collectors():
    assert format_hosted_collectors_cell([], status_labels={}) == ""


def test_hosted_cell_uses_rewritten_status():
    cell = format_hosted_collectors_cell(
        [{"collector_name": "Filebeat", "status": 0, "verbose_message": CollectorConstants.IGNORE_ERROR_EMPTY_CONFIG_MESSAGES[1]}],
        status_labels={0: "正常", 2: "异常"},
    )
    assert cell == "Filebeat:正常"


def test_build_export_row_online_and_upgradeable():
    row = build_export_row(
        {
            "name": "keep-node",
            "ip": "10.0.0.1",
            "operating_system": "linux",
            "cpu_architecture": "x86_64",
            "node_type": "host",
            "install_method": "auto",
            "organization": [7],
            "active": True,
            "updated_at": "2026-09-28T12:00:00+00:00",
            "versions": [{"component_type": "controller", "version": "1.2.3", "upgradeable": True}],
            "status": {"collectors": [{"collector_name": "Telegraf", "status": 2}]},
        },
        labels={
            "unassigned": "未归属",
            "online": "在线",
            "offline": "离线",
            "yes": "是",
            "no": "否",
            "os": {"linux": "Linux", "windows": "Windows"},
            "install_method": {"auto": "远程", "manual": "手动"},
            "node_type": {"host": "主机节点", "container": "容器节点"},
            "collector_status": {0: "正常", 1: "未知的", 2: "异常", 3: "停止", 4: "未启动", 10: "安装中", 11: "未启动", 12: "安装失败"},
        },
        organization_names={7: "alpha"},
    )
    assert row[0] == "keep-node"
    assert row[1] == "10.0.0.1"
    assert row[7] == "在线"
    assert row[10] == "是"
    assert row[11] == "Telegraf:异常"


def test_filename_contains_region_and_xlsx():
    name = build_export_filename("默认云区域", stamp="20260928_120000")
    assert name == "节点清单_默认云区域_20260928_120000.xlsx"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/node_mgmt/tests/test_node_export.py --no-cov --nomigrations -q
```

Expected: FAIL（模块不存在）

- [ ] **Step 3: Write minimal implementation**

`server/apps/node_mgmt/services/node_export.py`:

```python
from io import BytesIO
from urllib.parse import quote

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from apps.node_mgmt.constants.node import NodeConstants
from apps.system_mgmt.models import Group

EXPORT_LIMIT = 5000
COLLECTOR_JOIN = "；"
ORG_JOIN = ","

EXPORT_HEADERS_ZH = [
    "节点名称",
    "IP",
    "操作系统",
    "CPU 架构",
    "节点类型",
    "安装方式",
    "组织",
    "在线状态",
    "最后上报时间",
    "控制器版本",
    "控制器可升级",
    "托管组件",
]

EXPORT_HEADERS_EN = [
    "Node Name",
    "IP",
    "OS",
    "CPU Architecture",
    "Node Type",
    "Install Method",
    "Organization",
    "Online Status",
    "Last Report Time",
    "Controller Version",
    "Controller Upgradeable",
    "Hosted Collectors",
]


def is_english_locale(locale):
    return str(locale or "").lower().startswith("en")


def export_labels(locale):
    english = is_english_locale(locale)
    if english:
        return {
            "unassigned": "Unassigned",
            "online": "Online",
            "offline": "Offline",
            "yes": "Yes",
            "no": "No",
            "os": {"linux": "Linux", "windows": "Windows"},
            "install_method": {"auto": "Remote", "manual": "Manual"},
            "node_type": {"host": "Host", "container": "Container"},
            "collector_status": {
                0: "Normal",
                1: "Unknown",
                2: "Error",
                3: "Stopped",
                4: "Not Started",
                10: "Installing",
                11: "Not Started",
                12: "Failed to Install",
            },
            "headers": EXPORT_HEADERS_EN,
            "empty": "No nodes to export",
            "over_limit": "Export exceeds the limit of {limit} nodes, current count is {count}.",
        }
    return {
        "unassigned": "未归属",
        "online": "在线",
        "offline": "离线",
        "yes": "是",
        "no": "否",
        "os": {NodeConstants.LINUX_OS: NodeConstants.LINUX_OS_DISPLAY, NodeConstants.WINDOWS_OS: NodeConstants.WINDOWS_OS_DISPLAY},
        "install_method": {"auto": "远程", "manual": "手动"},
        "node_type": {"host": "主机节点", "container": "容器节点"},
        "collector_status": {
            0: "正常",
            1: "未知的",
            2: "异常",
            3: "停止",
            4: "未启动",
            10: "安装中",
            11: "未启动",
            12: "安装失败",
        },
        "headers": EXPORT_HEADERS_ZH,
        "empty": "没有可导出的节点",
        "over_limit": "导出数量超过上限 {limit}，当前 {count} 台",
    }


def format_organization_cell(organization_ids, organization_names, unassigned_label):
    names = []
    for org_id in organization_ids or []:
        try:
            key = int(org_id)
        except (TypeError, ValueError):
            continue
        name = organization_names.get(key)
        if name:
            names.append(name)
    return ORG_JOIN.join(names) if names else unassigned_label


def _hosted_collectors(node):
    status = node.get("status") if isinstance(node.get("status"), dict) else {}
    reported = status.get("collectors") or []
    installed = status.get("collectors_install") or []
    if not isinstance(reported, list):
        reported = []
    if not isinstance(installed, list):
        installed = []
    seen = {item.get("collector_id") for item in reported if isinstance(item, dict)}
    extra = [item for item in installed if isinstance(item, dict) and item.get("collector_id") not in seen]
    return [item for item in reported if isinstance(item, dict)] + extra


def format_hosted_collectors_cell(collectors, status_labels):
    parts = []
    for item in collectors or []:
        name = str(item.get("collector_name") or item.get("name") or "").strip()
        if not name:
            continue
        try:
            code = int(item.get("status"))
        except (TypeError, ValueError):
            code = 1
        label = status_labels.get(code, status_labels.get(1, ""))
        parts.append(f"{name}:{label}")
    return COLLECTOR_JOIN.join(parts)


def _controller_version(node):
    for item in node.get("versions") or []:
        if item.get("component_type") == "controller":
            version = item.get("version") or ""
            upgradeable = bool(item.get("upgradeable"))
            return version, upgradeable
    return "", False


def build_export_row(node, labels, organization_names):
    os_value = node.get("operating_system") or ""
    install_method = node.get("install_method") or ""
    node_type = node.get("node_type") or ""
    version, upgradeable = _controller_version(node)
    return [
        node.get("name") or "",
        node.get("ip") or "",
        labels["os"].get(os_value, os_value),
        node.get("cpu_architecture") or "",
        labels["node_type"].get(node_type, node_type),
        labels["install_method"].get(install_method, install_method),
        format_organization_cell(node.get("organization") or [], organization_names, labels["unassigned"]),
        labels["online"] if node.get("active") else labels["offline"],
        node.get("updated_at") or "",
        version,
        labels["yes"] if upgradeable else labels["no"],
        format_hosted_collectors_cell(_hosted_collectors(node), labels["collector_status"]),
    ]


def load_organization_names(organization_ids):
    ids = []
    for org_id in organization_ids:
        try:
            ids.append(int(org_id))
        except (TypeError, ValueError):
            continue
    if not ids:
        return {}
    return dict(Group.objects.filter(id__in=ids).values_list("id", "name"))


def build_export_filename(region_name, stamp):
    safe_region = str(region_name or "cloud").replace("/", "_")
    return f"节点清单_{safe_region}_{stamp}.xlsx"


def build_export_workbook_bytes(rows, headers):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "nodes"
    sheet.append(headers)
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    header_alignment = Alignment(horizontal="center", vertical="center")
    for col_num, _ in enumerate(headers, 1):
        cell = sheet.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    for row in rows:
        sheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def content_disposition(filename):
    ascii_name = "nodes.xlsx"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
```

把 `build_export_workbook_bytes` / `content_disposition` / `load_organization_names` 一并放进该文件，Task 2 会测工作簿。Task 1 测试不依赖它们也能绿。

- [ ] **Step 4: Run tests to verify they pass**

同一条 pytest 命令。Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/apps/node_mgmt/services/node_export.py server/apps/node_mgmt/tests/test_node_export.py
git commit -m "$(cat <<'EOF'
feat(node-mgmt): 抽出节点导出行列口径

导出单元格与列表 Sidecar / 托管组件展示对齐，避免在视图里拼文案。
EOF
)"
```

---

### Task 2: 工作簿字节

**Files:**
- Modify: `server/apps/node_mgmt/tests/test_node_export.py`
- Modify: `server/apps/node_mgmt/services/node_export.py`（若 Task 1 已写入工作簿函数则只补测试）

- [ ] **Step 1: Write the failing workbook test**

```python
from io import BytesIO

from openpyxl import load_workbook

from apps.node_mgmt.services.node_export import (
    EXPORT_HEADERS_ZH,
    build_export_workbook_bytes,
)


def test_workbook_contains_header_and_row():
    content = build_export_workbook_bytes(
        [["n1", "10.0.0.1", "Linux", "x86_64", "主机节点", "远程", "alpha", "在线", "t", "1.0", "否", ""]],
        EXPORT_HEADERS_ZH,
    )
    sheet = load_workbook(BytesIO(content)).active
    assert [cell.value for cell in sheet[1]] == EXPORT_HEADERS_ZH
    assert sheet[2][0].value == "n1"
    assert sheet[2][7].value == "在线"
```

- [ ] **Step 2: Run it**

Expected: PASS（若 Task 1 已实现）或 FAIL 后再补 `build_export_workbook_bytes`。

- [ ] **Step 3: Commit**

```bash
git add server/apps/node_mgmt/tests/test_node_export.py server/apps/node_mgmt/services/node_export.py
git commit -m "$(cat <<'EOF'
test(node-mgmt): 锁定导出工作表表头与数据行

读回 xlsx，避免只测拼行不测文件。
EOF
)"
```

若工作簿函数与 Task 1 同一次提交且测试已绿，可跳过本提交，把测试并进 Task 1。

---

### Task 3: 导出 HTTP 动作

**Files:**
- Create: `server/apps/node_mgmt/tests/test_node_viewset_export.py`
- Modify: `server/apps/node_mgmt/views/node.py`（只追加 action，不改 `search`）

- [ ] **Step 1: Write failing HTTP tests**

沿用 `test_node_viewset_search_update_enum.py` 的 `_user` / `_auth` / monkeypatch `get_node_permission` 与 `get_catalog_node_queryset`。

```python
"""NodeViewSet.export_excel：筛选导出、已选 ID、空结果、超限。"""
import uuid
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

import pytest
from django.utils import timezone as dj_timezone
from openpyxl import load_workbook
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import CloudRegion, Collector, Node
from apps.node_mgmt.models.sidecar import NodeOrganization
from apps.node_mgmt.services.node_export import EXPORT_LIMIT
from apps.node_mgmt.views import node as node_view
from apps.node_mgmt.views.node import NodeViewSet
from apps.system_mgmt.models import Group

pytestmark = pytest.mark.django_db
factory = APIRequestFactory()


def _user():
    user = UserFactory(username=f"node-ex-{uuid.uuid4().hex[:8]}", domain="domain.com", is_superuser=True)
    user.permission = {"node": {"cloud_region_node-View"}}
    user.locale = "zh-Hans"
    return user


def _auth(request, user=None):
    user = user or _user()
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = "1"
    return user


def _region_and_nodes():
    region = CloudRegion.objects.create(name="export-region")
    keep = Node.objects.create(
        id=f"keep-{uuid.uuid4().hex[:8]}",
        name="keep-node",
        ip="10.0.0.1",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/tmp",
        cloud_region=region,
        status={"collectors": [{"collector_id": "telegraf_linux", "status": 2}]},
    )
    other = Node.objects.create(
        id=f"other-{uuid.uuid4().hex[:8]}",
        name="other-node",
        ip="10.0.0.2",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/tmp",
        cloud_region=region,
        status={},
    )
    Node.objects.filter(id=keep.id).update(updated_at=dj_timezone.now() - timedelta(seconds=10))
    Node.objects.filter(id=other.id).update(updated_at=dj_timezone.now() - timedelta(seconds=120))
    NodeOrganization.objects.create(node=keep, organization=7)
    NodeOrganization.objects.create(node=other, organization=8)
    Group.objects.get_or_create(id=7, defaults={"name": "alpha", "parent_id": 0})
    Group.objects.get_or_create(id=8, defaults={"name": "beta", "parent_id": 0})
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
    return region, keep, other


def _post_export(monkeypatch, nodes, body, query=""):
    ids = [node.id for node in nodes]
    monkeypatch.setattr(node_view, "get_node_permission", lambda request: {"team": [1], "instance": []})
    monkeypatch.setattr(
        node_view,
        "get_catalog_node_queryset",
        lambda request, permission=None: Node.objects.filter(id__in=ids),
    )
    request = factory.post(f"/node/export_excel/{query}", body, format="json")
    _auth(request)
    return NodeViewSet.as_view({"post": "export_excel"})(request)


def test_export_filtered_offline_nodes(monkeypatch):
    region, keep, other = _region_and_nodes()
    resp = _post_export(
        monkeypatch,
        [keep, other],
        {
            "cloud_region_id": region.id,
            "filters": {"active": [{"lookup_expr": "in", "value": ["false"]}]},
        },
    )
    assert resp.status_code == 200
    sheet = load_workbook(BytesIO(resp.content)).active
    names = [row[0].value for row in sheet.iter_rows(min_row=2)]
    assert names == ["other-node"]
    assert "other-node" in names and "keep-node" not in names


def test_export_selected_ids_ignores_filters(monkeypatch):
    region, keep, other = _region_and_nodes()
    resp = _post_export(
        monkeypatch,
        [keep, other],
        {
            "cloud_region_id": region.id,
            "selected_ids": [keep.id, other.id],
            "filters": {"active": [{"lookup_expr": "in", "value": ["false"]}]},
        },
    )
    assert resp.status_code == 200
    names = [row[0].value for row in load_workbook(BytesIO(resp.content)).active.iter_rows(min_row=2)]
    assert set(names) == {"keep-node", "other-node"}


def test_export_drops_unknown_selected_id(monkeypatch):
    region, keep, other = _region_and_nodes()
    resp = _post_export(
        monkeypatch,
        [keep, other],
        {"cloud_region_id": region.id, "selected_ids": [keep.id, "missing-node"]},
    )
    assert resp.status_code == 200
    names = [row[0].value for row in load_workbook(BytesIO(resp.content)).active.iter_rows(min_row=2)]
    assert names == ["keep-node"]


def test_export_empty_selected_fails_without_file(monkeypatch):
    region, keep, other = _region_and_nodes()
    resp = _post_export(
        monkeypatch,
        [keep, other],
        {"cloud_region_id": region.id, "selected_ids": ["missing-node"]},
    )
    assert resp.status_code == 400
    assert resp["Content-Type"].startswith("application/json")
    assert "没有可导出的节点" in resp.content.decode()


def test_export_empty_filter_fails_without_file(monkeypatch):
    region, keep, other = _region_and_nodes()
    resp = _post_export(
        monkeypatch,
        [keep, other],
        {
            "cloud_region_id": region.id,
            "filters": {"name": [{"lookup_expr": "icontains", "value": "no-such-node"}]},
        },
    )
    assert resp.status_code == 400
    assert "没有可导出的节点" in resp.content.decode()


def test_export_over_limit_fails_without_truncation(monkeypatch):
    region, keep, other = _region_and_nodes()
    with patch("apps.node_mgmt.views.node.EXPORT_LIMIT", 1):
        resp = _post_export(monkeypatch, [keep, other], {"cloud_region_id": region.id})
    assert resp.status_code == 400
    assert "上限" in resp.content.decode()
    assert resp.get("Content-Disposition") is None


def test_export_hosted_cell_uses_collector_display_name(monkeypatch):
    region, keep, other = _region_and_nodes()
    resp = _post_export(
        monkeypatch,
        [keep],
        {"cloud_region_id": region.id, "selected_ids": [keep.id]},
    )
    sheet = load_workbook(BytesIO(resp.content)).active
    hosted = sheet[2][11].value
    assert hosted == "Telegraf:异常"
```

`test_export_over_limit` 里 patch 的是 view 模块绑定名。实现时必须 `from apps.node_mgmt.services.node_export import EXPORT_LIMIT` 写在 `views/node.py`，才能被 `apps.node_mgmt.views.node.EXPORT_LIMIT` patch 到。

- [ ] **Step 2: Run tests, expect FAIL**（`export_excel` 不存在）

- [ ] **Step 3: Implement `export_excel` only**

在 `server/apps/node_mgmt/views/node.py` 增加 import：

```python
from datetime import datetime
from django.http import HttpResponse
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.services.node_export import (
    EXPORT_LIMIT,
    build_export_filename,
    build_export_row,
    build_export_workbook_bytes,
    content_disposition,
    export_labels,
    load_organization_names,
)
```

确认 `CloudRegion` 已有现成 import；没有再补。在 `NodeViewSet` 的 `search` **之后**追加（不要改 `search` 方法体）：

```python
    @action(methods=["post"], detail=False, url_path="export_excel")
    def export_excel(self, request, *args, **kwargs):
        labels = export_labels(getattr(request.user, "locale", None))
        permission = get_node_permission(request)
        queryset = get_catalog_node_queryset(request, permission)
        selected_ids = [str(item).strip() for item in (request.data.get("selected_ids") or []) if str(item).strip()]

        cloud_region_id = request.query_params.get("cloud_region_id") or request.data.get("cloud_region_id")
        if not cloud_region_id:
            return WebUtils.response_error(error_message="cloud_region_id is required")
        queryset = queryset.filter(cloud_region_id=cloud_region_id)

        if selected_ids:
            queryset = queryset.filter(id__in=selected_ids)
        else:
            custom_filters = request.data.get("filters")
            if custom_filters:
                queryset = NodeFilterHandler.apply_filters(queryset, custom_filters)
            organization_ids = request.query_params.get("organization_ids") or request.data.get("organization_ids")
            if organization_ids:
                organization_ids = organization_ids.split(",")
                queryset = queryset.filter(nodeorganization__organization__in=organization_ids).distinct()

        queryset = NodeSerializer.setup_eager_loading(queryset).order_by("-created_at")
        total = queryset.count()
        if total == 0:
            return WebUtils.response_error(error_message=labels["empty"])
        if total > EXPORT_LIMIT:
            return WebUtils.response_error(
                error_message=labels["over_limit"].format(limit=EXPORT_LIMIT, count=total)
            )

        serializer = NodeSerializer(queryset, many=True)
        processed = NodeService.process_node_data(serializer.data)
        org_ids = []
        for node in processed:
            org_ids.extend(node.get("organization") or [])
        organization_names = load_organization_names(org_ids)
        rows = [build_export_row(node, labels, organization_names) for node in processed]
        content = build_export_workbook_bytes(rows, labels["headers"])
        region_name = CloudRegion.objects.filter(id=cloud_region_id).values_list("name", flat=True).first() or ""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = build_export_filename(region_name, stamp)
        response = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = content_disposition(filename)
        return response
```

日志：成功只打 DEBUG 有界汇总（`cloud_region_id`、`total`），不要打 node payload 或 Excel。失败走 `response_error`，不另加 traceback ERROR。空结果不是异常，不要 `logger.exception`。

- [ ] **Step 4: Run HTTP tests**

```
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/node_mgmt/tests/test_node_viewset_export.py apps/node_mgmt/tests/test_node_viewset_search_update_enum.py --no-cov --nomigrations -q
```

Expected: 导出测试 PASS，原搜索测试仍 PASS。

- [ ] **Step 5: Commit**

```bash
git add server/apps/node_mgmt/views/node.py server/apps/node_mgmt/tests/test_node_viewset_export.py
git commit -m "$(cat <<'EOF'
feat(node-mgmt): 节点搜索旁增加同步 Excel 导出

复用授权查询和列表状态加工，有已选 ID 时忽略组合筛选。
EOF
)"
```

---

### Task 4: 前端导出请求组装

**Files:**
- Create: `web/src/app/node-manager/utils/nodeListExport.ts`
- Test: `web/src/app/node-manager/utils/__tests__/nodeListExport.test.ts`

- [ ] **Step 1: Write failing tests**

```typescript
import { describe, expect, it } from 'vitest';
import { buildNodeExportRequest } from '../nodeListExport';

describe('buildNodeExportRequest', () => {
  it('sends selected ids and skips filters', () => {
    const result = buildNodeExportRequest({
      selectedIds: ['a', 'b'],
      cloudRegionId: 3,
      filters: { name: [{ lookup_expr: 'icontains', value: 'x' }] },
      unassignedOnly: true
    });
    expect(result.query).toEqual({ unassigned: true });
    expect(result.body).toEqual({
      cloud_region_id: 3,
      selected_ids: ['a', 'b']
    });
    expect(result.body.filters).toBeUndefined();
  });

  it('sends filters when nothing is selected', () => {
    const filters = { active: [{ lookup_expr: 'in', value: ['false'] }] };
    const result = buildNodeExportRequest({
      selectedIds: [],
      cloudRegionId: 3,
      filters,
      unassignedOnly: false
    });
    expect(result.query).toEqual({});
    expect(result.body).toEqual({
      cloud_region_id: 3,
      filters
    });
    expect(result.body.selected_ids).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run vitest, expect FAIL**

```
cd web && pnpm exec vitest run src/app/node-manager/utils/__tests__/nodeListExport.test.ts
```

- [ ] **Step 3: Implement**

```typescript
import { SearchFilters } from '@/components/search-combination/types';

export function buildNodeExportRequest({
  selectedIds,
  cloudRegionId,
  filters,
  unassignedOnly
}: {
  selectedIds: Array<string | number>;
  cloudRegionId: number | string;
  filters?: SearchFilters;
  unassignedOnly: boolean;
}): { query: { unassigned?: boolean }; body: Record<string, unknown> } {
  const query = unassignedOnly ? { unassigned: true } : {};
  const ids = selectedIds.map(String).filter(Boolean);
  if (ids.length) {
    return {
      query,
      body: {
        cloud_region_id: cloudRegionId,
        selected_ids: ids
      }
    };
  }
  const body: Record<string, unknown> = { cloud_region_id: cloudRegionId };
  if (filters && Object.keys(filters).length > 0) {
    body.filters = filters;
  }
  return { query, body };
}

export function nodeExportQueryString(query: { unassigned?: boolean }): string {
  if (!query.unassigned) return '';
  return '?unassigned=true';
}
```

- [ ] **Step 4: Run vitest, expect PASS**

- [ ] **Step 5: Commit**

```bash
git add web/src/app/node-manager/utils/nodeListExport.ts web/src/app/node-manager/utils/__tests__/nodeListExport.test.ts
git commit -m "$(cat <<'EOF'
feat(node-manager): 组装节点导出请求体

有勾选只传 ID，无勾选才带当前筛选。
EOF
)"
```

---

### Task 5: 接到节点清单页

**Files:**
- Modify: `web/src/app/node-manager/api/useNodeApi.ts`
- Modify: `web/src/app/node-manager/(pages)/cloudregion/node/page.tsx`
- Modify: `web/src/app/node-manager/locales/zh.json`
- Modify: `web/src/app/node-manager/locales/en.json`

- [ ] **Step 1: API 增加 blob 导出**

在 `useNodeApi.ts` 的 `getNodeList` 后：

```typescript
  const exportNodeList = async (params: {
    cloud_region_id?: number;
    filters?: SearchFilters;
    selected_ids?: string[];
    unassigned?: boolean;
  }) => {
    const { unassigned, ...bodyParams } = params;
    const queryParams = new URLSearchParams();
    if (unassigned) {
      queryParams.append('unassigned', 'true');
    }
    const queryString = queryParams.toString();
    const url = queryString
      ? `/node_mgmt/api/node/export_excel/?${queryString}`
      : '/node_mgmt/api/node/export_excel/';
    return await post<Blob>(url, bodyParams, { responseType: 'blob' });
  };
```

在 return 对象里导出 `exportNodeList`。

- [ ] **Step 2: 页面按钮**

`page.tsx`：从 `useNodeManagerApi()` 取出 `exportNodeList`（若当前解构来自该 hook）。增加 `exporting` state。

在工具栏「安装控制器」**之前**加按钮（与安装控制器同排，不进下拉）：

```tsx
<Button
  className="mr-[8px]"
  loading={exporting}
  onClick={handleExportNodes}
>
  {t('common.export')}
</Button>
```

`handleExportNodes`：

```typescript
  const handleExportNodes = async () => {
    setExporting(true);
    try {
      const request = buildNodeExportRequest({
        selectedIds: selectedRowKeys,
        cloudRegionId: cloudId,
        filters: searchFilters,
        unassignedOnly
      });
      const blob = await exportNodeList({
        ...request.body,
        ...request.query
      } as any);
      if (blob.type && blob.type.includes('application/json')) {
        const payload = JSON.parse(await blob.text());
        message.error(payload.message || t('common.exportFailed'));
        return;
      }
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `nodes.xlsx`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (error: any) {
      const data = error?.payload || error?.response?.data;
      if (data instanceof Blob) {
        try {
          const payload = JSON.parse(await data.text());
          if (payload?.message) {
            message.error(payload.message);
            return;
          }
        } catch {
          /* fall through */
        }
      }
      if (error?.message) {
        message.error(error.message);
      }
    } finally {
      setExporting(false);
    }
  };
```

`common.export` 已存在（「导出」/ Export）。若仓库没有 `common.exportFailed`，在 `web/src/locales/zh.json` / `en.json` 的 `common` 下增加 `"exportFailed": "导出失败"` / `"Export failed"`，不要只写在 node-manager 里造成键缺失。

文件名：浏览器会用 `nodes.xlsx`；真实中文名在 `Content-Disposition filename*`。不要在前端再拼云区域名。

- [ ] **Step 3: 手测清单**（无浏览器工具则依赖 Task 3 HTTP + Task 4 vitest）

- [ ] **Step 4: Commit**

```bash
git add web/src/app/node-manager/api/useNodeApi.ts web/src/app/node-manager/\(pages\)/cloudregion/node/page.tsx web/src/locales/zh.json web/src/locales/en.json
git commit -m "$(cat <<'EOF'
feat(node-manager): 节点清单工具栏同步导出 Excel

有勾选导勾选，没勾选导当前筛选，下载走现有 blob POST。
EOF
)"
```

---

### Task 6: 回归与规格状态

**Files:**
- Modify: `specs/changes/node-mgmt-agent-export/spec.md`（Status + Verification）

- [ ] **Step 1: 跑回归**

```
cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest \
  apps/node_mgmt/tests/test_node_export.py \
  apps/node_mgmt/tests/test_node_viewset_export.py \
  apps/node_mgmt/tests/test_node_viewset_search_update_enum.py \
  apps/node_mgmt/tests/test_b75_node_filter_handler.py \
  --no-cov --nomigrations
```

```
cd web && pnpm exec vitest run \
  src/app/node-manager/utils/__tests__/nodeListExport.test.ts \
  src/app/node-manager/utils/__tests__/nodeListSelection.test.ts \
  src/app/node-manager/hooks/__tests__/nodeFieldConfigs.test.ts
```

Expected: 全部 PASS。搜索/筛选原测试不得红。

- [ ] **Step 2: 把 spec Status 改为 `implemented`，写入本次 Verification 命令与条数**

- [ ] **Step 3: Commit**

```bash
git add specs/changes/node-mgmt-agent-export/spec.md
git commit -m "$(cat <<'EOF'
docs(node-mgmt): 标记 Agent 清单导出规格已实现
EOF
)"
```

---

### Task 7: 导出下拉范围

**Files:**
- Modify: `web/src/app/node-manager/utils/nodeListExport.ts`
- Modify: `web/src/app/node-manager/utils/__tests__/nodeListExport.test.ts`
- Modify: `web/src/app/node-manager/(pages)/cloudregion/node/page.tsx`
- Modify: `web/src/app/node-manager/locales/zh.json`
- Modify: `web/src/app/node-manager/locales/en.json`

服务端 `export_excel` 契约不变：非空 `selected_ids` 走 ID，否则走筛选。

- [x] **Step 1: Write failing request tests** for `scope=selected|currentPage|all`：已选择忽略筛选；当前页只用本页 ID 且忽略勾选；全部只用筛选且忽略勾选；已选择/当前页无 ID 时 `empty=true`，不得变成全部。
- [x] **Step 2: Run vitest, expect FAIL**
- [x] **Step 3: Implement `scope` on `buildNodeExportRequest`；工具栏改为 Dropdown（已选择无勾选禁用）；当前页空行提示「没有可导出的节点」**
- [x] **Step 4: Run vitest + 既有后端导出测试，Expected: PASS**
- [x] **Step 5: 把 spec Status 改为 implemented，写入 Verification**

---

## Spec coverage

| 规格 | 任务 |
|---|---|
| 已选择导勾选、忽略组合筛选 | T3、T4、T7 |
| 当前页导本页 ID，不改走全部 | T4、T7 |
| 全部导筛选（含 AND 状态），忽略勾选 | T3、T4、T7 |
| 仅未归属走 catalog query | T4 query + T3 使用 `get_catalog_node_queryset` |
| 固定 12 列、一行一台、组件拼格 | T1、T3 hosted cell |
| 组织显示名、未归属文案 | T1 |
| 空结果 400 无附件 | T3 |
| 无权/已删 ID 丢弃 | T3 |
| 5000 超限不截断 | T3 |
| 不新增 OpenAPI / 不改 search | T3 约束 |
| 工具栏导出下拉 | T5、T7 |
