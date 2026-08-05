# 2026-07-23 告警 UNASSIGNED 状态不重试分派 — 修复方案

> **状态**: 待 review
> **范围**: P0 主因(aggregation_processor.py)+ P1 兜底(新增 beat 任务)
> **不在范围**: outbox `_schedule_delivery` 静默吞异常(独立 PR)

---

## 1. 背景

告警中心存在一个隐蔽故障:**告警一旦处于 `UNASSIGNED` 状态,后续事件只更新 `last_event_time`,永远不会重新触发自动分派**。

用户在生产环境(2026-07-23)观察到:
- 24h 内 10 条 UNASSIGNED 告警,`operator` 字段全部为空
- `AlertOutbox` 表里 `kind='auto_assignment'` 记录数为 **0**

## 2. 根因分析

代码:`server/apps/alerts/aggregation/processor/aggregation_processor.py:580-595`

```python
is_new_alert = not self._is_existing_alert(fingerprint)   # 用 fingerprint + ACTIVE 状态判断

alert = AlertBuilder.create_or_update_alert(...)

if is_new_alert:                                            # ← 关键判断
    should_delay_assignment = ...
    if should_delay_assignment:
        ...
    else:
        new_alert_ids.append(alert.alert_id)               # ← 只有这条路进入 outbox
```

`_is_existing_alert` (line 686-688) 定义:

```python
return Alert.objects.filter(
    fingerprint=fingerprint,
    status__in=AlertStatus.ACTIVATE_STATUS,    # (PENDING, PROCESSING, UNASSIGNED)
).exists()
```

**死亡序列**:

```
T0  第一次事件 → DB 无告警 → is_new_alert=True
    → new_alert_ids.append(alert_id)
    → enqueue_outbox("auto_assignment", ...)
    → 任务执行但 AlertAssignmentOperator 0 命中(规则不匹配 / FIELD_MAPPING 错 / 其他)
    → 告警停留在 UNASSIGNED

T1  同 fingerprint 第二次事件 → DB 有 UNASSIGNED 告警
    → is_new_alert=False
    → 不加入 new_alert_ids
    → 不调 _schedule_auto_assignment
    → 告警永远 UNASSIGNED,不再有人来分派
```

## 3. 修复目标

**让任何 `status=UNASSIGNED` 的告警,在有事件流入时,都进入自动分派链路;并补一个 beat 兜底任务清历史沉积**。

成功标准:

| 指标 | 当前 | 目标 |
|---|---|---|
| UNASSIGNED 告警 `operator` 为空比例 | 10/10 (100%) | < 5% |
| UNASSIGNED 告警寿命 | 永久 | < 5 分钟(下次聚合) |
| 24h 内 `auto_assignment` outbox 任务数 | 0 | 与新事件量正相关 |
| 历史 UNASSIGNED 残留 | 10 条(24h) | 修复后 1 小时内 < 2 条 |

## 4. 详细改动(决策点 ⭐ 标出)

### 4.1 P0 主因 — 改 `aggregation_processor.py:580-595`

```python
# 改前
if is_new_alert:
    should_delay_assignment = (
        alert.is_session_alert
        and alert.session_status == SessionStatus.OBSERVING
    )
    if should_delay_assignment:
        logger.info(...)
    else:
        new_alert_ids.append(alert.alert_id)

# 改后
needs_assignment = is_new_alert or alert.status == AlertStatus.UNASSIGNED
if needs_assignment:
    should_delay_assignment = (
        alert.is_session_alert
        and alert.session_status == SessionStatus.OBSERVING
    )
    if should_delay_assignment:
        logger.info(...)
    else:
        new_alert_ids.append(alert.alert_id)
```

**新增日志**(可观测性):

```python
if alert.status == AlertStatus.UNASSIGNED and not is_new_alert:
    logger.info(
        "[AlertAggregation] 已有 UNASSIGNED 告警收到新事件,触发重试分派: alert_id=%s",
        alert.alert_id,
    )
```

### ⭐ 决策点 1:`needs_assignment` 判定时机

