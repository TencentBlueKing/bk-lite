# Proposal: CMDB 采集 v4 — 消费侧 e2e 平台化

## Why

v3 已完成代码侧(57/57 catalog + 160 pytest),但 fixture 落盘与 CMDB 端 e2e 验证**脱节**:

- **fixture 端**:32/57 真实落盘,但每个 fixture 缺乏自动验证
- **CMDB 端**:已有 4 段通用 e2e 流水线(`server/apps/cmdb/tests/e2e/pipeline.py:185`),但**只有 4 个对象**有 fixture_driven 测试
- **断链风险**:stargazer 改了一个字段名,CMDB 端要等生产环境踩坑才发现

**机会**:v3 已经把 e2e 框架搭好,4 个对象的 fixture_driven 测试模板(protocol/db/middleware 三种 runner)已验证通过。**铺到 27 个真实落盘对象的工作量很小**(每个 30 分钟),但能**首次实现"采集产物 → 落库 → 字段对齐"全链路自动验证**。

**为什么现在**:
- v3 worktree 5 个新 commit(Phase 1+2)已落,代码侧稳态
- 4 个 runner 模板就绪,铺到其他对象 = 重复工作,可批量
- 后续 v4 阶段(质量度量 / schema drift 检测)都依赖这个 e2e 平台

## What Changes

- **新增**:`server/apps/cmdb/tests/e2e/fixtures/<model_id>/01_stargazer_raw.json` × 23(覆盖剩余 23 个真实落盘对象)
- **新增**:`server/apps/cmdb/tests/e2e/schemas/<model_id>/01_stargazer_raw.schema.json` × 23
- **新增**:`server/apps/cmdb/tests/e2e/fixtures/<model_id>/04_expected_cmdb_result.json` × 23
- **新增**:`test_<model_id>_pipeline.py` × 23(每对象 fixture_driven 测试,3 层验证)
- **新增**:`server/apps/cmdb/tests/e2e/conftest.py` 扩展 — `load_runner_plugin_for_model_id()` 工厂函数(根据 model_id 自动选 runner + plugin)
- **新增**:`server/apps/cmdb/tests/e2e/schemas/00_common_contract.schema.json` — 跨对象公共契约(所有 fixture 必须满足的基础结构)
- **修改**:`test_influxdb_pipeline.py / test_mysql_pipeline.py / test_nginx_pipeline.py / test_redis_pipeline.py` — 抽出 `test_pipeline_fixture_driven` 为公共参数化 fixture(避免 23 份重复)
- **新增**:`docs/cmdb-e2e-author-guide.md` — 给后续对象写 e2e 的 step-by-step 文档(对齐用户"偏好文档支持 review"风格)

**BREAKING**:无(纯新增 + 测试基础设施)

## Capabilities

### New Capabilities

- `cmdb-collect-fixture-e2e`:为每个有 stargazer 真实落盘的对象,提供"采集 fixture → CMDB 端实例"全链路自动验证。包含 3 层验证(契约 jsonschema / 流水线 run / 字段 1:1 对齐)和 inst_name 规则 `{ip}-{model_id}-{port}` 兜底校验。
- `cmdb-e2e-runner-plugin-factory`:基于 model_id 自动选 runner + plugin + extra_payload_keys,屏蔽三个 runner 形态(protocol 平铺 / db 平铺 / middleware metric.result JSON)的差异。
- `cmdb-e2e-cross-object-contract`:所有 fixture 必须满足的公共契约(必须有 model_id / captured_at / raw_stdout.success / raw_stdout.result.{model_id}[] 至少 1 条),用于早期发现 fixture 漂移。

### Modified Capabilities

(暂无。v4 不修改 v3 已有 spec 的需求,只新增基础设施。)

## Impact

- **代码影响**:
  - `server/apps/cmdb/tests/e2e/` 新增 ~80 个文件(23 对象 × 3 fixture + 1 test + 共享工厂)
  - `server/apps/cmdb/tests/e2e/pipeline.py` 加 1 个工厂函数(单方法,≤30 行)
  - `server/apps/cmdb/tests/e2e/conftest.py` 加 1 个 fixture(≤20 行)
- **依赖影响**:无(纯 Python + 已有 jsonschema)
- **运行时影响**:本地开发跑 `pytest apps/cmdb/tests/e2e/ -v` 时间从 ~25s → 预计 ~3-4 min(23 个对象 × 8-10s/对象)
- **CI 影响**:v3 已有 CI(GitHub Actions),新增 e2e 测试加进去(增量 < 3 min)
- **风险**:
  - 23 个对象 plugin field_mapping 不全(role / master_host 等不入实例)→ 已在 Phase 2 摸到,test 走 expected_subset 子集比对
  - 部分对象 fixture 真实落盘版本为空字段(highgo version="")→ expected_subset 留空 + jsonschema 校验字段可选
  - middleware runner 的 extra_payload_keys 必须正确设置 → 工厂函数按 model_id 预设
- **可逆性**:高(纯新增,失败可逐对象回滚)
- **依赖前置**:
  - Phase 1 已完成(32/57 fixture 落盘)
  - Phase 2 P0 已完成(4 个对象 e2e 模板就绪)
  - **本 change 目标**:把 4 个对象扩到 27 个对象

## 验证标准(交付时)

- [ ] 23 个对象的 `test_<model_id>_pipeline.py::test_pipeline_fixture_driven` 全部 passed
- [ ] 全部 e2e 跑通(预计 ~100+ tests passed,包括 23 个 fixture_driven)
- [ ] `server/apps/cmdb/tests/e2e/conftest.py` 的 `load_runner_plugin_for_model_id()` 工厂就绪并被使用
- [ ] 跨对象公共契约 schema 验证 27 个 fixture(主分支 + worktree)全部命中
- [ ] 文档 `docs/cmdb-e2e-author-guide.md` 完成,包含"加一个新对象 e2e 只需 5 步"的模板
- [ ] pytest 增量覆盖率 ≥ 75%(QUALITY_SCORE.md 红线)
- [ ] 在 v3 路线图文档追加 v4 章节 + 链接

## 不在范围内(明确排除)

- **方向 1**(国产 fixture 真实采集)— 需 amd64 CI runner,前置依赖未达成
- **方向 4**(K8s / VMware / 云采集)— 用户历史偏好明确排除
- **方向 5**(stargazer 插件扩展)— 是方向 1 的子任务,不在本 change 范围
- **生产环境 schema drift dashboard** — 留 v4 Phase 2
- **fixture 覆盖率 dashboard** — 留 v4 Phase 2
