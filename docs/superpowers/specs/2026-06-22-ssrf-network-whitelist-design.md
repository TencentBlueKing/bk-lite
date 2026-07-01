# SSRF 内网白名单（NetworkWhiteList）设计

- 日期：2026-06-22
- 模块：`server/apps/core`（校验器）、`server/apps/system_mgmt`（模型/API/缓存）、`web/system-manager`（管理界面）
- 状态：设计已确认，待写实现计划
- 交付范围：全栈（后端 + 前端 UI）

## 1. 背景与问题

opspilot skilltool 添加内网工具时，后端走严格的 `SSRFValidator.validate()` 校验，会阻断全部 RFC1918 私网段。现象：填 `http://10.11.73.15:8000/sse` 点「获取工具」报错 `目标地址被禁止: 禁止的网段 10.0.0.0/8`，导致**内网部署的 MCP / DB / K8s 工具完全无法添加**。

校验器现有三档（`server/apps/core/utils/ssrf_validator.py`）：

- `validate()` —— 严格：挡 云元数据 + 私网 + localhost（skilltool 与 Agent 运行时 fetch/browser 都用它）
- `validate_callback()` —— 挡 云元数据 + localhost，放行私网
- `validate_llm_endpoint()` —— 只挡云元数据，放行私网 + localhost

需要一种**可控地放行特定内网网段**的机制，而不是一刀降级整档。

## 2. 目标 / 非目标

**目标**
- 管理员可在「系统管理 → 安全设置」维护一份可信内网网段白名单（CIDR 形式）。
- 严格 `validate()` 的判定改为 **`云元数据硬挡 → 白名单放行 → 私网黑名单`**，全局生效。
- 白名单为空时行为与现状**完全一致**（零回归）。

**非目标**
- 不做按组织 / 按工具的细粒度白名单（YAGNI，将来可在同一缓存层上扩展数据源）。
- 不放宽云元数据防护（任何情况下都硬挡）。
- 不改 `validate_callback` / `validate_llm_endpoint`（它们本就放行私网，白名单对其无意义）。

## 3. 关键决策记录（已与用户确认）

| 维度 | 结论 | 备注 |
|---|---|---|
| 放开范围 | 全部 skilltool 管理端入口起步，**最终选设计 X：全局生效** | 见下 |
| 匹配维度 | **IP / CIDR 网段** | DNS 解析后比对解析到的 IP，保留 DNS-rebinding 防护 |
| 配置载体 | **system_mgmt 专用 model + 管理 UI**（方案 B 精炼版） | 不复用 key-value `SystemSettings` |
| 派发方式 | **设计 X：白名单焊进 `validate()`，全局生效** | 含 Agent 运行时 fetch/browser |
| 模型命名 | `NetworkWhiteList` | 用户指定 |
| 前端落点 | **平台设置（`/system-manager/settings`）下新增「白名单」tab** | 与 密钥/审计日志/错误日志 并列，非"安全设置" |
| 权限资源 | **独立资源 `network_white_list`**（View/Add/Edit/Delete） | 贴合 tab 化权限范式，在 seed 文件注册 |

**设计 X 的已知接受代价（务必在 PR/文档中显式标注）**：白名单同样对 LLM 可控的 `fetch`/`browser`/`website_loader` 生效——提示词注入可诱导 Agent 访问被放行网段。缓解：白名单只填确需的最小网段；云元数据永封；写权限收口到安全设置管理员。

## 4. 架构总览

```
管理员 ──► 平台设置「白名单」tab (web, /system-manager/settings/network-whitelist)
                 │  CRUD  /api/v1/system_mgmt/network_white_list/
                 ▼
        NetworkWhiteListViewSet ──► NetworkWhiteList 表 (system_mgmt)
                 │ 写操作后失效缓存
                 ▼
        network_whitelist_cache  (cache key: system_settings:network_white_list, TTL 300s)
                 ▲ get_network_whitelist_cidrs()（延迟导入 + fail-closed）
                 │
SSRFValidator.validate() ─► _is_blocked_ip()
   顺序：① 云元数据硬挡  ② 白名单放行  ③ 私网黑名单
   （所有严格校验调用方：skilltool 守卫 + fetch/browser/website_loader 统一过这里）
```

## 5. 详细设计

### 5.1 数据模型 `server/apps/system_mgmt/models/network_white_list.py`

