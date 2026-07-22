# 告警中心-相关性规则新增即时告警类型 Tech Plan（2026-06-03）

Status: cancelled

> Migrated from `spec/tech_plan/告警中心/20260531.告警中心-相关性规则新增即时告警类型.md` as historical change evidence.

需求文档：[spec/requirements/告警中心/20260531.告警中心-相关性规则新增即时告警类型.md](../../requirements/告警中心/20260531.告警中心-相关性规则新增即时告警类型.md)
方案文档：[spec/solution_plan/告警中心/20260531.告警中心-相关性规则新增即时告警类型.md](../../solution_plan/告警中心/20260531.告警中心-相关性规则新增即时告警类型.md)

技术目标：在现有相关性规则体系内新增 `instant` 策略类型，复用现有 `AlarmStrategy` / `Alert` 模型、`AlertSourceAdapter` 入口、`async_auto_assignment_for_alerts` 分派任务，完成"事件命中 → 立即落 Alert → 异步分派"的瞬时通路。
非目标：不新增 Alert 字段、不引入自动关闭策略、不改写智能降噪聚合逻辑、不新增菜单或独立 API。
影响范围：仅改动告警中心入库链路、聚合管线策略筛选、自动关闭过滤；前端改动限定在相关性规则配置/列表/详情。边界限定在 `server/apps/alerts` 和 `web/src/app/alarm`。

## 1. 文件与目录结构

```text
server/apps/alerts/
├── aggregation/
│   ├── processor/
│   │   ├── aggregation_processor.py          # 修改：_get_active_strategies 排除 INSTANT
│   │   └── instant_dispatcher.py             # 新增：旁路调度入口
│   └── strategy/
│       ├── matcher.py                         # 不动（仅参考）
│       └── instant_matcher.py                 # 新增：内存匹配器
├── common/
│   └── source_adapter/
│       └── base.py                            # 修改：main() 注入旁路调用
├── constants/
│   └── constants.py                           # 修改：AlarmStrategyType.INSTANT
├── migrations/
│   └── <auto>_alter_alarmstrategy_strategy_type.py  # 新增：alter-choices
├── serializers/
│   └── strategy.py                            # 修改:增加 INSTANT 校验分支 + cache 失效钩子
├── tasks/
│   └── tasks.py                               # 修改:beat_close_alert 排除 INSTANT；新增 build_instant_alerts
└── test/
    ├── test_instant_matcher.py                # 新增
    ├── test_instant_dispatcher.py             # 新增
    ├── test_instant_alert_pipeline.py         # 新增（集成）
    └── test_strategy_serializer.py            # 修改：增加 INSTANT 校验用例

web/src/app/alarm/
├── (pages)/settings/correlationRules/components/
│   ├── operateModal.tsx                       # 修改：类型分支显隐
│   ├── list.tsx                               # 修改：类型列与筛选项
│   └── detail.tsx                             # 修改：类型展示与字段显隐
├── constants/
│   └── settings.ts                            # 修改：新增 INSTANT 常量
└── types/
    └── settings.ts                            # 修改：扩展类型联合
```

改动范围说明：
- 后端只新增"旁路调度 + 内存匹配 + Celery 兜底任务"，不改 Alert/Event 模型，不动现有 AlertBuilder 字段映射主干。
- 前端只处理类型分支显隐与文案，不动列表渲染、操作组件、通知设置。
- 不改动告警源、通知渠道、外部接口。

## 2. 核心数据结构 / Schema 定义

```python
# server/apps/alerts/constants/constants.py
class AlarmStrategyType:
    SMART_DENOISE = "smart_denoise"
    MISSING_DETECTION = "missing_detection"
    INSTANT = "instant"                       # NEW

    CHOICES = (
        (SMART_DENOISE, "智能降噪"),
        (MISSING_DETECTION, "缺失检测"),
        (INSTANT, "即时告警"),                  # NEW
    )

# 旁路同步/异步降级阈值
INSTANT_SYNC_THRESHOLD = 50
# 单次 dispatch 命中上限（防异常事件源刷爆）
INSTANT_HIT_CEILING = 5000
# 策略缓存 TTL（秒）
INSTANT_STRATEGY_CACHE_TTL = 60
```

