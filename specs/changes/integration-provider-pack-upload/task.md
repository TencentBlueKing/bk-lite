# 集成中心 Provider 包上传

Status: ready

- 规格：`specs/changes/integration-provider-pack-upload/task.md`
- 对齐日期：2026-08-28
- 范围：企业版。社区版含空的包表与 `system_mgmt` 迁移，不含上传入口与同步逻辑。

## Problem Statement

企业要把自研登录 / 同步 / IM 等集成以规范包的形式装进 BK-Lite，并在审查后通过界面分发。今天只能把代码放进内置目录再发镜像；没有运行时上传，换包若拆掉实例会丢掉凭据和下游绑定。

## Solution

企业版在集成中心的「Provider 包」页上传已审查的 zip。包进 Postgres，本地按 revision 解压缓存，各进程用 revision 拉平后热加载。同 key 须确认后更换：实例和登录绑定、用户同步源、IM 通道保留，连接状态打回待验证。卸载表示下线该类型，有实例则拒绝。

## User Stories

1. As a 有集成中心权限的企业管理员, I want 在集成中心二级页「Provider 包」上传 zip, so that 审查通过的包可以出现在新建实例的可选类型里，而无需发镜像。
2. As a 有集成中心新增权限的企业管理员, I want 上传新 key 在试加载通过后直接生效, so that 不必重启即可建实例。
3. As a 有集成中心编辑权限的企业管理员, I want 上传已有 key 时先看到影响（实例数、测通前登录/同步/IM 不可用）再确认更换, so that 不会误覆盖生产包。
4. As a 有集成中心编辑权限的企业管理员, I want 更换后该 key 下实例打回待验证且配置仍在, so that 只需再测连接，不必重建绑定。
5. As a 有集成中心权限的企业管理员, I want 仅对已上传行更换或卸载、内置包不可覆盖, so that 官方类型不被客户 zip 替换。
6. As a 有集成中心删除权限的企业管理员, I want 有实例时不能卸载包, so that 下线类型不会先拆掉接入数据。
7. As a 有集成中心查看权限的企业管理员, I want 加载失败的包仍出现在包列表并显示原因, so that 能重新上传或在无实例时卸载。
8. As a 集成管理员, I want 包加载失败时仍能打开已有实例改配置并保存, so that 表单和凭据不锁死；测连接应失败并说明 Provider 不可用。新建实例候选不含失败包。
9. As a 社区版用户, I want 集成中心与今天一致、没有 Provider 包页, so that 加类型只能把包放进内置目录后发镜像。
10. As a 没有集成中心权限的人, I want 看不到 Provider 包页, so that 该能力与集成中心同一套菜单权限。

## Implementation Decisions

### 产品与权限

- 仅企业版。无部署级功能开关。查看 / 上传 / 更换 / 卸载复用集成中心 `View` / `Add` / `Edit` / `Delete`，不单独限制超管。
- 上传是审查后的分发通道。技术校验只拦善意错误；恶意包在主进程执行，审查纪律（谁审、审网络/文件/ORM 范围、留痕）必须有。签名验签后置，不挡本期。
- 集成中心做成与用户管理相同的二级页签：集成实例（现有卡片与「添加集成」弹窗）与 Provider 包。不在添加集成弹窗里切换包管理。社区版不出现 Provider 包页签。
- 一个上传入口：无该 key 则新增；已有则 409 并带出现有版本与实例数，确认后同一接口带明确更换参数。无单独升级 API。不同时覆盖：对包行加行锁，先提交者成功，后者 409。
- 行内更换、卸载只出现在已上传行。内置行无操作。页头「上传」打开轻量弹窗（拖放 + zip/10MB/审查说明），再提交现有 POST。同 key 仍 409 确认。主表不展示 pack_revision 与作者 version。

### 对象生命周期

- 包与实例解耦。实例仍只认 `provider_key`。
- 同 key 更换：覆盖 zip、revision +1、热切换 adapter；该 key 下全部实例的 `status` 与 `capability_status` 与包写入同事务打回待验证。下游绑定不删。测通前该实例登录 / 同步 / IM 按未验证处理。
- 卸载：有该 `provider_key` 的实例则拒绝。无实例则删库记录、摘注册表。无启用/禁用开关（停用即卸）。
- 镜像内类型只放内置目录。删除 `providers/custom/` 扫描通道。上传不得占用当时内置目录名（含二开打进镜像的 key）。

### 存储与同步

- zip 存 Postgres（上限 10MB）。本轮不预留对象存储引用字段；以后若改存 MinIO 等再加列。模型与建表迁移放在社区 `system_mgmt`（空表、无上传路由），对齐敏感信息：`SensitiveInfoAuthorization` 模型 + 社区迁移建表，API/页面只在企业 overlay。读写、解压、同步、上传 ViewSet 只在企业 overlay。本地 `{PROVIDER_PACK_CACHE_DIR}/{key}/{revision}/` 可丢缓存，默认独立数据目录，不使用 `/apps/pkgs`，不解压进源码树。
- 各进程访问注册表前比对 `UploadedProviderPack` 的 `(key, pack_revision)` 快照（查询只取这两列，不得带 `archive`），与内存不一致则拉包、解压、导入；1～3 秒进程内缓存。快照未变但上次加载失败的 key 仍重试。同步失败不得清空内置包。不设独立 Catalog 单行表；上传包变多、热路径扫表成为问题时再加世代号。
- 不选共享盘、Redis 广播、MinIO 存包体、上传后自动重启。

