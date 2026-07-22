# 运营分析支持 YAML 导入导出 Tech Plan（2026-04-07）

Status: cancelled

> Migrated from `spec/tech_plan/运营分析/20260407.运营分析支持YAML导入导出.md` as historical change evidence.

需求文档：`spec/requirements/运营分析/20260327.运营分析支持YAML导入导出.md`
方案文档：`spec/solution_plan/运营分析/20260407.运营分析支持YAML导入导出.md`

## 0. 技术目标与非目标

### 0.1 技术目标

在运营分析模块内实现一套统一 YAML 导入导出能力，满足以下确定性目标：

1. 支持画布对象（仪表盘/拓扑/架构图）导出与导入。
2. 支持配置对象（数据源/命名空间）导出与导入。
3. 导出包含画布依赖的组件配置与关联对象，且仅导出实际依赖。
4. 导入前可预检并返回对象级问题清单。
5. 冲突处理固定支持：`skip` / `overwrite` / `rename`。
6. 页面与开放接口使用同一后端逻辑，返回语义一致。

### 0.2 技术非目标

1. 不实现目录结构导入导出与目录树恢复。
2. 不实现删除式同步（不会删除目标环境未在 YAML 出现的对象）。
3. 不实现 Excel/JSON/ZIP 等多格式支持。
4. 不改造其他模块（仅 `operation_analysis` 模块范围）。
5. 不引入异步任务系统（本期同步执行）。

## 1. 影响范围与改动点

### 1.1 后端（仅本模块）

```text
server/apps/operation_analysis/
├── constants/
│   └── import_export.py                          # 新增：常量、枚举、阈值
├── schemas/
│   └── import_export_schema.py                   # 新增：YAML 契约校验
├── services/
│   ├── import_export/
│   │   ├── export_service.py                     # 新增：导出装配
│   │   ├── precheck_service.py                   # 新增：预检
│   │   ├── import_service.py                     # 新增：导入执行
│   │   ├── mapping_service.py                    # 新增：业务键与ID映射
│   │   └── serializer.py                         # 新增：YAML 序列化/反序列化
├── serializers/
│   └── import_export_serializers.py              # 新增：接口入参/出参结构
├── views/
│   └── import_export_view.py                     # 新增：3个开放接口
├── urls.py                                       # 修改：新增 import_export 路由
└── tests/
    ├── test_import_export_export.py             # 新增
    ├── test_import_export_precheck.py           # 新增
    ├── test_import_export_import.py             # 新增
    └── test_import_export_api.py                # 新增
```

### 1.2 前端（仅本模块）

```text
web/src/app/ops-analysis/
├── api/
│   └── importExport.ts                           # 新增：导入导出 API
├── components/
│   └── import-export/
│       ├── exportModal.tsx                       # 新增
│       ├── importPrecheckModal.tsx               # 新增
│       ├── conflictResolveModal.tsx              # 新增
│       └── importResultModal.tsx                 # 新增
├── (pages)/view/dashBoard/index.tsx              # 修改：画布导出入口
├── (pages)/view/topology/index.tsx               # 修改：画布导出入口
├── (pages)/view/architecture/index.tsx           # 修改：画布导出入口
├── (pages)/settings/dataSource/page.tsx          # 修改：配置对象导入导出入口
└── (pages)/settings/namespace/page.tsx           # 修改：配置对象导入导出入口
```

### 1.3 模块外边界

1. 不新增跨模块公共导入导出框架。
2. 不改动 CMDB、告警、其他业务模块。
3. 外部系统仅通过本模块开放接口交互。

## 2. 固化技术决策（已确认）

1. 冲突 `overwrite` 语义：**全量覆盖对象**。
2. 同步执行阈值：`YAML <= 2MB` 且 `对象总数 <= 200`，超限直接拒绝。
3. 不提供结果查询接口，导入结果由 `import/submit` 同步直接返回。
4. `rename` 命名规则：`{original_name}_copy`。
5. `import/submit` 未提供 `conflict_decisions` 时，冲突对象默认执行 `rename`。
6. `overwrite` 允许覆盖目标对象的额外字段（全量覆盖语义生效）。
7. 敏感字段清单固定为 `password` / `secret` / `token`，无扩展字段。

## 3. 数据结构与规则口径

### 3.1 YAML 顶层结构（唯一版本）

