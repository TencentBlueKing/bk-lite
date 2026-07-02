# CMDB Community Collect Objects Batch 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 模型配置保留在社区版，配置采集能力在商业版 CMDB / Stargazer 中跑通 Nacos、IBM MQ、OceanBase、HighGo、Server BMC Redfish 5 个新增配置采集对象的完整链路。

> 2026-07-01 修正：配置采集能力归商业版，落点为 `server/apps/cmdb_enterprise/collect/` 与 `agents/stargazer/enterprise/plugins/inputs/`；本文中较早的社区采集路径仅作为历史执行记录，不作为最终边界。

**Architecture:** 模型、字段、关联写入社区 `model_config.xlsx`，采集入口写入社区 `COLLECT_OBJ_TREE`。Server 侧新增 NodeParams、collection plugin、formatter 映射；Stargazer 侧新增 `plugins/inputs/<model_id>/` 插件，输出稳定指标；Server formatter 将指标转换为图实例和 belong/auto 关联。

**Tech Stack:** Python 3.12, Django 4.2, pytest, openpyxl/pandas, Stargazer plugin.yml, requests, pymysql, psycopg/PostgresqlInfo, SSH JOB shell.

---

## Scope

本计划只实现 Batch 1：

- `nacos`
- `ibmmq`
- `oceanbase`
- `highgo`
- `server_bmc`

后续 43 个对象在 Batch 1 验证通过后，按同类模式复制扩展，不纳入本计划。

## File Structure

### Model Metadata

- Modify: `server/apps/cmdb/support-files/model_config.xlsx`
  - `classifications` 不新增分组。
  - `models` 新增 20 个模型：5 个主对象 + 15 个子对象。
  - 字段表新增对应 attr 字段。
  - 关联关系新增 belong 关系，以及 `server_bmc` 到 `physcial_server` 的自动关联关系。

### Server Collection Registry

- Modify: `server/apps/cmdb/constants/constants.py`
  - `COLLECT_OBJ_TREE` 增加 5 个采集对象。
- Modify: `server/apps/cmdb/collection/constants.py`
  - `PROTOCOL_METRIC_MAP` 增加 `highgo`、`oceanbase`、`server_bmc`。
  - `MIDDLEWARE_METRIC_MAP` 增加 `nacos`、`ibmmq`。

### Server NodeParams

- Create: `server/apps/cmdb/node_configs/protocol/nacos.py`
- Create: `server/apps/cmdb/node_configs/protocol/oceanbase.py`
- Create: `server/apps/cmdb/node_configs/protocol/highgo.py`
- Create: `server/apps/cmdb/node_configs/protocol/server_bmc.py`
- Create: `server/apps/cmdb/node_configs/ssh/ibmmq.py`

### Server Formatter and Plugins

- Create: `server/apps/cmdb/collection/collect_plugin/new_objects.py`
  - 多对象 formatter helpers：`NacosCollectMetrics`、`IbmMqCollectMetrics`、`OceanBaseCollectMetrics`、`ServerBmcCollectMetrics`。
- Create: `server/apps/cmdb/collection/plugins/community/middleware/nacos.py`
- Create: `server/apps/cmdb/collection/plugins/community/middleware/ibmmq.py`
- Create: `server/apps/cmdb/collection/plugins/community/protocol/oceanbase.py`
- Create: `server/apps/cmdb/collection/plugins/community/protocol/highgo.py`
- Create: `server/apps/cmdb/collection/plugins/community/protocol/server_bmc.py`

### Stargazer Plugins

- Create: `agents/stargazer/plugins/inputs/nacos/plugin.yml`
- Create: `agents/stargazer/plugins/inputs/nacos/nacos_info.py`
- Create: `agents/stargazer/plugins/inputs/ibmmq/plugin.yml`
- Create: `agents/stargazer/plugins/inputs/ibmmq/ibmmq_default_discover.sh`
- Create: `agents/stargazer/plugins/inputs/oceanbase/plugin.yml`
- Create: `agents/stargazer/plugins/inputs/oceanbase/oceanbase_info.py`
- Create: `agents/stargazer/plugins/inputs/highgo/plugin.yml`
- Create: `agents/stargazer/plugins/inputs/highgo/highgo_info.py`
- Create: `agents/stargazer/plugins/inputs/server_bmc/plugin.yml`
- Create: `agents/stargazer/plugins/inputs/server_bmc/server_bmc_info.py`

### Tests

- Create: `server/apps/cmdb/tests/test_new_collect_objects_registry.py`
- Create: `server/apps/cmdb/tests/test_new_collect_objects_formatters.py`
- Create: `server/apps/cmdb/tests/test_new_collect_objects_model_config.py`
- Create: `agents/stargazer/tests/test_new_collect_objects_plugins.py`

## Shared Test Helpers

Use these helper objects in server tests where a collect task instance is needed:

```python
from types import SimpleNamespace


def make_collect_instance(model_id, driver_type="PROTOCOL", credential=None):
    return SimpleNamespace(
        id=1001,
        model_id=model_id,
        driver_type=driver_type,
        decrypt_credentials=credential or {"username": "demo", "password": "secret", "port": 443},
        timeout=30,
        access_point=[{"id": 7}],
        instances=[{"ip_addr": "10.0.0.10"}],
        ip_range="10.0.0.10",
        params={},
    )
```

