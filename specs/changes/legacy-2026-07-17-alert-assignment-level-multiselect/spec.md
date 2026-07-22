# Historical Superpowers change: 2026-07-17-alert-assignment-level-multiselect

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-17-alert-assignment-level-multiselect.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 仅在告警分派策略中支持“级别”的等于/不等于多选，并保持历史单值规则和其他规则页面行为不变。

**Architecture:** 告警分派通过共享规则组件的显式开关启用级别多选，前端以数组保存选择。后端通用 `RuleMatcher` 让 `eq/ne` 同时兼容标量和非空数组，告警分派序列化器拒绝空级别数组；其他页面不启用该开关。

**Tech Stack:** Python 3.12、Django 4.2、Django REST Framework、pytest；Next.js 16、React 19、TypeScript、Ant Design、tsx、node:assert、pnpm。

## Global Constraints

- 仅修改告警分派级别筛选 UI；屏蔽、富化、告警处理和其他规则页面保持现状。
- `eq [a, b]` 等价于 `level = a OR level = b`。
- `ne [a, b]` 等价于 `level != a AND level != b`。
- 历史标量 `eq/ne` 继续执行，并回显为单项多选。
- 空数组不能提交；后端匹配器对异常空数组 fail-closed。
- 不新增数据库迁移或依赖，不使用原生 SQL。
- 严格 TDD，只格式化触及文件。

## 文件结构

- `server/apps/alerts/utils/rule_matcher.py`：标量/数组规则到 ORM `Q` 的唯一转换点。
- `server/apps/alerts/tests/test_utils.py`：数组匹配与标量回归。
- `server/apps/alerts/serializers/assignment_shield.py`：分派 API 空数组校验。
- `server/apps/alerts/tests/test_assignment_config_validation.py`：分派序列化边界测试。
- `server/apps/alerts/tests/test_assignment.py`：真实自动分派链路测试。
- `web/src/app/alarm/(pages)/settings/components/matchRuleValue.ts`：值规范化和空值判断纯函数。
- `web/src/app/alarm/(pages)/settings/components/matchRule.tsx`：显式能力开关和多选渲染。
- `web/src/app/alarm/(pages)/settings/alertAssign/components/operateModal.tsx`：唯一启用该能力的入口。
- `web/scripts/alert-assignment-level-multiselect-test.ts`：tsx 定向行为测试。
- `web/package.json`：定向测试命令。

---

### Task 1: 通用规则匹配器兼容数组

**Files:**
- Modify: `server/apps/alerts/utils/rule_matcher.py:131-176`
- Test: `server/apps/alerts/tests/test_utils.py:117-183`

**Interfaces:**
- Consumes: `{key, operator, value}` 和现有 `field_mapping`。
- Produces: `RuleMatcher.build_single_rule_q(rule) -> Optional[Q]`；数组 `eq/ne` 使用 `__in`，空数组返回 `None`，标量不变。

- [ ] **Step 1: 写失败测试**

在 `test_utils.py` 增加：

