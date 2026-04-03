# 监控系统｜集成自定义模版方案（API / PULL）

## 1. 方案概览

本次方案不再把“自建模版”限定为单一的 API 报数模式，而是统一建设为两类用户可创建的自定义插件：

1. **API 类型模版**
2. **PULL 类型模版**

两类模版虽然都挂在“监控集成”下面，但产品形态与底层链路完全不同：

- **API 类型**：第三方主动上报，页面是接入引导页
- **PULL 类型**：平台主动拉取，页面是采集配置页

本次方案采用“**展示层统一、实现层分流**”策略：

- 列表页统一展示内置模版与自定义模版
- API 类型走纯引导模型
- PULL 类型走插件级配置模型
- 不再沿用旧的 token + server push_api + 实例导入式 API 接入模型

---

## 2. 背景与目标

当前监控集成以内置模版为主，适合平台主动采集场景，但无法覆盖以下两类用户诉求：

1. **外部系统主动推送监控数据**
2. **用户自己提供 Prometheus 指标地址，由平台定时拉取**

因此，本次目标是建设统一的“自定义插件”能力，并明确拆分两类模型：

### 2.1 API 类型目标

建设一套标准化的第三方主动上报能力，特点为：

- 用户创建 API 类型模版
- 平台展示接入说明
- 第三方按固定协议向 Telegraf HTTP Listener 发送数据
- 页面不承担实例管理与 token 管理

### 2.2 PULL 类型目标

建设一套接近内置插件的自定义采集能力，特点为：

- 用户创建 PULL 类型模版
- 平台自动初始化配置模板与 UI 模板
- 用户填写实例级目标地址
- 平台生成 `[[inputs.prometheus]]` 配置并下发

---

## 3. 统一字段约定

### 3.1 模版主表字段

沿用 `MonitorPlugin`：

- `template_id`：模版 ID，由用户输入，唯一
- `template_type`：模版类型

### 3.2 `template_type` 统一枚举

固定使用：

- `builtin`
- `api`
- `pull`
- `snmp`

当前实际交付聚焦：

- `builtin`
- `api`
- `pull`

语义如下：

- `builtin`：内置插件
- `api`：自定义 API 模版
- `pull`：自定义 PULL 模版

---

## 4. 范围边界

### 4.1 In Scope

本次纳入范围：

1. 监控集成列表展示自定义 API / PULL 模版
2. 支持创建、编辑、删除自定义模版
3. 模版必须绑定一个监控对象
4. 支持模板级指标组、指标管理
5. API 模版支持接入引导页
6. PULL 模版支持自动初始化插件级配置模板与 UI 模板
7. PULL 模版支持基于 `[[inputs.prometheus]]` 创建采集配置
8. API 模版接入地址由云区域环境变量提供
9. API 模版采用 Telegraf `http_listener_v2` 接收入站报文
10. API 模版固定使用 `POST` + line protocol

### 4.2 Out of Scope

本次不纳入范围：

1. 旧 `push_api` 接口体系继续增强
2. token 查询、token 校验体系
3. API 模版实例创建 / 导入 / 列表展示能力
4. API 模版服务端入站校验与异步 NATS 投递链路
5. SNMP 自定义模版完整实现
6. 模版版本管理
7. 模版审批 / 发布流
8. 第三方 SDK 封装
9. 高级 TLS 双向证书配置
10. 自定义 PULL 高级 headers/TLS/UI 扩展能力

---

## 5. 两类模版的业务定义

## 5.1 API 类型模版

### 业务定位

API 类型模版本质是 **push**：

- 平台提供接入地址
- 平台规定数据格式
- 第三方主动发送数据

### 页面形态

API 模版详情页不是采集配置页，而是**接入引导页**。

当前引导页仅包含：

1. 云区域选择
2. 组织选择
3. API 端点
4. 请求示例
5. 请求参数说明

不再包含：

- token
- 实例创建
- 实例导入
- 实例列表
- 响应示例

### 接入地址来源

接入地址来自**云区域环境变量**：

- `TELEGRAF_HTTP_LISTENER_URL`

前端选择云区域后，由后端读取该云区域的环境变量并渲染到页面。

### 运行时监听配置

底层监听器采用：

- Telegraf `http_listener_v2`

当前固定监听形态：

- 端口：`19090`
- 路径：`/telegraf/api`
- 方法：`POST`
- 数据格式：`influx`（line protocol）

### 协议规则

请求方式固定为：

- `POST`

请求体固定为：

- line protocol

引导页示例中固定包含：

