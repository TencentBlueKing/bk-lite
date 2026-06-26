# Network Status Topology Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在运营分析仪表盘新增只读「网络状态拓扑」场景组件，用 CMDB 网络拓扑做结构，用告警中心活跃告警做状态叠加，并支持告警脉冲、故障链路高亮、实例详情和查看告警跳转。

**Architecture:** 组件以 `sceneWidget` 形态接入仪表盘添加入口，不进入普通数据源选择链路，也不生成组件级筛选字段。后端在 operation_analysis 新增聚合接口，复用 CMDB 拓扑权限与 Alert 告警权限过滤后返回合并后的 nodes/links/status。前端复用 CMDB 网络拓扑渲染能力的只读子集，在 `WidgetWrapper` 中为场景组件走独立请求路径，并跟随仪表盘刷新版本重新拉取。

**Tech Stack:** Django 4.2, DRF, pytest, Next.js 16, React 19, TypeScript, Ant Design, X6/XFlow

---

## 文件结构

**后端**

- Create: `server/apps/operation_analysis/serializers/scene_widget_serializers.py`  
  定义网络状态拓扑请求参数校验，字段固定为 `model_id`、`inst_id`、`depth`。
- Create: `server/apps/operation_analysis/services/network_status_topology.py`  
  聚合 CMDB 拓扑结构与 Alert 活跃告警状态，输出前端直接渲染的拓扑数据。
- Create: `server/apps/operation_analysis/views/scene_widget_view.py`  
  暴露 scene widget 聚合接口，入口权限使用运营分析查看权限。
- Modify: `server/apps/operation_analysis/urls.py`  
  注册 `api/scene_widgets/network_status_topology` 路由。
- Create: `server/apps/operation_analysis/tests/test_network_status_topology.py`  
  覆盖参数校验、状态映射、权限过滤、结构失败和状态失败。

**前端**

- Create: `web/src/app/ops-analysis/api/networkStatusTopology.ts`  
  封装聚合接口请求与响应类型。
- Create: `web/src/app/ops-analysis/types/sceneWidget.ts`  
  定义场景组件类型、网络状态拓扑配置、节点状态、接口响应。
- Create: `web/src/app/ops-analysis/constants/sceneWidgets.ts`  
  维护场景组件清单，当前只有 `networkStatusTopology`。
- Modify: `web/src/app/ops-analysis/types/dashBoard.ts`  
  给画布组件配置增加 `itemType: 'widget' | 'sceneWidget'` 与 `sceneWidgetType`。
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewSelector.tsx`  
  在添加组件弹窗中新增“场景组件”入口，网络状态拓扑直接打开配置。
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig.tsx`  
  增加场景组件配置分支，配置项只保留名称、模型、实例、展开层级。
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/widgetWrapper.tsx`  
  识别 `sceneWidget`，跳过普通数据源请求，按仪表盘刷新版本拉取聚合接口。
- Modify: `web/src/app/ops-analysis/components/widgetRenderer.tsx`  
  支持渲染场景组件。
- Modify: `web/src/app/ops-analysis/components/widgetRegistry.ts`  
  注册 `networkStatusTopology` 渲染组件。
- Create: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/networkStatusTopology/index.tsx`  
  只读拓扑组件主入口，处理加载、空、失败、刷新后的图更新。
- Create: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/networkStatusTopology/networkStatusTopology.module.scss`  
  状态色、critical 脉冲、选中态、故障链路高亮、无关元素减淡。
- Create: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/networkStatusTopology/graphModel.ts`  
  把接口 nodes/links 转为 X6 图数据，并计算从告警节点回到起点实例的故障链路。
- Create: `web/scripts/network-status-topology-validation.ts`  
  用轻量 TypeScript 断言覆盖状态映射、故障链路计算、告警跳转参数。
- Modify: `web/src/app/alarm/(pages)/alarms/page.tsx`  
  支持从 URL 查询参数初始化资源筛选，确保“查看告警”能筛到当前资产活跃告警。
- Modify: `web/src/app/ops-analysis/locales/zh.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`
- Modify: `web/src/app/alarm/locales/zh.json`
- Modify: `web/src/app/alarm/locales/en.json`

---

### Task 1: 后端聚合服务与单元测试

**Files:**

- Create: `server/apps/operation_analysis/tests/test_network_status_topology.py`
- Create: `server/apps/operation_analysis/services/network_status_topology.py`

- [ ] **Step 1: 写失败测试，锁定状态映射和响应结构**

Create `server/apps/operation_analysis/tests/test_network_status_topology.py` with these service-level tests:

```python
import pytest

from apps.operation_analysis.services.network_status_topology import (
    NetworkStatusTopologyService,
    map_alert_level_to_node_status,
)


def test_map_alert_level_to_node_status():
    assert map_alert_level_to_node_status(None) == {
        "status": "normal",
        "severity": None,
        "pulse": False,
        "color": "green",
    }
    assert map_alert_level_to_node_status("2") == {
        "status": "warning",
        "severity": "warning",
        "pulse": False,
        "color": "yellow",
    }
    assert map_alert_level_to_node_status("1") == {
        "status": "error",
        "severity": "error",
        "pulse": False,
        "color": "red",
    }
    assert map_alert_level_to_node_status("0") == {
        "status": "critical",
        "severity": "critical",
        "pulse": True,
        "color": "red",
    }


@pytest.mark.django_db
def test_merge_topology_status_marks_active_alerts(mocker, django_user_model):
    user = django_user_model.objects.create_user(username="ops")
    topology = {
        "center": {"id": "sw-core", "model_id": "switch", "name": "核心交换机", "hop": 0},
        "nodes": [
            {"id": "sw-core", "model_id": "switch", "name": "核心交换机", "hop": 0},
            {"id": "server-1", "model_id": "host", "name": "业务主机", "hop": 1},
        ],
        "links": [
            {
                "id": "link-1",
                "source": "sw-core",
                "target": "server-1",
                "source_port": "Gi0/1",
                "target_port": "eth0",
            }
        ],
        "truncated": False,
    }
    mocker.patch(
        "apps.operation_analysis.services.network_status_topology.NetworkStatusTopologyService._get_cmdb_topology",
        return_value=topology,
    )
    mocker.patch(
        "apps.operation_analysis.services.network_status_topology.NetworkStatusTopologyService._get_active_alert_summary",
        return_value={
            ("host", "server-1"): {"count": 2, "max_level": "0"},
        },
    )

    result = NetworkStatusTopologyService.build(
        request=mocker.Mock(user=user),
        model_id="switch",
        inst_id="sw-core",
        depth=2,
    )

    assert result["center_id"] == "sw-core"
    assert result["truncated"] is False
    assert result["nodes"][0]["alert_count"] == 0
    assert result["nodes"][0]["status"] == "normal"
    assert result["nodes"][1]["alert_count"] == 2
    assert result["nodes"][1]["status"] == "critical"
    assert result["nodes"][1]["pulse"] is True
    assert result["links"][0]["source_port"] == "Gi0/1"
```

- [ ] **Step 2: 运行测试确认 RED**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_network_status_topology.py -q`

Expected: FAIL because `apps.operation_analysis.services.network_status_topology` does not exist.

- [ ] **Step 3: 实现服务骨架和状态映射**

Create `server/apps/operation_analysis/services/network_status_topology.py`:

```python
from collections import defaultdict
from typing import Any

from apps.alerts.constants import AlertStatus
from apps.alerts.views.alert import AlertModelViewSet
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.cmdb.constants.constants import NETWORK_TOPO_MAX_HOP, NETWORK_TOPO_NODE_LIMIT, VIEW
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.utils.permission_util import CmdbRulesFormatUtil
from apps.cmdb.views.instance import InstanceViewSet


ALERT_LEVEL_PRIORITY = {"0": 0, "1": 1, "2": 2}


def map_alert_level_to_node_status(level: str | int | None) -> dict[str, Any]:
    level_key = None if level is None else str(level)
    if level_key == "0":
        return {"status": "critical", "severity": "critical", "pulse": True, "color": "red"}
    if level_key == "1":
        return {"status": "error", "severity": "error", "pulse": False, "color": "red"}
    if level_key == "2":
        return {"status": "warning", "severity": "warning", "pulse": False, "color": "yellow"}
    return {"status": "normal", "severity": None, "pulse": False, "color": "green"}


class NetworkStatusTopologyService:
    @classmethod
    def build(cls, request, model_id: str, inst_id: str, depth: int) -> dict[str, Any]:
        topology = cls._get_cmdb_topology(request, model_id, inst_id, depth)
        node_keys = {
            (str(node.get("model_id")), str(node.get("id")))
            for node in topology.get("nodes", [])
            if node.get("model_id") is not None and node.get("id") is not None
        }
        alert_summary = cls._get_active_alert_summary(request, node_keys)
        nodes = []
        for node in topology.get("nodes", []):
            node_key = (str(node.get("model_id")), str(node.get("id")))
            summary = alert_summary.get(node_key, {"count": 0, "max_level": None})
            status_info = map_alert_level_to_node_status(summary["max_level"])
            nodes.append(
                {
                    **node,
                    "alert_count": summary["count"],
                    **status_info,
                }
            )

        return {
            "center_id": str(topology.get("center", {}).get("id") or inst_id),
            "center_model_id": str(topology.get("center", {}).get("model_id") or model_id),
            "nodes": nodes,
            "links": topology.get("links", []),
            "truncated": bool(topology.get("truncated", False)),
            "node_limit": NETWORK_TOPO_NODE_LIMIT,
        }

    @staticmethod
    def _get_cmdb_topology(request, model_id: str, inst_id: str, depth: int) -> dict[str, Any]:
        bounded_depth = max(1, min(int(depth), NETWORK_TOPO_MAX_HOP))
        instance = InstanceManage.query_entity_by_id(int(inst_id))
        if not instance:
            raise NotFound("实例不存在")
        instance_view = InstanceViewSet()
        instance_view.request = request
        permission_error = instance_view.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            raise PermissionDenied("抱歉！您没有此实例的权限")
        permission_map = CmdbRulesFormatUtil.format_user_groups_permissions(request=request, model_id=instance["model_id"])
        return InstanceManage.network_topology(
            inst_id=int(inst_id),
            model_id=instance["model_id"],
            depth=bounded_depth,
            permission_map=permission_map,
            user=request.user,
            node_limit=NETWORK_TOPO_NODE_LIMIT,
        )

    @staticmethod
    def _get_active_alert_summary(request, node_keys: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
        if not node_keys:
            return {}

        alert_view = AlertModelViewSet()
        alert_view.request = request
        queryset = alert_view.get_queryset_by_permission(request, alert_view.get_queryset())
        resource_types = {resource_type for resource_type, _resource_id in node_keys}
        resource_ids = {resource_id for _resource_type, resource_id in node_keys}
        queryset = queryset.filter(
            resource_type__in=resource_types,
            resource_id__in=resource_ids,
            status__in=AlertStatus.ACTIVATE_STATUS,
        )

        summary: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"count": 0, "max_level": None})
        for alert in queryset.only("resource_type", "resource_id", "level"):
            key = (str(alert.resource_type), str(alert.resource_id))
            if key not in node_keys:
                continue
            current = summary[key]
            level = str(alert.level)
            current["count"] += 1
            if current["max_level"] is None:
                current["max_level"] = level
                continue
            if ALERT_LEVEL_PRIORITY.get(level, 99) < ALERT_LEVEL_PRIORITY.get(str(current["max_level"]), 99):
                current["max_level"] = level
        return dict(summary)
