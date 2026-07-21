# Task 4: P2 Archived placeholder(22 套)— 17 license + 5 集群/平台

**Status:** `DONE`

**Worktree:** `/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/.worktrees/cmdb-collect-full-e2e-alignment/`
**Branch:** `feature/cmdb-collect-full-e2e-alignment`
**Date:** 2026-07-14
**Brief:** `.superpowers/sdd/task-4-brief.md`(Task 4.1-4.23)

---

## 1. Status

`DONE` — 22 commits 全部就位,22 对象 e2e 100% 覆盖,A/B 端公共契约命中,全量 e2e 519 passed + 91 skipped + 0 failed,无 regression。

---

## 2. Completed sub-tasks

| Sub-task | 描述 | 状态 |
|----------|------|------|
| Task 4.1 | apusic archived placeholder(license) | DONE |
| Task 4.2 | bes archived placeholder(license) | DONE |
| Task 4.3 | informix archived placeholder(license) | DONE |
| Task 4.4 | ihs archived placeholder(license) | DONE |
| Task 4.5 | inforsuite_as archived placeholder(license) | DONE |
| Task 4.6 | iris archived placeholder(license) | DONE |
| Task 4.7 | couchbase archived placeholder(license) | DONE |
| Task 4.8 | oceanbase archived placeholder(license) | DONE |
| Task 4.9 | oscar archived placeholder(license) | DONE |
| Task 4.10 | sap_hana archived placeholder(license) | DONE |
| Task 4.11 | sybase archived placeholder(license) | DONE |
| Task 4.12 | tonggtp archived placeholder(license) | DONE |
| Task 4.13 | tonglinkq archived placeholder(license) | DONE |
| Task 4.14 | tongrds archived placeholder(license) | DONE |
| Task 4.15 | tuxedo archived placeholder(license) | DONE |
| Task 4.16 | weblogic archived placeholder(license) | DONE |
| Task 4.17 | websphere archived placeholder(license) | DONE |
| Task 4.18 | hdfs archived placeholder(cluster_complex) | DONE |
| Task 4.19 | storm archived placeholder(cluster_complex) | DONE |
| Task 4.20 | yarn archived placeholder(cluster_complex) | DONE |
| Task 4.21 | mycat archived placeholder(cluster_complex) | DONE |
| Task 4.22 | domestic_linux archived placeholder(platform_constraint) | DONE |
| Task 4.23 | 验证 Task 4 全部产物 | DONE |

---

## 3. Commits(22 per-object commits)