当前是 `AlertBuilder.create_or_update_alert` 之后(在 `with transaction.atomic():` 块内),`alert.status` 是写库后值。

**风险**:`create_or_update_alert` 内部是否会改 `status`?如果它把 `UNASSIGNED` 改成 `PENDING` 或其他,我们的判断会失效。

**需要 review 时确认**:
- 读 `aggregation/builder/alert_builder.py` 的 `create_or_update_alert` 全文,确认 `status` 字段不会被改
- 如果会改,需要先 `refresh_from_db()` 再读 `status`,或改用 `result` 里的 flag

### 4.2 P1 兜底 — 新增 beat 任务 `beat_retry_unassigned_assignment`

新文件追加(放 `server/apps/alerts/tasks/tasks.py`):

```python
UNASSIGNED_RETRY_BATCH = 200   # 与 AUTO_ASSIGNMENT_CHUNK_SIZE 对齐


@shared_task
def beat_retry_unassigned_assignment():
    """兜底:扫历史 UNASSIGNED 告警,重新入 auto_assignment outbox。

    每 5 分钟跑一次。配合 idempotency_key 防重。
    不影响主链路(beat_unassigned_assignment 失败只记日志)。
    """
    now = timezone.now()
    candidate_ids = list(
        Alert.objects.filter(
            status=AlertStatus.UNASSIGNED,
        )
        .exclude(
            is_session_alert=True,
            session_status__in=SessionStatus.OBSERVING,  # 观察期会话告警不算
        )
        .order_by("created_at")
        .values_list("alert_id", flat=True)[:UNASSIGNED_RETRY_BATCH]
    )

    if not candidate_ids:
        logger.info("[AlertTask] UNASSIGNED 兜底: 无候选告警")
        return {"retried": 0}

    digest = hashlib.sha256("\0".join(sorted(candidate_ids)).encode("utf-8")).hexdigest()
    from apps.alerts.service.outbox import enqueue_outbox

    enqueue_outbox(
        "auto_assignment",
        {"alert_ids": candidate_ids},
        f"auto-assignment:retry-unassigned:{digest}",
    )

    logger.info(
        "[AlertTask] UNASSIGNED 兜底: 入 outbox %s 条 (digest=%s...)",
        len(candidate_ids),
        digest[:8],
    )
    return {"retried": len(candidate_ids)}
```

调度追加(放 `server/apps/alerts/config.py` 的 `CELERY_BEAT_SCHEDULE`):

```python
"beat_retry_unassigned_assignment": {
    "task": "apps.alerts.tasks.tasks.beat_retry_unassigned_assignment",
    "schedule": crontab(minute="*/5"),
},
```

`tasks/__init__.py` 加导出:

```python
from .tasks import (
    # ... 现有导出
    beat_retry_unassigned_assignment,
)
```

### ⭐ 决策点 2:兜底频率 5 分钟 vs 1 分钟 vs 10 分钟

- **5 分钟**(推荐):跟"UNASSIGNED 告警寿命 < 5 分钟"目标对齐;不会对 DB 造成持续压力
- **1 分钟**:更激进,但每分钟扫 200 条 Alert + 写 1 条 outbox,可能跟 `event_aggregation_alert` 抢资源
- **10 分钟**:更轻,但 UNASSIGNED 告警寿命会到 10 分钟,跟目标 5 分钟不一致

### ⭐ 决策点 3:候选告警是否包含会话观察期

- 排除(`exclude(is_session_alert=True, session_status=OBSERVING)`):推荐,与会话告警的"超时确认再分派"语义一致
- 包含:会让会话告警的"观察期"语义失效,可能跟策略冲突

### ⭐ 决策点 4:候选告警是否包含 `is_session_alert=True` 且 `session_status=CONFIRMED`

- 这些告警:会话超时已转 CONFIRMED,应该分派了
- 排除:让主链路(超时检查)负责,避免双触发
- 包含:兜底也处理这类,保证不漏

我倾向**排除**(`is_session_alert=True` 整段排除),让会话告警完全由 `TimeoutChecker` 路径管。

