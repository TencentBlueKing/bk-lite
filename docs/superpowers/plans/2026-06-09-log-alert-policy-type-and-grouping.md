# 日志告警策略类型选择与分组 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在最小前端改造范围内前置策略类型选择，并让关键字告警支持可选分组字段与动态告警名称变量。

**Architecture:** 后端不新增表结构，继续使用 `Policy.alert_condition.group_by`。关键字告警未配置分组时保持旧逻辑，配置分组时用 VictoriaLogs `stats by (...)` 获取分组命中数，再按分组补查样本日志。前端保留现有策略详情页，列表页新增类型选择弹窗，详情页根据 URL 或策略详情锁定 `alert_type`，并把可测试的表单组装/变量逻辑抽到纯函数。

**Tech Stack:** Django 4.2、pytest、VictoriaLogs 查询语法、Next.js 16、React 19、TypeScript、Ant Design、`tsx` 脚本测试。

---

## 文件结构

- Modify: `server/apps/log/tasks/services/policy_scan.py`
  - 负责关键字告警扫描、聚合查询、告警名称模板渲染、分组样本查询。
- Create: `server/apps/log/tests/test_policy_scan_keyword_grouping.py`
  - 覆盖关键字未分组旧逻辑、关键字分组 `stats by`、动态变量渲染、缺失变量容错。
- Modify: `web/src/app/log/(pages)/event/strategy/page.tsx`
  - 「添加」入口改为打开策略类型选择弹窗，并按类型跳转到现有详情页。
- Modify: `web/src/app/log/(pages)/event/strategy/detail/page.tsx`
  - 从 URL 或详情锁定策略类型；提交时统一组装 `alert_condition.group_by`、`show_fields`、`rule`。
- Modify: `web/src/app/log/(pages)/event/strategy/detail/alertConditionsForm.tsx`
  - 展示字段对关键字和聚合都可见；关键字新增可选分组字段；聚合保留规则；接入变量面板和日志预览。
- Create: `web/src/app/log/(pages)/event/strategy/detail/policyFormUtils.ts`
  - 纯函数：策略类型解析、默认展示字段、变量列表、变量插入、提交参数组装。
- Create: `web/src/app/log/(pages)/event/strategy/detail/alertNameVariables.tsx`
  - 告警名称变量面板。
- Create: `web/src/app/log/(pages)/event/strategy/detail/logPreview.tsx`
  - 复用现有 `useSearchApi().getLogs` 的日志预览区域。
- Modify: `web/src/app/log/types/event.ts`
  - 补齐 `StrategyFields.alert_condition.group_by`、`show_fields` 等类型约束。
- Modify: `web/src/app/log/locales/zh.json`
  - 增加策略类型弹窗、变量面板、日志预览相关文案。
- Modify: `web/src/app/log/locales/en.json`
  - 增加英文兜底文案。
- Create: `web/scripts/log-policy-form-state-test.ts`
  - 使用 Node `assert` 验证前端纯函数。
- Modify: `web/package.json`
  - 增加 `test:log-policy-form` 脚本。

## Task 1: 后端 RED - 关键字分组与模板渲染测试

**Files:**
- Create: `server/apps/log/tests/test_policy_scan_keyword_grouping.py`

- [ ] **Step 1: 写失败测试**

创建 `server/apps/log/tests/test_policy_scan_keyword_grouping.py`：

