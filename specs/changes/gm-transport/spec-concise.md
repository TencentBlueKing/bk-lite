# SM2/SM3/SM4 国密与防重放技术方案

- 最近更新：2026-10-15
- 状态：方案已评审，未实现

## 背景与目标

等保密码应用要求前后端通信支持 SM2、SM3、SM4，并可开关。浏览器不支持国密 TLS（TLCP），本次只做应用层：BK-Lite 前端给请求套信封，Django 中间件解开，现有视图仍看到原来的方法、查询参数和正文；同一把一次性 SM4 密钥再加密这次响应。开关关闭时，请求和响应与今天一致。

信封自带防重放：同一份信封字节再次到达时被拒绝，视图只执行一次。

| 算法 | 作用 |
|---|---|
| SM2 | 加密客户端每次现生成的 SM4 密钥。公钥下发，私钥只在服务端 |
| SM4-CBC | 加密查询参数、请求正文和响应正文 |
| HMAC-SM3 | 分别覆盖请求信封和响应信封 |

## 非目标

- 不部署 TLCP，不改 Traefik 证书；不对齐 GM/T 0125，不用 SM4-GCM。
- 不加密、不去重没有信封的请求：直接打到 `/api/v1/` 的脚本、`/openapi/v1/`、NATS、采集端、移动端。开关打开也不拒绝这些明文请求。
- 不加密请求头和响应头，包括 `Authorization` 中的 Bearer token。
- 不改口令哈希（PBKDF2）和凭据落库加密（AES-CBC、Fernet）。
- 不把 SM2 私钥写入 `SystemSettings`（`get_sys_set` 会返回整表）。
- 不代替业务幂等：用户连点两次是两份新信封，都会进视图。

## 待定与需要注意

| 事项 | 性质 | 位置 |
|---|---|---|
| GET 请求带不上信封正文 | 待定，按实际实现确定 | 信封 |
| 纯 Python 加解密性能、大文件内存 | 需要注意 | 密码参数 |
| 登录后多传一份明文口令 | 优化项 | 前端 |
| 用户电脑时钟偏差 | 部署要求，缓解方式待定 | 部署 |
| 浏览器原生加载、密钥分离、ASGI 流式、密评边界 | 重要但不阻塞 | 文末同名一节 |

## 总体数据流

```
BK-Lite 前端
  读取开关与 SM2 公钥（明文，登录前可访问）
  生成 SM4 密钥、IV、nonce、ts
  SM4-CBC 加密「查询串 + 原始正文」
  SM2 公钥加密 SM4 密钥
  HMAC-SM3 覆盖方法、路径、ts、nonce、类型、IV 和密文
  发往 /api/proxy/...    正文为信封 JSON，URL 上不再带业务查询参数
        │
        ▼
Next.js /api/proxy/[...path]     原样转发到  {NEXTAPI_URL}/api/v1/...
        │
        ▼
GmTransportMiddleware
  校验时间窗与 MAC → 占用 nonce → 解密 → 写回 query 与 body
        │
        ▼
现有认证、权限、视图             不感知国密，仍返回明文
        │
        ▼
GmTransportMiddleware
  用同一把 SM4 密钥加密响应正文，回写信封
        │
        ▼
Next.js 原样转发响应
        │
        ▼
BK-Lite 前端用手里的 SM4 密钥解开响应，然后丢弃这把密钥
```

请求加密在前端完成，响应加密在 Django 中间件完成，Next 代理两个方向都只转发密文。

## 密码参数

前端用 `sm-crypto`（SM2 `cipherMode = 1`，SM4 `mode = 'cbc'`），服务端用 PyPI `gmssl`。两端用同一份固定测试向量验收。

