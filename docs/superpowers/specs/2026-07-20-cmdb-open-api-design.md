# CMDB 外部 OpenAPI 设计

日期：2026-07-20

## 1. 背景

BK-Lite 作业平台当前以两种方式开放能力：

- 作业执行、状态查询等通过 `@nats_client.register` 注册为 NATS Request-Reply 接口，默认信任内网 NATS，不承载外部用户身份鉴权。
- 文件上传、删除通过 `/api/v1/job_mgmt/api/open/` 下的 REST 接口开放，使用 `Api-Authorization` 和 `UserAPISecret` 鉴权，并以密钥绑定团队约束文件归属。

CMDB 已存在查询、实例写入和关联操作等 NATS 注册函数，但这些函数按可信机器调用设计，部分写路径会跳过用户权限检查，且允许调用方提供组织范围。它们不能直接作为面向外部系统的安全边界。

本设计为 CMDB 增加独立 REST OpenAPI 门面，复用现有认证、RBAC、领域服务、变更记录及自动关联能力，但不直接暴露控制台 ViewSet，也不包装 CMDB NATS 处理器。

## 2. 目标

首期提供以下外部能力：

- 模型相关只读：分类、模型、模型详情、模型字段、模型关联定义。
- 实例单条与批量 CRUD。
- 实例关联查询、创建和删除。
- 动态模型字段过滤、分页和排序。
- 通过 API Secret 绑定团队与所属用户当前 RBAC 实施双重授权。
- 保持现有 CMDB REST、NATS 和控制台行为不变。

## 3. 非目标

首期不包含：

- 分类、模型、字段、模型关联定义的创建、修改和删除。
- 采集任务、配置文件、导入导出和全文搜索。
- 绑定团队的子团队访问。
- API Secret 独立 scope。
- 对外开放 NATS。
- 写请求幂等键存储。
- 兼容旧入口或为现有内部接口增加别名。

## 4. 方案选择

### 4.1 采用方案：独立 CMDB OpenAPI 门面

新增专用 View、Serializer 和 Service：

- View 只负责 HTTP 方法、状态码及响应封装。
- Serializer 校验路径参数、动态过滤条件、实例字段和批量请求。
- Service 构建可信授权上下文，并委托现有 `ModelManage`、`InstanceManage` 等领域服务。

### 4.2 不采用的方案

不直接开放现有 CMDB ViewSet。现有接口包含 Cookie、`current_team`、`include_children` 及控制台响应约定，无法形成稳定的外部契约，也容易意外扩大开放面。

不直接包装 CMDB NATS 函数。NATS 写接口具有可信内网假设，部分路径会跳过用户权限检查或信任调用方传入的组织范围。

## 5. 架构与数据流

统一入口为：

```text
/api/v1/cmdb/api/open/
```

请求链路：

```text
外部系统
  -> Api-Authorization
  -> APISecretMiddleware
  -> 密钥所属用户与唯一绑定团队
  -> CMDB OpenAPI Serializer
  -> CMDB OpenAPI Service
  -> 当前用户 RBAC + 绑定团队过滤
  -> CMDB 领域服务
  -> FalkorDB / Django ORM / 变更记录 / 自动关联后处理
```

授权上下文完全由服务端生成。请求中的 `team`、`organization`、`allowed_org_ids` 或 `include_children` 均不能扩大访问范围。

## 6. 路由设计

### 6.1 模型只读接口

```text
GET /api/v1/cmdb/api/open/classifications
GET /api/v1/cmdb/api/open/models
GET /api/v1/cmdb/api/open/models/{model_id}
GET /api/v1/cmdb/api/open/models/{model_id}/attributes
GET /api/v1/cmdb/api/open/models/{model_id}/associations
```

分类与模型列表只返回密钥所属用户在绑定团队下可查看的对象。模型详情、字段和关联定义请求必须先通过模型查看权限校验。

### 6.2 实例接口

```text
GET    /api/v1/cmdb/api/open/models/{model_id}/instances
POST   /api/v1/cmdb/api/open/models/{model_id}/instances
GET    /api/v1/cmdb/api/open/models/{model_id}/instances/{inst_id}
PATCH  /api/v1/cmdb/api/open/models/{model_id}/instances/{inst_id}
DELETE /api/v1/cmdb/api/open/models/{model_id}/instances/{inst_id}

POST /api/v1/cmdb/api/open/models/{model_id}/instances/batch_create
POST /api/v1/cmdb/api/open/models/{model_id}/instances/batch_update
POST /api/v1/cmdb/api/open/models/{model_id}/instances/batch_delete
```

