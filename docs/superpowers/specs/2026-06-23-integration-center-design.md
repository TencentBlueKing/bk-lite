# 集成中心能力启停与可用实例治理设计

## 背景

集成中心（Integration Center）是 BK-Lite 系统管理模块中管理第三方集成系统实例的入口。当前存在以下体验与架构问题：

1. **能力缺少显式启停开关**：详情页各能力（登录认证 / 用户同步 / IM 通知）只能看到测试状态，无法单独启用或禁用。
2. **未保存配置直接测试会使用旧值**：详情页“保存”与“测试连接”是独立按钮，测试接口只接收 `capability_key`，不接收当前表单值。
3. **能力状态与操作流程不够闭环**：详情页缺少“配置 → 保存 → 启用/禁用 → 测试”的完整操作入口。
4. **卡片列表能力 Tag 表达冗余**：当前卡片同时显示实例级主状态 Tag 和能力 Tag，且能力 Tag 未按 provider manifest 声明的能力过滤。
5. **业务弹窗选项格式不统一**：登录认证、用户同步、IM 通知等页面引用集成实例时，下拉选项只显示 `name`，同名实例难以区分。
6. **可用实例接口重复且可见策略未统一**：三个业务模块各自实现了 `available_instances` 接口，都直接遍历 `IntegrationInstance.objects.all()`，未继承集成中心的访问控制逻辑。

## 设计目标

- 在集成实例上引入能力级启停控制，且不破坏业务模型自身的启用状态。
- 统一可用实例接口，由集成中心提供，业务模块只负责消费。
- 收敛卡片列表的视觉表达，去掉主状态 Tag，按 provider 能力渲染能力 Tag。
- 统一业务弹窗中的集成实例展示格式为 `名称（系统类型）`。
- 明确集成实例能力启停与业务实例启停的分层：
  - 集成实例能力启停 → 决定业务弹窗能否选到该实例
  - 业务实例启停 → 决定外部能否访问到该业务实例

## 关键决策

| 决策项 | 选择 | 原因 |
| --- | --- | --- |
| 能力启停存储方式 | 新增 `capability_enabled` JSONField，保留现有 `capability_status` | 能力数量少（最多 3 个），JSONField 足够；比统一 `capabilities` JSONField 改动小，比关系表更轻量 |
| Migration 策略 | 直接修改 `0034_integrationinstance.py`，不新增 migration | 线上共享数据库当前只到 `0033`，`0034` 尚未上线；本地开发者需回滚重建 |
| 可用实例接口 | 由 `IntegrationInstanceViewSet` 统一提供，业务模块删除重复实现 | 消除三处重复代码，统一过滤规则和展示字段 |
| 组织隔离 | `available_instances` 不过滤 `team` | 创建/编辑弹窗没有组织选择入口，原型也未体现；等入口明确后再补 |
| 内建 provider | 在 `available_instances` 中排除 `bk_lite_builtin` | 内建账户体系不应作为第三方集成系统被业务模块引用 |
| 未保存配置测试 | 弹窗提示“请先保存” | 不改变数据库状态，也不引入临时配置测试接口，实现最简单 |

## 数据模型

### IntegrationInstance 变更

在 `server/apps/system_mgmt/models/integration_instance.py` 中新增字段：

```python
class IntegrationInstance(MaintainerInfo, TimeInfo, EncryptMixin):
    name = models.CharField(max_length=100)
    provider_key = models.CharField(max_length=64, db_index=True)
    config = models.JSONField(default=dict)
    status = models.CharField(
        max_length=32,
        choices=IntegrationInstanceStatusChoices.choices,
        default=IntegrationInstanceStatusChoices.PENDING_VERIFICATION,
    )
    capability_status = models.JSONField(default=dict)
    capability_enabled = models.JSONField(default=dict)  # 新增
    enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")
    team = models.JSONField(default=list)
```

`capability_enabled` 结构示例：

```json
{
  "login_auth": true,
  "user_sync": false,
  "im_notification": true
}
```