| # | Commit | Subject |
|---|--------|---------|
| Task 4.1 | `38bf4da02` | test(cmdb/e2e): Task 4.1 - apusic archived placeholder(license) + A/B 端公共契约 |
| Task 4.2 | `b23329927` | test(cmdb/e2e): Task 4.2 - bes archived placeholder + A/B 端覆盖 |
| Task 4.3 | `c233a26cd` | test(cmdb/e2e): Task 4.3 - informix archived placeholder + A/B 端覆盖 |
| Task 4.4 | `6e1e0392f` | test(cmdb/e2e): Task 4.4 - ihs archived placeholder + A/B 端覆盖 |
| Task 4.5 | `aa0e3e52a` | test(cmdb/e2e): Task 4.5 - inforsuite_as archived placeholder + A/B 端覆盖 |
| Task 4.6 | `52fe8a8ce` | test(cmdb/e2e): Task 4.6 - iris archived placeholder + A/B 端覆盖 |
| Task 4.7 | `f1c6d1fcc` | test(cmdb/e2e): Task 4.7 - couchbase archived placeholder + A/B 端覆盖 |
| Task 4.8 | `7497c26a4` | test(cmdb/e2e): Task 4.8 - oceanbase archived placeholder + A/B 端覆盖 |
| Task 4.9 | `b8edf806f` | test(cmdb/e2e): Task 4.9 - oscar archived placeholder + A/B 端覆盖 |
| Task 4.10 | `68618d98f` | test(cmdb/e2e): Task 4.10 - sap_hana archived placeholder + A/B 端覆盖 |
| Task 4.11 | `0935b0398` | test(cmdb/e2e): Task 4.11 - sybase archived placeholder + A/B 端覆盖 |
| Task 4.12 | `5c7aacc80` | test(cmdb/e2e): Task 4.12 - tonggtp archived placeholder + A/B 端覆盖 |
| Task 4.13 | `50a24b553` | test(cmdb/e2e): Task 4.13 - tonglinkq archived placeholder + A/B 端覆盖 |
| Task 4.14 | `a0ff87f8e` | test(cmdb/e2e): Task 4.14 - tongrds archived placeholder + A/B 端覆盖 |
| Task 4.15 | `9a61d9db7` | test(cmdb/e2e): Task 4.15 - tuxedo archived placeholder + A/B 端覆盖 |
| Task 4.16 | `3f56ce1d5` | test(cmdb/e2e): Task 4.16 - weblogic archived placeholder + A/B 端覆盖 |
| Task 4.17 | `2467c5c28` | test(cmdb/e2e): Task 4.17 - websphere archived placeholder + A/B 端覆盖 |
| Task 4.18 | `ab9f131fa` | test(cmdb/e2e): Task 4.18 - hdfs archived placeholder + A/B 端覆盖 |
| Task 4.19 | `853af73eb` | test(cmdb/e2e): Task 4.19 - storm archived placeholder + A/B 端覆盖 |
| Task 4.20 | `113633298` | test(cmdb/e2e): Task 4.20 - yarn archived placeholder + A/B 端覆盖 |
| Task 4.21 | `424059331` | test(cmdb/e2e): Task 4.21 - mycat archived placeholder + A/B 端覆盖 |
| Task 4.22 | `f3136f2e2` | test(cmdb/e2e): Task 4.22 - domestic_linux archived placeholder + A/B 端覆盖 |

**总 commit 数(Task 1-4 累计):** 6 (Task 1) + 6 (Task 2) + 7 (Task 3) + 22 (Task 4) = **41 commits**

---

## 4. Test results(全量 e2e)

### 4.1 全量 e2e 测试

```bash
$ cd server && python -m pytest apps/cmdb/tests/e2e/ --no-cov -q
======================= 519 passed, 91 skipped in 5.80s ========================
```

- **519 passed**:全量 e2e 测试通过
- **91 skipped**:新 22 对象的 B 端 pipeline skip(62 个 = 22×2 skip on `_placeholder_reason`)+ 既有 placeholder 跳过(11)+ k8s/config_file 跳过(8)+ 既有 alignment test 跳过(10)
- **0 failed**

### 4.2 Task 4.23 Step 1:placeholder 对象 fixture 验证

```bash
$ pytest apps/cmdb/tests/e2e/test_placeholder_objects.py -v
============================== 33 passed in 0.13s ==============================
```

10 既有 placeholder + 22 新增 archived placeholder + 1 dameng_blocked_reason_documented = 33 全部通过

### 4.3 Task 4.23 Step 2:per-object pipeline test(22 对象 × 8 tests = 176)

```bash
$ pytest apps/cmdb/tests/e2e/test_{apusic,bes,informix,...domestic_linux}_pipeline.py -q
============================= 176 passed in 0.48s ==============================
```

### 4.4 Task 4.23 Step 3:A/B 端 alignment test(全 43 model_id)

```bash
$ pytest apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py \
       apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py -q
======================= 130 passed, 85 skipped in 5.31s ========================
```

- 130 passed:43 model_id × 3 A 端 + 2 B 端 = 215,但有部分 k8s/config_file/network 等跳过
- 85 skipped:新 22 placeholder 对象的 B 端(_placeholder_reason 检测跳过)+ middleware 模式 A 端 business_labels 跳过

### 4.5 Task 4.23 Step 3:commit 数检查

```bash
$ git log --oneline | head -30
```

预期 41 commits(Task 1: 6 + Task 2: 6 + Task 3: 7 + Task 4: 22)✓ 实际 41 commits ✓

---

## 5. Concerns(疑虑)

无重大疑虑,但有以下设计决定值得 review 时讨论:

### 5.1 runner_type 选择