```python
@pytest.mark.django_db
def test_rule_matcher_eq_list_matches_any_selected_value():
    from apps.alerts.models.models import Level

    critical = Level.objects.create(level_id=0, level_name="Critical", level_display_name="致命", level_type="alert")
    error = Level.objects.create(level_id=1, level_name="Error", level_display_name="错误", level_type="alert")
    warning = Level.objects.create(level_id=2, level_name="Warning", level_display_name="预警", level_type="alert")
    matcher = RuleMatcher({"level": "level_id"})

    ids = matcher.filter_queryset(
        Level.objects.all(),
        [[{"key": "level", "operator": "eq", "value": ["0", "1"]}]],
    )

    assert set(ids) == {critical.id, error.id}
    assert warning.id not in ids


@pytest.mark.django_db
def test_rule_matcher_ne_list_excludes_every_selected_value():
    from apps.alerts.models.models import Level

    critical = Level.objects.create(level_id=0, level_name="Critical", level_display_name="致命", level_type="alert")
    error = Level.objects.create(level_id=1, level_name="Error", level_display_name="错误", level_type="alert")
    warning = Level.objects.create(level_id=2, level_name="Warning", level_display_name="预警", level_type="alert")
    matcher = RuleMatcher({"level": "level_id"})

    ids = matcher.filter_queryset(
        Level.objects.all(),
        [[{"key": "level", "operator": "ne", "value": ["0", "1"]}]],
    )

    assert ids == [warning.id]
    assert critical.id not in ids
    assert error.id not in ids


def test_rule_matcher_empty_list_is_invalid():
    matcher = RuleMatcher({"level": "level"})
    assert matcher.build_single_rule_q({"key": "level", "operator": "eq", "value": []}) is None
    assert matcher.build_single_rule_q({"key": "level", "operator": "ne", "value": []}) is None
```

- [ ] **Step 2: 运行测试确认 RED**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_utils.py -k 'rule_matcher_eq_list or rule_matcher_ne_list or rule_matcher_empty_list' -q
```

Expected: 3 项失败；当前代码把列表当标量，且空数组未在构造阶段 fail-closed。

- [ ] **Step 3: 写最小实现**

在读取 `value` 后增加空数组保护，并替换 `eq/ne` 分支：

```python
        if isinstance(value, list) and not value:
            logger.warning("[AlertUtil] 规则值数组不能为空: %s", rule)
            return None

        try:
            if operator == "eq":
                if isinstance(value, list):
                    return Q(**{f"{model_field}__in": value})
                return Q(**{model_field: value})
            elif operator == "ne":
                if isinstance(value, list):
                    return ~Q(**{f"{model_field}__in": value})
                return ~Q(**{model_field: value})
```

保留 `contains/not_contains/re` 原代码；本次不让它们接收数组。

- [ ] **Step 4: 运行 RuleMatcher 回归确认 GREEN**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_utils.py -k rule_matcher -q
```

Expected: 新旧 RuleMatcher 测试全部通过。

- [ ] **Step 5: 提交**

```bash
git add server/apps/alerts/utils/rule_matcher.py server/apps/alerts/tests/test_utils.py
git commit -m "feat: 支持告警规则多值等于匹配"
```

---

### Task 2: 分派 API 校验与真实链路

**Files:**
- Modify: `server/apps/alerts/serializers/assignment_shield.py:7-29`
- Test: `server/apps/alerts/tests/test_assignment_config_validation.py`
- Test: `server/apps/alerts/tests/test_assignment.py:54-79`

**Interfaces:**
- Consumes: Task 1 的数组匹配语义。
- Produces: `AlertAssignmentModelSerializer.validate_match_rules(value)`；仅拒绝级别空数组，其他历史结构原样返回。

- [ ] **Step 1: 写序列化器失败测试**

让 `_payload` 接收覆盖字段，并增加：

```python
def _payload(escalation, **overrides):
    payload = {
        "name": "r1",
        "match_type": "all",
        "notify_channels": [{"id": 1, "channel_type": "email", "name": "邮件"}],
        "personnel": ["u1"],
        "config": {"escalation": escalation},
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_assignment_rejects_empty_level_value_list():
    serializer = AlertAssignmentModelSerializer(data=_payload(
        {"enabled": False},
        match_type="filter",
        match_rules=[[{"key": "level", "operator": "eq", "value": []}]],
    ))
    assert not serializer.is_valid()
    assert serializer.errors["match_rules"][0] == "级别至少选择一个值"


@pytest.mark.django_db
def test_assignment_accepts_non_empty_level_value_list():
    serializer = AlertAssignmentModelSerializer(data=_payload(
        {"enabled": False},
        match_type="filter",
        match_rules=[[{"key": "level", "operator": "ne", "value": ["0", "1"]}]],
    ))
    assert serializer.is_valid(), serializer.errors
```

