# CMDB 配置采集数据链路验证 Implementation Plan

> **Required skill:** 实施本计划时必须使用 `subagent-driven-development` 或 `executing-plans`；每个生产缺陷还必须使用 `systematic-debugging` 与 `test-driven-development`。

**Goal:** 为全部生产采集对象建立 Stargazer→Prometheus/Line Protocol/NATS 与 VM→CMDB→FalkorDB 两段可定位的离线契约，并为八类代表对象建立隔离真实基础设施烟测。

**Architecture:** 以生产插件注册中心展开的 `(task_type, supported_model_id, emitted_model_id)` 为唯一覆盖真相源。Lane A 运行 Stargazer 的真实格式转换至 NATS 发布边界；Lane B 从真实形态 VM vector 响应运行 collect plugin、模型约束和图库写入意图；smoke 使用独立 NATS、Telegraf、VictoriaMetrics、FalkorDB 容器闭环验证。

**Tech Stack:** Python 3.12、pytest、Django 4.2、Sanic、`prometheus_client.parser`、`influxdb_client.Point`、NATS、Telegraf、VictoriaMetrics、FalkorDB、Docker Compose。

**Global Constraints:**

- 中文注释、测试名、提交信息和文档；仅改本任务相关文件，不做全仓格式化。
- 严格 TDD：每个行为先运行 RED，再写最小实现并运行 GREEN；发现生产缺陷先记录根因，单独提交。
- 生产对象缺 fixture、schema、Golden 或 provenance 必须失败，不得以 `skip`/`xfail` 计入覆盖。
- Golden 不能从生产 mapping 反向生成；云 fixture 只来自官方 API 文档，测试运行时禁止联网。
- 烟测只允许 loopback/Compose 网络；必须显式 `CMDB_COLLECTION_SMOKE=1`，所有资源带 `run_id`，清理按账本精准且幂等。
- 每个任务提交前只暂存该任务文件；最终全部分层测试、八类烟测、静态门禁和覆盖率通过后才创建 PR。

---

## 文件结构

新增和调整后的核心结构如下：

```text
agents/stargazer/
├── plugins/base_utils.py                         # 修复合法假值标签丢失
└── tests/collection_contract/
    ├── conftest.py                               # 读取共享矩阵/fixture
    ├── semantics.py                              # Prometheus 与 Line Protocol 语义解析
    ├── test_lane_a_contract.py                   # 全对象 Lane A 参数化契约
    ├── test_prometheus_scalar_labels.py          # 0/False/空串回归
    └── test_publish_boundary.py                  # subject、行数、重试契约

server/apps/cmdb/tests/e2e/
├── contract_manifest.py                         # 三元组展开与清单比较
├── contract_manifest.json                       # 显式生产/非生产验证清单
├── contract_loader.py                           # 证据包及 schema 装载
├── graph_intent_spy.py                          # 可观测图库写入替身
├── pipeline.py                                  # 删除伪 VM 的覆盖职责，仅保留兼容 helper
├── test_collection_contract_manifest.py         # 覆盖真相源
├── test_contract_evidence.py                    # provenance/schema/敏感信息
├── test_lane_b_contract.py                      # 全对象 VM→CMDB 参数化契约
├── test_graph_write_intent.py                    # Management 写入意图
├── test_cloud_source_contract.py                # 云 SDK/API 边界
├── fixtures/{case_id}/
│   ├── 00_provenance.json
│   ├── 01_source_raw.json
│   ├── 02_prometheus.txt
│   ├── 03_line_protocol.txt
│   ├── 04_vm_response.json
│   └── 05_expected_cmdb.json
└── schemas/{case_id}/
    ├── source.schema.json
    ├── vm.schema.json
    └── cmdb.schema.json

server/apps/cmdb/tests/smoke/collection_chain/
├── compose.yaml                                  # 隔离 NATS/Telegraf/VM/FalkorDB
├── telegraf.conf                                 # NATS consumer → VM import
├── conftest.py                                   # 门禁、健康检查、账本、清理
├── runner.py                                     # 发布、轮询、CMDB 运行、图回读
├── cases.py                                      # 八类代表对象
├── test_full_chain.py                            # 闭环参数化烟测
└── README.md                                     # 本地/CI 命令与故障证据
```

现有 fixture 采用迁移脚本做机械重命名和补充，迁移结果必须逐对象审阅；脚本本身不保留为生产依赖。

