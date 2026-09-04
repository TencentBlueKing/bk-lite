# APM · 功能清单

**文档版本：** V1.0
**发布日期：** 2026-08-24
**适用范围：** BK-Lite APM 模块
**编制依据：** 与 `server/apps/apm`、`web/src/app/apm` 源代码核对

对应产品：[[apm-product.md#产品入口]]

对应架构：[[apm-architecture.md#职责与边界]]

对应告警契约：[[apm-alerting.md#长期契约]]

---

## 一、模块定位

APM 提供应用性能观察与自有告警，覆盖接入、服务目录、调用链探索、SLO 与策略告警。本清单只列已实现能力。数据面契约夹具存在，但仓库声明从未正式生产部署，故状态标 Beta。

## 二、功能清单

### 1. 集成与目录

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 应用管理 | 创建与维护应用，并分配组织 | 组织失败则拒绝 | Beta |
| 接入指引 | 按语言生成离线安装说明 | Java / Python / Node.js / Go / .NET（Linux x86_64 glibc）；指向系统内下载与区域内网接入；可选本次脚本采样率（默认全量，不持久化）；不支持公网令牌 | Beta |
| 探针下载 | 在目标主机下载白名单探针制品 | 免登录；未知制品返回不存在 | Beta |
| 服务目录 | 展示发现的服务，支持归档/恢复与组织授权 | 活跃窗口 15 分钟；分钟级对账 | Beta |
| 实例目录 | 展示上报实例并分配组织 | 与服务身份规范化唯一 | Beta |

### 2. 观察

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 首页总览 | 展示健康、SLO、告警与 Top 指标 | 分节可空或降级，不编造数据 | Beta |
| 调用链探索 | 检索与查看调用链 | 最长 35 天；敏感属性脱敏；禁止任意查询语言 | Beta |
| Span / 端点探索 | 检索 Span 与端点 | 组织过滤；参数白名单 | Beta |
| 错误聚合 | 按异常语义聚类错误 | 基于可见服务；服务详情错误 Tab 计数看入口失败、归因看该服务全部 Error Span，分区标注；探索页仍按 Issue fingerprint 翻页 | Beta |
| 服务拓扑 | 展示服务依赖 | 窗口不超过 7 天 | Beta |
| RED 指标 | 查看服务错误率、时延、吞吐 | 环境/端点/窗口受控 | Beta |

### 3. 可靠性

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| SLO | 定义并评估可用性或时延目标 | 目标 (0,100]；时延类必须带阈值 | Beta |
| 告警策略 | 配置并启停策略 | 仅五种指标；必选环境；不支持监控表达式 | Beta |
| 告警与事件 | 查看生命周期并关闭 | 告警状态 active/recovered/closed；事件不可变 | Beta |
| 告警证据 | 查看扫描点趋势与事件原始证据 | 禁止用实时库重建历史；证据可 pending/expired | Beta |
| 通知投递 | 按渠道投递并可人工重试 | 可补偿；告警中心副本不回写 | Beta |
| 运行健康 | 探测追踪库、采集链路与通知依赖 | 仅运行期；不阻断进程启动 | Beta |

> 证据来源：server/apps/apm/urls.py:25-46，web/src/app/apm/constants/menu.json:2-120，server/apps/apm/models/control_plane.py:182-308，server/apps/apm/adapters/victoriatraces.py:36-37，server/apps/apm/config.py:3-27，deploy/apm/README.md:1-22　|　同步基线：61bace9f　|　【已实现】

## 三、能力边界与约束

- 不提供 VictoriaMetrics、Span Metrics、尾采样或独立边缘网关。
- 不提供跨租户公网 OTLP。
- 不把监控对象、采集插件或日志检索纳入策略。

> 证据来源：deploy/apm/README.md:21-22,56-58，specs/capabilities/apm-alerting.md:7　|　同步基线：61bace9f　|　【已实现】

## 四、平台协同

- 组织与通知渠道来自系统管理。
- 接入区域信息来自节点管理。
- 可选把事件副本抄送到告警中心，告警中心不得回写。

> 证据来源：server/apps/apm/adapters/notifications.py:7-27，specs/capabilities/apm-alerting.md:12　|　同步基线：61bace9f　|　【已实现】
