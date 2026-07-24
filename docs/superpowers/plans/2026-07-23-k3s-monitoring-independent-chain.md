# BK-Lite 独立 K3S 监控链路实施计划

> 依据：`docs/superpowers/specs/2026-07-23-k3s-monitoring-independent-chain-design.md`

**目标：** 在不改变现有 K8S 行为的前提下，为监控中心交付一条入口、身份、后端编排、集群采集、实例发现和专业仪表盘均独立的 K3S 监控链路。

**架构：** 新增 `K3S/K3SCluster/K3SNode/K3SPod` 业务身份，由独立 `K3SOnboarding` 模块签发 K3S 令牌并调用 webhookd `/infra/k3s`。K3S 清单在 `bk-lite-k3s-collector` 中运行 vmagent、kube-state-metrics 和两类 Telegraf；vmagent 经 API Server Node Proxy 抓取 kubelet cAdvisor。平台只复用通用 ORM、插件导入、VictoriaMetrics 查询、NATS `metrics.cloud` 和基础 UI 组件。

**实施原则：**

- 每个任务先写失败测试，再写最小实现，再运行定向回归。
- 不修改 K8S 插件 JSON、K8S 清单、`InfraService`、`ManualCollectService` 或 K8S 仪表盘查询。
- 允许修改共享注册点：`server/apps/monitor/urls.py`、监控前端配置注册、配置页分派和专业仪表盘 registry；修改只能增加 K3S 项。
- K3S 代码不得导入 `configure/k8s` 或 `dashboards/objects/k8s-*` 下的业务模块。
- 不新增数据库表或 migration；实例继续使用现有 Django ORM 模型。
- 每个提交只覆盖一个可验证的纵向增量，提交信息使用中文。

## Task 1：固化 K3S 插件和指标契约

**新增文件：**

- `server/apps/monitor/support-files/plugins/unknown/k3s/k3s/metrics.json`
- `server/apps/monitor/support-files/plugins/unknown/k3s/k3s/language/zh-Hans.yaml`
- `server/apps/monitor/support-files/plugins/unknown/k3s/k3s/language/en.yaml`
- `server/apps/monitor/tests/test_k3s_plugin_contract.py`

**Step 1：先写插件失败测试**

测试必须断言：

- 插件名为 `K3S`，状态查询只使用 `instance_type="k3s"`。
- 对象严格为 `K3SCluster`、`K3SNode`、`K3SPod`。
- 基础/衍生关系和唯一键分别为：
  - `K3SCluster`：`["instance_id"]`
  - `K3SNode`：`["instance_id", "node"]`
  - `K3SPod`：`["instance_id", "pod"]`
- 指标数量与首期契约一致：Cluster 4、Pod 8、Node 28。
- 每条查询都含 K3S 身份，不出现 `instance_type="k8s"` 或 K8S 对象名。
- `display_fields` 和 `supplementary_indicators` 引用的指标均存在。
- 中英文语言文件含 `K3S` 描述。

运行并确认失败：

```bash
cd server
uv run pytest apps/monitor/tests/test_k3s_plugin_contract.py -v --no-cov
```

**Step 2：新增 K3S 插件**

- 以 K8S 的成熟指标口径为参考复制指标定义。
- 将插件和对象身份完整替换为 K3S 身份。
- 保留 Prometheus measurement 名，因为两条链路通过 `instance_type` 隔离。
- 使用现有通用插件导入链路，不给 `plugin_init` 增加 K3S 特判。

**Step 3：验证导入幂等性**

增加数据库测试：

- 第一次 `migrate_plugin()` 创建三个对象。
- 第二次执行只更新 K3S 对象和指标，不重复创建。
- K8S 的 `Cluster/Node/Pod` 和 K3S 的三个对象可同时存在。

运行：

```bash
cd server
uv run pytest apps/monitor/tests/test_k3s_plugin_contract.py apps/monitor/tests/test_management_migrate.py -v --no-cov
```

**Step 4：提交**

