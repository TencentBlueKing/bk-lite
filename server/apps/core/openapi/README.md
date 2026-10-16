# BK-Lite OpenAPI 接口编写指引规范

本文是新增或修改 BK-Lite 内部对外接口的代码级入口，按当前统一网关实现编写。
长期契约以 [OpenAPI capability](../../../../specs/capabilities/openapi-gateway.md) 和
[统一网关设计冻结清单](../../../../specs/changes/openapi-unified-gateway/design.md) 为准；
外部独立 HTTP 服务的注册和部署见 [接入指南](../../../../docs/openapi-gateway/onboarding.md)。
本文不要求新增校验框架或业务抽象，优先复用现有服务函数和权限逻辑。

## 1. 新增接口的最小交付

一个内部接口从编码到可调用，至少完成以下步骤：

1. 确定稳定的 service/path、HTTP 方法、组织范围和人员权限。
2. 在 app 的 `openapi_serializers.py` 定义对外专用请求 Serializer；按实际输出声明响应 Serializer。
3. 在 `openapi_api.py` 等现有接入模块写薄适配函数，以 `@openapi_expose` 显式注册。
4. 确认模块被当前 app 的 `AppConfig.ready()` 或已有导入链加载。
5. 编写真实网关调用、双组织隔离、权限和契约测试，并登记租户测试。
6. 在运行环境检查 `/_docs`、实际请求和响应；若用于 ITSM，再检查其输入子集及输出引用。

不要另开 `open_api` view、独立端口或绕过网关的认证入口。既有 NATS 函数可以继续保留 `@nats_client.register`；仅为 HTTP 暴露的薄适配函数不需要额外注册 NATS。

## 2. 路径、方法和兼容性

- 装饰器 path 写 `service/sub-path`，不包含前导 `/` 或 `/openapi/v1`；调用 URL 为 `/openapi/v1/{path}`。
- service 满足 `^[a-z][a-z0-9-]{0,31}$`；例如应用目录 `job_mgmt` 对外可用 `job-mgmt`。下划线开头是网关保留空间。
- 当前内部注册器支持 `GET`、`POST`、`PUT`、`DELETE`。不要因 ITSM 方法下拉包含 PATCH/HEAD/OPTIONS/ANY 就声明它们；增加网关方法支持需单独评审。
- GET 参数通过 query string，其他已支持方法通过 JSON object body。服务端输入 Serializer 字段名须与函数形参匹配，必要时使用 `param_map`，不能依赖启动检查发现参数错配。
- 已发布 path、请求字段名/类型、错误码语义冻结：请求只新增可选字段，响应允许新增字段；删除、改名或收紧既有字段需新 path 或新版本。
- 同 path 不同 method 分别声明请求与响应契约，并分别测试；登记表按 path 聚合不代表只需测试其中一个方法。

## 3. 请求 Serializer

放在 `server/apps/<app>/openapi_serializers.py`，使用暴露专用类，避免内部页面字段变化影响外部调用。

```python
from rest_framework import serializers

from apps.core.openapi.serializers import OpenAPIRequestSerializer, PaginatedRequestSerializer


class ApplicationQuerySerializer(PaginatedRequestSerializer):
    keyword = serializers.CharField(required=False, default="", allow_blank=True, max_length=128)


class ApplicationCreateSerializer(OpenAPIRequestSerializer):
    application_id = serializers.RegexField(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", max_length=128)
    name = serializers.CharField(max_length=128)
    description = serializers.CharField(required=False, allow_blank=True, max_length=512)
```

要求：

- 继承 `OpenAPIRequestSerializer`，需要分页时继承 `PaginatedRequestSerializer`；未知字段拒绝，不能直接复用内部 ModelSerializer 或使用 `fields = "__all__"`。
- `required=False`、`allow_blank=True`、`allow_null=True` 含义不同，按业务分别声明。默认值必须与业务函数默认行为一致。
- 分页基类默认 page=1、page_size=20，运行时钳制 page≥1、1≤page_size≤500；子类新增 min_value 等约束时，以其实际校验为准。
- 不用不受限的 DictField/JSONField 替代已知固定结构。真实业务确需动态字段时保留其原语义，不能为 ITSM 强行伪造成固定对象。
- 业务规则仍在原服务层执行；只在真实输入边界增加必要校验，不把内部受控数据再逐层重复校验。

## 4. 响应 Serializer 与 envelope

