# 七个平台凭据设计与采集测试记录

日期：2026-09-24。对应设计：`specs/changes/cmdb-seven-platform-credentials/spec.md`。

## 当前结论

七个平台的连接参数、凭据下发和异步采集调用已在代码中接通。此前页面/采集器缺口属于字段消费与执行契约不一致，不是缺少资源模型。本地测试覆盖实际认证请求、资源查询和非空结构化采集结果；尚未进行真实平台验收。

## 新鲜验证

| 范围 | 结果 | 证明范围 |
| --- | --- | --- |
| 前端配置采集组件 | 472/473 首轮通过；超时的主机选择文件单独重跑 6/6 通过 | 112 个认证入口的实际页面创建/编辑参数，生成 224 组手动/引用凭据请求；首轮一项并发超时，非断言失败 |
| 后端凭据及页面回放 | 508 通过 | 页面生成的 224 组请求，真实序列化、加密保存、编辑保留、凭据解析和配置下发；七个平台参数正反例；原 credential_version 回归 |
| 七个平台新增链路测试 | 56 通过 | 七平台 × 两种下发键名，实际 HTTP 接纳、请求规范化、YAML、执行器、认证、资源查询、非空资源 ID；401、403、TLS 开关、地址解析 |
| 七个平台原有采集测试 | 61 通过 | 既有字段映射、平台对象与关联所需数据、失败状态 |
| 运行时/预检/云凭据链路 | 60 通过 | 端口覆盖、HTTP 路径保留、原有云凭据传递 |
| 前端静态检查 | 相关四文件 ESLint、平台凭据脚本、`pnpm type-check` 通过 | 参数类型与现有组件契约 |

模拟网络仅替换 `requests.request/post`，使用测试账号和预设厂商响应。系统凭据 RPC 在后端测试中替换为内存凭据；没有使用真实密钥，没有访问真实平台。ManageOne 使用真实 CMP 驱动，七平台使用真实 CollectionService 和 YAML 解析。

## 复现

从仓库根目录，前端先导出当前采集入口树，再生成页面请求。已有导出说明见 `docs/cmdb-collection-page-credential-audit-2026-09-24.md`。本次临时文件为 `/tmp/cmdb-current-tree-final.json` 和 `/tmp/cmdb-page-payloads.json`，只含合成测试数据。

后端（`server/`）：

```bash
CMDB_PAGE_PAYLOADS=/tmp/cmdb-page-payloads.json DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true UV_CACHE_DIR=/tmp/bklite-uv-cache uv run --no-sync pytest -c pytest.ini apps/cmdb/tests/e2e/test_credential_page_payloads.py ../enterprise/server/apps/cmdb_enterprise/tests/test_seven_platform_connections.py apps/cmdb/tests/test_platform_api_task_serializer.py apps/cmdb/tests/test_collect_credential_metadata_serializer.py --no-cov --nomigrations -o addopts='' -q
```

采集端（`agents/stargazer/`）：

```bash
PYTHONPATH=.:../../enterprise/agents/stargazer .venv/bin/python -m pytest ../../enterprise/agents/stargazer/enterprise/tests/test_seven_platform_connections.py -q
PYTHONPATH=.:../../enterprise/agents/stargazer .venv/bin/python -m pytest ../../enterprise/agents/stargazer/enterprise/tests/test_{openstack*,smartx*,manageone*,fusioncompute*,nutanix*,inspurincloudrail*,azure*}.py -q
PYTHONPATH=. .venv/bin/python -m pytest tests/test_preflight.py tests/test_collection_plugins.py tests/test_cloud_credential_delivery_chain.py -q
```

以上采集测试分别执行。既有企业测试会修改 `sys.path`，混合运行可能把企业 `tasks` 包当成社区 `tasks` 包；本次曾复现导入失败，独立执行均通过。后端采用 `--nomigrations`，避开仓库既有 alerts 迁移基线问题。

## 真机验收还需要

已使用用户附件中的认证对 `localhost:3000/api/proxy/cmdb/api/collect` 做只读查询，返回成功。当前账号可见 10 个任务（nginx、network、k8s_cluster、vmware_vc、qcloud、aliyun_account），没有本次七个平台的任务。未修改现有任务，未触发真实采集。

每个平台提供实例/任务名称、平台版本、可连接的接入点、系统凭据名称或 ID，以及预期可见的一个资源标识；不要在聊天中提供密码。构建并部署包含社区与企业代码的 Server/Stargazer 后，对手动和引用模式分别验证：认证成功、实际读取资源、资源标识和数量符合范围、最终 CMDB 入库及任务状态正确。

真实环境未提供，所以上述真机验收状态仍为待验证，不能把模拟通过标为七个平台实采成功。