| 项 | 取值 |
|---|---|
| SM2 密文 | C1C3C2，十六进制，不带 `04` 前缀 |
| SM2 公钥 / 私钥 | 128 / 64 个十六进制字符；公钥为 `X \|\| Y`，库要求 `04` 时只在库边界补 |
| SM4 密钥、IV | 各 16 字节，每次请求用密码学随机数新生成 |
| nonce | 16 字节随机数，32 个十六进制字符 |
| 填充 | PKCS#7 |
| HMAC | HMAC-SM3，密钥为本次 SM4 密钥；先加密后 MAC |
| 编码 | `ek`、`iv`、`ct`、`mac` 用标准 Base64；公钥、私钥、nonce 用十六进制 |
| 时间窗 | 300 秒 |

**需要注意：性能。** 纯 Python `gmssl` 的 SM4 实测约 0.46MB/s，200MiB 采集包解密约 7 分钟，并长时间占住 uvicorn worker 的 GIL；服务端已依赖的 `cryptography` 约 57MB/s。SM4 和 HMAC-SM3 优先评估 `cryptography`，SM2 仍用 `gmssl`（解密每次约 3 毫秒）。前端 `sm-crypto` 和服务端 `json.loads` 处理大文件信封都会占用数倍内存；大文件上传改二进制分帧还是列为本期例外，按实测确定。

## 信封

请求头 `X-Gm-Transport: 1` 表示正文是信封，中间件只按这个头分流，不靠解析 JSON 判断。线上 `Content-Type` 固定为 `application/json`，业务原始类型放在 `cty`。

```json
{
  "v": 1,
  "ts": 1760490000000,
  "nonce": "32 个十六进制字符",
  "kid": "公钥标识",
  "method": "POST",
  "path": "/core/api/login/",
  "cty": "application/json",
  "ek": "Base64，SM2 密文",
  "iv": "Base64，16 字节",
  "ct": "Base64，SM4-CBC 密文",
  "mac": "Base64，HMAC-SM3 的 32 字节"
}
```

- `path`：`/api/v1` 之后的路径，以 `/` 开头并带尾部 `/`（Next 代理会补斜杠）。中间件拿去掉 `/api/v1` 后的 `request.path` 比对，少尾部斜杠视为不一致。
- `method` 大写；`ts` 为客户端 Unix 毫秒；`nonce` 每次新生成。

**明文格式**（二进制）：4 字节大端无符号整数表示查询串长度，接着是查询串的 UTF-8 字节（不含 `?`），其余全部是原始正文。multipart 上传保留原始字节，`cty` 带 boundary。开关打开后业务查询参数不再出现在 URL 上。

**MAC 输入**：下列各行以 `\n` 连接，末行后不加换行。

```
1
{ts}
{nonce}
{METHOD}
{path}
{cty}
{iv 的 Base64}
{ct 的 Base64}
```

MAC、填充、SM2 解密失败对外返回同一个错误，不暴露失败原因。

**待定：GET 带不上正文。** XHR 会静默丢弃 GET/HEAD 的正文，浏览器和 Node 的 `fetch` 会直接抛错；DELETE、PUT、PATCH 不受影响。候选做法：开关打开时 GET 线上改发 POST，真实方法只写在信封 `method`，中间件解开后改写 `request.method`，校验顺序第 2 步改为比对信封内方法。只改 GET 还是统一走 POST，按实际实现确定。

## 防重放

采用「时间窗 + nonce + MAC 绑定」，服务端用 Redis 记录用过的 nonce：

| 组成 | 作用 | 缺了它会怎样 |
|---|---|---|
| `ts` | 信封只在服务器时间 ±300 秒内有效 | nonce 记录必须永久保存 |
| `nonce` | 有效期内唯一标识这份信封 | 300 秒内同一份信封可提交任意次 |
| MAC 绑定 | 把 `ts`、`nonce` 与方法、路径、`cty`、IV、密文绑在一起 | 改 `ts` 续命、改 `nonce` 绕过去重 |
| Redis nonce 记录 | `cache.add` 即 `SET NX EX`，多 worker 共享、原子判断 | 识别不出第二次提交 |

MAC 密钥被 SM2 加密在 `ek` 里，抓包者算不出新 MAC，改不动 `ts` 和 `nonce`；他自己另造信封属于新请求，要过登录和权限。响应用本次独有的密钥，MAC 绑定本次 `nonce`，不另做去重。