---

### Task 1：建立三元组覆盖真相源

**Files:**

- Create: `server/apps/cmdb/tests/e2e/contract_manifest.py`
- Create: `server/apps/cmdb/tests/e2e/contract_manifest.json`
- Create: `server/apps/cmdb/tests/e2e/test_collection_contract_manifest.py`
- Modify: `server/apps/cmdb/collection/plugins/registry.py`

**Step 1: 写 RED 测试，要求注册表展开全部产出模型**

```python
def test_生产插件三元组与显式清单双向一致():
    actual = set(expand_production_contracts(CollectionPluginRegistry.get_registry_snapshot()))
    declared = set(load_manifest().production_contracts)
    assert actual == declared


def test_父插件必须展开所有产出模型():
    contracts = expand_plugin_contract(FakeCloudPlugin)
    assert contracts == {
        ("cloud", "qcloud", "qcloud_cvm"),
        ("cloud", "qcloud", "qcloud_vpc"),
    }
```

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/e2e/test_collection_contract_manifest.py
```

Expected: FAIL，提示尚无 `expand_production_contracts`，或父插件只登记 `supported_model_id`。

**Step 2: 实现确定性的产出模型展开**

```python
def emitted_model_ids(plugin_cls: type) -> tuple[str, ...]:
    names = {plugin_cls.supported_model_id}
    for attr in ("field_mapping", "field_mappings", "related_field_mappings"):
        value = getattr(plugin_cls, attr, None)
        if isinstance(value, dict):
            names.update(str(key) for key in value)
    for metric in getattr(plugin_cls, "metric_names", ()) or ():
        model_id = metric.removesuffix("_info_gauge")
        if model_id:
            names.add(model_id)
    return tuple(sorted(names))
```

注册表快照补充 `emitted_model_ids`，测试辅助层再组合成三元组；生产/企业优先级仍沿用现有注册逻辑。

**Step 3: 建立显式清单并区分生产与非生产**

`contract_manifest.json` 每项固定包含：

```json
{
  "task_type": "cloud",
  "supported_model_id": "qcloud",
  "emitted_model_id": "qcloud_cvm",
  "case_id": "qcloud_cvm",
  "lane_a": true,
  "lane_b": true
}
```

归档、许可证阻塞、占位型对象放入 `non_production_contracts`，不得计入生产覆盖率。

**Step 4: 运行 GREEN 与现有注册表回归**

Run 上述命令，并追加：

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_new_collect_objects_registry.py
```

Expected: PASS；差异输出按 missing-in-manifest / stale-in-manifest 分组。

**Step 5: Commit**

```bash
git add server/apps/cmdb/collection/plugins/registry.py server/apps/cmdb/tests/e2e/contract_manifest.py server/apps/cmdb/tests/e2e/contract_manifest.json server/apps/cmdb/tests/e2e/test_collection_contract_manifest.py
git commit -m "test(cmdb): 建立采集对象三元组覆盖清单"
```

---

### Task 2：统一证据包、schema 与敏感信息门禁

**Files:**

- Create: `server/apps/cmdb/tests/e2e/contract_loader.py`
- Create: `server/apps/cmdb/tests/e2e/test_contract_evidence.py`
- Modify: `server/apps/cmdb/tests/e2e/conftest.py`
- Rename/Modify: `server/apps/cmdb/tests/e2e/fixtures/**`
- Rename/Modify: `server/apps/cmdb/tests/e2e/schemas/**`

**Step 1: 写 RED 测试，缺任一制品即失败**

```python
@pytest.mark.parametrize("case", production_cases(), ids=lambda c: c.case_id)
def test_每个生产对象证据包完整(case):
    evidence = load_evidence(case.case_id)
    assert evidence.missing_files == []
    evidence.validate_schemas()
    evidence.validate_provenance()
    evidence.assert_no_secrets()
```

Expected: FAIL，并一次性列出当前全部缺 provenance、source、Prometheus、Line Protocol、VM、Golden、schema 的对象，禁止首错即停。

**Step 2: 实现严格 loader**

```python
REQUIRED = (
    "00_provenance.json", "01_source_raw.json", "02_prometheus.txt",
    "03_line_protocol.txt", "04_vm_response.json", "05_expected_cmdb.json",
)

def load_evidence(case_id: str) -> Evidence:
    fixture_dir = FIXTURE_ROOT / case_id
    schema_dir = SCHEMA_ROOT / case_id
    return Evidence.from_paths(fixture_dir, schema_dir, required=REQUIRED)
```