响应类独立定义，只描述函数返回的业务 data；不要再声明一层 result/data。

```python
class ApplicationResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    application_id = serializers.CharField(max_length=128)
    name = serializers.CharField(max_length=128)
    description = serializers.CharField(allow_blank=True, max_length=512)


class ApplicationPageResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField(min_value=0)
    page = serializers.IntegerField(min_value=1)
    page_size = serializers.IntegerField(min_value=1)
    items = ApplicationResponseSerializer(many=True)
```

函数直接返回业务字典，网关将其包装成：

```json
{
  "result": true,
  "data": {
    "count": 0,
    "page": 1,
    "page_size": 20,
    "items": []
  }
}
```

- 新增且需要目录展示或 ITSM 输出引用的接口，应声明准确的 response_schema。
- response_schema 在协议上仍可选；存量端点未声明时目录返回 null，不能因此阻止注册或调用。不要增加“所有端点必须补齐响应”的启动门禁。
- 目录发布的是完整成功响应 Schema，包含 required result/data，result 限定 true；失败响应不属于成功契约。
- 响应根、data 及嵌套 Serializer/数组元素对象允许新增字段，已声明字段的类型、必填、枚举和范围保留。不要手工重新施加递归 additionalProperties=false。
- 响应 Serializer 目前只用于目录投影，不会重新序列化或拦截真实返回。开发者须用实际返回测试保证二者一致；不要宣称仅加声明即可保证运行时响应合规。
- 顶层响应 data 当前按 object 描述，列表放到 items 等对象字段中；不要把顶层 ListSerializer 当作已支持的响应声明方式。

## 5. 注册与薄适配函数

以下示例采用已有 APM 服务函数的签名，说明适配层应做的事情；类名导入按所属 app 调整，不要在其他应用复制 APM 业务实现。

```python
from apps.apm.openapi_service import create_application, list_applications
from apps.core.openapi.decorators import openapi_expose

# 从本 app 的 openapi_serializers 导入上一节四个类。


@openapi_expose(
    path="apm/applications",
    method="GET",
    schema=ApplicationQuerySerializer,
    response_schema=ApplicationPageResponseSerializer,
    inject="team_list_with_user",
    permission="applications-View",
    permission_app="apm",
    summary="分页查询应用（按授权组织精确匹配，不级联子组织）",
)
def openapi_list_applications(page=1, page_size=20, keyword="", *, team=None, user_info=None):
    return list_applications(team=team, page=page, page_size=page_size, keyword=keyword)


@openapi_expose(
    path="apm/applications",
    method="POST",
    schema=ApplicationCreateSerializer,
    response_schema=ApplicationResponseSerializer,
    inject="team_list_with_user",
    permission="applications-Operate",
    permission_app="apm",
    summary="创建应用（绑定授权组织，不级联子组织）",
)
def openapi_create_application(application_id, name, description="", *, team=None, user_info=None):
    return create_application(
        team=team,
        user_info=user_info,
        application_id=application_id,
        name=name,
        description=description,
    )
```

加载示例（已有导入链时不重复添加）：

```python
class ApmConfig(AppConfig):
    # 其他既有属性省略。
    def ready(self):
        import apps.apm.openapi_api  # noqa: F401
```

如果函数对内也被调用，装饰器不改变原函数返回值。不要为了生成文档在 ready 中调用接口、查询外部服务或执行 Schema 投影。

## 6. 身份、组织与权限

### 6.1 选择 inject

| inject | 函数接收 | 请求 Serializer | 组织过滤职责 |
| --- | --- | --- | --- |
| team_list | `team`：授权组织 ID 列表 | 不声明 team | 服务按集合过滤并校验写入归属，不自动级联 |
| team_list_with_user | 上述 team，加可信 user_info（user/domain） | 不声明 team/user_info/user/domain | 同上；user_info 供实际操作者记录 |
| user_info | user_info，含 user/domain/team 及可选 include_children | 必须声明字面名 team 锚点，可声明 include_children；不声明 user_info/user/domain | 复用原服务锚点校验及授权展开，不自行假设锚点已完成资源过滤 |

个人令牌的 team 来自绑定组织；系统 Token 来自经过验证的 acting 组织；JWT 的 team_list 为用户直属组织集合。user_info 模式下，个人/系统令牌的锚点由认证组织覆盖，JWT 锚点仍需正确校验。