```bash
git add server/apps/monitor/support-files/plugins/unknown/k3s/k3s \
  server/apps/monitor/tests/test_k3s_plugin_contract.py
git commit -m "feat: 新增 K3S 监控插件契约"
```

## Task 2：实现 K3S 自包含采集清单

**新增文件：**

- `agents/webhookd/bk-lite-k3s-metric-collector.yaml`
- `agents/webhookd/infra/tests/test_k3s_manifest_contract.py`

**Step 1：先写清单静态失败测试**

测试解析所有 YAML 文档并断言：

- namespaced 资源全部属于 `bk-lite-k3s-collector`。
- 集群级资源全部使用 `bk-lite-k3s-` 前缀。
- 工作负载包含 `k3s-vmagent`、`k3s-kube-state-metrics`、`k3s-metric-telegraf`、`k3s-node-telegraf`。
- 不存在 cAdvisor DaemonSet、Docker Socket、`/var/lib/docker`、`--docker_only`、`insecure_skip_verify`。
- vmagent 使用 ServiceAccount Token、Service CA、`kubernetes.default.svc` 和 `/api/v1/nodes/$1/proxy/metrics/cadvisor`。
- vmagent RBAC：
  - `nodes` 仅有 `get/list/watch`
  - `nodes/proxy` 仅有 `get`
- cAdvisor allowlist 严格为六个指标族：
  - `container_cpu_usage_seconds_total`
  - `container_memory_working_set_bytes`
  - `container_fs_reads_total`
  - `container_fs_writes_total`
  - `container_network_receive_bytes_total`
  - `container_network_transmit_bytes_total`
- KSM allowlist 严格覆盖规格中的 17 个指标族。
- 所有输出都注入 `instance_id`、`instance_name`、`instance_type=k3s`。
- 两类 Telegraf 只发往 NATS `metrics.cloud`，且 NATS TLS 校验开启。

运行并确认失败：

```bash
cd server
uv run pytest ../agents/webhookd/infra/tests/test_k3s_manifest_contract.py -v --no-cov
```

**Step 2：实现清单资源和 RBAC**

- 创建独立 Namespace、Secret 占位引用、ServiceAccount、ClusterRole 和 ClusterRoleBinding。
- kube-state-metrics 使用独立只读 RBAC，不与 vmagent 共用账号。
- 所有容器设置只读根文件系统、禁止提权、删除不需要的 Linux capability，并设置合理 requests/limits。
- 不引用 `bk-lite-collector` 或任何 K8S 资源名。

**Step 3：实现 vmagent 抓取**

- Kubernetes SD 使用 `role: node`。
- relabel 把 API Server 地址固定为 `kubernetes.default.svc:443`。
- metrics path 使用发现到的节点名构造 Node Proxy 路径。
- 认证使用 `authorization.credentials_file`。
- TLS 使用 Service CA 和 `server_name: kubernetes.default.svc`。
- metric relabel 先保留六个指标族，再规范 `pod/node/container` 标签并丢弃高基数标签。

**Step 4：实现 KSM 和节点指标链路**

- vmagent 精确抓取 K3S 自有 kube-state-metrics Service。
- KSM 指标与 cAdvisor 指标统一 remote write 到 `k3s-metric-telegraf`。
- 节点 Telegraf 沿用现有 inputs 技术，标签改为 K3S 身份。
- 固定 60 秒周期，不暴露模板变量。

**Step 5：验证清单**

```bash
cd server
uv run pytest ../agents/webhookd/infra/tests/test_k3s_manifest_contract.py -v --no-cov
cd ..
kubectl apply --dry-run=client -f agents/webhookd/bk-lite-k3s-metric-collector.yaml
```

若本机 `kubectl` 不能完成 client dry-run，保留原始输出，但静态契约测试必须通过。

**Step 6：提交**

```bash
git add agents/webhookd/bk-lite-k3s-metric-collector.yaml \
  agents/webhookd/infra/tests/test_k3s_manifest_contract.py
git commit -m "feat: 新增 K3S 自包含监控采集清单"
```

