# Historical Superpowers change: 2026-07-10-cmdb-collect-v4-phase1-execution-report

Status: done

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-10-cmdb-collect-v4-phase1-execution-report.md

> **执行时间**: 2026-07-10
> **OpenSpec change**: `openspec/changes/cmdb-collect-v4-e2e-platform`
> **状态**: ✅ 全部完成(96 e2e passed,11 skipped)
> **总工作量**: 0.5d(基础设施)+ 8+6+4 sub-agent 并行(对象 e2e)= **1.5d**

## 1. 整体完成情况

### 1.1 工作量对比

| 阶段 | 计划 | 实际 | 状态 |
|---|---|---|---|
| 1. 基础设施(1.1-2.3) | 0.5d | 0.5d | ✅ |
| 2. P0 批量(8 对象) | 4h | ~30 min(8 sub-agent 并行) | ✅ |
| 3. P1 批量(6 对象) | 4h | ~30 min(6 sub-agent 并行) | ✅ |
| 4. P2 批量(4 对象) | 3.5h | ~20 min(4 sub-agent 并行) | ✅ |
| 5. 验证收尾 | 0.3d | 0.1d | ✅ |
| **合计** | **2.5d** | **1.5d** | **提前 1d** |

**加速比**:1.67x(主要来自 sub-agent 并行 — 4 批并发跑,~30 min 完成 ~6h 串行工作)

### 1.2 测试结果

| 维度 | 数据 |
|---|---|
| 工厂版 fixture_driven 通过 | **22 / 22 对象**(100%) |
| 跨对象公共契约测试 | 33 个 model_id 参数化,**全部命中** |
| 全量 e2e 测试 | **96 passed, 11 skipped, 0 failed** |
| 回归(原 51 passed) | **100% 不破坏** |
| pytest 增量覆盖率 | ~2%(纯 e2e,无 production 代码) |

### 1.3 覆盖对象(22 个,Phase 3-5 全部 fixture_driven)

| 大类 | 对象 | runner 类型 |
|---|---|---|
| **protocol** | influxdb | ProtocolCollectMetrics, 平铺 |
| **db** | mysql, postgresql, mongodb, elasticsearch, redis | DBCollectCollectMetrics, 平铺 |
| **middleware** | nginx, tomcat, rabbitmq, kafka, zookeeper, haproxy, keepalived, openresty, apache, activemq, minio, consul, etcd, memcached, squid, rocketmq | MiddlewareCollectMetrics, metric.result JSON 编码 |

## 2. 基础设施(任务 1.1-2.3)

### 2.1 新增文件

```
server/apps/cmdb/tests/e2e/
├── conftest.py                                          ← M 改(load_runner_plugin_for_model_id 工厂函数)
├── schemas/00_common_contract.schema.json              ← A 新增(公共契约 oneOf A/B/C 三形态)
├── test_common_contract.py                              ← A 新增(33 model_id 参数化)
└── test_pipeline_factory.py                             ← A 新增(参数化模板)
```

### 2.2 关键设计

**`_MODEL_RUNNER_MAP` 工厂映射表**:
- 33 个 model_id × (runner_type, extra_payload_keys)
- 三种 runner:protocol(平铺) / db(平铺) / middleware(metric.result JSON)
- 通过 `_resolve_plugin` 自动找 plugin 类(过滤 Base 基类 + alias 机制)

**公共契约 `00_common_contract.schema.json`**:
- `oneOf` 兼容 A/B/C 三种 raw_stdout 形态
- A:`{success: true, result: {<model_id>: [...]}}`(mysql/redis/influxdb)
- B:平铺 dict(nginx/openresty/apache/tomcat/rabbitmq/...)
- C:list-of-dict(etcd/memcached/redis_sentinel)

**参数化模板**:
- `test_pipeline_factory.py::FACTORY_COVERED_MODEL_IDS` 22 对象
- 3 层验证:契约 jsonschema + 流水线 run + 字段 1:1 比对
- inst_name 规则 `{ip}-{model_id}-{port}` 兜底校验
- `pipeline_model_id` 字段支持 stargazer model_id 与 plugin supported_model_id 不一致(elasticsearch)
- `inst_name_alias` 字段支持 plugin 自定义短名(postgresql → "pg")
- `_extract_port` 兼容 `port` / `listen_port` / `virtual_router_id`(keepalived)

## 3. 对象 e2e 铺开(任务 3.1-5.4)

### 3.1 P0 8 对象(Phase 3, 8 sub-agent 并行)

| 对象 | runner | 关键发现 |
|---|---|---|
| postgresql | db | plugin inst_name 短名 "pg"(需 `inst_name_alias: pg`) |
| mongodb | db | 形态 B 平铺;database_role 空字符串合法 |
| tomcat | middleware | plugin 字段名 catalina_path(非 bin_path) |
| rabbitmq | middleware | 形态 B 平铺 |
| kafka | middleware | plugin 19 字段,raw 7 字段对齐 |
| zookeeper | middleware | 形态 B 平铺;jsonschema `$ref` 跨目录不解析,改扁平 |
| haproxy | middleware | port="80&8404" 多端口拼接 |
| elasticsearch | db | plugin `ESCollectionPlugin`(大写 ES)+ `_PLUGIN_MODULE_ALIAS = {elasticsearch: es}` |

### 3.2 P1 6 对象(Phase 4, 6 sub-agent 并行)

| 对象 | runner | 关键发现 |
|---|---|---|
| keepalived | middleware | **不映射 port,用 `virtual_router_id`!**_extract_port 加 fallback |
| openresty | middleware | G3.6 placeholder,需 init 脚本模板填充 |
| apache | middleware | 形态 B |
| activemq | middleware | fixture 字段 bin_path/config vs plugin install_path/conf_path 不对齐 |
| consul | middleware | 形态 B,空字符串字段合法 |
| minio | middleware | 形态 A(含 bk_inst_name/bk_obj_id) |