Use this timestamp helper in formatter tests:

```python
import time


def metric(name, labels):
    return {
        "metric": {"__name__": name, "collect_status": "success", **labels},
        "value": [int(time.time()), "1"],
    }
```

## Task 1: Model Config Smoke Tests

**Files:**
- Test: `server/apps/cmdb/tests/test_new_collect_objects_model_config.py`
- Modify: `server/apps/cmdb/support-files/model_config.xlsx`

- [ ] **Step 1: Write failing tests for model presence and classification**

```python
import pandas as pd


MODEL_CONFIG = "apps/cmdb/support-files/model_config.xlsx"


EXPECTED_MODELS = {
    "nacos": "middleware",
    "nacos_node": "middleware",
    "nacos_namespace": "middleware",
    "nacos_service": "middleware",
    "ibmmq": "middleware",
    "ibmmq_channel": "middleware",
    "ibmmq_listener": "middleware",
    "ibmmq_localqueue": "middleware",
    "ibmmq_remotequeue": "middleware",
    "oceanbase": "database",
    "oceanbase_zone": "database",
    "oceanbase_server": "database",
    "oceanbase_tenant": "database",
    "highgo": "database",
    "server_bmc": "harware",
    "server_bmc_cpu": "hardware_components",
    "server_bmc_memory": "hardware_components",
    "server_bmc_disk": "hardware_components",
    "server_bmc_vdisk": "hardware_components",
    "server_bmc_nic": "hardware_components",
}


def test_batch1_models_have_expected_classifications():
    models = pd.read_excel(MODEL_CONFIG, sheet_name="models", header=1)
    by_id = models.set_index("model_id")["classification_id"].to_dict()

    for model_id, classification_id in EXPECTED_MODELS.items():
        assert by_id[model_id] == classification_id


def test_batch1_models_use_existing_icons():
    models = pd.read_excel(MODEL_CONFIG, sheet_name="models", header=1)
    by_id = models.set_index("model_id")["icn"].to_dict()

    for model_id in EXPECTED_MODELS:
        assert isinstance(by_id[model_id], str)
        assert by_id[model_id].strip()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_new_collect_objects_model_config.py
```

Expected: FAIL with `KeyError` for `nacos` or another missing Batch 1 model.

- [ ] **Step 3: Update `model_config.xlsx`**

Use a short Python/openpyxl script outside the repo or direct spreadsheet editing. Add these rows to `models`:

| model_id | model_name | classification_id |
| --- | --- | --- |
| nacos | Nacos | middleware |
| nacos_node | Nacos节点 | middleware |
| nacos_namespace | Nacos命名空间 | middleware |
| nacos_service | Nacos服务 | middleware |
| ibmmq | IBM MQ | middleware |
| ibmmq_channel | IBM MQ通道 | middleware |
| ibmmq_listener | IBM MQ监听器 | middleware |
| ibmmq_localqueue | IBM MQ本地队列 | middleware |
| ibmmq_remotequeue | IBM MQ远程队列 | middleware |
| oceanbase | OceanBase | database |
| oceanbase_zone | OceanBase Zone | database |
| oceanbase_server | OceanBase节点 | database |
| oceanbase_tenant | OceanBase租户 | database |
| highgo | 瀚高HighGo | database |
| server_bmc | 服务器BMC | harware |
| server_bmc_cpu | BMC CPU | hardware_components |
| server_bmc_memory | BMC内存 | hardware_components |
| server_bmc_disk | BMC物理磁盘 | hardware_components |
| server_bmc_vdisk | BMC虚拟磁盘 | hardware_components |
| server_bmc_nic | BMC网卡 | hardware_components |

Use existing icon values from nearby models:

- middleware children: reuse `rabbitmq` or `zookeeper` icon.
- database children: reuse `postgresql` icon.
- `server_bmc`: reuse `physcial_server` icon.
- BMC children: reuse `disk`、`memory`、`nic` or existing hardware component icon.

Add field definitions:

