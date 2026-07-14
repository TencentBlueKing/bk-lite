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

- v4 OpenSpec change:`openspec/changes/cmdb-collect-v4-e2e-platform/`
- 已有 4 个对象的范本(2026-07-10 commit):`test_influxdb_pipeline.py` / `test_mysql_pipeline.py` / `test_nginx_pipeline.py` / `test_redis_pipeline.py`
- v3 路线图 + Phase 1-5 执行报告:`docs/superpowers/plans/2026-07-0[6-8]-cmdb-collect-v3-*.md`
- 调研报告(本 change 立项依据):`docs/superpowers/plans/2026-07-10-cmdb-collect-next-step-discussion.md`