```python
# server/apps/alerts/aggregation/processor/instant_dispatcher.py
from dataclasses import dataclass

@dataclass(slots=True)
class InstantHit:
    """单条命中记录：(策略 id, 事件 id)"""
    strategy_id: int
    event_id: str

@dataclass(slots=True)
class InstantAlertTemplate:
    """存于 AlarmStrategy.params['alert_template']，三字段全部由用户配置且必填。"""
    title: str
    level: str | None    # 可空则继承 event.level；非空时仍以 event.level 为准（PRD 规定）
    description: str
```

```python
# AlarmStrategy.params 在 strategy_type == INSTANT 时的结构
{
    "alert_template": {
        "title": "<用户配置文案 / 支持模板变量>",
        "description": "<用户配置文案 / 支持模板变量>"
    }
}
```

```typescript
// web/src/app/alarm/types/settings.ts
export type StrategyType = 'smart_denoise' | 'missing_detection' | 'instant';

export interface InstantAlertTemplate {
  title: string;
  description: string;
}

export interface InstantStrategyParams {
  alert_template: InstantAlertTemplate;
}
```

规则口径：
- INSTANT 策略**不新增模型字段**，所有配置收敛到 `match_rules` 与 `params.alert_template`。
- `Alert.fingerprint = md5(f"instant:{strategy_id}:{event_id}")`，与聚合指纹命名空间完全隔离。
- `Alert.event_count = 1`，恒定。
- `Alert.level = event.level`，强制继承事件级别（不读 `alert_template.level`）。
- `Alert.rule_id = str(strategy.id)`，`Alert.group_by_field = "instant"`。
- `Alert.team = strategy.dispatch_team`。
- Alert↔Event M2M 关联同样写入（`Alert.events.add(event)` 等价物，通过 `through.objects.bulk_create`）。

## 3. 核心函数 / 接口签名

```python
# server/apps/alerts/aggregation/strategy/instant_matcher.py
from typing import Any
from apps.alerts.models.models import Event

class InstantMatcher:
    """内存版匹配器。语义与 StrategyMatcher 完全一致；区别在于作用于 Python 对象属性，零 DB 查询。"""

    @staticmethod
    def match_in_memory(event: Event, match_rules: list[list[dict]]) -> bool:
        """单事件 × 单策略 match_rules 命中判断。外层 OR，内层 AND；规则空返回 False。"""

    @staticmethod
    def _eval_condition(event: Event, condition: dict) -> bool:
        """单条件评估，操作符与 StrategyMatcher.OPERATOR_MAP 一一对应。"""

    @staticmethod
    def _get_field_value(event: Event, key: str) -> Any:
        """字段取值：先查 FIELD_MAP 映射，再依次从 event 属性 / event.labels / event.tags 取值。"""
```