```python
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.log.tasks.services.policy_scan import LogPolicyScan


class FakeVictoriaLogs:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def query(self, query, start, end, limit):
        self.calls.append(
            {
                "query": query,
                "start": start,
                "end": end,
                "limit": limit,
            }
        )
        if not self.responses:
            return []
        return self.responses.pop(0)


def make_policy(alert_condition, alert_name="${level} ${log.service.name} error"):
    return SimpleNamespace(
        id=7,
        alert_condition=alert_condition,
        alert_name=alert_name,
        alert_level="error",
        period={"type": "min", "value": 5},
        last_run_time=datetime(2026, 6, 9, 8, 0, tzinfo=timezone.utc),
        collect_type=None,
    )


def make_scan(policy, fake_api):
    scan = LogPolicyScan(policy, scan_time=policy.last_run_time)
    scan.vlogs_api = fake_api
    scan._build_query_with_log_groups = lambda query: query
    return scan


def test_keyword_without_group_by_keeps_single_policy_source_id():
    fake_api = FakeVictoriaLogs(
        responses=[
            [{"timestamp": "2026-06-09T08:00:00Z", "message": "error"}],
            [{"total_count": "3"}],
        ]
    )
    policy = make_policy({"query": "error", "limit": 5, "group_by": []}, alert_name="error alert")
    scan = make_scan(policy, fake_api)

    events = scan.keyword_alert_detection()

    assert len(events) == 1
    assert events[0]["source_id"] == "policy_7"
    assert events[0]["level"] == "error"
    assert events[0]["value"] == 3
    assert "检测到 3 条匹配日志" in events[0]["content"]
    assert fake_api.calls[0]["query"] == "error"
    assert fake_api.calls[1]["query"] == "error | stats count() as total_count"


def test_keyword_with_group_by_uses_stats_by_and_returns_one_event_per_group():
    fake_api = FakeVictoriaLogs(
        responses=[
            [
                {"log.service.name": "api", "total_count": "2"},
                {"log.service.name": "web", "total_count": "5"},
            ],
            [{"timestamp": "2026-06-09T08:00:00Z", "message": "api error", "log.service.name": "api"}],
            [{"timestamp": "2026-06-09T08:00:10Z", "message": "web error", "log.service.name": "web"}],
        ]
    )
    policy = make_policy(
        {"query": "error", "limit": 3, "group_by": ["log.service.name"]},
        alert_name="${level}:${log.service.name}",
    )
    scan = make_scan(policy, fake_api)

    events = scan.keyword_alert_detection()

    assert fake_api.calls[0]["query"] == "error | stats by (log.service.name) count() as total_count"
    assert len(events) == 2
    assert events[0]["source_id"] == "policy_7_log.service.name=api"
    assert events[0]["content"] == "error:api"
    assert events[0]["value"] == 2
    assert events[0]["raw_data"][0]["message"] == "api error"
    assert events[1]["source_id"] == "policy_7_log.service.name=web"
    assert events[1]["content"] == "error:web"
    assert events[1]["value"] == 5
    assert 'log.service.name:"api"' in fake_api.calls[1]["query"]
    assert 'log.service.name:"web"' in fake_api.calls[2]["query"]


def test_alert_name_template_renders_level_and_dotted_log_fields():
    policy = make_policy({}, alert_name="${level}|${log.service.name}|${missing}")
    scan = make_scan(policy, FakeVictoriaLogs([]))

    rendered = scan._render_alert_name({"log.service.name": "api"}, ["log.service.name"])

    assert rendered == "error|api|"


def test_keyword_group_by_skips_rows_without_group_key():
    fake_api = FakeVictoriaLogs(
        responses=[
            [{"total_count": "2"}, {"log.service.name": "api", "total_count": "4"}],
            [{"timestamp": "2026-06-09T08:00:00Z", "message": "api error", "log.service.name": "api"}],
        ]
    )
    policy = make_policy(
        {"query": "error", "limit": 3, "group_by": ["log.service.name"]},
        alert_name="${log.service.name}",
    )
    scan = make_scan(policy, fake_api)

    events = scan.keyword_alert_detection()

    assert len(events) == 1
    assert events[0]["source_id"] == "policy_7_log.service.name=api"
```

- [ ] **Step 2: 运行测试，确认失败**

Run:

```bash
cd server && uv run pytest apps/log/tests/test_policy_scan_keyword_grouping.py -q
```

Expected:

```text
FAILED ... test_keyword_with_group_by_uses_stats_by_and_returns_one_event_per_group
FAILED ... test_alert_name_template_renders_level_and_dotted_log_fields
```

失败原因应是当前关键字告警没有 `group_by` 分支，且 `_render_alert_name` 不能正确处理 `${level}` 和带点号的 `${log.service.name}`。

- [ ] **Step 3: 提交 RED 测试**

```bash
git add server/apps/log/tests/test_policy_scan_keyword_grouping.py
git commit -m "test: cover log keyword alert grouping"
```

## Task 2: 后端 GREEN - 实现关键字分组扫描

**Files:**
- Modify: `server/apps/log/tasks/services/policy_scan.py`
- Test: `server/apps/log/tests/test_policy_scan_keyword_grouping.py`

- [ ] **Step 1: 实现模板 formatter 与分组辅助函数**

在 `server/apps/log/tasks/services/policy_scan.py` 顶部增加导入：

```python
import re
```

在 `LogPolicyScan` 类中、`_render_alert_name` 前增加这些辅助方法：

```python
    _ALERT_NAME_TOKEN_RE = re.compile(r"\$\{([^}]+)\}")

    def _normalize_group_by(self, group_by):
        if not group_by:
            return []
        if isinstance(group_by, str):
            return [group_by]
        return [field for field in group_by if field]

    def _parse_count_value(self, raw_value, default=0):
        try:
            return int(float(str(raw_value))) if raw_value not in [None, ""] else default
        except (TypeError, ValueError):
            logger.warning(f"Failed to parse count value for policy {self.policy.id}: {raw_value}")
            return default

    def _build_keyword_group_query(self, final_query, group_by):
        by_fields = ", ".join(group_by)
        return f"{final_query} | stats by ({by_fields}) count() as total_count"

    def _escape_log_query_value(self, value):
        return str(value).replace("\\", "\\\\").replace('"', '\\"')

    def _build_group_sample_query(self, final_query, group_values):
        filters = []
        for field, value in group_values.items():
            escaped_value = self._escape_log_query_value(value)
            filters.append(f'{field}:"{escaped_value}"')

        if not filters:
            return final_query

        group_filter = " AND ".join(filters)
        if not final_query or final_query.strip() == "*":
            return group_filter
        return f"({final_query}) AND {group_filter}"

    def _extract_group_values(self, result, group_by):
        group_values = {}
        for field in group_by:
            value = result.get(field)
            if value in [None, ""]:
                return {}
            group_values[field] = value
        return group_values
```

- [ ] **Step 2: 替换 `_render_alert_name`**

