# CMDB 企业版分层规范（v2）

> ⚠️ **已被 v3 取代（2026-06-09）**：商业版已从嵌套 `apps/cmdb/enterprise/` 重构为同级 overlay app `apps/cmdb_enterprise` + 注册表 IoC。当前权威规范见
> `docs/superpowers/specs/2026-06-09-cmdb-enterprise-architecture-v3.md`。本文仅作历史保留。

> 本文为 CMDB 商业版代码的**落地规范**，取代同名的早期实施计划（早期计划只覆盖
> 读路径 facade，未涉及写路径/持久化/任务/调度/配置）。代码内同步副本见
> `server/apps/cmdb/enterprise/README.md`，二者保持一致；本文为权威全量版。
>
> 首个落地消费者：**模型字段附件/图片类型**（`enterprise/{model_ops,instance_ops}` +
> 社区 `CmdbFileObject` 台账）。采集域历史实现（达梦）已收敛到 `enterprise/collect/`。

## 目标与不变式

`apps/cmdb/enterprise` 是 CMDB 商业版能力的**唯一行为代码区域**，且必须是 cmdb app 内的普通包（**不是独立 Django app**）。

- 社区版只定义**扩展契约**与极少数**发现接缝**
- 企业版只提供**增量实现**（含自有任务/调度/配置注册）
- 删除 `apps/cmdb/enterprise` 后，CMDB **行为**自动回退社区版

**不变式（含边界）**

- **行为、字段类型、任务代码、调度内容、配置注册** —— 随 `enterprise/` 一起消失（真 add-only）。
- **有状态能力的表结构是社区基础设施**：企业能力需要的 DB 模型与迁移**正常放社区**
  `apps/cmdb/models/` 与 `apps/cmdb/migrations/`（与 `config_file_version.py` 同列），**不放
  enterprise**。原因：enterprise 非独立 app，把模型塞进去会让表结构/迁移结构错乱（注册依赖
  惰性导入、`makemigrations` 不可靠）。社区只持有表的 **schema**，企业版独占其**读写行为**；
  删 enterprise 后表闲置但无害。**schema 是社区脚手架，行为是 add-only**。

禁止：隐式覆盖、同名替换、monkey patch 替换社区主流程。

## 两层结构

```text
apps/cmdb/                              # 社区版
  extensions/loader.py                  #   共享 load_provider（缺 provider→默认；破损→报错）
  model_ops/extensions.py               #   ModelEnterpriseExtension  + get_model_enterprise_extension()
  instance_ops/extensions.py            #   InstanceEnterpriseExtension + get_instance_enterprise_extension()
  collect/extensions.py                 #   CollectEnterpriseExtension + get_collect_enterprise_extension()

  models/                               #   有状态能力的表（社区基础设施，正常归属 cmdb）
  migrations/                           #   表迁移（社区，正常归属 cmdb）
  tasks/__init__.py                     #   接缝①：guarded 导入 enterprise 任务
  config.py                             #   接缝②：guarded 合并 enterprise beat
  apps.py  (AppConfig.ready)            #   接缝③：guarded 调用 enterprise bootstrap（配置/采集注册）

  enterprise/                           # 企业版：唯一行为代码区，删掉即回退
    bootstrap.py                        #   install()：注册桶等运行时配置
    beat.py                             #   ENTERPRISE_BEAT_SCHEDULE
    tasks/                              #   企业 @shared_task
    model_ops/provider.py               #   字段类型规则等
    instance_ops/{provider,service,storage,constants}.py
    collect/{provider,tree,dameng}.py   #   采集域（达梦在此）
```

社区业务代码**只能依赖域门面**（`apps.cmdb.<domain>.extensions`），不得直接 import 更深的 enterprise 模块。

## 发现接缝（唯一允许的 community→enterprise 导入）

普通业务代码**禁止** `import apps.cmdb.enterprise.xxx`。允许的 community→enterprise 导入只有以下**四处**，全部 guarded 或经 loader 回退：

| # | 位置 | 作用 | 缺 enterprise 时 |
|---|---|---|---|
| 域 loader | `extensions/loader.py` | 加载 `enterprise.<domain>.provider` | 回退空契约 |
| ① | `tasks/__init__.py` | 导入 `enterprise.tasks` 使 Celery 发现 | 静默跳过 |
| ② | `config.py` | 合并 `enterprise.beat.ENTERPRISE_BEAT_SCHEDULE` | 合并 no-op |
| ③ | `apps.py:ready()` | 调 `enterprise.bootstrap.install()` | 静默跳过 |

> enterprise 非独立 app，无法靠「per-app 自动发现」注册任务/beat/配置，故由 cmdb app 在三个标准聚合点做 guarded 转接，均为固定接缝、非散落动态导入。
> **模型不在此列**：有状态能力的表正常定义在社区 `models/`、迁移在 `migrations/`，企业 provider 直接 import 社区模型即可。新增企业需求**不得**再增加新的 community→enterprise 接缝。

