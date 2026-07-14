# Design: CMDB 采集 v4 — 消费侧 e2e 平台化

## Context

v3 已完成代码侧 100%(commit `51c76aefa` + 5 个新 commit),32/57 fixture 真实落盘。Phase 2 P0 已在 v3 worktree 跑通 4 个对象的 fixture_driven e2e 测试(commit `f59351609` + 后续 3 个),共 51 passed。

**当前状态**:
- `server/apps/cmdb/tests/e2e/pipeline.py:185` — 4 段通用流水线(`step1_stargazer_normalize_generic` / `step2_push_to_vm` / `step3_cmdb_consume_generic` / `run_full_pipeline_generic`)就绪
- 3 个 runner 形态已验证:ProtocolCollectMetrics(平铺)/ DBCollectCollectMetrics(平铺)/ MiddlewareCollectMetrics(metric.result JSON 编码)
- 4 个对象有 fixture_driven 测试:influxdb(protocol)/ mysql(db)/ nginx(middleware)/ redis(db)
- **断链**:23 个有真实落盘的对象(主分支 7 + worktree 20 = 27,已做 4 个)无 e2e 验证

**约束**:
- 测试必须离线可跑(`DB_ENGINE=sqlite INSTALL_APPS=cmdb,system_mgmt,core` + monkeypatch)
- 不引入新依赖(只用 Python + 已有 jsonschema + pytest-django)
- 必须按用户偏好"先文档后动手 + 支持回填" — 作者文档必出
- 复用 v3 已有的 4 个对象模板(不重写,只抽取公共部分)

**stakeholders**:
- 用户本人(两边 owner,既要消费又要采集)
- 团队其他人(后续接手需要写新对象 e2e → 文档驱动)
- 未来 v4 Phase 2(质量度量 / schema drift)依赖此平台

## Goals / Non-Goals

### Goals

- 27 个真实落盘对象 100% 有 fixture_driven e2e 测试
- 跨对象公共契约自动验证(`test_common_contract.py` 自动遍历)
- 新对象加 e2e ≤ 5 步(按 author guide)
- 全部 e2e 跑通时间 ≤ 5 min
- pytest 增量覆盖率 ≥ 75%(QUALITY_SCORE 红线)
- 4 个对象的现有测试**不破坏**(回归)

### Non-Goals

- 方向 1(国产 fixture 真实采集)— 需 amd64 CI,前置未达成
- 方向 4(K8s / VMware / 云采集)— 用户偏好明确排除
- 生产环境 schema drift dashboard — v4 Phase 2
- fixture 覆盖率 dashboard — v4 Phase 2
- 修改 stargazer / CMDB production 代码 — 本 change 纯测试

## Decisions

### D1:工厂函数放 conftest.py 而非新建 plugin_registry

**决策**:`server/apps/cmdb/tests/e2e/conftest.py` 加 `load_runner_plugin_for_model_id()` 函数(单文件,≤30 行),不新建 `plugin_registry.py`。

**理由**:
- 27 个对象 × 1 行三元组 = 27 行表,放 conftest 自然
- 工厂是测试设施,不是 production 代码
- 不引入新的模块边界,降低 review 成本

**Alternatives considered**:
- 新建 `apps/cmdb/collection/plugin_registry.py`(production 模块)— 拒绝,因为是测试设施
- 用 decorator 自动注册(import 时副作用)— 拒绝,隐式行为难调试
- YAML 配置驱动(`plugin_registry.yaml`)— 拒绝,TypeScript 风格的动态类型带来额外复杂度

### D2:不重写 4 个对象现有 test,只抽公共参数化

**决策**:`test_influxdb_pipeline.py` 等 4 个对象的现有 test **保留不动**,新增 `test_pipeline_fixture_driven_via_factory` 参数化版本作为"工厂"模板。

**理由**:
- 4 个对象的现有 test 是已验证的"金标准",重写有回归风险
- 新增参数化版本作为后续 23 对象的可复用模板
- 现有 test 失败 = 工厂版本也失败(自然形成交叉验证)

**Alternatives considered**:
- 重写 4 个对象的 test 用工厂— 拒绝,增加回归面
- 删除 4 个对象原 test 只留工厂版— 拒绝,丢掉金标准

### D3:跨对象公共契约用 `$ref` 而非复制

**决策**:`schemas/00_common_contract.schema.json` 集中定义公共字段(必填 model_id / captured_at / raw_stdout 结构),对象级 schema 用 `$ref` 引用,不复制定义。

**理由**:
- 公共字段改了 = 改一处(避免 27 个 schema 同步修改)
- 符合 JSON Schema 规范
- 公共契约变更影响范围 = 1 个文件

**Alternatives considered**:
- 公共字段 inline 在每个对象 schema — 拒绝,维护灾难
- Python 端校验公共契约(不走 schema)— 拒绝,丢失 schema 验证的强类型保证

### D4:不写 conftest 跨对象 fixture 自动发现 — 用显式列举

**决策**:`test_common_contract.py` 用 `pytest.mark.parametrize` 显式列举 27 个 model_id(参数化列表),不靠 `os.listdir` 自动发现。

**理由**:
- 显式列举 = review 时一眼看出"哪些对象已覆盖 / 哪些漏了"
- 新增对象时 CI 必然 fail(参数化列表与新 fixture 不匹配),强制更新 test
- 自动发现会让"漏加 fixture"无法被发现

**Alternatives considered**:
- `os.listdir('fixtures/')` 自动发现 — 拒绝,失去"哪些覆盖了"的可视化
- glob pattern `fixtures/*/01_stargazer_raw.json` — 拒绝,同理由