- [ ] **Step 2: 运行序列化测试确认 RED**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_assignment_config_validation.py -q
```

Expected: 空数组用例失败，因为当前序列化器接受该 JSON。

- [ ] **Step 3: 实现专用输入校验**

在 `AlertAssignmentModelSerializer` 加入：

```python
    def validate_match_rules(self, value):
        for group in value or []:
            for rule in group or []:
                if (
                    rule.get("key") == "level"
                    and isinstance(rule.get("value"), list)
                    and not rule["value"]
                ):
                    raise serializers.ValidationError("级别至少选择一个值")
        return value
```

不要把该校验放到 `AlertShieldModelSerializer`。

- [ ] **Step 4: 写真实分派链路测试**

在 `test_assignment.py` 增加两个测试；`eq` 应分派 A1/A2，`ne` 应仅分派 A3：

```python
@pytest.mark.django_db
def test_auto_assignment_level_eq_list_matches_any_selected_level(sys_user):
    _make_alert("A1", level="0")
    _make_alert("A2", level="1")
    _make_alert("A3", level="2")
    _make_assignment(match_type="filter", match_rules=[[
        {"key": "level", "operator": "eq", "value": ["0", "1"]}
    ]])

    AlertAssignmentOperator(["A1", "A2", "A3"]).execute_auto_assignment()

    assert Alert.objects.get(alert_id="A1").status == AlertStatus.PENDING
    assert Alert.objects.get(alert_id="A2").status == AlertStatus.PENDING
    assert Alert.objects.get(alert_id="A3").status == AlertStatus.UNASSIGNED


@pytest.mark.django_db
def test_auto_assignment_level_ne_list_excludes_all_selected_levels(sys_user):
    _make_alert("A1", level="0")
    _make_alert("A2", level="1")
    _make_alert("A3", level="2")
    _make_assignment(match_type="filter", match_rules=[[
        {"key": "level", "operator": "ne", "value": ["0", "1"]}
    ]])

    AlertAssignmentOperator(["A1", "A2", "A3"]).execute_auto_assignment()

    assert Alert.objects.get(alert_id="A1").status == AlertStatus.UNASSIGNED
    assert Alert.objects.get(alert_id="A2").status == AlertStatus.UNASSIGNED
    assert Alert.objects.get(alert_id="A3").status == AlertStatus.PENDING
```

这些集成测试只依赖 Task 1，不在分派服务复制匹配逻辑。

- [ ] **Step 5: 运行分派回归确认 GREEN**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_assignment.py apps/alerts/tests/test_assignment_config_validation.py apps/alerts/tests/test_utils.py -k 'assignment or rule_matcher' -q
```

Expected: 新数组语义、序列化校验和既有分派回归全部通过。

- [ ] **Step 6: 提交**

```bash
git add server/apps/alerts/serializers/assignment_shield.py server/apps/alerts/tests/test_assignment_config_validation.py server/apps/alerts/tests/test_assignment.py
git commit -m "test: 覆盖告警分派级别多选"
```

---

### Task 3: 分派前端启用级别多选

**Files:**
- Create: `web/src/app/alarm/(pages)/settings/components/matchRuleValue.ts`
- Modify: `web/src/app/alarm/(pages)/settings/components/matchRule.tsx:18-29,32-62,158-213`
- Modify: `web/src/app/alarm/(pages)/settings/alertAssign/components/operateModal.tsx:1-17,271-313`
- Create: `web/scripts/alert-assignment-level-multiselect-test.ts`
- Modify: `web/package.json:5-55`

**Interfaces:**
- Consumes: Ant Design `Select mode="multiple"` 和现有 `onChange(PolicyItem[][])`。
- Produces: `enableLevelMultiSelect?: boolean`；纯函数 `normalizeMultipleRuleValue`、`isEmptyMatchRuleValue`、`isLevelMultiSelectEnabled`。