## Task 3：新增 webhookd K3S 独立渲染入口

**新增/修改文件：**

- 新增 `agents/webhookd/infra/k3s.sh`
- 新增 `agents/webhookd/infra/tests/test_k3s_render.py`
- 修改 `agents/webhookd/infra/API.md`

**Step 1：先写渲染失败测试**

通过子进程执行 `k3s.sh`，覆盖：

- 缺少 `cluster_name/nats_url/nats_username/nats_password/nats_ca` 时返回结构化错误。
- cluster name 只允许字母、数字、下划线和连字符。
- 不接受 `type`、`config_type`、`distribution` 等切换字段。
- 合法输入只加载 `bk-lite-k3s-metric-collector.yaml`。
- 输出包含 K3S Secret，凭据以 base64 安全替换。
- 输出不存在 K8S namespace、K8S Secret 或 K8S collector 资源名。
- shell stdout 只有 JSON 响应，诊断输出不得污染 webhookd 响应。

运行并确认失败：

```bash
cd server
uv run pytest ../agents/webhookd/infra/tests/test_k3s_render.py -v --no-cov
```

**Step 2：实现独立脚本**

- 不 source 或调用 `infra/kubernetes.sh`。
- 只读取 K3S 模板。
- 使用 `jq --arg`/`jq -n` 生成 JSON，避免字符串拼接污染。
- 使用 `envsubst` 时只开放显式变量集合。
- Secret 固定为 K3S 名称和命名空间。

**Step 3：更新 API 文档**

在 `agents/webhookd/infra/API.md` 增加 `POST /infra/k3s`：

- 精确请求字段。
- 成功和错误响应。
- 安全说明。
- 不把 K3S 加成 `/infra/kubernetes` 的 `type` 值。

**Step 4：验证**

```bash
bash -n agents/webhookd/infra/k3s.sh
cd server
uv run pytest ../agents/webhookd/infra/tests/test_k3s_render.py \
  ../agents/webhookd/infra/tests/test_k3s_manifest_contract.py -v --no-cov
```

**Step 5：提交**

```bash
git add agents/webhookd/infra/k3s.sh agents/webhookd/infra/API.md \
  agents/webhookd/infra/tests/test_k3s_render.py
git commit -m "feat: 新增 K3S 独立清单渲染入口"
```

## Task 4：实现 K3S Onboarding 深模块

**新增文件：**

- `server/apps/monitor/constants/k3s_onboarding.py`
- `server/apps/monitor/services/k3s_onboarding.py`
- `server/apps/monitor/tests/test_k3s_onboarding_service.py`

**Step 1：先写模块接口失败测试**

围绕四个公开操作测试，不测试内部透传函数：

1. `create_instance`
   - 只允许目标对象为 `K3SCluster`。
   - 使用现有 ORM 创建人工实例、组织关系和子对象分组规则。
   - 同对象名称冲突返回现有结构化校验错误。
2. `generate_install_command`
   - 实例必须存在、未删除且属于 `K3SCluster`。
   - 令牌 payload 绑定逻辑 `instance_id`、实例主键、cloud region 和租户/组织上下文。
   - 命令使用 `curl --fail --show-error --silent --location`，不含 `-k/--insecure`。
   - 返回安装命令、同一清单对应的有界卸载命令和过期时间。
3. `render_manifest`
   - 只接受 `k3s_infra_install_token:*`。
   - 令牌固定 300 秒、最多使用 5 次。
   - 使用 Django cache 的原子 `incr` 计数；第 6 次拒绝。
   - 调用 webhookd 的路径严格为 `/infra/k3s`。
   - webhookd TLS 使用 `get_webhook_tls_verify()`。
4. `verify_reporting`
   - 分别查询 `kube_node_info`、`container_cpu_usage_seconds_total`、`system_load1`。
   - 每个查询都包含目标 `instance_id` 和 `instance_type=k3s`。
   - 返回 `cluster/container/node` 三段状态和总状态。
   - 查询异常与空结果可区分，错误不阻断 Django 服务启动。

