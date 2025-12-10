# 监控插件 JSON 配置模板说明文档

## 概述

本文档详细说明监控插件 JSON 配置模板的结构和用法。该配置系统用于将监控插件的前端配置从硬编码迁移到 JSON 文件，支持批量新增（auto 模式）和编辑（edit 模式）两种场景。

**适用场景：**
- 各种监控插件配置

---

## 一、配置文件结构

### 1.1 顶层配置

```json
{
  "object_name": "Switch",
  "instance_type": "switch",
  "collect_type": "snmp",
  "config_type": ["switch"],
  "collector": "telegraf",
  "config_type_field": "metric_type",
  "instance_id": "{{cloud_region}}_{{instance_type}}_snmp_{{ip}}",
  "form_fields": [ ... ],
  "table_columns": [ ... ],
  "extra_fields": { ... }
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `object_name` | string | 是 | 监控对象名称(id,如Host、Mysql) |
| `instance_type` | string | 是 | 监控对象类型 |
| `collect_type` | string | 是 | 采集类型（如 snmp, ipmi, host） |
| `config_type` | array | 是 | 配置类型（如["switch"]、["mongodb"]） |
| `collector` | string | 是 | 采集器名称（如 telegraf） |
| `config_type_field` | string | 否 | 指定从哪个表单字段获取 config_type（用于动态配置类型） |
| `instance_id` | string | 否 | 实例ID生成模板（仅 auto 模式使用） |
| `form_fields` | array | 是 | 表单字段配置（auto 和 edit 模式共用） |
| `table_columns` | array | 否 | 表格列配置（仅 auto 模式使用） |
| `extra_edit_fields` | object | 否 | 额外字段配置（仅 edit 模式使用） |

**重要变化：**
- 移除了 `auto` 和 `edit` 层级，所有配置平铺在顶层
- `form_fields` 在 auto 和 edit 模式下共用，通过简单属性控制差异
- 使用 `editable` 控制字段是否可编辑（edit 模式下禁用）
- 使用 `visible_in` 控制字段可见性（'auto', 'edit', 'both'）
- `table_columns` 仅在 auto 模式下使用
- `extra_edit_fields` 仅在 edit 模式下使用

**新增功能：**
- ✨ **字段加密支持**：在 `form_fields` 和 `table_columns` 中添加 `"encrypted": true` 即可自动加密敏感字段（如密码、API密钥）

---

## 二、配置字段说明

### 2.1 form_fields（表单字段）

表单字段配置在 auto 和 edit 模式下共用，通过简单的顶层属性控制不同模式下的行为。

#### 基本结构

```json
{
  "name": "port",
  "label": "端口",
  "type": "inputNumber",
  "required": true,
  "editable": false,
  "default_value": 161,
  "tooltip": "SNMP 服务监听端口，默认为 161",
  "widget_props": { ... },
  "dependency": { ... },
  "data_transform": { ... }
}
```

#### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 字段名称（提交到后端的字段名） |
| `label` | string | 是 | 字段标签（显示文本，后端要支持 i18n） |
| `type` | string | 是 | 字段类型，见下方类型列表 |
| `required` | boolean | 是 | 是否必填 |
| `default_value` | any | 否 | 默认值（仅 auto 模式使用） |
| `tooltip` | string | 否 | 表单字段描述 （后端要支持 i18n）|
| `widget_props` | object | 否 | 前端组件属性配置（如inputNumber的最大值） |
| `dependency` | object | 否 | 字段依赖关系（表单联动） |
| `options` | array | 否 | 下拉选项（type 为 select 时） |
| `editable` | boolean | 否 | 是否可编辑，false 时 edit 模式下禁用（默认 true） |
| `visible_in` | string | 否 | 可见性控制：'auto'、'edit'、'both'（默认 'both'） |
| `encrypted` | boolean | 否 | 是否加密，true 时字段值使用 hash 加密后提交（默认 false） |
| `data_transform` | object | 否 | 数据转换配置（edit 模式使用） |

#### 支持的字段类型

| 类型 | 说明 | 示例 | 加密支持 |
|------|------|------|----------|
| `input` | 文本输入框 | IP 地址、主机名 | ✅ 支持 |
| `inputNumber` | 数字输入框 | 端口号、超时时间 | ✅ 支持 |
| `select` | 下拉选择框 | SNMP 版本、安全级别 | ✅ 支持 |
| `password` | 密码输入框 | 认证密码、加密密码 | ⭐ 推荐 |
| `textarea` | 多行文本框 | 备注、描述 | ✅ 支持 |
| `checkbox` | 单个复选框 | 开关选项 | ⚠️ 不推荐 |
| `checkbox_group` | 复选框组 | 多选指标类型（如 CPU、内存、磁盘） | ⚠️ 不推荐 |

**加密字段类型建议：**
- ⭐ **强烈推荐**：`password` - 专为敏感信息设计
- ✅ **适合使用**：`input`, `textarea` - 用于API密钥、Token等
- ⚠️ **不推荐**：`checkbox`, `checkbox_group`, `select` - 不适合加密

#### widget_props 配置

不同字段类型支持不同的 props：

**inputNumber 专用：**
```json
"widget_props": {
  "min": 1,
  "max": 65535,
  "placeholder": "SNMP 端口", // （后端要支持 i18n，可以不填，前端默认请输入）
  "addonAfter": "s"  // 后缀单位
}
```

**select 专用：**
```json
"widget_props": {
  "placeholder": "选择 SNMP 版本", //（后端要支持 i18n，可以不填，前端默认请选择）
  "mode": "multiple"  // 可选，多选模式
}
```

**通用：**
```json
"widget_props": {
  "placeholder": "提示文本", //（后端要支持 i18n，可以不填，前端默认请选择或请输入）
  "disabled": true, // 是否禁用
  "width": 200 // 组件长度、默认100%
}
```

#### 字段依赖关系

用于实现动态显示/隐藏字段：

```json
"dependency": {
  "field": "version",     // 依赖的字段名
  "value": 2              // 当该字段值等于此值时显示
}
```

**示例：**
```json
// community 字段仅在 version=2 时显示
{
  "name": "community",
  "label": "Community",
  "type": "input",
  "dependency": {
    "field": "version",
    "value": 2
  }
}
```

#### 模式控制属性

**特性说明**：通过简单的顶层属性控制字段在 auto 和 edit 模式下的行为。

##### 控制属性

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `editable` | boolean | true | 为 false 时，字段在 edit 模式下禁用（只读） |
| `visible_in` | string | "both" | 控制字段可见性："auto" 仅批量新增可见，"edit" 仅编辑可见，"both" 两者都可见 |

##### 使用场景

**场景1：控制字段可见性和编辑状态**

在 edit 模式下显示 IP 字段（只读），auto 模式下隐藏：

```json
{
  "name": "ip",
  "label": "IP",
  "type": "input",
  "required": true,
  "visible_in": "edit",  // 仅在编辑模式显示
  "editable": false,      // 禁用状态（只读）
  "data_transform": {
    "origin_path": "child.content.config.agents[0]",
    "to_form": {
      "regex": "://([^:]+):"
    }
  }
}
```

**场景2：编辑模式下禁用字段**

auto 模式下可选择，edit 模式下仅显示（不可编辑）：

```json
{
  "name": "metric_type",
  "label": "指标类型",
  "type": "checkbox_group",
  "required": true,
  "default_value": ["cpu", "disk", "mem"],
  "editable": false,  // edit 模式下禁用
  "options": [
    { "label": "CPU", "value": "cpu" },
    { "label": "Disk", "value": "disk" },
    { "label": "Memory", "value": "mem" }
  ],
  "data_transform": {
    "origin_path": "child.content.config.tags.config_type",
    "to_form": {
      "array": true
    }
  }
}
```

**场景3：edit 模式禁用编辑**

端口字段在 edit 模式下禁用编辑：

```json
{
  "name": "port",
  "label": "端口",
  "type": "inputNumber",
  "required": true,
  "default_value": 161,
  "editable": false,  // edit 模式禁用
  "widget_props": {
    "min": 1,
    "max": 65535
  },
  "data_transform": {
    "origin_path": "child.content.config.agents[0]",
    "to_form": {
      "regex": ":(\\d+)$"
    }
  }
}
```

#### 完整示例

**简单字段（auto 和 edit 共用）：**
```json
{
  "name": "version",
  "label": "版本",
  "type": "select",
  "required": true,
  "default_value": 2,
  "editable": false,  // edit 模式禁用
  "options": [
    { "label": "v2c", "value": 2 },
    { "label": "v3", "value": 3 }
  ],
  "widget_props": {
    "placeholder": "选择 SNMP 版本"
  },
  "data_transform": {
    "origin_path": "child.content.config.version"
  }
}
}
```

**依赖字段（带 edit 模式配置）：**
```json
{
  "name": "community",
  "label": "Community",
  "type": "input",
  "required": true,
  "default_value": "public",
  "widget_props": {
    "placeholder": "SNMP Community 字符串"
  },
  "dependency": {
    "field": "version",
    "value": 2
  },
  "mode_config": {
    "edit": {
      "data_transform": {
        "origin_path": "child.content.config.community",
        "to_api": {}  // 空对象表示原值提交
      }
    }
  }
}
```

**带单位的数字字段：**
```json
{
  "name": "interval",
  "label": "采集间隔",
  "type": "inputNumber",
  "required": true,
  "default_value": 10,
  "tooltip": "数据采集间隔时间",
  "widget_props": {
    "min": 1,
    "precision": 0,
    "placeholder": "采集间隔",
    "addonAfter": "s"
  },
  "mode_config": {
    "edit": {
      "data_transform": {
        "origin_path": "child.content.config.interval",
        "to_form": {
          "regex": "^(\\d+)s$"  // "10s" → 10
        },
        "to_api": {
          "suffix": "s"  // 10 → "10s"
        }
      }
    }
  }
}
```

**复选框组（配合 config_type_field）：**
```json
{
  "name": "metric_type",
  "label": "指标类型",
  "type": "checkbox_group",
  "required": true,
  "default_value": ["cpu", "disk", "mem"],
  "tooltip": "CPU: 监控CPU使用情况\nDisk: 监控磁盘使用情况\nMemory: 监控内存使用情况",
  "options": [
    { "label": "CPU", "value": "cpu" },
    { "label": "Disk", "value": "disk" },
    { "label": "Memory", "value": "mem" }
  ],
  "widget_props": {},
  "mode_config": {
    "auto": {
      "type": "checkbox_group"
    },
    "edit": {
      "type": "select",
      "widget_props": {
        "mode": "multiple",
        "disabled": true
      },
      "data_transform": {
        "origin_path": "child.content.config.tags.config_type",
        "to_form": {
          "array": true
        }
      }
    }
  }
}
```

**加密字段示例：**
```json
{
  "name": "api_key",
  "label": "API密钥",
  "type": "password",
  "required": true,
  "encrypted": true,
  "description": "用于身份验证的API密钥，提交时会自动加密",
  "widget_props": {
    "placeholder": "请输入API密钥"
  },
  "transform_on_edit": {
    "origin_path": "child.content.config.api_key"
  }
}
```

**说明：**
- `mode_config` 是可选的，如果字段在两种模式下行为完全一致，可以不配置
- `data_transform` 仅在 edit 模式有效
- `default_value` 仅在 auto 模式使用
- `tooltip` 支持使用 `\n` 换行
- `encrypted` 为 true 时，字段值在提交前会自动使用 hash 算法加密

### 2.2 table_columns（表格列配置）

**仅 auto 模式使用**，用于批量添加时的表格列定义。

#### 基本结构

```json
{
  "name": "ip",
  "label": "IP",
  "type": "input",
  "required": true,
  "default_value": "",
  "widget_props": { ... },
  "change_handler": { ... },
  "options_key": "node_ids_option",
  "enable_row_filter": false
}
```

#### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 列名（传给后端的名称） |
| `label` | string | 是 | 列标题（后端要支持 i18n） |
| `type` | string | 是 | 列类型 |
| `required` | boolean | 是 | 是否必填 |
| `default_value` | any | 是 | 默认值 |
| `widget_props` | object | 否 | 组件属性 |
| `change_handler` | object | 否 | 值变化处理器 |
| `options` | array | 否 | type为select时的下拉列表，目前有节点、组由前端接口获取，不用传options |
| `enable_row_filter` | boolean | 否 | 是否启用行过滤（去重节点，比如第一行选了某个节点，第二行不能选这个节点） |
| `encrypted` | boolean | 否 | 是否加密，true 时字段值使用 hash 加密后提交（默认 false） |
| `rules` | array | 否 | 失焦验证规则，支持必填、正则、自定义验证 |

#### change_handler（值变化处理，表格字段联动）

用于实现字段联动：

**simple 类型（简单复制）：**
```json
"change_handler": {
  "type": "simple",
  "source_fields": ["ip"],
  "target_field": "instance_name"
}
```
- 当 `ip` 字段变化时，自动复制到 `instance_name` 字段

**combine 类型（组合拼接）：**
```json
"change_handler": {
  "type": "combine",
  "source_fields": ["host", "port"],
  "target_field": "instance_name",
  "separator": ":"
}
```
- 将 `host` 和 `port` 用 `:` 拼接后赋值给 `instance_name`

#### rules（验证规则）

用于字段的失焦验证，支持多种验证类型。

**基本结构：**
```json
"rules": [
  {
    "type": "required",
    "message": "请输入URL"
  },
  {
    "type": "pattern",
    "pattern": "^https?://",
    "message": "URL必须以http://或https://开头"
  }
]
```

**支持的验证类型：**

**pattern（正则验证）**
```json
{
  "type": "pattern",
  "pattern": "^(\\d{1,3}\\.){3}\\d{1,3}$",
  "message": "请输入正确的IP地址格式",
  "excel_formula": "AND(LEN({{CELL}})-LEN(SUBSTITUTE({{CELL}},\".\",\"\"))=3,ISNUMBER(VALUE(LEFT({{CELL}},FIND(\".\",{{CELL}})-1))))",
  "excel_vars": {
    "CELL": "cell_ref"
  }
}
```

**字段说明：**
- `type`: 固定为 "pattern"
- `pattern`: 正则表达式（用于前端验证）
- `message`: 错误提示信息
- `excel_formula`: （可选）Excel公式字符串，用于Excel模板的数据验证。支持变量占位符：
  - `{{CELL}}`: 会被替换为实际单元格引用（如A2）
  - `{{ROW}}`: 会被替换为当前行号（如2）
  - `{{COL}}`: 会被替换为当前列字母（如A）
  - 自定义变量: 在excel_vars中定义的其他变量
- `excel_vars`: （可选）自定义变量映射，key为变量名，value为计算逻辑

**常用正则示例：**

- **URL验证**：
  - `"pattern": "^https?://.*"`
  - `"excel_formula": "OR(LEFT({{CELL}},7)=\"http://\",LEFT({{CELL}},8)=\"https://\")"`
  
- **邮箱验证**：
  - `"pattern": "^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$"`
  - `"excel_formula": "AND(ISNUMBER(FIND(\"@\",{{CELL}})),ISNUMBER(FIND(\".\",{{CELL}},FIND(\"@\",{{CELL}}))))"`
  
- **IP地址验证**：
  - `"pattern": "^(\\d{1,3}\\.){3}\\d{1,3}$"`
  - `"excel_formula": "AND(LEN({{CELL}})-LEN(SUBSTITUTE({{CELL}},\".\",\"\"))=3,ISNUMBER(VALUE(LEFT({{CELL}},FIND(\".\",{{CELL}})-1))))"`
  
- **端口号验证**：
  - `"pattern": "^([1-9]|[1-9]\\d{1,3}|[1-5]\\d{4}|6[0-4]\\d{3}|65[0-4]\\d{2}|655[0-2]\\d|6553[0-5])$"`
  - `"excel_formula": "AND(ISNUMBER({{CELL}}),{{CELL}}>=1,{{CELL}}<=65535)"`

**完整示例：**
```json
{
  "name": "url",
  "label": "URL地址",
  "type": "input",
  "required": true,
  "rules": [
    {
      "type": "pattern",
      "pattern": "^https://.*",
      "message": "URL必须以https://开头"
    }
  ]
}
```

**注意事项：**
- 必填验证通过字段的 `required` 属性控制，不需要在 `rules` 中配置
- 验证在字段onChange时实时触发
- 多个规则按顺序执行，遇到第一个错误就停止
- message 支持 i18n 翻译
- pattern类型用于正则表达式验证，支持各种复杂格式校验

#### 表格字段加密示例

当表格列包含敏感信息（如密码、密钥）时，可以使用 `encrypted` 属性：

```json
{
  "name": "password",
  "label": "密码",
  "type": "password",
  "required": true,
  "encrypted": true,
  "widget_props": {
    "placeholder": "请输入密码"
  }
}
```

**更多加密字段示例：**
```json
{
  "table_columns": [
    {
      "name": "node_ids",
      "label": "节点",
      "type": "select",
      "required": true,
      "enable_row_filter": true
    },
    {
      "name": "username",
      "label": "用户名",
      "type": "input",
      "required": true
    },
    {
      "name": "password",
      "label": "密码",
      "type": "password",
      "required": true,
      "encrypted": true,
      "widget_props": {
        "placeholder": "请输入密码"
      }
    },
    {
      "name": "api_key",
      "label": "API密钥",
      "type": "input",
      "required": false,
      "encrypted": true,
      "widget_props": {
        "placeholder": "可选的API密钥"
      }
    }
  ]
}
```

**加密字段说明：**
- `encrypted: true` 时，字段值在提交前会自动使用 hash 算法加密
- 加密后生成固定长度（10位）的字符串
- 相同输入总是生成相同的加密输出
- 空字符串会生成固定值：`"MDAwMDAwMDA"`
- 通常与 `type: "password"` 配合使用，但也支持 `input` 类型
- 加密在数据提交时自动进行，无需前端额外处理

#### enable_row_filter（行过滤）

当设置为 `true` 时，表格每行的下拉选项会自动过滤掉其他行已选的值：

```json
{
  "name": "node_ids",
  "label": "节点",
  "type": "select",
  "enable_row_filter": true  // 第一行选了节点A，第二行不会再显示节点A
}
```

**工作原理：**
- **单选模式**：过滤掉其他行选中的单个值
- **多选模式**：过滤掉其他行选中的所有值

#### 特殊列类型

**group_select（组选择器）：**
```json
{
  "name": "group_ids",
  "label": "组",
  "type": "group_select",
  "required": false,
  "default_value": [], // (默认值是当前组织)
  "widget_props": {
    "placeholder": "请选择组" //（后端要支持 i18n，前端有默认值）
  }
}
```

### 2.3 config_type_field（配置类型字段）

**可选配置**，位于顶层，用于指定从哪个表单字段获取 `config_type`，常用于需要根据用户选择动态生成多个配置的场景（如 Host 监控）。

#### 使用场景

当一个监控对象需要支持多种配置类型，且由用户选择时使用。例如：
- Host 监控：用户可以选择监控 CPU、内存、磁盘等多个指标
- 每个选中的指标需要生成一个独立的 config

#### 配置示例

```json
{
  "config_type_field": "metric_type",  // 顶层配置
  "form_fields": [
    {
      "name": "metric_type",
      "label": "指标类型",
      "type": "checkbox_group",
      "default_value": ["cpu", "disk", "mem"],
      "options": [
        { "label": "CPU", "value": "cpu" },
        { "label": "Disk", "value": "disk" },
        { "label": "Memory", "value": "mem" }
      ]
    },
    {
      "name": "interval",
      "label": "采集间隔",
      "type": "inputNumber",
      "default_value": 10
    }
  ]
}
```

#### 工作原理

1. 用户选择指标类型：`["cpu", "disk", "mem"]`
2. 填写采集间隔：`10`
3. 生成请求时：
   - 从 `formData.metric_type` 获取选中的类型
   - 为每个类型生成一个 config
   - `metric_type` 字段不会包含在最终请求中

#### 生成的请求格式

```json
{
  "collect_type": "host",
  "collector": "telegraf",
  "configs": [
    { "type": "cpu", "interval": 10 },
    { "type": "disk", "interval": 10 },
    { "type": "mem", "interval": 10 }
  ],
  "instances": [...]
}
```

**注意：**
- 如果不配置 `config_type_field`，则使用顶层的 `config_type` 数组
- `config_type_field` 指定的字段会从最终请求中移除
- 通常与 `checkbox_group` 类型配合使用

### 2.4 instance_id（实例ID模板）

**位于顶层**，仅 auto 模式使用，用于自动生成实例的唯一标识符。

#### 模板语法

使用 `{{变量名}}` 格式引用变量：

```json
"instance_id": "{{cloud_region}}_{{instance_type}}_snmp_{{ip}}"
```

#### 变量来源（按优先级）

1. **当前行字段**（来自 table_columns）
   ```json
   "instance_id": "{{ip}}_{{instance_name}}"
   ```
   
2. **上下文字段**（来自顶层配置）
   ```json
   "instance_id": "{{objectId}}_{{instance_type}}_{{ip}}"
   ```
   
3. **节点字段**（来自选中的节点对象）
   ```json
   "instance_id": "{{cloud_region}}_{{instance_type}}_snmp_{{ip}}"
   ```

#### 示例

```json
{
  "instance_id": "{{cloud_region}}_{{instance_type}}_snmp_{{ip}}",
  "table_columns": [ ... ]
}

