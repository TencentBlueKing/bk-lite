# 探索记忆：供应商详情页模型 Team 过滤问题

Status: cancelled

## Migration Context

非标准旧 artifact，原路径为 `openspec/changes/archive/2026-05-11-provider-model-team-filter/exploration.md`。完整内容保留如下。

## 问题背景

用户反馈供应商页面存在"配置链路"和"数据链路"混用异常：

1. **供应商列表页** (`/opspilot/provider`) 按用户当前组(team)筛选供应商，显示 "DeepSeek - 2个模型"
2. **供应商详情页** (`/opspilot/provider/detail?id=8&tab=models`) 进入后看不到模型，因为模型被 team 过滤了
3. **Skill 设置页** (`/opspilot/skill/detail/settings`) 选择 LLM 时也受 team 过滤影响

**根本原因**：供应商(ModelVendor)和模型(LLMModel/EmbedProvider/RerankProvider/OCRProvider)各自有独立的 `team` 字段，允许不同 team。

---

## 代码分析

### 数据模型 (`server/apps/opspilot/models/model_provider_mgmt.py`)

```
ModelVendor                          LLMModel / EmbedProvider / ...
├── id                               ├── id
├── name                             ├── name
├── vendor_type                      ├── vendor (FK → ModelVendor)
├── team: JSONField (list)  ◄───┐    ├── team: JSONField (list)  ◄── 独立的 team！
└── ...                         │    └── ...
                                │
                                └── 供应商和模型的 team 可以不同
```

### 后端 ViewSet

| ViewSet | 文件路径 | team 过滤 |
|---------|----------|-----------|
| ModelVendorViewSet | `server/apps/opspilot/viewsets/model_vendor_view.py` | 继承 LanguageViewSet，list 时不过滤 team |
| LLMModelViewSet | `server/apps/opspilot/viewsets/llm_view.py` (line 409) | 继承 AuthViewSet，调用 `query_by_groups()` 过滤 team |
| EmbedProviderViewSet | `server/apps/opspilot/viewsets/embed_view.py` | 继承 AuthViewSet，调用 `query_by_groups()` 过滤 team |
| RerankProviderViewSet | `server/apps/opspilot/viewsets/rerank_view.py` | 继承 AuthViewSet，调用 `query_by_groups()` 过滤 team |
| OCRProviderViewSet | `server/apps/opspilot/viewsets/ocr_view.py` | 继承 AuthViewSet，调用 `query_by_groups()` 过滤 team |

### Team 过滤核心逻辑 (`server/apps/core/utils/viewset_utils.py`)

```python
class AuthViewSet(MaintainerViewSet):
    ORGANIZATION_FIELD = "team"

    def query_by_groups(self, request, queryset):
        new_queryset = self.get_queryset_by_permission(request, queryset)
        return self._list(new_queryset.order_by(self.ORDERING_FIELD))

    def filter_by_group(cls, queryset, request, user):
        current_team = cls._parse_current_team_cookie(request)
        # 过滤: team__contains=current_team
        query = Q(**{f"{org_field}__contains": current_team})
        return current_team, include_children, org_field, query
```

### 前端调用链

```
modelManagement.tsx
    │
    │ fetchModels(type, { vendor: vendorId })
    ▼
provider.ts API
    │
    │ GET /opspilot/model_provider_mgmt/{type}/?vendor={id}
    ▼
后端 ViewSet.list()
    │
    │ query_by_groups() → 按 team 过滤
    ▼
返回: 只有当前 team 可见的模型
```

### 供应商列表页 model_count 统计问题

`model_vendor_view.py` line 25-33:
```python
def list(self, request, *args, **kwargs):
    # ...
    for provider_model_class in (LLMModel, EmbedProvider, OCRProvider, RerankProvider):
        provider_counts = dict(
            provider_model_class.objects.filter(enabled=True)  # 没有 team 过滤！
            .values("vendor_id")
            .annotate(count=models.Count("id"))
            .values_list("vendor_id", "count")
        )
```

---

## 产品设计决策

**配置链路 vs 数据链路**：

| 场景 | 页面 | Team 过滤行为 | 原因 |
|------|------|---------------|------|
| 配置场景 | 供应商详情页 | 不过滤模型的 team | 管理员需要看到该供应商下所有模型进行配置 |
| 使用场景 | Skill 设置页 | 过滤模型的 team | 用户只能选择有权限使用的模型 |

**模型的 team = 使用权限**，不是归属权限。

---

## 确定的改造方案

### 后端：新增 `by_vendor` action

在 4 个 ViewSet 中新增 action，用于配置场景：

```python
@action(methods=["GET"], detail=False)
def by_vendor(self, request):
    """按供应商查询模型（配置场景，不过滤模型的 team）

    安全控制：验证用户对该供应商有权限（vendor.team 包含 current_team）
    """
    vendor_id = request.query_params.get('vendor')
    if not vendor_id:
        return JsonResponse({"result": False, "message": "vendor is required"})

    # 获取用户可见的 team 列表
    query_groups = self.get_query_groups(request)

    # 过滤：vendor_id + vendor.team 包含用户的 team（安全校验）
    # 不过滤模型自身的 team（配置场景展示所有模型）
    queryset = self.get_queryset().filter(vendor_id=vendor_id)

    # 验证供应商权限
    team_filter = Q()
    for team_id in query_groups:
        team_filter |= Q(vendor__team__contains=team_id)
    queryset = queryset.filter(team_filter)

    return self._list(queryset.order_by(self.ORDERING_FIELD))
```

**新 API**: `GET /opspilot/model_provider_mgmt/{type}/by_vendor/?vendor={id}`

### 前端改动

1. **API 层** (`web/src/app/opspilot/api/provider.ts`):
   ```typescript
   const fetchModelsByVendor = async (type: string, vendorId: number): Promise<Model[]> => {
     return get(`/opspilot/model_provider_mgmt/${type}/by_vendor/`, { params: { vendor: vendorId } });
   };
   ```

2. **组件** (`web/src/app/opspilot/components/provider/modelManagement.tsx`):
   - 将 `fetchModels(type, { vendor: vendorId })` 改为 `fetchModelsByVendor(type, vendorId)`

### 不改动的部分

- 供应商列表页的 `model_count` 统计保持现状（统计所有 enabled 模型）
- Skill 设置页的模型选择保持现状（按 team 过滤）
- 其他使用场景的模型列表保持现状

---

## 改动文件清单

### 后端 (4 个文件)
- `server/apps/opspilot/viewsets/llm_view.py` - LLMModelViewSet 新增 by_vendor action
- `server/apps/opspilot/viewsets/embed_view.py` - EmbedProviderViewSet 新增 by_vendor action
- `server/apps/opspilot/viewsets/rerank_view.py` - RerankProviderViewSet 新增 by_vendor action
- `server/apps/opspilot/viewsets/ocr_view.py` - OCRProviderViewSet 新增 by_vendor action

### 前端 (2 个文件)
- `web/src/app/opspilot/api/provider.ts` - 新增 fetchModelsByVendor 方法
- `web/src/app/opspilot/components/provider/modelManagement.tsx` - 调用新 API

---

## 安全考虑

1. **防止越权访问**：by_vendor 接口验证 `vendor.team` 包含用户的 `current_team`
2. **不暴露敏感数据**：只返回模型基本信息，不返回 API Key 等敏感字段
3. **复用现有权限体系**：使用 `get_query_groups()` 获取用户可见的 team 列表