- `organization_id`
- `instance_type`
- `plugin_id`

时间戳规则：

- 时间戳为可选项
- 不传时间戳时，默认使用服务端接收时间
- 如需显式传入时间戳，推荐使用 13 位毫秒时间戳

引导页至少提供两种 line protocol 示例：

1. **不带时间戳**

```text
demo_metric,organization_id=1,instance_type=host,plugin_id=1 value=1
```

2. **带 13 位毫秒时间戳**

```text
demo_metric,organization_id=1,instance_type=host,plugin_id=1 value=1 1712052000000
```

### 服务端职责

对于 API 模版，server 只负责：

- 提供模版元数据
- 提供接入引导页数据
- 根据云区域渲染接入地址

server 不再负责：

- 接收上报数据
- token 校验
- 报文同步校验
- 异步投递 NATS

---

## 5.2 PULL 类型模版

### 业务定位

PULL 类型模版本质是 **pull**：

- 用户提供目标 Prometheus 指标地址
- 平台创建采集配置
- Telegraf 定时拉取目标地址

### 页面形态

PULL 模版详情页复用采集配置型页面，而不是引导页。

### 底层采集方式

底层固定采用：

- `[[inputs.prometheus]]`

### 配置模型

PULL 模版采用 **plugin-first** 模型：

1. 创建模版时初始化插件记录
2. 初始化 `MonitorPluginConfigTemplate`
3. 初始化 `MonitorPluginUITemplate`
4. 后续实例接入配置挂到插件维度

为支撑插件级配置，`CollectConfig` 新增：

- `monitor_plugin`

### 第一版参数分层

#### 公共采集参数

当前仅保留：

1. 认证
2. 用户名
3. 密码
4. Token
5. 采集间隔

#### 实例级参数

当前仅保留：

1. 节点
2. 服务地址 `server_url`
3. 实例名称
4. 分组

### 第一版默认策略

为降低用户使用成本，以下高级参数暂不暴露在页面：

- 自定义请求头
- 手工 TLS 开关
- 独立 timeout
- 独立 response_timeout

当前默认策略为：

- `insecure_skip_verify = true`
- `timeout = interval`
- `response_timeout = interval`

### 模板渲染规则

child 模板固定生成：

```toml
[[inputs.prometheus]]
    startup_error_behavior = "retry"
    urls = ["{{ server_url }}"]
    interval = "{{ interval }}s"
    timeout = "{{ interval }}s"
    response_timeout = "{{ interval }}s"
```

并额外写入：

- `plugin_id` tag

用于后续数据链路区分插件来源。

---

## 6. 页面与交互规划

### 6.1 模版列表页

在现有监控集成模版列表中统一展示：

- 内置模版
- 自定义 API 模版
- 自定义 PULL 模版

自定义模版支持：

- 新建
- 编辑
- 删除
- 查看详情

列表页统一通过 `is_custom` 标识自定义模版，不再拆分 `is_custom_api` / `is_custom_pull`。

### 6.2 创建模版弹窗

用户创建模版时选择：

1. 监控对象类型
2. 监控对象
3. 模版名称
4. 模版 ID
5. 模版类型（API / PULL）
6. 模版描述

### 6.3 API 模版详情页

API 模版详情页保留：

1. 配置（接入引导页）
2. 指标

其中“配置”页承载：

1. 云区域
2. 组织
3. API 端点
4. 请求示例
5. 请求参数说明

### 6.4 PULL 模版详情页

PULL 模版详情页保留：

1. 配置（自动采集配置页）
2. 指标

配置页中：

- 公共采集参数填写一次
- 实例级参数按行填写

---

## 7. 核心实现方案

### 7.1 API 类型实现

#### 后端

新增引导服务：

- `TemplateAccessGuideService`

职责：

1. 校验 `organization_id`
2. 校验 `cloud_region_id`
3. 读取云区域环境变量 `TELEGRAF_HTTP_LISTENER_URL`
4. 生成 API endpoint
5. 生成 line protocol 示例
6. 返回模版指标元数据

其中 line protocol 示例需同时返回：

- 不带时间戳示例
- 带 13 位毫秒时间戳示例

#### 前端

详情页使用独立目录：

- `configure/accessGuide/`

不再使用旧的 token / 实例 / push_api 风格页面。

### 7.2 PULL 类型实现

#### 创建时初始化

由 `CustomPullPluginService` 完成：

1. 创建插件记录
2. 初始化 `MonitorPluginConfigTemplate`
3. 初始化 `MonitorPluginUITemplate`

