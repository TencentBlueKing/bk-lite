# CMDB 配置采集全链路 e2e — A/B 端字段对齐检查

> **状态**：设计草案 v5(2026-07-13)
> **作者**：Mavis(在 windyzhao 协同下)
> **基线**：`feature_windyzhao` @ `aa7040c6a`(v3+v4 收尾)
> **姊妹文档**：
> - [`2026-07-10-cmdb-collect-archive-document.md`](../plans/2026-07-10-cmdb-collect-archive-document.md)(catalog 56 状态表)
> - [`2026-07-10-cmdb-collect-v3-v4-pr-description.md`](../plans/2026-07-10-cmdb-collect-v3-v4-pr-description.md)(v3+v4 工作收尾)
> - [`2026-07-06-cmdb-collect-v3-roadmap.md`](../plans/2026-07-06-cmdb-collect-v3-roadmap.md)(v3 路线图,云采集明确排除)

---

## 0. 文档使用约定

1. **「测试结果」字段**:每个对象完成 e2e 后,对应章节的「测试结果」字段由执行者**手动回填**(pytest 行号 + 验证状态)
2. **「能做 / 不能做 / 不做」三档标识**:
   - 🟢 **能做**:对象在 fixture 适配范围 + 镜像/API 文档可达 + 有可用 plugin
   - 🟡 **能做(降级方案)**:原生方案不可行,但有可接受的降级路径(读 API 文档虚构 JSON / placeholder 模式)
   - 🔴 **不能做**:受 license / 平台 / 集群硬约束
   - ⚪ **不做(明确不纳入)**:超出本路线图范围
3. **执行约定**(沿用 v3+v4):
   - 不修改 production 代码(`server/apps/cmdb/(collection|views|serializers|services|models|urls)`、`agents/stargazer/(plugins/inputs|tasks/collectors|core)`)
   - 所有改动是新增(无 modify 现有功能)
   - 不引入新依赖
   - 落盘 JSON schema 固定(对齐 4 段流水线边界)
   - 敏感字段掩码(若需要)
   - 完成后不自动 push(由用户本人提交)

---

## 1. 目标与边界

### 1.1 目标

复用 v3+v4 已搭建的 e2e 框架(`pipeline.py:185 run_full_pipeline_generic` + `conftest.py::load_runner_plugin_for_model_id` + `00_common_contract.schema.json` 公共契约),在 catalog 56 model_id 全部对象上跑通端到端测试,并在**数据流两端**加字段对齐检查:

- **A 端(stargazer 端)** — 采集数据经 `convert_to_prometheus`/`parse_metrics_to_prometheus`/`wmi_results_to_prometheus` 修复 + 格式化后,03 VM PromQL 响应字段跟 CMDB model 定义对不齐的检查
- **B 端(CMDB 端)** — CMDB 从 VM 拉数据后,经 plugin `field_mappings` 格式化,04 实例字段跟 CMDB model 定义对不齐的检查

**不**做 plugin 内部 tuple 字段清洗项(类型转换 / datetime format / set_instance_inst_name / set_asso_instances 等)的独立断言层 —— 用户已明确否决。

### 1.2 范围

#### 1.2.1 范围对象分类

| 范围 | 数量 | 现状 | 本期处理 |
|---|---|---|---|
| 真实落盘(已 e2e 100% 覆盖) | 33(24 passed + 9 placeholder) | v3+v4 已跑通 3 层验证 | **不动** |
| 已有 fixture 但未真实化 | 6(aliyun / k8s / vmware / host / network / config_file) | test_*.py 已写,fixture 简化(aliyun 17 行 1 实例)/不完整(k8s 缺 01_raw) | 真实化 + A/B 端检查 |
| 归档 license / amd64 / 集群 | 17(apusic / bes / hdfs / informix / ihs / inforsuite_as / iris / couchbase / oceanbase / oscar / sap_hana / storm / sybase / tonggtp / tonglinkq / tongrds / tuxedo / weblogic / websphere / mycat / domestic_linux / yarn,22 个减 1 个 enterprise 重复 + 减 1 个 mssql 主动删除) | 无 plugin / plugin stub | placeholder 模式 + license_status 标注 + A/B 端公共契约 |

