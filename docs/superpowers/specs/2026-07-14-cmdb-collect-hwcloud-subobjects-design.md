# 9 个 hwcloud 子对象 follow-up 设计稿

> **Task 3.8 follow-up** — 2026-07-14

## 背景

Task 3.1 真实化了 2 个 hwcloud 核心子对象(hwcloud_ecs + hwcloud_vpc),但 HwCloudCollectMetrics
实际支持 9 个其他子对象:hwcloud_evs / hwcloud_obs / hwcloud_subnet / hwcloud_eip / hwcloud_sg /
hwcloud_elb / hwcloud_rds / hwcloud_dcs 等。

根据 Pre-Flight Issue 4 决策,这些子对象推到下期 follow-up,作为独立 worktree + spec 处理。

## 目标

- 9 个子对象完整真实化(参考华为云真实 API 响应)
- 每个子对象的 fixture / schema / test / A/B 端对齐
- 不动现有 2 个子对象(hwcloud_ecs / hwcloud_vpc)的 1 commit + 5 commit 真实化

## 9 个子对象范围

| model_id | 中文名 | 优先级 | 父 plugin |
|----------|--------|--------|----------|
| hwcloud_evs | 云硬盘 | P1 | hwcloud |
| hwcloud_obs | 对象存储 | P1 | hwcloud |
| hwcloud_subnet | 子网 | P1 | hwcloud |
| hwcloud_eip | 弹性公网 IP | P1 | hwcloud |
| hwcloud_sg | 安全组 | P1 | hwcloud |
| hwcloud_elb | 弹性负载均衡 | P1 | hwcloud |
| hwcloud_rds | 云数据库 RDS | P1 | hwcloud |
| hwcloud_dcs | 分布式缓存 DCS | P1 | hwcloud |

## 实施计划

### Worktree

```bash
cd /Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite
git worktree add .worktrees/cmdb-collect-hwcloud-subobjects \
  -b feature/cmdb-collect-hwcloud-subobjects feature/cmdb-collect-full-e2e-alignment
```

### 实施步骤(每对象 1 commit)

```
1. 读华为云对应子对象 API 文档(每个子对象有独立 API 端点)
2. 写 01 fixture(参考 API 响应,30+ 行真实样本)
3. 写 02/03 fixture(标准化 + VM metric response)
4. 写 04 expected(实例字典断言基线)
5. 写 01/04 schema(JSON Schema 约束)
6. 写 test_hwcloud_<sub>_pipeline.py(3-5 测试 step1/step2/pipeline/A/B 端)
7. conftest._MODEL_RUNNER_MAP 加 model_id
8. conftest._PLUGIN_MODULE_ALIAS 已有"hwcloud_<sub>": "hwcloud" 别名
9. A/B 端 ALIGNMENT_COVERED_MODEL_IDS 加 model_id
10. 跑测试确认通过
11. 提交:git commit -m "test(cmdb/e2e): Task 6.<n> - hwcloud_<sub> 真实化 + A/B 端覆盖"
```

### 关键接口(从 Task 1/2 继承,已就绪)

- `apps.cmdb.tests.e2e.utils.model_reflection.get_model_field_def(model_id)` — 反射 04 schema
- A 端 `test_stargazer_prometheus_alignment.py` + B 端 `test_cmdb_vm_format_alignment.py`
- conftest `_PLUGIN_MODULE_ALIAS` 已有所有 9 个子对象 → "hwcloud" 别名
- conftest `_MODEL_RUNNER_MAP` 需追加 9 个 model_id → ("cloud_hwcloud", None)
- SCHEMA_DIR_ALIAS 无需新增(每个子对象用自己目录名)

### 重点关注

1. **hwcloud_subnet**:depend on hwcloud_vpc 关联(vpc_id 命中时建 belong_vpc),需保证先有 vpc 数据
2. **hwcloud_evs**:depend on hwcloud_ecs(server_id 命中时建 install_on),需保证先有 ecs 数据
3. **hwcloud_eip**:可能 install_on hwcloud_ecs(实例关联 EIP)
4. **hwcloud_sg**:可能 install_on hwcloud_ecs/vpc,需先有父对象

### 复用模式(从 Task 3.1 经验)

- fixture 用 flat dict 格式(同 aliyun_ecs 模式),不用 raw_stdout envelope
- 04 schema 字段对齐 plugin.field_mappings[model_id](不要加 plugin 没定义的字段)
- 04 schema 的 required 字段只保留 plugin 实际输出的字段(inst_name, resource_name, resource_id, 等)
- A 端 metric_name 后缀:hwcloud_<sub>_info_gauge(从 plugin.metric_names)
- B 端:vmware_vc sub-model 类似处理,hwcloud_<sub> 用自身 model_id

### 预期 commit 数

8 个子对象 × 1 commit = 8 commits(Task 6.1-6.8)
+ Task 6.0 follow-up spec 落档 commit
+ Task 6.9 全量验证 + report
= 共 10 commits

### 预期测试增量

- 8 objects × (4 test + 2 A/B) = 48 tests
- 0 regression(2 个核心子对象 18 tests 全部通过)
- 33 真实落盘对象 + 6 P0 真实化 + 8 商业版 placeholder = 47+ e2e 覆盖

## 风险与约束

1. **不修改 production 代码** — 延续 Task 1/2/3 红线,plugin / runner / collector 不动
2. **不修改 test_pipeline_factory.py** — 现有 33 真实落盘对象 0 regression
3. **subnet/evs 关联依赖**:测试时单 sub-model fixture 即可,关联关联是 plugin assos() 函数行为,不在 fixture 范围
4. **API 文档真实性**:参考华为云官方 API 文档,字段名严格对齐 plugin.field_mappings
5. **占位模式**:如有子对象无真实 API(罕见),按 zstack/h3c_cas stub plugin 模式处理

## References

- Task 3.1 commit `89d1b28f7` - hwcloud_ecs + hwcloud_vpc 真实化模板
- HwCloud plugin: `apps/cmdb/collection/plugins/community/cloud/hwcloud.py`
- HwCloud runner: `apps/cmdb/collection/collect_plugin/hwcloud.py`
- 华为云 API 文档: https://support.huaweicloud.com/api-ecs/ecs_02_0101.html
