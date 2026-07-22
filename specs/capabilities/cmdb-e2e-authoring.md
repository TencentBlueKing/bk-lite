# CMDB e2e Fixture 作者指南

> v4 Phase 1 — 给后续给新对象加 e2e 的 step-by-step 文档
> 目标:5 分钟上手,5 步加完一个对象

## 1. 整体结构

每个对象的 e2e 需要 5 个文件:

```
server/apps/cmdb/tests/e2e/
├── fixtures/<model_id>/
│   ├── 01_stargazer_raw.json            ← 复制 stargazer 落盘(2.5 步)
│   └── 04_expected_cmdb_result.json     ← 字段期望值(2.5 步)
├── schemas/<model_id>/
│   ├── 01_stargazer_raw.schema.json    ← 契约层(1 步)
│   └── 04_cmdb_instance.schema.json    ← 实例层(1 步)
└── test_<model_id>_pipeline.py         ← test 文件(1 步,工厂版可省略)
```

## 2. 五步加一个新对象 e2e

### 步骤 0:确认对象在 factory 工厂覆盖范围

`server/apps/cmdb/tests/e2e/conftest.py::_MODEL_RUNNER_MAP` 已有 31 个对象。

**新对象** → 需在 `_MODEL_RUNNER_MAP` 追加一行:

```python
"my_new_obj":    ("middleware", {"result": True}),  # 三选一:protocol/db/middleware
```

如果对象的 plugin 类不在 `apps/cmdb/collection/plugins/community/{db,middleware,protocol}/<model_id>.py`,需先实现 plugin(参考已有 plugin)。

### 步骤 1:复制 stargazer 真实落盘 fixture

```bash
cp agents/stargazer/tests/fixtures/collect/<model_id>.json \
   server/apps/cmdb/tests/e2e/fixtures/<model_id>/01_stargazer_raw.json
```

**前提**:stargazer 端已落盘(已通过 `python -m tests.collect_fixtures.cli <model_id>` 跑通)。

**两种 raw_stdout 形态**(2026-07-10 调研发现):

- **形态 A**(mysql/redis/influxdb 风格):
  ```json
  {
    "model_id": "mysql",
    "captured_at": "2026-07-04T16:43:33Z",
    "raw_stdout": {
      "success": true,
      "result": {
        "mysql": [
          {"ip_addr": "127.0.0.1", "port": 13306, "version": "8.0.46", ...}
        ]
      }
    }
  }
  ```
- **形态 B**(nginx 风格,raw_stdout 自身就是平铺 dict):
  ```json
  {
    "model_id": "nginx",
    "captured_at": "2026-07-08T06:34:48Z",
    "raw_stdout": {
      "ip_addr": "172.17.0.2",
      "listen_port": "80",
      "version": "1.18.0",
      ...
    }
  }
  ```

公共契约(`schemas/00_common_contract.schema.json`)用 `oneOf` 兼容两种形态。

### 步骤 2:写 01_stargazer_raw.schema.json

复制模板,**最少必填**字段:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Stargazer <model_id> 采集原始输出契约",
  "type": "object",
  "required": ["model_id", "captured_at", "raw_stdout"],
  "properties": {
    "model_id":    {"type": "string", "pattern": "^<model_id>$"},
    "captured_at": {"type": "string", "format": "date-time"},
    "raw_stdout":  {
      "type": "object",
      "required": ["ip_addr", "port"],
      "properties": {
        "ip_addr": {"type": "string"},
        "port":    {"type": ["string", "integer"]},
        "version": {"type": "string"}
        /* 其他重要字段,例如:
        "basedir": {"type": "string"},
        "datadir": {"type": "string"},
        */
      }
    }
  }
}
```

**注意**:`raw_stdout` 的具体形态(形态 A 或 B)由公共契约 `oneOf` 决定,本 schema 只规定具体业务字段。

### 步骤 3:写 04_cmdb_instance.schema.json

CMDB 实例输出契约,基于 plugin `field_mapping` 决定字段:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "CMDB <model_id> 实例契约",
  "type": "object",
  "required": ["inst_name", "ip_addr", "port"],
  "properties": {
    "inst_name": {"type": "string", "pattern": "^[0-9.]+-<model_id>-[0-9]+$"},
    "ip_addr":   {"type": "string"},
    "port":      {"type": ["string", "integer"]},
    "version":   {"type": "string"}
    /* 其他 plugin field_mapping 支持的字段 */
  }
}
```

**如何知道 plugin 支持哪些字段?** 看 `apps/cmdb/collection/plugins/community/{db,middleware,protocol}/<model_id>.py` 里的 `field_mapping` dict。