// 生成结果示例：
// "region1_switch_snmp_192.168.1.101"
// "region2_switch_snmp_192.168.1.102"
```

### 2.5 extra_edit_fields（额外字段）

**位于顶层**，仅 edit 模式使用，用于生成不在表单中显示，但需要提交到 API 的字段。

#### 使用场景

- 从多个表单字段组合生成一个 API 字段
- 自动计算的字段

#### 示例

```json
{
  "extra_edit_fields": {
    "agents": {
      "origin_path": "child.content.config.agents",
      "to_api": {
        "template": "udp://{{ip}}:{{port}}",
        "array": true
      }
    }
  }
}
```

**工作流程：**
1. 从表单中获取 `ip` 和 `port` 字段的值
2. 使用模板 `udp://{{ip}}:{{port}}` 拼接
3. 转为数组格式 `["udp://192.168.1.1:161"]`
4. 以 `agents` 字段名提交到 API

---

## 三、data_transform（数据转换）

**仅在 edit 模式有效**，用于定义字段在 **API 数据** 和 **表单数据** 之间的转换规则。

可以在以下两个地方配置：
1. `form_fields[].transform_on_edit` - 表单字段的数据转换
2. `extra_edit_fields.{field_name}` - 额外字段的数据转换（直接配置转换规则，无需嵌套）