### ⭐ 决策点 5:候选告警范围上限

`UNASSIGNED_RETRY_BATCH = 200` 跟 `AUTO_ASSIGNMENT_CHUNK_SIZE` 对齐,但兜底场景下如果积累 1000+ 条 UNASSIGNED,5 分钟只能清 200 条。

- 选 200:稳妥,不会对 DB 造成压力
- 选 500:激进,如果 outbox 任务跑得过来可以试
- 选 1000:激进 + 依赖 outbox 任务能并发处理

## 5. 测试策略

### 5.1 单元测试(`tests/test_aggregation_processor.py` 新增)

```python
def test_existing_unassigned_alert_gets_retried_on_new_event(source, strategy):
    """已有 UNASSIGNED 告警收到新事件时,必须重新入 auto_assignment outbox"""
    # 1. 创建已存在的 UNASSIGNED 告警
    Alert.objects.create(
        alert_id="A-EXISTING", fingerprint="fp-same",
        status="unassigned", level="1", title="t", content="c", team=[1],
    )
    # 2. 跑一次 process_aggregation 触发首次入 outbox
    with patch("apps.alerts.aggregation.processor.aggregation_processor._schedule_auto_assignment") as sched:
        AggregationProcessor().process_aggregation()
    # 3. 模拟 outbox 任务执行完(但分派 0 命中),告警还是 UNASSIGNED
    Alert.objects.filter(alert_id="A-EXISTING").update(operator=[])  # 保持 UNASSIGNED

    # 4. 模拟新事件
    Event.objects.create(source=source, fingerprint="fp-same", action="created", ...)

    # 5. 跑 process_aggregation
    with patch("apps.alerts.aggregation.processor.aggregation_processor._schedule_auto_assignment") as sched2:
        AggregationProcessor().process_aggregation()

    # 6. 验证 _schedule_auto_assignment 第二次也被调,且包含 A-EXISTING
    assert sched2.called
    assert "A-EXISTING" in sched2.call_args[0][0]


def test_pending_alert_does_not_re_trigger_assignment(source, strategy):
    """已分派(PENDING/PROCESSING)的告警不应再次入 outbox"""
    Alert.objects.create(
        alert_id="A-PENDING", fingerprint="fp-2",
        status="pending", level="1", title="t", content="c", team=[1],
    )
    Event.objects.create(source=source, fingerprint="fp-2", action="created", ...)

    with patch("apps.alerts.aggregation.processor.aggregation_processor._schedule_auto_assignment") as sched:
        AggregationProcessor().process_aggregation()

    assert not sched.called


def test_session_observation_alert_skips_retry(source, strategy):
    """观察期(OBSERVING)会话告警不触发重试"""
    Alert.objects.create(
        alert_id="A-SESS", fingerprint="fp-3",
        status="unassigned", is_session_alert=True,
        session_status="observing", session_end_time=...,
        level="1", title="t", content="c", team=[1],
    )
    Event.objects.create(source=source, fingerprint="fp-3", action="created", ...)

    with patch("apps.alerts.aggregation.processor.aggregation_processor._schedule_auto_assignment") as sched:
        AggregationProcessor().process_aggregation()

    # 观察期告警应该延迟分派,不入 outbox
    args = sched.call_args[0][0] if sched.called else []
    assert "A-SESS" not in args
```

### 5.2 兜底任务测试