```

- [ ] **Step 4: 运行服务测试确认 GREEN**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_network_status_topology.py -q`

Expected: PASS.

### Task 2: 后端接口、参数校验与权限入口

**Files:**

- Modify: `server/apps/operation_analysis/tests/test_network_status_topology.py`
- Create: `server/apps/operation_analysis/serializers/scene_widget_serializers.py`
- Create: `server/apps/operation_analysis/views/scene_widget_view.py`
- Modify: `server/apps/operation_analysis/urls.py`

- [ ] **Step 1: 写失败测试，锁定接口参数和 service 调用**

Append to `server/apps/operation_analysis/tests/test_network_status_topology.py`:

```python
from rest_framework.test import APIRequestFactory

from apps.operation_analysis.views.scene_widget_view import SceneWidgetViewSet


@pytest.mark.django_db
def test_network_status_topology_endpoint_validates_required_params(mocker, django_user_model):
    user = django_user_model.objects.create_user(username="ops")
    request = APIRequestFactory().post(
        "/operation_analysis/api/scene_widgets/network_status_topology/",
        {"model_id": "switch", "depth": 2},
        format="json",
    )
    request.user = user
    view = SceneWidgetViewSet.as_view({"post": "network_status_topology"})

    response = view(request)

    assert response.status_code == 400
    assert "inst_id" in response.data


@pytest.mark.django_db
def test_network_status_topology_endpoint_returns_service_payload(mocker, django_user_model):
    user = django_user_model.objects.create_user(username="ops")
    service = mocker.patch(
        "apps.operation_analysis.views.scene_widget_view.NetworkStatusTopologyService.build",
        return_value={"center_id": "sw-core", "nodes": [], "links": [], "truncated": False, "node_limit": 100},
    )
    request = APIRequestFactory().post(
        "/operation_analysis/api/scene_widgets/network_status_topology/",
        {"model_id": "switch", "inst_id": "sw-core", "depth": 2},
        format="json",
    )
    request.user = user
    view = SceneWidgetViewSet.as_view({"post": "network_status_topology"})

    response = view(request)

    assert response.status_code == 200
    assert response.data["center_id"] == "sw-core"
    service.assert_called_once_with(request=request, model_id="switch", inst_id="sw-core", depth=2)
```

- [ ] **Step 2: 运行接口测试确认 RED**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_network_status_topology.py -q`

Expected: FAIL because `apps.operation_analysis.views.scene_widget_view` does not exist.

- [ ] **Step 3: 添加 serializer**

Create `server/apps/operation_analysis/serializers/scene_widget_serializers.py`:

```python
from rest_framework import serializers

from apps.cmdb.constants.constants import NETWORK_TOPO_MAX_HOP


class NetworkStatusTopologyRequestSerializer(serializers.Serializer):
    model_id = serializers.CharField(required=True, allow_blank=False)
    inst_id = serializers.CharField(required=True, allow_blank=False)
    depth = serializers.IntegerField(required=False, min_value=1, max_value=NETWORK_TOPO_MAX_HOP, default=2)
```

- [ ] **Step 4: 添加 viewset**

Create `server/apps/operation_analysis/views/scene_widget_view.py`:

```python
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.operation_analysis.serializers.scene_widget_serializers import NetworkStatusTopologyRequestSerializer
from apps.operation_analysis.services.network_status_topology import NetworkStatusTopologyService


class SceneWidgetViewSet(AuthViewSet):
    @HasPermission("view-View")
    @action(detail=False, methods=["post"], url_path="network_status_topology")
    def network_status_topology(self, request, *args, **kwargs):
        serializer = NetworkStatusTopologyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data
        result = NetworkStatusTopologyService.build(
            request=request,
            model_id=params["model_id"],
            inst_id=params["inst_id"],
            depth=params["depth"],
        )
        return Response(result)
```

- [ ] **Step 5: 注册 URL**

Modify `server/apps/operation_analysis/urls.py`:

```python
from apps.operation_analysis.views.scene_widget_view import SceneWidgetViewSet

router.register(r"api/scene_widgets", SceneWidgetViewSet, basename="scene_widgets")
```

- [ ] **Step 6: 运行后端目标测试**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_network_status_topology.py -q`

Expected: PASS.

### Task 3: 前端类型、API 与纯函数验证

**Files:**

- Create: `web/src/app/ops-analysis/types/sceneWidget.ts`
- Create: `web/src/app/ops-analysis/api/networkStatusTopology.ts`
- Create: `web/src/app/ops-analysis/constants/sceneWidgets.ts`
- Create: `web/scripts/network-status-topology-validation.ts`

- [ ] **Step 1: 写失败验证脚本**

Create `web/scripts/network-status-topology-validation.ts`:

```typescript
import assert from 'node:assert/strict';
import {
  buildFaultPath,
  buildAlertListUrl,
} from '../src/app/ops-analysis/(pages)/view/dashBoard/widgets/networkStatusTopology/graphModel';

const nodes = [
  { id: 'core', model_id: 'switch', name: '核心', hop: 0, status: 'normal', alert_count: 0, pulse: false },
  { id: 'agg', model_id: 'switch', name: '汇聚', hop: 1, status: 'warning', alert_count: 1, pulse: false },
  { id: 'host', model_id: 'host', name: '主机', hop: 2, status: 'critical', alert_count: 2, pulse: true },
];
const links = [
  { id: 'core-agg', source: 'core', target: 'agg', source_port: 'Gi0/1', target_port: 'Gi0/2' },
  { id: 'agg-host', source: 'agg', target: 'host', source_port: 'Gi0/3', target_port: 'eth0' },
];

const path = buildFaultPath({ nodes, links, centerId: 'core', selectedNodeId: 'host' });
assert.deepEqual(path.nodeIds, ['host', 'agg', 'core']);
assert.deepEqual(path.linkIds, ['agg-host', 'core-agg']);

const alertUrl = buildAlertListUrl({ resourceType: 'host', resourceId: 'host' });
assert.equal(
  alertUrl,
  '/alarm/alarms?resource_type=host&resource_id=host&activate=1&status=pending%2Cprocessing%2Cunassigned',
);
```

- [ ] **Step 2: 运行验证脚本确认 RED**

Run: `cd web && pnpm exec tsx scripts/network-status-topology-validation.ts`

Expected: FAIL because `networkStatusTopology/graphModel` does not exist.

- [ ] **Step 3: 添加场景组件类型**

Create `web/src/app/ops-analysis/types/sceneWidget.ts`:

```typescript
export type SceneWidgetType = 'networkStatusTopology';

export interface NetworkStatusTopologyConfig {
  sceneWidgetType: 'networkStatusTopology';
  modelId: string;
  instId: string;
  depth: number;
}

export type NetworkNodeStatus = 'normal' | 'warning' | 'error' | 'critical';

export interface NetworkStatusTopologyNode {
  id: string;
  model_id: string;
  name: string;
  hop: number;
  status: NetworkNodeStatus;
  severity?: 'warning' | 'error' | 'critical' | null;
  color: 'green' | 'yellow' | 'red';
  pulse: boolean;
  alert_count: number;
  icon?: string;
  expanded?: boolean;
}

export interface NetworkStatusTopologyLink {
  id: string;
  source: string;
  target: string;
  source_port?: string;
  target_port?: string;
}

export interface NetworkStatusTopologyResponse {
  center_id: string;
  center_model_id: string;
  nodes: NetworkStatusTopologyNode[];
  links: NetworkStatusTopologyLink[];
  truncated: boolean;
  node_limit: number;
}
```

- [ ] **Step 4: 添加接口封装**

Create `web/src/app/ops-analysis/api/networkStatusTopology.ts`:

```typescript
import { useCallback } from 'react';
import useApiClient from '@/utils/request';
import type { NetworkStatusTopologyResponse } from '@/app/ops-analysis/types/sceneWidget';

interface NetworkStatusTopologyRequest {
  model_id: string;
  inst_id: string;
  depth?: number;
}

export const useNetworkStatusTopologyApi = () => {
  const { post } = useApiClient();

  const getNetworkStatusTopology = useCallback(
    (params: NetworkStatusTopologyRequest) =>
      post<NetworkStatusTopologyResponse>(
        '/operation_analysis/api/scene_widgets/network_status_topology/',
        params,
      ),
    [post],
  );

  return { getNetworkStatusTopology };
};
```

- [ ] **Step 5: 添加场景组件清单**

Create `web/src/app/ops-analysis/constants/sceneWidgets.ts`:

```typescript
import type { SceneWidgetType } from '@/app/ops-analysis/types/sceneWidget';

export interface SceneWidgetDefinition {
  type: SceneWidgetType;
  nameKey: string;
  descriptionKey: string;
  defaultWidth: number;
  defaultHeight: number;
}

export const SCENE_WIDGETS: SceneWidgetDefinition[] = [
  {
    type: 'networkStatusTopology',
    nameKey: 'dashboard.networkStatusTopology',
    descriptionKey: 'dashboard.networkStatusTopologyDesc',
    defaultWidth: 8,
    defaultHeight: 6,
  },
];
```

### Task 4: 添加组件入口与配置面板

**Files:**

- Modify: `web/src/app/ops-analysis/types/dashBoard.ts`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewSelector.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig.tsx`
- Modify: `web/src/app/ops-analysis/locales/zh.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`

- [ ] **Step 1: 扩展仪表盘配置类型**

Modify `web/src/app/ops-analysis/types/dashBoard.ts`:

```typescript
import type { NetworkStatusTopologyConfig, SceneWidgetType } from './sceneWidget';

export interface ValueConfig {
  chartType?: string;
  sceneWidgetType?: SceneWidgetType;
  networkStatusTopology?: NetworkStatusTopologyConfig;
  chartThemeMode?: OpsChartThemeMode;
  dataSource?: string | number;
  compare?: boolean;
  params?: Record<string, string | number | boolean | [number, number] | null>;
  dataSourceParams?: ParamItem[];
  tableConfig?: TableConfig;
  filterBindings?: FilterBindings;
  selectedFields?: string[];
  topNLabelField?: string;
  topNValueField?: string;
  unit?: string;
  unitId?: string;
  valueMappings?: ValueMapping[];
  stack?: boolean;
  fillOpacity?: number;
  content?: string;
  conversionFactor?: number;
  decimalPlaces?: number;
  thresholdColors?: ThresholdColorConfig[];
  gaugeMin?: number;
  gaugeMax?: number;
  gaugeShape?: 'semicircle' | 'circle';
  actions?: DashboardActionConfig[];
}