### 3.1 完整结构

```json
"data_transform": {
  "origin_path": "child.content.config.agents[0]",  // 数据源路径
  "to_form": {                                       // API → 表单（回显）
    "regex": "://([^:]+):",
    "type": "number"
  },
  "to_api": {                                        // 表单 → API（提交）
    "suffix": "s",
    "prefix": "udp://",
    "template": "udp://{{ip}}:{{port}}",
    "array": true,
    "type": "string"
  }
}
```

#### origin_path（数据源路径）

指定从 API 返回数据中提取值的路径：

```json
"origin_path": "child.content.config.agents[0]"
```

**支持的路径语法：**
- 点号分隔：`child.content.config.port`
- 数组索引：`child.content.config.agents[0]`
- 嵌套组合：`child.content.config.servers[0].host`

#### to_form（回显转换）

从 API 数据提取并转换为表单可用的格式。

**regex（正则提取）：**
```json
"to_form": {
  "regex": "://([^:]+):"  // 从 "udp://192.168.1.1:161" 提取 "192.168.1.1"
}
```

**type（类型转换）：**
```json
"to_form": {
  "type": "number"        // 将字符串 "161" 转为数字 161
}
```
支持的类型：`string`, `number`, `parseInt`, `parseFloat`

**array（转为数组）：**
```json
"to_form": {
  "array": true  // "cpu" → ["cpu"]
}
```