- `nacos`: `inst_name`, `ip_addr`, `port`, `name`, `version`, `mode`, `node_count`, `service_count`, `instance_count`, `config_count`, `namespace_count`
- `nacos_node`: `inst_name`, `ip`, `port`, `state`, `version`, `raft_role`, `last_refresh`
- `nacos_namespace`: `inst_name`, `namespace_id`, `name`, `config_count`, `quota`, `type`
- `nacos_service`: `inst_name`, `service_name`, `group_name`, `namespace`, `instance_count`, `healthy_count`, `protect_threshold`
- `ibmmq`: `inst_name`, `ip_addr`, `qmgr_name`, `version`, `port`, `deadq`, `install_path`, `hostname`, `status`
- `ibmmq_channel`: `inst_name`, `name`, `channel_type`, `xmitq`, `remote_ip`, `remote_port`
- `ibmmq_listener`: `inst_name`, `name`, `port`, `status`
- `ibmmq_localqueue`: `inst_name`, `name`, `q_type`, `maxmsgl`, `q_max_depth`, `q_trigdata`, `curdepth`
- `ibmmq_remotequeue`: `inst_name`, `name`, `q_type`, `destq`, `remote_qmgr_name`
- `oceanbase`: `inst_name`, `ip_addr`, `port`, `cluster_name`, `version`, `server_count`, `zone_count`, `tenant_count`, `compatibility`
- `oceanbase_zone`: `inst_name`, `zone_name`, `region`, `status`, `idc`, `server_count`
- `oceanbase_server`: `inst_name`, `svr_ip`, `svr_port`, `zone`, `status`, `build_version`, `cpu_capacity`, `memory_capacity`, `start_time`, `stop_time`
- `oceanbase_tenant`: `inst_name`, `tenant_id`, `tenant_name`, `tenant_type`, `compatibility_mode`, `status`, `primary_zone`, `locality`
- `highgo`: `inst_name`, `ip_addr`, `port`, `version`, `config`, `data_path`, `max_connect`, `shared_buffer`, `log_directory`
- `server_bmc`: `inst_name`, `ip_addr`, `brand`, `model`, `serial_number`, `bmc_version`, `bios_version`, `power_state`, `health`, `cpu_total`, `memory_total`, `phys_size`
- `server_bmc_cpu`: `inst_name`, `name`, `model`, `cores`, `speed`, `status`
- `server_bmc_memory`: `inst_name`, `name`, `capacity`, `speed`, `type`, `slot`, `status`
- `server_bmc_disk`: `inst_name`, `name`, `disk_size`, `disk_type`, `disk_media`, `disk_rpm`, `status`
- `server_bmc_vdisk`: `inst_name`, `name`, `raid_level`, `vdisk_size`, `disk_media`, `status`
- `server_bmc_nic`: `inst_name`, `name`, `mac_addr`, `speed`, `status`

Add belong relations:

- `nacos_node_belong_nacos`
- `nacos_namespace_belong_nacos`
- `nacos_service_belong_nacos`
- `ibmmq_channel_belong_ibmmq`
- `ibmmq_listener_belong_ibmmq`
- `ibmmq_localqueue_belong_ibmmq`
- `ibmmq_remotequeue_belong_ibmmq`
- `oceanbase_zone_belong_oceanbase`
- `oceanbase_server_belong_oceanbase`
- `oceanbase_server_belong_oceanbase_zone`
- `oceanbase_tenant_belong_oceanbase`
- `server_bmc_cpu_belong_server_bmc`
- `server_bmc_memory_belong_server_bmc`
- `server_bmc_disk_belong_server_bmc`
- `server_bmc_vdisk_belong_server_bmc`
- `server_bmc_nic_belong_server_bmc`
- `server_bmc_belong_physcial_server`

- [ ] **Step 4: Run model config test**

Run the same pytest command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/apps/cmdb/support-files/model_config.xlsx server/apps/cmdb/tests/test_new_collect_objects_model_config.py
git commit -m "test: add batch1 cmdb model config coverage"
```

## Task 2: Collection Tree and Metric Maps

**Files:**
- Modify: `server/apps/cmdb/constants/constants.py`
- Modify: `server/apps/cmdb/collection/constants.py`
- Test: `server/apps/cmdb/tests/test_new_collect_objects_registry.py`

- [ ] **Step 1: Write failing tests**

```python
from apps.cmdb.collection.constants import DB_COLLECT_METRIC_MAP, MIDDLEWARE_METRIC_MAP, PROTOCOL_METRIC_MAP
from apps.cmdb.constants.constants import COLLECT_OBJ_TREE, CollectDriverTypes, CollectPluginTypes


def _tree_items(group_id):
    return {item["id"]: item for item in COLLECT_OBJ_TREE[group_id]["children"]}


def test_batch1_collect_tree_entries():
    middleware = _tree_items("middleware")
    databases = _tree_items("databases")
    host_manage = _tree_items("host_manage")

    assert middleware["nacos"]["task_type"] == CollectPluginTypes.MIDDLEWARE
    assert middleware["nacos"]["type"] == CollectDriverTypes.PROTOCOL
    assert middleware["ibmmq"]["task_type"] == CollectPluginTypes.MIDDLEWARE
    assert middleware["ibmmq"]["type"] == CollectDriverTypes.JOB
    assert databases["oceanbase"]["task_type"] == CollectPluginTypes.PROTOCOL
    assert databases["highgo"]["task_type"] == CollectPluginTypes.PROTOCOL
    assert host_manage["server_bmc"]["task_type"] == CollectPluginTypes.PROTOCOL
    assert host_manage["server_bmc"]["type"] == CollectDriverTypes.PROTOCOL