### 步骤 4:写 04_expected_cmdb_result.json

从 `01_stargazer_raw.json` 抽出**关键字段**作为期望值。

**两种 fixture 源**(可能不同,分别声明):

```json
{
  "model_id": "<model_id>",
  "instance_count_min": 1,
  "expected_instance_subset_fixture_driven": {
    "inst_name": "<从 stargazer raw 计算: {ip}-{model_id}-{port}>",
    "ip_addr":   "<从 stargazer raw 抄>",
    "port":      "<从 stargazer raw 抄>",
    "version":   "<从 stargazer raw 抄>"
  },
  "fixture_source_fixture_driven": "agents/stargazer/tests/fixtures/collect/<model_id>.json(<日期> cli 真实落盘)",
  "notes": "<runner 类型说明>"
}
```

**关键原则**:
- `expected_instance_subset_fixture_driven` 只包含 **plugin field_mapping 实际支持**的字段
- 不要期望 plugin 不映射的字段(如 mysql 的 role / master_host)
- version 之类"采集时可能为空"的字段,fixture_driven 留空字符串,end_to_end 写实际值

### 步骤 5:(可选)写 test_<model_id>_pipeline.py

**如果** 已在 conftest._MODEL_RUNNER_MAP 覆盖,只需把对象加进 `test_pipeline_factory.py::FACTORY_COVERED_MODEL_IDS` 列表,工厂自动跑通(无需单独写 test)。

**如果** 对象需要特殊处理(自定义 raw_items 提取、自定义 expected_subset),才单独写 test_<model_id>_pipeline.py(参考 `test_nginx_pipeline.py` 的 `listen_port ?? port` 回退逻辑)。

### 步骤 6:跑测试

```bash
cd server
DB_ENGINE=sqlite INSTALL_APPS=cmdb,system_mgmt,core \
  .venv/bin/python -m pytest apps/cmdb/tests/e2e/test_pipeline_factory.py::test_pipeline_fixture_driven_via_factory[my_new_obj] -v
```

期望:`1 passed`。

## 3. 失败排查

| 错误 | 原因 | 修复 |
|---|---|---|
| `KeyError: model_id='X' 不在 _MODEL_RUNNER_MAP` | 工厂未覆盖 | 在 conftest._MODEL_RUNNER_MAP 追加 |
| `未在 db/middleware/protocol 三个子目录找到 plugin 类` | plugin 类未实现 | 在 `apps/cmdb/collection/plugins/community/{大类}/<model_id>.py` 实现 plugin |
| `jsonschema.ValidationError: 'success' is a required property` | 公共契约要求 success | 检查 stargazer 落盘的 raw_stdout 形态,需为 A 形态 `{success: true, result: {...}}` |
| `字段 X：期望 Y,实际 Z` | plugin field_mapping 与 expected_subset 不一致 | 修 expected_subset(取子集)或修 plugin field_mapping(加字段) |
| `inst_name 规则违反:X != Y` | runner get_inst_name 改了规则 | 检查 plugin 的 get_inst_name 方法,或更新 inst_name 模式 |

## 4. 进阶:批量铺对象

如需批量铺多个对象,用 `test_common_contract.py` 跨对象契约测试 + `test_pipeline_factory.py` 参数化模板:

```bash
# 跨对象公共契约(自动覆盖所有 31 个对象,未落盘的 skip)
DB_ENGINE=sqlite INSTALL_APPS=cmdb,system_mgmt,core \
  .venv/bin/python -m pytest apps/cmdb/tests/e2e/test_common_contract.py -v

# 工厂版流水线(目前覆盖 4 个对象,新对象需追加到 FACTORY_COVERED_MODEL_IDS)
DB_ENGINE=sqlite INSTALL_APPS=cmdb,system_mgmt,core \
  .venv/bin/python -m pytest apps/cmdb/tests/e2e/test_pipeline_factory.py -v
```

## 5. 参考

- 已有 4 个对象的范本(2026-07-10 commit):`test_influxdb_pipeline.py` / `test_mysql_pipeline.py` / `test_nginx_pipeline.py` / `test_redis_pipeline.py`
- 当前实现与验收事实以 `server/apps/cmdb/tests/e2e/` 下的 fixture、schema、测试和工具为准。

---

# 6. v2 章节:A/B 端对齐检查 / Placeholder 模式 / Drift Report(2026-07-13)