```python
# server/apps/alerts/aggregation/processor/instant_dispatcher.py
from datetime import datetime
from typing import Iterable
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.models import Alert, Event

class InstantStrategyCache:
    """active INSTANT 策略的进程内 TTL 缓存。"""

    @classmethod
    def get(cls) -> list[AlarmStrategy]:
        """命中缓存返回；未命中或过期则查 DB 并回填。"""

    @classmethod
    def cache_clear(cls) -> None:
        """主动失效。Strategy serializer save 钩子里调用。"""

class InstantAlertDispatcher:
    """旁路调度入口。在 AlertSourceAdapter.main() 内 create_events 之后被调用。"""

    @staticmethod
    def dispatch(bulk_events: list[list[Event]]) -> None:
        """
        主入口。捕获自身全部异常，不向上抛。
        步骤：取缓存 → 内存匹配 → 命中数 ≤ 阈值同步落库，> 阈值入 Celery 队列。
        """

    @staticmethod
    def _collect_hits(events: list[Event], strategies: list[AlarmStrategy]) -> list[InstantHit]:
        """双层循环匹配，返回命中列表。超过 INSTANT_HIT_CEILING 时截断并 ERROR 日志。"""

def _bulk_build_instant_alerts(hits: list[InstantHit]) -> list[str]:
    """
    按 strategy_id 分桶 bulk_create Alert + M2M。
    返回新建 alert_id 列表（已存在的 fingerprint 因 ignore_conflicts 被跳过，不进列表）。
    供同步路径与 Celery 任务共用。
    """

def _build_fingerprint(strategy_id: int, event_id: str) -> str:
    """md5(f'instant:{strategy_id}:{event_id}')。"""

def _build_alert_row(strategy: AlarmStrategy, event: Event, fingerprint: str) -> Alert:
    """字段映射：复用现有 Alert 模型字段，从 event 取原始文案与级别。"""

def _trigger_dispatch_async(alert_ids: list[str]) -> None:
    """current_app.send_task('async_auto_assignment_for_alerts', args=[alert_ids])。"""
```

```python
# server/apps/alerts/tasks/tasks.py
@shared_task(queue="instant_alerts", autoretry_for=(Exception,),
             retry_backoff=True, retry_kwargs={"max_retries": 3})
def build_instant_alerts(hits_payload: list[dict]) -> None:
    """
    异步兜底任务。仅在 dispatch 阶段命中数 > INSTANT_SYNC_THRESHOLD 时调用。
    hits_payload 是 [{"strategy_id": int, "event_id": str}, ...] 的可序列化形态。
    """

# 修改现有任务
def beat_close_alert() -> None:
    """
    保持原行为，仅在 Alert 查询条件中追加：
        .exclude(strategy__strategy_type=AlarmStrategyType.INSTANT)
    """
```

```python
# server/apps/alerts/aggregation/processor/aggregation_processor.py
class AggregationProcessor:
    def _get_active_strategies(self) -> QuerySet[AlarmStrategy]:
        """
        现状返回 is_active=True 的策略集合。
        修改：追加 .exclude(strategy_type=AlarmStrategyType.INSTANT)，
        保证聚合管线永不处理 INSTANT 策略。
        """
```

```python
# server/apps/alerts/common/source_adapter/base.py
class AlertSourceAdapter:
    def main(self, events=None) -> None:
        """
        在 self.event_operator(bulk_events) 调用之前插入：
            try:
                InstantAlertDispatcher.dispatch(bulk_events)
            except Exception:
                logger.exception("instant dispatch failed; continue main pipeline")
        旁路失败绝不阻断现有主流程。
        """
```

```python
# server/apps/alerts/serializers/strategy.py
class AlarmStrategySerializer(serializers.ModelSerializer):
    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """根据 strategy_type 分派校验：existing | _validate_instant。"""

    def _validate_instant(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """
        - match_rules 必须非空且至少一条有效条件
        - 拒绝等价于 ALL 的空规则
        - params['alert_template']['title'] 必填
        - params['alert_template']['description'] 必填
        - 静默清理 params 中的 window_size / group_by / aggregation_* 等聚合字段
        """

    def save(self, **kwargs):
        """保存成功后调用 InstantStrategyCache.cache_clear()。"""
```

```typescript
// web/src/app/alarm/(pages)/settings/correlationRules/components/operateModal.tsx
function isInstantStrategy(values: FormValues): boolean;
function normalizeInstantValues(rule?: CorrelationRule): FormValues;
function buildInstantPayload(values: FormValues): CorrelationRule;
```

## 4. 核心逻辑伪代码

### 4.1 旁路注入与调度