将现有 `_render_alert_name` 方法替换为：

```python
    def _render_alert_name(self, result=None, group_by=None):
        """渲染告警名称模板，支持 ${level} 和 ${log.fieldName}。"""
        if not self.policy.alert_name:
            return "聚合告警" if self.policy.alert_type == "aggregate" else "关键字告警"

        alert_name = self.policy.alert_name
        context = {
            "level": self.policy.alert_level,
        }
        if isinstance(result, dict):
            context.update(result)

        try:
            def replace_token(match):
                token = match.group(1)
                value = context.get(token, "")
                return "" if value is None else str(value)

            rendered_name = self._ALERT_NAME_TOKEN_RE.sub(replace_token, alert_name)
            return rendered_name.strip() or alert_name
        except Exception as e:
            logger.warning(f"Failed to render alert name template '{alert_name}': {e}")
            return alert_name
```

- [ ] **Step 3: 增加关键字分组检测方法**

在 `keyword_alert_detection` 前增加：

```python
    def _keyword_grouped_alert_detection(self, final_query, group_by, sample_limit, start_timestamp, end_timestamp):
        events = []
        group_query = self._build_keyword_group_query(final_query, group_by)
        grouped_results = self.vlogs_api.query(
            query=group_query,
            start=start_timestamp,
            end=end_timestamp,
            limit=1000,
        )

        for result in grouped_results or []:
            group_values = self._extract_group_values(result, group_by)
            if not group_values:
                logger.warning(f"Skip keyword grouped result without complete group values for policy {self.policy.id}: {result}")
                continue

            total_count = self._parse_count_value(result.get("total_count"), default=0)
            if total_count <= 0:
                continue

            sample_query = self._build_group_sample_query(final_query, group_values)
            try:
                logs = self.vlogs_api.query(
                    query=sample_query,
                    start=start_timestamp,
                    end=end_timestamp,
                    limit=sample_limit,
                )
            except Exception as e:
                logger.warning(f"Failed to query keyword grouped samples for policy {self.policy.id}: {e}")
                logs = []

            group_key = self._build_group_key(group_values, group_by)
            source_id = f"policy_{self.policy.id}_{group_key}"
            content = self._render_alert_name(group_values, group_by)

            events.append(
                {
                    "source_id": source_id,
                    "level": self.policy.alert_level,
                    "content": content,
                    "value": total_count,
                    "raw_data": logs[:sample_limit],
                }
            )

        return events
```

- [ ] **Step 4: 修改 `keyword_alert_detection` 分支**

在 `keyword_alert_detection` 中，`sample_limit = ...` 后添加：

```python
            group_by = self._normalize_group_by(alert_condition.get("group_by", []))
            if group_by:
                return self._keyword_grouped_alert_detection(
                    final_query,
                    group_by,
                    sample_limit,
                    start_timestamp,
                    end_timestamp,
                )
```

保留后续未分组旧逻辑。

- [ ] **Step 5: 运行后端聚焦测试，确认通过**

Run:

```bash
cd server && uv run pytest apps/log/tests/test_policy_scan_keyword_grouping.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 6: 运行日志模块已有最小测试**

Run:

```bash
cd server && uv run pytest apps/log/tests/test_query_log.py apps/log/tests/test_search_query_limits.py apps/log/tests/test_policy_scan_keyword_grouping.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: 提交后端实现**

```bash
git add server/apps/log/tasks/services/policy_scan.py server/apps/log/tests/test_policy_scan_keyword_grouping.py
git commit -m "feat: group keyword log alerts"
```

## Task 3: 前端 RED - 表单纯函数测试

**Files:**
- Create: `web/scripts/log-policy-form-state-test.ts`
- Create: `web/src/app/log/(pages)/event/strategy/detail/policyFormUtils.ts`
- Modify: `web/package.json`

- [ ] **Step 1: 先创建空工具文件**

创建 `web/src/app/log/(pages)/event/strategy/detail/policyFormUtils.ts`：

```typescript
export {};
```

- [ ] **Step 2: 写失败测试脚本**

创建 `web/scripts/log-policy-form-state-test.ts`：