运行并确认失败：

```bash
cd server
uv run pytest apps/monitor/tests/test_k3s_onboarding_service.py -v --no-cov
```

**Step 2：实现常量和令牌存储**

- K3S 常量独立定义：
  - `TOKEN_PREFIX = "k3s_infra_install_token"`
  - `TOKEN_EXPIRE_TIME = 300`
  - `TOKEN_MAX_USAGE = 5`
  - webhookd path `/infra/k3s`
- 令牌 payload 和使用次数使用不同 cache key。
- 使用 `cache.add` 初始化计数，`cache.incr` 消耗次数。
- payload/usage key 使用相同 TTL；超限后删除两者。
- 不调用 `InfraService.generate_install_token()`。

**Step 3：实现实例和命令编排**

- 复用现有通用 ORM 辅助能力，但实例类型校验留在 K3S 模块。
- 安装命令：

```text
curl --fail --show-error --silent --location -X POST .../open_api/k3s_onboarding/render/ ... | kubectl apply -f -
```

- 卸载命令使用新令牌重新渲染同一有界清单，并执行：

```text
... | kubectl delete --ignore-not-found=true -f -
```

- 命令中 URL 和 JSON token 使用安全 shell quoting，测试包含特殊 URL 场景。

**Step 4：实现 webhookd 适配和三段验证**

- 从 cloud region 环境读取现有 NATS 和 webhookd 配置。
- 缺失变量一次性返回完整缺失列表。
- requests 超时使用有界常量。
- 日志只记录 token 前缀、实例和结果，不记录 NATS 凭据。
- 验证结果结构固定为：

```json
{
  "status": "success|partial|pending|error",
  "signals": {
    "cluster": {"status": "...", "metric": "kube_node_info"},
    "container": {"status": "...", "metric": "container_cpu_usage_seconds_total"},
    "node": {"status": "...", "metric": "system_load1"}
  }
}
```

**Step 5：验证并提交**

```bash
cd server
uv run pytest apps/monitor/tests/test_k3s_onboarding_service.py \
  apps/monitor/tests/test_infra_tls.py \
  apps/monitor/tests/test_manual_collect_validators.py -v --no-cov
git add apps/monitor/constants/k3s_onboarding.py \
  apps/monitor/services/k3s_onboarding.py \
  apps/monitor/tests/test_k3s_onboarding_service.py
git commit -m "feat: 实现 K3S 接入编排模块"
```

## Task 5：暴露 K3S 鉴权与开放接口

**新增/修改文件：**

- 新增 `server/apps/monitor/views/k3s_onboarding.py`
- 修改 `server/apps/monitor/urls.py`
- 新增 `server/apps/monitor/tests/test_k3s_onboarding_views.py`

**Step 1：先写接口失败测试**

覆盖四条路由：

- `POST /api/v1/monitor/api/k3s_onboarding/create_instance/`
- `POST /api/v1/monitor/api/k3s_onboarding/install_command/`
- `GET /api/v1/monitor/api/k3s_onboarding/verify/`
- `POST /api/v1/monitor/open_api/k3s_onboarding/render/`

断言：

- 前三条使用普通受保护 ViewSet，执行现有组织和实例操作权限校验。
- render 使用 `OpenAPIViewSet`，但必须通过 K3S token 校验。
- 未知字段、错误类型、跨租户实例和 K8S 实例被拒绝。
- render 返回 `text/yaml` 和剩余使用次数响应头。
- 只有 K3S 两个 ViewSet 被新增到 router，现有 `/open_api/infra` 保持不变。

**Step 2：实现两个 ViewSet**

- `K3SOnboardingViewSet`：create/install/verify。
- `K3SOnboardingOpenViewSet`：render。
- View 层只做请求校验、权限和响应封装，业务留在 K3SOnboarding 模块。

**Step 3：验证并提交**

