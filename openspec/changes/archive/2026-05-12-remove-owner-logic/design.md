# 设计方案

## 权限模型变更

```
┌─────────────────────────────────────────────────────────────────┐
│                    当前权限模型                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   filter_by_group():                                            │
│     creator_query = Q(created_by=user, domain=domain)           │
│     team_query = Q(team__contains=current_team)                 │
│     query = team_query | creator_query  ← 问题所在              │
│                                                                 │
│   结果: 用户能看到 (组内数据 ∪ 自己创建的数据)                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    目标权限模型                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   filter_by_group():                                            │
│     team_query = Q(team__contains=current_team)                 │
│     query = team_query  ← 只看组                                │
│                                                                 │
│   结果: 用户只能看到组内数据                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 代码变更设计

### 1. viewset_utils.py - filter_by_group()

**当前代码 (L146-164)**:
```python
if "created_by" in fields:
    creator_query = Q(created_by=request.user.username, domain=request.user.domain)
    if include_children:
        # ... 子组逻辑 ...
        query = team_query | creator_query
    else:
        query = Q(**{f"{org_field}__contains": current_team}) | creator_query
elif org_field in fields:
    query = Q(**{f"{org_field}__contains": current_team})
```

**目标代码**:
```python
if include_children:
    # ... 子组逻辑 ...
    query = team_query
else:
    query = Q(**{f"{org_field}__contains": current_team})
```

移除 `created_by` 分支，统一使用 team 查询。

### 2. bot_view.py - update()

**当前代码 (L110-111)**:
```python
if (not request.user.is_superuser) and (obj.created_by != request.user.username):
    data.pop("team", [])
```

**目标**: 删除这两行。有编辑权限即可修改 team。

### 3. llm_view.py - update()

**当前代码 (L150-151)**:
```python
if (not request.user.is_superuser) and (instance.created_by != request.user.username):
    params.pop("team", [])
```

**目标**: 删除这两行。有编辑权限即可修改 team。

### 4. entity-card/index.tsx

**当前代码 (L203)**:
```tsx
text={`${t('common.organization')}: ${...} | ${t('skill.form.owner')}: ${created_by}`}
```

**目标代码**:
```tsx
text={`${t('common.organization')}: ${...}`}
```

移除 `| 所有者: xxx` 部分。

### 5. knowledge/page.tsx

**当前代码 (L236)**:
```tsx
<span>{t('knowledge.form.owner')}: {card.created_by} ｜ {t('common.organization')}: {...}</span>
```

**目标代码**:
```tsx
<span>{t('common.organization')}: {...}</span>
```

移除 `所有者: xxx ｜` 部分。

## 影响分析

| 组件 | 影响 |
|------|------|
| Bot (智能体) | 权限查询、team 编辑、卡片展示 |
| LLMSkill (技能) | 权限查询、team 编辑、卡片展示 |
| KnowledgeBase (知识库) | 权限查询、卡片展示 |
| 其他 AuthViewSet 子类 | 权限查询（全局影响） |

## 风险

1. **全局影响**: `viewset_utils.py` 是通用基类，改动影响所有模块
2. **数据可见性变化**: 部分用户可能突然看不到自己创建但不在当前组的数据

## 测试要点

1. 创建者在组内 → 能看到数据 ✓
2. 创建者被移出组 → 看不到数据 ✓
3. 非创建者在组内 → 能看到数据 ✓
4. 非创建者有编辑权限 → 能修改 team ✓
5. 卡片不显示所有者 ✓