#### 配置渲染

配置渲染优先按 `monitor_plugin_id` 查模板，而不是仅按：

- `collector`
- `collect_type`
- `monitor_object_id`

#### 编辑回显

编辑实例配置时优先按插件获取 UI 模板，保证多个自定义 PULL 插件可共存。

---

## 8. 删除与兼容策略

### 8.1 删除规则

删除自定义模版时：

- 删除模板本身
- 删除模板关联的插件级配置模板 / UI 模板
- 删除插件级采集配置（依赖数据库外键级联）
- 不删除监控实例本体

### 8.2 兼容策略

本次不兼容旧的“自建 API + token + push_api + 实例导入”逻辑。

旧逻辑相关代码应视为废弃，不再作为产品主方案。

---

## 9. 部署与运行前提

### 9.1 数据库迁移

必须执行 monitor 最新迁移，当前关键迁移为：

- `0032_collectconfig_monitor_plugin_and_custom_pull_templates.py`

否则会出现：

- 删除自定义插件时报 `monitor_collectconfig.monitor_plugin_id does not exist`

### 9.2 云区域配置

每个云区域必须配置：

- `TELEGRAF_HTTP_LISTENER_URL`

该变量用于 API 模版接入页渲染地址。

### 9.3 容器节点监听要求

Telegraf 运行配置固定为：

- 监听端口：`19090`
- 监听路径：`/telegraf/api`

部署时需确保：

1. Telegraf 配置已生效
2. 容器 / 宿主机 / 网络策略已放通 `19090`
3. `TELEGRAF_HTTP_LISTENER_URL` 与实际暴露地址一致

---

## 10. 验收清单

### 10.1 通用验收

1. 可创建 API / PULL 两类自定义模版
2. 可编辑自定义模版基础信息
3. 可删除自定义模版
4. 可维护模板级指标组与指标

### 10.2 API 模版验收

1. API 模版详情页展示为接入引导页
2. 云区域切换后地址正确变化
3. 接入地址来自 `TELEGRAF_HTTP_LISTENER_URL`
4. 请求示例固定为 `POST` + line protocol
5. 引导页同时展示“不带时间戳”与“带 13 位毫秒时间戳”两种示例
6. 页面不再展示 token / 实例 / 响应示例

### 10.3 PULL 模版验收

1. 创建 PULL 模版时自动初始化 DB 配置模板与 UI 模板
2. 可按实例填写 `server_url`
3. 可填写最小公共参数（认证 + 采集间隔）
4. 可成功生成 `[[inputs.prometheus]]` 配置
5. 配置记录正确关联到 `monitor_plugin`

### 10.4 稳定性验收

1. 空 `status_query` 不会导致实例列表调用 VM 报 422
2. 未执行 migration 时，删除插件有明确报错提示
3. PULL 配置编辑能正确回显并更新

---

## 11. 风险与应对

### 风险 1：继续沿用旧 API token / push_api 思路，导致业务口径混乱
**应对：**
- 明确 API 模版只做接入引导
- 明确数据不经过 server

### 风险 2：自定义 PULL 仍按 collect_type 粗粒度取模板，导致多个插件串模板
**应对：**
- 使用 plugin-first 方案
- `CollectConfig` 关联 `monitor_plugin`

### 风险 3：PULL 第一版参数过多，导致接入成本高
**应对：**
- 第一版仅暴露最小必要参数
- 高级参数默认内置，不在页面暴露

### 风险 4：云区域未配置 `TELEGRAF_HTTP_LISTENER_URL`
**应对：**
- 引导页明确报配置缺失
- 部署前作为必查项

---

## 12. 回滚与降级策略

### 12.1 回滚原则

- 仅回滚自定义 API / PULL 模版能力
- 不影响现有内置模版

### 12.2 回滚方式

1. 隐藏前端创建入口
2. 停止使用自定义模板
3. 回滚数据库迁移与相关后端逻辑

### 12.3 降级策略

- 若 API 引导页不可用：临时隐藏 API 模版入口
- 若 PULL 初始化模板异常：临时仅保留 API 模版入口
- 若容器节点 HTTP Listener 不可用：阻断 API 模版外部接入

---

## 13. 完整性检查

### 范围边界
- 已拆分 API / PULL 两类模版

### 依赖方
- 已覆盖云区域环境变量、Telegraf、数据库迁移、配置下发链路

### 验收口径
- 已覆盖通用、API、PULL、稳定性四个维度

### 风险与回滚
- 已覆盖迁移、配置、链路与最小降级策略