```text
AlertSourceAdapter.main(events):
1. bulk_events = self.create_events(events)         # 已有
2. if not bulk_events: return                       # 已有
3. self.event_operator(bulk_events)                 # 已有
4. self.handle_recovery_events(bulk_events)         # 已有
5. try:
       InstantAlertDispatcher.dispatch(bulk_events) # 新增（位置：在 create_events 之后即可，
                                                    # 与 event_operator 并列；失败被旁路自身吞掉）
   except Exception:
       logger.exception("instant dispatch failed")
```

```text
InstantAlertDispatcher.dispatch(bulk_events):
1. strategies = InstantStrategyCache.get()
   若 strategies 为空：return
2. events = [e for batch in bulk_events for e in batch if e.action == EventAction.CREATED]
   若 events 为空：return
3. hits = _collect_hits(events, strategies)
   若 hits 为空：return
4. if len(hits) <= INSTANT_SYNC_THRESHOLD:
       alert_ids = _bulk_build_instant_alerts(hits)
       if alert_ids: _trigger_dispatch_async(alert_ids)
   else:
       payload = [{"strategy_id": h.strategy_id, "event_id": h.event_id} for h in hits]
       current_app.send_task("build_instant_alerts", args=[payload])
```

```text
InstantAlertDispatcher._collect_hits(events, strategies):
1. hits = []
2. for event in events:
       for strategy in strategies:
           if InstantMatcher.match_in_memory(event, strategy.match_rules):
               hits.append(InstantHit(strategy.id, event.event_id))
               if len(hits) >= INSTANT_HIT_CEILING:
                   logger.error("instant hits truncated at ceiling=%s", INSTANT_HIT_CEILING)
                   return hits
3. return hits
```

### 4.2 命中转 Alert（同步 / 异步共用）

```text
_bulk_build_instant_alerts(hits):
1. all_sids = {h.strategy_id for h in hits}
   all_eids = {h.event_id for h in hits}
2. strategies = AlarmStrategy.objects.in_bulk(all_sids)
   events = {e.event_id: e for e in Event.objects.filter(event_id__in=all_eids)}
3. by_sid = defaultdict(list)
   for h in hits:
       by_sid[h.strategy_id].append(events[h.event_id])
4. created_alert_ids = []
   for sid, evt_list in by_sid.items():
       strategy = strategies[sid]
       alerts = [
           _build_alert_row(strategy, evt, _build_fingerprint(sid, evt.event_id))
           for evt in evt_list
       ]
       with transaction.atomic():
           Alert.objects.bulk_create(alerts, ignore_conflicts=True)
           # bulk_create 后 alerts 中实例 pk 是否回填依赖 DB；为兼容 MySQL，重新查询
           created = list(
               Alert.objects.filter(fingerprint__in=[a.fingerprint for a in alerts])
                            .values_list("id", "alert_id", "fingerprint")
           )
           fp_to_alert = {fp: (pk, aid) for pk, aid, fp in created}
           m2m_rows = []
           for evt in evt_list:
               fp = _build_fingerprint(sid, evt.event_id)
               if fp in fp_to_alert:
                   alert_pk, alert_id = fp_to_alert[fp]
                   m2m_rows.append(Alert.events.through(alert_id=alert_pk, event_id=evt.id))
                   created_alert_ids.append(alert_id)
           Alert.events.through.objects.bulk_create(m2m_rows, ignore_conflicts=True)
5. return created_alert_ids
```

```text
_build_alert_row(strategy, event, fingerprint):
return Alert(
    alert_id="ALERT-" + uuid4().hex,
    fingerprint=fingerprint,
    rule_id=str(strategy.id),
    group_by_field="instant",
    status=AlertStatus.UNASSIGNED,
    level=event.level,                          # PRD: 继承事件级别
    title=event.title,                          # 用户可在前端为 INSTANT 配置 alert_template.title
                                                # 渲染逻辑由 _build_alert_row 内的 render_template 处理（见 4.3）
    content=event.description,
    first_event_time=event.received_at,
    last_event_time=event.received_at,
    event_count=1,
    team=strategy.dispatch_team,
    source_id=event.source_id,
    resource_id=event.resource_id,
    resource_name=event.resource_name,
    resource_type=event.resource_type,
    service=event.service,
    item=event.item,
    location=event.location,
)
```