**组合使用：**
```json
"to_form": {
  "regex": "^(\\d+)s$",   // 从 "10s" 提取 "10"
  "type": "number"        // 转为数字 10
}
```

### 3.3 to_api（提交转换）

将表单数据转换为 API 所需的格式。

**suffix（添加后缀）：**
```json
"to_api": {
  "suffix": "s"           // 10 → "10s"
}
```

**prefix（添加前缀）：**
```json
"to_api": {
  "prefix": "udp://"      // "192.168.1.1" → "udp://192.168.1.1"
}
```

**template（模板拼接）：**
```json
"to_api": {
  "template": "udp://{{ip}}:{{port}}"  // 从其他字段组合
}
```

**array（转为数组）：**
```json
"to_api": {
  "template": "udp://{{ip}}:{{port}}",
  "array": true           // "udp://192.168.1.1:161" → ["udp://192.168.1.1:161"]
}
```

**type（类型转换）：**
```json
"to_api": {
  "type": "number"        // "161" → 161
}
```

**空对象（原值提交）：**
```json
"to_api": {}  // 表示该字段需要提交，但不做任何转换
```

### 3.4 完整示例

**示例1：提取 IP（只读字段）**
```json
{
  "name": "ip",
  "label": "IP",
  "type": "input",
  "mode_config": {
    "auto": {
      "visible": false
    },
    "edit": {
      "visible": true,
      "widget_props": {
        "disabled": true
      },
      "data_transform": {
        "origin_path": "child.content.config.agents[0]",
        "to_form": {
          "regex": "://([^:]+):"  // "udp://192.168.1.1:161" → "192.168.1.1"
        }
        // 没有 to_api，因为是只读字段
      }
    }
  }
}
```