**判定规则**：MAC 正确、`ts` 在窗口内、`nonce` 在 Redis 中首次出现，三者同时满足才接受；前两项通过后才写 nonce。

**时间窗**：两端都用 Unix 纪元毫秒（前端 `Date.now()`，服务端 `time.time_ns() // 1_000_000`），与时区无关。`abs(server_now_ms - ts) > 300000` 返回 `gm_transport_expired`。

**nonce 记录**：键 `gm_transport:nonce:{nonce}`，走 Django 默认缓存。TTL 算到这份 `ts` 离开窗口的时刻，否则 `ts` 偏快的信封会在窗口关闭前失去记录：

```
ttl_seconds = max(1, ceil((ts + 300000 - server_now_ms) / 1000))
```

默认缓存不是 Redis（`locmem` 无法跨 worker 去重）时，带信封的请求返回 `gm_transport_unavailable`。

**校验顺序**（不能颠倒，否则错误 MAC 也能占掉别人的 nonce）：

1. 解析 JSON；不是对象、缺字段、`v` 不是 1 → `gm_transport_rejected`
2. `method`、`path` 与当前请求不一致 → `gm_transport_rejected`
3. `ts` 超窗 → `gm_transport_expired`
4. `kid` 不匹配 → `gm_transport_rejected`；私钥缺失 → `gm_transport_unavailable`
5. SM2 解出 SM4 密钥失败 → `gm_transport_rejected`
6. 恒定时间比较 MAC 失败 → `gm_transport_rejected`（此时未写 nonce）
7. 默认缓存不是 Redis → `gm_transport_unavailable`
8. `cache.add` 键已存在 → `gm_transport_replay`；缓存抛错 → `gm_transport_unavailable`
9. SM4 解密、PKCS#7 或长度前缀失败 → `gm_transport_rejected`（不回滚 nonce）

**客户端重试**：任何重试都重新生成 `ts`、nonce、IV 和 SM4 密钥，禁止重发已发出的信封字节；重试点放在包装函数之外。

## 密钥与开关

**私钥**：环境变量 `GM_SM2_PRIVATE_KEY`，缺失时服务照常启动。公钥由私钥导出；`kid` 为 SM3(公钥 64 字节) 的前 8 字节，16 个十六进制字符。不支持多密钥并存。

**开关**：`SystemSettings` 键 `enable_gm_transport`，`"0"` / `"1"`，缺省 `"0"`。放在安全策略页（`/system-manager/user/security-settings`，与 OTP 同页），读写走现有 `get_sys_set` / `update_sys_set`，权限 `security_settings-View` / `-Edit`。中间件不读开关，只看请求头；开关只决定前端是否发信封。

**公钥接口**：`GET /api/v1/core/api/gm_transport_public/`，`AllowAny`，不走信封、不占 nonce。

| 状态 | `data` |
|---|---|
| 开关关闭 | `{"enabled": "0"}` |
| 开启且就绪 | `{"enabled": "1", "kid": "...", "public_key": "..."}` |
| 开启但未就绪（私钥缺失或不合法、缓存不是 Redis） | `{"enabled": "0", "degraded": "1"}`，不返回原因 |

**拉取与缓存**：结果在内存缓存 5 分钟。

- 首次需要时拉取，并发请求只拉一次。
- `kid` 不匹配、`gm_transport_unavailable`、本页保存了国密开关时立即重新拉取。前两种情况重新拉取后自动重发一次：仍开启就用新信封，已降级就发明文。`unavailable` 发生在视图执行之前，重发不会重复执行业务。
- 公钥接口拉取失败时，本次按 `enabled = "0"` 发送，结果不缓存。
- 开关从关切到开，已打开的页面最长 5 分钟内仍发明文。

**故障兜底**：前端只在服务端返回「已开启且就绪」而自身加密失败时拒发请求，其余故障都降级为明文，避免锁死后连开关都关不了。能挡住公钥接口的主动攻击者本来就能换掉公钥，降级的安全代价有限。