```yaml
meta:
  schema_version: '1.0.0'
  exported_at: '2026-04-07T12:00:00Z'
  source:
    organization_id: 100
  object_counts:
    dashboards: 1
    topologies: 0
    architectures: 0
    datasources: 1
    namespaces: 1

dashboards: []
topologies: []
architectures: []
datasources: []
namespaces: []
```

章节规则：

1. 允许部分章节为空或缺失；缺失章节按空数组处理。
2. 导入导出共用同一 schema_version（本期固定 `1.0.0`）。
3. 任意对象中不得出现数据库主键/外键 ID 字段作为身份或关系依据。

### 3.2 业务键（Canonical Key）

```text
namespace_key    = namespace.name
datasource_key   = datasource.name + "::" + datasource.rest_api
dashboard_key    = "dashboard::" + dashboard.name
topology_key     = "topology::" + topology.name
architecture_key = "architecture::" + architecture.name
```

规则：

1. YAML 内引用一律使用上述 key，不使用 DB ID。
2. 导入时先建立 `key -> target_db_id` 映射，再写入对象引用。

### 3.3 对象结构（最小必要字段）

```yaml
dashboards:
  - key: 'dashboard::CPU总览'
    name: 'CPU总览'
    description: '...'
    view_sets:
      - valueConfig:
          dataSource: '指标数据源::/api/v1/metric'
      - x: 0
        y: 0
    other: {}
    refs:
      datasource_keys: ['指标数据源::/api/v1/metric']
      namespace_keys: ['prod']

datasources:
  - key: '指标数据源::/api/v1/metric'
    name: '指标数据源'
    rest_api: '/api/v1/metric'
    tags: ['监控']
    chart_type: ['line', 'bar']
    params: {}
    namespace_keys: ['prod']

namespaces:
  - key: 'prod'
    name: 'prod'
    domain_name: 'https://example.com'
    username: 'ops'
    password: '******'
    logical_name_space: 'default'
    tls: true
```

画布 `view_sets` 契约规则：

1. `dashboard.view_sets` 在 YAML 中直接使用数组，与真实运行时/存储结构一致。
2. `topology.view_sets` 在 YAML 中使用 `{ nodes, edges }`。
3. `architecture.view_sets` 在 YAML 中使用 `{ items, views }`。
4. YAML 契约不为了表面统一额外包装 `dashboard.view_sets`（即不使用 `{ layout: [...] }`）。

### 3.4 敏感字段策略

1. 导出时 `password`、`secret`、`token` 统一脱敏为 `"******"`。
2. 导入时若字段为 `"******"`，视为“需补充”；不覆盖目标已存在明文配置。
3. 对新建对象若存在必填敏感字段且值为 `"******"`，导入标记失败并返回明确原因。

### 3.5 非法 DB ID 拦截规则

预检阶段执行以下检测：

1. 若对象中出现字段名命中正则 `(^|_)(id|ids)$` 且属于引用语义，直接报错。
2. 若引用字段值为纯数字且无业务键前缀，直接报错。
3. 报错码固定 `OA_YAML_ID_REFERENCE_FORBIDDEN`。

## 4. 开放接口定义（字段级）

统一前缀：`/operation_analysis/api/import_export`

### 4.1 导出接口

`POST /export/`

请求：

```json
{
  "scope_type": "canvas|config",
  "object_types": [
    "dashboard",
    "topology",
    "architecture",
    "datasource",
    "namespace"
  ],
  "object_keys": ["dashboard::CPU总览"]
}
```

响应：

```json
{
  "request_id": "uuid",
  "yaml_content": "<yaml_string>",
  "summary": {
    "exported": {
      "dashboards": 1,
      "topologies": 0,
      "architectures": 0,
      "datasources": 1,
      "namespaces": 1
    }
  }
}
```

### 4.2 导入预检接口

`POST /import/precheck/`

请求：

```json
{
  "yaml_content": "<yaml_string>",
  "target_directory_id": 12,
  "default_conflict_action": "skip|overwrite|rename"
}
```

规则：

1. 当 YAML 含画布对象时，`target_directory_id` 必填。
2. 页面导入场景下，`target_directory_id` 固定为用户当前所在目录 ID（由前端自动注入）。

响应：