### 4.3 告警模板渲染

```text
若 strategy.params['alert_template']['title'] 非空:
    title = render_template(template_title, context_from_event)
    description = render_template(template_description, context_from_event)
否则:
    title = event.title
    description = event.description

context_from_event 提供变量：service / location / resource_name / resource_id /
                              resource_type / item / title / level / external_id
```

未提供 template 时直接复用 event 原始文案，保证"原汁原味"诉求。

### 4.4 策略缓存

```text
InstantStrategyCache.get():
1. now = monotonic()
2. if cached and now - cached_at < INSTANT_STRATEGY_CACHE_TTL:
       return cached_value
3. value = list(
       AlarmStrategy.objects.filter(
           is_active=True,
           strategy_type=AlarmStrategyType.INSTANT,
       )
   )
4. cached_value, cached_at = value, now
5. return value

InstantStrategyCache.cache_clear():
1. cached_value = None
2. cached_at = 0
```

注意：进程内缓存，多 worker 间最坏 60s 窗口不一致；可接受（策略变更非高频，TTL 已较短）。

### 4.5 异步兜底任务

```text
build_instant_alerts(hits_payload):
1. hits = [InstantHit(p["strategy_id"], p["event_id"]) for p in hits_payload]
2. alert_ids = _bulk_build_instant_alerts(hits)
3. if alert_ids: _trigger_dispatch_async(alert_ids)
```

任务自身 `autoretry_for=(Exception,)` + 指数退避 ×3。最终失败仅 ERROR 日志，不引入死信表。

### 4.6 聚合管线排除 INSTANT

```text
AggregationProcessor._get_active_strategies():
return AlarmStrategy.objects.filter(is_active=True) \
    .exclude(strategy_type=AlarmStrategyType.INSTANT) \
    .order_by("-updated_at")
```

### 4.7 自动关闭排除 INSTANT

```text
beat_close_alert():
现有查询 Alert.objects.filter(<已有条件>):
追加 .exclude(strategy__strategy_type=AlarmStrategyType.INSTANT)
说明：Alert 与 AlarmStrategy 通过 rule_id 字符串关联，需通过 rule_id 反查策略类型。
若现有 Alert 表无外键关系，则改为：
    instant_rule_ids = set(AlarmStrategy.objects
        .filter(strategy_type=INSTANT).values_list("id", flat=True))
    instant_rule_ids = {str(i) for i in instant_rule_ids}
    queryset = queryset.exclude(rule_id__in=instant_rule_ids)
```

### 4.8 Serializer 校验

```text
_validate_instant(attrs):
1. match_rules = attrs.get("match_rules") or []
   if not match_rules:
       raise ValidationError("即时告警必须配置筛选条件")
2. 遍历 match_rules，至少存在一组非空 AND 条件，否则视为 ALL，报错
3. params = attrs.get("params") or {}
   template = params.get("alert_template") or {}
   if not template.get("title"):
       raise ValidationError("告警模板标题必填")
   if not template.get("description"):
       raise ValidationError("告警模板描述必填")
4. 清理聚合参数（静默，不报错）：
   for k in ("window_size", "group_by", "aggregation_window", "aggregation_method"):
       params.pop(k, None)
   attrs["params"] = {"alert_template": template}
5. return attrs

save 钩子末尾：
   InstantStrategyCache.cache_clear()
```

### 4.9 前端表单分支

