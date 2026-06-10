# CMDB 商业版独立 App 重构设计（cmdb_enterprise）

- 日期：2026-06-09
- 状态：已确认，待写实施计划
- 取代：`apps/cmdb/enterprise/` 嵌套式分层（v2 规范）；本设计为 v3 架构方向

## Context（为什么重构）

CMDB 商业版能力当前**嵌套**在 `server/apps/cmdb/enterprise/` 内，社区版通过「guarded 导入 + load_provider facade」与之耦合。随着商业功能增多，这套方案的代价在真实累积，且伤到了社区版的核心（模型层）：

- **模型污染（核心痛点）**：`custom_reporting` 把 6 个模型的**完整定义**放进社区 `apps/cmdb/models/custom_reporting.py` 作为「fallback」，再被企业版**覆盖**；`models/__init__.py` 里有一段 guarded `apps.cmdb.enterprise.models` 导入 + 社区 fallback 的**双模型**逻辑。社区版实打实地包含并维护着商业模型——「容易把社区模型搞乱」。
- **接缝蔓延**：`tasks/__init__.py`、`config.py`、`apps.py`、`urls.py` 四处 guarded 接缝 + 三个域的 `extensions.py` load_provider；custom_reporting 还在 `views/`、`serializers/`、3 个 service、`services/model.py` 的 **7 个方法**里散落导入（部分**无 try/except 守卫**）。
- **迁移混放**：`0024_cmdbfileobject.py`、`0024_custom_reporting.py` 等商业表迁移落在社区 `apps/cmdb/migrations/`。

**已有先例**：本仓库 `config/components/app.py:91-100` 已有「同级商业 app」模式——`license_mgmt`：目录存在即加载、挂自己的中间件。商业版抽成同级 app 在本仓库是被验证过的做法。

**目标**：把商业版变成一个**自包含、可插拔、自带表/任务/路由/迁移的独立 app**，社区 cmdb 通过**注册表**与它解耦到「互不 import」，从根上消除模型污染与接缝蔓延。

## 已确认决策

1. **交付方式**：独立同级 app `server/apps/cmdb_enterprise/`，被 `.gitignore` 忽略（overlay，对齐 license_mgmt）；目录存在即由现有 `apps/` 扫描自动加载，不在则社区版正常运行。
2. **集成机制**：注册表 / 钩子（IoC）。社区定义扩展点接口与默认空契约；商业 app 在 `AppConfig.ready()` 注册实现。社区代码**不出现任何 enterprise / cmdb_enterprise 字样**。
3. **范围**：全量迁移 —— 达梦 + 附件/图片 + custom_reporting 三个现有商业功能全部迁入新 app，删除社区侧对应模型与 0024 迁移，由新 app 自有迁移重建表（**前提：三者尚未上生产、无需保留数据**）。

## 架构

### 1. 目录结构与加载

```
server/apps/
  cmdb/                         # 社区版：只有「扩展点接口 + 调用点」，零企业知识
    extensions/registry.py      #   通用具名注册表（社区拥有）
    model_ops/extensions.py     #   ModelEnterpriseExtension 默认空契约 + get_*()→registry
    instance_ops/extensions.py  #   InstanceEnterpriseExtension 默认空契约 + get_*()
    collect/extensions.py       #   CollectEnterpriseExtension 默认空契约 + get_*()
    custom_reporting/extensions.py  # CustomReportingExtension 默认空契约 + get_*()（新增）

  cmdb_enterprise/              # 商业版 overlay（.gitignore 忽略）
    apps.py                     #   AppConfig.ready()：向社区注册表注册各域实现
    config.py                   #   CELERY_BEAT_SCHEDULE（celery 组件按 app 自动合并）
    urls.py                     #   接口（url 自动发现 → api/v1/cmdb_enterprise/）
    models/ + migrations/       #   自有表，app_label=cmdb_enterprise，自有迁移目录
    tasks/                      #   @shared_task（Celery autodiscover）
    instance_ops/               #   附件/图片：provider/service/storage/constants
    model_ops/                  #   字段类型规则 provider
    collect/                    #   达梦 tree/dameng/provider
    custom_reporting/           #   models/views/serializers/services 等
    tests/                      #   企业测试（随 app 走，gitignore）
```

加载：`config/components/app.py` 现有逻辑已自动注册 `apps/` 下所有子目录（除 base/core/rpc）。`cmdb_enterprise` 存在即装、缺失即跳，**无需改 app.py**。字母序在 `cmdb` 之后 → 其 `ready()` 在 cmdb 加载后执行，注册时机正确。

### 2. 集成：注册表 IoC（社区零企业知识）

社区 `apps/cmdb/extensions/registry.py`（通用、不含任何企业名）：

```python
_registry = {}

def register(name: str, impl) -> None:
    _registry[name] = impl

def get(name: str, default=None):
    return _registry.get(name, default)
```

