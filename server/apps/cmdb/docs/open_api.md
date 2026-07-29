# CMDB OpenAPI 接口说明

本文说明 CMDB 对外开放的模型、实例和关联接口。接口以 API Secret 对调用方进行认证，并继续使用该 Secret 所绑定用户及团队的 CMDB 权限。

## 1. 基础约定

### 1.1 基础地址

```text
{BK_LITE_BASE_URL}/api/v1/cmdb/api/open
```

例如 BK-Lite 地址为 `https://bk-lite.example.com`，模型列表接口就是：

```text
https://bk-lite.example.com/api/v1/cmdb/api/open/models
```

接口路径末尾不带 `/`。

### 1.2 认证方式

API Token 需要在 BK-Lite 产品页面申请，入口为：

```text
系统管理 → 平台设置 → 密钥
```

在该页面申请密钥后，将获得的 Token 作为接口认证凭据。本文中的“API Secret”与产品页面申请到的“API Token”指同一凭据。

所有接口都必须携带请求头：

```http
Api-Authorization: <API_SECRET>
```

API Secret 必须只绑定一个团队；接口只能访问该团队内、且绑定用户有权限访问的模型和实例。跨团队实例会按不存在处理并返回 404，防止通过 ID 枚举数据。

写接口还必须携带：

```http
Content-Type: application/json
```

### 1.3 统一响应结构

成功响应：

```json
{
  "result": true,
  "data": {},
  "message": "",
  "code": "ok"
}
```

失败响应：

```json
{
  "result": false,
  "data": {},
  "message": "请求参数非法",
  "code": "cmdb.validation.failed"
}
```

固定字段如下：

| 字段 | 类型 | 说明 |
|---|---|---|
| `result` | boolean | 调用是否成功 |
| `data` | object、array | 成功数据或错误上下文 |
| `message` | string | 成功时为空；失败时为可读错误信息 |
| `code` | string | 成功为 `ok`；失败为稳定错误码 |

### 1.4 路径参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `model_id` | string | 模型 ID，例如 `host`、`app` |
| `inst_id` | integer | 实例 ID，正整数 |
| `association_id` | integer | 实例关联边 ID，正整数 |

## 2. 接口总览

当前共 12 个 URL 模板、16 个操作。

| 方法 | URL | 接口名称 | 作用 |
|---|---|---|---|
| GET | `/classifications` | 查询模型分类 | 查询当前调用方可见的模型分类 |
| GET | `/models` | 查询模型列表 | 查询当前调用方可见的模型 |
| GET | `/models/{model_id}` | 查询模型详情 | 查询指定模型定义 |
| GET | `/models/{model_id}/attributes` | 查询模型属性 | 查询创建、更新及过滤实例所需的字段定义 |
| GET | `/models/{model_id}/associations` | 查询模型关联定义 | 查询指定模型参与的关联类型 |
| GET | `/models/{model_id}/instances` | 查询实例列表 | 分页、过滤和排序查询实例 |
| POST | `/models/{model_id}/instances` | 创建实例 | 创建单个实例 |
| GET | `/models/{model_id}/instances/{inst_id}` | 查询实例详情 | 查询单个实例 |
| PATCH | `/models/{model_id}/instances/{inst_id}` | 更新实例 | 局部更新单个实例 |
| DELETE | `/models/{model_id}/instances/{inst_id}` | 删除实例 | 删除单个实例 |
| POST | `/models/{model_id}/instances/batch_create` | 批量创建实例 | 一次创建 1 至 100 个实例 |
| POST | `/models/{model_id}/instances/batch_update` | 批量更新实例 | 使用相同字段更新 1 至 100 个实例 |
| POST | `/models/{model_id}/instances/batch_delete` | 批量删除实例 | 一次删除 1 至 100 个实例 |
| GET | `/models/{model_id}/instances/{inst_id}/associations` | 查询实例关联 | 查询实例已有的关联关系 |
| POST | `/models/{model_id}/instances/{inst_id}/associations` | 创建实例关联 | 从当前实例连接到目标实例 |
| DELETE | `/models/{model_id}/instances/{inst_id}/associations/{association_id}` | 删除实例关联 | 删除指定关联边 |

以下章节中的 URL 均省略基础地址 `/api/v1/cmdb/api/open`。