**示例2：带单位的数字字段**
```json
{
  "name": "timeout",
  "label": "超时时间",
  "type": "inputNumber",
  "widget_props": {
    "addonAfter": "s"
  },
  "mode_config": {
    "edit": {
      "data_transform": {
        "origin_path": "child.content.config.timeout",
        "to_form": {
          "regex": "^(\\d+)s$"    // "10s" → "10"
        },
        "to_api": {
          "suffix": "s"           // 10 → "10s"
        }
      }
    }
  }
}
```

**示例3：可编辑字段（简单映射）**
```json
{
  "name": "community",
  "label": "Community",
  "type": "input",
  "mode_config": {
    "edit": {
      "data_transform": {
        "origin_path": "child.content.config.community",
        "to_api": {}  // 空对象表示表单原值提交
      }
    }
  }
}
```

**示例4：extra_edit_fields（额外字段）**
```json
{
  "extra_edit_fields": {
    "agents": {
      "origin_path": "child.content.config.agents",
      "to_api": {
        "template": "udp://{{ip}}:{{port}}",
        "array": true
      }
    }
  }
}
```

---

## 四、高级特性

### 4.1 模式控制属性使用场景

使用 `editable` 和 `visible_in` 属性控制字段在 auto 和 edit 模式下的不同行为。

**最佳实践：**

1. **字段可见性控制**
   - 使用 `visible_in: "edit"` 让字段仅在编辑模式显示
   - 使用 `visible_in: "auto"` 让字段仅在批量新增模式显示
   
2. **禁用字段编辑**
   - 使用 `editable: false` 让字段在 edit 模式下禁用（如版本、端口、IP等）
   
3. **数据转换**
   - edit 模式需要从 API 回显数据时，使用 `data_transform`

### 4.2 动态配置类型（config_type_field）

用于根据用户选择动态生成多个配置。详见 [2.3 config_type_field](#23-config_type_field配置类型字段)。

**典型应用场景：**
- Host 监控：用户选择需要监控的指标（CPU、内存、磁盘等）
- 每个选中的指标生成一个独立的 config

**优势：**
- 用户按需选择，避免生成不必要的配置
- 配置更灵活，易于扩展
- 请求结构清晰，后端易于处理

### 4.3 字段依赖（dependency）

实现动态显示/隐藏字段。

**单值依赖：**
```json
"dependency": {
  "field": "version",
  "value": 2
}
```

**多值依赖（OR 关系）：**
```json
"dependency": {
  "field": "sec_level",
  "value": ["authNoPriv", "authPriv"]
}
```

### 4.4 undefined 处理

如果表单字段的值为 `undefined`，该字段不会被提交到 API。

**示例：**
```javascript
// 表单值
{
  "version": 2,
  "community": "public",
  "sec_name": undefined      // v3 字段，因为选了 v2
}

// 提交到 API（sec_name 被过滤）
{
  "version": 2,
  "community": "public"
}
```

### 4.5 行过滤（enable_row_filter）

防止在批量添加时选择重复的节点。

```json
{
  "name": "node_ids",
  "label": "节点",
  "type": "select",
  "enable_row_filter": true
}
```

**单选模式：**
- 第一行选择：节点 A
- 第二行可选：节点 B, C, D（节点 A 被过滤）

**多选模式：**
- 第一行选择：节点 A, B
- 第二行可选：节点 C, D（节点 A, B 被过滤）

---

## 五、数据流说明
  "data_transform": {
    "origin_path": "child.content.config.timeout",
    "to_form": {
      "regex": "^(\\d+)s$"    // "10s" → "10"
    },
    "to_api": {
      "suffix": "s"           // 10 → "10s"
    }
  }
}
```

**示例3：可编辑字段（简单映射）**
```json
{
  "name": "community",
  "label": "Community",
  "type": "input",
  "data_transform": {
    "origin_path": "child.content.config.community",
    "to_api": {}  // 空对象表示表单原值提交，但需要有 to_api 才会提交，例如你改了用户名，提交时要有 to_api才生效
  }
}
```

### 3.4 extra_edit_fields（额外字段）

用于生成不在表单中显示，但需要提交到 API 的字段。

#### 使用场景

- 从多个表单字段组合生成一个 API 字段
- 自动计算的字段

#### 示例

```json
"extra_edit_fields": {
  "agents": {
    "origin_path": "child.content.config.agents",
    "to_api": {
      "template": "udp://{{ip}}:{{port}}",
      "array": true
    }
  }
}
```

**工作流程：**
1. 从表单中获取 `ip` 和 `port` 字段的值
2. 使用模板 `udp://{{ip}}:{{port}}` 拼接
3. 转为数组格式 `["udp://192.168.1.1:161"]`
4. 以 `agents` 字段名提交到 API