export interface DashboardWidgetLayoutItem extends LayoutItem {
  itemType?: 'widget' | 'sceneWidget';
  groupId?: string | null;
}
```

- [ ] **Step 2: 在选择弹窗新增场景组件菜单**

Modify `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewSelector.tsx`:

```typescript
import { AppstoreOutlined, DatabaseOutlined } from '@ant-design/icons';
import { SCENE_WIDGETS } from '@/app/ops-analysis/constants/sceneWidgets';
import type { SceneWidgetDefinition } from '@/app/ops-analysis/constants/sceneWidgets';

type SelectorMode = 'dataSource' | 'sceneWidget';

const [selectorMode, setSelectorMode] = useState<SelectorMode>('dataSource');

const menuItems = [
  { key: 'dataSource', label: t('dashboard.dataComponents'), icon: <DatabaseOutlined /> },
  { key: 'sceneWidget', label: t('dashboard.sceneComponents'), icon: <AppstoreOutlined /> },
];

const handleSceneConfig = (item: SceneWidgetDefinition) => {
  onOpenConfig?.({
    id: `scene:${item.type}`,
    name: t(item.nameKey),
    desc: t(item.descriptionKey),
    chart_type: [],
    sceneWidgetType: item.type,
  } as any);
};
```

Render `SCENE_WIDGETS` when `selectorMode === 'sceneWidget'`, and keep the existing data-source list unchanged when `selectorMode === 'dataSource'`.

- [ ] **Step 3: 配置面板识别 scene widget**

Modify `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig.tsx`:

```typescript
import { useModelApi, useInstanceApi } from '@/app/cmdb/api';
import type { NetworkStatusTopologyConfig } from '@/app/ops-analysis/types/sceneWidget';

interface FormValues {
  name: string;
  description?: string;
  chartType: string;
  sceneWidgetType?: 'networkStatusTopology';
  networkStatusTopology?: NetworkStatusTopologyConfig;
  chartThemeMode?: OpsChartThemeMode;
  dataSource: string | number;
  compare?: boolean;
  dataSourceParams?: ParamItem[];
  params?: Record<string, string | number | boolean | [number, number] | null>;
  tableConfig?: TableConfig;
  selectedFields?: string[];
  topNLabelField?: string;
  topNValueField?: string;
  unit?: string;
  unitId?: string;
  valueMappings?: ValueConfig['valueMappings'];
  stack?: boolean;
  content?: string;
  conversionFactor?: number;
  decimalPlaces?: number;
  gaugeMin?: number;
  gaugeMax?: number;
  gaugeShape?: 'semicircle' | 'circle';
  actions?: DashboardActionConfig[];
}
```

Add a branch that renders only:

```tsx
<>
  <Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}>
    <Input />
  </Form.Item>
  <Form.Item
    name={['networkStatusTopology', 'modelId']}
    label={t('cmdb.model')}
    rules={[{ required: true, message: t('dashboard.selectModel') }]}
    tooltip={t('dashboard.networkTopoModelHelp')}
  >
    <Select showSearch placeholder={t('dashboard.selectModel')} />
  </Form.Item>
  <Form.Item
    name={['networkStatusTopology', 'instId']}
    label={t('cmdb.instance')}
    rules={[{ required: true, message: t('dashboard.selectInstance') }]}
    tooltip={t('dashboard.networkTopoInstanceHelp')}
  >
    <Select showSearch placeholder={t('dashboard.selectInstance')} />
  </Form.Item>
  <Form.Item
    name={['networkStatusTopology', 'depth']}
    label={t('dashboard.expandDepth')}
    initialValue={2}
  >
    <Select
      options={[
        { label: '1', value: 1 },
        { label: '2', value: 2 },
        { label: '3', value: 3 },
        { label: '4', value: 4 },
      ]}
    />
  </Form.Item>
