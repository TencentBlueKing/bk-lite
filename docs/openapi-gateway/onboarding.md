# OpenAPI 统一网关 · 接入指南

BK-Lite 统一网关把对外 API 收口到 `https://<平台地址>/openapi/v1/<服务名>/*`：调用方只面对一个入口、一种凭据，认证 / 审计 / 限流由网关统一承担。

接入分两条路径，按被接入方形态选择：

| 路径 | 适用 | 面向 | 章节 |
| --- | --- | --- | --- |
| **外部服务接入** | 独立部署的 HTTP 服务（ITSM、审批系统、第三方 / 内网 API） | 平台运维 + 被接入方开发 | 第 1–7 节 |
| **内部接口接入** | BK-Lite 自身各应用（cmdb、monitor、patch_mgmt…）的已有函数 | bk-lite 后端开发 | 第 8 节 |

两者的对外契约一致（同一入口、同一凭据、同一错误码），差别只在注册方式：外部服务写 NATS KV（秒级生效、不发版），内部接口用装饰器声明（随版本发布）。

> 设计依据与契约冻结清单见 `specs/changes/openapi-unified-gateway/design.md`；
> 内部接入的代码级说明另见 `server/apps/core/openapi/README.md`。

---

---

# 第一部分 · 外部服务接入

## 1. 接入前置条件

| 条件 | 说明 |
| --- | --- |
| 服务可达 | 被接入服务与 BK-Lite 在同一 compose / K8s 网络内，Traefik 能以 `base_url` 直连 |
| 服务名 | 满足 `^[a-z][a-z0-9-]{0,31}$`；下划线开头为网关保留（`_me`、`_docs`、`_auth`、`_provider`） |
| 允许清单 | `base_url` 的主机必须落在 `OPENAPI_BASEURL_ALLOWLIST` 内，**缺省为空即拒绝一切**（fail-closed） |
| 身份传递方式 | 二选一，见第 3 节 |
| 网络封锁 | 接入后必须封锁该服务的直连端口，否则统一认证 / 审计 / 限流可被绕过 |

---

## 2. 接入四步

### 步骤 1：配置允许清单与密钥（server 侧 env）

在部署目录的 `.env` 中配置，然后重建 server 容器：

```bash
cd /opt/bk-lite/deploy/docker-compose-ha   # 单机栈为 .../docker-compose

# 允许清单：逗号分隔的主机名或 IP；后缀匹配按点边界（itsm-svc 不会放行 evil-itsm-svc）
echo 'OPENAPI_BASEURL_ALLOWLIST=itsm-svc,10.10.24.11' >> .env

# 共享密钥（信任头模式用）。变量名自定，注册条目里以 env: 引用它
echo 'ITSM_GW_SECRET=<32位随机串>' >> .env
```

密钥必须能被 **server 容器**读到。若变量名不在 `compose/server.yaml` 的 `environment` 中，需要补一行透传并重新渲染：

```yaml
# compose/server.yaml
    environment:
      - ITSM_GW_SECRET=${ITSM_GW_SECRET:-}
```

该 `environment:` 必须落在 **server 服务**名下（`compose/server.yaml` 的第一个 `environment:` 即是）。

```bash
set -a; source common.env; source ha.env; source .env; set +a   # 单机栈无 ha.env
docker compose -f compose/infra.yaml -f compose/postgres.yaml -f compose/monitor.yaml \
  -f compose/server.yaml -f compose/web.yaml -f compose/log.yaml -f compose/ha.yaml \
  config --no-interpolate > docker-compose.yaml
docker compose up -d server

# server 重建需约 1 分钟才就绪，后续验证前必须等待（仅 sleep 几秒会得到 404/解析错误）
for i in $(seq 1 24); do
  docker logs --tail 3 bk-primary-server-1 2>&1 | grep -q 'Application startup complete' && break
  sleep 10
done
```

> **重渲染前务必 `source` 全部 env 文件**（HA 栈的 `COMPOSE_PROJECT_NAME` 在 `ha.env` 里）。
> 漏 source 会让项目名变化、容器挂到全新空卷，等同数据丢失。
> 稳妥做法：先渲染到临时文件再 `diff docker-compose.yaml /tmp/new.yaml` 确认只有预期改动。

