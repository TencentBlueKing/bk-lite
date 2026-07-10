# Tasks: CMDB 采集 v4 — 消费侧 e2e 平台化

> 实施任务清单,按依赖顺序排列。每对象独立 commit,失败可单对象回滚。

## 1. 基础设施搭建(0.5d)

- [ ] 1.1 写 `server/apps/cmdb/tests/e2e/schemas/00_common_contract.schema.json`(公共契约:必填 model_id / captured_at / raw_stdout 结构)
- [ ] 1.2 写 `server/apps/cmdb/tests/e2e/conftest.py::load_runner_plugin_for_model_id(model_id)` 工厂函数(覆盖 27 个对象,返回 (runner_cls, plugin_cls, extra_payload_keys) 三元组)
- [ ] 1.3 写 `server/apps/cmdb/tests/e2e/test_common_contract.py` 跨对象公共契约测试(用 `pytest.mark.parametrize` 显式列举 27 个 model_id,自动校验所有 fixture 满足公共契约)
- [ ] 1.4 写 `docs/cmdb-e2e-author-guide.md` 作者指南(5 步加新对象 e2e + 常见 expected_subset 模式 + 失败排查)

## 2. 参数化工厂模板(0.3d)

- [ ] 2.1 抽 `server/apps/cmdb/tests/e2e/test_pipeline_factory.py::test_pipeline_fixture_driven_via_factory` 参数化模板(基于 model_id 调工厂 + 三层验证 + inst_name 规则)
- [ ] 2.2 把 4 个现有对象(influxdb / mysql / nginx / redis)的 fixture 也加进工厂参数化列表,确认工厂版本跑通且**不破坏现有 test**
- [ ] 2.3 跑 `pytest apps/cmdb/tests/e2e/ -v`,确认 51+ tests 仍 passed

## 3. P0 批量(8 个对象 × 30 min ≈ 4h)

> 按"已落盘 + 业务高价值"排序。模板参考已存在的 4 个对象(每对象 5 步)

- [ ] 3.1 **postgresql** e2e — db runner 平铺,模板参考 mysql
- [ ] 3.2 **mongodb** e2e — db runner 平铺
- [ ] 3.3 **tomcat** e2e — middleware runner metric.result JSON,模板参考 nginx
- [ ] 3.4 **rabbitmq** e2e — middleware runner
- [ ] 3.5 **elasticsearch** e2e — protocol runner,模板参考 influxdb
- [ ] 3.6 **kafka** e2e — middleware runner
- [ ] 3.7 **zookeeper** e2e — middleware runner
- [ ] 3.8 **haproxy** e2e — middleware runner

## 4. P1 批量(8 个对象 × 30 min ≈ 4h)

- [ ] 4.1 **keepalived** e2e — middleware runner
- [ ] 4.2 **openresty** e2e — middleware runner
- [ ] 4.3 **apache** e2e — middleware runner
- [ ] 4.4 **activemq** e2e — middleware runner
- [ ] 4.5 **dameng** e2e — db runner(国产化优先)
- [ ] 4.6 **tongweb** e2e — middleware runner(国产化)
- [ ] 4.7 **minio** e2e — protocol runner
- [ ] 4.8 **consul** e2e — middleware runner

## 5. P2 批量(7 个对象 × 30 min ≈ 3.5h)

- [ ] 5.1 **etcd** e2e
- [ ] 5.2 **memcached** e2e
- [ ] 5.3 **squid** e2e
- [ ] 5.4 **rocketmq** e2e
- [ ] 5.5 **redis_sentinel** e2e
- [ ] 5.6 **jboss** e2e
- [ ] 5.7 **jetty** e2e

## 6. 验证 + 收尾(0.3d)

- [ ] 6.1 跑 `pytest apps/cmdb/tests/e2e/ -v` 全量(预计 ~100+ tests passed)
- [ ] 6.2 跑 `pytest apps/cmdb/tests/e2e/ --cov=apps/cmdb/tests/e2e --cov-report=term`,确认增量覆盖率 ≥ 75%
- [ ] 6.3 跑 `pre-commit run --all-files`(black / isort / flake8 / check_migrate)确认无格式问题
- [ ] 6.4 按 commit 粒度拆 commit(基础设施 1 个 / 工厂模板 1 个 / 每对象 1 个 / docs 1 个)
- [ ] 6.5 写 v4 收尾报告 `docs/superpowers/plans/2026-07-10-cmdb-collect-v4-phase1-execution-report.md`
- [ ] 6.6 跑 `openspec validate cmdb-collect-v4-e2e-platform` 确认仍 valid
- [ ] 6.7 在 `docs/superpowers/plans/2026-07-10-cmdb-collect-execution-roadmap.md` 追加 v4 章节 + 链接到本 OpenSpec change

## 验证标准汇总

- [ ] 27 个真实落盘对象 100% 有 fixture_driven e2e 测试
- [ ] 4 个对象现有 test 不破坏(51 passed 起步 → ~100+ passed 收尾)
- [ ] `pytest --cov` 增量覆盖率 ≥ 75%
- [ ] 跨对象公共契约测试自动发现新 fixture
- [ ] 作者指南 5 步模板可让新人 5 分钟上手
- [ ] OpenSpec 仍 valid
- [ ] commit 粒度可逐对象回滚

## 总工作量估算

| 阶段 | 时间 | 累计 |
|---|---|---|
| 1. 基础设施 | 0.5d | 0.5d |
| 2. 工厂模板 | 0.3d | 0.8d |
| 3. P0 批量 | 4h | 1.3d |
| 4. P1 批量 | 4h | 1.8d |
| 5. P2 批量 | 3.5h | 2.2d |
| 6. 验证收尾 | 0.3d | **2.5d** |

**总周期**:2.5 个工作日(对比调研报告的 1.5-2 人月估算,本 change 是 Phase 1 切片,聚焦"e2e 平台化"主线)
