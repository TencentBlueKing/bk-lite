# 2026-07-23 告警分派不生效 — `strategy_id=2` `match_rules=[]` 配置错误

> **状态**: 待 review
> **根因**: 策略 `strategy_id=2`(名字"主机")的 `match_rules=[]` 是空规则,导致 process_aggregation 永远 0 命中,告警从未被自动创建
> **影响范围**: 所有 `rule_id="2"` 的告警(用户现场 27 条 UNASSIGNED)都是手工 / 同步数据,不是 system 真实产物

---

## 1. 背景(用户反馈)

用户在 2026-07-23 18:09 提供了一份 API 返回数据,显示 27 条 UNASSIGNED 告警,全部 `rule_id="2"`,全部 `source_name="RESTful"`。

**用户疑问**:正常推送 event + 本机 celery worker + beat 跑,告警被生成了但**自动分派不生效**;手动调 `async_auto_assignment_for_alerts(alert_id)` 能成功分派。

**用户要求**:验证根因,出修复方案。

## 2. 静态 + 动态调研路径(已经走完)

| 步骤 | 工具 | 结论 |
|---|---|---|
| 1. grep 所有写 Alert 表的生产代码 | ripgrep | 只有 3 条路径: `AlertBuilder._create_new_alert`、`SyntheticAlertBuilder.create_alert`、`instant_dispatcher._bulk_build_instant_alerts` |
| 2. 验证 3 条路径是否都被走通 | Django shell ORM 查询 | `ActiveAlertFingerprint` 0 条 → 3 条路径**全都没走通**(因为每条路径必写租约) |
| 3. 验证 outbox 入队 | Django shell ORM 查询 | `AlertOutbox auto_assignment` 0 条 → 跟 0 租约完全自洽 |
| 4. 验证告警真实来源 | 用户贴 27 条 alert API 数据 | 全部 `rule_id="2"` + `source_name="RESTful"` |
| 5. 查 strategy 表 | Django shell ORM 查询 | `strategy_id=2` name="主机" `match_rules=[]` **空规则** |

## 3. 根因(精确)

### 3.1 真正根因

**`strategy_id=2` 的 `match_rules=[]` 是空规则**。

代码位置:`server/apps/alerts/aggregation/processor/aggregation_processor.py:189-191`(`_process_strategy` 处理完事件匹配后):
```python
matched_events = StrategyMatcher.match_events_to_strategy(
    events, cast(List[List[Dict]], strategy.match_rules or [])
)
if not matched_events.exists():
    logger.info("[AlertAggregation] 策略 %s: 无匹配规则的事件", strategy.name)
    self._mark_strategy_executed(strategy, now)
    return
```

`strategy.match_rules or []` → `[]`(空规则)→ `match_events_to_strategy(events, [])` → 0 命中 → return,**不进 `_create_or_update_alerts`**。

### 3.2 现象闭环

| 现象 | 因果 |
|---|---|
| 27 条 UNASSIGNED alert 在 DB | **手工 / 同步数据**,rule_id="2" 是手工填的(标记"想用 strategy_id=2 触发"的意图) |
| `ActiveAlertFingerprint` 0 条 | process_aggregation 跑过 strategy_id=2,但 `match_rules=[]` 直接 return,**不调 `claim_active_fingerprint`** |
| `AlertOutbox auto_assignment` 0 条 | 同上,没有 alert 被 process_aggregation 路径创建,无 outbox 任务 |
| 手动 `async_auto_assignment_for_alerts(alert_id)` 成功 | 分派下游(`AlertAssignmentOperator`)完全 OK,任务函数能跑通;**只是没人自动触发** |
| `strategy_id=1` `match_rules=[{source_id=2, eq}]` | 只匹配 source_id=2(非 RESTful),RESTful event 也不命中 |

### 3.3 排除的假设(全程排查过)

- ❌ **broker 故障**:54 条 PENDING(action/notification)证明 broker OK;auto_assignment kind 0 条不是 broker 问题
- ❌ **`is_new_alert=False` 永远跳过**:旧猜测,推翻
- ❌ **AlertAssignmentOperator 0 命中静默**:用户手动调能成功,排除
- ❌ **`enqueue_outbox` 静默吞异常**:action/notification 入 outbox OK,排除
- ❌ **野生创建路径**:生产代码里只有 3 条 Alert 创建路径,都必走 `claim_active_fingerprint`
- ❌ **代码版本不一致**:本机有 `async_auto_assignment_for_alerts` + outbox 表存在 + 54 条 PENDING 证明代码是新版

