# CMDB 模型字段治理标记设计

日期：2026-06-10

## 背景

CMDB 数据治理需要在字段定义层面回答两个问题：

- 哪些字段是关键属性，用于后续完整性度量。
- 每个字段应多久核实一次，用于后续新鲜度度量。

本阶段只交付模型字段治理标记的定义与维护，不做治理健康度计算，不在实例录入、实例列表、实例详情中暴露治理标记，也不接入运营分析仪表盘。

本需求只面向商业版。社区版代码只保留稳定扩展缝，商业版代码拥有真实治理规则和展示逻辑。

## 目标

- 在模型字段定义中新增系统预定义的治理标记属性族。
- 本期支持两个标记：
  - 关键属性：是/否，默认否。
  - 时效性：未设置、需要及时更新、不频繁更新、基本不变。
- 标记均为可选，未设置时不影响字段现有行为。
- 附件、图片、表格、密码字段不可设置治理标记。
- 治理标记随模型配置导入导出。
- 治理标记变更在模型管理变更记录中可追溯。
- 前后端商业逻辑按仓库现有成熟方式分离。

## 非目标

- 管理员自定义标记维度或选项。
- 时效性时窗配置。
- 治理健康度计算。
- 运营分析仪表盘展示。
- 实例创建、编辑、列表、详情侧暴露治理标记。
- 关系完整性、字段分层等后续治理维度。

## 采用的现有模式

### 后端模式

CMDB 已有社区扩展注册表：`server/apps/cmdb/extensions/registry.py`。

模型能力域已有社区契约：`server/apps/cmdb/model_ops/extensions.py` 中的 `ModelEnterpriseExtension`。

商业版通过 `enterprise/server/apps/cmdb_enterprise/model_ops/provider.py` 注册企业实现。

本设计继续扩展模型能力域契约。社区代码只调用契约，不包含商业治理规则。

### 前端模式

前端不参考 CMDB 现有附件/图片字段的社区硬编码方式。

本需求参考 `system-manager` 的企业 hook 增强模式：

- 社区代码定义默认实现。
- 社区代码尝试加载 `@/app/<module>/(enterprise)/...`。
- 企业模块不存在时回退到社区默认实现。
- 企业代码在 `enterprise/web/src/app/...` 下提供真实增强。

参考位置：

- `web/src/app/system-manager/hooks/useUserModalData.ts`
- `web/src/app/system-manager/hooks/useSensitiveFieldEditBehavior.ts`
- `enterprise/web/src/app/system-manager/hooks/useSensitiveFieldEditBehavior.ts`

## 数据模型

在模型字段 `attrs` JSON 的每个字段对象上新增同级属性族 `governance`。

```json
{
  "attr_id": "inst_name",
  "attr_name": "实例名称",
  "attr_type": "str",
  "is_required": true,
  "is_only": true,
  "editable": true,
  "governance": {
    "key_attribute": true,
    "freshness": "timely"
  }
}
```

`governance` 表示治理标记属性族。它与 `is_required`、`is_only`、`editable` 同级；具体治理维度放在 `governance` 内部，便于后续扩展。

### governance 字段

`key_attribute`：

- 类型：布尔值。
- 默认值：`false`。
- 含义：是否为关键属性，供后续完整性度量使用。

`freshness`：

- 类型：字符串。
- 默认值：`""`。
- 可选值：
  - `""`：未设置。
  - `timely`：需要及时更新，固定 7 天判定窗口。
  - `occasional`：不频繁更新，固定 90 天判定窗口。
  - `stable`：基本不变，不参与新鲜度判定。

时效性判定窗口是商业版固定常量，不提供配置入口：

```python
{
    "timely": 7,
    "occasional": 90,
    "stable": None,
}
```

## 不支持的字段类型

以下字段类型不支持治理标记：

- `attachment`
- `image`
- `table`
- `pwd`

商业版后端对这些字段统一规范化为默认治理结构：

```json
{
  "key_attribute": false,
  "freshness": ""
}
```

这里采用规范化而不是报错。这样字段类型切换到不支持类型时，编辑流程更稳定，后端也能兜底清理绕过前端提交的治理值。

