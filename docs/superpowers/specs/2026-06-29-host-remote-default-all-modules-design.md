# Host Remote / Windows WMI 默认全量采集设计

## 背景

监控模块的主机远程插件目前在配置页暴露了“采集模块”复选框。用户可以勾选 CPU、Memory、Disk、Disk IO、Network、Processes、System 等模块。截图中暴露出两个问题：

1. 产品期望采集模块默认全部采集，不再让用户在页面上选择。
2. 指标页中部分插件分组和指标名仍显示英文，例如 `Network`、`Processes`，说明语言包存在缺口。

本次范围限定为两个主机远程插件：

- `Host Remote`
- `Windows WMI`

## 目标

1. `Host Remote` 和 `Windows WMI` 新增配置时默认全量采集：`cpu,mem,disk,diskio,net,processes,system`。
2. 配置页不再展示采集模块勾选项。
3. 编辑已有配置时不再允许用户修改采集模块。
4. 已存在的 `Host Remote` / `Windows WMI` 子配置通过幂等修复统一改为全量采集，避免页面隐藏后仍保留部分采集的旧状态。
5. 补齐这两个插件在 Host 对象指标页使用到的中英文分组和指标翻译。

## 非目标

1. 不改变 Stargazer 的采集实现、任务队列或指标生成逻辑。
2. 不重构监控插件 UI 渲染框架。
3. 不清理其他插件的历史翻译缺口。
4. 不引入用户可配置的采集模块开关。

## 方案

### 插件 UI 模板

修改以下插件 UI 模板：

- `server/apps/monitor/support-files/plugins/Telegraf/http/host/UI.json`
- `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/UI.json`

将 `metrics_modules` 从可见的 `checkbox_group` 改为 `hidden` 字段，默认值为：

```json
["cpu", "mem", "disk", "diskio", "net", "processes", "system"]
```

前端 `web/src/app/monitor/hooks/integration/useConfigRenderer.tsx` 已支持 `hidden` 类型，隐藏字段仍可进入表单默认值和提交参数，因此不需要扩展前端渲染器。

### 采集模板默认值

修改以下采集模板中的 `metrics_modules` 默认值：

- `server/apps/monitor/support-files/plugins/Telegraf/http/host/host.child.toml.j2`
- `server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/windows_wmi.child.toml.j2`

默认值统一为：

```text
cpu,mem,disk,diskio,net,processes,system
```

同时修改 Stargazer HTTP API 的兜底默认值：

- `agents/stargazer/api/monitor.py`

`/api/monitor/host/metrics` 当前默认是 `cpu,mem,disk,net`，需要改成全量。`/api/monitor/windows/wmi/metrics` 当前已经是全量，保留并用测试覆盖。

### 已有配置迁移

在监控插件迁移流程中增加幂等修复步骤，放在插件模板导入之后执行。

修复对象：

- `CollectConfig.collect_type = "http"`
- `CollectConfig.config_type in {"host", "windows_wmi"}`
- `CollectConfig.is_child = true`
- 关联的 NodeMgmt 子配置内容中包含 `metrics_modules = "..."`

修复行为：

1. 读取对应子配置内容。
2. 将 `metrics_modules = "现有双引号内模块列表"` 替换为 `metrics_modules = "cpu,mem,disk,diskio,net,processes,system"`。
3. 内容已是全量时不更新。
4. 不匹配的配置不修改。

该步骤重复执行结果一致，不依赖用户是否重新编辑配置。

## 翻译

补齐语言包：

- `server/apps/monitor/language/zh-Hans.yaml`
- `server/apps/monitor/language/en.yaml`

### 分组

在 `monitor_object_metric_group.Host` 下补：

- `Network`
- `Processes`

保留已有 `Net`、`Process`，避免影响旧指标或其他页面。

### 指标

在 `monitor_object_metric.Host` 下补齐：

- `system_uptime`
- `net_packets_recv_total`
- `net_packets_sent_total`
- `net_drop_in_total`
- `net_drop_out_total`
- `diskio_reads_total`
- `diskio_writes_total`
- `diskio_read_bytes_total`
- `diskio_write_bytes_total`

这些 key 覆盖 `Host Remote` 缺失的指标翻译；`Windows WMI` 复用 `system_uptime`。

## 测试

新增或更新 monitor 相关测试，覆盖以下断言：

1. `Host Remote` / `Windows WMI` 的 `UI.json` 中 `metrics_modules` 为 `hidden`，默认值为全量模块，不再是可见 `checkbox_group`。
2. `host.child.toml.j2`、`windows_wmi.child.toml.j2` 和 Stargazer API 默认值均为全量模块。
3. 两个插件 `metrics.json` 使用到的 Host 分组和指标 key 在 `zh-Hans.yaml` 与 `en.yaml` 中都有映射。
4. 已有子配置修复逻辑只修改 `collect_type=http` 且 `config_type in {"host", "windows_wmi"}` 的子配置内容，并且重复执行幂等。

最小验证命令：

```bash
cd server && make test
```

如测试耗时过长，可先运行覆盖本次变更的精确 pytest 用例，再补跑模块门禁。

## 风险与处理

1. **旧配置被强制扩展采集范围**：这是本次产品目标。采集量会增加，但两个插件目标就是主机指标全量采集，且页面隐藏后必须避免用户不可见的部分采集状态。
2. **已有翻译 key 命名不一致**：只新增 `Network` / `Processes`，不删除旧 `Net` / `Process`，降低兼容风险。
3. **迁移误改其他插件**：通过 `CollectConfig` 元数据限定 `collect_type`、`config_type`、`is_child`，并只替换明确的 `metrics_modules` 行。

## 验收标准

1. 配置页不再显示 Host Remote / Windows WMI 的采集模块复选框。
2. 新建 Host Remote / Windows WMI 配置时生成的 Telegraf 子配置包含全量 `metrics_modules`。
3. 已存在的 Host Remote / Windows WMI 子配置在迁移后也包含全量 `metrics_modules`。
4. 指标页中 `Network`、`Processes` 分组不再回退显示英文；缺失指标显示对应中英文文案。
5. 相关自动化测试通过。