</>
```

The model field loads `useModelApi().getModelList()`. After model selection, call `useInstanceApi().getTopoThemes(modelId)`; if no network theme is returned, show `dashboard.modelNotSupportNetworkTopo` and clear instance. The instance field searches with `useInstanceApi().searchInstances({ model_id: modelId, query_list: [], page: 1, page_size: 20 })`.

- [ ] **Step 4: 保存 scene widget 配置**

In `handleConfirm`, branch before normal data-source handling:

```typescript
if (values.sceneWidgetType === 'networkStatusTopology') {
  const topo = values.networkStatusTopology;
  const result: WidgetConfig = {
    name: values.name,
    description: values.description,
    chartType: 'networkStatusTopology',
    sceneWidgetType: 'networkStatusTopology',
    networkStatusTopology: {
      sceneWidgetType: 'networkStatusTopology',
      modelId: topo!.modelId,
      instId: topo!.instId,
      depth: topo!.depth || 2,
    },
  };
  onConfirm?.(result);
  return;
}
```

- [ ] **Step 5: 增加文案**

Add zh locale keys:

```json
{
  "dashboard": {
    "dataComponents": "数据组件",
    "sceneComponents": "场景组件",
    "networkStatusTopology": "网络状态拓扑",
    "networkStatusTopologyDesc": "基于 CMDB 网络结构叠加当前告警状态",
    "selectModel": "选择模型",
    "selectInstance": "选择实例",
    "networkTopoModelHelp": "仅支持已具备网络拓扑关系的模型",
    "networkTopoInstanceHelp": "以所选实例为中心展开网络拓扑",
    "modelNotSupportNetworkTopo": "该模型不支持网络拓扑",
    "expandDepth": "展开层级"
  }
}
```

Add en locale keys with the same key names:

```json
{
  "dashboard": {
    "dataComponents": "Data Components",
    "sceneComponents": "Scene Components",
    "networkStatusTopology": "Network Status Topology",
    "networkStatusTopologyDesc": "Overlay active alert status on the CMDB network topology",
    "selectModel": "Select model",
    "selectInstance": "Select instance",
    "networkTopoModelHelp": "Only models with network topology relationships are supported",
    "networkTopoInstanceHelp": "Expand the topology from the selected instance",
    "modelNotSupportNetworkTopo": "This model does not support network topology",
    "expandDepth": "Expand Depth"
  }
}
```

### Task 5: 场景组件请求路径和只读渲染入口

**Files:**

- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/widgetWrapper.tsx`
- Modify: `web/src/app/ops-analysis/components/widgetRenderer.tsx`
- Modify: `web/src/app/ops-analysis/components/widgetRegistry.ts`
- Create: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/networkStatusTopology/index.tsx`

- [ ] **Step 1: WidgetWrapper 识别 scene widget**

Modify `WidgetWrapperProps`:

```typescript
interface WidgetWrapperProps {
  dashboardId?: number | string;
  widgetId: string;
  chartType?: string;
  itemType?: 'widget' | 'sceneWidget';
  config?: ValueConfig;
  onReady?: (hasData?: boolean) => void;
  dataSource?: DatasourceItem;
  unifiedFilterValues?: Record<string, FilterValue>;
  filterDefinitions?: UnifiedFilterDefinition[];
  filterSearchVersion?: number;
  namespaceSearchVersion?: number;
  reloadVersion?: string;
  builtinNamespaceId?: number;
}
```

Add a top-level scene branch:

```tsx
if (itemType === 'sceneWidget' || config?.sceneWidgetType) {
  return (
    <WidgetRenderer
      chartType={config?.sceneWidgetType || chartType}
      rawData={null}
      loading={false}
      config={config}
      onReady={onReady}
      fallback={renderError(`${t('dashboard.unknownComponentType')}: ${chartType}`)}
    />
  );
}
```

- [ ] **Step 2: 注册组件**

Modify `web/src/app/ops-analysis/components/widgetRegistry.ts`:

```typescript
import NetworkStatusTopology from '@/app/ops-analysis/(pages)/view/dashBoard/widgets/networkStatusTopology';

export const widgetRegistry: Record<string, ComponentType<any>> = {
  line: ComLine,
  pie: ComPie,
  bar: ComBar,
  table: ComTable,
  single: ComSingle,
  topN: ComTopN,
  gauge: ComGauge,
  barGauge: ComBarGauge,
  stateTimeline: ComStateTimeline,
  text: ComText,
  eventTable: EventTable,
  networkStatusTopology: NetworkStatusTopology,
};
```

- [ ] **Step 3: 组件内部请求聚合接口**

Create `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/networkStatusTopology/index.tsx`:

```tsx
import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Empty, Spin } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useNetworkStatusTopologyApi } from '@/app/ops-analysis/api/networkStatusTopology';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import type { NetworkStatusTopologyResponse } from '@/app/ops-analysis/types/sceneWidget';

interface Props {
  config?: ValueConfig;
  onReady?: (ready?: boolean) => void;
}