### 步骤 2：编写注册条目

```json
{
  "schema_version": 1,
  "type": "http",
  "base_url": "http://itsm-svc:8000",
  "strip_prefix": true,
  "paths": ["/tickets/*", "/approvals/*"],
  "auth_mode": "trusted-header",
  "shared_secret_ref": "env:ITSM_GW_SECRET",
  "required_roles": [],
  "rate_limit": { "average": 50, "burst": 100 },
  "doc_url": "http://itsm-svc:8000/swagger.json",
  "enabled": true
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `schema_version` | 否 | 固定 `1`，缺省按 1 处理 |
| `type` | 是 | 目前仅 `http` |
| `base_url` | 是 | 上游地址，须过允许清单；末尾斜杠会被去除 |
| `strip_prefix` | 否 | 默认 `true`：转发前去掉 `/openapi/v1/<服务名>` 前缀 |
| `paths` | 否 | 接口级白名单（`/x/*` 形式）；**省略表示该前缀下全部路径都被反代** |
| `auth_mode` | 是 | `trusted-header` 或 `service-token`，见第 3 节 |
| `shared_secret_ref` | 条件 | `trusted-header` 模式必填，形如 `env:VAR`，**只存引用不存明文** |
| `token_ref` | 条件 | `service-token` 模式必填，同上 |
| `required_roles` | 否 | 服务级粗粒度授权；**空数组 = 放行任意已认证身份** |
| `rate_limit` | 否 | `{average, burst}`，按调用方分桶 |
| `doc_url` | 否 | 该服务自身的接口文档地址，会出现在 `/openapi/v1/_docs` |
| `gateway_versions` | 否 | 挂载的网关契约版本，缺省挂载全部活跃版本 |
| `enabled` | 否 | 默认 `true`；置 `false` 即下线（一个拉取周期内生效） |

### 步骤 3：注册

```bash
cd /opt/bk-lite/deploy/docker-compose-ha
set -a; source common.env; set +a
export NATS_URL=tls://<本机IP>:4222
export NATS_CA_FILE=$PWD/conf/certs/ca.crt

wxc openapi validate -n itsm -f itsm.json      # 写前预检（结构与枚举）
wxc openapi register -n itsm -f itsm.json --probe itsm-svc:8000
wxc openapi list                                # 确认已写入
```

`--probe` 会从本机探测该服务的直连端口：**可达即告警**——注册进网关的服务必须同步封锁直连入口。

封锁直连的做法按部署形态选其一（网关经 compose 内网访问上游，不受影响）：

- **同栈 compose 服务**：移除该服务的宿主端口映射（`ports:`），只保留 `expose`，容器间仍可互通；
- **独立主机上的服务**：用防火墙 / 安全组只放行 Traefik 所在主机的来源 IP；
- 改完用 `wxc openapi register ... --probe <host:port>` 复测，输出应为 `✓ 直连探测：目标端口不可直达`。

> `validate` 只做本地结构校验。`base_url` 是否在允许清单内、`env:` 引用能否解析，由 server 渲染器权威判定，以 `wxc openapi list` 与实际路由为准。

### 步骤 4：验证生效

```bash
TOKEN=<API 令牌>       # 在「系统管理 → API 密钥」页自助生成
BASE=https://<平台地址>:<端口>

# 目录里应出现该服务，kind=external
# 注意：server 多 worker 时该列表来自各自进程内的快照，刚注册后可能要多请求几次
# 才会出现；以下面的实际调用是否连通为准，不要仅凭 _docs 判断接入失败
curl -sk -H "Authorization: Bearer $TOKEN" $BASE/openapi/v1/_docs | jq '.data.services'

# 无凭据必须被网关挡回 401
curl -sk -o /dev/null -w '%{http_code}\n' $BASE/openapi/v1/itsm/tickets/list

# 带凭据应穿透到上游
curl -sk -H "Authorization: Bearer $TOKEN" $BASE/openapi/v1/itsm/tickets/list
```

路由在**一个拉取周期（5 秒）**内生效。若未生效，见第 6 节排查。

---

## 3. 两种身份传递模式

> **先按上游是否自带鉴权选模式**：上游若有自己的 Bearer / API Key 认证（多数第三方
> API、LLM 服务属此类），必须用 `service-token`——网关会用 `token_ref` 的值覆盖
> `Authorization` 头；若错用 `trusted-header`，上游会因收到平台令牌而返回
> `Invalid token` 之类的鉴权失败。上游若能读 `X-BK-*` 身份头（与平台同用户体系），
> 才用 `trusted-header`。

### 信任头模式 `trusted-header`（推荐）

网关认证后向上游注入身份头，上游据此识别用户：

```http
POST /tickets/create HTTP/1.1
X-BK-Gateway-Auth: <shared_secret_ref 解引用后的共享密钥>
X-BK-User: zhangsan@domain.com
X-BK-Team: 2
```

- `X-BK-User`：`用户名@域`，ASCII 稳定标识；
- `X-BK-Team`：逗号分隔的组织 id。API 令牌为其绑定组织（单值）；登录态 JWT 为用户全部直属组织；
- `X-BK-Gateway-Auth`：网关与该服务之间的共享密钥，**上游的唯一信任根**。

网关同时会**清空转发给上游的 `Authorization` 头**：上游按身份头识别用户即可，不应看到
调用方的平台凭据（否则上游可凭其冒充调用方回调平台）。

适用：上游与平台用户体系已打通。

### 服务账号模式 `service-token`

网关注入上游自己颁发的服务令牌（`Authorization: Bearer <token_ref 解引用>`），上游按自身体系认证该服务账号；`X-BK-User` 仅作审计参考。

适用：用户体系未打通、或上游改不动。代价是上游侧无法做用户级授权。

---

## 4. 上游服务侧如何处理身份（信任头模式）

```python
def gateway_identity_middleware(request):
    # 1. 共享密钥校验 —— 唯一信任根，常数时间比较；缺失或不符一律拒绝
    if not hmac.compare_digest(
        request.headers.get("X-BK-Gateway-Auth", ""), GW_SHARED_SECRET
    ):
        return reject_401()

    # 2. 解析身份
    user_id = request.headers["X-BK-User"]          # user@domain
    teams = [int(t) for t in request.headers.get("X-BK-Team", "").split(",") if t]

    # 3. 映射本地用户（同体系直查 / 首次自动建影子账号 / 拒绝，按集成策略定）
    local_user = resolve_or_provision(user_id)

    # 4. 以 teams 为本次请求的数据域边界，接入自身权限模型
    request.ctx = Context(user=local_user, teams=teams)

    # 5. 审计：X-On-Behalf-Of 仅记录并标注「自报、未经验证」，不参与鉴权
    audit_log(actor=user_id,
              on_behalf_of=request.headers.get("X-On-Behalf-Of"),
              on_behalf_verified=False)
```

**三条禁令**

1. 不得信任任何未通过 `X-BK-Gateway-Auth` 校验的 `X-BK-*` 头；
2. 不得把 `X-BK-*` 头继续透传给更下游系统（防止信任链被隐式延长）；
3. 不得以来源 IP 白名单代替密钥校验（网络拓扑一变即失效）。

---

## 5. 调用方须知

| 项 | 约定 |
| --- | --- |
| 入口 | `https://<平台地址>/openapi/v1/<服务名>/<上游路径>` |
| 凭据 | `Authorization: Bearer <API 令牌 或 登录态 JWT>`，**不接受 Cookie** |
| 令牌获取 | 「系统管理 → API 密钥」自助生成，绑定「用户 × 组织」，仅展示一次 |
| 内省 | `GET /openapi/v1/_me` 返回自身身份、授权组织、可用服务清单 |
| 目录 | `GET /openapi/v1/_docs` 返回接口目录（内部端点含 schema，外部服务给 `doc_url`） |

**响应格式**：内部应用统一为 `{"result": true, "data": ...}` / `{"result": false, "code": "...", "message": "..."}`；
**外部服务为透传**——上游返回什么，调用方拿到什么，网关只保证认证与限流层面的统一。

常见错误码：

| 状态码 | code | 含义 |
| --- | --- | --- |
| 401 | `AUTH_INVALID` | 凭据无效或缺失 |
| 403 | `ROLE_REQUIRED` | 未满足该服务的 `required_roles` |
| 404 | `NOT_FOUND` | 服务未注册 / 路径不在 `paths` 白名单 |
| 429 | `RATE_LIMITED` | 触发限流（带 `Retry-After`） |
| 502 | `UPSTREAM_UNREACHABLE` | 上游不可达 |

---

## 6. 排查

**症状：注册成功但调用返回 404**

按顺序查（大部分问题在前两条）：

```bash
# 1. 条目是否被渲染器丢弃？——最常见原因：base_url 不在允许清单、env 引用解析不了
docker exec <server容器> sh -c \
  'curl -s -H "X-Provider-Token: $OPENAPI_PROVIDER_TOKEN" \
   http://127.0.0.1:8000/openapi/v1/_provider/traefik' | jq '.http.routers'

# 2. Traefik 是否消费到动态路由？
docker exec <traefik容器> wget -qO- http://127.0.0.1:8080/api/http/routers \
  | jq '[.[] | select(.provider=="http") | {name, status}]'

# 3. Traefik 拉取是否报错
docker logs --since 5m <traefik容器> 2>&1 | grep -i "provider error"
```

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 步骤 1 中 `routers` 为空 | 条目被跳过 | 查 server 日志中 `openapi_registry 条目 X 被跳过：<原因>` |
| 跳过原因 `base_url not in allowlist` | 允许清单未含该主机 | 补 `OPENAPI_BASEURL_ALLOWLIST` 并重建 server |
| 跳过原因 `shared_secret_ref unresolvable` | server 容器内没有该 env | 见步骤 1 的透传配置 |
| 步骤 2 中查不到 router | Traefik 未拉到配置 | 查步骤 3 的错误；注意 server 重启期间的 `connection refused` 属正常瞬时现象 |
| `provider error` 报连接被拒 | server 未就绪 | 等待 server 启动完成，Traefik 会自动重试 |

**症状：调用返回 401 但凭据正确** —— 确认用的是 `Authorization: Bearer`（不接受 Cookie）；确认令牌未被删除；令牌吊销存在缓存延迟。

**症状：上游收不到 `X-BK-*` 头** —— 确认注册条目是 `trusted-header` 模式；确认上游读的是网关注入的头而非自建认证。

---

## 7. 下线与变更

```bash
# 下线：置 enabled=false 后重新 register，一个拉取周期内路由消失
# 顺序很重要：先确认路由已下线，再解除网络封锁
wxc openapi list                      # 确认状态
```

变更 `base_url` / `paths` / 限流：改条目重新 `register` 即可，秒级生效，无需发版或重启。

---

---

# 第二部分 · 内部接口接入

## 8. 内部接口接入规范

把 BK-Lite 某个应用的已有函数暴露为对外 API。与外部服务不同，内部接口的暴露是
**代码级声明**：随版本发布，受编译期（启动期）校验与 CI 门禁约束。

### 8.1 基本原则

1. **默认全关，显式 opt-in**：未声明 `@openapi_expose` 的函数一律不可经网关调用（返回 404）。不存在"批量暴露"开关。
2. **fail-closed**：契约声明不完整时**在 server 启动阶段直接报错**（`ImproperlyConfigured`），不会带病上线。
3. **schema 即契约**：对外暴露的字段名与类型一经发布即冻结，内部重构不得波及。
4. **暴露 ≠ 免鉴权**：网关只解决"谁在调用"，数据可见范围仍由函数自身的组织过滤逻辑负责——这是暴露方的责任，见 8.5。

### 8.2 四步接入

**① 写暴露专用 serializer**（`apps/<app>/openapi_serializers.py`）

```python
from rest_framework import serializers
from apps.core.openapi.serializers import PaginatedRequestSerializer

class ModuleDataQuerySerializer(PaginatedRequestSerializer):
    module = serializers.ChoiceField(choices=["patch_target"])
    group_id = serializers.IntegerField(min_value=1)
```

- **禁止复用内部业务 serializer**：内部迭代改字段会静默破坏对外契约；
- 禁止 `fields = "__all__"`：新增字段会意外外泄；
- 基类已内建：未知字段拒绝（客户端身份字段无从混入）、分页钳制（`page` 1-based、`page_size` 默认 20 / 上限 500、越限钳制而非报错）。

**② 叠加装饰器**（与 `@nats_client.register` 共存，不影响原有 NATS 调用）

```python
@nats_client.register
@openapi_expose(
    path="patch-mgmt/module-data",     # service/sub-path，发布后永久固定
    method="GET",                       # GET 走 query string；写方法走 JSON body
    schema=ModuleDataQuerySerializer,   # 必填
    inject="team_list",                 # 或 "user_info"，见 8.3
    permission="patch_mgmt-View",       # 可选；声明时必须同时给 permission_app
    permission_app="patch",
    summary="…（须写明组织口径：是否级联子组织）",
)
def get_patch_mgmt_module_data(module, child_module, page, page_size, group_id, *, team=None):
    ...
```

其余可选参数：`param_map`（schema 字段 → 函数形参的显式映射，用于内部重命名形参而不动契约）、`team_free`（见 8.4）。

**③ 写双租户测试并登记**（合并的硬性门禁）

用 `apps/core/openapi/testing.py` 的基建构造两个组织身份，断言读隔离与写归属，然后登记到 `apps/core/openapi/tests/tenant_coverage.py`：

```python
TENANT_ISOLATION_COVERAGE = {
    "patch-mgmt/module-data": [
        "apps.core.openapi.tests.test_gateway::test_tenant_cannot_read_other_org",
    ],
}
```

未登记或引用失效时 `test_governance.py` 失败，**CI 拒绝合并**。

**④ 过命名与契约评审**（见 8.6 checklist）

### 8.3 两种身份注入协议

按被暴露函数**已有的**组织参数形态选择，无需改造函数：

| `inject` | 函数期待 | 网关注入 | 语义 |
| --- | --- | --- | --- |
| `team_list` | `*, team=None` | API 令牌 → `[绑定组织]`；JWT → 用户全部直属组织 | 函数按注入集合做精确成员校验（**不级联**子组织） |
| `user_info` | `user_info=None` | 仅注入 `{user, domain}`；组织锚点为业务参数 | 函数自查 `group_list` 并**级联展开**子组织 |

两点必须写进 `summary` 并对调用方讲清：

- **可见范围口径不同**：同一用户经两类接口能看到的组织范围可能不同（历史实现差异，非有意的权限模型）；
- **锚点式的锚点必须是调用者的直属组织**：传入真实存在但非直属的子组织 id 会**静默返回空结果**而非报错。

API 令牌为单组织收窄凭据：锚点式下网关**强制覆盖**客户端传入的锚点为令牌绑定组织。

### 8.4 `team_free` 的适用与约束

仅用于**不含任何组织维度数据**的公共元信息接口（如枚举字典、版本信息）。声明后网关不注入任何组织上下文，因此：

- 必须附带"响应不含组织相关字段"的断言测试；
- 须经 CODEOWNERS 安全评审签字；
- 审计日志对此类调用打标。

`team_free=True` 与 `inject` 互斥（同时声明会启动报错）。

### 8.5 暴露方的数据域责任（最容易出事的一条）

网关能保证"注入的身份不可伪造"，**不能保证"函数用了这个身份"**。一个签名完全合规、却在函数体里 `Model.objects.all()` 的函数，会安静地跨租户泄漏数据——请求返回 200，无任何报错。

因此：

- 每条查询必须经过组织过滤（`build_json_membership_query` 等既有 helper），写操作必须校验目标对象归属；
- 越权应返回明确拒绝（网关会将组织越权类软错误映射为 `403 TEAM_OUT_OF_SCOPE`）；
- **双租户测试是唯一能验证"注入被真正使用"的手段**，故列为准入门槛而非建议。

### 8.6 评审 checklist

`@openapi_expose` 与暴露 serializer 的任何变更须经 API 设计责任人评审：

- [ ] schema 字段命名与全平台一致（组织概念统一字段名，不把内部 NATS 字段名直接透传为对外契约）；
- [ ] 每条查询经过组织过滤，写操作校验目标归属；
- [ ] 已发布字段未被改名 / 收紧 / 删除——**破坏性变更必须以新 path（或新版本段）发布**；请求 schema 只能新增可选字段，响应只能新增字段；
- [ ] 函数短耗时、强制分页；长任务已拆为「提交 + 查询」两个接口；
- [ ] 双租户测试已登记；`team_free` 有豁免理由与断言测试；
- [ ] `summary` 写明组织口径。

### 8.7 发布后不可变的契约面

以下一经发布即冻结（详见设计文档第 8 章冻结清单）：`path` 字符串、serializer 字段名与类型、响应结构、`inject` 形状与组织口径、错误码语义。内部实现（函数名、形参名、内部 serializer、调用链）可自由重构——前提是经 `param_map` 与暴露专用 serializer 与契约解耦。

### 8.8 自检与排查

```bash
# 已暴露的内部端点清单（含 schema 内省）
curl -sk -H "Authorization: Bearer $TOKEN" $BASE/openapi/v1/_docs | jq '.data.services[] | select(.kind=="internal")'
```

| 现象 | 原因 |
| --- | --- |
| server 启动即报 `ImproperlyConfigured` | 装饰器声明不完整：缺 schema / 缺 inject / 身份参数缺失 / path 非法 / 重复注册。错误信息直指函数名与缺失项 |
| 调用返回 404 | 该函数未声明 `@openapi_expose`，或 path / method 不匹配 |
| 返回 400 `SCHEMA_INVALID` | 请求含 schema 未声明的字段（含试图传 `team`、`user_info` 等身份字段——设计如此） |
| 返回 403 `PERM_MISSING` | 未满足装饰器声明的 `permission` |
| 返回 403 `TEAM_OUT_OF_SCOPE` | 业务组织参数越出注入的授权集合 |
| CI 报未登记双租户测试 | 补测试并登记到 `tenant_coverage.py` |

---

## 附：完整接入示例（内网 LLM API，已实测通过）

把内网 LLM 服务 `http://10.10.24.11:3000` 接入为 `llmapi`。该上游**自带 Bearer 鉴权**，
因此用 `service-token` 模式注入它自己的 key：

```bash
cd /opt/bk-lite/deploy/docker-compose-ha

# 1. 允许清单 + 上游自己的 API key
echo 'OPENAPI_BASEURL_ALLOWLIST=10.10.24.11' >> .env
echo 'LLMAPI_UPSTREAM_TOKEN=<上游的 API key>' >> .env
# compose/server.yaml 的 server 服务 environment 补一行：
#   - LLMAPI_UPSTREAM_TOKEN=${LLMAPI_UPSTREAM_TOKEN:-}

set -a; source common.env; source ha.env; source .env; set +a
docker compose -f compose/infra.yaml -f compose/postgres.yaml -f compose/monitor.yaml \
  -f compose/server.yaml -f compose/web.yaml -f compose/log.yaml -f compose/ha.yaml \
  config --no-interpolate > docker-compose.yaml
docker compose up -d server
for i in $(seq 1 24); do
  docker logs --tail 3 bk-primary-server-1 2>&1 | grep -q 'Application startup complete' && break
  sleep 10
done

# 2. 注册条目
cat > llmapi.json <<'EOF'
{
  "schema_version": 1,
  "type": "http",
  "base_url": "http://10.10.24.11:3000",
  "strip_prefix": true,
  "auth_mode": "service-token",
  "token_ref": "env:LLMAPI_UPSTREAM_TOKEN",
  "required_roles": [],
  "enabled": true
}
EOF

export NATS_URL=tls://10.10.41.149:4222 NATS_CA_FILE=$PWD/conf/certs/ca.crt
wxc openapi validate -n llmapi -f llmapi.json
wxc openapi register -n llmapi -f llmapi.json --probe 10.10.24.11:3000
wxc openapi list

# 3. 验证（TRAEFIK_WEB_PORT 见 .env）
BASE=https://10.10.41.149:${TRAEFIK_WEB_PORT}
curl -sk -o /dev/null -w '%{http_code}\n' $BASE/openapi/v1/llmapi/v1/models   # 期望 401
curl -sk -H "Authorization: Bearer $TOKEN" $BASE/openapi/v1/llmapi/v1/models  # 期望模型列表
```

调用方此后即可用**平台令牌**访问该 LLM 服务，无需持有上游 key——上游 key 只存在于
server 的环境变量中，由网关注入。