实例详情、更新和删除统一通过 `model_id + inst_id` 定位。服务端必须确认实例的真实 `model_id` 与路径一致。

### 6.3 实例关联接口

```text
GET    /api/v1/cmdb/api/open/models/{model_id}/instances/{inst_id}/associations
POST   /api/v1/cmdb/api/open/models/{model_id}/instances/{inst_id}/associations
DELETE /api/v1/cmdb/api/open/models/{model_id}/instances/{inst_id}/associations/{association_id}
```

创建和删除关联时必须同时验证源实例与目标实例的团队范围和对象级权限，并验证模型关联定义及方向。

## 7. 认证与授权

### 7.1 认证

认证请求头与 Job 保持一致：

```http
Api-Authorization: <api_secret>
```

复用现有 `UserAPISecret`、`APISecretMiddleware` 和认证后端，不新增密钥表或认证协议。

### 7.2 团队范围

- 每个 API Secret 只允许访问其唯一绑定团队。
- 不包含绑定团队的子团队。
- 客户端不能选择或切换团队。
- 查询时只返回 `organization` 包含绑定团队的实例。
- 创建实例时服务端强制写入 `organization: [绑定团队]`。
- 更新实例时禁止修改 `organization`，不允许通过 OpenAPI 迁移实例组织。

### 7.3 RBAC

API Secret 同时继承所属用户当前的 CMDB RBAC：

- 模型接口检查模型查看权限。
- 实例列表和详情应用团队过滤及实例级查看规则。
- 创建、更新和删除分别检查现有 CMDB 新增、编辑和删除权限。
- 关联写操作同时检查源、目标实例及相应关联权限。
- 用户停用、角色撤销或权限变更后，后续密钥请求立即使用新的权限结果，不保留密钥创建时的权限快照。

团队范围与 RBAC 必须同时满足，任一条件失败均不得访问资源。

## 8. 请求契约

### 8.1 实例列表

实例列表支持分页、排序和动态字段过滤：

```text
page=1
page_size=20
order=-updated_at
filters=[{"field":"ip_addr","type":"str*","value":"10.0."}]
```

`filters` 使用 CMDB 现有 `{field, type, value}` 结构。OpenAPI Serializer 必须完成以下校验后才能调用领域服务：

- `field` 属于路径指定模型的可查询字段。
- `type` 属于 OpenAPI 明确允许的过滤操作符。
- `value` 与字段类型、操作符匹配。
- 不允许通过过滤条件读取内部系统字段。

默认 `page=1`、`page_size=20`，单页最大 `page_size=200`。

### 8.2 单实例创建

请求体直接提交可编辑实例属性：

```json
{
  "inst_name": "host-01",
  "ip_addr": "10.0.0.1"
}
```

服务端忽略客户端组织上下文并写入：

```json
{"organization": [1]}
```

其中 `1` 为 API Secret 的绑定团队。

### 8.3 单实例更新

更新采用 `PATCH`，只修改请求中出现的可编辑字段。以下字段禁止写入：

- `_id`
- `model_id`
- `organization`
- `_creator`
- 创建、更新时间等审计字段
- 模型定义为只读或计算生成的字段

### 8.4 批量请求

批量创建：

```json
{
  "items": [
    {"inst_name": "host-01", "ip_addr": "10.0.0.1"},
    {"inst_name": "host-02", "ip_addr": "10.0.0.2"}
  ]
}
```

批量更新沿用现有 CMDB 语义，所有实例应用同一份修改：

```json
{
  "inst_ids": [101, 102],
  "update_data": {"status": "active"}
}
```

批量删除：

```json
{"inst_ids": [101, 102]}
```

单次批量写入最多 100 个实例。批量操作先校验全部目标、权限、字段、组织范围和唯一性，再进入现有批量领域操作。接口只提供整体成功或整体错误，不提供逐条部分成功契约。

若任一项在执行前校验失败，响应必须指出失败项的索引或 `inst_id`，且不得开始批量写入。

### 8.5 实例关联

创建关联请求：

```json
{
  "model_asst_id": "host_run_app",
  "target_model_id": "app",
  "target_inst_id": 201
}
```

源模型和源实例来自 URL。服务端必须验证：

- 源、目标实例存在且模型匹配。
- 模型关联定义存在且方向匹配。
- 源、目标实例均属于绑定团队的可访问范围。
- 当前用户对源、目标实例均有相应操作权限。
- 不重复创建同一条关联。

删除关联时必须确认关联属于 URL 中的源实例，并对其目标实例执行同等权限校验。

## 9. 响应与错误契约

成功响应：

```json
{
  "result": true,
  "data": {},
  "message": "",
  "code": "ok"
}
```