### 加载

- 身份：`manifest.key` 稳定；`revision` 每次成功入库单调递增，作为 import 名与缓存目录身份；作者 `version` 只展示。
- 上传包 `import_name` 由加载器生成（含 revision）。builtin 与上传包的 `adapter_path` / `base_connection_adapter_path` 均为包内相对路径，拼到本次 `import_name`（或 builtin 模块前缀）再取类。`adapter_key` 必须以 `{manifest.key}.` 为前缀。
- 有包目录时禁止写死本包绝对模块路径。测试里无目录的假 manifest 仍可绝对导入。
- 成功更换：锁内按 key 替换注册表（含增减 capability 时摘掉旧 adapter_key），然后按前缀去掉上一版 `sys.modules` 条目；在途仍持有的旧类对象继续跑完，无引用后可被回收。可删上一版磁盘目录。不 `reload`，不复用旧 `import_name`。
- 失败（解压、布局、import、试取类、写库）：不提交、不增加 `pack_revision`、不切注册表；清掉本次 `import_name` 整树；删除本次新目录。避免同号 revision 重试撞上半截模块。
- 钩子挂在现有注册表读锁之后：先加载内置，再同步上传包。`system_mgmt` 启动 `ready()` 仍不扫包。
- 内置继续绝对稳定模块名，不走 revision 缓存。

### 界面与 API 要点

- Provider 包列表：内置 + 已上传，标来源与加载状态；失败行展示原因。
- 新建实例候选：仅加载成功的包。失败包不可选。
- 实例详情在包加载失败时仍可改配置并保存；测连接失败并说明 Provider 不可用。

## Testing Decisions

测外部行为，不测 `sys.modules` 键名实现细节（可测「换包后新请求走新行为、在途不崩」）。

- 加载器：内置不受上传失败影响；相对 `adapter_path`；builtin key 拒绝上传；去掉 custom 扫描后的回归（现有 `test_provider_loader`）。
- 解压：zip slip、体积上限、失败不留脏目录。
- 同步：`(key, pack_revision)` 快照落后才拉；查询不含 archive；进程内短缓存；DB 不可用时内置仍可用。
- 上传：无 `Add` 则 403；新 key 成功；已有 key 无确认参数 409；无 `Edit` 则 `replace=true` 403；`replace=true` 覆盖并打回该 key 实例状态；并发后者 409；试加载失败不落库。
- 卸载：有实例拒绝；无实例后列表与新建候选不再出现该 key。
- 列表：失败包可见原因且不可用于新建。
- 企业/社区：社区构建无上传路由与页签。
- 日志：不含 archive、凭据、响应正文。先验：`test_provider_loader`、集成实例测连接与权限测试。

## Out of Scope

- 社区版上传、部署开关、签名验签与签名 CLI。
- 用户可见的多版本并存或升级协议；作者 version 不当模块名。
- 启用/禁用、有实例时卸载或级联删实例、配置迁移向导。
- 通用 HTTP provider、隔离插件进程、自动重启 worker。
- 从 `sys.modules` 强制立刻销毁仍被在途引用的旧类。

## Further Notes

### 现状（实现时以代码为准）

包在 `system_mgmt/providers/`。内置四套目录须含 `__init__.py`、`adapters/client.py`、`adapters/base_connection.py` 和 `PROVIDER_MANIFEST`。前端实例表单由 providers 接口的 public dict 驱动。adapter 在 uvicorn 多 worker 与 Celery 主进程 `import` 执行。注册表为每进程内存 dict，经读锁惰性加载。`ready()` 不扫包。

### 安全事实

主进程持有凭据解密密钥与 DB。import 即执行包顶层代码。故上传等价于进程内执行面；本期用企业版 + 集成中心操作权限 + 事先审查，而不是运行时沙箱。

### 调研摘要（未改变本期方案）

Dify / Airbyte 走隔离进程或容器；Jenkins 等进程内插件是安全重灾区。bk-user 与当前加载模型同构且需重启。本期仍进程内加载。通用 HTTP provider 可另开需求，与上传不冲突。

### 已否决

- 共享卷 / PVC / 文件同步；Redis 当版本权威；MinIO 存包体。
- 上传后自动重启；只重载当前 worker。
- 部署开关；无审查即开放上传。
- 卸包必须先删实例才能换代码；静默覆盖同 key。
- 用 `providers/custom/` 或 `/apps/pkgs` 当上传缓存；把运行时包打进 `custom/`。
- `importlib.reload` 做换包。
- 在「添加集成」弹窗里切换包管理。
- 启用/禁用作为本期运营开关。

### 阶段

本期一次交付：包规范与校验 CLI、表与缓存与拉模型、相对 adapter_path（含内置四套对齐）、上传/更换/卸载 API 与企业页签、失败可观测、实例打回待验证。签名、通用 HTTP provider、启用禁用均后置。