约束：

- key 必须为 provider manifest 声明的能力。
- 创建实例时，声明的能力默认 `enabled=true`。
- 未声明的能力不会出现；不存在的 key 视为 `false`。

### Migration 说明

直接修改 `server/apps/system_mgmt/migrations/0034_integrationinstance.py`，将 `capability_enabled` 字段加入 `IntegrationInstance` 的 `fields` 列表。

> 注意：线上共享数据库当前仅应用至 `0033`，因此修改 `0034` 不会影响线上。本地已应用 `0034` 的环境需回滚后重建：
>
> ```bash
> cd server
> uv run python manage.py migrate system_mgmt 0033
> uv run python manage.py migrate
> ```

## API 设计

### 统一可用实例接口

在 `IntegrationInstanceViewSet` 中新增 `available_instances` action：

```python
@action(methods=["GET"], detail=False)
@HasPermission("integration_center-View")
def available_instances(self, request):
    capability = request.query_params.get("capability")
    if not capability:
        return Response({"result": False, "message": "capability is required"}, status=400)

    queryset = IntegrationInstance.objects.filter(
        enabled=True,
        status=IntegrationInstanceStatusChoices.READY,
    ).exclude(provider_key="bk_lite_builtin")

    instances = []
    for item in queryset.order_by("name", "id"):
        if (
            item.capability_enabled.get(capability) is True
            and item.capability_status.get(capability) == IntegrationInstanceStatusChoices.READY
        ):
            instances.append({
                "id": item.id,
                "name": item.name,
                "provider_key": item.provider_key,
                "display_name": f"{item.name}({item.provider.name})",
            })
    return Response(instances)
```

调用示例：

- `/system_mgmt/integration_instance/available_instances/?capability=login_auth`
- `/system_mgmt/integration_instance/available_instances/?capability=user_sync`
- `/system_mgmt/integration_instance/available_instances/?capability=im_notification`

### 删除业务端重复接口

从以下 ViewSet 中移除 `available_instances` action：

- `server/apps/system_mgmt/viewset/login_auth_binding_viewset.py`
- `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`
- `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`

前端三个业务弹窗统一改调集成中心接口。

### 序列化器更新

在 `IntegrationInstanceSerializer` 中：

1. 新增 `display_name` 只读字段：

```python
display_name = serializers.SerializerMethodField()

def get_display_name(self, obj):
    return f"{obj.name}({obj.provider.name})"
```

2. 允许读写 `capability_enabled`，并在 `validate` 中校验 key 属于 provider manifest 声明的能力范围。

返回示例：

```json
{
  "id": 1,
  "name": "总部通讯录",
  "display_name": "总部通讯录（飞书）",
  "provider_key": "feishu",
  "provider": {"key": "feishu", "name": "飞书"},
  "status": "ready",
  "capability_status": {
    "login_auth": "ready",
    "user_sync": "ready",
    "im_notification": "pending_verification"
  },
  "capability_enabled": {
    "login_auth": true,
    "user_sync": true,
    "im_notification": false
  }
}
```

### 能力启停更新

复用现有的 `PUT /system_mgmt/integration_instance/{id}/` 接口。前端传：

```json
{
  "capability_enabled": {
    "login_auth": false,
    "user_sync": true,
    "im_notification": true
  }
}
```

后端行为：

- 校验 `capability_enabled` 的 key 必须在 provider manifest 声明的能力范围内。
- 切换 `enabled` 不影响 `capability_status`。
- 从 `false` 切回 `true` 时，保持禁用前的测试状态（ready 则立即可用）。

## 前端设计

### 详情页能力 Tab 底部操作区

参考原型布局：

```
测试状态：● 待测试    平台状态：● 未启用    [保存配置] [测试连接] [启用能力]
```

交互规则：