- [ ] **Step 1: 写前端失败测试并注册命令**

创建 `web/scripts/alert-assignment-level-multiselect-test.ts`：

```typescript
import assert from 'node:assert/strict';
import {
  LEVEL_MULTI_OPERATOR_OPTIONS,
  isEmptyMatchRuleValue,
  isLevelMultiSelectEnabled,
  normalizeMultipleRuleValue,
} from '../src/app/alarm/(pages)/settings/components/matchRuleValue';

assert.deepEqual(normalizeMultipleRuleValue('0'), ['0']);
assert.deepEqual(normalizeMultipleRuleValue(['0', '1']), ['0', '1']);
assert.deepEqual(normalizeMultipleRuleValue(undefined), []);
assert.equal(isEmptyMatchRuleValue([]), true);
assert.equal(isEmptyMatchRuleValue('0'), false);
assert.equal(isLevelMultiSelectEnabled('level', true), true);
assert.equal(isLevelMultiSelectEnabled('title', true), false);
assert.deepEqual(LEVEL_MULTI_OPERATOR_OPTIONS, [
  { name: 'eq', desc: '等于' },
  { name: 'ne', desc: '不等于' },
]);
console.log('alert assignment level multiselect validation passed');
```

在 `web/package.json` scripts 增加：

```json
"test:alert-assignment-level-multiselect": "pnpm exec tsx scripts/alert-assignment-level-multiselect-test.ts"
```

- [ ] **Step 2: 运行确认 RED**

Run: `cd web && pnpm test:alert-assignment-level-multiselect`

Expected: FAIL，提示 `matchRuleValue` 模块不存在。

- [ ] **Step 3: 实现纯函数**

创建 `matchRuleValue.ts`：

```typescript
export type MatchRuleScalar = string | number;
export type MatchRuleValue = MatchRuleScalar | MatchRuleScalar[] | undefined;

export const LEVEL_MULTI_OPERATOR_OPTIONS = [
  { name: 'eq', desc: '等于' },
  { name: 'ne', desc: '不等于' },
] as const;

export const isLevelMultiSelectEnabled = (
  key: string | undefined,
  enabled: boolean,
) => enabled && key === 'level';

export const normalizeMultipleRuleValue = (
  value: MatchRuleValue,
): MatchRuleScalar[] => {
  if (value === undefined || value === '') return [];
  return Array.isArray(value) ? value : [value];
};

export const isEmptyMatchRuleValue = (value: MatchRuleValue) =>
  value === undefined ||
  value === '' ||
  (Array.isArray(value) && value.length === 0);
```

Run: `cd web && pnpm test:alert-assignment-level-multiselect`

Expected: PASS，输出成功消息。

- [ ] **Step 4: 扩展共享组件但默认关闭**

在 `matchRule.tsx` 导入工具，把 `PolicyItem.value` 改为 `MatchRuleValue`，并给 `MatchRuleProps` 增加：

```typescript
enableLevelMultiSelect?: boolean;
```

解构参数时设置 `enableLevelMultiSelect = false`。保持当前规则行的隐式返回结构，直接把操作符列表表达式替换为：

```tsx
{(
  isLevelMultiSelectEnabled(i.key, enableLevelMultiSelect)
    ? LEVEL_MULTI_OPERATOR_OPTIONS
    : ((conditionOptions || initialConditionLists)[i.key as string] || [])
).map((item) => (
  <Option key={item.name} value={item.name}>
    {item.desc}
  </Option>
))}
```

操作符 Select 使用 `operatorOptions`；切换多选级别操作符时执行：

```typescript
const item = updatedPolicyList[index][ind];
item.operator = value;
if (isLevelMultiSelectEnabled(item.key, enableLevelMultiSelect)) {
  item.value = undefined;
}
```

值 Select 增加以下两个属性：