## 后端代码分离

社区代码只拥有扩展缝和公共数据流。

`ModelEnterpriseExtension` 增加或复用以下契约：

- 复用现有 `validate_attr(attr)`，在字段新增/编辑时规范化字段元数据。
- 增加模型配置导入行规范化 hook。
- 增加模型配置导出列 hook。
- 增加字段变更记录 diff 文案 hook。

边界要求：

- 社区代码负责调用扩展 hook。
- 商业代码负责治理字段名、枚举值、校验规则、展示文案和导入导出列。
- 社区代码不写死关键属性、时效性等商业语义。

商业版实现位置：

```text
enterprise/server/apps/cmdb_enterprise/model_ops/provider.py
```

商业版 provider 负责：

- 定义 `governance` 字段结构。
- 定义时效性可选值。
- 定义固定时窗。
- 规范化不支持字段类型。
- 输出校验错误信息。
- 输出变更记录治理 diff 文案。
- 输出模型配置导入导出的治理列定义与解析逻辑。

## 后端数据流

### 新增字段

1. `ModelManage.create_model_attr` 接收字段 payload。
2. 现有 tag、enum、default value 等规范化逻辑继续执行。
3. 通过 `get_model_enterprise_extension().validate_attr(attr)` 进入商业版规范化。
4. 商业版规范化 `attr["governance"]`。
5. 规范化后的字段写入模型 `attrs` JSON。
6. 创建模型管理变更记录。
7. 商业版扩展补充治理标记相关 message 片段。

### 编辑字段

1. `ModelManage.update_model_attr` 读取当前字段。
2. 通过 `get_model_enterprise_extension().validate_attr(attr)` 规范化传入字段。
3. 更新字段时必须显式持久化 `governance`，不能只更新现有白名单字段。
4. 治理标记发生变化时，变更记录 message 追加治理 diff。

示例：

```text
治理标记: 关键属性 否 -> 是; 时效性 未设置 -> 需要及时更新(7天)
```

### 查询字段

现有 `attr_list` 和 `field_groups/full_info` 继续返回字段 `attrs`。

旧字段没有 `governance` 时，商业扩展和前端按默认值处理。

### 复制模型

模型复制现有逻辑会整体复制 `attrs` JSON。治理标记自然随字段复制，不需要额外同步表。

### 删除字段

删除字段时从 `attrs` 中移除整个字段对象，治理标记随字段一起消失。

## 前端代码分离

社区 CMDB 属性管理页只增加企业扩展加载点，不包含治理标记 UI。

社区默认扩展接口：

```ts
interface AttributeEnterpriseExtension {
  getExtraColumns: () => ColumnItem[];
  renderExtraFormItems: (context: AttributeFormContext) => React.ReactNode;
  normalizeInitialValues: (values: AttrFieldType) => AttrFieldType;
  normalizeSubmitValues: (values: AttrFieldType) => AttrFieldType;
}
```

社区默认实现：

```ts
{
  getExtraColumns: () => [],
  renderExtraFormItems: () => null,
  normalizeInitialValues: values => values,
  normalizeSubmitValues: values => values,
}
```

社区加载方式参考 `system-manager`：

```ts
try {
  const mod = require('@/app/cmdb/(enterprise)/hooks/useAttributeEnterpriseExtension');
  return mod.useAttributeEnterpriseExtension || useCEAttributeEnterpriseExtension;
} catch {
  return useCEAttributeEnterpriseExtension;
}
```

社区属性页只在稳定扩展点使用该能力：

- 属性表格 columns 追加企业列。
- 属性弹窗渲染企业表单区。
- 编辑回显前调用 `normalizeInitialValues`。
- 提交前调用 `normalizeSubmitValues`。

商业版前端实现位置：

```text
enterprise/web/src/app/cmdb/hooks/useAttributeEnterpriseExtension.tsx
```

商业版前端负责：

- 返回治理标记表格列。
- 返回治理标记表单分组。
- 定义时效性选项与展示文案。
- 处理不支持字段类型的禁用与清空逻辑。