各域 `extensions.py`：保留**契约类**（社区拥有的接口，默认全 no-op），把 `get_*_enterprise_extension()` 从 load_provider 改为 `registry.get(name, _DEFAULT)`。调用点不变（如 `get_instance_enterprise_extension().normalize_file_fields(...)`）。

商业 `cmdb_enterprise/apps.py`：

```python
class CmdbEnterpriseConfig(AppConfig):
    name = "apps.cmdb_enterprise"

    def ready(self):
        from apps.cmdb.extensions import registry
        from apps.cmdb_enterprise.model_ops.provider import FileFieldModelExtension
        from apps.cmdb_enterprise.instance_ops.provider import FileFieldInstanceExtension
        from apps.cmdb_enterprise.collect.provider import get_collect_enterprise_extension
        from apps.cmdb_enterprise.custom_reporting.provider import CustomReportingExtension

        registry.register("model_ops", FileFieldModelExtension())
        registry.register("instance_ops", FileFieldInstanceExtension())
        registry.register("collect", get_collect_enterprise_extension())
        registry.register("custom_reporting", CustomReportingExtension())

        # 采集插件/NodeParams：import 本域模块触发既有 __init_subclass__ 自注册
        from apps.cmdb_enterprise.collect import dameng  # noqa: F401
        # MinIO 桶运行时注册
        self._register_buckets()
```

结果：社区代码中**搜不到 enterprise/cmdb_enterprise**，无 guarded import、无 load_provider 路径、无双模型。社区只认「注册表 + 契约」，谁来填它不知道。

### 3. 资源归属（Django/Celery 自动发现，无社区接缝）

| 资源 | 归属 | 机制 |
|---|---|---|
| 模型 + 迁移 | `cmdb_enterprise` app | app 自带 migrations，`app_label=cmdb_enterprise`，社区零企业模型 |
| 异步任务 | `cmdb_enterprise/tasks` | Celery `autodiscover_tasks()` |
| beat 调度 | `cmdb_enterprise/config.py` | celery 组件按 INSTALLED_APPS 合并 `CELERY_BEAT_SCHEDULE` |
| 接口 URL | `cmdb_enterprise/urls.py` | url 自动发现 → `api/v1/cmdb_enterprise/` |
| MinIO 桶 | app `ready()` 运行时注册 | 向 `settings.MINIO_PRIVATE_BUCKETS` 追加，不改社区 minio.py |
| 行为钩子 | 注册表（§2） | 社区调用点 → `registry.get()` |
| 采集 tree | 注册表（懒取） | `get_collect_obj_tree()` 请求时读 registry |
| 采集插件/NodeParams | 既有全局注册表 | app `ready()` import collect 模块触发 `__init_subclass__` |

时机说明：beat/tasks/urls/models 走 settings 加载或 autodiscover（早于或独立于 ready()），均为真 app 机制；行为钩子在请求时读注册表（晚于 ready()，已就绪）；采集 tree 请求时懒取（安全），插件/NodeParams 在 enterprise `ready()` 时 import 自注册。

### 4. 注册表暴露的扩展点（来自现有契约）

- `model_ops`（`ModelEnterpriseExtension`）：`file_attr_types()`、`validate_attr(attr)`、`unsupported_unique_attr_types()`、`unsupported_auto_relation_attr_types()`
- `instance_ops`（`InstanceEnterpriseExtension`）：`normalize_file_fields(...)`、`commit_instance_files(...)`、`on_instance_delete(...)`、`handle_upload/download/delete_temp(...)`
- `collect`（`CollectEnterpriseExtension`）：`collect_tree`、`plugin_packages`、`node_param_packages`
- `custom_reporting`（`CustomReportingExtension`，新建社区契约）：把 `services/model.py:565-643` 现有 7 个方法（`register_custom_reporting_model_fields`、`validate_custom_reporting_instance_fields`、`_get_custom_reporting_declared_attr_ids`、`validate_custom_reporting_relation_fields`、`normalize_custom_reporting_identity_keys`、`bootstrap_custom_reporting_model`、`sync_custom_reporting_model_group`）收敛为契约方法，社区方法体改为 `get_custom_reporting_extension().xxx(...)`，默认契约 no-op。

## 迁移：三个现有功能

### 附件/图片
- `apps/cmdb/enterprise/instance_ops` + `model_ops` → `apps/cmdb_enterprise/{instance_ops,model_ops}`。
- `CmdbFileObject` 模型移到 `cmdb_enterprise/models/`；**删** `apps/cmdb/models/file_object.py` 与迁移 `0024_cmdbfileobject.py`；新 app 迁移重建表。
- 上传/下载/删除接口移到 `cmdb_enterprise/urls.py`（社区 `views/instance.py` 的三个 action 移除，社区 `urls.py` 接缝删除）。前端改调 `api/v1/cmdb_enterprise/...`（见风险 R3）。