```json
{
  "request_id": "uuid",
  "valid": true,
  "counts": {
    "total": 12,
    "by_type": { "dashboard": 1, "datasource": 5, "namespace": 6 }
  },
  "conflicts": [
    {
      "object_key": "dashboard::CPU总览",
      "object_type": "dashboard",
      "reason": "name_conflict",
      "suggested_actions": ["skip", "overwrite", "rename"]
    }
  ],
  "warnings": [
    {
      "code": "OA_SECRET_PLACEHOLDER",
      "message": "datasource secret placeholder found"
    }
  ],
  "errors": []
}
```

### 4.3 导入提交接口

`POST /import/submit/`

请求：

```json
{
  "yaml_content": "<yaml_string>",
  "target_directory_id": 12,
  "conflict_decisions": [
    {
      "object_key": "dashboard::CPU总览",
      "action": "rename",
      "new_name": "CPU总览_copy_20260407153000"
    }
  ]
}
```

规则：

1. `conflict_decisions` 为可选字段。
2. 当 `conflict_decisions` 缺失时，服务端对全部冲突对象默认执行 `rename`。
3. 默认 `rename` 名称由服务端生成，规则为 `原名称_copy`；若重名继续追加递增后缀。
4. 当 YAML 含画布对象时，`target_directory_id` 必须等于导入入口所在目录 ID。

响应：

```json
{
  "request_id": "uuid",
  "status": "completed",
  "counts": { "success": 10, "failed": 1, "skipped": 0, "overwritten": 1 },
  "items": [
    {
      "object_key": "dashboard::CPU总览",
      "object_type": "dashboard",
      "action": "rename",
      "status": "success",
      "reason": ""
    },
    {
      "object_key": "prod",
      "object_type": "namespace",
      "action": "overwrite",
      "status": "failed",
      "reason": "secret_required"
    }
  ],
  "message": "import completed"
}
```

## 5. 后端实现流程（确定性步骤）

### 5.1 导出流程

```text
Step 1: 校验入参（scope_type/object_types/object_keys）
Step 2: 读取对象（按 object_keys）
Step 3: 依赖收敛（仅收集实际引用 datasource/namespace）
Step 4: DB对象 -> YAML对象转换（生成 canonical key）
Step 5: 敏感字段脱敏
Step 6: 稳定排序（按 object_type + name）
Step 7: 序列化输出 yaml_content
Step 8: 返回 summary
```

### 5.2 预检流程

```text
Step 1: 检查阈值（大小<=2MB、对象<=200）
Step 2: YAML 解析（safe_load）
Step 3: schema_version 与章节结构校验
Step 4: 非法 DB ID 引用扫描
Step 5: 业务键唯一性校验
Step 6: 依赖完整性校验（refs 是否可解析）
Step 7: 冲突识别（目标环境同名/同业务键）
Step 8: 生成 counts/conflicts/warnings/errors
```

### 5.3 导入流程

```text
Step 1: 重复执行预检（导入接口内强制）
Step 2: 解析 conflict_decisions（未提供则对冲突对象 default=rename）
Step 3: 开启数据库事务
Step 4: 校验 target_directory_id（画布对象必填，且为当前导入目录）
Step 5: 先导入 namespaces -> datasources -> canvases
Step 6: 每个对象按 action 执行：
        - skip: 记 skipped
        - overwrite: 全量覆盖 YAML 声明对象
        - rename: 按 new_name 创建新对象
Step 7: 画布对象统一写入 target_directory_id（当前目录）
Step 8: 根据 key->id 映射回填画布内引用
Step 9: 遇关键错误时回滚事务并标记失败对象
Step 10: 生成对象级 items 与聚合 counts
Step 11: 返回 completed 结果
```

### 5.4 事务与失败策略

1. 单次导入使用单事务。
2. 关键依赖失败（如引用无法解析）触发事务回滚。
3. 非关键告警（如脱敏占位需补充）不触发回滚，写入 warning。

## 6. 前端实现流程（确定性步骤）

### 6.1 导出流程

```text
1) 用户在目录下的画布点击“导出 YAML”
2) 组装 export 请求参数
3) 调用 /export/
4) 下载 yaml_content 为 .yaml 文件
5) 展示导出对象统计
```

### 6.2 导入流程

```text
1) 用户在某个目录下点击“导入 YAML”
2) 调用 /import/precheck/
3) 展示对象概览 + 冲突列表 + 风险提示
4) 用户逐项选择冲突动作（skip/overwrite/rename）；未选择时默认 rename
5) 前端自动注入当前目录的 target_directory_id（无需用户二次选择）
6) 调用 /import/submit/
7) 导入后的画布在当前目录下生效并展示对象级导入结果（success/failed/skipped/overwritten）
```