Provenance 必填字段为 `source_type`、`vendor`、`service`、`api_operation`、`api_or_sdk_version`、`documentation_url`、`read_at`、`sanitization`；真实环境来源可将 API 字段设为明确的 `not_applicable`，不得缺键。

**Step 3: 迁移既有有效 fixture，补齐统一 schema**

- 保留原始值语义，不从 expected 生成 raw。
- 对每个对象加入 `0`、`False`、空字符串、Unicode、引号、反斜杠、换行中适用的边界值。
- 扫描高风险键和值：`secret`、`token`、`password`、`api_key`、私网域名和未脱敏主机标识。

**Step 4: GREEN**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/e2e/test_contract_evidence.py
```

Expected: 所有生产 case PASS；历史非生产 case 只校验其声明的归档状态。

**Step 5: Commit**

```bash
git add server/apps/cmdb/tests/e2e
git commit -m "test(cmdb): 统一采集链路证据包契约"
```

---

### Task 3：Lane A 语义解析与真实发布边界

**Files:**

- Create: `agents/stargazer/tests/collection_contract/conftest.py`
- Create: `agents/stargazer/tests/collection_contract/semantics.py`
- Create: `agents/stargazer/tests/collection_contract/test_lane_a_contract.py`
- Create: `agents/stargazer/tests/collection_contract/test_publish_boundary.py`
- Modify: `server/apps/cmdb/tests/e2e/pipeline.py`

**Step 1: 写 RED 测试，证明不再伪造 VM 响应**

```python
@pytest.mark.parametrize("case", lane_a_cases(), ids=lambda c: c.case_id)
def test_源数据经过真实_prometheus_与_line_protocol(case, evidence):
    payload = case.run_real_adapter(evidence.source_raw)
    prometheus_text = convert_to_prometheus_format(payload)
    assert parse_prometheus(prometheus_text) == parse_prometheus(evidence.prometheus_text)

    lines = convert_prometheus_to_influx(prometheus_text, case.publish_params)
    assert parse_line_protocol(lines) == parse_line_protocol(evidence.line_protocol_text)
```

Expected: FAIL；现有 `step2_push_to_vm` 只构造 dict，且没有真实格式转换覆盖。

**Step 2: 实现语义比较器**

- Prometheus 比较 `(metric_name, sorted(labels), numeric_value, timestamp_ms)`。
- Line Protocol 比较 `(measurement, sorted(tags), typed_fields, timestamp_ns)`。
- 时间戳按精度与传播关系断言；记录顺序不参与比较。
- NaN/Inf、非法时间戳、坏行必须产生显式异常或明确丢弃计数。

**Step 3: 捕获真实 NATS 发布调用**

```python
async def test_发布边界包含正确_subject_与全部行(fake_ctx):
    count = await publish_metrics_to_nats(fake_ctx, metrics, params, task_id=1001)
    assert count == len(expected_lines)
    expected_subject = ".".join(
        (NATS_METRIC_TOPIC, params["monitor_type"], params["plugin_name"], params["model_id"])
    )
    assert fake_ctx.published_subject == expected_subject
    assert parse_line_protocol(fake_ctx.payload) == parse_line_protocol(expected_lines)
```

覆盖零投递、部分投递、发布失败重试和已确认投递不重复发送。

**Step 4: 收窄旧 helper 职责**

`step2_push_to_vm` 更名或标记为仅构造 Lane B fixture 的 legacy helper；任何 Lane A 测试不得调用它。新增测试静态检查 Lane A 文件中不存在该调用。

**Step 5: GREEN**

Run:

```bash
cd agents/stargazer && uv run pytest -q tests/collection_contract/test_lane_a_contract.py tests/collection_contract/test_publish_boundary.py
```

Expected: 语义解析和发布边界测试 PASS；尚未补齐对象在 Task 5 的矩阵测试中保持 RED，不允许 skip。

**Step 6: Commit**

```bash
git add agents/stargazer/tests/collection_contract server/apps/cmdb/tests/e2e/pipeline.py
git commit -m "test(stargazer): 接入真实指标转换发布契约"
```

---

### Task 4：修复 Prometheus 合法假值标签丢失

**Files:**

- Create: `agents/stargazer/tests/collection_contract/test_prometheus_scalar_labels.py`
- Modify: `agents/stargazer/plugins/base_utils.py`

**Step 1: 写并运行 RED**

```python
def test_合法标量假值不会被静默丢弃():
    text = convert_to_prometheus_format({
        "host": [{"model_id": "host", "zero": 0, "disabled": False, "empty": "", "missing": None}]
    })
    labels = next(iter(parse_prometheus(text))).labels
    assert labels["zero"] == "0"
    assert labels["disabled"] == "False"
    assert labels["empty"] == ""
    assert "missing" not in labels