```text
operateModal 渲染逻辑：
1. 策略类型选项：[智能降噪, 缺失检测, 即时告警]
2. 若当前 strategy_type == "instant":
   - 隐藏字段：window_size, group_by, auto_close, close_minutes
   - 隐藏聚合相关的 step 或 section
   - 匹配方式字段：只渲染"按条件筛选"radio，禁用"全部"
   - 筛选条件：required=true，未填禁用保存按钮
   - 告警模板：required=true，title/description 必填
   - 保留字段：策略名称、生效组织、分派组织、匹配方式、筛选条件、告警模板
3. 提交时 buildInstantPayload(values):
   - 仅保留必要字段
   - params = { alert_template: { title, description } }

列表页：
1. 类型列展示文案映射：instant -> "即时告警"
2. 类型筛选下拉新增"即时告警"

详情页：
1. 类型字段展示"即时告警"
2. 若类型为即时告警：隐藏聚合相关展示字段
```

## 5. 第三方依赖与环境要求

- 无新增第三方依赖。
- 直接复用 `server/pyproject.toml` 中已存在依赖：Django ORM `bulk_create(ignore_conflicts=True)`、`celery`、`hashlib`。
- 后端环境：Python 3.12、Django 4.2、Celery 5.4、PostgreSQL（主用） / MySQL（次用）。
- 前端环境：Node 24、pnpm、Ant Design。
- Celery 队列：新增 `instant_alerts` 队列；若未在 `server/config/components/celery.py` 中显式定义，则降级使用 default 队列（不阻塞功能）。

验证命令：
```bash
cd server && make test
cd web && pnpm lint && pnpm type-check
```

## 6. 注释、日志、测试要求

### 6.1 注释要求

- `InstantAlertDispatcher` 与 `_bulk_build_instant_alerts` 必须在 docstring 写明：
  - 是相关性规则 INSTANT 类型的"旁路"调度器，与聚合管线并行
  - 自身吞掉异常，不影响 adapter 主流程
  - 同步/异步降级阈值含义
- `InstantMatcher.match_in_memory` 必须注明语义与 `StrategyMatcher` 完全一致；任何分歧都是 bug。
- `AggregationProcessor._get_active_strategies` 的修改点必须加注释："排除 INSTANT 策略，由旁路调度器处理。"
- `beat_close_alert` 的修改点必须加注释："即时告警按 PRD 不自动关闭。"
- 类内所有非简单函数必须补充 docstring：作用 / 入参 / 返回值 / DB 副作用。

### 6.2 日志要求

统一使用 `alert_logger`，日志级别如下：

```text
INFO
- 旁路调度开始：active strategy 数 / events 数
- 命中汇总：hits 数 / 同步 or 异步分支
- 同步落库完成：created alert_ids 数
- Celery 兜底任务入队 / 执行完成
- 触发分派：alert_ids 数

DEBUG
- 单事件 × 单策略匹配结果
- 策略缓存命中 / 失效

ERROR / EXCEPTION
- 命中数超 INSTANT_HIT_CEILING 截断
- bulk_create / M2M 写入失败
- Celery 任务最终失败
```

限制：
- 不记录事件 raw_data 全量
- 不记录敏感字段
- 不记录 match_rules 完整内容（量大），只记规则条数

### 6.3 测试方案

后端测试文件：
- `server/apps/alerts/test/test_instant_matcher.py`
- `server/apps/alerts/test/test_instant_dispatcher.py`
- `server/apps/alerts/test/test_instant_alert_pipeline.py`
- `server/apps/alerts/test/test_strategy_serializer.py`（扩展）

后端最小测试集：

**test_instant_matcher.py**
- 与 `StrategyMatcher` Q 表达式等价性：所有操作符（eq/ne/contains/not_contains/regex/in/not_in/gt/gte/lt/lte）逐个对拍
- AND/OR 嵌套：单组 AND、多组 OR、混合
- 字段映射覆盖 `FIELD_MAP` 全集
- 空 match_rules → 返回 False（不返回 True，避免无差别命中）

