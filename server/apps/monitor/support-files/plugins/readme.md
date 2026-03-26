# 监控采集插件接入手册（生产可落地）

适用场景：在当前仓库中新增一个“内置监控采集插件”，让系统能够正确导入采集器、监控对象、指标、UI 模板和可选告警策略。

## 1. 先理解两类目录

新增一个监控采集插件，实际涉及两个模块：

- **节点采集器定义**：`apps/node_mgmt/support-files/collectors`
- **监控插件模板**：`apps/monitor/support-files/plugins`

两者职责不同：

### 1.1 节点采集器定义（node 模块）

目录：`apps/node_mgmt/support-files/collectors`

作用：定义 Sidecar/节点管理可识别的采集器基础信息。系统会在初始化时扫描该目录下的 `*.json` 文件导入采集器。

代码依据：

- `apps/node_mgmt/management/services/node_init/collector_init.py`
- `apps/node_mgmt/management/commands/node_init.py`

### 1.2 监控插件模板（monitor 模块）

目录：`apps/monitor/support-files/plugins`

作用：定义监控对象、指标、配置模板、UI 模板、告警策略。系统会在初始化时扫描该目录下的插件文件并导入数据库。

代码依据：

- `apps/monitor/constants/plugin.py`
- `apps/monitor/management/services/plugin_migrate.py`
- `apps/monitor/management/services/policy_migrate.py`
- `apps/monitor/management/commands/plugin_init.py`

---

## 2. 接入总流程

生产上新增一个插件，建议按下面顺序执行：

1. 在 `apps/node_mgmt/support-files/collectors` 新增采集器定义 JSON 文件。
2. 在 `apps/monitor/support-files/plugins/<collector>/<collect_type>/<instance_type>/` 新增插件目录及文件。
3. 在 `server/` 目录执行初始化命令：
   - `python manage.py node_init`
   - `python manage.py plugin_init`
4. 在页面验证采集器和监控对象是否可见。
5. 如需批量初始化整套内置数据，也可执行 `batch_init`，其中会调用：
   - `plugin_init`
   - `node_init`

代码依据：

- `server/manage.py`
- `apps/node_mgmt/management/commands/node_init.py`
- `apps/monitor/management/commands/plugin_init.py`
- `apps/core/management/commands/batch_init.py`

> 注意：`node_init` 与 `plugin_init` 都会同步“内置定义”到数据库；如果你删除了目录中的内置文件，再执行初始化，系统会清理对应的内置数据。

---

## 3. 目录结构约束（非常重要）

### 3.1 标准目录结构

```text
apps/
├── node_mgmt/
│   └── support-files/
│       └── collectors/
│           └── Telegraf.json
└── monitor/
    └── support-files/
        └── plugins/
            └── Telegraf/
                └── ping/
                    └── ping/
                        ├── metrics.json
                        ├── UI.json
                        ├── policy.json            # 可选
                        ├── ping.child.toml.j2
                        └── ping.base.yaml.j2      # 可选
```

### 3.2 路径层级是导入逻辑的一部分

插件目录必须满足下面的层级：

```text
apps/monitor/support-files/plugins/<collector>/<collect_type>/<instance_type>/
```

例如：

```text
apps/monitor/support-files/plugins/Telegraf/ping/ping/
apps/monitor/support-files/plugins/Oracle-Exporter/exporter/oracle/
```

原因：

- 系统只按固定层级扫描目录（采集器 / 采集方式 / 具体插件目录 / 文件）。
- `collector` 和 `collect_type` 是从路径中提取的，不是只靠 `metrics.json` 内部字段决定。

代码依据：

- `apps/monitor/management/utils.py`
  - `find_files_by_pattern`
  - `extract_plugin_path_info`

> 如果目录多一层、少一层，或者放错位置，文件可能不会被扫描到。

---

## 4. 第一步：新增采集器定义（node 模块）

### 4.1 文件位置

在 `apps/node_mgmt/support-files/collectors` 下新增一个以采集器名称命名的 JSON 文件，例如：

```text
apps/node_mgmt/support-files/collectors/Telegraf.json
```

### 4.2 文件格式

该文件内容是 **JSON 数组**，数组中的每个元素对应一个采集器定义。通常同一个采集器会按操作系统拆成多条记录，例如 Linux / Windows。

示例可参考：

- `apps/node_mgmt/support-files/collectors/Telegraf.json`

