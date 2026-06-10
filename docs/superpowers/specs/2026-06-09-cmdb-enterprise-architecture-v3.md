# CMDB 商业版架构规范 v3（cmdb_enterprise overlay app + 注册表 IoC）

- 日期：2026-06-09
- 状态：已落地（取代 v2 嵌套 `apps/cmdb/enterprise/` 方案）
- 设计依据：`docs/superpowers/specs/2026-06-09-cmdb-enterprise-sibling-app-design.md`
- 实施计划：`docs/superpowers/plans/2026-06-09-cmdb-enterprise-sibling-app.md`

## 一句话

CMDB 商业版是一个**与 `apps/cmdb` 同级的独立 overlay app** `apps/cmdb_enterprise`，被 `.gitignore` 忽略（单独交付），目录存在即随 Django app 自动加载。社区 `cmdb` 通过**扩展注册表（IoC）**与它解耦到「互不 import」：社区定义契约与调用点，商业 app 在 `AppConfig.ready()` 把实现注册进来。

## 为什么是这套（取代 v2）

v2 把商业代码嵌套在 `apps/cmdb/enterprise/`，社区靠「guarded 导入 + load_provider 路径」耦合。随商业功能增多（附件/图片、custom_reporting），社区版**实际持有并维护了商业模型的完整定义再被覆盖**（双模型），并散落出大量 guarded 导入与裸惰性导入——「容易把社区模型搞乱」。v3 用独立 app + 注册表彻底消除：社区零企业模型、零 guarded 企业导入、零双模型。

先例：`config/components/app.py` 早有同级商业 app `license_mgmt`（目录存在即加载）。

## 结构

```
apps/cmdb/                      # 社区版：契约 + 调用点，零企业知识
  extensions/registry.py        #   IoC 注册表：register(name, impl) / get(name, default)
  model_ops/extensions.py       #   ModelEnterpriseExtension 默认空契约 + get_*()→registry.get("model_ops")
  instance_ops/extensions.py    #   InstanceEnterpriseExtension（"instance_ops"）
  collect/extensions.py         #   CollectEnterpriseExtension（"collect"）
  custom_reporting/extensions.py#   CustomReportingExtension（"custom_reporting"）

apps/cmdb_enterprise/           # 商业版 overlay（.gitignore 忽略，单独交付）
  apps.py                       #   AppConfig.ready() → import registry_hooks
  registry_hooks.py             #   registry.register(各域实现) + 运行时配置（MinIO 桶）
  config.py                     #   CELERY_BEAT_SCHEDULE（celery 组件按 app 自动合并）
  tasks/                        #   @shared_task（Celery autodiscover）
  urls.py                       #   接口（url 自动发现 → api/v1/cmdb_enterprise/）
  models/ + migrations/         #   自有表（app_label=cmdb_enterprise，自有迁移）
  instance_ops/ model_ops/ collect/ custom_reporting/   # 各域实现
  tests/                        #   商业测试（随 app 走）
```

## 集成机制（IoC）

- 社区各域 `extensions.py` 持有**默认空契约**与 `get_*_enterprise_extension()`，后者 = `registry.get("<slot>", _DEFAULT)`。社区调用点照常调契约方法。
- 商业 app `cmdb_enterprise/registry_hooks.py`（在 `AppConfig.ready()` 执行）把实现注册进对应槽位：`registry.register("model_ops", ...)` 等。
- **社区代码不出现任何 `apps.cmdb.enterprise` / `apps.cmdb_enterprise` 路径**——只 `registry.get`。缺 overlay 时返回默认空契约（add-only 回退）。

## 各资源归属（Django/Celery 自动发现，无社区接缝）

| 资源 | 归属 | 机制 |
|---|---|---|
| 模型 + 迁移 | cmdb_enterprise app | app 自带 migrations，`app_label=cmdb_enterprise`，社区零企业模型 |
| 异步任务 | cmdb_enterprise/tasks | Celery `autodiscover_tasks()` |
| beat 调度 | cmdb_enterprise/config.py | `config/components/celery.py` 按 INSTALLED_APPS 合并 |
| 接口 URL | cmdb_enterprise/urls.py | url 自动发现 → `api/v1/cmdb_enterprise/` |
| MinIO 桶等运行时配置 | `registry_hooks` 在 ready() 注册 | 不改社区 `config/components/*` |
| 行为钩子 | 注册表 | 社区 `registry.get` |

## 加载与部署（重要）

- `apps/` 目录扫描自动注册子目录为 app；但本仓 `server/.env` 用 **`INSTALL_APPS` 白名单**（非空），因此 **`cmdb_enterprise` 必须显式列入 `INSTALL_APPS`** 才会加载。部署商业版时打包流程须保证这一点（或令 `INSTALL_APPS` 为空＝全装）。
- 字母序 `cmdb_enterprise` 在 `cmdb` 之后 → 其 `ready()` 在 cmdb 加载后执行，注册时机正确；行为钩子在请求时读注册表（已就绪）。

## 新增商业需求的接入流程

1. 判断能力域：`model_ops` / `instance_ops` / `collect` / `custom_reporting`，或平台场景（持久化/任务/调度/配置）。
2. 行为：契约已够 → 在 `cmdb_enterprise/<domain>/` 写实现，在 `registry_hooks` 注册；契约不足 → 先在社区 `apps/cmdb/<domain>/extensions.py` 给契约加方法（默认 no-op），再实现注册。
3. 持久化：模型放 `cmdb_enterprise/<domain>/models.py`（`app_label=cmdb_enterprise`），迁移落 `cmdb_enterprise/migrations/`。**社区不放任何商业模型/迁移。**
4. 任务/调度/URL：放 app 自有 `tasks/`、`config.py`、`urls.py`，靠自动发现。
5. 不得在社区 `apps/cmdb` 里新增任何 `enterprise`/`cmdb_enterprise` 路径引用。

## 不变式与验收

- **删除 `apps/cmdb_enterprise`（或不部署）→ 社区 CMDB 行为正常**，无附件/custom_reporting/达梦能力且无报错（注册表空 → 默认契约）。
- 社区 `grep -rn "cmdb_enterprise\|cmdb.enterprise" apps/cmdb --include=*.py`（排除 tests）→ 无匹配。
- 已验证（2026-06-09）：
  - 有 overlay：`pytest apps/cmdb apps/cmdb_enterprise`（排除 bdd/e2e）→ **1210 passed, 3 skipped, 0 failed**。
  - 无 overlay（移除 dir + 从 INSTALL_APPS 去除）：`pytest apps/cmdb` → **1186 passed, 3 skipped, 0 failed**；`makemigrations cmdb --check` 干净；实例扩展回退为默认 `InstanceEnterpriseExtension`。

## 边界 / 后续

- **前端**：商业前端 overlay（`web/enterprise` 已被 gitignore）是独立话题，本次未动；附件前端仍在社区 `web/`，接口仍走 `api/v1/cmdb/instance/...`（端点是社区瘦 viewset 经注册表委托，未迁 URL 命名空间）。
- **custom_reporting**：本仓只含其 schema（迁入 overlay）+ 社区契约委托；行为实现（`CustomReportingModelService`）由商业 overlay 仓单独交付并 `registry.register("custom_reporting", ...)`。
- **历史孤儿表**：迁移按「无生产数据、重建表」执行，旧社区表（`cmdb_cmdbfileobject`、`cmdb_custom_reporting_*`）成为闲置孤儿，可后续清理。