def test_batch1_metric_maps():
    assert MIDDLEWARE_METRIC_MAP["nacos"] == [
        "nacos_info_gauge",
        "nacos_node_info_gauge",
        "nacos_namespace_info_gauge",
        "nacos_service_info_gauge",
    ]
    assert MIDDLEWARE_METRIC_MAP["ibmmq"] == [
        "ibmmq_info_gauge",
        "ibmmq_channel_info_gauge",
        "ibmmq_listener_info_gauge",
        "ibmmq_localqueue_info_gauge",
        "ibmmq_remotequeue_info_gauge",
    ]
    assert PROTOCOL_METRIC_MAP["oceanbase"] == [
        "oceanbase_info_gauge",
        "oceanbase_zone_info_gauge",
        "oceanbase_server_info_gauge",
        "oceanbase_tenant_info_gauge",
    ]
    assert PROTOCOL_METRIC_MAP["highgo"] == ["highgo_info_gauge"]
    assert PROTOCOL_METRIC_MAP["server_bmc"] == [
        "server_bmc_info_gauge",
        "server_bmc_cpu_info_gauge",
        "server_bmc_memory_info_gauge",
        "server_bmc_disk_info_gauge",
        "server_bmc_vdisk_info_gauge",
        "server_bmc_nic_info_gauge",
    ]
    assert DB_COLLECT_METRIC_MAP["oceanbase"] == PROTOCOL_METRIC_MAP["oceanbase"]
    assert DB_COLLECT_METRIC_MAP["highgo"] == ["highgo_info_gauge"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_new_collect_objects_registry.py
```

Expected: FAIL because new tree entries and metric mappings are missing.

- [ ] **Step 3: Add tree entries**

In `COLLECT_OBJ_TREE`:

- Add `nacos` and `ibmmq` under `middleware`.
- Add `oceanbase` and `highgo` under `databases`.
- Add `server_bmc` under `host_manage`.

Each entry must include:

```python
{
    "id": "nacos",
    "name": "Nacos",
    "model_id": "nacos",
    "task_type": CollectPluginTypes.MIDDLEWARE,
    "type": CollectDriverTypes.PROTOCOL,
    "tag": ["REST", "配置中心"],
    "encrypted_fields": ["password"],
}
```

Use the same shape for the other four entries:

- `ibmmq`: name `IBM MQ`, `task_type=CollectPluginTypes.MIDDLEWARE`, `type=CollectDriverTypes.JOB`, tags `["JOB", "Linux"]`
- `oceanbase`: name `OceanBase`, `task_type=CollectPluginTypes.PROTOCOL`, `type=CollectDriverTypes.PROTOCOL`, tags `["国产", "分布式DB"]`
- `highgo`: name `瀚高HighGo`, `task_type=CollectPluginTypes.PROTOCOL`, `type=CollectDriverTypes.PROTOCOL`, tags `["国产", "PG兼容"]`
- `server_bmc`: name `服务器BMC`, `task_type=CollectPluginTypes.PROTOCOL`, `type=CollectDriverTypes.PROTOCOL`, tags `["Redfish"]`

- [ ] **Step 4: Add metric maps**

Add exact mappings from the test into `server/apps/cmdb/collection/constants.py`.

- [ ] **Step 5: Run tests**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add server/apps/cmdb/constants/constants.py server/apps/cmdb/collection/constants.py server/apps/cmdb/tests/test_new_collect_objects_registry.py
git commit -m "feat: register batch1 cmdb collect objects"
```

## Task 3: NodeParams Registration

**Files:**
- Create: `server/apps/cmdb/node_configs/protocol/nacos.py`
- Create: `server/apps/cmdb/node_configs/protocol/oceanbase.py`
- Create: `server/apps/cmdb/node_configs/protocol/highgo.py`
- Create: `server/apps/cmdb/node_configs/protocol/server_bmc.py`
- Create: `server/apps/cmdb/node_configs/ssh/ibmmq.py`
- Test: `server/apps/cmdb/tests/test_new_collect_objects_registry.py`

- [ ] **Step 1: Extend failing tests**

Append:

```python
from apps.cmdb.node_configs.base import BaseNodeParams


def test_batch1_node_params_registered_by_model_and_driver():
    expected = {
        ("nacos", "PROTOCOL"): "nacos_info",
        ("ibmmq", "JOB"): "ibmmq_info",
        ("oceanbase", "PROTOCOL"): "oceanbase_info",
        ("highgo", "PROTOCOL"): "highgo_info",
        ("server_bmc", "PROTOCOL"): "server_bmc_info",
    }

    for key, plugin_name in expected.items():
        assert BaseNodeParams.PLUGIN_MAP[key] == plugin_name
        assert key in BaseNodeParams._registry
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_new_collect_objects_registry.py::test_batch1_node_params_registered_by_model_and_driver
```

Expected: FAIL because NodeParams classes are missing.

- [ ] **Step 3: Add protocol NodeParams**

Create `server/apps/cmdb/node_configs/protocol/nacos.py`:

```python
from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.node_configs.base import BaseNodeParams


class NacosNodeParams(BaseNodeParams):
    supported_model_id = "nacos"
    supported_driver_type = CollectDriverTypes.PROTOCOL
    plugin_name = "nacos_info"
    host_field = "ip_addr"
    default_port = 8848

    def set_credential(self, *args, **kwargs):
        port = self.credential.get("port", self.default_port) if self.credential else self.default_port
        return {
            "username": self.credential.get("username", "") if self.credential else "",
            "password": "${" + self._password_env_name() + "}" if self.credential else "",
            "port": port,
            "ssl": self.credential.get("ssl", False) if self.credential else False,
        }

    def env_config(self, *args, **kwargs):
        if not self.credential:
            return {}
        return {self._password_env_name(): self.credential.get("password", "")}

    def _password_env_name(self):
        return f"PASSWORD_password_{self._instance_id}"
```

Create `server/apps/cmdb/node_configs/protocol/server_bmc.py` with the same structure, changing:

```python
class ServerBmcNodeParams(BaseNodeParams):
    supported_model_id = "server_bmc"
    supported_driver_type = CollectDriverTypes.PROTOCOL
    plugin_name = "server_bmc_info"
    host_field = "ip_addr"
    default_port = 443
```

Create `server/apps/cmdb/node_configs/protocol/oceanbase.py` using `DirectPasswordNodeParamsMixin`:

```python
from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.databases.direct_password import DirectPasswordNodeParamsMixin


class OceanBaseNodeParams(DirectPasswordNodeParamsMixin, BaseNodeParams):
    supported_model_id = "oceanbase"
    supported_driver_type = CollectDriverTypes.PROTOCOL
    plugin_name = "oceanbase_info"
    default_port = 2881

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host_field = "ip_addr"
        self.executor_type = "protocol"
```

Create `server/apps/cmdb/node_configs/protocol/highgo.py`:

```python
from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.databases.direct_password import DirectPasswordNodeParamsMixin


class HighGoNodeParams(DirectPasswordNodeParamsMixin, BaseNodeParams):
    supported_model_id = "highgo"
    supported_driver_type = CollectDriverTypes.PROTOCOL
    plugin_name = "highgo_info"
    default_port = 5432

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.host_field = "ip_addr"
        self.executor_type = "protocol"
```

Create `server/apps/cmdb/node_configs/ssh/ibmmq.py`:

```python
from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.node_configs.base import BaseNodeParams
from apps.cmdb.node_configs.ssh.base import SSHNodeParamsMixin


class IbmMqNodeParams(SSHNodeParamsMixin, BaseNodeParams):
    supported_model_id = "ibmmq"
    supported_driver_type = CollectDriverTypes.JOB
    plugin_name = "ibmmq_info"
```

- [ ] **Step 4: Run NodeParams test**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/apps/cmdb/node_configs/protocol/nacos.py server/apps/cmdb/node_configs/protocol/oceanbase.py server/apps/cmdb/node_configs/protocol/highgo.py server/apps/cmdb/node_configs/protocol/server_bmc.py server/apps/cmdb/node_configs/ssh/ibmmq.py server/apps/cmdb/tests/test_new_collect_objects_registry.py
git commit -m "feat: add batch1 cmdb node params"
```

## Task 4: Server Collection Plugins and Formatter Mapping

**Files:**
- Create: `server/apps/cmdb/collection/collect_plugin/new_objects.py`
- Create: `server/apps/cmdb/collection/plugins/community/middleware/nacos.py`
- Create: `server/apps/cmdb/collection/plugins/community/middleware/ibmmq.py`
- Create: `server/apps/cmdb/collection/plugins/community/protocol/oceanbase.py`
- Create: `server/apps/cmdb/collection/plugins/community/protocol/highgo.py`
- Create: `server/apps/cmdb/collection/plugins/community/protocol/server_bmc.py`
- Test: `server/apps/cmdb/tests/test_new_collect_objects_registry.py`
- Test: `server/apps/cmdb/tests/test_new_collect_objects_formatters.py`

- [ ] **Step 1: Add failing registry tests**

Append:

```python
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import CollectPluginTypes


def test_batch1_collection_plugins_registered():
    assert get_collection_plugin(CollectPluginTypes.MIDDLEWARE, "nacos").supported_model_id == "nacos"
    assert get_collection_plugin(CollectPluginTypes.MIDDLEWARE, "ibmmq").supported_model_id == "ibmmq"
    assert get_collection_plugin(CollectPluginTypes.PROTOCOL, "oceanbase").supported_model_id == "oceanbase"
    assert get_collection_plugin(CollectPluginTypes.PROTOCOL, "highgo").supported_model_id == "highgo"
    assert get_collection_plugin(CollectPluginTypes.PROTOCOL, "server_bmc").supported_model_id == "server_bmc"
```

- [ ] **Step 2: Add failing formatter tests**

```python
from apps.cmdb.collection.collect_plugin.new_objects import (
    IbmMqCollectMetrics,
    NacosCollectMetrics,
    OceanBaseCollectMetrics,
    ServerBmcCollectMetrics,
)


def test_nacos_formatter_outputs_children_with_belong_associations():
    formatter = NacosCollectMetrics("10.0.0.10-nacos-8848", 1, 2)
    formatter.model_id = "nacos"
    formatter.format_data({
        "result": [
            metric("nacos_info_gauge", {"ip_addr": "10.0.0.10", "port": "8848", "version": "2.3.0", "mode": "cluster"}),
            metric("nacos_node_info_gauge", {"ip": "10.0.0.11", "port": "8848", "state": "UP"}),
        ]
    })
    formatter.format_metrics()

    assert formatter.result["nacos"][0]["inst_name"] == "10.0.0.10-nacos-8848"
    node = formatter.result["nacos_node"][0]
    assert node["inst_name"] == "10.0.0.10-nacos-8848/10.0.0.11:8848"
    assert node["assos"][0]["model_asst_id"] == "nacos_node_belong_nacos"


def test_ibmmq_formatter_outputs_queue_manager_children():
    formatter = IbmMqCollectMetrics("10.0.0.20-ibmmq-QM1", 1, 2)
    formatter.model_id = "ibmmq"
    formatter.format_data({
        "result": [
            metric("ibmmq_info_gauge", {"ip_addr": "10.0.0.20", "qmgr_name": "QM1", "status": "RUNNING"}),
            metric("ibmmq_channel_info_gauge", {"name": "TO.REMOTE", "channel_type": "SDR"}),
        ]
    })
    formatter.format_metrics()

    assert formatter.result["ibmmq"][0]["qmgr_name"] == "QM1"
    channel = formatter.result["ibmmq_channel"][0]
    assert channel["inst_name"] == "10.0.0.20-ibmmq-QM1/TO.REMOTE"
    assert channel["assos"][0]["model_asst_id"] == "ibmmq_channel_belong_ibmmq"


def test_oceanbase_formatter_outputs_zone_server_tenant():
    formatter = OceanBaseCollectMetrics("10.0.0.30-oceanbase-obcluster", 1, 2)
    formatter.model_id = "oceanbase"
    formatter.format_data({
        "result": [
            metric("oceanbase_info_gauge", {"ip_addr": "10.0.0.30", "port": "2881", "cluster_name": "obcluster"}),
            metric("oceanbase_zone_info_gauge", {"zone_name": "zone1", "status": "ACTIVE"}),
            metric("oceanbase_server_info_gauge", {"svr_ip": "10.0.0.31", "svr_port": "2882", "zone": "zone1"}),
            metric("oceanbase_tenant_info_gauge", {"tenant_id": "1002", "tenant_name": "tenant_a"}),
        ]
    })
    formatter.format_metrics()

    assert formatter.result["oceanbase_zone"][0]["inst_name"] == "10.0.0.30-oceanbase-obcluster/zone1"
    assert formatter.result["oceanbase_server"][0]["assos"][1]["model_asst_id"] == "oceanbase_server_belong_oceanbase_zone"
    assert formatter.result["oceanbase_tenant"][0]["tenant_name"] == "tenant_a"


def test_server_bmc_formatter_outputs_auto_relation_to_physical_server():
    formatter = ServerBmcCollectMetrics("10.0.0.40-server_bmc-SN123", 1, 2)
    formatter.model_id = "server_bmc"
    formatter.format_data({
        "result": [
            metric("server_bmc_info_gauge", {"ip_addr": "10.0.0.40", "serial_number": "SN123", "brand": "Dell"}),
            metric("server_bmc_cpu_info_gauge", {"name": "CPU1", "model": "Xeon", "cores": "16"}),
        ]
    })
    formatter.format_metrics()

    parent = formatter.result["server_bmc"][0]
    assert parent["inst_name"] == "10.0.0.40-server_bmc-SN123"
    assert parent["assos"][0]["model_asst_id"] == "server_bmc_belong_physcial_server"
    assert formatter.result["server_bmc_cpu"][0]["assos"][0]["model_asst_id"] == "server_bmc_cpu_belong_server_bmc"
```

- [ ] **Step 3: Run tests to verify failure**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_new_collect_objects_registry.py::test_batch1_collection_plugins_registered apps/cmdb/tests/test_new_collect_objects_formatters.py
```

Expected: FAIL because modules are missing.

- [ ] **Step 4: Implement `new_objects.py`**

Implement four classes modeled after `OceanStorCollectMetrics`:

- `MultiObjectCollectMetrics`: shared `format_data`, `format_metrics`, `_belong_parent`, `_child_inst_name`.
- `NacosCollectMetrics`: `MODEL_ORDER = ["nacos", "nacos_node", "nacos_namespace", "nacos_service"]`.
- `IbmMqCollectMetrics`: `MODEL_ORDER = ["ibmmq", "ibmmq_channel", "ibmmq_listener", "ibmmq_localqueue", "ibmmq_remotequeue"]`.
- `OceanBaseCollectMetrics`: `MODEL_ORDER = ["oceanbase", "oceanbase_zone", "oceanbase_server", "oceanbase_tenant"]`.
- `ServerBmcCollectMetrics`: `MODEL_ORDER = ["server_bmc", "server_bmc_cpu", "server_bmc_memory", "server_bmc_disk", "server_bmc_vdisk", "server_bmc_nic"]`.

The shared parent relation helper must return:

```python
{
    "model_id": parent_model,
    "inst_name": self.inst_name,
    "asst_id": "belong",
    "model_asst_id": f"{child_model}_belong_{parent_model}",
}
```

`ServerBmcCollectMetrics` must add a parent-level relation when `serial_number` exists:

```python
{
    "model_id": "physcial_server",
    "inst_name": data["serial_number"],
    "asst_id": "belong",
    "model_asst_id": "server_bmc_belong_physcial_server",
}
```

- [ ] **Step 5: Implement collection plugin classes**

Use exact `supported_task_type`:

- Nacos and IBM MQ: `CollectPluginTypes.MIDDLEWARE`
- OceanBase, HighGo, Server BMC: `CollectPluginTypes.PROTOCOL`

HighGo plugin should mirror `PostgresqlCollectionPlugin` field mapping, changing only:

```python
class HighGoCollectionPlugin(BaseProtocolCollectionPlugin):
    supported_model_id = "highgo"
    metric_names = ("highgo_info_gauge",)
```

- [ ] **Step 6: Run tests**

Run the command from Step 3.

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add server/apps/cmdb/collection/collect_plugin/new_objects.py server/apps/cmdb/collection/plugins/community/middleware/nacos.py server/apps/cmdb/collection/plugins/community/middleware/ibmmq.py server/apps/cmdb/collection/plugins/community/protocol/oceanbase.py server/apps/cmdb/collection/plugins/community/protocol/highgo.py server/apps/cmdb/collection/plugins/community/protocol/server_bmc.py server/apps/cmdb/tests/test_new_collect_objects_registry.py server/apps/cmdb/tests/test_new_collect_objects_formatters.py
git commit -m "feat: add batch1 cmdb collection formatters"
```

## Task 5: Stargazer Plugin Manifests and Collectors

**Files:**
- Create: `agents/stargazer/tests/test_new_collect_objects_plugins.py`
- Create: all Stargazer files listed in File Structure.

- [ ] **Step 1: Write failing Stargazer tests**

```python
import importlib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_plugin(model_id):
    return yaml.safe_load((ROOT / "plugins" / "inputs" / model_id / "plugin.yml").read_text())


def test_batch1_plugin_manifests_have_expected_defaults():
    expected = {
        "nacos": ("middleware", "protocol", "plugins.inputs.nacos.nacos_info", "NacosInfo"),
        "ibmmq": ("middleware", "job", "plugins.script_executor", "SSHPlugin"),
        "oceanbase": ("database", "protocol", "plugins.inputs.oceanbase.oceanbase_info", "OceanBaseInfo"),
        "highgo": ("database", "protocol", "plugins.inputs.highgo.highgo_info", "HighGoInfo"),
        "server_bmc": ("host_manage", "protocol", "plugins.inputs.server_bmc.server_bmc_info", "ServerBmcInfo"),
    }

    for model_id, (category, default_executor, module, class_name) in expected.items():
        plugin = load_plugin(model_id)
        assert plugin["metadata"]["model_id"] == model_id
        assert plugin["category"] == category
        assert plugin["default_executor"] == default_executor
        executor = plugin["executors"][default_executor]
        assert executor["collector"]["module"] == module
        assert executor["collector"]["class"] == class_name


def test_protocol_collectors_are_importable():
    imports = {
        "plugins.inputs.nacos.nacos_info": "NacosInfo",
        "plugins.inputs.oceanbase.oceanbase_info": "OceanBaseInfo",
        "plugins.inputs.highgo.highgo_info": "HighGoInfo",
        "plugins.inputs.server_bmc.server_bmc_info": "ServerBmcInfo",
    }
    for module_name, class_name in imports.items():
        module = importlib.import_module(module_name)
        assert hasattr(module, class_name)
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd agents/stargazer
uv run pytest -q tests/test_new_collect_objects_plugins.py
```

Expected: FAIL because plugin files are missing.

- [ ] **Step 3: Add `plugin.yml` files**

Use these defaults:

- `nacos`: category `middleware`, `default_executor: protocol`, collector `plugins.inputs.nacos.nacos_info.NacosInfo`
- `ibmmq`: category `middleware`, `default_executor: job`, script `plugins/inputs/ibmmq/ibmmq_default_discover.sh`, collector `plugins.script_executor.SSHPlugin`
- `oceanbase`: category `database`, `default_executor: protocol`, collector `plugins.inputs.oceanbase.oceanbase_info.OceanBaseInfo`
- `highgo`: category `database`, `default_executor: protocol`, collector `plugins.inputs.highgo.highgo_info.HighGoInfo`
- `server_bmc`: category `host_manage`, `default_executor: protocol`, collector `plugins.inputs.server_bmc.server_bmc_info.ServerBmcInfo`

- [ ] **Step 4: Add protocol collectors**

Implement minimal importable collectors:

- `HighGoInfo` subclasses `plugins.inputs.postgresql.postgresql_info.PostgresqlInfo` and renames `postgresql` results to `highgo`.
- `NacosInfo` uses `requests.Session`, logs in via `/nacos/v1/auth/login` when username/password exist, emits the four Nacos metric groups.
- `OceanBaseInfo` uses `pymysql`, queries `SELECT ob_version()`, `SHOW PARAMETERS LIKE 'cluster'`, `DBA_OB_ZONES`, `DBA_OB_SERVERS`, `DBA_OB_TENANTS`.
- `ServerBmcInfo` uses `requests.Session` with Basic Auth, only sends GET requests to Redfish endpoints, emits six metric groups.

Collectors must catch per-endpoint exceptions and include `cmdb_collect_error` on the affected metric instead of raising for the whole run.

- [ ] **Step 5: Add IBM MQ script**

Create `agents/stargazer/plugins/inputs/ibmmq/ibmmq_default_discover.sh`:

- Use `dspmq -o all`, `runmqsc -e <qmgr>`.
- Only run display commands: `dis qmgr`, `dis queue`, `dis channel`, `dis LSSTATUS`, `dis listener`.
- Do not run MQ start/stop/delete/change commands.
- Output one JSON object per running queue manager.

- [ ] **Step 6: Run Stargazer tests**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add agents/stargazer/plugins/inputs/nacos agents/stargazer/plugins/inputs/ibmmq agents/stargazer/plugins/inputs/oceanbase agents/stargazer/plugins/inputs/highgo agents/stargazer/plugins/inputs/server_bmc agents/stargazer/tests/test_new_collect_objects_plugins.py
git commit -m "feat: add batch1 stargazer collect plugins"
```

## Task 6: End-to-End Formatter Smoke Verification

**Files:**
- Test: `server/apps/cmdb/tests/e2e/test_new_collect_objects_pipeline.py`

- [ ] **Step 1: Write pipeline tests using mocked metric payloads**

Create tests that call the formatter classes directly with payloads shaped like Stargazer output and assert:

- each parent model has one instance;
- each child model has at least one instance;
- each child instance has an `assos` list;
- `server_bmc` parent has `server_bmc_belong_physcial_server` relation when serial number is present.

- [ ] **Step 2: Run pipeline tests**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/e2e/test_new_collect_objects_pipeline.py
```

Expected: PASS.

- [ ] **Step 3: Run focused Batch 1 server tests**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_new_collect_objects_model_config.py apps/cmdb/tests/test_new_collect_objects_registry.py apps/cmdb/tests/test_new_collect_objects_formatters.py apps/cmdb/tests/e2e/test_new_collect_objects_pipeline.py
```

Expected: PASS.

- [ ] **Step 4: Run Stargazer plugin tests**

```bash
cd agents/stargazer
uv run pytest -q tests/test_new_collect_objects_plugins.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/apps/cmdb/tests/e2e/test_new_collect_objects_pipeline.py
git commit -m "test: add batch1 cmdb collect pipeline smoke tests"
```

## Task 7: Final Verification

**Files:**
- No source edits unless tests reveal defects.

- [ ] **Step 1: Run server focused verification**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_new_collect_objects_model_config.py apps/cmdb/tests/test_new_collect_objects_registry.py apps/cmdb/tests/test_new_collect_objects_formatters.py apps/cmdb/tests/e2e/test_new_collect_objects_pipeline.py
```

Expected: PASS.

- [ ] **Step 2: Run Stargazer focused verification**

```bash
cd agents/stargazer
uv run pytest -q tests/test_new_collect_objects_plugins.py
```

Expected: PASS.

- [ ] **Step 3: Run lint for touched Python server files**

```bash
cd server
uv run ruff check apps/cmdb/node_configs/protocol/nacos.py apps/cmdb/node_configs/protocol/oceanbase.py apps/cmdb/node_configs/protocol/highgo.py apps/cmdb/node_configs/protocol/server_bmc.py apps/cmdb/node_configs/ssh/ibmmq.py apps/cmdb/collection/collect_plugin/new_objects.py apps/cmdb/collection/plugins/community/middleware/nacos.py apps/cmdb/collection/plugins/community/middleware/ibmmq.py apps/cmdb/collection/plugins/community/protocol/oceanbase.py apps/cmdb/collection/plugins/community/protocol/highgo.py apps/cmdb/collection/plugins/community/protocol/server_bmc.py apps/cmdb/tests/test_new_collect_objects_model_config.py apps/cmdb/tests/test_new_collect_objects_registry.py apps/cmdb/tests/test_new_collect_objects_formatters.py apps/cmdb/tests/e2e/test_new_collect_objects_pipeline.py
```

Expected: PASS.

- [ ] **Step 4: Run lint for Stargazer touched Python files**

```bash
cd agents/stargazer
uv run ruff check plugins/inputs/nacos/nacos_info.py plugins/inputs/oceanbase/oceanbase_info.py plugins/inputs/highgo/highgo_info.py plugins/inputs/server_bmc/server_bmc_info.py tests/test_new_collect_objects_plugins.py
```

Expected: PASS.

- [ ] **Step 5: Inspect final git diff**

```bash
git status --short
git diff --stat
```

Expected: only Batch 1 CMDB/Stargazer files and tests are changed, plus the approved design/plan docs.

## Self-Review

Spec coverage:

- Community-only boundary: covered by file structure and all paths under `server/apps/cmdb` and `agents/stargazer`.
- Batch 1 object list: covered by Tasks 1-6.
- Model classifications: covered by Task 1.
- HMC/XSKY/ZStack/H3C CAS decisions: not implemented in Batch 1; captured in the design doc for later batches.
- Server BMC to `physcial_server` association at ingest time: covered by Task 4 formatter relation and Task 6 smoke verification.
- Existing icons first: covered by Task 1 test and model update instruction.
- TDD: every implementation task starts with a failing test and a command to prove failure.

Placeholder scan:

- No `TBD`, `TODO`, or unspecified implementation steps remain.
- Object fields, relation IDs, metric names, and paths are explicit.

Type consistency:

- Model IDs use `server_bmc`, not the source document's older `pc_server`.
- Existing typo `physcial_server` and classification `harware` are preserved intentionally.
- Task type constants are explicit: Nacos/IBM MQ use `MIDDLEWARE`; OceanBase/HighGo/Server BMC use `PROTOCOL`.