## 前端交互

治理表单按分组展示，分组标题为“治理标记”。

位置：

- 字段类型和类型专属配置之后。
- 必填、可编辑之前。

支持治理标记的字段类型：

- 显示可编辑治理控件。
- 关键属性：是/否。
- 时效性：未设置、需要及时更新、不频繁更新、基本不变。

不支持治理标记的字段类型：

- 显示禁用态或简短提示。
- 当字段类型切换到 `attachment`、`image`、`table`、`pwd` 时清空治理表单值。
- 提交默认治理值。

属性表格商业版追加列：

- 关键属性：是/否。
- 时效性：未设置 / 需要及时更新(7天) / 不频繁更新(90天) / 基本不变(不参与判定)。

## 模型配置迁移

内部存储使用 `governance` 分组 JSON，Excel 导入导出使用平铺列，便于用户维护。

英文列：

- `governance_key_attribute`
- `governance_freshness`

中文列：

- `关键属性`
- `时效性`

导出流程：

1. 社区代码按现有逻辑生成模型字段行。
2. 调用商业扩展追加治理列。
3. 旧字段没有 `governance` 时导出默认值。
4. 无商业扩展时不追加治理列。

导入流程：

1. 社区代码按现有逻辑读取 Excel。
2. 调用商业扩展解析治理列。
3. 商业扩展把平铺列规范化为 `attr["governance"]`。
4. 导入合并已有字段时，把 `governance` 纳入可更新字段。

旧模板没有治理列时仍可正常导入。

## 校验策略

商业版后端是唯一可信校验入口。

校验规则：

- `governance` 缺失：补默认结构。
- `key_attribute` 缺失：补 `false`。
- `key_attribute` 非布尔值：拒绝。
- `freshness` 缺失：补 `""`。
- `freshness` 不在允许范围内：拒绝。
- 不支持字段类型：治理标记清空为默认结构。

错误文案：

- `关键属性标记必须为布尔值`
- `时效性标记不合法`

前端校验只用于改善体验，不能作为唯一防线。

## 测试设计

### 后端社区侧

- 未注册商业实现时，模型企业扩展保持 no-op。
- 字段新增/编辑继续调用企业扩展，不破坏现有行为。
- 旧字段没有 `governance` 时，字段查询与模型配置导出不报错。

### 后端商业侧

- 新增普通字段时补默认 `governance`。
- 新增普通字段时可保存 `key_attribute=true`。
- 新增普通字段时可保存每个合法 `freshness` 值。
- 编辑普通字段时可修改治理标记。
- `attachment`、`image`、`table`、`pwd` 字段保存后治理标记被清空。
- 非法 `freshness` 被拒绝。
- 非法 `key_attribute` 被拒绝。
- 变更记录 message 包含治理标记 diff。
- 模型配置导出包含治理列。
- 模型配置导入能解析治理列。
- 导入合并已有字段时能更新 `governance`。

### 前端社区侧

- 无企业扩展时，属性表格不出现治理列。
- 无企业扩展时，属性弹窗不出现治理标记分组。
- 无企业扩展时，提交 payload 不包含治理标记。

### 前端商业侧

- 企业扩展返回治理表格列。
- 属性弹窗渲染治理标记分组。
- 旧字段没有 `governance` 时按默认值回显。
- 支持字段类型提交 `governance`。
- 不支持字段类型禁用或清空治理标记。
- 切换到不支持字段类型时清空治理标记。
- 时效性文案包含固定窗口。

## 验证命令

后端：

```bash
cd server && make test
```

前端：

```bash
cd web && pnpm lint && pnpm type-check
```

实现过程中可以先跑聚焦测试；最终变更应通过受影响模块的质量门禁。

## 实施注意事项

- 本需求不实现第二阶段治理健康度计算。
- 本需求不实现第三阶段运营分析仪表盘展示。
- 不把整个 CMDB 属性管理页复制到企业版。
- 前端商业分离参考 `system-manager` hook 增强模式。
- 不沿用 CMDB 附件/图片字段当前在社区前端硬编码的做法。