1. 开启前自检：改为 `"1"` 前检查私钥合法、缓存是可写的 Redis，并完整跑一遍 SM2、SM4、HMAC 往返；不通过拒绝保存。改为 `"0"` 不做自检。
2. 运行中未就绪自动降级：公钥接口返回 `degraded = "1"`，前端发明文，安全策略页显示「已开启，未生效」。服务端日志记录原因，同一进程同一原因只记一次 ERROR。
3. 运维命令强制关闭：在 server 容器内执行 `python manage.py disable_gm_transport`（放在 `system_mgmt/management/commands/`，用 ORM 写回 `"0"`，幂等）。

## 后端中间件

`apps.core.enterprise.gm_transport_middleware.GmTransportMiddleware`，企业包在运行目录时挂在 `SecurityMiddleware` 之后、`SessionMiddleware` 之前，请求进来时还原、响应离开时加密。没有企业包则不注册。

- 路径不以 `/api/v1/` 开头、是公钥接口、或没有 `X-Gm-Transport: 1`：原样放行。
- 有该头：先查体积，再按校验顺序验证。成功后写回查询串和正文，`CONTENT_LENGTH` 改为明文长度，`Content-Type` 改回 `cty`，删除 `X-Gm-Transport`；SM4 密钥留在请求对象上供响应加密，视图和日志读不到。
- 失败返回明文 `{"result": false, "message": "..."}`，文案来自 `core` 语言包。日志只记路径、`kid`、`error_type`，不记正文、查询串、密钥、MAC、nonce；解密失败不打 traceback。

**体积**：不经 `request.body` 读信封（Django 默认 2.5MB 上限会挡住大文件）。按原始流读取，信封上限 280MiB，覆盖 200MiB 采集包明文经 Base64 膨胀后的体积；超限返回 `gm_transport_too_large`，不占 nonce。解密结果写入可溢出到临时文件的流。

## 响应

请求解开后，中间件用同一把 SM4 密钥加密响应正文，不再做 SM2。截获响应的人读不了；自己造合法信封的调用方只能解开自己这次的响应，加密不代替登录和权限。

**保持明文**：没有信封的请求、公钥接口、请求信封自身的失败、204/304 等无正文响应、Next 代理自己生成的 500/504。密钥解出之后，JSON、业务错误、文件下载和 SSE 一律加密，不允许加密失败后改发明文。

**普通响应**：HTTP 状态不变，`Content-Type` 改为 `application/json`，加响应头 `X-Gm-Transport: 1`。

```json
{
  "v": 1,
  "nonce": "与请求相同",
  "seq": 1,
  "status": 200,
  "cty": "application/json",
  "iv": "Base64，新的 16 字节",
  "ct": "Base64，SM4-CBC 密文",
  "mac": "Base64，HMAC-SM3 的 32 字节"
}
```

MAC 输入：`1`、`resp`、`{nonce}`、`{seq}`、`{status}`、`{cty}`、`{iv 的 Base64}`、`{ct 的 Base64}` 以 `\n` 连接，末行后不加换行。客户端校验 `nonce` 等于本次请求、`status` 等于 HTTP 状态、`seq` 为 1。明文超过 200MiB 返回明文的 `gm_transport_too_large`。

**流式响应**：视图每产出一块就加密成一帧，线上仍是 `text/event-stream`（Next 代理才会走 SSE 分支）。每帧是一条 SSE 事件，`data` 为上面的信封 JSON，`seq` 从 1 递增；客户端缺号、乱序或 MAC 失败即终止。累计超过 200MiB 时发一帧加密的 `gm_transport_too_large` 后结束。响应头（如文件名）不进信封。

## 前端

`web/src/utils/gmTransport.ts` 是前端唯一的加解密入口，实现从企业包加载；没有企业包时这些调用保持明文。必须接在两个出口上：`request.ts` 的 axios 请求与响应拦截器，以及登录等没有 token 时直接调用的 `fetch('/api/proxy/...')`。绕过它的调用会发出明文，中间件也会放行，所以实施时要清点并收拢。Next 代理只透传，不解密、不缓存正文，日志不记查询串和正文。