```typescript
import assert from 'node:assert/strict';
import {
  buildAlertNameVariables,
  buildStrategyPayload,
  getDefaultShowFields,
  getLockedPolicyType,
  insertAlertNameVariable
} from '../src/app/log/(pages)/event/strategy/detail/policyFormUtils';

assert.equal(getLockedPolicyType({ urlAlertType: 'keyword' }), 'keyword');
assert.equal(getLockedPolicyType({ detailAlertType: 'aggregate' }), 'aggregate');
assert.equal(getLockedPolicyType({ urlAlertType: 'unknown', detailAlertType: 'keyword' }), 'keyword');

assert.deepEqual(getDefaultShowFields(undefined), ['timestamp', 'message']);
assert.deepEqual(getDefaultShowFields(['message', 'host']), ['timestamp', 'message', 'host']);

assert.deepEqual(buildAlertNameVariables(['log.service.name', 'host']), [
  { value: '${level}', label: '${level}' },
  { value: '${log.service.name}', label: '${log.service.name}' },
  { value: '${host}', label: '${host}' }
]);

assert.equal(insertAlertNameVariable('告警', '${level}', 0, 0), '${level}告警');
assert.equal(insertAlertNameVariable('api告警', '${log.service.name}', 3, 3), 'api${log.service.name}告警');
assert.equal(insertAlertNameVariable('告警', '${level}'), '告警${level}');

const keywordPayload = buildStrategyPayload(
  {
    name: '关键字策略',
    alert_type: 'keyword',
    alert_name: '${level}:${log.service.name}',
    alert_level: 'error',
    log_groups: ['1'],
    organizations: ['10'],
    query: 'error',
    show_fields: ['timestamp', 'message'],
    group_by: ['log.service.name'],
    schedule: 5,
    period: 10,
    notice_type_id: 2
  },
  {
    unit: 'min',
    periodUnit: 'min',
    channelList: [{ id: 2, channel_type: 'email', name: 'Email' }],
    conditions: [{ field: 'message', func: 'count', op: '>', value: 10 }],
    term: 'and',
    isEdit: false
  }
);

assert.deepEqual(keywordPayload.alert_condition, {
  query: 'error',
  group_by: ['log.service.name']
});
assert.deepEqual(keywordPayload.show_fields, ['timestamp', 'message']);
assert.equal(keywordPayload.notice_type, 'email');
assert.equal(keywordPayload.enable, true);

const aggregatePayload = buildStrategyPayload(
  {
    name: '聚合策略',
    alert_type: 'aggregate',
    alert_name: '${level}:${log.service.name}',
    alert_level: 'warning',
    log_groups: ['1'],
    organizations: ['10'],
    query: 'error',
    show_fields: ['timestamp', 'message'],
    group_by: ['log.service.name'],
    schedule: 5,
    period: 10,
    notice_type_id: 2
  },
  {
    unit: 'min',
    periodUnit: 'min',
    channelList: [{ id: 2, channel_type: 'email', name: 'Email' }],
    conditions: [{ field: 'message', func: 'count', op: '>', value: 10 }],
    term: 'and',
    isEdit: true,
    formData: { id: 99 }
  }
);

assert.deepEqual(aggregatePayload.alert_condition, {
  query: 'error',
  group_by: ['log.service.name'],
  rule: {
    mode: 'and',
    conditions: [{ field: 'message', func: 'count', op: '>', value: 10 }]
  }
});
assert.equal(aggregatePayload.id, 99);
assert.equal(Object.prototype.hasOwnProperty.call(aggregatePayload, 'enable'), false);

console.log('log-policy-form-state validation passed');
```

- [ ] **Step 3: 增加测试脚本命令**

在 `web/package.json` 的 `scripts` 中加入：

```json
"test:log-policy-form": "pnpm exec tsx scripts/log-policy-form-state-test.ts"
```

- [ ] **Step 4: 运行测试，确认失败**

Run:

```bash
cd web && pnpm test:log-policy-form
```

Expected:

```text
Module ... has no exported member 'buildAlertNameVariables'
```

- [ ] **Step 5: 提交 RED 测试**

```bash
git add web/scripts/log-policy-form-state-test.ts web/src/app/log/\(pages\)/event/strategy/detail/policyFormUtils.ts web/package.json
git commit -m "test: cover log policy form state"
```

## Task 4: 前端 GREEN - 实现表单纯函数并接入详情页提交

**Files:**
- Modify: `web/src/app/log/(pages)/event/strategy/detail/policyFormUtils.ts`
- Modify: `web/src/app/log/(pages)/event/strategy/detail/page.tsx`
- Modify: `web/src/app/log/types/event.ts`
- Test: `web/scripts/log-policy-form-state-test.ts`

- [ ] **Step 1: 实现 `policyFormUtils.ts`**

将 `policyFormUtils.ts` 替换为：