## 各场景接入范式

1. **行为扩展（读/写/生命周期）**：在域契约加方法，社区在固定 seam 调用。读路径 `extend_*`、写路径 `validate_*/normalize_*`、生命周期 `commit_*/on_*`。社区默认 no-op/原样返回。
2. **新字段类型**：`ModelEnterpriseExtension.file_attr_types()` 声明，`validate_attr(attr)` 落规则；社区用 `is_file_attr_type()` 识别，缺企业时恒空集 → 相关分支 inert。
3. **新接口/动作**：URL 留在社区瘦 viewset，仅委托域契约 `handle_*`；社区默认抛「未启用」。enterprise 不放 `urls.py`（否则被 URL 自动发现挂成独立命名空间）。
4. **持久化（模型/迁移）**：模型类**正常放社区** `apps/cmdb/models/*.py` 并在 `models/__init__.py` 直接 import；迁移落 `apps/cmdb/migrations/`。企业 provider/service 直接 `from apps.cmdb.models.xxx import ...`。**不要**把模型放 enterprise。
5. **异步任务**：`@shared_task` 放 `enterprise/tasks/*.py`，接缝①使其被 Celery 发现。
6. **周期调度**：beat 字典放 `enterprise/beat.py` 的 `ENTERPRISE_BEAT_SCHEDULE`，接缝②在 `config.py` guarded 合并。
7. **运行时配置**：企业专属 settings（如 MinIO 桶）在 `enterprise/bootstrap.py:install()` 运行时注册（向 `settings.MINIO_PRIVATE_BUCKETS` 追加），由接缝③触发；不改社区 `config/components/*`。
8. **采集注册**：经 `CollectEnterpriseExtension` 暴露 `collect_tree / plugin_packages / node_param_packages`；社区 `collect_object_tree.py`、`plugins/loader.py`、`node_configs` 统一从门面取，仅扫描 `enterprise.collect` 单包。
9. **规则守卫集合**：社区「不支持类型」集合（联合唯一、自动关联）通过契约方法合并企业增量 `unsupported_unique_attr_types()` / `unsupported_auto_relation_attr_types()`；社区集合里**不出现** `attachment/image` 等企业类型名。

## 契约方法清单（当前）

```python
class ModelEnterpriseExtension:        # apps/cmdb/model_ops/extensions.py
    file_attr_types() -> set
    validate_attr(attr) -> attr
    unsupported_unique_attr_types() -> set
    unsupported_auto_relation_attr_types() -> set

class InstanceEnterpriseExtension:     # apps/cmdb/instance_ops/extensions.py
    normalize_file_fields(model_id, data, attrs, *, operator, old_instance=None) -> data
    commit_instance_files(model_id, inst_id, saved, attrs, *, operator)
    on_instance_delete(model_id, inst_id, instance)
    handle_upload(*, request, model_id, attr_id, uploaded_file) -> meta
    handle_download(*, request, file_id, check_read_permission=None) -> url
    handle_delete_temp(*, request, file_id)

class CollectEnterpriseExtension:      # apps/cmdb/collect/extensions.py（frozen dataclass）
    collect_tree: list
    plugin_packages: tuple[str, ...]
    node_param_packages: tuple[str, ...]
```

## 错误处理

- **provider 模块/父包不存在** → 正常回退空契约。
- **provider 存在但不符契约（缺方法）** → 显式 `AttributeError`，统一日志暴露，绝不静默。

CMDB 可以没有企业版，但不能悄悄接受损坏的企业版实现。

## 后续商业需求接入流程

1. 判断归属能力域：`model_ops` / `instance_ops` / `collect`，或平台场景（持久化/任务/调度/配置）。
2. 能力域行为：契约已够 → 只在 `enterprise/<domain>/` 补实现；契约不足 → 先在社区 `<domain>/extensions.py` 加显式契约方法，再由 provider 实现。
3. 平台场景：行为放 `enterprise/{tasks,beat,bootstrap}` 复用既有三接缝；需建表则把模型/迁移正常放社区 `apps/cmdb/{models,migrations}`。**不得新增新的 community→enterprise 接缝**。

## 落地状态（2026-06）

- 共享 loader + 三域门面（model_ops / instance_ops / collect）已落地。
- 达梦由 `enterprise/tree.py`+`enterprise/db/dameng.py` 收敛到 `enterprise/collect/`，社区三处采集钩子改走 collect 门面、仅扫 `enterprise.collect`。
- 附件/图片字段：`enterprise/instance_ops`（校验/落账/回收/上传下载）+ `enterprise/model_ops`（字段类型规则）+ 社区 `CmdbFileObject` 台账（`migrations/0024`）。
- 回归：cmdb 后端全量通过；`makemigrations --check` 干净；前端 `tsc`/ESLint 干净。