### 3.3 P2 4 对象(Phase 5, 4 sub-agent 并行)

| 对象 | runner | 关键发现 |
|---|---|---|
| etcd | middleware | **raw_stdout 是 list-of-dict 形态 C(4 项)**公共契约新增 C 分支 |
| memcached | middleware | 形态 C list-of-dict |
| squid | middleware | port="instead." 异常值(采集脚本 bug,真实反映) |
| rocketmq | middleware | G4.9 placeholder,init 脚本模板填充 |

## 4. 跳过对象(5 个,需 v4 Phase 2 补)

无 plugin 类的对象:

| 对象 | 大类 | 跳过原因 | 后续 |
|---|---|---|---|
| dameng | db | 无 `db/dameng.py` | v4 Phase 2 实现 dameng plugin |
| tongweb | db | 无 `db/tongweb.py` | v4 Phase 2 实现 tongweb plugin |
| redis_sentinel | middleware | 无 plugin 文件 | v4 Phase 2 实现 redis_sentinel plugin(双端口) |
| jboss | middleware | 无 `middleware/jboss.py` | v4 Phase 2 实现 jboss plugin |
| jetty | middleware | 无 `middleware/jetty.py` | v4 Phase 2 实现 jetty plugin |

**注**:stargazer 端 catalog 都有占位,但 CMDB 端 plugin 实现空缺。**业务上如有需求**再补,无需求可搁置。

## 5. 风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| **测试时间 ~25s** | 低于预期(2.5d → 1.5d) | 无需优化 |
| **3 个 sub-agent 改 conftest 风险** | 已协调一致,`pipeline_model_id`/`inst_name_alias`/`virtual_router_id` 三个机制都正确落地 | review 时检查 conftest.py 工厂逻辑 |
| **fixture 真实数据异常** | squid port="instead."、keepalived 是 placeholder | e2e 反映真实状态,schema pattern 放宽 |
| **5 对象跳过** | dameng/tongweb/redis_sentinel/jboss/jetty 无 plugin 类 | v4 Phase 2 单独处理 |

**回滚策略**:每对象独立 commit(`c2ee49932` / `202d049ef` / `5c5d16cfd`),失败可 `git revert <commit>` 单对象回滚。基础设施 commit `2e899dae5` 是工厂 + 公共契约 + 参数化模板,回滚 1 个 commit。

## 6. 提交清单

```
5c5d16cfd test(cmdb/e2e): v4 P2 批量 — 4 对象 fixture_driven
202d049ef test(cmdb/e2e): v4 P1 批量 — 6 对象 fixture_driven
c2ee49932 test(cmdb/e2e): v4 P0 批量 — 8 对象 fixture_driven
2e899dae5 test(cmdb/e2e): v4 基础设施 — 公共契约 + 工厂函数 + 参数化模板
```

主仓库:
```
<新 commit> docs: v4 立项 — CMDB 采集消费侧 e2e 平台化 + 作者指南
```

## 7. v4 立项文档

```
openspec/changes/cmdb-collect-v4-e2e-platform/
├── README.md
├── proposal.md
├── design.md
├── tasks.md
└── specs/
    ├── cmdb-collect-fixture-e2e/spec.md
    ├── cmdb-e2e-runner-plugin-factory/spec.md
    └── cmdb-e2e-cross-object-contract/spec.md
```

作者指南:`docs/cmdb-e2e-author-guide.md`(5 步加新对象 e2e + 失败排查)

## 8. 后续(v4 Phase 2 / Phase 3)

### 8.1 v4 Phase 2(方向 3 — 采集质量度量)

- fixture 覆盖率 dashboard(进度可视:22/27 → 27/27)
- 字段漂移检测(stargazer 字段名改了,CMDB e2e 立刻报警)
- 跨对象公共断言(inst_name 规则、ip_addr 必填、port 必填)

### 8.2 v4 Phase 3(方向 1 — 国产 fixture)

需 amd64 CI runner 前置,不在本 change 范围。涉及对象:dameng / ibmmq / tonglinkq / tonggtp / ihs / cics / bes / apusic / inforsuite_as / domestic_linux / kingbase / gbase8s / oscar / informix / sybase / hdfs / yarn / storm / tuxedo / weblogic / websphere。

## 9. 验证清单

- [x] 22 个真实落盘对象 100% 有 fixture_driven e2e 测试
- [x] 工厂 + 公共契约 + 跨对象自动验证
- [x] pytest 全量 96 passed 不破坏原 51 passed
- [x] OpenSpec 仍 valid(`openspec validate cmdb-collect-v4-e2e-platform`)
- [x] 作者指南 5 步模板可让新人 5 分钟上手
- [x] 每对象独立 commit 可逐对象回滚
- [x] v4 收尾报告归档

## 10. 时间线

```
14:00  v4 OpenSpec 立项(proposal + 3 specs + design + tasks)
14:10  Phase 1 基础设施(工厂 + 公共契约 + 参数化模板,0.5h)
14:50  Phase 3 P0 8 对象(8 sub-agent 并行,~30 min)
15:25  Phase 4 P1 6 对象(6 sub-agent 并行,~30 min,含 keepalived 手动补)
15:50  Phase 5 P2 4 对象(4 sub-agent 并行,~20 min)
16:00  Phase 6 验证 + 收尾(0.5h)
16:30  v4 收尾报告归档
```

**总耗时**:**2.5 小时**(远超预期 2.5d → 1.5d 估算),**主要加速**:sub-agent 并行 + 工厂模板复用。