```bash
cd server
uv run pytest apps/monitor/tests/test_k3s_onboarding_views.py \
  apps/monitor/tests/test_k3s_onboarding_service.py \
  apps/monitor/tests/test_api_boundary_validation.py -v --no-cov
git add apps/monitor/views/k3s_onboarding.py apps/monitor/urls.py \
  apps/monitor/tests/test_k3s_onboarding_views.py
git commit -m "feat: 暴露 K3S 独立接入接口"
```

## Task 6：新增 K3S 前端接入向导

**新增/修改文件：**

- 新增 `web/src/app/monitor/(pages)/integration/list/detail/configure/k3s/k3sConfiguration.tsx`
- 新增 `web/src/app/monitor/(pages)/integration/list/detail/configure/k3s/accessConfig.tsx`
- 新增 `web/src/app/monitor/(pages)/integration/list/detail/configure/k3s/collectorInstall.tsx`
- 新增 `web/src/app/monitor/(pages)/integration/list/detail/configure/k3s/commonIssuesDrawer.tsx`
- 修改 `web/src/app/monitor/(pages)/integration/list/detail/configure/page.tsx`
- 修改 `web/src/app/monitor/api/integration.ts`
- 修改 `web/src/app/monitor/types/integration.ts`
- 修改 `web/src/app/monitor/locales/zh.json`
- 修改 `web/src/app/monitor/locales/en.json`
- 新增 `web/scripts/k3s-monitoring-onboarding-test.ts`
- 修改 `web/package.json`

**Step 1：先写前端契约失败测试**

静态/逻辑测试断言：

- `collect_type === "k3s"` 只渲染 K3S 向导。
- K3S API 方法只调用 `/monitor/api/k3s_onboarding/*`。
- K3S 页面不导入 `./k8s/*` 或调用 `createK8sInstance/getK8sCommand/checkCollectStatus`。
- 表单没有 interval 字段。
- 安装命令展示不含 `-k`。
- 验证区分别显示 cluster/container/node 三段状态。
- K3S 文案使用独立 locale key。

运行并确认失败：

```bash
cd web
pnpm exec tsx scripts/k3s-monitoring-onboarding-test.ts
```

**Step 2：实现 API 类型和调用**

- 新增 `createK3sInstance`、`getK3sCommands`、`verifyK3sReporting`。
- 为三段验证响应定义明确 TypeScript 类型，不使用 `any`。
- K8S 现有 API 方法不改名、不改路径。

**Step 3：实现独立向导**

- 参考 K8S 三步交互，但 K3S 目录持有自己的状态和业务调用。
- 允许复用 Ant Design、CodeEditor、组织选择器等通用组件。
- 不复用 `IntegrationK8sConfigurationShell`；K3S 本地实现最小三步壳，避免以 K8S 命名的业务模块成为依赖。
- 安装页提供安装命令和折叠的有界卸载命令。
- 验证只有三段都成功才进入完成页。

**Step 4：增加配置页分派**

分派顺序明确为：

1. API template。
2. Flow。
3. K3S。
4. K8S。
5. 其他自动配置。

避免用 `!isK8s` 让 K3S 落入自动配置。

**Step 5：验证并提交**

```bash
cd web
pnpm exec tsx scripts/k3s-monitoring-onboarding-test.ts
pnpm exec eslint \
  'src/app/monitor/(pages)/integration/list/detail/configure/k3s/**/*.{ts,tsx}' \
  'src/app/monitor/(pages)/integration/list/detail/configure/page.tsx' \
  'src/app/monitor/api/integration.ts' \
  'src/app/monitor/types/integration.ts'
cd ..
git add \
  'web/src/app/monitor/(pages)/integration/list/detail/configure/k3s/k3sConfiguration.tsx' \
  'web/src/app/monitor/(pages)/integration/list/detail/configure/k3s/accessConfig.tsx' \
  'web/src/app/monitor/(pages)/integration/list/detail/configure/k3s/collectorInstall.tsx' \
  'web/src/app/monitor/(pages)/integration/list/detail/configure/k3s/commonIssuesDrawer.tsx' \
  'web/src/app/monitor/(pages)/integration/list/detail/configure/page.tsx' \
  web/src/app/monitor/api/integration.ts \
  web/src/app/monitor/types/integration.ts \
  web/src/app/monitor/locales/zh.json \
  web/src/app/monitor/locales/en.json \
  web/scripts/k3s-monitoring-onboarding-test.ts \
  web/package.json
git commit -m "feat: 新增 K3S 独立接入向导"
```