## 4. 修复方案

### 4.1 Layer A — 改 strategy_id=2 配置(治本,1 行 SQL / Admin 改)

**目标**:让 `strategy_id=2` 能匹配 host cpu_usage 类 event,process_automation 真实创建 alert。

**方法 A**(推荐,Django Admin):
- 进入告警策略管理 → 找到"主机"策略 → 编辑 `match_rules` 为:

```json
[[
    {"key": "resource_type", "operator": "eq", "value": "host"},
    {"key": "item", "operator": "eq", "value": "cpu_usage"}
]]
```

**方法 B**(SQL):
```sql
UPDATE alerts_alarmstrategy
SET match_rules = '[[{"key": "resource_type", "operator": "eq", "value": "host"}, {"key": "item", "operator": "eq", "value": "cpu_usage"}]]'
WHERE id = 2 AND name = '主机';
```

**验证**:重启 celery beat(或等下一次 beat 跑)+ push 1 个 host cpu_usage event → 应该看到 `ActiveAlertFingerprint` + `AlertOutbox auto_assignment` 各 1 条新记录。

### 4.2 Layer B — 一次性 retry 历史 27 条 UNASSIGNED(补锅)

**目标**:让历史手工 / 同步的 27 条 alert 也被分派。

**新文件**:`server/apps/alerts/management/commands/retry_unassigned_dispatch.py`

```python
from django.core.management.base import BaseCommand
from apps.alerts.models.models import Alert
from apps.alerts.constants.constants import AlertStatus
from apps.alerts.service.alert_lifecycle import dispatch_alert_lifecycle


class Command(BaseCommand):
    help = "对所有 UNASSIGNED 告警手动触发一次 auto_assignment dispatch"

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]
        qs = Alert.objects.filter(status=AlertStatus.UNASSIGNED)
        count = qs.count()
        self.stdout.write(f"找到 {count} 条 UNASSIGNED 告警")
        if dry_run:
            for a in qs[:5]:
                self.stdout.write(f"  干跑: alert_id={a.alert_id} fp={a.fingerprint[:30]}")
            return
        for i in range(0, count, batch_size):
            batch = list(qs[i : i + batch_size].values_list("alert_id", flat=True))
            dispatch_alert_lifecycle(batch, "created", auto_assign=True)
            self.stdout.write(self.style.SUCCESS(f"  入 outbox {len(batch)} 条"))
        self.stdout.write(self.style.SUCCESS("完成"))
```

**使用**:
```bash
python manage.py retry_unassigned_dispatch --dry-run   # 预览
python manage.py retry_unassigned_dispatch            # 实际跑
```

**安全**:`enqueue_outbox` 用 `idempotency_key=sha256(alert_ids)`,重跑幂等;分片 200,避免大批量 outbox 任务。

### 4.3 Layer C — 代码层防再发(治标)

**目标**:即使 `match_rules` 又配错 / 新的野生路径绕过,AlertBuilder 内部也保证入 outbox。

**改动**:`server/apps/alerts/aggregation/builder/alert_builder.py:301-303`

```python
# 改前
transaction.on_commit(
    lambda aid=alert.alert_id: dispatch_alert_lifecycle([aid], "created")
)

# 改后
transaction.on_commit(
    lambda aid=alert.alert_id: dispatch_alert_lifecycle([aid], "created", auto_assign=True)
)
```

**理由**:
- 当前 `_create_new_alert` 内部 `dispatch_alert_lifecycle` 用默认 `auto_assign=False`,**永远不入 outbox**
- 靠 path A(`_schedule_auto_assignment` in `_create_or_update_alerts`)补上
- 但如果 path A 被跳过(老 alert 复用 / `is_new_alert=False`),**整个流程**就不入 outbox
- 改成 `auto_assign=True` 冗余但安全,**`idempotency_key` 防重**(path A 也用同 `idempotency_key`,不会重复)

**注**:`instant_dispatcher._trigger_dispatch_async` 已经传 `auto_assign=True`,本改动只针对 `AlertBuilder._create_new_alert` 主路径。