---

## 四、高级特性

### 4.1 动态配置类型（config_type_field）

用于根据用户选择动态生成多个配置。详见 [2.4 config_type_field](#24-config_type_field配置类型字段)。

**典型应用场景：**
- Host 监控：用户选择需要监控的指标（CPU、内存、磁盘等）
- 每个选中的指标生成一个独立的 config

**优势：**
- 用户按需选择，避免生成不必要的配置
- 配置更灵活，易于扩展
- 请求结构清晰，后端易于处理

### 4.2 字段依赖（dependency）

实现动态显示/隐藏字段。

**单值依赖：**
```json
"dependency": {
  "field": "version",
  "value": 2
}
```

**多值依赖（OR 关系）：**
```json
"dependency": {
  "field": "sec_level",
  "value": ["authNoPriv", "authPriv"]
}
```

### 4.3 undefined 处理

如果表单字段的值为 `undefined`，该字段不会被提交到 API。

**示例：**
```javascript
// 表单值
{
  "version": 2,
  "community": "public",
  "sec_name": undefined      // v3 字段，因为选了 v2
}

// 提交到 API（sec_name 被过滤）
{
  "version": 2,
  "community": "public"
}
```

### 4.3 行过滤（enable_row_filter）

防止在批量添加时选择重复的节点。

```json
{
  "name": "node_ids",
  "label": "节点",
  "type": "select",
  "enable_row_filter": true
}
```

**单选模式：**
- 第一行选择：节点 A
- 第二行可选：节点 B, C, D（节点 A 被过滤）

**多选模式：**
- 第一行选择：节点 A, B
- 第二行可选：节点 C, D（节点 A, B 被过滤）

---

## 五、数据流说明

### 5.1 Auto 模式数据流

#### 5.1.1 标准流程（Switch SNMP）

```
表单数据 + 表格数据
    ↓
transformAutoRequest()
    ↓
{
  collect_type: "snmp",
  collector: "telegraf",
  configs: [
    { type: "switch", port: 161, version: 2, community: "public", ... }
  ],
  instances: [
    {
      ip: "192.168.1.101",
      instance_name: "192.168.1.101",
      node_ids: ["node-001"],
      instance_id: "region1_switch_snmp_192.168.1.101",
      instance_type: "switch",
      group_ids: []
    }
  ],
  monitor_object_id: 80
}
```

#### 5.1.2 动态配置类型流程（Host）

```
表单数据（包含 metric_type: ["cpu", "mem", "disk"]）+ 表格数据
    ↓
transformAutoRequest() 识别 config_type_field
    ↓
1. 提取 metric_type 值：["cpu", "mem", "disk"]
2. 删除 formData.metric_type
3. 为每个类型生成独立 config
    ↓
{
  collect_type: "host",
  collector: "telegraf",
  configs: [
    { type: "cpu", interval: 10, ... },
    { type: "mem", interval: 10, ... },
    { type: "disk", interval: 10, ... }
  ],
  instances: [
    {
      instance_name: "web-server-01",
      node_ids: ["node-001"],
      group_ids: ["group-web"]
    }
  ],
  monitor_object_id: 90
}
```

**关键差异：**
- 标准流程：单个 config，type 固定
- 动态流程：多个 configs，type 由用户选择决定
- 共同点：instances 结构相同，表格数据转换逻辑一致

### 5.2 Edit 模式数据流

**回显（API → 表单）：**
```
API 返回数据
    ↓
根据 mode_config.edit.visible 过滤字段
    ↓
origin_path 提取
    ↓
to_form 转换（regex, type, array）
    ↓
表单显示
```

**提交（表单 → API）：**
```
表单数据
    ↓
根据 mode_config.edit 获取有效字段
    ↓
过滤 undefined
    ↓
to_api 转换（suffix, prefix, template, type, array）
    ↓
extra_fields 生成
    ↓
提交到 API
```

---

## 六、完整示例

### 6.1 Host 监控配置（使用 config_type_field 和模式控制）

```json
{
  "object_name": "Host",
  "instance_type": "os",
  "collect_type": "host",
  "config_type": ["cpu", "disk", "diskio", "mem", "net", "processes", "system", "gpu"],
  "collector": "telegraf",
  "config_type_field": "metric_type",
  "instance_id": "{{cloud_region}}_{{instance_type}}_{{ip}}",
  "form_fields": [
    {
      "name": "metric_type",
      "label": "指标类型",
      "type": "checkbox_group",
      "required": true,
      "editable": false,
      "default_value": ["cpu", "disk", "diskio", "mem", "net", "processes", "system"],
      "tooltip": "CPU: 监控CPU使用情况\nDisk: 监控磁盘使用情况\n...",
      "options": [
        { "label": "CPU", "value": "cpu" },
        { "label": "Disk", "value": "disk" },
        { "label": "Disk IO", "value": "diskio" },
        { "label": "Memory", "value": "mem" },
        { "label": "Net", "value": "net" },
        { "label": "Processes", "value": "processes" },
        { "label": "System", "value": "system" },
        { "label": "Nvidia-GPU", "value": "gpu" }
      ],
      "widget_props": {},
      "data_transform": {
        "origin_path": "child.content.config.tags.config_type",
        "to_form": {
          "array": true
        }
      }
    },
    {
      "name": "ip",
      "label": "IP",
      "type": "input",
      "required": true,
      "visible_in": "edit",
      "editable": false,
      "tooltip": "监控的目标主机的 IP 地址",
      "widget_props": {
        "placeholder": "1_os_172.18.0.17"
      },
      "data_transform": {
        "origin_path": "child.content.instance.instance_id"
      }
    },
    {
      "name": "interval",
      "label": "采集间隔",
      "type": "inputNumber",
      "required": true,
      "default_value": 10,
      "tooltip": "数据采集间隔时间(单位:秒)",
      "widget_props": {
        "min": 1,
        "precision": 0,
        "placeholder": "采集间隔",
        "addonAfter": "s"
      },
      "data_transform": {
        "origin_path": "child.content.config.interval",
        "to_form": {
          "regex": "^(\\d+)s$"
        },
        "to_api": {
          "suffix": "s"
        }
      }
    }
  ],
  "table_columns": [
    {
      "name": "node_ids",
      "label": "节点",
      "type": "select",
      "required": true,
      "default_value": "",
      "widget_props": {
        "placeholder": "请选择节点"
      },
      "enable_row_filter": true
    },
    {
      "name": "instance_name",
      "label": "实例名称",
      "type": "input",
      "required": true,
      "default_value": "",
      "widget_props": {
        "placeholder": "实例名称"
      }
    },
    {
      "name": "group_ids",
      "label": "组",
      "type": "group_select",
      "required": false,
      "default_value": [],
      "widget_props": {
        "placeholder": "请选择组"
      }
    }
  ]
}
```

### 6.2 Switch SNMP 监控配置（完整示例）

参考 `d:\react\bk-lite\web\public\monitor\configs\switch-snmp.json` 文件，包含：
- v2c 和 v3 两种 SNMP 版本的支持
- 字段依赖关系（dependency）
- 模式控制属性（editable, visible_in）
- 数据转换（正则、后缀、模板）
- 行过滤（enable_row_filter）
- 实例 ID 自动生成（instance_id）
- 额外字段（extra_fields）

**关键特性：**
```json
{
  "form_fields": [
    {
      "name": "ip",
      "visible_in": "edit",
      "editable": false,
      "transform_on_edit": {
        "origin_path": "child.content.config.agents[0]",
        "to_form": { "regex": "://([^:]+):" }
      }
    },
    {
      "name": "version",
      "editable": false,
      "transform_on_edit": {
        "origin_path": "child.content.config.version"
      }
    },
    {
      "name": "community",
      "dependency": { "field": "version", "value": 2 },
      "transform_on_edit": {
        "origin_path": "child.content.config.community",
        "to_api": {}
      }
    }
  ],
  "extra_edit_fields": {
    "agents": {
      "origin_path": "child.content.config.agents",
      "to_api": {
        "template": "udp://{{ip}}:{{port}}",
        "array": true
      }
    }
  }
}
```

---

## 七、常见问题

### Q1: 如何添加新字段？

在 `form_fields` 或 `table_columns` 中添加字段配置即可。如果字段在 auto 和 edit 模式下有不同行为，使用 `mode_config` 配置。

### Q2: 如何实现字段联动？

使用 `dependency` 实现显示/隐藏，使用 `change_handler` 实现值联动。

### Q3: 模式控制属性什么时候使用？

当字段在 auto 和 edit 模式下有不同行为时使用：
- 仅在某个模式显示：使用 `visible_in`
- edit 模式禁用字段：使用 `editable: false`
- 需要数据转换：使用 `data_transform`（主要用于 edit 模式）

### Q4: to_api 为空对象 `{}` 是什么意思？

表示该字段需要提交到 API，但不做任何转换，原值提交。如果不写 `to_api`，该字段不会被提交。

### Q5: 正则表达式怎么写？

使用 JavaScript 正则语法，捕获组 `()` 中的内容会被提取。

```json
"regex": "://([^:]+):"  // 提取 :// 和 : 之间的内容
"regex": "^(\\d+)s$"    // 提取以 s 结尾的数字
```

### Q6: instance_id 可以使用哪些变量？

- 当前行字段：`{{ip}}`, `{{instance_name}}`
- 上下文字段：`{{objectId}}`, `{{instance_type}}`
- 节点字段：`{{cloud_region}}`, `{{name}}`, `{{id}}`

### Q7: encrypted 加密功能如何使用？

**基本用法：**
在任何 `form_fields` 或 `table_columns` 字段中添加 `"encrypted": true`，该字段值在提交前会自动加密。

```json
{
  "name": "password",
  "label": "密码",
  "type": "password",
  "required": true,
  "encrypted": true
}
```

**加密特性：**
- 使用 hash 算法（简化的 SHA256 实现）
- 生成固定长度（10位）的加密字符串
- 相同输入总是生成相同输出（可用于验证）
- 空字符串不会报错，生成固定值 `"MDAwMDAwMDA"`

**适用场景：**
- 密码字段：数据库密码、服务密码
- API密钥：第三方服务的 API Key
- Token：认证令牌、访问令牌
- 证书密码：SSL 证书密码、私钥密码

**完整示例：**
```json
{
  "form_fields": [
    {
      "name": "username",
      "label": "用户名",
      "type": "input",
      "required": true
    },
    {
      "name": "ENV_PASSWORD",
      "label": "密码",
      "type": "password",
      "required": true,
      "encrypted": true,
      "description": "登录密码，提交时自动加密",
      "transform_on_edit": {
        "origin_path": "child.env_config.PASSWORD__{{config_id}}"
      }
    }
  ],
  "table_columns": [
    {
      "name": "api_key",
      "label": "API密钥",
      "type": "password",
      "required": false,
      "encrypted": true,
      "widget_props": {
        "placeholder": "请输入API密钥"
      }
    }
  ]
}
```

**注意事项：**
- 加密在提交前自动进行，无需前端额外处理
- 建议配合 `required: true` 使用，避免提交空值
- 加密是单向的，无法从加密值还原原始值
- Auto 模式和 Edit 模式都支持字段加密

### Q8: 如何从旧配置迁移到新结构？

**迁移步骤：**

1. **移除 auto 和 edit 层级**
   ```json
   // 旧结构
   {
     "auto": {
       "form_fields": [...],
       "table_columns": [...],
       "instance_id": "..."
     },
     "edit": {
       "form_fields": [...],
       "extra_fields": {...}
     }
   }
   
   // 新结构
   {
     "form_fields": [...],
     "table_columns": [...],
     "instance_id": "...",
     "extra_fields": {...}
   }
   ```

2. **合并 form_fields**
   - 将 auto.form_fields 和 edit.form_fields 合并
   - 相同字段使用模式控制属性区分差异
   
3. **添加模式控制属性**
   - edit 特有字段：添加 `"visible_in": "edit"`
   - auto 特有字段：添加 `"visible_in": "auto"`
   - edit 模式禁用字段：添加 `"editable": false`
   - edit 模式数据转换：添加 `data_transform` 到字段根级别
   
4. **移动顶层配置**
   - `config_type_field`: 从 auto 移到顶层
   - `instance_id`: 从 auto 移到顶层
   - `table_columns`: 从 auto 移到顶层
   - `extra_fields`: 从 edit 移到顶层

---

## 八、最佳实践

1. **合理使用 mode_config**
   - 仅在字段行为确实不同时使用
   - 简单字段可以不配置 mode_config
   
2. **明确数据转换**
   - edit 模式中，明确哪些字段需要 `to_api`
   - 只读字段不需要 `to_api`
   
3. **测试正则表达式**
   - 确保正则能正确提取所需内容
   - 使用在线工具测试正则表达式
   
4. **使用 tooltip**
   - 为复杂字段添加说明
   - tooltip 支持 `\n` 换行
   
5. **统一命名规范**
   - 字段名使用下划线命名法（snake_case）
   - label 使用人类可读的文本
   
6. **验证 JSON 格式**
   - 使用 JSON 验证工具检查语法错误
   - 确保所有必填字段都已配置
   
7. **依赖关系**
   - 避免过于复杂的依赖链
   - 测试依赖字段的显示/隐藏逻辑

---

## 九、相关文件

- **配置文件示例**：
  - `web/public/monitor/configs/host.json` - Host 监控配置
  - `web/public/monitor/configs/switch-snmp.json` - Switch SNMP 监控配置
  
- **核心代码**：
  - `web/src/app/monitor/hooks/integration/useDataMapper.ts` - 数据映射逻辑
  - `web/src/app/monitor/hooks/integration/useConfigRenderer.tsx` - 配置渲染组件
  - `web/src/app/monitor/hooks/integration/usePluginFromJson.tsx` - 插件加载器
  
- **页面组件**：
  - `web/src/app/monitor/(pages)/integration/list/detail/configure/automatic.tsx` - 批量新增页面
  - `web/src/app/monitor/(pages)/integration/list/detail/configure/updateConfig.tsx` - 编辑弹窗

---

## 附录 B：字段加密快速参考

### 加密功能概览

| 项目 | 说明 |
|------|------|
| **配置属性** | `"encrypted": true` |
| **适用范围** | `form_fields` 和 `table_columns` |
| **加密算法** | 简化的 hash 算法（基于字符串哈希） |
| **输出长度** | 固定 10 位字符串 |
| **空值处理** | 返回固定值 `"MDAwMDAwMDA"` |
| **可逆性** | 单向加密，不可还原 |

### 推荐字段类型

| 字段类型 | 推荐度 | 使用场景 |
|----------|--------|----------|
| `password` | ⭐⭐⭐ | 密码、私钥密码 |
| `input` | ⭐⭐ | API密钥、Token |
| `textarea` | ⭐ | 长文本密钥、证书 |
| `select` | ❌ | 不推荐 |
| `checkbox` | ❌ | 不推荐 |

### 常见使用模式

**模式1：表单密码字段**
```json
{
  "name": "password",
  "label": "密码",
  "type": "password",
  "required": true,
  "encrypted": true,
  "description": "登录密码",
  "transform_on_edit": {
    "origin_path": "child.env_config.PASSWORD__{{config_id}}"
  }
}
```

**模式2：表格密码字段**
```json
{
  "name": "password",
  "label": "密码",
  "type": "password",
  "required": true,
  "encrypted": true,
  "widget_props": {
    "placeholder": "请输入密码"
  }
}
```

**模式3：API密钥字段**
```json
{
  "name": "api_key",
  "label": "API密钥",
  "type": "input",
  "required": false,
  "encrypted": true,
  "description": "第三方服务的API密钥"
}
```

### 注意事项

✅ **建议做的：**
- 配合 `required: true` 使用，避免空值
- 用于 `password` 类型的密码字段
- 用于敏感的 `input` 字段（API密钥、Token）
- 在表单和表格中都可以使用

❌ **不建议做的：**
- 对非敏感字段使用加密
- 对 `select`、`checkbox` 类型使用加密
- 期望从加密值还原原始值
- 在前端代码中手动调用加密函数

---

**版本：** v2.1  
**更新日期：** 2025-12-08  
**维护者：** 开发团队  
**主要变化：** 
- v2.1: 新增字段加密功能（encrypted 属性）
- v2.0: 移除 auto 和 edit 层级，配置扁平化
- v2.0: 新增 mode_config 机制统一管理模式差异