暂存前必须用 `git diff --cached --name-only` 排除 `web/src/app/monitor` 下与任务无关的用户改动；不能使用目录级暂存覆盖未知文件。

## Task 7：注册 K3S 对象配置和独立专业仪表盘

**新增/修改文件：**

- 新增 `web/src/app/monitor/hooks/integration/objects/k3s/cluster.tsx`
- 新增 `web/src/app/monitor/hooks/integration/objects/k3s/node.tsx`
- 新增 `web/src/app/monitor/hooks/integration/objects/k3s/pod.tsx`
- 修改 `web/src/app/monitor/hooks/integration/index.tsx`
- 新增 `web/src/app/monitor/dashboards/objects/k3s-cluster/`
- 新增 `web/src/app/monitor/dashboards/objects/k3s-node/`
- 新增 `web/src/app/monitor/dashboards/objects/k3s-pod/`
- 修改 `web/src/app/monitor/dashboards/registry.ts`
- 新增 `web/scripts/k3s-monitoring-dashboard-contract-test.ts`
- 修改 `web/package.json`

**Step 1：先写对象与查询失败测试**

断言：

- 配置键为 `K3SCluster/K3SNode/K3SPod`。
- `instance_type` 和 `collectTypes.K3S` 都为 `k3s`。
- registry 只新增：
  - `k3s-cluster -> K3SCluster`
  - `k3s-node -> K3SNode`
  - `k3s-pod -> K3SPod`
- K3S 目录没有导入 `k8s-*` 目录。
- 每条 PromQL 都显式包含 `instance_type="k3s"`。
- K3S 查询文件中不存在 `instance_type="k8s"`。
- K3S 仪表盘引用的 measurement 与清单 allowlist、插件 metrics.json 一致。

**Step 2：实现对象配置**

- 在 `useMonitorConfig` 中新增三个独立 config。
- 不改变现有 `Cluster/Node/Pod` 配置键或 K8S collect type。
- K3S 对象使用自己的 dashboard display 和 group IDs。

**Step 3：实现三个专业仪表盘**

- 可以复制 K8S 的布局和展示算法，但文件归 K3S 目录所有。
- 所有查询、route key、object name 和文案替换为 K3S。
- K3S Node 只能导入 K3S Cluster 的 parse/query 工具。
- 不为了减少重复而新增可切换 K8S/K3S 的运行时参数。

**Step 4：验证并提交**

```bash
cd web
pnpm exec tsx scripts/k3s-monitoring-dashboard-contract-test.ts
pnpm run test:k8s-cluster-filter
pnpm exec eslint \
  'src/app/monitor/hooks/integration/objects/k3s/**/*.{ts,tsx}' \
  'src/app/monitor/dashboards/objects/k3s-*/**/*.{ts,tsx}' \
  'src/app/monitor/hooks/integration/index.tsx' \
  'src/app/monitor/dashboards/registry.ts'
cd ..
git add \
  web/src/app/monitor/hooks/integration/objects/k3s \
  web/src/app/monitor/hooks/integration/index.tsx \
  web/src/app/monitor/dashboards/objects/k3s-cluster \
  web/src/app/monitor/dashboards/objects/k3s-node \
  web/src/app/monitor/dashboards/objects/k3s-pod \
  web/src/app/monitor/dashboards/registry.ts \
  web/scripts/k3s-monitoring-dashboard-contract-test.ts \
  web/package.json
git commit -m "feat: 新增 K3S 专业监控仪表盘"
```

## Task 8：验证 K3S 衍生实例发现

**新增/修改文件：**

- 新增 `server/apps/monitor/tests/test_k3s_instance_discovery.py`
- 仅在测试证明通用同步模块缺少必要能力时，最小修改 `server/apps/monitor/services/monitor_instance.py` 或现有同步模块