**test_instant_dispatcher.py**
- 无 INSTANT 策略 → 不创建 Alert
- 1 个事件 × 1 个策略命中 → 1 条 Alert，指纹符合 `md5("instant:<sid>:<eid>")`
- 1 个事件 × N 个策略命中 → N 条 Alert，指纹两两不同
- 同一事件重复投递 → `bulk_create(ignore_conflicts=True)` 不产生重复
- 命中数超 `INSTANT_SYNC_THRESHOLD` → mock `current_app.send_task` 被调用且参数正确，未走同步路径
- 命中数超 `INSTANT_HIT_CEILING` → 截断 + ERROR 日志
- 策略 save 后 `InstantStrategyCache.get()` 不返回旧值
- `dispatch` 内异常被吞掉，不抛出

**test_instant_alert_pipeline.py**（集成）
- 调用 `AlertSourceAdapter.main(events)`，断言：
  - Event 行 1 条入库
  - Alert 行 N 条入库（N = 命中策略数）
  - Alert↔Event M2M 关联存在
  - `event_count == 1`
  - `level == event.level`
  - `team == strategy.dispatch_team`
  - `async_auto_assignment_for_alerts` 被 mock 调用 1 次，args 含正确 alert_ids
- 同一事件同时匹配 SMART_DENOISE 与 INSTANT 规则：
  - INSTANT Alert 同步产出
  - 事件仍进入 `event_operator`，后续 Beat 触发聚合时产出 SMART_DENOISE Alert
  - 两条 Alert 互不影响

**test_strategy_serializer.py**（扩展用例）
- `strategy_type=INSTANT` + 空 `match_rules` → 400
- `strategy_type=INSTANT` + 等价 ALL 的空 AND 组 → 400
- `strategy_type=INSTANT` + 缺 `alert_template.title` → 400
- `strategy_type=INSTANT` + 缺 `alert_template.description` → 400
- `strategy_type=INSTANT` + 多余 `params.window_size` → 通过校验，但 saved params 不含该字段
- 保存成功后 `InstantStrategyCache.cache_clear` 被调用

**回归**
- `test_aggregation_processor.py`：注入 1 个 INSTANT 策略，确认 `_get_active_strategies()` 排除它，原 SMART_DENOISE/MISSING_DETECTION 行为不变
- `test_strategy_matcher.py`：行为零变化
- `test_setting_strategy_views.py`：CRUD 行为零变化

**性能验证（合并前手工）**
```bash
# 准备：创建 5 条 active INSTANT 策略 + 1 条 active SMART_DENOISE 策略
# 用脚本对 NATS receive 接口打 1000 RPS，每次 1 event
# 观察：
#   - adapter P99 延迟 < 100ms
#   - PostgreSQL write QPS 增量 < 3000（≈ 1000 events + 800 alerts + 800 M2M）
#   - Celery worker CPU 平稳
#   - 无 Celery 队列积压（同步路径下不应有 build_instant_alerts 任务）
```

前端自动验证：
```bash
cd web && pnpm lint
cd web && pnpm type-check
```

## 7. 发布与回滚

**发布顺序**：
1. 后端先发：Phase 1（常量/迁移/serializer）+ Phase 2（旁路实现）。旁路代码上线后处于"无 INSTANT 策略 → 不生效"的休眠态。
2. 前端再发：Phase 3（表单分支）。用户可开始创建 INSTANT 策略。
3. 性能验证通过后开放给生产用户。

**回滚策略**：
- 紧急情况下只需将 INSTANT 策略全部 `is_active=False`，旁路立即休眠（缓存最多 60s 内失效）。
- 代码回滚：只需回退 `AlertSourceAdapter.main()` 中的一行 `InstantAlertDispatcher.dispatch(bulk_events)` 调用即可关闭旁路；策略数据保留，不影响后续重新启用。
- migration 仅 alter choices，无需回滚（即使保留新值也不影响旧策略类型）。