```tsx
mode={
  isLevelMultiSelectEnabled(i.key, enableLevelMultiSelect)
    ? 'multiple'
    : undefined
}
value={
  isLevelMultiSelectEnabled(i.key, enableLevelMultiSelect)
    ? normalizeMultipleRuleValue(i.value)
    : i.value
}
```

不要修改全局 `initialConditionLists.level`。

- [ ] **Step 5: 仅在分派入口启用并校验空数组**

在分派 `operateModal.tsx` 导入 `isEmptyMatchRuleValue`，把值校验改为：

```typescript
if (!item.key || !item.operator || isEmptyMatchRuleValue(item.value)) {
  return Promise.reject(new Error(t('common.inputTip')));
}
```

仅在分派调用传入开关：

```tsx
<MatchRule
  levelType="alert"
  enableLevelMultiSelect
  ruleOptions={ruleList.filter(
    (item) => item.name !== 'location' && item.name !== 'service'
  )}
/>
```

- [ ] **Step 6: 运行前端验证**

```bash
cd web
pnpm test:alert-assignment-level-multiselect
pnpm lint
pnpm type-check
```

Expected: 定向脚本、ESLint、TypeScript 均退出码 0。

- [ ] **Step 7: 提交**

```bash
git add web/package.json web/scripts/alert-assignment-level-multiselect-test.ts 'web/src/app/alarm/(pages)/settings/components/matchRuleValue.ts' 'web/src/app/alarm/(pages)/settings/components/matchRule.tsx' 'web/src/app/alarm/(pages)/settings/alertAssign/components/operateModal.tsx'
git commit -m "feat: 告警分派支持级别多选"
```

---

### Task 4: 最终回归

**Files:**
- Verify only: Tasks 1-3 的全部触及文件。

**Interfaces:**
- Consumes: 后端数组匹配、分派校验、前端能力开关。
- Produces: 可交付验证证据，不新增接口。

