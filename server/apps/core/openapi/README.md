# OpenAPI 统一网关 · 开发者指南

如何把一个内部函数暴露为对外 API。契约全文见
`specs/changes/openapi-unified-gateway/`（design.md 第 8 章为冻结清单），
本文是操作指引。

## 暴露一个 API 的四步

### 1. 写暴露专用 serializer

放在 `apps/<app>/openapi_serializers.py`，继承本包基类，**禁止复用内部业务
serializer、禁止 `fields = "__all__"`**：

```python
from apps.core.openapi.serializers import PaginatedRequestSerializer

class ModuleDataQuerySerializer(PaginatedRequestSerializer):
    module = serializers.ChoiceField(choices=["patch_target"])
    group_id = serializers.IntegerField(min_value=1)
```

- 基类已内建：未知字段拒绝（客户端身份字段无法混入）、`page`/`page_size`
  钳制（默认 20、上限 500）；
- 字段名一经发布即为对外契约：只能新增可选字段，不得改名 / 收紧 / 删除；
- **组织概念的字段命名须过命名评审**（见下文评审 checklist）。

### 2. 叠加装饰器

```python
@nats_client.register
@openapi_expose(
    path="patch-mgmt/module-data",   # service/sub-path，发布后永久固定
    method="GET",                     # GET 走 query string；写方法走 JSON body
    schema=ModuleDataQuerySerializer, # 必填
    inject="team_list",               # 或 "user_info"（锚点式）；见下
    permission="patch_mgmt-View",     # 可选；声明时必须同时给 permission_app
    permission_app="patch",
    summary="一句话说明（含组织口径：是否级联子组织）",
)
def get_patch_mgmt_module_data(..., *, team=None):
    ...
```

`inject` 二选一（与函数的组织参数协议匹配）：

| inject | 函数期待 | 网关注入 | 适用 |
| --- | --- | --- | --- |
| `team_list` | `*, team=None`（授权组织 id 集合） | API 令牌 → `[绑定组织]`；JWT → 用户全部直属组织 | 函数按注入集合精确过滤（patch_mgmt 型） |
| `user_info` | `user_info=None`（`{user, domain, team, include_children}`） | 仅注入认证身份；组织锚点为业务参数（API 令牌下强制覆盖为绑定组织） | 函数自查 group_list 做级联展开（cmdb 型） |

无组织维度数据的公共元信息接口可声明 `team_free=True`（须附「响应不含
组织字段」断言测试并经安全评审）。

任何契约缺失（缺 schema / 缺 inject / 身份参数缺失 / path 违规 / 重复注册）
都会在 **server 启动时报错**（fail-closed），不会静默放过。

### 3. 写双租户测试并登记（合并的硬性门禁）

为端点编写双租户测试（两个组织身份分别调用，断言读隔离与写归属；
测试基建见 `apps/core/openapi/testing.py`），然后登记到
`apps/core/openapi/tests/tenant_coverage.py`：

```python
TENANT_ISOLATION_COVERAGE = {
    "patch-mgmt/module-data": [
        "apps.core.openapi.tests.test_gateway::test_tenant_cannot_read_other_org",
    ],
}
```

未登记或引用失效时 `test_governance.py` 失败，CI 拒绝合并。

### 4. 过评审 checklist

`@openapi_expose` 与暴露 serializer 的任何变更须经 API 设计责任人评审：

- [ ] schema 字段命名与全平台一致（组织概念统一字段名，不透传内部 NATS 字段名）；
- [ ] 每条查询经过组织过滤（team helper / 级联展开），写操作校验目标归属；
- [ ] 已发布字段未被改名 / 收紧 / 删除（破坏性变更须以新 path 发布）；
- [ ] 函数短耗时、强制分页；长任务已拆分为「提交 + 查询」；
- [ ] 双租户测试已登记；`team_free` 有豁免理由与断言测试；
- [ ] summary 写明组织口径（是否级联子组织）。

## 本包结构

| 模块 | 职责 |
| --- | --- |
| `envelope.py` | 统一响应 / 错误码枚举（对外冻结，只增不改） |
| `registry.py` / `decorators.py` | 端点注册表与 `@openapi_expose`（fail-closed） |
| `identity.py` | 双凭据形态路由（API 令牌 / JWT，复用平台现有认证） |
| `dispatcher.py` | 权限位 → schema 校验 → 身份注入 → 强制超时 → envelope |
| `views.py` / `urls.py` | invoke、`_me`、`_docs`、`_auth`（ForwardAuth）、`_provider/traefik` |
| `kv.py` / `renderer.py` | 外部服务注册表（NATS KV）读取与 Traefik 动态配置渲染 |
| `serializers.py` | 暴露专用 serializer 基类（未知字段拒绝、分页钳制） |
| `testing.py` | 双租户测试基建 |

## 运行期配置（env）

| 变量 | 说明 |
| --- | --- |
| `OPENAPI_INVOKE_TIMEOUT` | invoke 强制超时秒数；0（默认）同步执行，生产须显式配置 |
| `OPENAPI_PROVIDER_TOKEN` | provider 端点共享令牌；未配置时端点 503（fail-closed） |
| `OPENAPI_AUTH_ADDRESS` | Traefik ForwardAuth 回调地址；未配置时不渲染外部路由 |
| `OPENAPI_BASEURL_ALLOWLIST` | 外部服务 base_url 允许清单（逗号分隔 host 后缀；未配置拒绝一切） |