```python
from django.db import models
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class NetworkWhiteList(MaintainerInfo, TimeInfo):
    """SSRF 内网白名单条目（CIDR）。命中条目的解析 IP 可绕过私网阻断（云元数据除外）。"""

    network = models.CharField(max_length=64, unique=True)   # 规范化 CIDR：10.11.73.0/24 / 10.11.73.15/32
    remark = models.CharField(max_length=255, default="")    # 备注：为什么放行
    enabled = models.BooleanField(default=True)              # 软开关

    class Meta:
        verbose_name = "Network White List"
        db_table = "system_mgmt_network_white_list"
```

- 继承 `MaintainerInfo`（`created_by`/`updated_by`/`domain`）+ `TimeInfo`（`created_at`/`updated_at`），与仓库其它模型一致。
- **用 `CharField` 而非 PG 专属 `CIDRField`**：仓库需多库支持（PostgreSQL/MySQL/SQLite/Dameng/GaussDB…，见 CLAUDE.md），CIDR 校验在序列化器层用 `ipaddress` 做，不依赖数据库类型。
- `models/__init__.py` 追加 `from .network_white_list import *  # noqa`。
- 生成迁移：`make migrate` / `uv run python manage.py makemigrations system_mgmt`。

### 5.2 校验 / 规范化（序列化器 + 可选 model.clean）

`server/apps/system_mgmt/serializers/network_white_list_serializer.py`：

- `validate_network(value)`：
  - `net = ipaddress.ip_network(value.strip(), strict=False)`，非法 → `ValidationError`；
  - 裸 IP（无 `/`）自动成 `/32`、`/128`；
  - 存规范化字符串 `str(net)`；
  - **安全护栏**：拒绝 `0.0.0.0/0` 与 `::/0`（等于关闭全部防护）。
- 元数据网段无需在此拒绝——§5.4 保证其永远被硬挡，填进来也无效（但可在 UI 文案提示"元数据不会被放行"）。

### 5.3 缓存层 `server/apps/system_mgmt/utils/network_whitelist_cache.py`（仿 `pwd_policy_cache`）

```python
from django.core.cache import cache

NETWORK_WHITELIST_CACHE_KEY = "system_settings:network_white_list"
NETWORK_WHITELIST_CACHE_TTL = 300  # 5 分钟；写操作主动失效

def get_network_whitelist_cidrs() -> list[str]:
    """返回启用中的规范化 CIDR 字符串列表（缓存字符串，避免跨缓存后端 pickle 问题）。"""
    cached = cache.get(NETWORK_WHITELIST_CACHE_KEY)
    if cached is not None:
        return cached
    try:
        from apps.system_mgmt.models.network_white_list import NetworkWhiteList  # 延迟导入，避免 core→system_mgmt 顶层耦合
        rows = list(NetworkWhiteList.objects.filter(enabled=True).values_list("network", flat=True))
    except Exception:
        rows = []  # ★ fail-closed：表不存在 / app 未安装 / DB 异常 → 视为空白名单 → 维持严格
    cache.set(NETWORK_WHITELIST_CACHE_KEY, rows, NETWORK_WHITELIST_CACHE_TTL)
    return rows

def invalidate_network_whitelist_cache() -> None:
    cache.delete(NETWORK_WHITELIST_CACHE_KEY)
```

### 5.4 校验器改造 `server/apps/core/utils/ssrf_validator.py` —— `_is_blocked_ip`（核心）

判定顺序改为（这是全局生效的关键，所有 `validate()` 都过这里）：

```python
@classmethod
def _is_blocked_ip(cls, ip):
    ip_str = str(ip)

    # ① 云元数据永远硬挡（白名单不可覆盖）
    if ip_str in cls.CLOUD_METADATA_HOSTS:
        return True, f"云元数据地址 {ip_str}"
    for network in cls.CLOUD_METADATA_NETWORKS:      # 显式补上网段级元数据硬挡
        try:
            if ip in network:
                return True, f"云元数据地址 {ip_str}"
        except TypeError:
            continue

    # ② 白名单放行（私网黑名单之前）
    for cidr in cls._get_allowed_networks():
        try:
            if ip in cidr:
                return False, ""
        except TypeError:
            continue

    # ③ 私网 / 特殊地址黑名单
    for network in cls.BLOCKED_NETWORKS:
        try:
            if ip in network:
                return True, f"禁止的网段 {network}"
        except TypeError:
            continue
    return False, ""

@classmethod
def _get_allowed_networks(cls):
    """读取并解析白名单 CIDR（延迟导入 + fail-closed）。"""
    try:
        from apps.system_mgmt.utils.network_whitelist_cache import get_network_whitelist_cidrs
        return [ipaddress.ip_network(c, strict=False) for c in get_network_whitelist_cidrs()]
    except Exception:
        return []
```

