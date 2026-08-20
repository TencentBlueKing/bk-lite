# 集成中心 Provider 插件化交接

**日期**：2026-08-14  
**状态**：方案探索完成，尚未开始实现  
**范围**：可信平台管理员上传 Provider 插件包，使其在服务应用后可被集成中心选择并创建集成实例。  
**包结构（内置/自研、非上传）**：`server/apps/system_mgmt/docs/provider-packs.md`

## 1. 已确认的产品边界

### 1.1 Provider 与集成实例

- **Provider 插件包（Provider Package）**：某种外部系统的集成定义与实现，例如飞书、微信、企业微信、AD，或管理员上传的 Acme IDP。
- **集成实例（Integration Instance）**：某个 Provider 的具体连接配置，例如“生产企业微信”或“总部 AD 域”。

一个 Provider 可以创建多个集成实例。当前集成中心的“添加集成”仅创建实例；插件化后仍保持这个职责，不把 Provider 安装与实例创建混在同一个操作中。

### 1.2 内置与上传 Provider 的关系

飞书、微信、企业微信、AD 都应被视为 Provider 插件，只是来源为 `builtin`，随 BK-Lite 发布。管理员上传的插件来源为 `uploaded`。

二者应共享：

- Provider Manifest；
- Capability Adapter 契约；
- 注册、发现与 Provider 列表行为；
- 版本和启停语义（后续可逐步统一）。

二者当前可保留不同安装方式：内置包随镜像/代码发布，上传包进入持久化插件目录。

### 1.3 信任与运行模型

本期采用受信任部署管理员模型：上传者等同于平台管理员，插件包允许包含并执行 Python 代码。

本期不包含：

- 插件签名、审核或供应链可信校验；
- 沙箱、独立 Runner、容器隔离；
- 插件自带依赖的动态安装或依赖隔离；
- 在线热加载。

不做在线热加载的原因是 Provider Registry 位于 Web、任务和 NATS 等进程的内存中。仅在上传请求命中的进程执行 `import` 会造成各进程 Provider 集合不一致。

安装后应进入“待应用”状态；通过滚动重启或明确的服务重启，所有进程在启动时扫描并加载插件。只有所有必要进程可成功加载时，该 Provider 才应被标记为可选。

## 2. 当前实现事实

### 2.1 后端 Provider 框架

当前已有内置 Provider 的实现骨架：

| 职责 | 位置 |
| --- | --- |
| Manifest 数据模型与校验 | `server/apps/system_mgmt/providers/schemas.py` |
| 内置 Provider 加载器 | `server/apps/system_mgmt/providers/loader.py` |
| Provider / Adapter 注册表 | `server/apps/system_mgmt/providers/registry.py` |
| 能力运行时与统一结果 | `server/apps/system_mgmt/providers/runtime.py` |
| 能力 Adapter 基类 | `server/apps/system_mgmt/providers/adapters/base.py` |
| 内置 Manifest | `server/apps/system_mgmt/providers/manifests/{feishu,wechat,wecom,ad}.py` |
| 内置 Adapter | `server/apps/system_mgmt/providers/adapters/{feishu,wechat,wecom,ad}.py` |

当前 Loader 使用 `BUILTIN_PROVIDER_MODULES` 硬编码导入四个 Provider 模块，尚未扫描外部目录或数据库记录。

### 2.2 集成中心

Provider 清单由以下接口返回：

```text
GET /system_mgmt/integration_instance/providers/
```

入口实现：`server/apps/system_mgmt/viewset/integration_instance_viewset.py`。

前端已在创建集成实例时拉取该清单：

- `web/src/app/system-manager/(pages)/integration-center/page.tsx`
- `web/src/app/system-manager/(pages)/integration-center/CreateIntegrationInstanceModal.tsx`
- `web/src/app/system-manager/api/integration-center/index.ts`

因此，当上传 Provider 已成功注册并出现在 `/providers/` 响应中后，现有“添加集成”入口即可选择它；无需为 Provider 选择器另造一套实例创建流程。

### 2.3 `bk-user` 的参考价值

`bk-user` 采用受信任、部署期 Python 插件模式：应用启动时扫描固定目录、导入每个插件 Python 包，再由包的 `__init__.py` 主动注册插件。

参考位置：

- `/Users/lanyu/Work/bk-user/src/api/bkuser_core/categories/apps.py`
- `/Users/lanyu/Work/bk-user/src/api/bkuser_core/categories/loader.py`
- `/Users/lanyu/Work/bk-user/src/api/bkuser_core/categories/plugins/README.md`

其“修改插件后需重启服务”的模式适合本期 BK-Lite 方案。

## 3. Provider 插件包规范建议

上传包与未来的内置包应采用相同内部结构：

```text
acme-idp-1.0.0.zip
├─ manifest.yaml
├─ plugin.py
├─ adapters/
│  ├─ login_auth.py
│  ├─ user_sync.py
│  └─ im_notification.py
├─ assets/
│  └─ icon.svg
└─ README.md
```

安装后的目录建议按不可变版本保存：

```text
<persistent-plugin-root>/
└─ acme_idp/
   └─ 1.0.0/
      ├─ manifest.yaml
      ├─ plugin.py
      ├─ adapters/
      └─ assets/
```

`manifest.yaml` 应描述可静态读取的元数据、表单和能力，例如：

```yaml
key: acme_idp
version: 1.0.0
name: Acme IDP
description: 企业身份服务
entrypoint: plugin:register
capabilities:
  - key: login_auth
    name: 登录认证
    adapter: adapters.login_auth:AcmeLoginAuthAdapter
```

建议将当前绝对 `adapter_path` 改为相对于插件根目录的入口（如 `adapters.login_auth:AcmeLoginAuthAdapter`）。上传包不应依赖主项目源码包路径。