**总范围**:catalog 56 model_id 全部对象(33 沿用 + 23 补做)。

#### 1.2.2 范围外

- K8s / VMware vCenter / 云采集(K8s 的部分功能在 6 套真实化里做,但不展开 K8s 集群复杂度)—— 用户在 v3 已明确排除,本期仅真实化已有 fixture
- Network 设备采集(走 SNMP,跟 prometheus 协议无关)—— 本期仅真实化已有 fixture
- Storage(community storage + enterprise storage_device)—— fixture 语义不匹配
- Host(config_file / physcial_server)—— 本期真实化已有 fixture,集群形态略过

---

## 2. 现状回顾(v3+v4 已交付)

### 2.1 已落地的能力

- ✅ e2e 4 段流水线框架:`pipeline.py:185 run_full_pipeline_generic`
  - step1_stargazer_normalize_generic(raw_items) → Stargazer 标准化 payload
  - step2_push_to_vm(stargazer_payload) → VictoriaMetrics PromQL 响应
  - step3_cmdb_consume_generic(runner_cls, plugin_cls, model_id) → CMDB 实例字典
  - step4_collect_base 关联挂载(自动)
- ✅ 公共契约:`00_common_contract.schema.json` 覆盖 01 阶段 5 种 oneOf 形态(A/B/C/placeholder_object/placeholder_array)
- ✅ 工厂函数:`conftest.py::load_runner_plugin_for_model_id` 返回 `(runner_cls, plugin_cls, extra_payload_keys)` 三元组
- ✅ 33 真实落盘对象 e2e 100% 触达,113 passed + 6 skipped + 0 failed
- ✅ placeholder 模式约定:fixture 用 `_placeholder_reason` 标记,license 解锁后增量升级
- ✅ 6 套已有 fixture(test_aliyun_pipeline.py / test_k8s_pipeline.py / test_vmware_pipeline.py / host / network / config_file)框架代码就绪

### 2.2 v3+v4 留下的关键 Gap

| Gap | 描述 | 本期处理 |
|---|---|---|
| A 端缺对齐检查 | 03 VM PromQL 响应字段(`__name__` / `instance_id` / `result` JSON / 业务 label)跟 `cmdb.models.<Model>` 字段定义对不齐,无检查 | **新增** `test_stargazer_prometheus_alignment.py`(A 端) |
| B 端缺对齐检查 | 04 实例字段跟 model 定义对不齐,无全量检查(只有 expected_instance_subset 子集) | **新增** `test_cmdb_vm_format_alignment.py`(B 端) |
| 6 套 fixture 不够真实 | aliyun 17 行 1 实例,无法触发 plugin 里 `(int, x)` / `(convert_datetime_format, x)` / `set_instance_inst_name` / `set_asso_instances` 复杂清洗路径 | P0 真实化 |
| 17 个 archived 无 e2e | license / amd64 / 集群复杂对象无 e2e | P2 placeholder 套壳 |

### 2.3 关键约束(继承基线)

- aliyun / hwcloud / qcloud plugin 字段清洗复杂:`(int, "vcpus")` / `(int, "memory")` / `(convert_datetime_format, "create_time")` / `set_instance_inst_name(resource_name + resource_id)` / `set_asso_instances` 关联对象拼装
- K8s 流水线走不了 generic 驱动:`CollectK8sMetrics` 不继承 `CollectBase`,业务逻辑硬编码(namespace/workload/pod/node 4 分组),需走 minimal path
- stargazer 端用 prometheus 修复:`tasks/utils/metrics_helper.py` + `tasks/collectors/vmware_collector.py` 等用 `convert_to_prometheus` / `parse_metrics_to_prometheus` / `wmi_results_to_prometheus` 转换采集 dict 为 prometheus 格式
- 23 archived 对象封档原则:不再主动重试,placeholder 模式 + license_status 标注,等 license 解锁增量升级

---

## 3. 设计方案

### 3.1 数据流 + A/B 端检查点