```

Run:

```bash
cd agents/stargazer && uv run pytest -q tests/collection_contract/test_prometheus_scalar_labels.py
```

Expected: FAIL；`if v` 过滤掉 `0`、`False`、空字符串。

**Step 2: 最小生产修复**

```python
if v is not None and not isinstance(v, (list, dict)):
    labels[k] = str(v)
```

保持 list/dict 的既有处理和敏感字段过滤不变。

**Step 3: GREEN 与同类回归**

Run Task 3 全部测试，并运行：

```bash
cd agents/stargazer && uv run pytest -q tests/test_collect_multicred.py
```

Expected: PASS。

**Step 4: Commit**

```bash
git add agents/stargazer/plugins/base_utils.py agents/stargazer/tests/collection_contract/test_prometheus_scalar_labels.py
git commit -m "fix(stargazer): 保留指标标签合法假值"
```

---

### Task 5：补齐全部生产对象 Lane A 与云 API 边界

**Files:**

- Modify: `agents/stargazer/tests/collection_contract/conftest.py`
- Modify: `agents/stargazer/tests/collection_contract/test_lane_a_contract.py`
- Create: `server/apps/cmdb/tests/e2e/test_cloud_source_contract.py`
- Modify: `server/apps/cmdb/tests/e2e/fixtures/**`
- Modify: `server/apps/cmdb/tests/e2e/schemas/**`

**Step 1: 写 RED 覆盖审计**

```python
def test_lane_a覆盖全部生产三元组():
    assert covered_lane_a_contracts() == production_contracts()
```

Expected: FAIL，并列出未绑定真实 Stargazer adapter 或缺 Lane A Golden 的三元组。

**Step 2: 按适配器族补齐真实环境样本**

依次处理 Host、DB、Protocol、Middleware、VMware、K8s、Network；同一父插件共享 raw 时，测试必须证明一次运行实际产出清单中全部 `emitted_model_id`。

每一族执行：添加一个最小 case → 运行 RED → 补 fixture/适配器绑定 → GREEN → 再加入下一个 case。不得一次生成全部 expected 后只跑一次。

**Step 3: 按官方文档补齐云样本**

对清单中的每个云 API 操作冻结成功单页、分页、空结果、缺可选字段、文档化错误五类输入；Mock 固定在 SDK client 方法：

```python
client.describe_instances.side_effect = [page_1, page_2]
result = adapter.collect(client=client)
assert result == expected_plugin_raw
assert client.describe_instances.call_count == 2
```

`00_provenance.json` 中 URL、API/SDK 版本、读取日期必须与测试参数一致。自动测试使用 socket 禁网 fixture，任何外联直接失败。

**Step 4: GREEN**

Run:

```bash
cd agents/stargazer && uv run pytest -q tests/collection_contract
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/e2e/test_cloud_source_contract.py apps/cmdb/tests/e2e/test_collection_contract_manifest.py apps/cmdb/tests/e2e/test_contract_evidence.py
```

Expected: Lane A 覆盖集合与生产三元组集合完全相等。

**Step 5: Commit**

```bash
git add agents/stargazer/tests/collection_contract server/apps/cmdb/tests/e2e/fixtures server/apps/cmdb/tests/e2e/schemas server/apps/cmdb/tests/e2e/test_cloud_source_contract.py
git commit -m "test(collection): 补齐全部对象写入链路契约"
```

---

### Task 6：Lane B 真实 VM 查询与字段清洗契约

**Files:**

- Create: `server/apps/cmdb/tests/e2e/test_vm_query_contract.py`
- Create: `server/apps/cmdb/tests/e2e/test_lane_b_contract.py`
- Modify: `server/apps/cmdb/tests/e2e/pipeline.py`
- Modify: `server/apps/cmdb/tests/e2e/conftest.py`

**Step 1: 写 VM 查询 RED 测试**

```python
def test_vm查询使用_last_over_time_并传播超时(requests_mock):
    requests_mock.post(VM_URL, json={"status": "success", "data": {"result": []}})
    Collection().query('mysql_info_gauge{instance_id="cmdb_1001"}', timeout=7)
    request = requests_mock.last_request
    assert request.urlencoded_form["query"] == ['last_over_time((mysql_info_gauge{instance_id="cmdb_1001"})[1h:])']
    assert request.timeout == 7
```

覆盖连接异常/5xx 退避重试和 4xx 不重试。

**Step 2: 写全对象 Lane B RED**

```python
@pytest.mark.parametrize("case", lane_b_cases(), ids=lambda c: c.contract_id)
def test_vm响应经过真实插件得到独立_golden(case, evidence, monkeypatch):
    actual = run_real_cmdb_pipeline(case, evidence.vm_response, monkeypatch)
    assert normalize_runtime_fields(actual) == evidence.expected_cmdb
```

Expected: 当前 helper 使用手写 alias/runner map、Host 简化 mapping，无法满足注册表三元组和真实 plugin 要求。

**Step 3: 用注册表实例化真实 plugin/runner**

- 从 `task_type + supported_model_id` 获取生产 plugin，不再按文件名猜类。
- VM 只在 HTTP 边界返回 `04_vm_response.json`；`prom_sql`、`format_data`、`format_metrics`、绑定 mapping 均运行生产代码。
- 每个 `emitted_model_id` 分别与其 `05_expected_cmdb.json` 比较。
- 显式校验 `collect_status`、新鲜度、顶层 label/`metric.result` JSON 两种形态、时间/布尔/单位/枚举/`inst_name`/association。

**Step 4: GREEN**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/e2e/test_vm_query_contract.py apps/cmdb/tests/e2e/test_lane_b_contract.py
```

Expected: 全部生产三元组 Lane B PASS；新增未映射可选原字段只进入 drift，不改变 Golden。

**Step 5: Commit**

```bash
git add server/apps/cmdb/tests/e2e/pipeline.py server/apps/cmdb/tests/e2e/conftest.py server/apps/cmdb/tests/e2e/test_vm_query_contract.py server/apps/cmdb/tests/e2e/test_lane_b_contract.py
git commit -m "test(cmdb): 接入真实VM查询与字段清洗契约"
```

---

### Task 7：模型反射、drift 与图库写入意图

**Files:**

- Modify: `server/apps/cmdb/tests/e2e/utils/model_reflection.py`
- Modify: `server/apps/cmdb/tests/e2e/utils/drift_report.py`
- Create: `server/apps/cmdb/tests/e2e/graph_intent_spy.py`
- Create: `server/apps/cmdb/tests/e2e/test_graph_write_intent.py`
- Modify: `server/apps/cmdb/tests/e2e/test_lane_b_contract.py`

**Step 1: 写 RED 测试**

```python
def test_模型反射与独立Golden必须同时通过(case):
    assert validate_model_constraints(case.actual, case.model_schema) == []
    assert compare_golden(case.actual, case.expected) == []


def test_图库意图包含实体关联和采集元数据(case, graph_spy):
    run_metrics_cannula(case, graph_client=graph_spy)
    assert graph_spy.intent == case.expected["graph_intent"]
```

Expected: FAIL；现有 fake graph 仅让调用通过，没有统一精确意图 Golden。

**Step 2: 实现模型反射和 drift 分类**

- 校验必填、类型、枚举和允许字段；排除 `_id` 与不稳定运行时字段。
- `mapped_contract_errors` 非空即失败。
- `optional_unmapped_vendor_fields` 只写结构化 JSON 报告。
- 报告键固定为 contract_id、stage、field_path、source_field、expected、actual、provenance、plugin、runner。

**Step 3: 实现 GraphIntentSpy**

Spy 记录 `query_entity`、`create_entity`、`set_entity_properties`、`detach_delete_entity`、`create_edge`；运行真实 `MetricsCannula` 与 `Management`，只替换 FalkorDB I/O 边界。

**Step 4: GREEN**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/e2e/test_lane_b_contract.py apps/cmdb/tests/e2e/test_graph_write_intent.py apps/cmdb/tests/test_collect_management_svc.py
```

Expected: PASS；报告中生产契约错误为零。

**Step 5: Commit**

```bash
git add server/apps/cmdb/tests/e2e
git commit -m "test(cmdb): 校验模型约束与图库写入意图"
```

---

### Task 8：隔离烟测基础设施与安全账本

**Files:**

- Create: `server/apps/cmdb/tests/smoke/collection_chain/compose.yaml`
- Create: `server/apps/cmdb/tests/smoke/collection_chain/telegraf.conf`
- Create: `server/apps/cmdb/tests/smoke/collection_chain/conftest.py`
- Create: `server/apps/cmdb/tests/smoke/collection_chain/runner.py`
- Create: `server/apps/cmdb/tests/smoke/collection_chain/test_smoke_safety.py`
- Create: `server/apps/cmdb/tests/smoke/collection_chain/README.md`

**Step 1: 写安全门禁 RED 测试**

```python
def test_未显式开启时拒绝启动写入烟测(monkeypatch):
    monkeypatch.delenv("CMDB_COLLECTION_SMOKE", raising=False)
    with pytest.raises(SmokeSafetyError):
        SmokeEnvironment.from_env()


def test_外部地址与无归属资源均拒绝删除():
    env = SmokeEnvironment.from_values(vm_host="https://prod.example.com")
    with pytest.raises(SmokeSafetyError):
        env.validate()
    assert CleanupLedger("run-a").may_delete({"run_id": "run-b"}) is False
```

Expected: FAIL，基础设施尚不存在。

**Step 2: 添加最小 Compose 栈**

- 固定兼容版本镜像；容器名、网络、volume 使用 Compose project + `run_id` 隔离。
- NATS 仅开放本机随机端口；Telegraf `inputs.nats_consumer` 接收 Stargazer Line Protocol，`outputs.http` 写入 VM import API。
- VM 与 FalkorDB 提供条件健康检查；不使用固定长 sleep。

**Step 3: 实现 runner 安全边界**

```python
def wait_until(predicate, *, timeout_s: float, interval_s: float = 0.25):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval_s)
    raise TimeoutError("等待测试基础设施就绪超时")
```

Runner 生成唯一 run_id/task_id/subject/instance，限制消息数、实例数、单请求与总时长；`finally` 中执行账本清理并单独报告原始错误与清理错误。

**Step 4: GREEN**

Run:

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/smoke/collection_chain/test_smoke_safety.py
```

Expected: PASS，不启动任何容器。

**Step 5: Commit**

```bash
git add server/apps/cmdb/tests/smoke/collection_chain
git commit -m "test(cmdb): 搭建隔离采集链路烟测环境"
```

---

### Task 9：八类真实基础设施闭环烟测

**Files:**

- Create: `server/apps/cmdb/tests/smoke/collection_chain/cases.py`
- Create: `server/apps/cmdb/tests/smoke/collection_chain/test_full_chain.py`
- Modify: `server/apps/cmdb/tests/smoke/collection_chain/runner.py`
- Modify: `server/apps/cmdb/tests/smoke/collection_chain/README.md`

**Step 1: 写八类 RED 测试**

```python
SMOKE_CASES = ("host", "mysql", "influxdb", "nginx", "qcloud", "vmware", "k8s", "network")

@pytest.mark.parametrize("case_id", SMOKE_CASES)
def test_真实基础设施闭环(case_id, smoke_environment):
    result = run_full_chain(case_id, smoke_environment)
    assert result.vm_semantics == result.expected_vm_semantics
    assert result.graph_entities == result.expected_graph_entities
    assert result.graph_associations == result.expected_graph_associations
    assert result.cleanup_residuals == []
```

Expected: 首次 FAIL 在缺少真实发布/查询/图回读连接，不能退回 fixture 替身。

**Step 2: 实现闭环**

每个 case 执行：真实 Stargazer adapter/转换 → `publish_metrics_to_nats` → 轮询 VM 的 run_id 数据 → `Collection.query`/真实 runner/plugin → 真实 GraphClient 写入 → FalkorDB 回读实体和关联 → 与独立 Golden 比较。

**Step 3: 实现精准清理与证据保留**

- 删除图实体/关联前验证 `run_id`。
- 删除 VM series 只使用本次 run_id matcher，并轮询残留为零。
- 无论成功失败都清理；失败工件包含脱敏 NATS 摘要、VM 响应、CMDB 结果、图回读、清理审计，限制总大小。

**Step 4: 逐类 GREEN，最后全量 GREEN**

Run 单个 case：

```bash
cd server && CMDB_COLLECTION_SMOKE=1 MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/smoke/collection_chain/test_full_chain.py -k mysql
```

然后运行八类：

```bash
cd server && CMDB_COLLECTION_SMOKE=1 MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/smoke/collection_chain/test_full_chain.py
```

Expected: 8 PASS；成功与失败路径结束后 VM/FalkorDB 残留均为零。

**Step 5: Commit**

```bash
git add server/apps/cmdb/tests/smoke/collection_chain
git commit -m "test(cmdb): 覆盖八类真实采集闭环烟测"
```

---

### Task 10：缺陷收敛、全量验证与 PR 前报告

**Files:**

- Create: `docs/testing/cmdb-collection-chain-validation.md`
- Create: `server/apps/cmdb/tests/e2e/validation_report.py`
- Modify: 仅限前述测试稳定揭示的生产文件，每个根因单独提交

**Step 1: 处理所有剩余 RED**

对每个失败严格执行：记录组件边界证据 → 单一根因假设 → 最小 RED → 最小生产修复 → 定向 GREEN → 同族回归。连续三次失败停止打补丁并回到设计讨论。禁止用 skip/xfail 或放宽 Golden 收口。

每个缺陷必须只暂存已确认的生产文件及其定向回归测试，提交信息使用
`fix(collection): 修复……` 的中文根因摘要；不得使用 `git add server` 扩大提交范围。

**Step 2: 生成确定性验证报告**

报告包含：生产三元组总数、Lane A/B 通过数、缺失证据数、mapped contract errors、optional drift、八类 smoke 结果、清理残留、fixture provenance 摘要。测试断言生产覆盖率必须为 100%。

**Step 3: 运行 Stargazer 门禁**

```bash
cd agents/stargazer && uv run pytest -q tests/collection_contract
cd agents/stargazer && make lint
```

Expected: PASS，无未解释 warning。

**Step 4: 运行 CMDB 定向与全量门禁**

```bash
cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/e2e apps/cmdb/tests/test_collect_management_svc.py apps/cmdb/tests/test_new_collect_objects_registry.py apps/cmdb/tests/test_new_collect_objects_formatters.py
cd server && make test
```

Expected: PASS；触及代码覆盖率不低于 75%。

**Step 5: 再跑完整烟测并确认零残留**

```bash
cd server && CMDB_COLLECTION_SMOKE=1 MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/smoke/collection_chain/test_full_chain.py
```

Expected: 8 PASS，VM/FalkorDB residuals=0。

**Step 6: 文档与报告提交**

```bash
git add docs/testing/cmdb-collection-chain-validation.md server/apps/cmdb/tests/e2e/validation_report.py
git commit -m "docs(cmdb): 记录采集全链路验证结果"
```

**Step 7: PR 前审查**

- 检查 `git status --short`，排除 `.pnpm-store/`、`.superpowers/` 和其他用户变更。
- 使用 `requesting-code-review` 审查需求覆盖、测试有效性、安全清理和最小 diff。
- 使用 `verification-before-completion` 重新读取最后一次命令输出；不得引用历史运行冒充当前通过。
- 仅当所有验收项满足后，按用户要求创建一个完整 PR；不创建中间 PR。

---

## 计划自检

- 设计中的两段生产链路分别由 Task 3–5 和 Task 6–7 覆盖，真实传输由 Task 8–9 覆盖。
- 覆盖单位为三元组，并从父插件全部产出模型展开；不存在“父对象通过即代表子模型通过”。
- 真实环境与云文档 fixture 都从源边界开始，Golden 与生产 mapping 独立。
- `0`、`False`、空字符串、时间、单位、枚举、实例名、关联、敏感信息均有明确断言。
- NATS、Telegraf、VM、FalkorDB 的真实兼容性仅在显式开启的隔离 smoke 中验证，且有资源边界与零残留门禁。
- 每个已知生产缺陷有独立 RED/修复/GREEN/提交；未知缺陷按同一流程收敛，不预设修改范围。
- 最终 PR 条件与已批准设计一致：全部对象、八类烟测、门禁和覆盖率完成后才创建。