- `validate()` 主流程不变；仅 `_is_blocked_ip` 的判定顺序与白名单逻辑变化。
- `validate_callback` / `validate_llm_endpoint` 不调 `_is_blocked_ip`、且本就放行私网，**不改**。
- 既有 `allowlist`（域名收紧）参数语义无关，保留不动；两者可正交组合。

### 5.5 管理 API

- `server/apps/system_mgmt/serializers/network_white_list_serializer.py`：`NetworkWhiteListSerializer(ModelSerializer)`，`fields="__all__"` + `validate_network`。
- `server/apps/system_mgmt/viewset/network_white_list_viewset.py`：`NetworkWhiteListViewSet(ModelViewSet)`：
  - 权限：独立资源 `network_white_list`——`@HasPermission("network_white_list-View", "system-manager")`（list/retrieve）/ `-Add`（create）/ `-Edit`（update/partial_update）/ `-Delete`（destroy），与 `api_secret_key` 等平台设置 tab 的权限范式一致。
  - 写操作（create/update/destroy）成功后：`invalidate_network_whitelist_cache()` + `log_operation(request, action, "system-manager", f"...内网白名单: {network}")`。
  - `created_by`/`updated_by` 由 `request.user` 注入（参考其它 system_mgmt viewset 写法）。
- `server/apps/system_mgmt/viewset/__init__.py` 导出；`server/apps/system_mgmt/urls.py` `router.register(r"network_white_list", NetworkWhiteListViewSet)` → `api/v1/system_mgmt/network_white_list/`。
- **权限 seed**：`server/support-files/system_mgmt/menus/system-manager.json` 的 `"Setting"` 组 `children` 追加：
  ```json
  { "id": "network_white_list", "name": "Network Whitelist", "operation": ["View", "Add", "Edit", "Delete"] }
  ```
  并视需要把 `network_white_list-*` 加入相应角色（`admin` 的 `menus: []` 默认全量；如需 `security` 角色可用则补 4 条）。

### 5.6 前端（web / system-manager，全栈范围）

落点：**平台设置（`/system-manager/settings`）新增「白名单」tab**，与 密钥/审计日志/错误日志 并列（截图里 门户/许可 是企业版注入，社区 menu.json 无）。tab 由 `constants/menu.json` 的 `"平台设置"/"Setting"` 组 `children` 驱动，页面落在 `(pages)/settings/<route>/page.tsx`，沿用密钥页范式（`TopSection` + antd `Table` + `PermissionWrapper`）。

- 菜单 tab：`web/src/app/system-manager/constants/menu.json` 的「平台设置」`children` 追加（**zh 与 en 两份都加**）：
  ```jsonc
  // zh
  { "title": "白名单", "url": "/system-manager/settings/network-whitelist", "icon": "<图标>", "name": "network_white_list" }
  // en
  { "title": "Network Whitelist", "url": "/system-manager/settings/network-whitelist", "icon": "<图标>", "name": "network_white_list" }
  ```
- 页面：`web/src/app/system-manager/(pages)/settings/network-whitelist/page.tsx`——antd `Table` 列出 CIDR / 备注 / 启停 / 创建时间 / 操作；新增/编辑 Modal（CIDR 输入 + 前端格式校验 + 备注 + 启停 Switch）；按钮包 `PermissionWrapper requiredPermissions={['Add'|'Edit'|'Delete']}`；文案提示"云元数据地址不会被放行"。参考实现：`(pages)/settings/key/page.tsx`。
- API：`web/src/app/system-manager/api/settings/index.ts` 的 `useSettingsApi()` 增 CRUD（`fetchNetworkWhiteList` / `createNetworkWhiteList` / `updateNetworkWhiteList` / `deleteNetworkWhiteList`），打 `/system_mgmt/network_white_list/`。
- i18n：社区版 locales 增 `system.settings.networkWhitelist.*` 文案（zh/en）。
- 注意事项：
  - web 前端有**企业版/社区版拆分**——社区端路由由 `prepare-enterprise.mjs` 自动生成（别手改生成产物），i18n 文案在社区版 locales。
  - worktree 内前端难跑，**前端验证去主仓库走 Storybook**（含整页/带数据场景），不启 dev server。