```
┌─────────────────────────────────────────────────────────────────────┐
│  [1] Stargazer 采集脚本/SDK 原始输出          (fixture 01)          │
│        ↓ step1_stargazer_normalize                                   │
│  [2] Stargazer 标准化 payload                (fixture 02, 本期新增) │
│        ↓ step2_push_to_vm                                            │
│  [3] VictoriaMetrics PromQL 响应              (fixture 03)           │
│        ↓ step3_cmdb_consume                                          │
│  [4] CMDB 实例字典(落库前)                   (fixture 04)           │
└─────────────────────────────────────────────────────────────────────┘

  ┌────────────────────────┐    ┌────────────────────────┐
  │ A 端对齐检查(本期新增) │    │ B 端对齐检查(本期新增) │
  │ ──────────────────────  │    │ ──────────────────────  │
  │ 03 字段 vs Model 定义  │    │ 04 字段 vs Model 定义  │
  │ - __name__ 后缀        │    │ - 字段名 ⊆ Model.field │
  │ - instance_id label   │    │ - 字段类型匹配         │
  │ - 业务 label 集合     │    │ - 必填字段非空         │
  │ - result JSON 编码     │    │ - choice 枚举合法      │
  └────────────────────────┘    └────────────────────────┘
```

### 3.2 A 端检查(stargazer 端)语义

`test_stargazer_prometheus_alignment.py` 核心:

| 检查项 | 来源 | 期望 | 失败信号 |
|---|---|---|---|
| `metric.__name__` 后缀 | `step2_push_to_vm` 产物 | `_<model_id>_info_gauge`(middleware/db/protocol)或 `prometheus_kube_*`(K8s) | 后缀错(跟 plugin.metric_names 对不齐) |
| `metric.instance_id` label | `step2_push_to_vm` 产物 | `cmdb_<task_id>` 格式 | 缺 instance_id label |
| `metric.collect_status` label | `step2_push_to_vm` 产物 | `success` | 状态错 |
| 业务 label 集合 | `step2_push_to_vm` 产物(middleware 走 result JSON) | ⊇ CMDB model 字段名(必填字段全部在 label 里)| 缺业务 label(模型字段没生成) |
| `metric.value` | VM 响应格式 | `[<timestamp>, "1"]` 数组 | 格式错 |
| K8s 特殊:`__name__ ∈ prometheus_kube_*` | K8s plugin 硬编码 metric | `prometheus_kube_*` 前缀 | 缺前缀(被 K8s 流水线过滤) |

### 3.3 B 端检查(CMDB 端)语义

`test_cmdb_vm_format_alignment.py` 核心:

| 检查项 | 来源 | 期望 | 失败信号 |
|---|---|---|---|
| 实例字段名 ⊆ Model 字段定义 | `step3_cmdb_consume` 产物 | CMDB model `<Model>` 定义的字段全部出现(允许额外字段) | 漏字段(模型定义没接上) |
| 字段类型匹配 | `step3_cmdb_consume` 产物 | Model `field_type` 定义(int / str / choice / etc) | 类型错(`vcpus` 应该是 int 但成了 str) |
| 必填字段非空 | `step3_cmdb_consume` 产物 | Model `is_required` 字段全部非空 | 必填空(数据没接上) |
| `choice` 枚举合法 | `step3_cmdb_consume` 产物 | Model `choice` 字段值在白名单内 | 非法值(状态码 / 区域码漂移) |
| `inst_name` 模式 | `step3_cmdb_consume` 产物 | 跟 `inst_name_alias` 规则一致(`{ip}-{name_token}-{port}`) | inst_name 错位 |

### 3.4 不做之事(明确排除)

- ❌ plugin 内部 tuple 字段清洗项的独立断言层(用户已明确否决)
- ❌ 修改 production 代码(collection / views / serializers / services / models / urls / apps.py)
- ❌ 引入新依赖
- ❌ 自动重试 17 个 archived 对象(license 阻塞)
- ❌ 33 真实落盘对象的 e2e 代码改动

---

## 4. e2e 测试架构

