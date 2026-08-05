# CMDB 配置采集凭据协议指引实施计划

> 依据：`specs/changes/cmdb-collection-credential-guidance/spec.md`

**目标：** 通过“凭据 `?`”统一说明插件真实协议，并修复 InfluxDB、云平台与私有平台当前表单和采集下发不一致的问题。

**架构：** 简单插件在采集对象目录声明语义化凭据元数据，前端纯函数解析为帮助定义；复杂插件由专用任务组件显式配置表单和帮助。`CredentialPoolEditor` 只渲染定义，不认识插件。后端 NodeParams、Stargazer 采集器和任务结果共同保证界面说明与真实连接契约一致。

**实施原则：**

- 每项先补失败测试，再做最小实现，再运行定向回归。
- `task_type` 只作为执行分类，不用于猜测协议或凭据。
- 保留现有 `credential` 数据结构和密钥脱敏语义，不新增 migration。
- 只改本变更涉及的采集对象，保留工作区其他未提交内容。
- 每个提交覆盖一个可独立验证的纵向增量，提交信息使用中文。

## Task 1：固化简单插件凭据元数据契约

**修改文件：**

- `server/apps/cmdb/constants/constants.py`
- `server/apps/cmdb/tests/test_collect_object_tree.py`
- `web/src/app/cmdb/types/autoDiscovery.ts`

**新增文件：**

- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialHelp.ts`
- `web/scripts/cmdb-credential-help-test.ts`

**步骤：**

1. 在后端对象树测试中先断言 MySQL、PostgreSQL、MSSQL 和典型 SSH/JOB 插件包含 `credential_protocol`、`credential_kind`、`credential_default_port`，并断言 `task_type` 与协议可不同。
2. 给简单对象补语义元数据；只声明事实，不放用户密钥或前端 JSX。
3. 扩展 `TreeNode`、`ModelItem` 类型。
4. 新增纯函数 `resolveCredentialHelp()`：
   - 优先使用显式复杂对象定义；
   - 否则按 `credential_protocol` 选择简单模板；
   - 应用可选 `credential_tip_key` 覆盖；
   - 元数据缺失时返回明确兜底，不根据 `task_type` 推断。
5. 用脚本测试覆盖 SSH、三种数据库协议、插件覆盖、无元数据兜底和中英文键完整性。

**验证：**

```bash
cd server
uv run pytest -q -o addopts='' apps/cmdb/tests/test_collect_object_tree.py
cd ../web
pnpm exec tsx scripts/cmdb-credential-help-test.ts
```

## Task 2：统一凭据帮助 Popover 和编辑器实现

**修改文件：**

- `web/src/app/cmdb/components/cmdb-credential-pool-editor/index.tsx`
- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialPoolEditor.tsx`
- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/index.module.scss`
- `web/src/app/cmdb/locales/zh.json`
- `web/src/app/cmdb/locales/en.json`
- `web/src/stories/cmdb-family.stories.tsx`
- 各专业采集任务组件中的 `credentialHelp` 传参
- `web/package.json`

**步骤：**

1. 先扩展前端测试，断言：
   - 业务页面与 Storybook 引用同一个共享编辑器；
   - 帮助入口为 click `Popover`，不是 hover-only `Tooltip`；
   - 简单定义渲染固定四行；
   - 多凭据表单包含原有策略说明，单凭据表单不显示；
   - 缺少定义显示兜底。
2. 以共享 `cmdb-credential-pool-editor` 为唯一实现，把专业采集目录下的本地文件替换为兼容重导出；现有业务 import 路径保持不变，但运行时与 Storybook 使用同一个组件。
3. 给编辑器增加 `credentialHelp` 属性。编辑器只展示帮助定义，不读取 `model_id`。
4. 把标题旁 `Tooltip` 改为 click `Popover`，补 `aria-label`、键盘触发和合理宽度；保留删除按钮等无关 Tooltip。
5. 将标题、四行字段、兜底、最小权限、多凭据策略等文案加入 CMDB 中英文语言文件。
6. Storybook 增加 SSH、MySQL、SNMP、InfluxDB 和云平台状态，覆盖 Popover 展开态及窄宽度。

**验证：**

```bash
cd web
pnpm exec tsx scripts/cmdb-credential-help-test.ts
pnpm lint --quiet
pnpm build-storybook
```

## Task 3：接入简单协议与 SNMP 专用说明

**修改文件：**

- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/hostTask.tsx`
- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/sqlTask.tsx`
- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/snmpTask.tsx`
- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/credentialHelp.ts`
- `web/src/app/cmdb/locales/zh.json`
- `web/src/app/cmdb/locales/en.json`
- `web/scripts/cmdb-credential-help-test.ts`

**步骤：**

1. 让 HostTask 和 SQLTask 从当前 `modelItem` 解析帮助，而不是从组件名或 `task_type` 决定提示。
2. 验证 Redis、MongoDB、中间件等 JOB 插件显示“SSH / 目标主机操作系统账户”，MySQL/PostgreSQL/MSSQL 显示各自数据库协议和账户。
3. 为 SNMP 提供专用定义，一次说明 V2/V2C、V3 `authNoPriv`、V3 `authPriv` 及 UDP 161。
4. 保持现有 SNMP 字段联动，不增加字段级帮助图标。

**验证：**

```bash
cd web
pnpm exec tsx scripts/cmdb-credential-help-test.ts
pnpm lint --quiet
```

## Task 4：修复 InfluxDB 端到端连接契约

**新增文件：**

- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/influxdbTask.tsx`
- `server/apps/cmdb/node_configs/protocol/influxdb.py`
- `server/apps/cmdb/tests/test_influxdb_node_params.py`
- `agents/stargazer/tests/test_influxdb_info.py`