网关保证注入身份可信，不能替代业务数据过滤。查询必须按可信组织过滤；写入必须验证目标归属。多分支服务若只有部分分支有组织隔离，应以 ChoiceField 限定可暴露分支。

无组织维度的公共元信息才可用 `team_free=True`，不与 inject 并用，并按已有规范完成安全评审及“不含组织数据”断言。

### 6.2 权限与凭据

- 有菜单权限的能力声明 permission 和 permission_app；后者取真实菜单 client_id，不照抄 app 目录名。常见映射：system_mgmt→system-manager、node_mgmt→node、job_mgmt→job、patch_mgmt→patch、alerts→alarm。
- permission 在现有协议中可选；不声明意味着不执行该项人员菜单权限检查，不能将其当作默认已保护。是否可省略按业务和安全规范评审。
- Token Scope 与人员权限是两个检查。超管可能通过人员权限，但仍受 Token 的端点名单约束；必须用非超管和名单外端点分别测试。
- 系统调用使用 Bearer 系统 Token 与 `X-Bklite-Acting-User: <username>@<domain>`、`X-Bklite-Acting-Team: <id>`；凭据由环境或受管配置提供，不写代码/文档。

## 7. Schema 支持与失败边界

| 字段 | 公共投影行为 |
| --- | --- |
| Serializer | object/properties/required，递归处理 |
| ListSerializer、ListField | array/items、minItems/maxItems |
| DictField | object，声明空 properties，additionalProperties 为 child Schema 或 true |
| JSONField | 任意 JSON 值；不允许 null 时用 not 排除 null |
| ChoiceField | enum，可推断时给出单一基础 type |
| Boolean、Integer、Float | boolean/integer/number，保留显式数值范围 |
| Char、Regex | string、长度及 pattern |
| DateTime、Date、Time、UUID | string 与对应 format |

静态 JSON 默认值会投影；list/dict 工厂投影 []/{}；其他 callable 不执行。nullable 用含 null 的类型数组，枚举相应补 null。字段子类按命中的基类投影，不自动涵盖其所有 validator；跨字段规则也不自动转换。格式声明不等于所有 JSON Schema 校验器默认执行 format 检查。

未支持的类型（如 DecimalField）产生 ValueError。提交新接口前应主动验证目录，不应把容错跳过当作合格的文档交付。

两类错误必须区分：

- **注册错误**：缺请求 Serializer、类类型不合法、非法 service/method、重复注册、缺 inject 或身份参数、漏 permission_app 等，沿原 ImproperlyConfigured 阻止错误注册。
- **已知文档投影错误**：只影响当前 method/path 目录条目，记录有界 WARNING，其他目录继续返回，端点注册/调用不受影响。catalog 不吞其他未知异常，不生成假的空 Schema。

网关 `/_docs` 与系统管理目录必须复用 catalog。不要在 app 或前端另拼一份接口契约。

## 8. 错误与执行行为

- 成功直接返回业务 dict；不要返回 JsonResponse，也不要返回重复的 `{result:true,data:...}` envelope。
- 既有服务软失败 `{result:false,message:...}` 由 dispatcher 映射为 BUSINESS_REJECTED；已识别的组织越权映射为 TEAM_OUT_OF_SCOPE。新增接口复用现有结构化约定，不新造私有错误协议。
- 请求字段错误为 SCHEMA_INVALID，Scope/权限不足分别为 SCOPE_DENIED/PERM_MISSING，未注册路由为 NOT_FOUND；以 envelope.py 的现行映射为准，错误码只追加不复用。
- 不捕获所有异常再返回空成功；不在业务适配层重复包装 dispatcher 已处理的错误。
- 复用 Django ORM，禁止原生 SQL。按 app 使用核心 logger，稳定模板与独立参数；生产日志不记录凭据、payload、响应正文或其他无界对象。
- 大列表采用分页；长任务沿用业务任务提交与状态查询模式。不要假设调用方超时等于远端未执行，写请求不可随意自动重试。网关执行超时的实际保障取决于部署 settings，不能以函数中存在超时代码推断生产已启用。

## 9. 测试与目录验收

每个新 method 都要验证以下相关行为：