- 6 个模型 + views/serializers/services 全移到 `cmdb_enterprise/custom_reporting/`；**删**社区双模型 fallback（`models/custom_reporting.py`）、`views/custom_reporting.py`、`serializers/custom_reporting.py`、3 个社区 service 壳、迁移 `0024_custom_reporting.py`。
- `services/model.py` 的 7 个方法改走 `custom_reporting` 注册表契约。
- **明确**：删除社区 fallback 后，custom_reporting 自此为**商业版独占**能力——社区版不再具备该功能（与 overlay 定位一致）。若需保留社区可用的基础版，则属另案，本次不做。

### 达梦
- `apps/cmdb/enterprise/collect` → `apps/cmdb_enterprise/collect`。
- 社区 `services/collect_object_tree.py`、`collection/plugins/loader.py`、`node_configs/__init__.py` 改为从 `collect` 注册表取 `collect_tree`/`plugin_packages`/`node_param_packages`（默认空）。

## 社区清理（净身）

删除：
- 整个 `apps/cmdb/enterprise/` 目录。
- `models/__init__.py` 的 guarded enterprise 块（恢复为纯社区导入，移除 file_object/custom_reporting 企业相关导入）。
- 四接缝：`tasks/__init__.py`、`config.py`、`apps.py`、`urls.py` 中的 guarded enterprise 导入。
- 三域 `extensions.py` 里的 `load_provider`，改为 `registry.get`。
- custom_reporting 的社区 fallback 文件与 `services/model.py` 的裸惰性导入。

保留（社区拥有的通用接口）：`extensions/registry.py`、各域契约类与 `get_*_enterprise_extension()`、调用点。

## 范围边界（本次只动后端）

- **前端不动**：附件前端已在社区 `web/`，本次聚焦后端 app 化。前端商业 overlay（`web/enterprise` 已 gitignore）是独立话题，后续单独议。唯一前端联动：附件接口 URL 命名空间变化（见 R3）。
- **本地 dev 库**：无生产数据前提下，删社区 0024 迁移后，本地需重置/删旧表（新 app 迁移重建）。

## 测试

- 企业测试随 app 走（`apps/cmdb_enterprise/tests/`，gitignore），有 overlay 才跑（`testpaths = apps` 会自动发现）。
- 社区测试改为验证「**无 overlay 时社区行为正常**」：注册表空 → 默认契约 no-op；移除社区 tracked 测试对 enterprise 的硬依赖（现有 `test_file_field_*`、`test_enterprise_extensions` 的企业断言迁入 app 测试）。
- 验收：删掉 `cmdb_enterprise` 目录后，`uv run pytest apps/cmdb` 全绿、`makemigrations cmdb --check` 干净、社区 `grep -r "enterprise" apps/cmdb` 仅余通用注册表/契约（无路径）。

## 风险与缓解

- **R1 删除已提交迁移**：`0024_*` 已提交，删除后已应用它们的本地 dev 库会出现「有记录无文件」。缓解：无生产数据，提供 DB 重置说明；新 app 迁移重建表。
- **R2 跨 app 外键**：custom_reporting 模型若 FK 到社区 cmdb 模型，跨 app FK Django 支持；`CmdbFileObject` 仅存图库 inst_id（无 FK），无碍。实施前核对 custom_reporting 模型的 FK。
- **R3 接口命名空间变化**：附件接口从 `api/v1/cmdb/...` 变 `api/v1/cmdb_enterprise/...`，前端 `api/instance.ts` 的 upload/download/delete 路径需同步改（本次后端改、前端跟一处路径）。
- **R4 采集注册时机**：node_configs/plugins 若在 enterprise `ready()` 前 finalize 会漏达梦。缓解：collect_tree 懒取；插件/NodeParams 在 enterprise `ready()` import 自注册；必要时令社区加载器幂等可重入。
- **R5 app 加载顺序**：依赖 `cmdb_enterprise` 在 `cmdb` 之后 ready()。字母序天然满足；如不放心可在 AppConfig 显式声明依赖或在 ready() 内惰性取注册表。

## 非目标

- 不动前端商业 overlay 化（仅跟随 R3 改一处路径）。
- 不引入独立商业仓库 / 子模块（overlay 目录由现有打包流程交付）。
- 不改其他 app（monitor/opspilot 等）的 enterprise 子目录。

## Verification（端到端）

1. 有 overlay：`apps/cmdb_enterprise` 在位 → 附件/custom_reporting/达梦功能与现状一致；`makemigrations` 干净；企业测试全绿。
2. 无 overlay：删 `apps/cmdb_enterprise` → 社区 cmdb 启动正常、`pytest apps/cmdb` 全绿、无附件/custom_reporting/达梦能力且无报错；`grep -rn "cmdb_enterprise\|enterprise" apps/cmdb` 只剩通用注册表/契约。
3. `makemigrations cmdb_enterprise` 生成自有迁移；新库 `migrate` 重建全部商业表。