**修改文件：**

- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/page.tsx`
- `web/src/app/cmdb/components/cmdb-credential-pool-editor/index.tsx`
- `web/src/app/cmdb/types/autoDiscovery.ts`
- `web/src/app/cmdb/locales/zh.json`
- `web/src/app/cmdb/locales/en.json`
- `server/apps/cmdb/node_configs/protocol/__init__.py`
- `server/apps/cmdb/serializers/collect_serializer.py`
- `server/apps/cmdb/constants/constants.py`
- `server/apps/cmdb/tasks/celery_tasks.py`
- `server/apps/cmdb/tests/test_influxdb_collection_pure.py`
- `server/apps/cmdb/tests/test_collect_dispatch_service.py`
- `agents/stargazer/plugins/inputs/influxdb/influxdb_info.py`

**步骤：**

1. 先写 Stargazer 采集器测试：
   - v2 无 Token 时只请求 `/health`，返回基础信息且成功；
   - v2 有有效 Token 时请求 `/api/v2/config` 并返回完整配置；
   - 有 Token 时 401/403 返回基础结果和结构化采集告警，不泄露 Token；
   - v1 走 `/ping`；
   - `verify_tls=true/false` 分别真实传给 `requests`；
   - HTTP/HTTPS 与端口正确组成地址。
2. 定义采集结果告警契约，例如在插件结果中携带受控的 `cmdb_collect_warning`。CMDB 格式化和保存链路把“有可用数据 + 有采集告警”判为 `PARTIAL_SUCCESS`，将脱敏原因写入摘要；“未提供 Token”不产生告警。
3. 新增 `InfluxdbNodeParams`，下发 `host`、`port`、`ssl`、`verify_tls`、可选 Token 和超时；Token 通过环境变量引用传递。
4. 在 serializer 中按 `model_id=influxdb` 校验：
   - `scheme` 仅为 HTTP/HTTPS；
   - 端口合法；
   - `verify_tls` 为布尔值；
   - Token 可空。
5. 新增专用前端表单并在页面按 `model_id` 优先分派，避免落入 `protocol -> SQLTask`。
6. 表单显示 HTTP/HTTPS、端口 8086、证书校验和可选 Operator Token；关闭证书校验时显示风险提示；帮助说明基础/完整采集边界和 Operator Token 权限风险。
7. 覆盖创建、编辑掩码、复制清空、无 Token、有 Token和无效 Token的端到端参数测试。

**验证：**

```bash
cd server
uv run pytest -q -o addopts='' \
  apps/cmdb/tests/test_influxdb_collection_pure.py \
  apps/cmdb/tests/test_influxdb_node_params.py \
  apps/cmdb/tests/test_collect_dispatch_service.py