const NetworkStatusTopology: React.FC<Props> = ({ config, onReady }) => {
  const { t } = useTranslation();
  const { getNetworkStatusTopology } = useNetworkStatusTopologyApi();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<NetworkStatusTopologyResponse | null>(null);
  const [error, setError] = useState('');
  const topoConfig = config?.networkStatusTopology;

  const requestPayload = useMemo(() => {
    if (!topoConfig?.modelId || !topoConfig?.instId) return null;
    return {
      model_id: topoConfig.modelId,
      inst_id: topoConfig.instId,
      depth: topoConfig.depth || 2,
    };
  }, [topoConfig?.modelId, topoConfig?.instId, topoConfig?.depth]);

  useEffect(() => {
    let cancelled = false;
    const fetchTopology = async () => {
      if (!requestPayload) {
        setData(null);
        onReady?.(false);
        return;
      }
      try {
        setLoading(true);
        setError('');
        const response = await getNetworkStatusTopology(requestPayload);
        if (cancelled) return;
        setData(response);
        onReady?.((response.nodes || []).length > 0);
      } catch (err) {
        if (cancelled) return;
        setData(null);
        setError(t('dashboard.networkTopoLoadFailed'));
        onReady?.(false);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void fetchTopology();
    return () => {
      cancelled = true;
    };
  }, [getNetworkStatusTopology, onReady, requestPayload, t]);

  if (loading) {
    return <div className="h-full flex items-center justify-center"><Spin /></div>;
  }
  if (error) {
    return <Alert type="error" showIcon message={error} />;
  }
  if (!data || data.nodes.length === 0) {
    return <Empty description={t('dashboard.networkTopoEmpty')} />;
  }
  return <div className="h-full w-full" data-testid="network-status-topology" />;
};

export default NetworkStatusTopology;
```

- [ ] **Step 4: 增加运行态文案**

Add zh locale keys:

```json
{
  "dashboard": {
    "networkTopoLoadFailed": "网络拓扑结构加载失败",
    "networkTopoStatusLoadFailed": "告警状态加载失败",
    "networkTopoEmpty": "暂无网络拓扑关系",
    "networkTopoTruncated": "拓扑节点较多，已达展示上限（100），不再继续展开"
  }
}
```

### Task 6: 图渲染、告警脉冲与故障链路高亮

**Files:**

- Create: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/networkStatusTopology/graphModel.ts`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/networkStatusTopology/index.tsx`
- Create: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/networkStatusTopology/networkStatusTopology.module.scss`
- Modify: `web/scripts/network-status-topology-validation.ts`

- [ ] **Step 1: 实现图模型纯函数**

Create `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/networkStatusTopology/graphModel.ts`:

```typescript
import type {
  NetworkStatusTopologyLink,
  NetworkStatusTopologyNode,
} from '@/app/ops-analysis/types/sceneWidget';

export interface FaultPathInput {
  nodes: NetworkStatusTopologyNode[];
  links: NetworkStatusTopologyLink[];
  centerId: string;
  selectedNodeId: string;
}

export interface FaultPathResult {
  nodeIds: string[];
  linkIds: string[];
}

export const buildFaultPath = ({
  nodes,
  links,
  centerId,
  selectedNodeId,
}: FaultPathInput): FaultPathResult => {
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const pathNodeIds: string[] = [];
  const pathLinkIds: string[] = [];
  let currentId = selectedNodeId;
  const visited = new Set<string>();

  while (currentId && !visited.has(currentId)) {
    visited.add(currentId);
    pathNodeIds.push(currentId);
    if (currentId === centerId) break;
    const current = nodeMap.get(currentId);
    if (!current) break;
    const parentLink = links.find((link) => {
      const source = nodeMap.get(link.source);
      const target = nodeMap.get(link.target);
      if (!source || !target) return false;
      if (link.source === currentId) return target.hop < current.hop;
      if (link.target === currentId) return source.hop < current.hop;
      return false;
    });
    if (!parentLink) break;
    pathLinkIds.push(parentLink.id);
    currentId = parentLink.source === currentId ? parentLink.target : parentLink.source;
  }

  return { nodeIds: pathNodeIds, linkIds: pathLinkIds };
};

export const buildAlertListUrl = ({
  resourceType,
  resourceId,
}: {
  resourceType: string;
  resourceId: string;
}) => {
  const params = new URLSearchParams({
    resource_type: resourceType,
    resource_id: resourceId,
    activate: '1',
    status: 'pending,processing,unassigned',
  });
  return `/alarm/alarms?${params.toString()}`;
};
```

- [ ] **Step 2: 运行验证脚本确认纯函数 GREEN**

Run: `cd web && pnpm exec tsx scripts/network-status-topology-validation.ts`

Expected: PASS.

- [ ] **Step 3: 接入 X6 只读画布**

Modify `index.tsx` to create an X6 Graph in a `ref` container. Configure it as read-only:

```typescript
const graph = new Graph({
  container: containerRef.current,
  background: { color: 'transparent' },
  panning: true,
  mousewheel: { enabled: true, modifiers: ['ctrl', 'meta'] },
  connecting: { allowBlank: false, allowLoop: false },
  interacting: {
    nodeMovable: false,
    edgeMovable: false,
    edgeLabelMovable: false,
    arrowheadMovable: false,
    vertexMovable: false,
    vertexAddable: false,
    vertexDeletable: false,
  },
});
```

Use the same layout names as CMDB:

```typescript
type LayoutMode = 'hierarchical' | 'force' | 'circular';
const [layoutMode, setLayoutMode] = useState<LayoutMode>('hierarchical');
```

- [ ] **Step 4: 添加节点样式和脉冲**

Create `networkStatusTopology.module.scss`:

```scss
.topology {
  position: relative;
  height: 100%;
  width: 100%;
}

.toolbar {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 2;
  display: flex;
  gap: 8px;
}

.pulse {
  animation: criticalPulse 1.6s ease-in-out infinite;
}

@keyframes criticalPulse {
  0% {
    box-shadow: 0 0 0 0 rgba(244, 59, 44, 0.36);
  }
  70% {
    box-shadow: 0 0 0 14px rgba(244, 59, 44, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(244, 59, 44, 0);
  }
}

.dimmed {
  opacity: 0.24;
}

.faultPath {
  opacity: 1;
  filter: drop-shadow(0 0 6px rgba(244, 59, 44, 0.42));
}
```

- [ ] **Step 5: 点击节点高亮故障链路**

Add graph event handlers:

```typescript
graph.on('node:click', ({ node }) => {
  const nodeData = node.getData() as NetworkStatusTopologyNode;
  const activeAlert = nodeData.alert_count > 0;
  if (selectedNodeId === nodeData.id) {
    setSelectedNodeId('');
    setFaultPath({ nodeIds: [], linkIds: [] });
    return;
  }
  setSelectedNodeId(nodeData.id);
  if (!activeAlert) {
    setFaultPath({ nodeIds: [nodeData.id], linkIds: [] });
    return;
  }
  setFaultPath(buildFaultPath({
    nodes: data.nodes,
    links: data.links,
    centerId: data.center_id,
    selectedNodeId: nodeData.id,
  }));
});

graph.on('blank:click', () => {
  setSelectedNodeId('');
  setFaultPath({ nodeIds: [], linkIds: [] });
});
```

### Task 7: Hover 浮层、CMDB 跳转和告警列表筛选

**Files:**

- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/networkStatusTopology/index.tsx`
- Modify: `web/src/app/alarm/(pages)/alarms/page.tsx`
- Modify: `web/src/app/alarm/locales/zh.json`
- Modify: `web/src/app/alarm/locales/en.json`

- [ ] **Step 1: Hover 浮层展示摘要和两个动作**

In the topology widget, render node popover content:

```tsx
const renderNodePopover = (node: NetworkStatusTopologyNode) => (
  <div className="min-w-48">
    <div className="font-medium mb-2">{node.name}</div>
    <div>{t('dashboard.status')}: {t(`dashboard.networkStatus.${node.status}`)}</div>
    <div>{t('dashboard.activeAlertCount')}: {node.alert_count}</div>
    <div className="flex gap-2 mt-3">
      <Button size="small" onClick={() => window.open(`/cmdb/assetData/detail/${node.model_id}/${node.id}`, '_blank')}>
        {t('dashboard.instanceDetail')}
      </Button>
      <Button
        size="small"
        disabled={node.alert_count === 0}
        onClick={() => window.open(buildAlertListUrl({ resourceType: node.model_id, resourceId: node.id }), '_blank')}
      >
        {t('dashboard.viewAlerts')}
      </Button>
    </div>
  </div>
);
```

- [ ] **Step 2: 告警列表消费 URL 查询参数**

Modify `web/src/app/alarm/(pages)/alarms/page.tsx`:

```typescript
import { useSearchParams } from 'next/navigation';

const searchParams = useSearchParams();
const initialResourceType = searchParams.get('resource_type') || '';
const initialResourceId = searchParams.get('resource_id') || '';
const initialActivate = searchParams.get('activate') || '';
const initialStatus = searchParams.get('status') || '';

const [searchCondition, setSearchCondition] = useState<SearchFilterCondition | null>(() => {
  if (initialResourceType && initialResourceId) {
    return {
      field: 'resource_id',
      operator: 'eq',
      value: initialResourceId,
    } as SearchFilterCondition;
  }
  return null;
});

const [filters, setFilters] = useState<FiltersConfig>(() => {
  const { stateFilters } = getSettings();
  return {
    level: [],
    state: initialStatus ? initialStatus.split(',') : stateFilters || ['pending', 'processing'],
    alarm_source: [],
  };
});
```

Extend `getParams`:

```typescript
const params: any = {
  status: filters.state.join(','),
  level: filters.level.join(','),
  source_name: filters.alarm_source.join(','),
  page: pagination.current,
  page_size: pagination.pageSize,
  created_at_after: dayjs(timeRange[0]).toISOString(),
  created_at_before: dayjs(timeRange[1]).toISOString(),
  activate: initialActivate || (isActiveAlarms ? 1 : ''),
  my_alert: isActiveAlarms ? (myAlarms ? 1 : '') : undefined,
  has_incident: '',
  resource_type: initialResourceType,
  [conditionValue?.field as string]: conditionValue?.value,
};
```

- [ ] **Step 3: 添加动作文案**

Add zh locale keys:

```json
{
  "dashboard": {
    "activeAlertCount": "活跃告警数",
    "instanceDetail": "实例详情",
    "viewAlerts": "查看告警",
    "networkStatus": {
      "normal": "正常",
      "warning": "Warning",
      "error": "Error",
      "critical": "Critical"
    }
  }
}
```

### Task 8: 联动刷新、截断提示和最终验证

**Files:**

- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/dashboardCanvas.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/widgetWrapper.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/networkStatusTopology/index.tsx`
- Test: `server/apps/operation_analysis/tests/test_network_status_topology.py`
- Test: `web/scripts/network-status-topology-validation.ts`

- [ ] **Step 1: 确认画布把 itemType 传给 WidgetWrapper**

In `dashboardCanvas.tsx`, pass the layout item type:

```tsx
<WidgetWrapper
  dashboardId={dashboardId}
  widgetId={item.i}
  itemType={item.itemType}
  chartType={item.valueConfig?.chartType}
  config={item.valueConfig}
  dataSource={dataSource}
  unifiedFilterValues={unifiedFilterValues}
  filterDefinitions={filterDefinitions}
  filterSearchVersion={filterSearchVersion}
  namespaceSearchVersion={namespaceSearchVersion}
  reloadVersion={reloadVersion}
  builtinNamespaceId={builtinNamespaceId}
/>
```

- [ ] **Step 2: scene widget 跟随仪表盘刷新**

Pass `reloadVersion` into `NetworkStatusTopology` through `WidgetRenderer`:

```typescript
interface WidgetRendererProps {
  chartType?: string;
  rawData: any;
  baselineData?: any;
  loading?: boolean;
  config?: ValueConfig;
  dataSource?: DatasourceItem;
  reloadVersion?: string;
  onReady?: (ready?: boolean) => void;
  onQueryChange?: (params: Record<string, any>) => void;
  fallback?: React.ReactNode;
}
```

Use `reloadVersion` in the topology widget effect dependency:

```typescript
useEffect(() => {
  void fetchTopology();
}, [fetchTopology, reloadVersion]);
```

- [ ] **Step 3: 渲染截断提示**

In `NetworkStatusTopology`, show the same wording as CMDB when `data.truncated`:

```tsx
{data.truncated && (
  <Alert
    className="absolute left-2 top-2 z-10"
    type="warning"
    showIcon
    message={t('dashboard.networkTopoTruncated')}
  />
)}
```

- [ ] **Step 4: 运行后端目标测试**

Run: `cd server && uv run pytest apps/operation_analysis/tests/test_network_status_topology.py -q`

Expected: PASS.

- [ ] **Step 5: 运行前端纯函数验证**

Run: `cd web && pnpm exec tsx scripts/network-status-topology-validation.ts`

Expected: PASS.

- [ ] **Step 6: 运行前端门禁**

Run: `cd web && pnpm lint && pnpm type-check`

Expected: PASS.

- [ ] **Step 7: 检查工作区**

Run: `git status --short`

Expected: 只出现网络状态拓扑相关代码文件，以及本次讨论生成但不提交的 `docs/superpowers/specs/2026-06-25-network-status-topology-widget-design.md` 和 `docs/superpowers/plans/2026-06-25-network-status-topology-widget.md`。