### 6.3 前端接口文件约束

`web/src/app/ops-analysis/api/importExport.ts`

```typescript
export interface ExportRequest {
  scope_type: 'canvas' | 'config';
  object_types: Array<
    'dashboard' | 'topology' | 'architecture' | 'datasource' | 'namespace'
  >;
  object_keys: string[];
}
```

## 7. 错误码与返回约定

```text
OA_YAML_TOO_LARGE                    # 超过2MB
OA_IMPORT_OBJECT_LIMIT_EXCEEDED      # 对象数超过200
OA_YAML_PARSE_ERROR                  # YAML语法错误
OA_YAML_SCHEMA_INVALID               # schema不合法
OA_YAML_ID_REFERENCE_FORBIDDEN       # 出现数据库ID引用
OA_IMPORT_CONFLICT_UNRESOLVED        # 冲突未决策
OA_IMPORT_TARGET_DIRECTORY_REQUIRED  # 画布导入未指定目录
OA_IMPORT_DEPENDENCY_MISSING         # 依赖缺失
OA_IMPORT_SECRET_REQUIRED            # 新建对象缺失敏感字段
```

返回格式统一：

```json
{
  "result": false,
  "code": "OA_YAML_SCHEMA_INVALID",
  "message": "invalid yaml schema",
  "data": {}
}
```

## 8. 测试方案

### 8.1 后端单测

1. 导出仅包含实际依赖对象。
2. 导出内容不含 DB ID。
3. 预检可识别非法 ID 引用。
4. 预检可识别冲突并返回 actions。
5. `overwrite` 为全量覆盖（未声明字段按模型默认）。
6. `rename` 生成固定后缀命名。
7. 新建对象敏感字段占位触发失败。
8. 导入不删除未命中对象。

### 8.2 前端联调用例

1. 单画布导出并可下载 YAML。
2. 仅配置对象 YAML 可成功预检与导入。
3. 冲突三策略（skip/overwrite/rename）交互可用。
4. 画布导入未选目录时提交被拦截。
5. 结果面板显示对象级状态与失败原因。

### 8.3 回归范围

1. 运营分析现有 CRUD 不受影响。
2. 数据源取数链路不受影响。
3. 权限未授权场景下导入导出不可执行。

## 9. 发布与回滚策略

### 9.1 发布策略

1. 后端先发布新接口，前端入口灰度开启。
2. 入口开关按模块配置控制（仅运营分析）。
3. 首批仅对管理员角色可见。

### 9.2 回滚策略

1. 关闭前端导入导出入口开关。
2. 后端接口保留但返回维护态（可选）或通过路由回退。
3. 导入事务失败自动回滚，避免半成品落库。

## 10. OpenCode 执行任务拆分

```text
T1  新增 import_export 常量与 schema 校验模块
T2  新增 export_service 并完成导出单测
T3  新增 precheck_service 并完成预检单测
T4  新增 import_service（含overwrite/rename/skip）并完成单测
T5  新增 import_export_view 与 urls 路由
T6  新增前端 api/importExport.ts
T7  新增导入导出弹窗组件（导出/预检/冲突/结果）
T8  在 5 个入口页面接入按钮与流程
T9  完成前后端联调与错误码映射
T10 执行最小回归并输出验证记录
```

每个任务完成判据：

1. 至少 1 个可执行测试或手动验证步骤。
2. 输出与本 Tech Plan 接口字段完全一致。
3. 不修改模块边界外代码。
4. 新增或重构代码需包含“合适注释”，满足本 Tech Plan 的注释规范。

## 11. 代码注释规范（代码生成强制）

1. 对外接口（View/API 方法）必须有函数级注释，说明用途、关键入参、返回结构与错误语义。
2. 复杂业务逻辑必须有块级注释，至少覆盖：依赖收敛、冲突决策、业务键映射、事务回滚条件。
3. 非直观规则必须有行内注释，至少覆盖：默认 `rename` 触发条件、`target_directory_id` 当前目录约束、敏感字段占位处理。
4. 注释内容必须解释“为什么”，避免仅复述代码“做了什么”。
5. 禁止无意义注释（如“设置变量”“循环开始”），避免注释噪音。
6. 注释语言统一中文，术语与本文档保持一致（如 `overwrite`、`rename`、业务键、预检）。

## 12. 待人工确认项

当前无待人工确认项。