cd ../agents/stargazer
uv run pytest -q tests/test_influxdb_info.py
cd ../../web
pnpm exec tsx scripts/cmdb-credential-help-test.ts
pnpm lint --quiet
```

## Task 5：按提供商修正公有云凭据

**新增文件：**

- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/cloudCredentialConfig.ts`
- `web/scripts/cmdb-cloud-credential-contract-test.ts`

**修改文件：**

- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/cloudTask.tsx`
- `web/src/app/cmdb/components/cmdb-credential-pool-editor/index.tsx`
- `web/src/app/cmdb/types/autoDiscovery.ts`
- `web/src/app/cmdb/locales/zh.json`
- `web/src/app/cmdb/locales/en.json`
- `server/apps/cmdb/serializers/collect_serializer.py`
- `server/apps/cmdb/node_configs/cloud/_cloud_base.py`
- `server/apps/cmdb/tests/test_remaining_collect_objects_node_params.py`
- `server/apps/cmdb/tests/test_cloud_region_service.py`
- `web/package.json`

**步骤：**

1. 建立按 `model_id` 的公有云配置表：
   - 阿里云：AccessKey ID / AccessKey Secret / Region；
   - 腾讯云：SecretId / SecretKey / Region；
   - 华为云：AK / SK / Project ID / Region。
2. 让 CloudTask 的标签、字段、必填校验、Region 查询参数、任务提交、编辑回填和复制清空都由配置表驱动。
3. 保持后端存储的兼容键，必要时只在提交边界映射提供商字段，不把 UI 标签直接当数据键。
4. 后端为华为云强制校验 Project ID，并验证 Region 查询与 NodeParams 下发都携带该字段。
5. 公有云 Popover 说明 SDK/API 凭据和最小只读权限建议。

**验证：**

```bash
cd server
uv run pytest -q -o addopts='' \
  apps/cmdb/tests/test_remaining_collect_objects_node_params.py \
  apps/cmdb/tests/test_cloud_region_service.py