```typescript
import { FilterItem } from '@/app/log/types/integration';
import { ChannelItem, StrategyFields } from '@/app/log/types/event';

export type LogPolicyType = 'keyword' | 'aggregate';

const POLICY_TYPES = new Set<LogPolicyType>(['keyword', 'aggregate']);
const DEFAULT_SHOW_FIELDS = ['timestamp', 'message'];

export const getLockedPolicyType = ({
  urlAlertType,
  detailAlertType,
}: {
  urlAlertType?: string | null;
  detailAlertType?: string | null;
}): LogPolicyType => {
  if (POLICY_TYPES.has(urlAlertType as LogPolicyType)) {
    return urlAlertType as LogPolicyType;
  }
  if (POLICY_TYPES.has(detailAlertType as LogPolicyType)) {
    return detailAlertType as LogPolicyType;
  }
  return 'keyword';
};

export const getDefaultShowFields = (fields?: string[] | null): string[] => {
  const merged = [...DEFAULT_SHOW_FIELDS, ...(fields || [])].filter(Boolean);
  return Array.from(new Set(merged));
};

export const buildAlertNameVariables = (groupBy?: string[] | null) => {
  const variables = [{ value: '${level}', label: '${level}' }];
  (groupBy || []).filter(Boolean).forEach((field) => {
    variables.push({
      value: `\${${field}}`,
      label: `\${${field}}`,
    });
  });
  return variables;
};

export const insertAlertNameVariable = (
  text: string,
  variable: string,
  selectionStart?: number | null,
  selectionEnd?: number | null
): string => {
  if (typeof selectionStart === 'number' && typeof selectionEnd === 'number') {
    return `${text.slice(0, selectionStart)}${variable}${text.slice(selectionEnd)}`;
  }
  return `${text}${variable}`;
};

export const buildStrategyPayload = (
  values: StrategyFields,
  options: {
    unit: string;
    periodUnit: string;
    channelList: ChannelItem[];
    conditions: FilterItem[];
    term: string | null;
    isEdit: boolean;
    formData?: StrategyFields;
  }
): StrategyFields => {
  const params: StrategyFields = {
    ...values,
    show_fields: getDefaultShowFields(values.show_fields),
    schedule: {
      type: options.unit,
      value: values.schedule as unknown as number,
    },
    period: {
      type: options.periodUnit,
      value: values.period as unknown as number,
    },
  };

  if (params.notice_type_id) {
    params.notice_type =
      options.channelList.find((item) => item.id === params.notice_type_id)?.channel_type || '';
  }

  const groupBy = Array.isArray(values.group_by) ? values.group_by : [];
  params.alert_condition = {
    query: values.query || '',
    group_by: groupBy,
  };

  if (params.alert_type === 'aggregate') {
    params.alert_condition.rule = {
      mode: options.term || 'and',
      conditions: options.conditions,
    };
  }

  if (options.isEdit) {
    params.id = options.formData?.id;
  } else {
    params.enable = true;
  }

  return params;
};
```

- [ ] **Step 2: 修正变量格式实现**

运行 Step 3 测试会暴露一个细节：`buildAlertNameVariables` 必须输出 `${log.service.name}`，而不是模板字符串转义错误。若 Step 1 粘贴后结果不对，将该函数修正为：

```typescript
export const buildAlertNameVariables = (groupBy?: string[] | null) => {
  const variables = [{ value: '${level}', label: '${level}' }];
  (groupBy || []).filter(Boolean).forEach((field) => {
    const token = '${' + field + '}';
    variables.push({
      value: token,
      label: token,
    });
  });
  return variables;
};
```

- [ ] **Step 3: 运行前端纯函数测试**

Run:

```bash
cd web && pnpm test:log-policy-form
```

Expected:

```text
log-policy-form-state validation passed
```

- [ ] **Step 4: 更新 `StrategyFields` 类型**

在 `web/src/app/log/types/event.ts` 中，把 `StrategyFields` 的 `schedule`、`period` 和 `alert_condition` 改为兼容表单数字与保存对象：

```typescript
  schedule?: {
    type: string;
    value: number;
  } | number;
  period?: {
    type: string;
    value: number;
  } | number;
  alert_condition?: {
    group_by?: string[];
    query?: string;
    rule?: {
      mode: string;
      conditions: FilterItem[];
    };
  };
```

- [ ] **Step 5: 接入详情页类型锁定与提交组装**

在 `web/src/app/log/(pages)/event/strategy/detail/page.tsx` 增加导入：

```typescript
import {
  buildStrategyPayload,
  getDefaultShowFields,
  getLockedPolicyType
} from './policyFormUtils';
```

读取 URL 参数：

```typescript
  const urlAlertType = searchParams.get('alert_type');
```

增加锁定类型：

```typescript
  const lockedAlertType = useMemo(
    () =>
      getLockedPolicyType({
        urlAlertType,
        detailAlertType: formData.alert_type
      }),
    [urlAlertType, formData.alert_type]
  );
```

创建初始化表单时设置默认展示字段和锁定类型：

```typescript
      const initForm: TableDataItem = {
        organizations: groupId,
        notice_type_id: channelItem?.id,
        notice_type: channelItem?.channel_type,
        notice: false,
        period: 5,
        schedule: 5,
        alert_type: lockedAlertType,
        show_fields: getDefaultShowFields()
      };
```

编辑回填时保留 `show_fields`：

```typescript
      show_fields: getDefaultShowFields(data.show_fields),
```

替换 `createStrategy` 中手写 `params` 的逻辑：

```typescript
  const createStrategy = () => {
    form?.validateFields().then((values) => {
      const params = buildStrategyPayload(
        {
          ...values,
          alert_type: lockedAlertType
        },
        {
          unit,
          periodUnit,
          channelList,
          conditions,
          term,
          isEdit,
          formData
        }
      );
      operateStrategy(params);
    });
  };
```

传给 `AlertConditionsForm`：

```tsx
                      policyType={lockedAlertType}
                      form={form}
```

- [ ] **Step 6: 运行前端纯函数测试**

Run:

```bash
cd web && pnpm test:log-policy-form
```

Expected:

```text
log-policy-form-state validation passed
```

- [ ] **Step 7: 提交前端工具与详情页接入**

```bash
git add web/src/app/log/\(pages\)/event/strategy/detail/policyFormUtils.ts web/src/app/log/\(pages\)/event/strategy/detail/page.tsx web/src/app/log/types/event.ts web/scripts/log-policy-form-state-test.ts web/package.json
git commit -m "feat: lock log policy form type"
```