```python
def test_beat_retry_unassigned_assignment_enqueues_unassigned_alerts():
    """beat 兜底任务必须入 outbox 所有未分派告警"""
    Alert.objects.create(alert_id="A-1", status="unassigned", ...)
    Alert.objects.create(alert_id="A-2", status="unassigned", ...)
    Alert.objects.create(alert_id="A-3", status="pending", ...)   # 不该入

    beat_retry_unassigned_assignment()

    record = AlertOutbox.objects.get(kind="auto_assignment")
    assert "A-1" in record.payload["alert_ids"]
    assert "A-2" in record.payload["alert_ids"]
    assert "A-3" not in record.payload["alert_ids"]


def test_beat_retry_skips_observation_alerts():
    """观察期会话告警被排除"""
    Alert.objects.create(alert_id="A-OBS", status="unassigned",
                        is_session_alert=True, session_status="observing", ...)
    Alert.objects.create(alert_id="A-NORM", status="unassigned", ...)

    beat_retry_unassigned_assignment()

    record = AlertOutbox.objects.get(kind="auto_assignment")
    assert "A-OBS" not in record.payload["alert_ids"]
    assert "A-NORM" in record.payload["alert_ids"]


def test_beat_retry_is_idempotent():
    """idempotency_key 保证重跑不产生重复 outbox 记录"""
    Alert.objects.create(alert_id="A-1", status="unassigned", ...)

    beat_retry_unassigned_assignment()
    beat_retry_unassigned_assignment()

    assert AlertOutbox.objects.filter(kind="auto_assignment").count() == 1


def test_beat_retry_respects_batch_limit():
    """批次上限 UNASSIGNED_RETRY_BATCH"""
    from apps.alerts.tasks.tasks import UNASSIGNED_RETRY_BATCH
    for i in range(UNASSIGNED_RETRY_BATCH + 5):
        Alert.objects.create(alert_id=f"A-{i}", status="unassigned", ...)

    result = beat_retry_unassigned_assignment()

    assert result["retried"] == UNASSIGNED_RETRY_BATCH
    record = AlertOutbox.objects.get(kind="auto_assignment")
    assert len(record.payload["alert_ids"]) == UNASSIGNED_RETRY_BATCH
```

### 5.3 集成测试(`tests/bdd/test_assignment_bdd.py` 新增场景)

```gherkin
场景:已有 UNASSIGNED 告警收到新事件,会被分派人
  假设 存在 1 条 UNASSIGNED 告警 A-1
  并且 存在 1 条分派规则(全部匹配)
  当 同一 fingerprint 的新事件到达
  那么 告警 A-1 应该被分派人
  并且 operator 字段非空

场景:UNASSIGNED 告警没有任何匹配规则
  假设 存在 1 条 UNASSIGNED 告警 A-1
  并且 没有匹配的分派规则
  当 beat_retry_unassigned_assignment 跑过
  那么 AlertOutbox 应该被写入
  并且 分派任务的 assigned_alerts=0
  并且 系统发未分派通知(不报错)
```

### 5.4 回归测试

跑完整测试套,重点关注:

- `tests/test_aggregation_processor.py`
- `tests/test_assignment.py`
- `tests/test_repro_filter_assignment.py`(FIELD_MAPPING 修复回归)
- `tests/test_bdd/test_assignment_bdd.py`
- `tests/test_timeout_checker.py`(会话超时路径)

## 6. 回滚方案

每个改动都在独立文件 / 函数里:

| 改动 | 文件 | 回滚方式 |
|---|---|---|
| 主因修复 | `aggregation_processor.py:580-595` | git revert 1 个 commit |
| 兜底任务 | `tasks/tasks.py` 新增函数 | 删函数 + 从 `tasks/__init__.py` 移除 |
| 调度 | `config.py` 删 1 条 | 删 1 条 CELERY_BEAT_SCHEDULE |

无 schema 变更,无需数据迁移。

## 7. 风险评估

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| P0 修改引入"重复分派"(同一告警分派多次) | 低 | 中 | `AlertAssignmentOperator` 已有 `assigned_alert_ids` 集合 + `assigned` 状态过滤 |
| P0 修改触发历史 UNASSIGNED 一次性大批量入 outbox | 中 | 中 | 第一次 beat 后会清,后续稳态是"新事件才入" |
| 兜底任务跟 `event_aggregation_alert` 同时跑,资源争抢 | 低 | 低 | 不同任务,celery 多 worker 各自跑;idempotency_key 防重 |
| `AlertBuilder.create_or_update_alert` 改 status 导致判断失效 | **待确认** | 高 | **决策点 1**:review 时先读 alert_builder 全文 |
| 兜底任务积累告警太多,5 分钟清不完 | 低 | 中 | 监控 outbox 入队量;`UNASSIGNED_RETRY_BATCH` 可调 |