## 3. 模型接口

### 3.1 查询模型分类

- 方法与 URL：`GET /classifications`
- 作用：只返回至少包含一个可见模型的可见分类。
- 入参：无。
- 成功状态码：200。
- 返回：`data` 为分类对象数组。

分类对象的主要字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `classification_id` | string | 分类 ID |
| `classification_name` | string | 分类名称，按调用用户语言返回 |
| `order` | integer | 展示顺序 |
| `is_visible` | boolean | 分类是否可见 |
| `exist_model` | boolean | 分类下是否存在模型 |
| `_id` | integer | 内部分类节点 ID，存在时返回 |

### 3.2 查询模型列表

- 方法与 URL：`GET /models`
- 作用：返回调用方有模型查看权限的可见模型。
- 入参：无。
- 成功状态码：200。
- 返回：`data` 为模型对象数组。

模型对象的主要字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `model_id` | string | 模型 ID |
| `model_name` | string | 模型名称 |
| `classification_id` | string | 所属分类 ID |
| `is_visible` | boolean | 是否可见 |
| `order` | integer | 展示顺序，存在时返回 |
| `group` | array[integer] | 模型所属权限组，存在时返回 |
| `attrs` | string | 模型原始属性定义 JSON，存在时返回；调用方应优先使用属性查询接口 |

### 3.3 查询模型详情

- 方法与 URL：`GET /models/{model_id}`
- 作用：返回一个可见模型的完整定义。
- 入参：路径参数 `model_id`。
- 成功状态码：200。
- 返回：`data` 为模型对象，字段含义与模型列表一致，并可能包含该模型保存的扩展配置。
- 不存在或不可见：404，`cmdb.model.not_found`。

### 3.4 查询模型属性

- 方法与 URL：`GET /models/{model_id}/attributes`
- 作用：查询实例字段定义。创建、更新、过滤前建议先调用本接口。
- 入参：路径参数 `model_id`。
- 成功状态码：200。
- 返回：`data` 为属性对象数组。

属性对象的主要字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `attr_id` | string | 实例 JSON 中使用的字段名 |
| `attr_name` | string | 字段显示名称 |
| `attr_type` | string | 字段类型，例如 `str`、`int`、`list` |
| `required` | boolean | 创建时是否必填，存在时返回 |
| `editable` | boolean | 是否允许通过更新接口修改 |
| `is_display_field` | boolean | 是否为展示计算字段；此类字段不能由调用方写入 |
| `option` | array、object | 枚举或选项定义，存在时返回 |
| `default` | 任意 JSON 值 | 默认值，存在时返回 |
| `is_unique` | boolean | 是否受唯一性约束，存在时返回 |

### 3.5 查询模型关联定义

- 方法与 URL：`GET /models/{model_id}/associations`
- 作用：查询指定模型作为源或目标参与的关联类型；创建实例关联前应先查询并确认方向。
- 入参：路径参数 `model_id`。
- 成功状态码：200。
- 返回：`data` 为模型关联对象数组。

模型关联对象的主要字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `model_asst_id` | string | 模型关联 ID |
| `asst_id` | string | 关联类型 ID，存在时返回 |
| `src_model_id` | string | 源模型 ID |
| `dst_model_id` | string | 目标模型 ID |
| `mapping` | string | 关联基数或映射类型，存在时返回 |
| `_id` | integer | 内部关联定义 ID，存在时返回 |

## 4. 实例公共结构与写入规则

实例对象包含固定系统字段和当前模型定义的动态属性。

| 字段 | 类型 | 说明 |
|---|---|---|
| `inst_id` | integer | 实例 ID；内部 `_id` 对外统一改名为 `inst_id` |
| `model_id` | string | 模型 ID |
| `creator` | string | 创建人；内部 `_creator` 对外统一改名 |
| `created_at` | string | 创建时间；内部 `_created_at` 对外统一改名 |
| `updated_at` | string | 更新时间；内部 `_updated_at` 对外统一改名 |
| `organization` | array[integer] | 实例所属团队；创建时由 API Secret 绑定团队自动写入 |
| `<attr_id>` | 任意 JSON 值 | 模型自定义属性，类型由属性定义决定 |