### D5:作者文档 `docs/cmdb-e2e-author-guide.md` 用 step-by-step 模板

**决策**:作者文档按"5 步加新对象 e2e"写,每步给具体命令 + 期望输出 + 注意事项。

**理由**:
- 用户偏好"文档支持 review + 回填"
- 团队其他人接手时 5 分钟就能上手
- 与 v3 路线图风格一致(看 v3 plan 文档就能感受到)

**Alternatives considered**:
- 只写 README 几行 — 拒绝,信息密度不够
- 视频教程 — 拒绝,需要外部存储且不便 review

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| **27 个对象的 plugin field_mapping 不全**(如 mysql 缺 role)→ expected_subset 不一致 | Phase 2 已踩过,test 用 expected_subset 子集比对,只断言 plugin 实际映射的字段 |
| **stargazer 真实 fixture 字段值可能不准确**(如 highgo version="") | expected_subset 留空字符串 + schema `type: ["string", "null"]`,不强制值 |
| **27 个对象 e2e 跑通时间 > 5 min** | factory 用 model_id 直接跳到 step3(避免重复 step1/step2),每个对象 8-10s 预计 |
| **新增对象 e2e 模板** | author guide 详细 + Phase 2 已铺 4 个可参考 |
| **公共契约 schema 改了 → 大量 test fail** | schema 改前先在 1 个对象试跑,确认无回归再推广 |
| **工厂函数 import 失败**(plugin 路径改了) | 工厂 import 集中在 conftest,失败时明确抛 `ImportError(f"plugin for {model_id} not found")` |
| **CI runner 环境差异**(Mac vs Linux) | 已有 e2e 在 sqlite 跑,跨平台一致 |
| **27 个对象 e2e 不能完全照搬 4 个模板**(各对象 plugin 字段不同) | author guide 留"自定义 expected_subset 模板"段,显式列常见情况 |

## Migration Plan

### 阶段 1:基础设施(0.5d,优先)

1. 写 `00_common_contract.schema.json`
2. 写 `load_runner_plugin_for_model_id()` 工厂(conftest.py)
3. 写 `test_common_contract.py` 跨对象公共契约测试
4. 写 `docs/cmdb-e2e-author-guide.md`

### 阶段 2:参数化工厂模板(0.3d)

5. 抽 `test_pipeline_fixture_driven_via_factory` 参数化模板(conftest 或独立文件)
6. 跑通 4 个现有对象的工厂版本,确认不破坏现有 test

### 阶段 3:批量铺 23 个对象(1.5-2d)

按"已落盘 / 高价值"优先级:

| 优先 | 对象 | 模板参考 | 预计 |
|---|---|---|---|
| P0 | postgresql / mongodb / tomcat / rabbitmq | mysql / redis / nginx 模板 | 30 min/对象 |
| P1 | elasticsearch / kafka / zookeeper / haproxy | influxdb(protocol) + mysql(db) | 30 min/对象 |
| P2 | keepalived / openresty / apache / activemq / dameng / tongweb / minio / consul / etcd / memcached / squid / rocketmq / redis_sentinel / jboss / jetty | 同上 | 30 min/对象 |
| (worktree 中已有 fixture 但未在主分支) | 18 个对象 | 同上 | 30 min/对象 |

每对象 5 步:
1. `cp` stargazer fixture → `fixtures/<obj>/01_stargazer_raw.json`
2. 写 `schemas/<obj>/01_stargazer_raw.schema.json` + `04_cmdb_instance.schema.json`(用 `$ref` 公共契约)
3. 写 `fixtures/<obj>/04_expected_cmdb_result.json`(从 fixture raw 抽出关键字段,标注数据源)
4. 写 `test_<obj>_pipeline.py` 调工厂 + 三层验证
5. 跑 `pytest -v`,失败修 expected_subset

### 阶段 4:验证 + commit(0.3d)

27. `pytest apps/cmdb/tests/e2e/ -v` 全跑(预计 ~100+ tests passed)
28. 提交 commit:feat / docs 拆开
29. 写 v4 收尾报告

### Rollback 策略

- 每个对象 commit 独立,失败可 `git revert <commit>` 单对象回滚
- 工厂函数放 conftest.py 不放新建文件,回滚 1 个 commit 即可
- 公共契约 schema 集中 1 个文件,回滚简单
- 4 个对象原 test 不动,即使新代码坏也不影响

## Open Questions

1. **工厂函数的 import 失败处理**:`ImportError` 还是 `pytest.skip`?
   - 倾向 `pytest.skip` + warning,避免某对象 plugin 没装导致整个 e2e 套件 fail
   - 需 review 时确认

2. **27 个对象 e2e 是否分批 commit 还是一个 commit?**
   - 倾向每对象 1 commit(原子性好,review 友好)
   - 阶段 1 基础设施可独立 1 commit
   - 阶段 3 批量阶段每对象 1 commit

3. **跨对象参数化模板放 conftest 还是 `test_pipeline_factory.py`?**
   - 倾向 `test_pipeline_factory.py`(独立文件,符合 pytest 自动发现)
   - conftest 只放 fixture + 工厂函数

4. **文档放 docs/ 还是 `server/apps/cmdb/tests/e2e/README.md`?**
   - 倾向 `docs/cmdb-e2e-author-guide.md`(跨模块文档统一)
   - 也可加 `server/apps/cmdb/tests/e2e/README.md` 作为本地入口

5. **作者指南用什么工具写?** Markdown(默认) vs Docusaurus(若后续接 docs 站)
   - 倾向 Markdown(v4 不引入新工具)