**Step 1：先用现有通用同步接口写失败测试**

模拟 VictoriaMetrics 返回：

- `kube_node_info{instance_type="k3s",instance_id="c1",node="n1"}`
- `kube_pod_info{instance_type="k3s",instance_id="c1",pod="p1"}`
- 同时混入 `instance_type="k8s"` 的同名节点和 Pod

断言：

- 只创建 `K3SNode ('c1','n1')` 和 `K3SPod ('c1','p1')`。
- 不把 K8S 序列同步进 K3S 对象。
- 重复同步幂等。
- K3SCluster 被删除或不存在时不创建孤儿衍生实例。

**Step 2：优先只补测试**

如果现有通用实例同步已经根据对象 default metric 和唯一键正确工作，不修改生产代码。只有测试证明存在 K3S 所需的通用缺口时，才在原 seam 内做最小修复，且同时运行 K8S 同步回归。

**Step 3：验证并提交**

```bash
cd server
uv run pytest apps/monitor/tests/test_k3s_instance_discovery.py \
  apps/monitor/tests/test_sync_instance_service.py \
  apps/monitor/tests/test_monitor_instance_projection.py -v --no-cov
git add apps/monitor/tests/test_k3s_instance_discovery.py \
  apps/monitor/services/monitor_instance.py \
  apps/monitor/tasks/services/sync_instance.py
git commit -m "test: 固化 K3S 实例发现隔离"
```

## Task 9：增加跨层一致性和零回归门禁

**新增文件：**

- `server/apps/monitor/tests/test_k3s_vertical_contract.py`
- `web/scripts/k3s-monitoring-isolation-test.ts`

**修改文件：**

- `web/package.json`

**Step 1：实现后端/清单跨层契约测试**

自动抽取并比较：

- K3S `metrics.json` 查询中的 measurement。
- K3S vmagent cAdvisor/KSM allowlist。
- K3S 节点 Telegraf inputs 能产生的 measurement。
- K3S 前端仪表盘查询 measurement。

规则：

- 仪表盘 measurement 必须都能由 K3S 清单产生。
- 插件核心 measurement 必须都能由 K3S 清单产生。
- 允许采集但尚未展示的 measurement 使用显式集合，不使用模糊跳过。
- 所有层的身份标签统一为 `k3s`。

**Step 2：实现隔离扫描**

测试限定业务目录，断言：

- K3S 后端不调用 `InfraService` 或 `ManualCollectService`。
- K3S renderer 不调用 `kubernetes.sh`。
- K3S 前端不导入 K8S onboarding/dashboard。
- K3S 清单不声明任何 K8S 专属资源。
- K8S 现有关键文件相对实施起点没有业务改写；共享注册点只增加 K3S 条目。

**Step 3：运行定向全链路回归**

```bash
cd server
uv run pytest \
  apps/monitor/tests/test_k3s_plugin_contract.py \
  apps/monitor/tests/test_k3s_onboarding_service.py \
  apps/monitor/tests/test_k3s_onboarding_views.py \
  apps/monitor/tests/test_k3s_instance_discovery.py \
  apps/monitor/tests/test_k3s_vertical_contract.py \
  apps/monitor/tests/test_infra_tls.py \
  apps/monitor/tests/test_sync_instance_service.py \
  ../agents/webhookd/infra/tests/test_k3s_manifest_contract.py \
  ../agents/webhookd/infra/tests/test_k3s_render.py -v --no-cov

cd ../web
pnpm exec tsx scripts/k3s-monitoring-onboarding-test.ts
pnpm exec tsx scripts/k3s-monitoring-dashboard-contract-test.ts
pnpm exec tsx scripts/k3s-monitoring-isolation-test.ts
pnpm run test:k8s-cluster-filter
```

**Step 4：提交**

```bash
git add server/apps/monitor/tests/test_k3s_vertical_contract.py \
  web/scripts/k3s-monitoring-isolation-test.ts web/package.json
git commit -m "test: 增加 K3S 纵向链路隔离门禁"
```