## Task 5: 前端 UI - 添加入口弹窗与条件表单差异

**Files:**
- Modify: `web/src/app/log/(pages)/event/strategy/page.tsx`
- Modify: `web/src/app/log/(pages)/event/strategy/detail/alertConditionsForm.tsx`
- Modify: `web/src/app/log/locales/zh.json`
- Modify: `web/src/app/log/locales/en.json`

- [ ] **Step 1: 修改列表页添加入口**

在 `web/src/app/log/(pages)/event/strategy/page.tsx` 的 antd 导入中加入 `Modal`：

```typescript
import { Input, Button, message, Switch, Popconfirm, Modal } from 'antd';
```

新增 state：

```typescript
  const [typeModalOpen, setTypeModalOpen] = useState(false);
```

新增选择类型函数：

```typescript
  const openCreateTypeModal = () => {
    setTypeModalOpen(true);
  };

  const createByPolicyType = (alertType: string) => {
    setTypeModalOpen(false);
    linkToStrategyDetail('add', { id: '', name: '', alert_type: alertType });
  };
```

把 `linkToStrategyDetail` 改为带 `alert_type`：

```typescript
  const linkToStrategyDetail = (
    type: string,
    row = { id: '', name: '', alert_type: '' }
  ) => {
    const params = new URLSearchParams({
      type,
      id: row.id,
      name: row.name
    });
    if (row.alert_type) {
      params.set('alert_type', row.alert_type);
    }
    const targetUrl = `/log/event/strategy/detail?${params.toString()}`;
    router.push(targetUrl);
  };
```

把添加按钮 `onClick` 改为：

```tsx
              onClick={openCreateTypeModal}
```

在返回 JSX 的根节点末尾、`CustomTable` 后加入弹窗：

```tsx
        <Modal
          title={t('log.event.selectPolicyType')}
          open={typeModalOpen}
          footer={null}
          onCancel={() => setTypeModalOpen(false)}
          destroyOnHidden
        >
          <div className="grid grid-cols-2 gap-4">
            {ALGORITHM_LIST.map((item) => (
              <button
                key={item.value}
                type="button"
                className="text-left rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg-1)] p-4 cursor-pointer hover:border-[var(--color-primary)]"
                onClick={() => createByPolicyType(String(item.value))}
              >
                <div className="font-medium mb-2">{item.title}</div>
                <div className="text-[12px] text-[var(--color-text-3)]">
                  {item.description}
                </div>
              </button>
            ))}
          </div>
        </Modal>
```

- [ ] **Step 2: 修改 `AlertConditionsFormProps`**

在 `alertConditionsForm.tsx` 导入 `FormInstance`：

```typescript
import { Form, Input, Select, InputNumber, Radio, FormInstance } from 'antd';
```

Props 增加：

```typescript
  policyType: 'keyword' | 'aggregate';
  form: FormInstance;
```

函数参数解构增加 `policyType`、`form`。

- [ ] **Step 3: 移除表单内部策略类型选择**

删除或不渲染当前 `name="alert_type"` 的 `SelectCard` 表单项。保留隐藏字段：

```tsx
      <Form.Item<StrategyFields> name="alert_type" hidden>
        <Input />
      </Form.Item>
```

- [ ] **Step 4: 让两类策略都展示展示字段和分组字段**

在查询条件后渲染展示字段：

```tsx
      <Form.Item<StrategyFields>
        required
        label={<span className="w-[100px]">{t('log.event.displayFields')}</span>}
      >
        <Form.Item
          name="show_fields"
          noStyle
          rules={[{ required: true, message: t('common.required') }]}
        >
          <Select
            style={{ width: 800 }}
            showSearch
            mode="multiple"
            maxTagCount="responsive"
            options={fieldList
              .filter((item) => !['_time', '_msg'].includes(item))
              .map((item) => ({ value: item, label: item }))}
          />
        </Form.Item>
        <div className="text-[var(--color-text-3)] mt-[10px]">
          {t('log.event.displayFieldsDes')}
        </div>
      </Form.Item>
```

紧接着渲染可选分组字段：

```tsx
      <Form.Item<StrategyFields>
        label={<span className="w-[100px]">{t('log.event.groupFields')}</span>}
      >
        <Form.Item name="group_by" noStyle>
          <Select
            style={{ width: 800 }}
            allowClear
            showSearch
            mode="multiple"
            maxTagCount="responsive"
            options={fieldList.map((item) => ({ value: item, label: item }))}
          />
        </Form.Item>
        <div className="text-[var(--color-text-3)] mt-[10px]">
          {t('log.event.groupFieldsDes')}
        </div>
      </Form.Item>
```

只在 `policyType === 'aggregate'` 时渲染规则配置：

```tsx
      {policyType === 'aggregate' && (
        <Form.Item<StrategyFields>
          required
          label={<span className="w-[100px]">{t('log.integration.rule')}</span>}
        >
          ...
        </Form.Item>
      )}
```

- [ ] **Step 5: 增加中英文文案**

在 `web/src/app/log/locales/zh.json` 的 `log.event` 下增加：