1. 实际网关请求成功，Serializer 字段名与函数形参匹配；默认值、分页和空结果正确。
2. 目录中存在对应 path/method，Schema 合法；声明的 response_schema 能校验完整实际响应。
3. 请求未知字段/伪造身份拒绝，写入归属正确；另一组织不能读写目标资源。
4. 人员权限不足和 Token Scope 不足分别拒绝，不能只用超级管理员测成功。
5. 已声明响应缺必填/类型错失败，新增字段通过；未声明响应保持 null。

双租户工具位于 `testing.py`：`create_api_tenant` 构造个人令牌，`create_system_tenant` 构造系统 Token + acting 身份；HTTP 头分别用 `bearer()`、`acting_headers()`。

将测试登记到 `tests/tenant_coverage.py`（示意，替换为实际已有测试引用）：

```python
TENANT_ISOLATION_COVERAGE = {
    # 保留既有登记，此处只展示新增项。
    "your-service/resources": [
        "apps.your_app.tests.test_openapi_gateway::test_other_org_cannot_read_resource",
        "apps.your_app.tests.test_openapi_gateway::test_create_belongs_to_acting_org",
    ],
}
```

`test_governance.py` 检查登记存在及测试引用可解析，不能替代测试本身的行为断言。同 path 多方法须在同一登记项中覆盖相关行为。

在 server 目录、现有开发依赖与独立测试数据库下执行：

```bash
pytest apps/core/openapi/tests apps/<app>/tests/<相关测试文件> --no-cov
```

测试环境初始化方式见仓库 `DEVELOP.md`。若本地 SQLite 因既有迁移限制使用 `--nomigrations`，需在记录中写明；不要将其当作正式数据库迁移验证。

运行态再以实际凭据访问 `/_me`、`/_docs`，调用新接口。_me 只证明身份有效；目录可读只证明契约已发布；均不能替代业务成功及组织隔离验收。

## 10. 面向 ITSM 的额外适配

通用 BK-Lite Schema 能力与 ITSM 表单子集分别看待：

- 输入支持 string/integer/number/boolean、固定 properties 对象以及有明确 items 的数组；nullable 由 ITSM 取非 null 类型渲染。
- 不扩展动态 key 输入，也不接入依赖输入 $ref、allOf/anyOf/oneOf/not/if/then/else 的端点。BK-Lite 原有 Dict/JSON 能力不为此收紧。
- ITSM 允许缺省/null/空 Schema；没有输出 Schema 不等于禁止调用，但不能从目录自动加载输出字段。
- ITSM 保存 Schema 快照。响应契约更新后，应重新获取、保存动作并更新流程版本；输出引用使用完整动作结果中的 data 字段。
- 动作调试传值与真实工单自动输出引用是不同验收范围，不能相互代替。

## 11. 提交前清单

- [ ] 仅走统一网关，path/method 和 Serializer 为稳定对外契约。
- [ ] 请求继承专用基类，响应只描述 data，实际返回通过契约校验。
- [ ] inject 与原函数组织协议一致，业务查询/写入落实组织过滤和归属。
- [ ] permission_app 正确，非超管权限和 Scope 测试均覆盖。
- [ ] 模块被导入注册，不在启动阶段生成文档或依赖外部运行期服务。
- [ ] 新端点真实出现在目录中；投影失败未被忽略为“测试通过”。
- [ ] 双租户测试已登记；必要的写入安全、幂等/回滚按实际业务要求验证。
- [ ] 未破坏旧请求/响应与错误语义；破坏性变更使用新 path/版本。
- [ ] 未增加假设性防御分支、兼容层或内部重复校验。
- [ ] 已运行相关测试与仓库检查，并记录未验证的部署或运行边界。

## 12. 模块地图与参考实现

| 模块 | 职责 |
| --- | --- |
| decorators.py / registry.py | 显式注册、保存 Serializer、注册安全检查 |
| schema.py / catalog.py | Draft 7 投影与共享目录、逐接口投影失败隔离 |
| identity.py / token_scope.py | 凭据身份和 Token 路由名单 |
| dispatcher.py | 权限、请求校验、身份注入、调用、envelope |
| envelope.py | 成功/失败结构及错误码映射 |
| testing.py / tests/tenant_coverage.py | 双租户测试工具和登记 |

可运行参考：`server/apps/apm/openapi_api.py`、`openapi_serializers.py`、`tests/test_openapi_gateway.py`。该实现已覆盖应用 GET/POST、固定系统身份和精确组织范围；其他业务应按自身组织协议选择 inject，不能照搬权限或业务语义。