## 8. 实施步骤

1. **建 worktree**(按 AGENTS.md worktree 规则)
   - `git worktree add .worktrees/fix-unassigned-retry -b fix/alert-unassigned-retry`
2. **改 `aggregation_processor.py`**
   - 替换 `is_new_alert` 判断
   - 加 INFO 日志
3. **加 beat 任务**
   - `tasks/tasks.py` 加函数
   - `tasks/__init__.py` 加导出
   - `config.py` 加调度
4. **写单元测试 + 集成测试**
5. **跑测试套**(全量 + 目标测试)
6. **记录测试结果**(回填到本文档 §9)
7. **MR / 提 PR** 走 code review
8. **合并后清理 worktree**

## 9. 测试结果(实施后回填)

2026-07-24 P0 主因修复已实施(TDD):

- 失败测试先行:`test_existing_unassigned_alert_retried_on_new_event` 按预期失败
  (AssertionError: 存量 UNASSIGNED 告警收到新事件后未重新触发自动分派)
- 最小修复:`aggregation_processor.py` `is_new_alert` 门控 →
  `needs_assignment = is_new_alert or alert.status == UNASSIGNED`,会话观察期延迟逻辑不变
- 修复后验证:
  - [x] 新增 3 测试通过(UNASSIGNED 重试 / PENDING 不重试 / 会话观察期不触发)
  - [x] 回归 54 通过(test_aggregation_processor / test_assignment /
        test_repro_filter_assignment / test_timeout_checker)
  - [x] BDD 43 通过(tests/bdd 全量)
- [x] P1 兜底 beat 任务已实施(2026-07-24):beat_retry_unassigned_assignment,
      5 分钟周期 / 批次 200 / 会话告警整段排除;新增 test_beat_retry_unassigned.py 4 测试通过
- [x] 附带修复(同日,TDD):
      1) 分派调度异常隔离(_schedule_auto_assignment 独立 try,不再拖垮整轮聚合)
      2) outbox 卡死 DELIVERING 行纳入 dispatch_pending_alert_outbox 重投(5 分钟去重窗口)
- [x] alerts 全量 1030 通过;唯一失败 test_nats_handlers::...distribution 已验证为
      干净 HEAD 基线失败,与本次改动无关
- [ ] 历史 UNASSIGNED 存量由 beat_retry_unassigned_assignment 上线后自动清理(不做手工数据清理)
- [ ] 生产环境部署后 24h 监控数据(UNASSIGNED 告警数 / auto_assignment outbox 任务数)

## 10. 后续(独立 PR,不在本次范围)

- **P2 outbox 静默吞异常**:`outbox.py:14-19` `_schedule_delivery` 失败时写 FAILED + 设 next_retry_at,让 54 条 PENDING 类问题不再死循环
- **P1 监控**:`AlertAssignmentOperator` 0 命中时记 ERROR 日志 + 发告警
- **P2 历史 54 条 PENDING 清理 SQL**:独立工单

## 11. 决策点待 review

| # | 决策点 | 我的推荐 | 你确认 |
|---|---|---|---|
| 1 | `needs_assignment` 判定时机(读 `alert_builder.py` 确认 status 不被改) | 在 `create_or_update_alert` 后读 `alert.status` | ☐ |
| 2 | 兜底频率 | 5 分钟 | ☐ |
| 3 | 候选告警是否包含会话观察期 | 排除 | ☐ |
| 4 | 候选告警是否包含 `is_session_alert=True` | 全部排除 | ☐ |
| 5 | 批次上限 | 200 | ☐ |

---

> **Review checklist**:
> 1. §4.1 改动是否合理(逻辑 + 日志)
> 2. §4.2 兜底任务的 batch / 频率 / 排除条件
> 3. §5 测试覆盖是否够(主因 / 兜底 / 集成 / 回归)
> 4. §7 风险评估是否有遗漏
> 5. §11 5 个决策点逐个确认