> 本章节是 v5 阶段(53 commit / 315 files / 521 passed e2e)新增能力。**v3+v4 工作(33 真实落盘对象 e2e 100% 覆盖)沿用 §1-§5 的 5 步流程,本章节仅适用于新增对象 / license 解锁升级 / 字段漂移检测**。

## 6.1 A/B 端对齐检查(基于 `model_reflection` + alignment test)

### 6.1.1 model_reflection 反射工具

**位置**:`server/apps/cmdb/tests/e2e/utils/model_reflection.py`

**接口**:
```python
from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def, ModelFieldDef

# 返回 {field_name: ModelFieldDef} 字典
fields = get_model_field_def("mysql")
# fields["inst_name"] = ModelFieldDef(name="inst_name", field_type="str", is_required=True)
# fields["port"] = ModelFieldDef(name="port", field_type="str", is_required=False)
```

**数据源**:读 `04_cmdb_instance.schema.json`(JSON Schema),**不是 Django ORM Model**。**CMDB 实例模型是 graph-backed 动态 model,不是 Django ORM**。

**SCHEMA_DIR_ALIAS 机制**:model_id 跟 schema 目录名不一致时(`aliyun_ecs` → `aliyun/`, `vmware_vc` → `vmware/`, `k8s_namespace` → `k8s/`),加 alias 映射。

### 6.1.2 A 端对齐检查(`test_stargazer_prometheus_alignment.py`)

**3 个参数化测试**:

| 测试 | 检查项 | 失败信号 |
|---|---|---|
| `test_a_alignment_metric_name_suffix` | `metric.__name__` 后缀合法(`_<model_id>_info_gauge` / `prometheus_kube_*`) | 后缀错 |
| `test_a_alignment_instance_id_label` | `metric.instance_id == "cmdb_<task_id>"` | 格式错 |
| `test_a_alignment_business_labels` | 业务 label 集合 ⊇ model 必填字段 | 漏字段 |

**A_LABEL_EXCLUDE 机制**:`inst_name` / `cpu_arch` / `model_id` / `id` / `create_time` / `update_time` / `assos` 是 runner 派生字段,不在 03 metric label 里,需排除。

**A 端主 metric filter**:`test_a_alignment_business_labels` 只查主 metric `{model_id}_info_gauge`,跳过附属 metric(如 `host_proc_usage_info_gauge`)。

**K8s 走 minimal path**:K8s 走 `CollectK8sMetrics.run()` 直接拉 VM,不走 `step1_normalize + step2_push_to_vm`,A 端对齐检查 `pytest.skip` 当 `model_id.startswith("k8s_")`。

### 6.1.3 B 端对齐检查(`test_cmdb_vm_format_alignment.py`)

**2 个参数化测试**:

| 测试 | 检查项 | 失败信号 |
|---|---|---|
| `test_b_alignment_field_subset` | 实例字段 ⊆ model 字段定义 | 漏字段 |
| `test_b_alignment_required_nonempty` | Model `is_required` 字段非空 | 必填空 |

**P0_RUNNER_PLUGIN 注册表**:对象特殊路径(aliyun / vmware 走 sub-model mapping;network 走 CollectNetworkMetrics 特殊路径),`P0_RUNNER_PLUGIN` 集中管理。

**B 端 placeholder skip**:archived 对象 plugin stub 空 `metric_names/field_mappings` 触发 `KeyError`,B 端加 `pytest.skip` 当 `_placeholder_reason` 存在。

**B 端 `@pytest.mark.django_db`**:alibaba-style plugin 实例化需 DB。

### 6.1.4 加新对象 A/B 端覆盖

1. 加进 `ALIGNMENT_COVERED_MODEL_IDS`(`conftest.py` 末尾 fixture,append 不重写)
2. 写 `04_cmdb_instance.schema.json`(model 字段定义)
3. 写 `01_stargazer_raw.json` / `04_expected_cmdb_result.json`(fixture)
4. 跑 A/B 端 alignment test 验证
5. 跑 `make e2e-drift-report` 验证 fixture 跟 model 一致

## 6.2 Placeholder 模式(`_placeholder_reason` + `license_status` + archived plugin stub)

### 6.2.1 3 种 `_placeholder_reason` 标注

| 标注 | 对象 | 数量 |
|---|---|---|
| `license_missing` | 17 license 类(apusic / bes / informix / ihs / inforsuite_as / iris / couchbase / oceanbase / oscar / sap_hana / sybase / tonggtp / tonglinkq / tongrds / tuxedo / weblogic / websphere) | 17 |
| `cluster_complex` | 4 cluster 类(hdfs / storm / yarn / mycat) | 4 |
| `platform_constraint` | 1 platform 类(domestic_linux) | 1 |