## 6. 安全边界与不变量（实现必须守住）

- ✅ 云元数据 `169.254.169.254`/`169.254.170.2`/`fd00:ec2::254` 永封；§5.4 的元数据检查排在白名单**之前**，即便有人把 `169.254.0.0/16` 填进白名单也无法暴露元数据。
- ✅ `0.0.0.0/0`、`::/0` 入库即被序列化器拒绝。
- ✅ fail-closed：白名单读取/解析任何异常 → 视为空 → 维持严格校验。
- ✅ 写权限收口到 `network_white_list-Add/Edit/Delete`（平台设置管理员），在 seed 文件注册。
- ⚠️ 已接受代价（设计 X）：白名单对 Agent 运行时 fetch/browser 同样生效（见 §3）。

## 7. 测试方案

**后端校验器**（`server/apps/core/tests/utils/test_ssrf_validator.py` 追加，mock `_get_allowed_networks` 或缓存函数）：

- 白名单内私网（如 `10.11.73.0/24` 覆盖 `10.11.73.15`）→ `validate` 通过；
- 不在白名单的私网（如 `10.0.0.1`）→ 仍抛 `SSRFError(禁止的网段)`；
- **元数据 `169.254.169.254` 即便加入白名单仍被挡**；
- 空白名单 → 与现状一致（既有严格模式用例全绿，零回归）；
- `0.0.0.0/0`/`::/0` 序列化器校验拒绝。

**system_mgmt**（`server/apps/system_mgmt/tests/`）：

- CRUD + 权限门（`security_settings-View/Edit`）；
- 序列化器 CIDR 规范化（裸 IP→/32）、非法值拒绝、超网拒绝；
- 写操作触发缓存失效（mock `invalidate_network_whitelist_cache` 断言被调）。

**前端**：Storybook（主仓库）覆盖列表/新增/编辑/校验态。

> 后端 pytest 在**主仓库**跑（worktree 缺 MINIO 等环境变量）；运行环境见 `server/.env` + `server/local_settings.py`，解释器 `D:\app\venv\bkliteserver`。

## 8. 改动文件清单

**后端（新增）**
- `server/apps/system_mgmt/models/network_white_list.py`
- `server/apps/system_mgmt/serializers/network_white_list_serializer.py`
- `server/apps/system_mgmt/viewset/network_white_list_viewset.py`
- `server/apps/system_mgmt/utils/network_whitelist_cache.py`
- `server/apps/system_mgmt/migrations/XXXX_networkwhitelist.py`（生成）

**后端（修改）**
- `server/apps/core/utils/ssrf_validator.py`（`_is_blocked_ip` 顺序 + `_get_allowed_networks`）
- `server/apps/system_mgmt/models/__init__.py`、`viewset/__init__.py`、`urls.py`
- `server/support-files/system_mgmt/menus/system-manager.json`（注册 `network_white_list` 权限资源）

**前端**
- `web/src/app/system-manager/(pages)/settings/network-whitelist/page.tsx`（新增）
- `web/src/app/system-manager/api/settings/index.ts`（`useSettingsApi` 增 CRUD）
- `web/src/app/system-manager/constants/menu.json`（平台设置组增「白名单」tab，zh/en）
- 社区版 i18n locales（`system.settings.networkWhitelist.*`，zh/en）

**测试**
- `server/apps/core/tests/utils/test_ssrf_validator.py`（追加）
- `server/apps/system_mgmt/tests/test_network_white_list*.py`（新增）

## 9. 兼容性与回滚

- 默认零回归：白名单空表时 `_is_blocked_ip` 行为与改造前等价。
- 回滚：删除/停用白名单条目即恢复严格；代码回滚仅需还原 `_is_blocked_ip`（其余为新增文件，互不影响）。
- 性能：`validate` 热路径上白名单走 5 分钟缓存 + 少量 CIDR 解析，开销可忽略。

## 10. 联调验证步骤（实现后）

1. 后端：`network_white_list` CRUD 接口通；新增 `10.11.73.0/24` 后查缓存失效生效。
2. skilltool「获取工具」填 `http://10.11.73.15:8000/sse` → 不再报 `禁止的网段`，进入真实 MCP 连接。
3. 反例：填未放行的 `http://10.0.0.1` → 仍被 `禁止的网段` 拦。
4. 元数据反例：白名单加 `169.254.0.0/16`，访问 `169.254.169.254` 仍被云元数据硬挡。
5. 前端：Storybook 验证列表/新增/编辑/校验态。