### 4.3 采集器字段说明

以下字段来自 `apps/node_mgmt/models/sidecar.py` 与现有 JSON：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 采集器唯一标识，全局唯一 |
| name | string | 采集器名称；同一名称可按不同 OS 定义多条 |
| service_type | string | 服务类型，当前模型支持 `exec` / `svc` |
| node_operating_system | string | 节点操作系统，当前模型支持 `linux` / `windows` |
| executable_path | string | 采集器可执行文件路径 |
| execute_parameters | string | 执行参数，可包含 `%s` 占位符 |
| validation_parameters | string | 校验参数，可为空 |
| default_template | string | 默认模板内容，可为空 |
| introduction | string | 采集器简介 |
| icon | string | 图标 key |
| controller_default_run | bool | 是否由控制器默认运行 |
| default_config | object | 默认初始化配置 |
| tags | array | 标签 |
| package_name | string | 包名称 |

### 4.4 生产注意事项

- `id` 必须稳定，后续更新会按 `id` 做更新。
- 同一采集器如需支持 Linux/Windows，建议放在同一个 JSON 文件内，用多条记录区分。
- 删除该目录中的内置采集器定义后再次执行 `node_init`，系统会删除数据库中对应的内置采集器。

代码依据：

- `apps/node_mgmt/management/services/node_init/collector_init.py`
- `apps/node_mgmt/models/sidecar.py`

---

## 5. 第二步：新增监控插件目录（monitor 模块）

### 5.1 目录命名规则

目录结构：

```text
apps/monitor/support-files/plugins/<collector>/<collect_type>/<instance_type>/
```

各层含义：

- `collector`：采集器名称，如 `Telegraf`、`Oracle-Exporter`
- `collect_type`：采集方式，如 `ping`、`host`、`exporter`
- `instance_type`：监控对象实例类型，如 `ping`、`os`、`oracle`

### 5.2 该目录下可包含的文件

| 文件名 | 是否必需 | 作用 |
|---|---|---|
| `metrics.json` | 必需 | 定义监控对象与指标 |
| `UI.json` | 建议提供 | 定义页面表单与实例编辑 UI |
| `policy.json` | 可选 | 定义默认告警策略模板 |
| `*.j2` | 按需提供 | 定义采集配置模板 |

---

## 6. metrics.json（必需）

### 6.1 文件作用

`metrics.json` 是插件接入的核心文件。系统会先导入它，再根据同目录下的模板和 UI 文件补充配置。

代码依据：

- `apps/monitor/management/services/plugin_migrate.py`
- `apps/monitor/services/plugin.py`

### 6.2 基础对象模式

适用于一个插件只对应一个监控对象的场景。

最小结构可参考：

```json
{
  "plugin": "Ping",
  "plugin_desc": "...",
  "status_query": "any({instance_type='ping', collect_type='ping'}) by (instance_id)",
  "name": "Ping",
  "icon": "wangzhan1",
  "type": "Web",
  "description": "",
  "default_metric": "any({instance_type='ping'}) by (instance_id)",
  "instance_id_keys": ["instance_id"],
  "supplementary_indicators": ["ping_average_response_ms"],
  "metrics": []
}
```

参考示例：

- `apps/monitor/support-files/plugins/Telegraf/ping/ping/metrics.json`

### 6.3 复合对象模式

适用于一个插件下包含多个监控对象的场景，例如一个 base 对象 + 多个 derivative 对象。

关键字段：

- `is_compound_object: true`
- `objects: []`
- 每个对象需要 `level`，值为 `base` 或 `derivative`

参考示例：

- `apps/monitor/support-files/plugins/unknown/k8s/k8s/metrics.json`
- `apps/monitor/support-files/plugins/Telegraf/docker/docker/metrics.json`

### 6.4 字段说明

#### 顶层字段（基础对象模式）

| 字段 | 类型 | 说明 |
|---|---|---|
| plugin | string | 插件名称，全局唯一；数据库按该字段更新/删除内置插件 |
| plugin_desc | string | 插件描述 |
| status_query | string | 状态查询语句 |
| name | string | 监控对象名称；数据库中唯一 |
| icon | string | 监控对象图标 |
| type | string | 监控对象分类 ID；不存在时会自动创建分类 |
| description | string | 监控对象描述 |
| default_metric | string | 默认指标查询语句 |
| instance_id_keys | array | 实例唯一键列表 |
| supplementary_indicators | array | 实例列表补充指标 |
| metrics | array | 指标列表 |

