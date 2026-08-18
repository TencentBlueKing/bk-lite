# OpenAPI 统一网关 · 外部服务接入指南

面向把一个已有 HTTP 服务（ITSM、审批系统、第三方 API 等）接入 BK-Lite 统一网关的**平台运维**与**被接入方开发**。

接入后的效果：调用方只面对 `https://<平台地址>/openapi/v1/<服务名>/*` 一个入口、一种凭据，认证 / 审计 / 限流由网关统一承担；被接入服务不需要自建认证。

> 设计依据与契约冻结清单见 `specs/changes/openapi-unified-gateway/design.md`。

---

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
