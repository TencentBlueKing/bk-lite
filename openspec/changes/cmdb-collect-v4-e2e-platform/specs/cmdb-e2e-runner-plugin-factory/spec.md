# Spec: cmdb-e2e-runner-plugin-factory

## ADDED Requirements

### Requirement: 基于 model_id 自动选 runner / plugin / extra_payload_keys

`server/apps/cmdb/tests/e2e/conftest.py` MUST 提供 `load_runner_plugin_for_model_id(model_id)` fixture 或工厂函数,根据 model_id 返回 `(runner_cls, plugin_cls, extra_payload_keys)` 三元组。

#### Scenario: protocol 类对象(无 metric.result 解析)
- **WHEN** model_id 在 `{influxdb, mssql, ibmmq, ...}`(protocol 大类)中
- **THEN** `load_runner_plugin_for_model_id("influxdb")` 返回 `(ProtocolCollectMetrics, InfluxdbCollectionPlugin, None)`
- **THEN** `extra_payload_keys=None` 表示业务字段平铺到 labels

#### Scenario: db 类对象(平铺)
- **WHEN** model_id 在 `{mysql, postgresql, redis, mongodb, ...}`(db 大类)中
- **THEN** `load_runner_plugin_for_model_id("mysql")` 返回 `(DBCollectCollectMetrics, MysqlCollectionPlugin, None)`
- **THEN** `extra_payload_keys=None` 表示业务字段平铺到 labels

#### Scenario: middleware 类对象(metric.result JSON 编码)
- **WHEN** model_id 在 `{nginx, tomcat, rabbitmq, kafka, ...}`(middleware 大类)中
- **THEN** `load_runner_plugin_for_model_id("nginx")` 返回 `(MiddlewareCollectMetrics, NginxCollectionPlugin, {"result": True})`
- **THEN** `extra_payload_keys={"result": True}` 表示业务字段经 metric.result JSON 编码

### Requirement: 工厂函数覆盖所有 27 个真实落盘对象

`load_runner_plugin_for_model_id` MUST 覆盖 v3 阶段所有 27 个真实落盘对象(main 7 + worktree 20),否则抛 `KeyError` 并给出明确错误信息("model_id X 不在 factory 覆盖范围")。

#### Scenario: 未知 model_id 明确报错
- **WHEN** 调用 `load_runner_plugin_for_model_id("unknown_obj")`
- **THEN** 抛 `KeyError("unknown_obj")` 或工厂自定义异常,错误信息明确指出"未在 factory 覆盖范围,需先在 `apps/cmdb/collection/plugin_registry.py` 注册"

### Requirement: 工厂函数不引入新的 plugin 依赖

`load_runner_plugin_for_model_id` MUST 只 import 已经在 `apps/cmdb/collection/plugins/` 目录存在的 plugin 类,不引入新的依赖。

#### Scenario: 不引入新依赖
- **WHEN** 工厂被调用
- **THEN** 所有 import 路径在 `apps/cmdb/collection/plugins/{community,enterprise}/{protocol,db,middleware}/<model_id>.py` 范围
- **THEN** pyproject.toml / requirements.txt 不变