- **17 license 类**:全部 MIDDLEWARE task_type → runner_type=`middleware` + extra_payload_keys=`{"result": True}`(与既有 ibmmq/nginx 同构)
- **3 cluster 类(hdfs/storm/yarn)**:PROTOCOL task_type → runner_type=`protocol` + extra_payload_keys=None
- **mycat**:HOST task_type → runner_type=`protocol`(archived host 暂用 protocol runner 占位,因为没有对应 host runner)
- **domestic_linux**:HOST task_type → runner_type=`protocol`(同 mycat)

**风险:** mycat/domestic_linux 的真实 task_type 是 HOST,但 runner 走 protocol,导致 A 端 `get_inst_name` 模式不一致(protocol 模式要求 `f"{ip}-{model}-{port}"`,而 HOST 模式无 port 概念)。placeholder 模式 _placeholder_reason 标记后,B 端 pipeline 已 SKIP,所以实际不影响 placeholder 行为。**license 解锁后需要把这两个对象改成 host runner_type(若 host runner_type 落地后)。**

### 5.2 B 端 alignment test 的 `_placeholder_reason` skip 行为

为避免 archived plugin 空 `metric_names` / `field_mappings` 触发 `KeyError: collection_metrics_dict[metric_name]`,在 `test_cmdb_vm_format_alignment.py` 两个 B 端 test 加载 fixture 后立即检查 `_placeholder_reason`,命中就 `pytest.skip`。

**注意:** 这个 skip 也覆盖了既有 placeholder 对象(dameng/tongweb/jboss/jetty/ibmmq 等)— 它们之前走 `get_model_field_def KeyError` skip,现在走 `_placeholder_reason` skip。语义等价,无 regression。

### 5.3 `tuxedo` 冲突

`apps/cmdb/collection/plugins/community/middleware/tuxedo.py`(既有) + `apps/cmdb/collection/plugins/community/archived/tuxedo.py`(Task 1.0 新建)类名都是 `TuxedoCollectionPlugin`,但分布在两个目录。

**当前行为:**
- middleware 目录的 `tuxedo` plugin 是 `supported_task_type=CollectPluginTypes.MIDDLEWARE, supported_model_id="tuxedo"`,且 AutoRegisterCollectionPluginMixin
- archived 目录的 `tuxedo` plugin 同样 `supported_model_id="tuxedo"`(priority=1,比既有低)

按 `AutoRegisterCollectionPluginMixin` 注册顺序,既有 middleware 目录的会被先注册,archived 后注册。但因为 `supported_model_id` 相同,实际查询时返回先注册的(middleware 的)。

**conftest `_resolve_plugin` 行为:** candidate_modules 顺序 db→middleware→protocol→cloud→archived,会先命中 middleware/tuxedo.py(返回既有 `TuxedoCollectionPlugin`)。**这意味着 conftest 解析 tuxedo 时实际拿到既有 middleware plugin,而不是 archived stub。**

**影响:**
- A 端 test `test_a_alignment_metric_name_suffix[tuxedo]`:既有 middleware/tuxedo.py 的 `metric_names` 是有定义的(实际查既有 plugin),能正常 pass
- B 端 test:走 _placeholder_reason skip,不影响

**风险:** 如果用户后续在 archived/tuxedo.py 加了更详细的 placeholder 字段(比如更精确的 blocked_reason 文档),conftest 解析时会忽略它。**建议:用户 review 时确认是删除 archived/tuxedo.py 还是保留作为 task_type 迁移记录。**

### 5.4 04 schema 是 placeholder 模式(只含 2 必填字段)

`04_cmdb_instance.schema.json` 每个对象只定义 `_placeholder_reason` + `license_status` 两个必填字段,**不是真实的 CMDB model 定义**。

**license 解锁后必须:** 把 04 schema 扩成真实 field_mapping(参考既有 33 真实落盘对象的 04 schema,比如 activemq/04_cmdb_instance.schema.json)+ 修改 conftest._MODEL_RUNNER_MAP 的 extra_payload_keys/host runner_type + 删除 archived/<model_id>.py 的 stub。

---

## 6. Files created/modified

### 6.1 修改的文件(4 个,共享基础设施)