### 4.1 文件结构

```
server/apps/cmdb/tests/e2e/
├── test_pipeline_factory.py                        # 现有,33 真实落盘对象不动
├── test_stargazer_prometheus_alignment.py          # NEW - A 端检查
├── test_cmdb_vm_format_alignment.py                # NEW - B 端检查
├── test_common_contract.py                         # 现有
├── test_placeholder_objects.py                     # 现有
├── test_aliyun_pipeline.py                         # 现有
├── test_k8s_pipeline.py                            # 现有
├── test_vmware_pipeline.py                         # 现有
├── test_host_pipeline.py                           # 现有
├── test_network_pipeline.py                        # 现有
├── test_config_file_pipeline.py                    # 现有
├── conftest.py                                     # 现有(扩 load_runner_plugin)
├── pipeline.py                                     # 现有
├── fixtures/                                       # 扩 6 + 17 = 23 套
│   ├── aliyun/                                     # 真实化
│   ├── k8s/                                        # 真实化(补 01_raw)
│   ├── vmware/                                     # 真实化
│   ├── host/                                       # 真实化
│   ├── network/                                    # 真实化
│   ├── config_file/                                # 真实化
│   ├── hwcloud/                                    # 新增(P1)
│   ├── qcloud/                                     # 新增(P1)
│   ├── fusioninsight/                              # 新增(P1)
│   ├── zstack/                                     # 新增(P1)
│   ├── h3c_cas/                                    # 新增(P1)
│   └── <archived_obj>/                             # 新增 17 套 placeholder
└── schemas/                                        # 扩 23 套
```

### 4.2 A 端测试文件骨架

```python
# test_stargazer_prometheus_alignment.py 草图
"""A 端对齐检查:stargazer 端 prometheus 修复格式化后,03 VM PromQL 响应字段跟 CMDB model 定义对齐。

检查项:
  - metric.__name__ 后缀合法
  - metric.instance_id / collect_status label 完整
  - 业务 label 集合 ⊇ model 必填字段
  - metric.value 格式合法
  - K8s 特殊:prometheus_kube_* 前缀
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


ALIGNMENT_COVERED_MODEL_IDS = [...]  # 6 真实化 + 7 云采集 + 17 archived


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_a_alignment_metric_name_suffix(model_id, load_fixture, runner_plugin_factory):
    """metric.__name__ 后缀必须与 plugin.metric_names 对齐。"""
    ...


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_a_alignment_instance_id_label(model_id, load_fixture, runner_plugin_factory):
    """metric.instance_id label 必须是 cmdb_<task_id> 格式。"""
    ...


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_a_alignment_business_labels(model_id, load_fixture, runner_plugin_factory):
    """业务 label 集合必须 ⊇ model 必填字段(避免漏字段)。"""
    ...
```

### 4.3 B 端测试文件骨架

```python
# test_cmdb_vm_format_alignment.py 草图
"""B 端对齐检查:CMDB 端从 VM 拉数据后,04 实例字段跟 CMDB model 定义对齐。

检查项:
  - 实例字段名 ⊆ Model 字段定义
  - 字段类型匹配 Model field_type
  - 必填字段非空
  - choice 枚举合法
  - inst_name 模式
"""
import jsonschema
import pytest

from apps.cmdb.tests.e2e import pipeline


ALIGNMENT_COVERED_MODEL_IDS = [...]  # 同 A 端


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_b_alignment_field_subset(model_id, load_fixture, runner_plugin_factory):
    """实例字段名 ⊆ Model 字段定义(允许额外字段,不能漏)。"""
    ...


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_b_alignment_field_types(model_id, load_fixture, runner_plugin_factory):
    """字段类型匹配 Model field_type(避免 vcpus 等该 int 的成了 str)。"""
    ...


@pytest.mark.parametrize("model_id", ALIGNMENT_COVERED_MODEL_IDS)
def test_b_alignment_required_nonempty(model_id, load_fixture, runner_plugin_factory):
    """Model is_required 字段全部非空。"""
    ...
```

### 4.4 公共契约扩展(扩 2 套通用 schema)