`_labels` 与 `permission` 不会出现在实例响应中。

写入限制：

- 请求体必须是非空 JSON 对象。
- 只能写模型属性接口返回的字段。
- 创建和更新都不能提交 `_id`、`model_id`、`organization`、`_creator`、`_created_at`、`_updated_at`。
- 更新只能提交 `editable=true` 且 `is_display_field=false` 的字段。
- 创建时 `organization` 由服务端强制设置为 API Secret 绑定团队。

## 5. 实例接口

### 5.1 查询实例列表

- 方法与 URL：`GET /models/{model_id}/instances`
- 作用：在权限和团队范围内分页查询实例。
- 成功状态码：200。

Query 参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `page` | integer | 否 | 1 | 页码，最小 1 |
| `page_size` | integer | 否 | 20 | 每页数量，范围 1 至 200 |
| `order` | string | 否 | 空 | 排序字段；前缀 `-` 表示倒序 |
| `filters` | string | 否 | `[]` | JSON 编码的过滤条件数组 |

`order` 支持模型属性字段，以及三个别名：`inst_id`、`created_at`、`updated_at`。例如 `-inst_id` 表示按实例 ID 倒序。

每个过滤条件必须恰好包含：

```json
{"field": "inst_name", "type": "str*", "value": "web"}
```

过滤操作符：

| 字段类型 | 操作符 | 含义 |
|---|---|---|
| `str` | `str=` | 字符串精确匹配 |
| `str` | `str*` | 字符串模糊匹配 |
| `str` | `str[]` | 字符串属于给定数组 |
| `int` | `int=` | 整数精确匹配 |
| `int` | `int[]` | 整数属于给定数组 |
| `list` | `list[]` | 列表字段匹配给定值集合 |

系统字段和不存在的模型字段不能用于 `filters`。

`data` 返回字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `count` | integer | 符合条件的实例总数 |
| `page` | integer | 当前页码 |
| `page_size` | integer | 当前每页数量 |
| `items` | array[实例对象] | 当前页实例 |

### 5.2 创建实例

- 方法与 URL：`POST /models/{model_id}/instances`
- 作用：创建单个实例。
- 请求体：以 `attr_id` 为键的非空实例属性对象。
- 成功状态码：201。
- 返回：`data` 为创建后的实例对象。

示例请求：

```json
{
  "inst_name": "host-01",
  "ip": "10.0.0.1"
}
```

### 5.3 查询实例详情

- 方法与 URL：`GET /models/{model_id}/instances/{inst_id}`
- 作用：查询单个可见实例。
- 入参：路径参数 `model_id`、`inst_id`。
- 成功状态码：200。
- 返回：`data` 为实例对象。
- 实例不存在、模型不匹配或跨团队：404，`cmdb.instance.not_found`。

### 5.4 更新实例

- 方法与 URL：`PATCH /models/{model_id}/instances/{inst_id}`
- 作用：局部更新单个实例。
- 请求体：需要修改的可编辑模型属性，必须为非空对象。
- 成功状态码：200。
- 返回：`data` 为更新后的实例对象。

示例请求：

```json
{
  "ip": "10.0.0.2"
}
```

### 5.5 删除实例

- 方法与 URL：`DELETE /models/{model_id}/instances/{inst_id}`
- 作用：删除单个实例。
- 请求体：无。
- 成功状态码：200。
- 返回：`data.deleted` 为已删除实例 ID 数组。

```json
{
  "deleted": [12]
}
```

## 6. 批量实例接口

批量接口每次接收 1 至 100 个实例。更新和删除会先验证所有实例均属于当前团队且有操作权限，再执行领域写入。

### 6.1 批量创建实例

- 方法与 URL：`POST /models/{model_id}/instances/batch_create`
- 请求体：`items` 为 1 至 100 个实例属性对象。
- 成功状态码：201。
- 返回：`data.created` 为创建后的实例对象数组。

```json
{
  "items": [
    {"inst_name": "host-01", "ip": "10.0.0.1"},
    {"inst_name": "host-02", "ip": "10.0.0.2"}
  ]
}
```

单项预校验失败时，`data.index` 返回从 0 开始的错误项下标。

### 6.2 批量更新实例