```json
"selectPolicyType": "选择策略类型",
"groupFields": "分组字段",
"groupFieldsDes": "用于将命中的日志按字段值拆分为不同告警；不配置时按策略收敛。",
"alertNameVariables": "可选变量",
"useVariable": "选用",
"logPreview": "日志预览",
"logPreviewGuide": "填写查询条件后展示最近 10 条日志预览。",
"logPreviewEmpty": "暂无预览日志"
```

在 `web/src/app/log/locales/en.json` 的 `log.event` 下增加：

```json
"selectPolicyType": "Select Policy Type",
"groupFields": "Group Fields",
"groupFieldsDes": "Split matched logs into alerts by field value. Leave empty to converge by policy.",
"alertNameVariables": "Variables",
"useVariable": "Use",
"logPreview": "Log Preview",
"logPreviewGuide": "Enter a query to preview the latest 10 logs.",
"logPreviewEmpty": "No preview logs"
```

- [ ] **Step 6: 运行前端类型检查的较小验证**

Run:

```bash
cd web && pnpm test:log-policy-form
```

Expected:

```text
log-policy-form-state validation passed
```

Run:

```bash
cd web && pnpm lint -- --file 'src/app/log/(pages)/event/strategy/page.tsx' --file 'src/app/log/(pages)/event/strategy/detail/page.tsx' --file 'src/app/log/(pages)/event/strategy/detail/alertConditionsForm.tsx'
```

Expected:

```text
No ESLint warnings or errors
```

- [ ] **Step 7: 提交入口与表单 UI**

```bash
git add web/src/app/log/\(pages\)/event/strategy/page.tsx web/src/app/log/\(pages\)/event/strategy/detail/alertConditionsForm.tsx web/src/app/log/locales/zh.json web/src/app/log/locales/en.json
git commit -m "feat: select log policy type before create"
```

## Task 6: 前端 UI - 变量面板与日志预览

**Files:**
- Create: `web/src/app/log/(pages)/event/strategy/detail/alertNameVariables.tsx`
- Create: `web/src/app/log/(pages)/event/strategy/detail/logPreview.tsx`
- Modify: `web/src/app/log/(pages)/event/strategy/detail/alertConditionsForm.tsx`
- Test: `web/scripts/log-policy-form-state-test.ts`

- [ ] **Step 1: 创建变量面板组件**

创建 `web/src/app/log/(pages)/event/strategy/detail/alertNameVariables.tsx`：

```tsx
import React from 'react';
import { Button, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';

interface AlertNameVariablesProps {
  variables: Array<{ label: string; value: string }>;
  onUse: (value: string) => void;
}

const AlertNameVariables: React.FC<AlertNameVariablesProps> = ({
  variables,
  onUse
}) => {
  const { t } = useTranslation();

  return (
    <div className="mb-4">
      <div className="font-medium mb-2">{t('log.event.alertNameVariables')}</div>
      <div className="flex flex-col gap-2">
        {variables.map((variable) => (
          <div
            key={variable.value}
            className="flex items-center justify-between gap-2"
          >
            <Tag className="m-0">{variable.label}</Tag>
            <Button size="small" type="link" onClick={() => onUse(variable.value)}>
              {t('log.event.useVariable')}
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AlertNameVariables;
```

- [ ] **Step 2: 创建日志预览组件**

创建 `web/src/app/log/(pages)/event/strategy/detail/logPreview.tsx`：

```tsx
import React, { useEffect, useMemo, useState } from 'react';
import { Empty, Spin, Table } from 'antd';
import useSearchApi from '@/app/log/api/search';
import { useTranslation } from '@/utils/i18n';

interface LogPreviewProps {
  query?: string;
  logGroups?: string[];
  showFields?: string[];
}

const LogPreview: React.FC<LogPreviewProps> = ({ query, logGroups, showFields }) => {
  const { t } = useTranslation();
  const { getLogs } = useSearchApi();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Record<string, unknown>[]>([]);

  const fields = useMemo(
    () => Array.from(new Set(['timestamp', 'message', ...(showFields || [])])),
    [showFields]
  );

  useEffect(() => {
    const trimmedQuery = query?.trim();
    if (!trimmedQuery || !logGroups?.length) {
      setData([]);
      return;
    }

    let ignore = false;
    setLoading(true);
    getLogs({
      query: trimmedQuery,
      log_groups: logGroups,
      limit: 10
    })
      .then((res) => {
        if (ignore) return;
        setData(Array.isArray(res) ? res : res?.data || res?.items || []);
      })
      .catch(() => {
        if (!ignore) setData([]);
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [query, logGroups, getLogs]);

  if (!query?.trim()) {
    return <Empty description={t('log.event.logPreviewGuide')} />;
  }

  return (
    <Spin spinning={loading}>
      <Table
        size="small"
        rowKey={(_, index) => String(index)}
        pagination={false}
        locale={{ emptyText: t('log.event.logPreviewEmpty') }}
        columns={fields.map((field) => ({
          title: field,
          dataIndex: field,
          key: field,
          ellipsis: true,
          render: (value) => (value == null ? '--' : String(value))
        }))}
        dataSource={data}
      />
    </Spin>
  );
};

export default LogPreview;
```