- `00_common_contract.schema.json` — 现有,01 阶段 5 种 oneOf,**不动**
- `02_stargazer_normalized.schema.json` — **新增** 02 阶段统一 schema
- `03_vm_metrics_response.schema.json` — **新增** 03 阶段通用 schema(已有 k8s/03,补通用版)
- `04_cmdb_instance.schema.json` — **新增** 04 阶段通用 schema(基于 `apps/cmdb/models` 反射生成)

> 反射生成 model 字段定义的辅助函数 `apps/cmdb/tests/e2e/utils/model_reflection.py`:
> - 加载 `cmdb.models.<Model>`,提取 `attr_list` / `field_type` / `is_required` / `choice`
> - 输出 jsonschema 子集(用于 B 端断言)

---

## 5. 范围对象分类(详细)

### 5.1 P0 真实化(6 套,0.5 人天/对象)

| 对象 | runner | 真实化重点 | 状态 |
|---|---|---|---|
| **aliyun** | AliyunCollectMetrics | 17 行 → 100+ 行,8 个 metric_name 各 1 实例,补 plugin `(int, "vcpus")` 等复杂清洗路径 | 🟢 |
| **k8s** | CollectK8sMetrics(minimal path)| 补 01_raw_collector.json(K8s 走 VM 不走 raw),补 workload / pod / node 3 分组 | 🟢 |
| **vmware** | VMCollectMetrics | 扩 vmware fixture,补 02 标准化格式 | 🟢 |
| **host** | HostCollectMetrics | 补 host 真实采集样本(cpu / mem / disk / net 多维度) | 🟢 |
| **network** | NetworkCollectMetrics | 补 network 设备样本 | 🟢 |
| **config_file** | ConfigFileCollectMetrics | 补真实配置文件样本 | 🟢 |

### 5.2 P1 云采集新增(7 套,0.5 人天/对象)

| 对象 | runner | 真实化重点 | 状态 |
|---|---|---|---|
| **hwcloud** | HwCloudCollectMetrics | 11 个子对象(hwcloud_ecs/evs/vpc/obs/subnet/eip/sg/elb/rds/dcs),读华为云 API 文档虚构 JSON | 🟡 |
| **qcloud** | QCloudCollectMetrics | 子对象(cvm/vpc/clb/cdb/redis 等),读腾讯云 API 文档 | 🟡 |
| **fusioninsight** | FusionInsightCollectMetrics | 华为大数据(HDFS/HBase/Hive/Spark),读 API 文档 | 🟡 |
| **zstack** | ZStackCollectMetrics | 私有云,读 API 文档 | 🟡 |
| **h3c_cas** | H3cCasCollectMetrics | H3C 云,读 API 文档 | 🟡 |
| **dameng_enterprise** | (复用 dameng) | 跟 33 真实落盘里的 dameng 合并 | 🟡 |
| **redis_sentinel_enterprise** | (复用 redis_sentinel) | 跟 33 真实落盘里的 redis_sentinel 合并 | 🟡 |

### 5.3 P2 Archived placeholder(17 套,0.2 人天/对象)

| 对象 | 阻塞根因 | placeholder 策略 |
|---|---|---|
| **apusic** | 东方通 rpm + license | `_placeholder_reason: "license_missing"`,plugin stub,公共契约验证 |
| **bes** | 国产中间件 license | 同上 |
| **hdfs** | Hadoop 集群复杂 | `_placeholder_reason: "cluster_complex"`,plugin stub |
| **informix** | IBM license | 同 apusic |
| **ihs** | IBM license + amd64 | 同 apusic |
| **inforsuite_as** | 中创 license | 同 apusic |
| **iris** | InterSystems license | 同 apusic |
| **couchbase** | Enterprise license | 同 apusic |
| **oceanbase** | OceanBase license | 同 apusic |
| **oscar** | 神通 license | 同 apusic |
| **sap_hana** | SAP license | 同 apusic |
| **storm** | 集群复杂 | 同 hdfs |
| **sybase** | SAP license | 同 apusic |
| **tonggtp** | 东方通 license | 同 apusic |
| **tonglinkq** | 东方通 license | 同 apusic |
| **tongrds** | 东方通 RDS license | 同 apusic |
| **tuxedo** | Oracle license | 同 apusic |
| **weblogic** | Oracle license | 同 apusic |
| **websphere** | IBM license | 同 apusic |
| **mycat** | amd64 only | `_placeholder_reason: "platform_constraint"`,plugin stub |
| **domestic_linux** | 国产 Linux iso | `_placeholder_reason: "platform_constraint"`,plugin stub |
| **yarn** | 集群复杂 | 同 hdfs |