- [ ] **Step 1: 运行 Alerts 聚焦回归**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=:memory: uv run pytest -o addopts='' --nomigrations apps/alerts/tests/test_utils.py apps/alerts/tests/test_assignment.py apps/alerts/tests/test_assignment_config_validation.py apps/alerts/tests/test_shield.py -q
```

Expected: 全部通过；`test_shield.py` 保护共享匹配器的标量调用。

- [ ] **Step 2: 运行触及 Python 文件静态门禁**

```bash
cd server
uv run black --check apps/alerts/utils/rule_matcher.py apps/alerts/serializers/assignment_shield.py apps/alerts/tests/test_utils.py apps/alerts/tests/test_assignment.py apps/alerts/tests/test_assignment_config_validation.py
uv run isort --check-only apps/alerts/utils/rule_matcher.py apps/alerts/serializers/assignment_shield.py apps/alerts/tests/test_utils.py apps/alerts/tests/test_assignment.py apps/alerts/tests/test_assignment_config_validation.py
uv run flake8 apps/alerts/utils/rule_matcher.py apps/alerts/serializers/assignment_shield.py apps/alerts/tests/test_utils.py apps/alerts/tests/test_assignment.py apps/alerts/tests/test_assignment_config_validation.py
```

Expected: 三项均退出码 0；失败时只格式化列出的触及文件。

- [ ] **Step 3: 重跑 Web 门禁**

```bash
cd web
pnpm test:alert-assignment-level-multiselect
pnpm lint
pnpm type-check
```

Expected: 三项均退出码 0。

- [ ] **Step 4: 检查最终边界**

```bash
git diff --check HEAD~3..HEAD
git status --short
```

Expected: diff check 无输出；仅允许任务开始前已有的 `.pnpm-store/` 与 `.superpowers/brainstorm/` 未跟踪文件。

## specs: 2026-07-17-alert-assignment-level-multiselect-design.md

## 背景

告警分派策略的筛选规则当前仅允许为“级别”选择单个值，且操作符只有“等于”。运维人员需要用一条条件同时覆盖多个告警级别，并需要排除一组级别。

## 范围

本次只修改告警分派策略：

- “级别”值改为多选。
- “级别”操作符支持“等于”和“不等于”。
- 屏蔽、富化、告警处理及其他复用规则组件的页面保持现状。

不扩展其他字段的多选能力，不调整规则组现有的外层 OR、内层 AND 结构。

## 规则语义

- `等于 [致命, 错误]` 表示 `级别 = 致命 OR 级别 = 错误`，命中任一所选级别即可匹配。
- `不等于 [致命, 错误]` 表示 `级别 != 致命 AND 级别 != 错误`，即排除所有所选级别。
- 级别条件至少选择一个值，空数组不能提交。
- 既有单值规则继续有效；编辑时将标量规范化为单项数组回显。

## 方案选择

采用“分派页面开放多选，通用匹配器兼容标量与数组”的方案。

前端只在告警分派入口启用级别多选及 `ne` 选项。后端匹配器为 `eq`、`ne` 增加数组语义：数组 `eq` 使用集合包含匹配，数组 `ne` 对该集合整体取反；标量仍走现有精确匹配逻辑。其他页面不会提交数组，因此行为不变。

未采用以下方案：

- 将一个多选条件展开成多条 OR/AND 规则：会改变用户原始规则结构，编辑回显和复杂规则组合容易失真。
- 在告警分派服务内复制一套数组匹配逻辑：改动边界看似更窄，但会重复通用规则匹配语义，增加长期维护成本。

## 前端设计

共享规则组件增加一个由调用方显式传入的能力开关。只有告警分派表单启用该开关：

- 字段为 `level` 时，Select 使用 `mode="multiple"`。
- `level` 的操作符列表为 `eq` 和 `ne`。
- 历史标量值在展示层转换成单项数组，不在打开抽屉时主动改写服务端数据。
- 切换字段时清空操作符和值；切换级别操作符时清空值，避免标量与数组或旧语义残留。
- 表单校验同时拒绝 `undefined`、空字符串和空数组。

提交结构示例：

```json
{
  "key": "level",
  "operator": "eq",
  "value": ["0", "1"]
}
```

## 后端设计

规则 JSON 字段无需数据库迁移。通用规则匹配器按值类型解释 `eq`、`ne`：

- 标量 `eq`：保持 `Q(field=value)`。
- 标量 `ne`：保持 `~Q(field=value)`。
- 非空数组 `eq`：使用 `Q(field__in=values)`。
- 非空数组 `ne`：使用 `~Q(field__in=values)`。
- 空数组视为无效规则，由输入校验拒绝；匹配器仍采用 fail-closed，避免异常数据意外匹配全部告警。

数组元素沿用现有级别 ID 类型，不引入名称到 ID 的额外转换。

## 兼容性与错误处理

- 历史单值规则的存储和执行语义不变。
- 新数组数据可由更新后的后端执行。
- 非级别字段不在本次前端产生数组值。
- 未知操作符、未知字段、空数组等非法规则继续采用 fail-closed，不返回匹配结果。

## 测试与验收

按 TDD 顺序先增加失败测试，再实现最小修改：

1. 匹配器标量 `eq/ne` 回归测试。
2. 数组 `eq` 命中任一所选级别、排除未选级别。
3. 数组 `ne` 排除所有所选级别、命中其他级别。
4. 空数组 fail-closed。
5. 告警分派执行链使用多级别 `eq/ne` 得到正确分派结果。
6. 前端类型、标量回显规范化、空数组校验与分派入口能力开关测试。
7. 运行 Alerts 定向测试，以及 Web 的 lint 和 type-check 门禁。

验收标准：用户可在新增或编辑告警分派策略时选择多个级别；保存后重新打开能正确回显；实际自动分派符合本设计的 OR/AND 语义；其他规则页面交互不变。