`plugin.py` 保持薄层，仅完成 Manifest 与 Adapter 的注册；HTTP、LDAP 或厂商 SDK 调用逻辑放在对应 Adapter 中。

## 4. Capability 的本期边界

当前平台真正支持的 Capability 类型只有：

```text
login_auth
user_sync
im_notification
```

详情页 Tab 顺序、能力展示文本和部分专用交互仍存在前端硬编码，主要位于：

- `web/src/app/system-manager/utils/integrationCenter.ts`
- `web/src/app/system-manager/(pages)/integration-center/detail/page.tsx`
- `web/src/app/system-manager/locales/{zh,en}.json`

下游业务同样依赖固定能力及其数据契约：

| Capability | 下游行为 |
| --- | --- |
| `login_auth` | 构造登录地址、认证、回调处理 |
| `user_sync` | 列举部门、同步用户及映射字段 |
| `im_notification` | 列举外部用户、同步映射、发送消息 |

相关 Adapter 基类：`server/apps/system_mgmt/providers/adapters/base.py`。  
相关业务校验：`server/apps/system_mgmt/services/capability_contract_service.py`。

本期必须明确：

> 上传插件可以扩展外部系统类型，不能扩展 BK-Lite 的业务 Capability 类型。

因此，安装校验应拒绝未知 Capability。上传 Provider 只能通过上述三种既有契约接入。

前端可做的最小去硬编码收敛：

- Provider 名称、描述优先使用 Manifest；
- 未提供图标的 Provider 使用通用集成图标；
- Capability 标签优先使用 Manifest 的 `name`；
- Tab 由 `base + Provider 已声明且平台支持的 Capability` 生成。

专用于微信或登录认证的现有 UI 增强可暂时保留为内置 Provider 特例；上传插件默认使用通用配置字段表单和测试连接能力。

## 5. 安装、应用与 UI 流程

建议增加独立的“Provider 管理”页或抽屉，与“添加集成”分层：

```text
Provider 管理（平台管理员）
  上传 ZIP → 校验 → 安装 → 应用 → 查看状态/错误

添加集成（具备集成中心新增权限的用户）
  选择已启用 Provider → 创建 Integration Instance → 配置和测试
```

完整生命周期：

```text
上传 ZIP
  → 临时解压与包结构/Manifest 校验
  → 原子写入持久化插件目录
  → 创建 Provider Release（pending_apply）
  → 管理员执行“应用”
  → 滚动重启或受控服务重启
  → 启动时扫描 builtin + uploaded 插件目录
  → import 插件并注册 Manifest/Adapter
  → 成功：enabled；失败：failed
  → /providers/ 仅返回当前已成功加载的 Provider
```

上传校验至少应包含：

- ZIP 大小限制和目录穿越防护；
- `manifest.yaml`、`plugin.py` 是否存在；
- `provider_key` 格式、唯一性及与内置 Provider 的冲突检查；
- Manifest 是否能通过 `ProviderManifest` 校验；
- Capability 是否均属于平台支持范围；
- 入口和 Adapter 是否可导入及注册；
- 任一 Adapter 注册失败时，整包不得标记为已启用；
- 校验/加载错误应持久化并在管理 UI 展示。

建议新增独立权限，例如：

```text
integration_provider-Manage
```

不得复用 `integration_center-Add`，后者仅授权创建集成实例。

## 6. 数据模型与 API 的后续设计方向

建议新增 Provider 包/版本记录（具体模型名称待设计），至少包含：

- `provider_key`、`name`、`version`；
- `source`：`builtin` / `uploaded`；
- `manifest`；
- `status`：`pending_apply` / `enabled` / `failed` / `disabled`；
- 安装目录、原包校验和、错误信息；
- 上传者、创建和更新时间。

需要进一步决定集成实例是否在一期就绑定 Provider 版本。建议至少预留版本字段；默认不让已存在实例在插件升级后静默切换到新实现。

建议 API 分层：

```text
POST /system_mgmt/provider_packages/upload/
GET  /system_mgmt/provider_packages/
POST /system_mgmt/provider_packages/{id}/apply/
POST /system_mgmt/provider_packages/{id}/disable/

GET  /system_mgmt/integration_instance/providers/
```

具体 URL、权限资源和应用重启的执行方式需结合现有部署与 Supervisor 机制设计，不能在启动路径中通过等待、无限重试等方式掩盖依赖问题。

## 7. 外部调用方式

插件契约不限制 Adapter 如何访问外部系统：

```text
BK-Lite Runtime → Capability Adapter → HTTP / LDAP / 厂商官方 SDK → 外部系统
```

现有飞书、微信、企业微信以直接 HTTP 为主，AD 使用 LDAP。使用厂商 SDK 只是减少插件作者手写鉴权、请求构造、分页或错误转换的工作，不影响 Provider 插件协议。

一期建议优先使用平台已有 Python 依赖；插件自带第三方依赖、版本冲突和隔离留待后续处理。

## 8. 下一步建议

1. 先创建 change spec，明确一期验收标准、部署路径及“应用”动作如何完成服务重启。
2. 阅读并遵守 `docs/operations/server-startup-dependencies.md` 后，再设计启动扫描与注册时机。
3. 设计 Provider Package / Provider Release 数据模型、迁移和权限资源。
4. 定义并固化 `manifest.yaml` 规范、最小示例包和加载测试夹具。
5. 将 Loader 从硬编码模块列表扩展为 builtin + uploaded 插件目录扫描。
6. 新增 Provider 管理 API 和 UI；将 `/providers/` 结果限定为已成功加载的 Provider。
7. 以一个最小测试 Provider 验证完整链路：上传、校验、应用、重启加载、Provider 可选、创建实例。