#### 顶层字段（复合对象模式）

| 字段 | 类型 | 说明 |
|---|---|---|
| plugin | string | 插件名称，全局唯一 |
| plugin_desc | string | 插件描述 |
| status_query | string | 状态查询语句 |
| is_compound_object | bool | 固定为 `true` |
| objects | array | 监控对象列表 |

#### `metrics[*]` 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| metric_group | string | 指标分组名称 |
| name | string | 指标名称；同一监控对象下唯一 |
| display_name | string | 指标展示名称 |
| query | string | 查询语句 |
| data_type | string | 数据类型 |
| unit | string | 单位 |
| dimensions | array | 维度列表 |
| instance_id_keys | array | 指标实例键 |
| description | string | 指标描述 |

### 6.5 隐式规则

- `collector` 与 `collect_type` 不是在 `metrics.json` 内手工维护，而是由文件路径自动提取后写入数据库。
- `plugin` 用于更新同名内置插件；不要随意改名。
- `name` 对应监控对象名，在数据库中是唯一字段；与已有对象重名会被更新而不是新增。
- 同一监控对象下，指标 `name` 需要唯一。

代码依据：

- `apps/monitor/management/services/plugin_migrate.py`
- `apps/monitor/services/plugin.py`
- `apps/monitor/models/plugin.py`
- `apps/monitor/models/monitor_object.py`
- `apps/monitor/models/monitor_metrics.py`

---

## 7. 配置模板文件（*.j2，按需提供）

### 7.1 命名规则

模板文件名格式：

```text
{type}.{config_type}.{file_type}.j2
```

例如：

- `ping.child.toml.j2`
- `oracle.base.yaml.j2`

代码依据：

- `apps/monitor/management/utils.py#parse_template_filename`

### 7.2 字段含义

| 片段 | 说明 |
|---|---|
| `type` | 模板类型 |
| `config_type` | 配置类型，如 `base` / `child` |
| `file_type` | 文件类型，如 `yaml` / `toml` |

### 7.3 生产注意事项

- 系统会扫描插件目录下所有 `.j2` 文件。
- 文件名不符合规则时，模板不会被正确解析。
- 如果某模板此前已导入数据库，后续从目录中删掉并执行 `plugin_init`，数据库中的对应模板也会被删除。

代码依据：

- `apps/monitor/management/services/plugin_migrate.py`
- `apps/monitor/management/utils.py`

---

## 8. UI.json（强烈建议提供）

### 8.1 文件作用

用于定义监控实例创建/编辑时的 UI 表单内容。系统会在 `plugin_init` 时导入同目录下的 `UI.json`。

参考示例：

- `apps/monitor/support-files/plugins/Telegraf/ping/ping/UI.json`

### 8.2 生产注意事项

- `UI.json` 不是 `metrics.json` 的替代品，二者职责不同。
- 如果 `UI.json` 缺失，系统不会为该插件导入 UI 模板。
- 如果数据库中已有 UI 模板，而目录中的 `UI.json` 被删除，再执行 `plugin_init` 时系统会删除数据库中的对应 UI 模板。

代码依据：

- `apps/monitor/management/services/plugin_migrate.py`

---

## 9. policy.json（可选）

### 9.1 文件作用

用于导入默认告警策略模板。

参考示例：

- `apps/monitor/support-files/plugins/Telegraf/ping/ping/policy.json`

### 9.2 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| object | string | 监控对象名称，必须能在系统中找到对应 `MonitorObject.name` |
| plugin | string | 插件名称，必须能在系统中找到对应 `MonitorPlugin.name` |
| templates | array | 告警模板列表 |
| templates.name | string | 模板名称 |
| templates.alert_name | string | 告警名称 |
| templates.description | string | 告警描述 |
| templates.metric_name | string | 关联指标名 |
| templates.algorithm | string | 算法 |
| templates.threshold | array | 阈值列表 |
| templates.threshold.level | string | 阈值级别 |
| templates.threshold.value | number | 阈值值 |
| templates.threshold.method | string | 比较方式 |

### 9.3 约束

- `object` 必须与 `metrics.json` 中导入后的监控对象名称一致。
- `plugin` 必须与 `metrics.json` 中的 `plugin` 一致。
- `policy.json` 导入时会按 `plugin` 和 `object` 查库，不匹配会失败。