### 6.2.2 Placeholder fixture 模板

**01_stargazer_raw.json**(最小集):
```json
{
  "_placeholder_reason": "license_missing",
  "model_id": "<model_id>",
  "ip_addr": "192.0.2.1",
  "inst_name": "<model_id>-placeholder-01"
}
```

**04_expected_cmdb_result.json**:
```json
{
  "model_id": "<model_id>",
  "instance_count_min": 0,
  "expected_instance_subset": {},
  "license_status": "missing"
}
```

**04_cmdb_instance.schema.json**:
```json
{
  "type": "object",
  "required": ["_placeholder_reason", "license_status"],
  "properties": {
    "_placeholder_reason": {"type": "string", "enum": ["license_missing", "cluster_complex", "platform_constraint"]},
    "license_status": {"type": "string", "enum": ["available", "missing", "unknown"]}
  }
}
```

### 6.2.3 archived plugin stub 复用

**位置**:`server/apps/cmdb/collection/plugins/community/archived/<model_id>.py`

**模板**:
```python
from apps.cmdb.collection.plugins.base import AutoRegisterCollectionPluginMixin
from apps.cmdb.constants.constants import CollectPluginTypes


class ApusicCollectionPlugin(AutoRegisterCollectionPluginMixin):
    supported_task_type = CollectPluginTypes.MIDDLEWARE
    supported_model_id = "apusic"
    plugin_source = "community"
    priority = 1  # fallback,真实 plugin 替代后失效
    metric_names = []  # stub
    field_mappings = {}  # stub
```

**注意**:`archived/tuxedo.py` 会被既有 `middleware/tuxedo.py`(priority=10)覆盖,这是 by design(priority 差异),archived 是 fallback。

### 6.2.4 license 解锁后升级流程

1. 业务方提供 license + 真实 SDK
2. 替换 `fixtures/<model_id>/{01,02,03,04}.json` 为真实数据
3. 删 `_placeholder_reason` 字段
4. `license_status: "available"`
5. e2e test 自动从 placeholder 升级为 3 层验证(contract / pipeline / field alignment)
6. 测试代码无需改动

## 6.3 Drift Report 工具(字段漂移检测)

### 6.3.1 用途

扫描 `fixtures/<model_id>/04_expected_cmdb_result.json` 跟 `apps.cmdb.models.<Model>` 反射字段定义比对,生成漂移报告。

### 6.3.2 用法

**JSON 格式**(stdout):
```bash
cd server
.venv/bin/python -m apps.cmdb.tests.e2e.utils.drift_report --format json
```

**Markdown 格式**(写文件):
```bash
cd server
.venv/bin/python -m apps.cmdb.tests.e2e.utils.drift_report --format markdown -o drift_report.md
```

**Makefile target**:
```bash
cd server
make e2e-drift-report
```

**测试**(2 tests):
```bash
cd server
.venv/bin/python -m pytest apps/cmdb/tests/e2e/test_drift_report.py -v
```

### 6.3.3 输出字段

| 字段 | 含义 |
|---|---|
| `model_id` | 对象 ID |
| `status` | `ok` / `missing_or_mismatch` / `extra_fields` / `no_fixture` / `no_expected_subset` |
| `missing_fields` | model 有但 expected 没有(漏字段) |
| `extra_fields` | expected 有但 model 没有(多字段) |
| `type_mismatch` | 字段类型不匹配(如 vcpus 应该是 int 但成了 str) |

### 6.3.4 报告样例

参考 `server/apps/cmdb/tests/e2e/drift_report.md`(首次运行生成)。

### 6.3.5 集成到 CI(后续 follow-up)

当前:手动跑。下期集成到 CI,每次 PR 跑 + 报告写 artifact。

## 6.4 v2 章节速查表

| 能力 | 位置 | 用法 |
|---|---|---|
| `get_model_field_def` | `utils/model_reflection.py` | `from apps.cmdb.tests.e2e.utils.model_reflection import get_model_field_def` |
| A 端 alignment | `test_stargazer_prometheus_alignment.py` | 3 个参数化测试 |
| B 端 alignment | `test_cmdb_vm_format_alignment.py` | 2 个参数化测试 |
| Placeholder 模式 | `fixtures/<model_id>/{01,04}.json` | `_placeholder_reason` + `license_status` |
| Archived stub | `plugins/community/archived/<model_id>.py` | 空 metric_names / field_mappings |
| Drift report | `utils/drift_report.py` | `python -m ...utils.drift_report` |
| Makefile | `e2e-drift-report` target | `make e2e-drift-report` |