- [ ] **Step 3: 接入 `AlertConditionsForm` 的右侧区域**

在 `alertConditionsForm.tsx` 增加导入：

```typescript
import AlertNameVariables from './alertNameVariables';
import LogPreview from './logPreview';
import {
  buildAlertNameVariables,
  insertAlertNameVariable
} from './policyFormUtils';
```

在组件内增加：

```typescript
  const watchedGroupBy = Form.useWatch('group_by', form) || [];
  const watchedQuery = Form.useWatch('query', form) || '';
  const watchedLogGroups = Form.useWatch('log_groups', form) || [];
  const watchedShowFields = Form.useWatch('show_fields', form) || [];
  const alertNameVariables = buildAlertNameVariables(watchedGroupBy);

  const handleUseVariable = (variable: string) => {
    const currentName = form.getFieldValue('alert_name') || '';
    form.setFieldValue('alert_name', insertAlertNameVariable(currentName, variable));
  };
```

将原返回内容包一层左右布局：

```tsx
    <div className="grid grid-cols-[minmax(0,820px)_minmax(280px,1fr)] gap-6">
      <div>
        {/* existing Form.Item fields */}
      </div>
      <div>
        <AlertNameVariables variables={alertNameVariables} onUse={handleUseVariable} />
        <div className="font-medium mb-2">{t('log.event.logPreview')}</div>
        <LogPreview
          query={watchedQuery}
          logGroups={watchedLogGroups}
          showFields={watchedShowFields}
        />
      </div>
    </div>
```

如果布局在 `Steps` 里过宽，则把 grid 改为：

```tsx
    <div className="flex gap-6">
      <div className="w-[820px] flex-shrink-0">...</div>
      <div className="min-w-[280px] flex-1">...</div>
    </div>
```

- [ ] **Step 4: 运行测试与 lint**

Run:

```bash
cd web && pnpm test:log-policy-form
```

Expected:

```text
log-policy-form-state validation passed
```

Run:

```bash
cd web && pnpm lint -- --file 'src/app/log/(pages)/event/strategy/detail/alertConditionsForm.tsx' --file 'src/app/log/(pages)/event/strategy/detail/alertNameVariables.tsx' --file 'src/app/log/(pages)/event/strategy/detail/logPreview.tsx'
```

Expected:

```text
No ESLint warnings or errors
```

- [ ] **Step 5: 提交变量与预览 UI**

```bash
git add web/src/app/log/\(pages\)/event/strategy/detail/alertConditionsForm.tsx web/src/app/log/\(pages\)/event/strategy/detail/alertNameVariables.tsx web/src/app/log/\(pages\)/event/strategy/detail/logPreview.tsx
git commit -m "feat: add log policy variables and preview"
```

## Task 7: 集成验证与收尾

**Files:**
- Verify only unless prior tasks reveal type or lint issues.

- [ ] **Step 1: 运行后端聚焦测试**

Run:

```bash
cd server && uv run pytest apps/log/tests/test_policy_scan_keyword_grouping.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 2: 运行前端聚焦测试**

Run:

```bash
cd web && pnpm test:log-policy-form
```

Expected:

```text
log-policy-form-state validation passed
```

- [ ] **Step 3: 运行前端 lint/type-check 门禁**

Run:

```bash
cd web && pnpm lint && pnpm type-check
```

Expected:

```text
lint exits 0
type-check exits 0
```

- [ ] **Step 4: 运行后端日志模块相关测试**

Run:

```bash
cd server && uv run pytest apps/log/tests/test_query_log.py apps/log/tests/test_search_query_limits.py apps/log/tests/test_policy_scan_keyword_grouping.py -q
```

Expected:

```text
passed
```

- [ ] **Step 5: 手动验证前端关键路径**

Run:

```bash
cd web && pnpm dev
```

Open `http://localhost:3000/log/event/strategy` and verify:

- 点击「添加」先出现「选择策略类型」弹窗。
- 选择「关键字告警」后进入创建页，页面不展示策略类型切换控件。
- 关键字告警展示「分组字段」，不展示「规则」。
- 选择分组字段后右侧出现 `${level}` 和对应 `${field}` 变量。
- 查询条件为空时日志预览显示引导提示。
- 填写查询条件且选择日志分组后，预览请求最近 10 条日志。
- 编辑已有策略时不能修改策略类型。

- [ ] **Step 6: 最终提交或修正**

如果 Step 1-5 有修正，提交：

```bash
git add server/apps/log web/src/app/log web/scripts/log-policy-form-state-test.ts web/package.json
git commit -m "fix: polish log policy grouping flow"
```

如果没有修正，不创建空提交。

## Self-Review

- Spec coverage: 已覆盖添加入口前置选择、创建后类型不可改、关键字可选分组、未分组旧逻辑、VictoriaLogs `stats by`、变量渲染、日志预览、校验、兼容性、测试策略。
- Completeness scan: 计划中没有未完成内容或跨任务省略说明。
- Type consistency: 前端统一使用 `alert_type`、`group_by`、`show_fields`、`alert_condition.rule`；后端统一使用 `group_by`、`total_count`、`source_id = policy_{policy.id}_{group_key}`。