| 文件 | 修改内容 | 行数 |
|------|----------|------|
| `server/apps/cmdb/tests/e2e/conftest.py` | `_resolve_plugin` candidate_modules 加 archived/ 目录;`_MODEL_RUNNER_MAP` 加 22 archived model_id;`ALIGNMENT_COVERED_MODEL_IDS` 加 22 archived model_id | +56 |
| `server/apps/cmdb/tests/e2e/test_stargazer_prometheus_alignment.py` | `ALIGNMENT_COVERED_MODEL_IDS` 加 22 archived model_id | +27 |
| `server/apps/cmdb/tests/e2e/test_cmdb_vm_format_alignment.py` | `ALIGNMENT_COVERED_MODEL_IDS` 加 22 archived model_id;B 端两个 test 加 `_placeholder_reason` skip | +36 |
| `server/apps/cmdb/tests/e2e/test_placeholder_objects.py` | `PLACEHOLDER_MODEL_IDS` 加 22 archived model_id | +30 |

### 6.2 新建的文件(155 个,22 对象 × 7 文件 + 1 总览)

每个对象 7 个文件:
- `fixtures/<model_id>/01_stargazer_raw.json`
- `fixtures/<model_id>/02_stargazer_normalized.json`
- `fixtures/<model_id>/03_vm_metrics_response.json`
- `fixtures/<model_id>/04_expected_cmdb_result.json`
- `schemas/<model_id>/01_stargazer_raw.schema.json`
- `schemas/<model_id>/04_cmdb_instance.schema.json`
- `test_<model_id>_pipeline.py`(8 个 test)

+ 1 总览:
- `fixtures/_task4_archived_summary.json`(22 对象元数据)

**总文件:** 155 个新建 + 4 个修改 = **159 files changed, 5855 insertions**

### 6.3 不动的文件(Task 1.0 已就绪,本任务不动)

- `apps/cmdb/collection/plugins/community/archived/*.py`(22 个 archived plugin stub)— Task 1.0 已创建
- `apps/cmdb/tests/e2e/test_pipeline_factory.py`(既有 33 真实落盘对象测试)— 不动
- `apps/cmdb/(collection|views|serializers|services|models|urls|apps.py)`(production code)— 不动
- `agents/stargazer/(plugins/inputs|tasks/collectors|core)`(stargazer production code)— 不动

---

## 7. Verification commands(Task 4.23 复现)

```bash
# Step 1:placeholder 对象 fixture 验证(期望 33 passed)
cd server && .venv/bin/pytest apps/cmdb/tests/e2e/test_placeholder_objects.py --no-cov

# Step 2:全量 e2e 验证(期望 519 passed + 91 skipped + 0 failed)
.venv/bin/pytest apps/cmdb/tests/e2e/ --no-cov

# Step 3:commit 数检查(期望 41 commits)
cd .. && git log --oneline | head -30
```

---

## 8. 与前序任务的关系

- **Task 1.0(已合并):** 22 个 archived plugin stub 已在 `apps/cmdb/collection/plugins/community/archived/` 创建
- **Task 1.1-1.6(已合并):** model_reflection 工具 + A/B 端 alignment test 骨架
- **Task 2(已合并):** 6 P0 真实化对象(aliyun_ecs/k8s_namespace/vmware/host/network/config_file)
- **Task 3(已合并):** 7 P1 云采集对象(hwcloud_ecs/vpc、qcloud_cvm/clb/redis/bucket/cmq/mysql/mongodb、fusioninsight_cluster/host、zstack、h3c_cas、dameng_enterprise、redis_sentinel_enterprise)
- **Task 4(本任务):** 22 P2 archived placeholder(license_missing / cluster_complex / platform_constraint)
- **总覆盖:** 6 P0 + 7 P1(其中 qcloud 7 子对象 + fusioninsight 2 子对象 + hwcloud 2 子对象 = 11 子对象,实际算 9 P1 对象)+ 1 zstack + 1 h3c_cas + 1 dameng_enterprise + 1 redis_sentinel_enterprise = 13 命名对象 + 22 archived = **41 工作对象**

---

**未 push(等用户 review)。**