## 5. 验证计划

### 5.1 Layer A 验证
1. 改 `strategy_id=2.match_rules` 后,重启 celery beat
2. push 1 个 host cpu_usage event 到 RESTful source
3. 等下一次 `event_aggregation_alert` beat 跑(1 分钟内)
4. 查 DB:
   - `ActiveAlertFingerprint` 应该 +1 条(对应新 fingerprint)
   - `AlertOutbox auto_assignment` 应该 +1 条 DELIVERED
5. 查告警:`alert.status` 应该从 `unassigned` → `pending` 或 `processing`(被分派人)

### 5.2 Layer B 验证
```bash
python manage.py retry_unassigned_dispatch --dry-run
python manage.py retry_unassigned_dispatch
```
- 跑前:`AlertOutbox auto_assignment` 0 条
- 跑后:应该有 1 条 outbox 记录(payload.alert_ids 包含 27 个 alert_id)
- 等 1-2 分钟,outbox 状态 `delivered`
- 27 条告警 `operator` 字段非空(被分派人)

### 5.3 Layer C 验证
- 单元测试:`test_alert_builder.py` 新增 case 验证 `_create_new_alert` 调 `dispatch_alert_lifecycle` 时 `auto_assign=True`
- 集成测试:跑 `process_aggregation`,验证 outbox 有 auto_assignment 记录(无论 `is_new_alert` 状态)

## 6. 决策点(请 review)

| # | 决策点 | 我的推荐 | 你的选择 |
|---|---|---|---|
| 1 | Layer A 改 match_rules 用什么规则? | `resource_type=host AND item=cpu_usage`(只匹配 host CPU 类) | ☐ |
| 2 | Layer B management command 立即跑? | **是**(用户现场有 27 条 UNASSIGNED 等待分派) | ☐ |
| 3 | Layer C 代码改动纳入本 PR 还是独立 PR? | 独立 PR(本 PR 聚焦 match_rules 修复,Layer C 改 `AlertBuilder` 风险面更大) | ☐ |
| 4 | Layer C 改 `_create_new_alert` 后,是否会跟 path A(`_schedule_auto_assignment`)重复入 outbox? | **不会**,`idempotency_key` 同 `auto-assignment:created:<sha256>`,`get_or_create` 返回 `created=False` | ☐ |

## 7. 实施步骤

1. **建 worktree**:`git worktree add .worktrees/fix-strategy-match-rules -b fix/strategy-match-rules`
2. **Layer B 写 management command**(纯新增,无破坏性)
3. **Layer B 跑一次**(可选,review 完先跑补锅)
4. **Layer A 改 strategy 配置**(用 Django Admin / SQL,review 完做)
5. **Layer C 改 `_create_new_alert` 内部 dispatch**(独立 commit)
6. **跑测试套**(单元 + 集成)
7. **MR / PR** 走 code review
8. **生产部署** + 监控 `ActiveAlertFingerprint` + `AlertOutbox auto_assignment` 数量

## 8. 风险评估

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| Layer A 改 match_rules 太宽,误命中非 host 类 event | 中 | 中 | 测试 + 灰度 + 监控 `Alert` 创建速率 |
| Layer B management command 入 outbox 失败 | 低 | 中 | `idempotency_key` 防重,可重跑 |
| Layer C 改 `auto_assign=True` 导致重复 dispatch(虽然 `idempotency_key` 防重) | 低 | 低 | `idempotency_key` 保证幂等 |
| 历史 27 条 alert 没有匹配的分派规则,dispatch 跑 0 命中 | 高 | 低 | 现状就这样,retry 只是给个机会,失败不影响 |

## 9. 测试结果(实施后回填)

待实施后回填:
- [ ] Layer A: 改 match_rules + push event → outbox 写入验证
- [ ] Layer B: management command 跑完 → outbox 写入 + 告警 operator 非空
- [ ] Layer C: 单元测试 + 集成测试结果

---

> **Review checklist**:
> 1. 根因 §3 描述是否准确
> 2. 修复方案 §4 三层是否合理
> 3. 验证计划 §5 是否能覆盖所有场景
> 4. 决策点 §6 逐个确认
> 5. 风险评估 §8 是否有遗漏