## Task 10：执行真实 K3S 发布验证

**新增文件：**

- `agents/webhookd/infra/tests/k3s-e2e/README.md`
- `agents/webhookd/infra/tests/k3s-e2e/verify.sh`
- `docs/changelog/k3s-monitoring.md`

**Step 1：冻结版本和镜像**

- 记录发布时官方仍维护的最旧 minor 最新 patch。
- 记录发布时 `stable` channel 的完整版本。
- 列出清单中每个镜像的 tag、digest、amd64 digest 和 arm64 digest。

`verify.sh image-platforms` 从 K3S 清单解析去重后的镜像并逐个执行 `docker buildx imagetools inspect`，验证：

```bash
agents/webhookd/infra/tests/k3s-e2e/verify.sh image-platforms
```

只有所有镜像同时包含 `linux/amd64` 和 `linux/arm64` 才进入双架构验证。

**Step 2：执行环境矩阵**

按规格测试：

- amd64 单节点。
- amd64 多节点。
- arm64 单节点。
- arm64 多节点。
- 最旧维护 minor 和 stable 完整版本。
- server+agent、agentless server 场景。

**Step 3：执行三段数据验证**

每个环境确认：

- `kube_node_info` 带 `instance_type=k3s` 和正确集群身份。
- `container_cpu_usage_seconds_total` 能覆盖业务 Pod。
- `system_load1` 能覆盖运行 agent 的节点。
- K3SCluster/K3SNode/K3SPod 实例发现正确。
- 三个专业仪表盘无缺失 measurement。

**Step 4：演练生命周期**

- 连续 apply 两次，确认幂等。
- 升级 collector 版本并确认配置滚动生效。
- 回滚到上一版。
- 使用有界卸载命令删除 K3S 清单。
- 验证同集群中的 K8S、CMDB 和用户自建 KSM 资源均未变化。

**Step 5：记录结果**

- `verify.sh` 只读取和验证 K3S 标签/资源，不执行宽泛删除。
- README 记录命令、预期、实际版本和失败诊断。
- changelog 写明独立链路、支持白名单、权限风险和卸载方式。

**Step 6：提交**

```bash
git add agents/webhookd/infra/tests/k3s-e2e docs/changelog/k3s-monitoring.md
git commit -m "docs: 记录 K3S 监控发布验证"
```

## 最终验证

### 自动化

```bash
cd server
uv run pytest apps/monitor/tests/test_k3s_*.py -v --no-cov
uv run pytest apps/monitor/tests/test_infra_tls.py \
  apps/monitor/tests/test_sync_instance_service.py \
  apps/monitor/tests/test_management_migrate.py -v --no-cov
uv run pytest ../agents/webhookd/infra/tests/test_k3s_*.py -v --no-cov

cd ../web
pnpm exec tsx scripts/k3s-monitoring-onboarding-test.ts
pnpm exec tsx scripts/k3s-monitoring-dashboard-contract-test.ts
pnpm exec tsx scripts/k3s-monitoring-isolation-test.ts
pnpm run test:k8s-cluster-filter
pnpm type-check
```

### 人工检查

- K3S 卡片、向导、三段验证和仪表盘均使用 K3S 文案。
- 安装命令不含 TLS 绕过参数。
- K3S 清单只包含 `bk-lite-k3s-*` 资源。
- K8S 原入口、安装命令、清单、对象和仪表盘行为未变化。
- 工作区无凭据、临时 kubeconfig、渲染后 Secret 或集群输出被提交。

### 完成判定

- 自动化定向测试全部通过。
- 真实 K3S 矩阵通过并形成完整版本白名单。
- 安装、重复安装、升级、回滚、卸载均有证据。
- K3S 在没有 K8S/CMDB collector 的集群中可独立上报并展示。
- K3S 生命周期操作不修改任何 K8S、CMDB 或用户资源。
- `git diff` 只包含本计划列出的文件，或有逐项说明的必要偏差。
