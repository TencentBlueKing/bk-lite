# CMDB 采集端到端流水线测试

> 模拟"采集脚本 → Stargazer → VictoriaMetrics → CMDB → FalkorDB"链路，
> 不依赖真实环境，**所有 9 大采集对象全覆盖**。

## 当前覆盖（34 个测试全过）

| 采集大类 | 代表对象 | 测试文件 | 链路特点 |
|---|---|---|---|
| host | host | `test_host_pipeline.py` | shell 脚本 + proc 子流；VM labels 平铺 |
| middleware | nginx | `test_nginx_pipeline.py` | 业务字段编码到 `metric.result` JSON |
| db | redis | `test_redis_pipeline.py` | VM labels 平铺；`inst_name = ip-{model}-port` |
| protocol | mysql | `test_mysql_pipeline.py` | 同 db 模式（runner 共用） |
| cloud | aliyun_ecs | `test_aliyun_pipeline.py` | 多 sub-model（bucket/clb/ecs/...） |
| vm | vmware_vc | `test_vmware_pipeline.py` | 多 sub-model + 关联（vc/esxi/vm/ds） |
| k8s | k8s_namespace | `test_k8s_pipeline.py` | 独立 runner，硬编码业务逻辑 |
| network | switch | `test_network_pipeline.py` | SNMP；sysobjectid 推导 device_type |
| **NATS 路径** | config_file | `test_config_file_pipeline.py` | 不走 VM；NATS handler → ConfigFileService |

总计 9 个采集对象 / **34 个测试 / 全过 / 整套跑 < 45 秒**。

## 设计原则

四个契约边界用 JSON Schema 强制：

```
[1] 采集脚本/SDK 原始输出  → schemas/<对象>/01_raw_collector.schema.json
[2] Stargazer 标准化       → schemas/<对象>/02_stargazer_payload.schema.json (host 有；其他可省)
[3] VM PromQL / NATS payload → schemas/<对象>/03_vm_metrics.schema.json
[4] CMDB 实例字典           → schemas/<对象>/04_cmdb_instance.schema.json
```

- **格式漂移** → schema validate 报错（CI gate）
- **逻辑漂移** → expected fixture 对比业务字段
- **真实代码** → runner.format_data + format_metrics 真实跑（不 mock 业务）
- **只 mock 边界** → VM HTTP、DB 任务查询、NATS 消息总线

## 目录约定

```
e2e/
├── pipeline.py                    # 通用流水线驱动（适用 host/middleware/db/protocol/cloud/vm）
├── conftest.py                    # load_fixture / load_schema / fake_nats
├── fixtures/<采集对象>/           # golden 样本（mock 数据）
├── schemas/<采集对象>/            # JSON Schema 契约
└── test_<采集对象>_pipeline.py    # 每个对象一个测试文件
```

## 跑测试

```bash
cd server
.venv/bin/python -m pytest apps/cmdb/tests/e2e/ -v   # 全套
.venv/bin/python -m pytest apps/cmdb/tests/e2e/test_nginx_pipeline.py -v   # 单个
```

## 扩展到新采集对象（基于 middleware 大类示例）

1. 看 plugin 注册：`apps/cmdb/collection/plugins/community/middleware/<新组件>.py`
   找到 `metric_names` 和 `field_mapping`
2. 抓 fixture（4 个）：
   - `fixtures/<新组件>/01_raw_collector.json` 采集脚本输出样本
   - `fixtures/<新组件>/04_expected_cmdb_result.json` 期望 CMDB 实例
3. 写 schema（4 个）：
   - `schemas/<新组件>/01_raw_collector.schema.json`
   - `schemas/<新组件>/04_cmdb_instance.schema.json`
4. 复制 `test_nginx_pipeline.py` → `test_<新组件>_pipeline.py`，改三处：
   - 调 `from apps.cmdb...<新组件> import <新组件>CollectionPlugin`
   - `model_id="<新组件>"`
   - `runner_cls=MiddlewareCollectMetrics`（同大类共享）

**整套接入新对象 < 30 分钟**。

## 已发现的真实 bug（e2e 价值证明）

1. **`HostCollectMetrics.set_cpu_arch` 用错映射表** ✅ 已修复
   原来用 `cup_arch_list`（含 `{"name": "x86"}`）做子串匹配，`x86_64` 先命中 `x86` →
   `cpu_arch=x86`。改为用 `server_cpuarch_list`（OS 架构名 → CMDB 业务编码），
   `x86_64 → x64`、`aarch64 → arm64` 等。`cup_arch_list` 已删除。

2. **`AliyunCollectMetrics._metrics` 疑似无限递归**
   `plugin_cls._metrics.fget(self)` 中 plugin 没 override `_metrics` property，
   会递归回父类同一个 property。生产环境疑似该 property 从未被访问。
   `vmware.py` 同模式但 plugin 有 override，避开了递归。
   已 spawn 任务跟进。

## 设计取舍

| 维度 | 选择 | 理由 |
|---|---|---|
| 不用 docker | ✓ | CI 不依赖容器、毫秒级跑、调试方便 |
| 不用真实 NATS | ✓ | `fake_nats` 同进程派发 + 直接 mock handler |
| 中间转换走真实代码 | ✓ | 真实 `format_data + format_metrics` 跑，bug 不被 mock 掩盖 |
| Schema 在测试期校验 | ✓ | 格式漂移立即报警 |
| Schema 在生产期校验 | ✗（后续可加） | 双重保险：Stargazer publish 前 validate |
| Golden fixture 维护 | 手工 + AI 辅助 | 抓一次真实样本，AI 帮生成 schema 草稿；漂移会被 schema 拦下 |

## 后续可加

- [ ] **声明式 YAML 工作流执行器**（替代手写 `test_*.py`，新对象只需 YAML+fixture）
- [ ] **Stargazer 侧 schema 校验**（发布前校验 NATS payload）
- [ ] 端到端 smoke（docker-compose + nightly）
- [ ] 把 vmware_esxi/vmware_vm/vmware_ds、aliyun bucket/clb/mysql 等 sub-model 补全（每个 + 30 分钟）
- [ ] k8s workload/node/pod 子流补全（每个 + 1 小时，因业务逻辑硬编码较深）

## 关键文件

- `pipeline.py` —— 通用流水线驱动，`run_full_pipeline_generic()` 是核心入口
- `conftest.py` —— `load_fixture` / `load_schema` / `fake_nats` fixture
- `test_host_pipeline.py` —— **最详细的样板**（含 4 段全部 schema + 漂移检测）
- `test_nginx_pipeline.py` —— **大类代表样板**（中间件，最简洁的 generic 用法）
- `test_config_file_pipeline.py` —— **NATS 路径样板**（不走 VM）