- 方法与 URL：`POST /models/{model_id}/instances/batch_update`
- 成功状态码：200。
- 返回：`data.updated` 为更新后的实例对象数组。

请求体字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `inst_ids` | array[integer] | 是 | 1 至 100 个正整数实例 ID；重复 ID 会去重 |
| `update_data` | object | 是 | 应用于全部实例的非空、可编辑属性 |

```json
{
  "inst_ids": [11, 12],
  "update_data": {"status": "active"}
}
```

### 6.3 批量删除实例

- 方法与 URL：`POST /models/{model_id}/instances/batch_delete`
- 成功状态码：200。
- 请求体：`inst_ids` 为 1 至 100 个正整数实例 ID；重复 ID 会去重。
- 返回：`data.deleted` 为已删除实例 ID 数组。

```json
{
  "inst_ids": [11, 12]
}
```

## 7. 实例关联接口

### 7.1 查询实例关联

- 方法与 URL：`GET /models/{model_id}/instances/{inst_id}/associations`
- 作用：查询源实例参与的实例关联，并按模型关联定义分组。
- 请求体：无。
- 成功状态码：200。
- 返回：`data` 为关联分组数组。

关联分组的主要字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `model_asst_id` | string | 模型关联 ID |
| `inst_list` | array | 此关联定义下的关联实例列表；实例和关联边的扩展字段按模型定义返回 |

### 7.2 创建实例关联

- 方法与 URL：`POST /models/{model_id}/instances/{inst_id}/associations`
- 作用：以 URL 中实例为源端点，创建到目标实例的关联。
- 成功状态码：201。

请求体字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `model_asst_id` | string | 是 | 模型关联 ID，最长 255 字符 |
| `target_model_id` | string | 是 | 目标模型 ID，最长 255 字符 |
| `target_inst_id` | integer | 是 | 目标实例 ID，正整数 |

```json
{
  "model_asst_id": "host_run_app",
  "target_model_id": "app",
  "target_inst_id": 21
}
```

返回 `data`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `association_id` | integer | 新建关联边 ID |
| `model_asst_id` | string | 模型关联 ID |

只有 `src_model_id` 等于 URL 的 `model_id`，且 `dst_model_id` 等于 `target_model_id` 的关联定义才允许创建。重复关联返回 409 和 `cmdb.association.conflict`。

### 7.3 删除实例关联

- 方法与 URL：`DELETE /models/{model_id}/instances/{inst_id}/associations/{association_id}`
- 作用：删除指定关联边。
- 请求体：无。
- 成功状态码：200。
- 返回：`data.deleted` 为已删除关联边 ID。

```json
{
  "deleted": 10
}
```

URL 中的实例必须与关联边源端点一致，且源、目标实例都必须在当前团队和权限范围内。关联不存在、端点异常或源端点不匹配时返回 404 和 `cmdb.association.not_found`。

## 8. 常见状态码与错误码

| HTTP 状态码 | `code` | 说明 |
|---|---|---|
| 400 | `cmdb.validation.failed` | 请求字段、过滤条件或实例属性非法 |
| 400 | `cmdb.association.invalid_direction` | 模型关联方向与请求源、目标不匹配 |
| 403 | `cmdb.auth.api_secret_required` | 未通过 API Secret 认证 |
| 403 | `cmdb.auth.authentication_required` | API Secret 没有形成有效用户身份 |
| 403 | `cmdb.permission.denied` | 用户缺少功能或对象权限 |
| 404 | `cmdb.model.not_found` | 模型不存在或不可见 |
| 404 | `cmdb.instance.not_found` | 实例不存在、模型不匹配、跨团队或不可见 |
| 404 | `cmdb.association.not_found` | 实例关联不存在、异常或不属于 URL 中的源实例 |
| 405 | `cmdb.request.method_not_allowed` | URL 不支持该 HTTP 方法 |
| 409 | `cmdb.instance.unique_conflict` | 实例字段违反唯一性约束 |
| 409 | `cmdb.association.conflict` | 实例关联已存在 |
| 500 | `cmdb.instance.batch_incomplete` | 批量领域操作没有完整完成 |
| 500 | `cmdb.request.failed` | 未归类的请求处理失败 |

批量错误的 `data` 可能附带 `index`、`inst_id`、`field`，用于定位失败项。