`enabled = "1"` 时，包装函数：取公钥和 `kid` → 生成 SM4 密钥、IV、nonce 和 `ts` → 把查询串移出 URL → 正文取原始字节（`FormData` 先序列化为 multipart）→ 设置 `X-Gm-Transport: 1` 与 `Content-Type: application/json`。收到带 `X-Gm-Transport: 1` 的响应时用本次密钥解开，流式响应按 `seq` 逐帧解密，读完丢弃密钥。不把密钥、nonce 或信封写入 `sessionStorage` / `localStorage`。

**优化项**：`SigninClient.tsx` 调 `signIn("credentials")` 时传了 `password: nextPassword ?? password`，走 `/api/auth/callback/credentials`，不经过代理。所有调用都带 `skipValidation: 'true'`，`authorize` 不读口令，其他两处已传 `''`。这里改为 `''` 即可，next-auth 不需要接入信封。

## 错误语义

| 情况 | HTTP | code | 客户端行为 |
|---|---|---|---|
| MAC、填充、SM2、`kid` 或格式失败 | 400 | `gm_transport_rejected` | 提示无法解密，不重发 |
| `ts` 超窗 | 400 | `gm_transport_expired` | 校时后由用户再次操作 |
| nonce 已使用 | 400 | `gm_transport_replay` | 提示请求已失效，不重发 |
| 私钥缺失、缓存不是 Redis 或缓存失败 | 503 | `gm_transport_unavailable` | 重新拉取公钥后自动重发一次，已降级则发明文 |
| 信封超过 280MiB | 413 | `gm_transport_too_large` | 提示过大，不重发 |

语言包键放在 `server/apps/core` 的中英文包中，日志 `error_type` 用上表 code。

## 部署

产品仓库不改部署模板，由部署仓库 `bklite-website` 落地。

- **路由**：前端经 Traefik（优先级 10）进 Next，再由代理转发到 server。Traefik 开了 `--accesslog`，查询串必须移出 URL。公钥真实性依赖浏览器信任 `server.crt`，用户忽略证书警告后中间人可以换公钥。
- **nonce 存储**：三种部署形态都把 `REDIS_CACHE_URL` 指向 `redis:6379/1`，8 个 worker 共用。Redis 没开 AOF，重启或主备切换会丢失窗口内的 nonce，本次接受。HA 备节点的 server 在提升前不运行。
- **时钟**：服务器之间、以及用户电脑与服务器之间，偏差都要在 300 秒内。用户电脑时钟偏了，这个用户连登录都会失败。上线前要求终端与服务器接入同一对时源，并写进交付检查项。候选缓解：公钥接口返回 `server_time`，前端据此修正 `ts`；做不做以实际实现为准。
- **私钥**：只注入 server 容器，必须是落在 `[1, n-2]` 内的合法 SM2 私钥，生成处做范围检查（bash 用 `openssl genpkey -algorithm SM2`，Go 用 `crypto/rand` 加 `math/big`）。生成、`common.env` 持久化、HA 主备一致性校验、`wxc` 生成与下发、Kubernetes 独立 Secret（不进 `app-secrets`），都按 `DASHBOARD_SHARE_SIGNING_KEY` 的现有链路逐处补齐，逐文件清单见 `spec.md`。重部署和升级复用已有值。
- **应急关闭**：`python manage.py disable_gm_transport`（Kubernetes 用 `kubectl exec`），写进部署仓库的运维文档。

## 测试

服务端（Postgres，Redis 缓存替身需具备 NX 语义）：