- **测试状态**：根据 `capability_status[capability]` 映射为“待测试 / 已就绪 / 测试失败”。
- **平台状态**：根据 `capability_enabled[capability]` 映射为“已启用 / 未启用”。
- **启用能力 / 禁用能力**：点击后调用 `updateInstance` 更新 `capability_enabled`。
- **测试连接**：点击前检测当前表单是否 dirty，若存在未保存修改则弹窗提示“请先保存配置”，不调用测试接口。

### 卡片列表

- 去掉 `buildIntegrationInstanceCardItem` 生成的主状态 Tag。
- 只渲染 provider manifest 声明的能力 Tag。
- Tag 颜色：
  - **绿色**：`capability_enabled == true` 且 `capability_status == ready`
  - **灰色**：其它任何状态
- 卡片主标题保持 `name`，副标题保持 `provider.name`；或考虑使用 `display_name` 替代主标题（待实现时确认）。

### 业务弹窗下拉选项

- 改调统一接口 `/system_mgmt/integration_instance/available_instances/?capability=xxx`。
- 选项文案使用 `display_name`，格式为 `名称（系统类型）`。
- 不展示 `bk_lite_builtin` 内建实例。

## 状态流转

| 场景 | 行为 |
| --- | --- |
| 创建实例 | 根据 provider manifest 创建 `capability_enabled=true`，`capability_status=pending_verification` |
| 禁用能力 | `capability_enabled=false`，`capability_status` 保持不变 |
| 重新启用能力 | `capability_enabled=true`，`capability_status` 保持禁用前状态 |
| 基础连接配置变化 | 所有能力 `capability_status=pending_verification` |
| 某能力配置变化 | 仅该能力 `capability_status=pending_verification` |

## 测试策略

### 后端

- `test_integration_instance_serializer.py`：覆盖 `capability_enabled` 的序列化/反序列化、key 校验、默认值。
- 新增/更新 `test_integration_instance_viewset.py`：覆盖 `available_instances` 过滤逻辑（`enabled`、`status`、`capability_enabled`、`capability_status`、排除内建 provider）。
- 更新 `test_builtin_platform_login_auth.py` 等相关测试：确认内建 provider 不在 `available_instances` 中。

### 前端

- 更新 `types/integration-center.ts` 中的 `IntegrationInstance` 类型，增加 `capability_enabled`。
- 运行 `pnpm type-check` 确保所有消费点类型正确。
- 更新详情页、卡片列表、业务弹窗的相关单元测试（如有）。

## 影响范围

### 后端文件

- `server/apps/system_mgmt/models/integration_instance.py`
- `server/apps/system_mgmt/migrations/0034_integrationinstance.py`
- `server/apps/system_mgmt/serializers/integration_instance_serializer.py`
- `server/apps/system_mgmt/viewset/integration_instance_viewset.py`
- `server/apps/system_mgmt/viewset/login_auth_binding_viewset.py`
- `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`
- `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`
- 相关测试文件

### 前端文件

- `web/src/app/system-manager/(pages)/integration-center/detail/page.tsx`
- `web/src/app/system-manager/(pages)/integration-center/page.tsx`
- `web/src/app/system-manager/api/integration-center/index.ts`
- `web/src/app/system-manager/types/integration-center.ts`
- `web/src/app/system-manager/utils/intergrationCenter.ts`
- 登录认证 / 用户同步 / IM 通知弹窗中引用集成实例下拉的相关文件

## 后续可扩展项

- 当产品原型给集成实例增加“组织归属”编辑入口后，再在 `available_instances` 中按 `team` 过滤。
- 当能力专属配置增多时，可考虑将能力配置从 `IntegrationInstance.config` 中拆出，迁移到独立模型。
- 当 provider 支持动态能力时，需要重新评估 `capability_enabled` 的 key 管理方式。

## 备注

- 本次设计不涉及登录认证、用户同步、IM 通知业务模型自身的启用状态变更。这些业务模型的 `enabled` 字段继续独立工作。
- 集成实例能力的禁用不会级联禁用下游已创建的业务实例，仅阻止新建业务实例时引用该能力。