分页响应：

```json
{
  "result": true,
  "data": {
    "count": 120,
    "page": 1,
    "page_size": 20,
    "items": []
  },
  "message": "",
  "code": "ok"
}
```

错误响应示例：

```json
{
  "result": false,
  "data": {
    "index": 2,
    "inst_id": 103,
    "field": "ip_addr"
  },
  "message": "字段值违反唯一性约束",
  "code": "cmdb.instance.unique_conflict"
}
```

HTTP 状态约定：

- `400`：参数、过滤条件或字段校验失败。
- `401`：缺少认证信息。
- `403`：密钥无效，或用户缺少对应操作权限。
- `404`：模型或实例不存在，或者资源不属于绑定团队。跨团队资源统一按不存在处理，避免枚举。
- `409`：唯一字段冲突、关联重复或批量请求内部冲突。
- `500`：脱敏后的内部错误。

应用错误码保持稳定，错误消息允许国际化。响应不得包含异常堆栈、数据库信息、图查询语句或密钥内容。

## 10. 审计与可观测性

- 实例与关联写操作继续调用现有领域服务，复用现有 CMDB 变更记录。
- 操作人记录 API Secret 所属用户名。
- 结构化请求日志记录方法、路径、用户名、绑定团队、批量数量、状态码和耗时。
- 日志不得记录 `Api-Authorization`、完整请求体或完整实例返回数据。
- 批量错误日志只记录错误码、失败索引或 `inst_id`，不输出可能包含凭据的动态属性值。

## 11. 一致性与重试

首期不新增写请求幂等键存储。创建请求在服务端已成功、但调用方未收到响应时，重试可能因唯一约束返回 `409`。调用方应根据模型唯一字段查询确认结果后再决定是否重试。

批量接口遵循现有 CMDB 的整体请求语义，不承诺 FalkorDB、Django 数据库及异步后处理之间的分布式事务。实现必须复用现有领域服务的执行顺序、审计与后处理策略，不在 OpenAPI 门面自行拼接跨存储写操作。

## 12. 测试策略

### 12.1 Serializer 单元测试

- 模型字段与过滤操作符校验。
- 动态字段类型和值校验。
- 系统字段和组织字段写入拒绝。
- 分页及批量数量上限。
- 批量错误位置返回。

### 12.2 权限矩阵测试

- 缺少和无效 API Secret。
- API Secret 固定绑定团队，不接受调用方团队参数。
- 用户 RBAC 变更后权限立即生效。
- 跨团队实例按 `404` 处理。
- 只读用户不能写实例。
- 源或目标任一实例无权限时关联写入失败。

### 12.3 API 行为测试

- 分类、模型、字段和模型关联只读查询。
- 实例单条创建、查询、更新和删除。
- 动态过滤、分页和排序。
- 批量创建、统一更新和删除。
- 批量校验失败不开始写入。
- 关联查询、创建、重复冲突和删除。
- 唯一约束、模型不匹配及非法关联方向。

### 12.4 回归与质量门禁

- 现有 CMDB REST ViewSet 行为不变。
- 现有 CMDB NATS 注册函数行为不变。
- 目标改动覆盖率不低于 75%。
- 执行后端相关最小测试，并在最终验收前运行 `cd server && make test`；若全量门禁被既有仓库问题阻断，必须记录具体阻断和目标测试结果。
- 数据访问继续使用现有 ORM 和图服务，禁止新增原生 SQL。

## 13. 文档与验收

实现同步提供：

- `server/apps/cmdb/docs/open_api.md`，包含认证、路由、过滤操作符、错误码和完整示例。
- 可导入的 OpenAPI/Swagger 描述，复用项目现有文档生成能力。
- API Secret 创建及用户权限配置说明。
- `curl` 示例和最小联调清单。

真实验收使用一个绑定测试团队的 API Secret 完成：

1. 查询可见分类、模型、字段和模型关联。
2. 创建、查询、更新和删除单个实例。
3. 执行批量创建、更新和删除。
4. 创建、查询和删除实例关联。
5. 验证跨团队实例不可枚举或操作。
6. 撤销所属用户写权限后，确认同一密钥不能继续写入。

## 14. 发布与回滚

该设计复用现有 `UserAPISecret`，不需要数据库迁移。新增路由和门面代码独立于现有 CMDB REST/NATS 契约。

回滚时移除 OpenAPI 路由注册和门面代码即可停止新入口；通过 OpenAPI 创建的实例属于正常 CMDB 数据，不随代码回滚删除。发布前不得把 NATS 端口或内部 CMDB NATS subject 暴露到外部网络。