**注**:v3+v4 archive 文档列 18 个,本期 17 个 = 18 - 1(enterprise dameng 合并到 P1)。

### 5.4 范围对象数量汇总

```
P0 真实化:6
P1 云采集:7
P2 archived:17
─────────────────
本期新工作:30
沿用(v3+v4 已 e2e):33
────────────────────
catalog 56 model_id:63 (实际 56,因部分 enterprise 跟 community 合并)
```

> 实际 catalog 56 model_id 分布,详细看 [`2026-07-10-cmdb-collect-archive-document.md`](../plans/2026-07-10-cmdb-collect-archive-document.md) §1。

---

## 6. 实施步骤 / Phase 拆分

### 6.1 Phase 时间线

| Phase | 内容 | 周期 | 验收 |
|---|---|---|---|
| **P0 基础** | A/B 端测试文件骨架;02/03 通用 schema;反射 model 工具 | 0.5 人天 | 6 真实化对象先跑通,作为模板 |
| **P0 真实化(6)** | aliyun / k8s / vmware / host / network / config_file 真实 fixture + A/B 端覆盖 | 3 人天 | 6 × A/B 端测试全过 |
| **P1 云采集新增(7)** | hwcloud / qcloud / fusioninsight / zstack / h3c_cas / dameng_enterprise / redis_sentinel_enterprise 读 API 文档虚构 JSON | 3.5 人天 | 7 × A/B 端测试全过 |
| **P2 Archived placeholder(17)** | 17 个 archived 走 placeholder + license_status + A/B 端公共契约 | 3.4 人天 | 17 × A/B 端公共契约过 |
| **收尾** | 字段漂移报告 + cross-cutting 公共契约固化 + 文档(e2e 作者指南 v2 扩展 A/B 端)| 1 人天 | 全量 30 × A/B 端 + 33 真实落盘回归 0 fail |

**总周期**:约 11.4 人天(2-3 人周)。

### 6.2 关键设计决策(本节需要用户 review)

| 决策点 | 选项 | 推荐 | 理由 |
|---|---|---|---|
| 33 真实落盘是否加 A/B 端检查 | 加 / 不加 | **不加**(用户已确认) | 不破坏现有 33 passed |
| P2 archived 的 license 标记形式 | `_placeholder_reason` / `license_status: missing` / 两者 | **两者**(沿用 v4 `_placeholder_reason` + 新增 `license_status: missing` 标准字段) | 兼容 v4 placeholder 模式,新增 license_status 标准化 |
| K8s 流水线 minimal path 是否扩 | 扩 / 不扩 | **不扩**,只真实化已有 fixture | K8s 集群复杂度超出本期范围 |
| e2e fixture 02 阶段是否新建 | 新建 / 不新建 | **不新建**,02 阶段暂用公共契约(02 阶段跟 01 形态紧耦合) | 减少 fixture 数量,降低维护成本 |
| 跑通标准 | 5 层验证 / 3 层 + 2 端 | **3 层 + 2 端对齐**(沿用现有 3 层,A/B 端独立)| 兼容 v3+v4 已有架构 |

### 6.3 前置依赖

- 无 amd64 CI runner 需求(全部是 e2e 测试代码 + fixture 改造)
- 无 production 代码改动
- 无新依赖

---

## 7. 风险评估

### 7.1 低风险 ✅