代码依据：

- `apps/monitor/management/services/policy_migrate.py`
- `apps/monitor/services/policy.py`

---

## 10. 初始化命令

以下命令在 `server/` 目录执行：

### 10.1 导入采集器

```bash
python manage.py node_init
```

作用：

- 初始化默认云区域
- 初始化控制器
- 初始化采集器

其中采集器导入来自：

- `apps/node_mgmt/support-files/collectors/*.json`

### 10.2 导入监控插件

```bash
python manage.py plugin_init
```

作用：

- 导入 `metrics.json`
- 同步 `.j2` 配置模板
- 同步 `UI.json`
- 导入 `policy.json`
- 更新默认排序

### 10.3 全量初始化

```bash
python manage.py batch_init
```

适用于整套内置数据初始化。该命令内部会调用 `plugin_init` 与 `node_init`。

---

## 11. 验证清单（接入后必须做）

### 11.1 采集器侧验证

执行 `python manage.py node_init` 后确认：

- 节点管理页面能看到新增采集器。
- 采集器的名称、OS、执行路径、默认配置是否正确。

### 11.2 监控插件侧验证

执行 `python manage.py plugin_init` 后确认：

- 监控管理 / 集成页面能看到新增监控对象。
- 新建实例时能读取到 `UI.json` 对应的表单。
- 插件关联的指标、指标分组已导入。
- 如提供 `policy.json`，默认告警模板可见。

### 11.3 文件级自检

提交前至少检查：

- `collectors/*.json` 是合法 JSON，且顶层为数组。
- `metrics.json` 是合法 JSON。
- `UI.json` 是合法 JSON。
- `policy.json` 是合法 JSON。
- 模板文件名符合 `{type}.{config_type}.{file_type}.j2`。
- 插件目录层级严格为 `<collector>/<collect_type>/<instance_type>/`。

---

## 12. 常见失败原因

### 12.1 目录层级不对，插件未导入

表现：执行 `plugin_init` 后插件不存在。

优先检查：

- 是否放在 `apps/monitor/support-files/plugins` 下
- 是否严格满足 `<collector>/<collect_type>/<instance_type>/metrics.json`

### 12.2 collector / collect_type 不符合预期

表现：插件数据导入了，但归属采集器或采集方式不正确。

原因：

- 这两个字段来自路径解析，不是手工指定。

### 12.3 模板文件未生效

表现：插件导入了，但没有配置模板。

优先检查：

- 文件是否为 `.j2`
- 文件名是否符合 `{type}.{config_type}.{file_type}.j2`

### 12.4 policy 导入失败

表现：插件有了，但默认告警模板没进来。

优先检查：

- `policy.json.object` 是否等于实际监控对象名
- `policy.json.plugin` 是否等于 `metrics.json.plugin`

### 12.5 内置数据被清理

表现：已有内置插件/采集器/模板被删。

原因：

- `node_init` / `plugin_init` 会以当前目录中的内置文件为准进行同步。
- 从内置目录删除文件后再次初始化，系统会清理数据库中的对应内置数据。

代码依据：

- `apps/node_mgmt/management/services/node_init/collector_init.py`
- `apps/monitor/management/services/plugin_migrate.py`

---

## 13. 推荐接入顺序（最稳妥）

1. 先复制一个最接近的现有插件目录作为模板。
2. 先完成 `collectors/*.json`。
3. 再完成 `metrics.json`。
4. 再补 `UI.json`。
5. 按需补 `.j2` 模板与 `policy.json`。
6. 执行：
   - `python manage.py node_init`
   - `python manage.py plugin_init`
7. 最后在页面验证。

推荐优先参考的现成样例：

- 简单对象：`apps/monitor/support-files/plugins/Telegraf/ping/ping/`
- 复合对象：`apps/monitor/support-files/plugins/unknown/k8s/k8s/`
- 采集器定义：`apps/node_mgmt/support-files/collectors/Telegraf.json`

---

## 14. 最后提醒

- 不要只新增 `metrics.json`，却忘记新增 node 模块的采集器定义。
- 不要修改目录层级来“优化结构”，当前导入逻辑依赖固定层级。
- 不要随意修改已上线插件的 `plugin`、监控对象 `name`、采集器 `id`，这些字段都会影响更新与关联关系。
- 新增或调整内置插件后，必须重新执行初始化命令验证结果。