- 固定向量：Python 与前端共用，锁住 C1C3C2、CBC 和 MAC 输入。
- 往返：GET 查询串、JSON、multipart 还原一致；视图 JSON 离开中间件时是响应信封，能解回原文；同步与异步 SSE 各一个，逐帧到达。
- 防重放：同一信封只执行一次；两份相同信封并发只进一份；MAC 错误不写 nonce，随后用正确 MAC 仍能通过；`ts` 快 299 秒的信封在固定 300 秒 TTL 会过期的时刻重放仍被拒。
- 失败路径：改 `path`、超窗、`kid` 不匹配均失败，响应是明文错误；`locmem` 下返回 `gm_transport_unavailable`；无信封的 `/api/v1/` 和 `/openapi/v1/` 原样放行、不写 nonce。
- 边界：路径尾部斜杠；3MB 信封不被 2.5MB 挡住且 `CONTENT_LENGTH` 为明文长度；超过 280MiB 返回 413 且不写 nonce。
- 开关与兜底：公钥接口四种状态的响应形状；自检失败拒绝开启、关闭不受影响；`disable_gm_transport` 幂等；降级 ERROR 只记一次。
- 日志：不出现明文、nonce、私钥哨兵，失败只记模板和 `error_type`。

前端：开关关闭时请求与今天一致；开关打开时查询串进入信封、两次调用 nonce 不同、响应能解回；登录 `fetch` 与 axios 走同一个包装；公钥缓存、重拉、降级与拒发行为符合「拉取与缓存」；与后端用同一份固定向量。

## 实施顺序

1. 请求、响应信封的纯函数和固定向量，先通过 Python 侧加解密与 MAC 测试。
2. 中间件、公钥接口、nonce 去重、响应加密，同一步加上开启前自检、降级和 `disable_gm_transport`，保证能打开之前就能关闭。
3. 前端 `gmTransport` 接入 axios 拦截器和无 token 的 `fetch`，向量测试锁定与后端一致。
4. 清点绕过包装的 `fetch('/api/proxy')`，以及 `<img src>`、下载链接、`window.open` 等浏览器原生加载。
5. 安全策略页加开关，端到端验证列表、登录、表单和重放登录信封。文件上传和下载与 SSE 一样属于流式传输，首期不加密，也不做大文件上传检查。演练一次故障：去掉私钥重启后页面自动降级，再用命令关闭。
6. 部署仓库注入私钥。

## 重要但不阻塞的问题

**浏览器原生加载的资源无法加信封。** `<img src>`、`<a href>` 下载、`window.open` 由浏览器自己发请求，`gmTransport` 接不进去，请求和响应都是明文，查询串会进访问日志。典型位置有 wiki 图片（`/api/proxy/opspilot/wiki_mgmt/media/...`）、对话下载链接、监控插件导出、MLOps 数据集与模型下载、Windows 安装包下载。需要保护的改为经 `gmTransport` 取 blob 再 `URL.createObjectURL`，其余列为残留明文，清点结果写回本节。

**加密与 MAC 共用同一把密钥。** 建议客户端生成 32 字节，SM2 加密这 32 字节，前 16 字节作 SM4 密钥、后 16 字节作 HMAC 密钥；或用 SM3 KDF 从 16 字节主密钥派生两把。成本几乎为零，采用时同步改参数表和测试向量。以实际实现为准。

**ASGI 下的流式响应。** 现有 SSE 同步、异步生成器都有。包装 `streaming_content` 时按 `response.is_async` 分别处理，否则可能整段收进内存或报错；每块产出后立即加密，不缓冲；客户端断开时把取消传给内层生成器；`FileResponse` 同样处理。

**密评合规边界。** 本方案满足「前后端通信支持国密并可开关」这一项。不在范围内的有：密码模块未取得商用密码产品认证；私钥以环境变量明文注入，没有密码机或 KMS；入口 HTTPS 不是 TLCP；请求头、URL 路径、无信封请求和浏览器原生加载不加密；存储层不改成国密。正式按 GB/T 39786 做密评时需要另行处理。

## 后续才考虑

- 换用 SM4-GCM 与 GmSSL C 库绑定（GM/T 0125）；GCM 不代替 nonce 去重。
- 会话内复用 SM4 密钥以减少 SM2 运算，每个请求仍需独立的 nonce 和 `ts`。
- 移动端经 `tauriApiFetch` / `tauriApiStream` 接入同一套信封，MAC 用 Next 补斜杠后的路径。
- 强制 `/api/v1/` 只收密文，会打断现有脚本，需单独决定。