- **零 production 代码改动**(沿用 v3+v4 模式)
- 所有改动是新增 fixture / schema / test 文件
- 33 真实落盘对象 e2e 不动,不影响 113 passed
- 6 真实化有 test_*.py 框架就绪,只需扩 fixture

### 7.2 中风险 ⚠️

- **P1 云采集读 API 文档**:hwcloud 11 个子对象 / aliyun 8 个 metric_names,需要逐个虚构 JSON,工作量超预期
- **P2 archived license_status 标注**:17 个对象需要统一标注,可能漏标
- **A/B 端检查可能暴露新问题**:比如 K8s 的 prometheus_kube_* metric 跟 CMDB model 字段对不齐,发现后需修复(超出本期范围,记录到后续)
- **cmdb.models 反射**:某些动态字段(如 vcpus / memory_mb)需要 type hint 正确

### 7.3 高风险 🔴

- 无(本期所有改动都是 e2e 测试代码 + fixture)

### 7.4 缓解措施

- P1 子对象拆分:hwcloud / aliyun 先做核心对象(ecs / vpc),子对象作为下期
- A/B 端检查暴露的新问题:**不修复**,记录到"后续工作",但 e2e 测试用 `xfail` 标记,等修复后转 pass
- 反射工具:**逐步覆盖**,先覆盖 6 真实化对象需要的 model,再扩到 30 对象

---

## 8. 验证清单

### 8.1 单元 / 集成验证

- [x] `pytest server/apps/cmdb/tests/e2e/test_pipeline_factory.py` 沿用 v3+v4 113 passed
- [ ] `pytest server/apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py` 30 个新对象 A 端全过
- [ ] `pytest server/apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py` 30 个新对象 B 端全过
- [ ] `pytest server/apps/cmdb/tests/e2e/test_common_contract.py` 公共契约 30 + 33 = 63 个对象覆盖
- [ ] `pytest server/apps/cmdb/tests/e2e/test_placeholder_objects.py` 17 个 archived placeholder 全过

### 8.2 跨对象验证

- [ ] 字段漂移报告:`make e2e-drift-report`(自动生成)
- [ ] 公共契约反向校验:`test_common_contract_cover_no_orphan_model_id` 扩展到 63 个对象
- [ ] 沿用 v3+v4 `test_pipeline_factory.py` 的 3 层验证 0 fail

### 8.3 文档验证

- [ ] `docs/cmdb-e2e-author-guide.md` 扩展 v2:加 A/B 端检查章节
- [ ] `docs/superpowers/specs/2026-07-13-cmdb-collect-full-e2e-alignment-design.md`(本 spec) review 通过
- [ ] `docs/superpowers/plans/2026-MM-dd-cmdb-collect-full-e2e-alignment-execution-report.md` 各 Phase 收尾报告

---

## 9. 测试结果回填字段(本节由执行者填)

> 按"文档使用约定"§0.1,每个对象完成 e2e 后,执行者手动回填 pytest 行号 + 验证状态。

| 对象 | Phase | A 端 pytest 行号 | B 端 pytest 行号 | 验证状态 | 备注 |
|---|---|---|---|---|---|
| aliyun | P0 | TBD | TBD | TBD | TBD |
| k8s | P0 | TBD | TBD | TBD | TBD |
| ... | | | | | |

---

## 10. 一句话总结

**本期新增 A 端 + B 端两类字段对齐检查(独立 cross-cutting 测试文件),覆盖 6 真实化 + 7 云采集 + 17 archived placeholder 共 30 个新对象,catalog 56 model_id 100% e2e 触达。不动现有 33 真实落盘对象,零 production 代码改动,周期约 11.4 人天。**

---

## 11. 后续工作(本 spec 外)

- 17 archived 对象 license 解锁后,fixture 替换为真实数据,自动升级 placeholder → passed
- A/B 端检查暴露的新问题(可能在 K8s / 国产化二进制对象)→ 单独 follow-up spec
- amd64 CI runner 解锁后,18 archived 国产 binary 对象重试 fixture 真实采集
- 字段漂移检测自动化(`make e2e-drift-report`)+ dashboard
- e2e 作者指南 v2 扩展 A/B 端章节