cd ../web
pnpm exec tsx scripts/cmdb-cloud-credential-contract-test.ts
pnpm lint --quiet
```

## Task 6：修复 FusionInsight 与 OceanStor 平台账户契约

**新增文件：**

- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/platformApiTask.tsx`
- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/platformApiCredentialConfig.ts`
- `server/apps/cmdb/node_configs/cloud/oceanstor.py`
- `server/apps/cmdb/tests/test_platform_api_node_params.py`
- `web/scripts/cmdb-platform-api-credential-test.ts`

**修改文件：**

- `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/page.tsx`
- `web/src/app/cmdb/components/cmdb-credential-pool-editor/index.tsx`
- `web/src/app/cmdb/locales/zh.json`
- `web/src/app/cmdb/locales/en.json`
- `server/apps/cmdb/node_configs/cloud/fusioninsight.py`
- `server/apps/cmdb/node_configs/cloud/__init__.py`
- `server/apps/cmdb/serializers/collect_serializer.py`
- `server/apps/cmdb/constants/constants.py`
- `server/apps/cmdb/tests/test_fusioninsight_collection_service.py`
- `server/apps/cmdb/tests/test_storage_collection_service.py`
- `agents/stargazer/tests/test_fusioninsight_info.py`
- `agents/stargazer/tests/test_oceanstor_info.py`

**步骤：**

1. 先用 NodeParams 测试证明当前 FusionInsight 错误映射为 AK/SK、OceanStor 无注册，再锁定期望入参。
2. 增加两个显式平台配置：
   - FusionInsight：HTTPS 平台地址、用户名、密码、证书校验；
   - OceanStor：HTTPS DeviceManager 地址、用户名、密码、端口 8088、证书校验。
3. 在页面按 `model_id` 优先分派 `platformApiTask`，不再通过 `cloud -> CloudTask`。
4. 重写 FusionInsight NodeParams，把 `username/password/host/scheme/verify_tls` 与采集器对齐；新增 OceanStor NodeParams。
5. 让两个 Stargazer 采集器真实尊重 TLS 校验开关；默认开启。保留现有会话登录、分页和登出行为。
6. 更新对象树标签和 `encrypted_fields`，移除误导性的 SDK/AK/SK 语义。
7. 测试凭据脱敏、编辑回填、复制清空、登录失败、证书校验和 NodeParams 注册。

**验证：**

```bash
cd server
uv run pytest -q -o addopts='' \
  apps/cmdb/tests/test_platform_api_node_params.py \
  apps/cmdb/tests/test_fusioninsight_collection_service.py \
  apps/cmdb/tests/test_storage_collection_service.py
cd ../agents/stargazer
uv run pytest -q tests/test_fusioninsight_info.py tests/test_oceanstor_info.py
cd ../../web
pnpm exec tsx scripts/cmdb-platform-api-credential-test.ts
pnpm lint --quiet
```

## Task 7：整体验收与回归

**步骤：**

1. 运行 CMDB 对象树、序列化、NodeParams、任务分派、采集状态和三类复杂插件的全部定向测试。
2. 运行前端三组契约脚本、类型检查和 Storybook 构建。
3. 在 Storybook 或本地页面人工检查：
   - click、外部关闭、Enter/Space、Esc；
   - 中英文；
   - 700px 抽屉和窄屏下不溢出；
   - SSH/MySQL/SNMP/InfluxDB/五类云平台；
   - 新建、编辑、复制；
   - 密钥不回显。
4. 用受控测试服务验证 InfluxDB 无 Token、有效 Token、无效 Token三种结果，并确认日志和摘要中没有 Token。
5. 检查 `git diff --check` 和工作区状态，确保未带入无关改动。

**完整验证命令：**

```bash
cd server
uv run pytest -q -o addopts='' \
  apps/cmdb/tests/test_collect_object_tree.py \
  apps/cmdb/tests/test_influxdb_collection_pure.py \
  apps/cmdb/tests/test_influxdb_node_params.py \
  apps/cmdb/tests/test_platform_api_node_params.py \
  apps/cmdb/tests/test_collect_dispatch_service.py \
  apps/cmdb/tests/test_fusioninsight_collection_service.py \
  apps/cmdb/tests/test_storage_collection_service.py
cd ../agents/stargazer
uv run pytest -q \
  tests/test_influxdb_info.py \
  tests/test_fusioninsight_info.py \
  tests/test_oceanstor_info.py
cd ../../web
pnpm exec tsx scripts/cmdb-credential-help-test.ts
pnpm exec tsx scripts/cmdb-cloud-credential-contract-test.ts
pnpm exec tsx scripts/cmdb-platform-api-credential-test.ts
pnpm type-check
pnpm build-storybook
cd ..
git diff --check
```

## 建议提交顺序

1. `feat: 增加采集凭据协议元数据`
2. `feat: 统一采集凭据帮助交互`
3. `feat: 增加简单协议与 SNMP 凭据说明`
4. `fix: 对齐 InfluxDB 采集凭据契约`
5. `fix: 区分公有云提供商凭据`
6. `fix: 对齐平台 API 采集凭据`
7. `test: 补充采集凭据端到端回归`
