# SM2/SM3/SM4 国密与防重放技术方案

- 最近更新：2026-10-26
- 状态：方案已评审。实现在企业包，社区只保留加载接缝。本期只做 JSON 信封，文件和流式见「本期范围」
- 跨模块边界：[`specs/capabilities/gm-transport.md`](../../capabilities/gm-transport.md)

## 背景

等保密码应用要求前后端通信支持国密算法 SM2、SM3、SM4，并且可以开关。

BK-Lite 入口已经是 Traefik 上的 HTTPS。国密 TLS（TLCP，GB/T 38636）跑在网关证书层，Chrome、Edge、Firefox、Safari 都不实现，不放进产品。本次只做应用层：BK-Lite 前端在请求离开之前套上信封，Django 中间件解开后，现有视图仍看到原来的方法、查询参数和正文。

机密性挡的是旁路看见明文。抓到一份已经发出的信封后，攻击者仍可以把同一份字节再提交一次。防重放是这套信封的一部分：时间窗限制密文能活多久，一次性 nonce 保证这份密文在窗口内只能进入视图一次。

口令存储继续用 Django 4.2 的 PBKDF2。凭据落库继续用现有 AES-CBC 和 Fernet。这两处不改成国密。

## 目标

开关打开时，本期范围内的请求带国密信封。中间件在认证和视图读正文之前还原请求。同一把一次性 SM4 密钥再把这次 JSON 响应的正文加密。开关关闭时，请求和响应都与今天一致。移动端这次不改，开关打开后仍按今天的明文请求工作。

## 本期范围

2026-10-20 按方案一收窄本期交付。后文里的文件分帧和 SSE 逐帧加密仍是后续设计，本期不实现。

| 请求 | 本期 |
|---|---|
| 网页端普通业务 JSON | 开关打开后加密 |
| 登录、验证码、密码重置等 JSON | 开关打开后加密 |
| OpenAPI、外部 Token 调用 | 明文 |
| NATS、Agent、Celery | 不在本次浏览器通信范围 |
| 文件上传、下载 | 明文 |
| SSE、WebChat 流式接口 | 明文 |
| 公钥接口 | 明文，依赖现有 HTTPS |

开关关闭时，上表里的 JSON 也仍是明文。中间件只在带 `X-Gm-Transport: 1` 时解开 JSON 信封，并只加密非流式 JSON 响应。`StreamingHttpResponse`（含 SSE 和文件下载）原样返回。浏览器对 `FormData`、`responseType: blob` 和 `Accept: text/event-stream` 不套信封。

同一份信封字节再次到达时，中间件拒绝，视图不会执行第二次。客户端超时后的重试必须生成新信封。

三个算法的分工：

| 算法 | 作用 |
|---|---|
| SM2 | 加密一把由客户端现生成的 16 字节 SM4 密钥。公钥可下发，私钥只在服务端 |
| SM4-CBC | 加密查询参数、请求正文和响应正文。请求和响应各用各的 16 字节初始化向量，PKCS#7 填充 |
| SM3 | HMAC-SM3 分别覆盖请求信封和响应信封。改其中任一项都会使校验失败 |

## 非目标

- 不部署 TLCP，不改 Traefik 证书。
- 不对齐 GM/T 0125 的 JWE 五段串，也不使用 SM4-GCM。客户若要求按该标准的 GCM 测试向量检测，再换带 GCM 的 GmSSL C 库绑定。
- 不加密没有信封的响应。直接打到 `/api/v1/` 的明文脚本、`/openapi/v1/`、NATS、采集端和节点上报，响应仍是明文，也不做 nonce 去重。
- 不因为开关打开而拒绝直接打到 `/api/v1/` 的明文脚本。开关约束的是 BK-Lite 前端必须发信封。
- 不做移动端。移动端这次不发信封，也不解密响应。
- 不把 SM2 私钥写入 `SystemSettings`。`get_sys_set` 会返回整表设置。
- 不替换口令哈希和现有落库加密。
- 不代替业务自己的幂等。用户连点两次会生成两份新信封，两个请求都会进视图。防重放只拒绝字节完全相同的那一份。

## 评审记录

2026-10-15 评审，对照了本仓库代码与部署仓库 `bklite-website`。已定的结论：

- 公钥接口结果在客户端缓存 5 分钟，规则见「拉取与缓存」。
- 加密故障采用三层兜底：开启前自检、运行中服务端未就绪时自动降级为明文并在页面显示「已开启，未生效」、运维命令强制关闭。前端只在服务端已就绪而自身加密失败时拒发请求。规则见「故障兜底」。
- 部署相关的事实与改动位置已按部署仓库核对，见「部署」。

待定与需要注意的事项，正文对应位置有完整说明：

| 事项 | 性质 | 正文位置 |
|---|---|---|
| GET 请求带不上信封正文 | 已定：只有 GET 在线上改 POST，HEAD 不改 | 信封 › GET 在线上改发 POST |
| 纯 Python 加解密性能与大文件内存 | 需要注意 | 密码参数 › 需要注意：加解密性能 |
| 登录后多传一份明文口令 | 优化项 | 前端 › 发现的优化项 |
| 用户电脑时钟偏差 | 部署要求，缓解方式待定 | 部署 › 时钟 |
| 浏览器原生加载的资源无法加信封 | 重要但不阻塞 | 重要但不阻塞的问题 |
| 加密与 MAC 共用同一把密钥 | 建议，以实际实现为准 | 重要但不阻塞的问题 |
| ASGI 下的流式响应写法 | 实施注意 | 重要但不阻塞的问题 |
| 密评合规边界 | 边界说明 | 重要但不阻塞的问题 |

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

请求加密发生在 BK-Lite 前端，不发生在 Next.js 代理里。响应加密发生在 Django 中间件，代理只转发密文。代理到 Django 之前若请求仍是明文，或者视图的响应在离开中间件时仍是明文，浏览器到 Next 这段就没有被国密保护。

## 密码参数

两端锁定同一套参数，并用同一份测试向量验收。库分别是：

- BK-Lite 前端：`sm-crypto`（SM2 `cipherMode = 1`，即 C1C3C2；SM4 `mode = 'cbc'`，PKCS#7）
- 服务端：SM4-CBC 与 HMAC-SM3 用已有的 `cryptography==45.0.0`（`algorithms.SM4`、`hashes.SM3`）；SM2 用 PyPI `gmssl==3.2.2`，`mode=1`（C1C3C2，不带 `04` 前缀）。该库的 `decrypt` 算出 C3 后不比较，解开 SM4 密钥时自行核对 C3。性能取舍见下文「需要注意：加解密性能」

| 项 | 取值 |
|---|---|
| SM2 密文排列 | C1C3C2，十六进制，不带 `04` 前缀 |
| SM2 公钥 | 128 个十六进制字符，`X \|\| Y`，不带 `04` 前缀。调用库若要求 `04`，只在库边界补上 |
| SM2 私钥 | 64 个十六进制字符 |
| SM4 密钥 | 16 字节，客户端用密码学随机数生成，每次请求一把 |
| SM4 IV | 16 字节，同样每次随机 |
| nonce | 16 字节密码学随机数，写成 32 个十六进制字符 |
| 填充 | PKCS#7 |
| HMAC | HMAC-SM3，密钥就是这把 SM4 密钥。先加密，再对密文计算 MAC |
| 编码 | `ek`、`iv`、`ct`、`mac` 使用标准 Base64。公钥、私钥和 nonce 使用十六进制 |
| 时间窗 | 300 秒 |

SM2 只加密 16 字节的 SM4 密钥，不加密正文。

### 需要注意：加解密性能

2026-10-15 在开发机上的实测：

| 实现 | 结果 |
|---|---|
| PyPI `gmssl` SM4-CBC（纯 Python） | 1MiB 约 2.2 秒，约 0.46MB/s |
| PyPI `gmssl` SM2 解密 16 字节 | 每次约 2.9 毫秒 |
| `cryptography==45.0.0` SM4-CBC（服务端已依赖） | 64MiB 约 1.1 秒，约 57MB/s |
| `cryptography==45.0.0` HMAC-SM3 | 64MiB 约 0.5 秒 |

按纯 Python SM4 的速度，200MiB 采集包仅解密就要约 7 分钟，1MB 的列表响应加密也要约 2 秒。服务端以 `uvicorn asgi:application` 多 worker 运行，纯 Python 运算长时间持有 GIL，同一 worker 上的 SSE 和其他请求会一起变慢。实施时 SM4 和 HMAC-SM3 优先评估 `cryptography`（`algorithms.SM4`、`hashes.SM3`），SM2 解密开销可接受。

前端 `sm-crypto` 以普通 JS 数组处理字节，大文件再经 Base64 和 JSON 字符串，内存占用会是明文的数倍。服务端对接近 280MiB 的信封做 `json.loads` 同样占用大量内存。大文件上传是否改为二进制分帧、或列为本期不加密的例外，实施时按实测确定。

## 信封

线上正文的 `Content-Type` 固定为 `application/json`。这个头只说明正文是 JSON，分不出信封和普通业务数据：登录、列表、表单本来就是 `application/json`，开关关闭时正文也是 JSON。

请求头 `X-Gm-Transport: 1` 才表示这份 JSON 是信封。中间件在读正文之前用它分流：有这个头就解密、做防重放，并按「响应」一节加密响应；没有这个头就原样进入视图。脚本、OpenAPI 和开关关闭时的 BK-Lite 前端走后面这条。不靠「先解析 JSON，看有没有 `ek`」来判断，避免每个 JSON 请求都被读完，也避免业务字段碰巧同名时和信封混在一起。这个头不是密钥，也不代替 MAC。

业务上的原始 `Content-Type` 放在字段 `cty` 里。中间件解开后用 `cty` 恢复视图看到的类型，例如 JSON 或带 boundary 的 `multipart/form-data`。

```json
{
  "v": 1,
  "ts": 1760490000000,
  "nonce": "32 个十六进制字符",
  "kid": "公钥标识，见密钥一节",
  "method": "POST",
  "path": "/core/api/login/",
  "cty": "application/json",
  "ek": "Base64，SM2 密文",
  "iv": "Base64，16 字节",
  "ct": "Base64，SM4-CBC 密文",
  "mac": "Base64，HMAC-SM3 的 32 字节"
}
```

`path` 是 Django 挂载点 `/api/v1` 之后的路径，以 `/` 开头，并带尾部 `/`。浏览器请求 `/api/proxy/core/api/login` 或 `/api/proxy/core/api/login/` 时，Next 代理都会补上尾部斜杠，Django 收到 `/api/v1/core/api/login/`，信封里的 `path` 是 `/core/api/login/`。中间件拿去掉 `/api/v1` 前缀之后的 `request.path` 与信封比对，不拿地址栏上的原始字符串比对。少了尾部斜杠视为路径不一致。

`method` 是大写 HTTP 方法。`ts` 是客户端的 Unix 毫秒。`nonce` 每次请求新生成，不复用。

### GET 在线上改发 POST

信封放在正文里。2026-10-20 实测：浏览器 `fetch` 和 Node 24 `fetch` 对带正文的 GET、HEAD 抛 `TypeError`，请求不发出；浏览器 XHR 不报错，但正文被丢掉，`Content-Length` 为 0。`curl` 发出的 GET、HEAD 正文，Django ASGI 的 `request.body` 能读到。挡点在浏览器和 Node `fetch`，不在 Django。

HEAD 不改。它没有查询串要放进信封，响应也没有正文。本仓库页面不对业务接口发 HEAD。

开关打开时，只有 GET 在线上改发 POST。调用方仍传 GET 和原来的查询串。包装层去掉查询串，信封 `method` 写 `GET`，HTTP 方法用 POST。PUT、PATCH、DELETE、POST 的线上方法保持不变。开关关闭时 GET 仍是 GET，查询串仍在 URL 上。

中间件只在带 `X-Gm-Transport: 1` 时改写方法：

- 信封 `method` 为 GET 时，线上方法必须是 POST。解开后把 `request.method` 和 `REQUEST_METHOD` 改回 GET。
- 其他方法必须与线上方法一致，否则 `gm_transport_rejected`。线上 POST 配信封 DELETE 不会进视图。
- HEAD 不改写。

视图看到的仍是 GET 和原来的查询串。Next.js 只转发这个 POST，不识别信封。

### 被加密的明文

明文是一段二进制，不是 JSON：

1. 4 字节大端无符号整数，表示查询串的字节长度。
2. 查询串的 UTF-8 字节，不含前导 `?`。没有查询串时长度为 0。
3. 其后全部是原始正文。GET、DELETE 和无正文的请求，这段为空。文件上传时，这段是原来的 `multipart/form-data` 原始字节，`cty` 保留原来的 `Content-Type`（含 boundary）。

开关打开后，业务查询参数不再出现在 URL 上。中间件解开后写回 `request.META["QUERY_STRING"]` 和 `request.GET`。

### MAC 输入

HMAC 的消息是下列各行用 `\n` 连接后的 UTF-8 字节，最后一行之后不再加换行：

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

`ts` 和 `nonce` 放在 MAC 里面。改时间不能把过期密文续活，改 nonce 也不能把已经用过的密文变成新请求。方法、路径和 `cty` 同样在 MAC 里，密文不能挪到另一个接口。

校验失败、填充错误、SM2 解密失败对外都返回同一个错误，避免把失败原因暴露成解密神谕。时间超窗和 nonce 重复是另一类结果，见防重放。

## 防重放

防的是同一份信封被再次提交。典型来源是抓包后重放、代理或浏览器把已经序列化的正文再发一次。用户再次点击产生的是新的 `ts`、`nonce`、IV 和 SM4 密钥，MAC 不同，不在这条规则里。

### 组成

防重放采用「时间窗 + nonce + MAC 绑定」，服务端用 Redis 记录用过的 nonce。四部分各管一件事，缺一不可：

| 组成 | 谁生成或持有 | 作用 | 缺了它会怎样 |
|---|---|---|---|
| 时间戳 `ts` | 客户端每次请求取 Unix 毫秒 | 限定这份信封的有效期：与服务器时间相差不超过 300 秒 | nonce 记录必须永久保存，存储无限增长 |
| `nonce` | 客户端每次请求生成 16 字节随机数 | 在有效期内唯一标识这份信封 | 300 秒内同一份登录或删除可以提交任意次 |
| MAC 绑定 | 客户端用本次 SM4 密钥计算 HMAC-SM3，服务端校验 | 把 `ts`、`nonce` 与方法、路径、`cty`、IV、密文绑在一起 | 攻击者改 `ts` 让过期信封续命，改 `nonce` 绕过去重 |
| 服务端 nonce 记录 | Redis，`cache.add` 即 `SET NX EX`，过期时间算到窗口结束 | 记下已经用过的 nonce，多个 worker 共用，判断是原子的 | 服务端无从知道这是第二次提交 |

MAC 的密钥是本次请求的 SM4 密钥，它被 SM2 公钥加密在 `ek` 里，只有发出请求的客户端和持有私钥的服务端知道。抓到信封的人解不开 `ek`，也就算不出新的 MAC，所以改不动 `ts` 和 `nonce`。他可以用自己的密钥另造一份信封，但那是一次新的请求，要经过登录和权限，不属于重放。

判定规则：一份信封被接受，当且仅当 MAC 正确、`ts` 在窗口内、`nonce` 在 Redis 中第一次出现。任一条件不满足即拒绝。前两项都通过后才写 nonce，具体顺序见「校验顺序」。

nonce 记录只需要活到这份信封的时间窗结束：窗口关闭后，同一份信封会因为 `ts` 超窗被拒，不再需要靠 nonce 拦截。

响应不另做 nonce 记录。响应用的是本次请求独有的 SM4 密钥，响应 MAC 还绑定了本次请求的 `nonce`、`seq` 和 `status`，把旧响应塞给新请求会校验失败。

### 时间窗

服务端和前端比的是 Unix 纪元毫秒，不比墙上的本地时间。`server/config/components/locale.py` 里 `TIME_ZONE = "UTC"`、`USE_TZ = True`，这只影响 Django 展示和入库的时区，不给时间戳加 8 小时。

- 前端 `ts` 用 `Date.now()`。它是从 1970-01-01T00:00:00Z 起算的毫秒，和浏览器所在时区无关。上海时间下午 3 点和 UTC 上午 7 点是同一个数值。
- 服务端 `server_now_ms` 用同一套纪元毫秒，例如 `time.time_ns() // 1_000_000`。不要用 `datetime.now()` 的年月日时分秒，也不要先转成 `Asia/Shanghai` 再格式化成数字。

比较仍是 `abs(server_now_ms - ts) <= 300000`。超出则返回 `gm_transport_expired`，不写 nonce，也不解密正文。

正常请求会失败，只因为两端机器时钟相差超过 300 秒，不是因为一个在 UTC、一个在东八区。容器时钟跟宿主走。本次不提供服务器时间校准接口，时钟差过大时校时后再试。用户电脑时钟带来的风险与候选缓解见「部署」一节的「时钟」。

### nonce 去重

去重使用 Django 默认缓存。`server/config/components/cache.py` 在配置了 `REDIS_CACHE_URL` 时，默认缓存是 Redis，多进程、多副本共用这一份。调用 `cache.add(key, "1", timeout=ttl)`，对应 Redis 的 `SET NX EX`。返回假表示这个 nonce 已经占用，本次请求是重放。

缓存键是 `gm_transport:nonce:{nonce}`。Django 会再加上自己的键前缀，业务侧不自己连 Redis。

`ttl` 算到这份 `ts` 离开时间窗的时刻，而不是固定 300 秒：

```
ttl_seconds = max(1, ceil((ts + 300000 - server_now_ms) / 1000))
```

`ts` 比服务器快 300 秒时，ttl 约为 600 秒。若固定写成 300 秒，nonce 会先过期，而时间窗还没关，旧密文可以再进一次。`ts` 已经靠近窗口末端时，ttl 至少 1 秒，避免并发的第二次提交赶在键过期之后。

进程内的 `locmem` 不能在多个 Worker 之间去重。默认缓存不是 Redis 时，带信封的请求直接返回 `gm_transport_unavailable`，不进入视图。未配置 `REDIS_CACHE_URL` 时服务仍可启动，开关无法通过开启前自检；若开启后才失去 Redis，公钥接口自动降级，见「故障兜底」。官方部署已经把这份缓存指到 Redis，进程数、持久化和主备复制的边界见「部署」。

### 校验顺序

顺序不能颠倒。MAC 通过之前就占用 nonce，攻击者可以用错误的 MAC 把受害者即将使用的 nonce 占掉。

1. 解析 JSON。不是对象、缺字段、`v` 不是 1：`gm_transport_rejected`。
2. `path` 与去掉 `/api/v1` 前缀后的 `request.path` 不一致：`gm_transport_rejected`。信封 `method` 为 GET 时，线上方法必须是 POST，通过后改写为 GET；其他方法必须与线上方法一致，否则 `gm_transport_rejected`。HEAD 不改写。
3. `ts` 超出 300 秒：`gm_transport_expired`。
4. `kid` 与当前公钥不一致，或私钥不存在：`kid` 失败走 `gm_transport_rejected`，私钥缺失走 `gm_transport_unavailable`。
5. 用 SM2 私钥解出 SM4 密钥。失败：`gm_transport_rejected`。
6. 计算 HMAC-SM3 并与 `mac` 比较，比较采用恒定时间。失败：`gm_transport_rejected`。此时还没有写 nonce。
7. 默认缓存不是 Redis：`gm_transport_unavailable`。
8. `cache.add`。键已存在：`gm_transport_replay`。缓存抛错：`gm_transport_unavailable`。
9. SM4-CBC 解密，检查 PKCS#7，按长度前缀拆出查询串和正文。失败：`gm_transport_rejected`。这一步不再回滚 nonce。解密失败说明 MAC 键与密文不一致，留下 nonce 可以挡住用同一份材料继续试。

两个相同信封同时到达时，只有一个 `cache.add` 成功。失败的那个返回重放，视图只执行一次。

### 客户端重试

超时、断网、5xx 之后若要再试，必须重新生成 `ts`、`nonce`、IV 和 SM4 密钥，重新加密、重新计算 MAC。禁止把已经发出的信封字节放进下一次 HTTP。axios 或代理层若存在重试，重试点要落在包装函数之外，让每一次尝试都是新信封。

公钥 `kid` 不匹配时的那一次自动重试同样生成新信封。

## 密钥与开关

### 私钥

环境变量 `GM_SM2_PRIVATE_KEY`，值为 64 个十六进制字符。进程启动时若变量缺失，服务照常启动。只有收到信封时才要求这个变量存在。

公钥由私钥导出，不单独配置。`kid` 是 SM3(公钥原始 64 字节) 的前 8 字节，写成 16 个十六进制字符。信封里的 `kid` 必须等于当前公钥。本次不提供多密钥并存。

### 开关

开关放在系统管理的「安全策略」页，和 OTP 开关同一页。页面是 `web/src/app/system-manager/(pages)/user/security-settings/page.tsx`，菜单路径是 `/system-manager/user/security-settings`。

值存在 `SystemSettings`，键 `enable_gm_transport`，取 `"0"` 或 `"1"`，缺省 `"0"`。管理员的读写走现有安全策略接口，不另开一套：

- 读取：`GET /system_mgmt/system_settings/get_sys_set/`，权限 `security_settings-View`。返回的设置表里带这个键，页面按 `enable_otp` 同样的方式读取。
- 保存：`POST /system_mgmt/system_settings/update_sys_set/`，权限 `security_settings-Edit`。把 `enable_gm_transport` 改为 `"1"` 前先做开启前自检，不通过则拒绝保存，见「故障兜底」。

这两个接口要登录，登录页用不了。BK-Lite 前端决定要不要套信封时，只读 `GET /api/v1/core/api/gm_transport_public/`。它不需要登录，返回 `enabled` 为 `"0"` 或 `"1"`。`gmTransport` 按下文「拉取与缓存」的规则读取它，不是每个请求都调用。`enabled` 为 `"0"` 时原样发送；为 `"1"` 时再取同一响应里的公钥。

中间件不读这个开关。它看到请求头 `X-Gm-Transport: 1` 就解密并做防重放，响应也按「响应」一节加密。开关只决定 BK-Lite 前端是否发送信封。

这样直接调用 `/api/v1/` 的脚本和 `/openapi/v1/` 在开关打开后仍走明文。BK-Lite 前端若在开关打开后仍发不带该头的业务请求，属于客户端缺陷，由前端测试锁住，而不是由中间件把整个 `/api/v1/` 改成只收密文。

### 登录前的公钥接口

`GET /api/v1/core/api/gm_transport_public/`，`AllowAny`，不需要信封，也不占用 nonce。

开关关闭：

```json
{ "result": true, "data": { "enabled": "0" } }
```

开关打开且 Redis 与私钥都就绪：

```json
{
  "result": true,
  "data": {
    "enabled": "1",
    "kid": "16 个十六进制字符",
    "public_key": "128 个十六进制字符"
  }
}
```

开关打开，但服务端未就绪（私钥缺失或不合法，或默认缓存不是 Redis）：按「故障兜底」自动降级，返回 `enabled = "0"`，并带 `degraded = "1"`，不带公钥：

```json
{ "result": true, "data": { "enabled": "0", "degraded": "1" } }
```

客户端按 `enabled = "0"` 发明文，系统保持可用。`degraded` 只供安全策略页显示「已开启，未生效」，接口不返回具体原因，原因只写服务端日志。

### 拉取与缓存

客户端把这个接口的结果（`enabled`、公钥、`kid`）缓存在内存里，有效期 5 分钟：

- 页面加载后第一次需要发请求时拉取。多个请求同时等待时只发一次公钥请求，其余请求共用同一个结果。
- 缓存过期后，下一次请求前重新拉取。
- 以下情况立即作废缓存并重新拉取：收到 `kid` 不匹配；收到 `gm_transport_unavailable`；管理员在本页保存了安全策略中的国密开关。刷新页面后缓存自然清空。
- 收到 `kid` 不匹配时，重新拉取后用新信封重试该请求，同一业务操作只自动重试一次。
- 收到 `gm_transport_unavailable` 时，重新拉取后按新结果重发一次：仍是 `enabled = "1"` 就用新信封，已降级为 `"0"` 就发明文。这个错误发生在解出 SM4 密钥之前，视图没有执行过，重发不会重复执行业务。同一业务操作只自动重发一次。
- 公钥接口本身拉取失败（网络错误、非 2xx 或响应格式不对）时，本次按 `enabled = "0"` 发送，不缓存这次结果，下一次请求重新拉取。否则公钥接口自身的故障会锁死整个前端，连关闭开关的页面都打不开。

开关从开切到关，客户端在缓存期内继续发信封，中间件照常处理，没有影响。开关从关切到开，已打开的页面最长 5 分钟内仍发明文，后端照常接收，这段时间不受国密保护。5 分钟是生效延迟与请求量之间的取舍：每个页面每 5 分钟只多一次公钥请求。

### 故障兜底

开关在前端页面里，而前端开关打开后才发信封。若加密出故障时前端一律拒发，管理员连登录进去关开关都做不到。后端不是锁死的原因：中间件不读开关，明文请求始终放行。兜底因此落在前端行为和开关的修改通道上，分三层。

前端只在一种情况下拒绝发出请求：服务端明确返回已开启且就绪（`enabled = "1"` 并带公钥），而前端自己加密失败。这多半是前端缺陷，由第三层解决。其余故障都降级为明文，保持可用。降级带来的安全代价有限：能挡住或篡改公钥接口的主动攻击者，同样能直接换掉公钥，见「部署」一节的「入口与路由」。

**第一层：开启前自检。** `update_sys_set` 把 `enable_gm_transport` 改为 `"1"` 前，服务端依次检查：私钥存在且是合法 SM2 私钥；默认缓存是 Redis 且可写；用这把私钥完整跑一遍 SM2 加解密、SM4-CBC 加解密和 HMAC-SM3 的往返。任一项不通过就拒绝保存，开关保持原值，页面按语言包提示原因。改为 `"0"` 不做自检，任何时候都能关。

**第二层：运行中未就绪时自动降级。** 开启后若服务端变为未就绪，例如重部署时私钥没注入或 Redis 配置丢失：

- 公钥接口返回 `enabled = "0"`、`degraded = "1"`，前端发明文，系统可用。
- 已缓存旧公钥的页面发来的信封，中间件返回 `gm_transport_unavailable`；前端按「拉取与缓存」重新拉取后改发明文。
- 安全策略页看到 `degraded = "1"` 时显示「已开启，未生效」，提示检查私钥与 Redis 配置并查看服务端日志，不让管理员误以为加密在工作。
- 服务端日志记录降级原因，`error_type` 为 `gm_transport_unavailable`，`failed_stage` 区分私钥与缓存。公钥接口会被频繁调用，同一进程内同一原因只记一次 ERROR，之后降为 DEBUG，原因变化或恢复就绪时再记。

**第三层：运维命令强制关闭。** 前端加密本身有缺陷、谁都登录不进去时，运维在 server 容器内执行管理命令，把开关改回 `"0"`：

```
python manage.py disable_gm_transport
```

命令放在 `server/apps/system_mgmt/management/commands/`，写法对照同目录的 `init_login_settings.py`，用 ORM 把 `SystemSettings` 中的 `enable_gm_transport` 写为 `"0"`。命令幂等，已经是 `"0"` 时直接成功；向 stdout 输出修改前后的值，并记一条 INFO 日志。已打开的页面最长 5 分钟内拿到新结果后改发明文；刷新页面立即生效。

单个用户电脑时钟偏差导致的 `gm_transport_expired` 只影响该用户，不在这三层里处理，见「部署」一节的「时钟」。

## 后端中间件

类：`apps.core.enterprise.gm_transport_middleware.GmTransportMiddleware`。企业包不在运行目录时不注册。

挂在 `server/config/components/app.py` 的 `MIDDLEWARE` 里，位于 `SecurityMiddleware` 之后、`SessionMiddleware` 和 `AuthenticationMiddleware` 之前。这样后续中间件和视图读到的已经是还原后的正文。它不替换认证。请求还原成功后，同一层中间件在响应离开时把正文加密。

处理规则：

1. 路径不以 `/api/v1/` 开头：原样放行。因此 `/openapi/v1/`、管理后台和国际化接口不进入国密逻辑，也不查 nonce。
2. 路径是公钥接口：原样放行。
3. 没有 `X-Gm-Transport: 1`：原样放行。
4. 有该头：先看体积，再按「防重放」一节的顺序验证。成功后：
   - 用信封中的查询串替换当前查询参数。
   - 用解密后的正文替换请求流，并把 `CONTENT_LENGTH` 改成明文长度。
   - 把 `Content-Type` 改回 `cty`。
   - 删除 `X-Gm-Transport`，避免视图把它当成业务头。
   - 把这次请求的 SM4 密钥留在请求对象上，供响应加密使用。视图和日志读不到它。
   - 释放请求信封的字节。

失败时按错误表返回明文。此时还没有 SM4 密钥，响应不能加密。体为现有风格的 `{"result": false, "message": "..."}`。`message` 来自 `core` 语言包。日志使用 `apps.core.logger`，模板固定，参数独立传递，只记路径、`kid`、`error_type`。不记正文、查询串、密钥、MAC、nonce 和私钥。解密失败不打 traceback；只有中间件自身的未预期异常由这一处记录 traceback。

### 体积

不要通过 `request.body` 读取信封。Django 4.2 在 `CONTENT_LENGTH` 超过 `DATA_UPLOAD_MAX_MEMORY_SIZE` 时会拒绝，项目没有改这个值，默认 2.5MB。采集包上传的明文上限是 200MiB（`server/apps/node_mgmt/services/collector_release/constants.py` 的 `MAX_COMPRESSED_BYTES`）。开关打开后，现在能上传的包会先变成一份 JSON，2.5MB 会把它挡在中间件外面。

中间件按原始流读取，信封上限 280MiB。这盖住 200MiB 明文经 Base64 膨胀后的体积，并留下 JSON 字段的余量。超过上限返回 `gm_transport_too_large`，不解析，不占 nonce。

还原之后必须改写 `CONTENT_LENGTH`。采集包接口用这个头和 200MiB 比较；若仍是信封长度，不到 200MiB 的包会被误拒。解密结果写入可溢出到临时文件的流，供现有 `MultiPartParser` 使用。MAC 校验结束后释放请求信封的字节。中间件不把明文再写入日志，也不另存一份明文文件。

## 响应

产品要求整条链路的业务数据都是密文：旁路看见的响应正文也不能读。请求解开之后，中间件已经有这把一次性 SM4 密钥，客户端也还拿着它。响应用这把密钥加密，不再做一次 SM2，也不把密钥放进响应。

这挡住的是截获响应的人。仿造一个客户端、自己生成 SM4 密钥并发出合法信封的调用方，解得开的是他自己这次请求的响应，因为密钥就是他提供的。双向加密不代替登录和权限。没有信封的 `/api/v1/` 脚本拿到的仍是明文响应。

### 哪些响应保持明文

SM4 密钥还没有解出来时，没有东西可以用来加密：

- 没有 `X-Gm-Transport: 1` 的请求，包括 `/openapi/v1/` 和直接打到 `/api/v1/` 的脚本。
- 公钥接口。
- 请求信封自己的失败：`gm_transport_rejected`、`gm_transport_expired`、`gm_transport_replay`、`gm_transport_unavailable`、`gm_transport_too_large`。这些正文没有业务数据。
- 204、304 和没有正文的响应。
- Next 代理自己生成的 500 和 504。它们没有到达 Django。

密钥已经解出之后，视图返回的 JSON、业务错误、文件下载和 SSE 都加密。不允许加密失败后改发明文。

### 一次性响应

普通响应收成一份 JSON 信封，HTTP 状态保持视图原来的状态。`Content-Type` 改为 `application/json`，并加响应头 `X-Gm-Transport: 1`。原始类型放进 `cty`。

```json
{
  "v": 1,
  "nonce": "与请求相同的 32 个十六进制字符",
  "seq": 1,
  "status": 200,
  "cty": "application/json",
  "iv": "Base64，新的 16 字节",
  "ct": "Base64，SM4-CBC 密文",
  "mac": "Base64，HMAC-SM3 的 32 字节"
}
```

`iv` 每次响应新生成，不复用请求的 IV。明文是视图的原始正文，不再加查询串长度前缀。

HMAC 的消息是下列各行用 `\n` 连接后的 UTF-8 字节，最后一行之后不再加换行：

```
1
resp
{nonce}
{seq}
{status}
{cty}
{iv 的 Base64}
{ct 的 Base64}
```

客户端只用这次请求留下的 SM4 密钥校验。`nonce` 必须等于本次请求，`status` 必须等于 HTTP 状态，`seq` 必须是 1。校验失败则不把正文交给业务解析。读完响应后丢弃 SM4 密钥。

明文字节超过 200MiB 时不加密、也不改发明文，返回明文的 `gm_transport_too_large`。200MiB 与采集包明文上限相同，对应的信封仍落在 280MiB 以内。

### 流式响应

本期不加密 SSE、WebChat 和 `StreamingHttpResponse`，响应原样返回。下面是后续逐帧加密的设计，本期不实现。

SSE 和 `StreamingHttpResponse` 不把整段收进内存。视图每产出一块，中间件就用同一把 SM4 密钥打成一帧。线上 `Content-Type` 仍是 `text/event-stream`，这样 Next 代理继续按 SSE 转发，不会套上普通响应的正文超时。响应头同样带 `X-Gm-Transport: 1`。

每一帧是一条 SSE 事件，`data` 的内容是一帧 JSON，字段与上面的信封相同。`seq` 从 1 递增。`cty` 仍是视图原来的类型，例如 `text/event-stream`。明文是这一块的原始字节，客户端按 `seq` 解密后拼回原来的字节流。缺号、乱序或 MAC 失败则终止流，不把坏帧交给业务。

流已经开始之后若累计明文超过 200MiB，不再继续输出业务块，改发一帧加密的 `gm_transport_too_large`，然后结束。已经发出的帧保持密文，不改回明文。

文件名等响应头不进信封。加密的是正文。

## 前端

BK-Lite 前端没有一个能罩住所有浏览器请求的中间件。和 `GmTransportMiddleware` 对应的是 `web/src/utils/gmTransport.ts`：请求离开页面前套信封，响应回到页面之前解开信封。业务页面不自己做加解密。

它必须接在现有的两个出口上，缺一个就会漏明文：

- 已登录请求走 `web/src/utils/request.ts` 的 axios 拦截器。请求拦截器调用 `gmTransport` 加密，响应拦截器用同一次请求留下的 SM4 密钥解密。
- 登录和其它还没有 token 的请求不走这个 axios。`request.ts` 在没有 token 时会直接拒绝。这些 `fetch('/api/proxy/...')` 改为调用同一个 `gmTransport`，不各自实现一套加密。

直接写 `fetch('/api/proxy/...')` 又没经过 `gmTransport` 的调用，发出去的是明文，也没有 `X-Gm-Transport`。后端中间件看到没有这个头会放行，开关打开也挡不住。实施时要清点这类调用并收进同一个包装。清点结果里如果还剩绕过包装的业务请求，开关打开后的前端测试要能把它标出来。

Next.js 的 `web/src/app/(core)/api/proxy/[...path]/route.ts` 不是这层拦截。它继续按收到的正文和 URL 转发，不解密、不加密，也不缓存请求或响应正文。响应头 `X-Gm-Transport` 原样透传。代理日志继续只记方法、来源和路径，不记查询串和正文。流式响应保持 `text/event-stream`，代理才会走现有的 SSE 分支；若改成普通 JSON，长连接会被正文超时切断。

`enabled` 为 `"0"`（包括服务端降级和公钥接口拉取失败）时，包装函数返回原请求，见「拉取与缓存」与「故障兜底」。`enabled` 为 `"1"` 时：

- 按「拉取与缓存」取得公钥和 `kid`。
- 生成 SM4 密钥、IV 和 nonce。`ts` 取调用当时的 `Date.now()`；若实现了时钟校准，再加上偏移量，见「部署」一节的「时钟」。
- 从 URL 中取出查询串，发出的 URL 只保留路径。
- 正文使用原始字节。`FormData` 在加密前序列化为带 boundary 的 multipart 字节，`cty` 使用该 `Content-Type`。
- 设置 `X-Gm-Transport: 1` 和 `Content-Type: application/json`。
- 每次调用都使用新的 nonce 和 IV。调用方拿不到上一次的请求信封字节。
- 响应头带 `X-Gm-Transport: 1` 时，用这次请求的 SM4 密钥解开正文，再交给 axios 或 `fetch` 的调用方。调用方看到的是原来的状态、类型和明文。请求信封的失败响应没有这个头，按明文错误处理。
- 流式响应按 `seq` 逐帧解密，拼回原来的字节流。MAC 失败或序号中断则终止，不把坏帧往后传。
- 响应读完后丢弃 SM4 密钥。不把 SM4 密钥、nonce 或信封放进 `sessionStorage` 或 `localStorage`。

### 发现的优化项：登录后多传一份明文口令

登录信封成功后，`web/src/app/(core)/auth/signin/SigninClient.tsx` 调用 next-auth 的 `signIn("credentials")` 写会话，并传了 `password: nextPassword ?? password`。这次提交走 `/api/auth/callback/credentials`，不经过 `/api/proxy`，开关打开时口令仍以明文出现在浏览器到 Next 这一段。

所有 `signIn("credentials")` 调用都带 `skipValidation: 'true'`，此分支的 `authorize` 只读 `userData`，不读 `password`。`web/src/context/auth.tsx` 与 `web/src/app/(core)/auth/wechat-popup/bridge/page.tsx` 已经传 `password: ''`。`SigninClient.tsx` 同样改为 `''` 即可，next-auth 本身不需要接入信封。

## 错误语义

| 情况 | HTTP | 对外 code | 客户端行为 |
|---|---|---|---|
| MAC、填充、SM2、`kid` 或信封格式失败 | 400 | `gm_transport_rejected` | 提示请求无法解密，不自动重发这份正文 |
| `ts` 超出 300 秒 | 400 | `gm_transport_expired` | 校时后由用户再次操作，生成新信封 |
| nonce 已使用 | 400 | `gm_transport_replay` | 提示请求已失效，不重发这份正文 |
| 带信封但私钥未配置、缓存不是 Redis，或缓存访问失败 | 503 | `gm_transport_unavailable` | 重新拉取公钥接口后自动重发一次，已降级则发明文；仍失败再提示国密传输暂不可用 |
| `Content-Length` 超过 280MiB | 413 | `gm_transport_too_large` | 提示请求过大，不自动重发 |

语言包键放在 `server/apps/core` 的中英文包中。日志里的 `error_type` 使用上表的 code。

## 部署

产品仓库不改部署模板。上线时部署仓库 `bklite-website` 按「私钥放在哪」注入私钥。密码学行为仍以本文为准。

前端因加密故障无法使用时，运维在 server 容器内执行 `python manage.py disable_gm_transport` 关闭开关（Kubernetes 用 `kubectl exec` 进入 server 容器）。这条写进部署仓库的运维文档，见「故障兜底」。

### 入口与路由

官方入口是 Traefik，只开了 `websecure`，证书来自 `conf/traefik/certs/server.crt`。`bootstrap.sh` 用 openssl 生成自签证书，SAN 是安装时的 `HOST_IP`。相关路由有三条：

| 优先级 | 规则 | 落到 |
|---|---|---|
| 20 | `PathPrefix(/api/v1)` | `server:8000`，不经过 Next |
| 15 | `PathPrefix(/openapi/v1)`，排除 `_provider` 和 `_auth` | 同一个 server |
| 10 | `Host(HOST_IP)` | `web:3000` |

BK-Lite 前端走优先级 10，再由 Next 的 `NEXTAPI_URL=http://server:8000` 在 compose 网络里转发。请求的国密在 BK-Lite 前端完成，响应的国密在 Django 中间件完成。Next 两个方向都只转发密文。代理已经复制请求头并用 `req.body` 流式转发，`X-Gm-Transport` 可以到达 Django，也不在 Next 里解密响应。查询串必须从 URL 上拿掉：Traefik 开了 `--accesslog`，留在 URL 上的查询会被记进访问日志。

公钥下发的真实性依赖浏览器信任这张 `server.crt`。用户忽略证书警告之后，中间人可以换掉公钥。本次不改 Traefik 证书，也不改成国密证书。

### nonce 存储与主备

`server` 容器默认 `APP_WORKERS=8`。单机 compose、双机 compose 和 Kubernetes 都把 `REDIS_CACHE_URL` 设为 `redis:6379` 的 1 号库。这 8 个进程共用这一份 Redis，nonce 去重成立。Kubernetes 的 server Deployment `replicas` 是 1，横向副本不是当前形态。1 号库同时给监控使用，nonce 只用 Django 缓存键，不自己 `FLUSHDB`。

这份 Redis 的启动参数只有 `--requirepass`，没有 AOF。进程重启后，时间窗里还没进快照的 nonce 会丢，旧信封可以再进一次。双机时备节点 Redis 是 `replicaof`，只读；主备切换提升之后，还没复制过去的 nonce 同样会丢。这两处本次接受，不为防重放改 Redis 持久化，也不另起存储。双机备节点上 server 属于 compose profile `active`（`deploy/docker-compose-ha/compose/ha.yaml`），提升之前不运行，不会收到信封。

### 时钟

双机时两台服务器的时钟都要落在 300 秒窗口里。部署仓库没有配置对时服务。

`ts` 取自用户浏览器所在电脑的 `Date.now()`，不是服务器时间。服务器对时只保证服务端一侧，用户电脑与服务器相差超过 300 秒时，该用户的所有信封请求都返回 `gm_transport_expired`，包括登录，表现为整个产品不可用。内网办公机未接 NTP、时钟偏差几分钟的情况并不少见。

上线前要求客户确认终端与服务器都接入同一对时源，并把这一条写进交付检查项。

候选缓解：公钥接口顺带返回服务器的 Unix 毫秒 `server_time`，前端拉取时记下 `offset = server_time - Date.now()`，之后 `ts = Date.now() + offset`。时间窗仍以服务器时间判断，防重放不被削弱。是否实现以实际实现情况为准；若实现，「时间窗」一节「本次不提供服务器时间校准接口」一句同步删除。

### 私钥放在哪

`GM_SM2_PRIVATE_KEY` 只注入 server 容器。取值是 64 位十六进制，必须是合法 SM2 私钥，即落在 `[1, n-2]`，`n` 为 SM2 曲线阶。32 字节随机数绝大多数情况下落在范围内，但生成处仍要做范围检查，不合法则重抽。

生成方式：

- bash：`openssl genpkey -algorithm SM2`（OpenSSL 1.1.1 及以上），再从私钥中取出 32 字节转十六进制。`bootstrap.sh` 现有的 `generate_password` 生成字母数字，`generate_urlsafe_secret` 生成 Base64url，都不能拿来当这把密钥。
- Go（`wxc`）：标准库没有 SM2，用 `crypto/rand` 取 32 字节，再用 `math/big` 与 `n` 比较做范围检查。

链路按 `DASHBOARD_SHARE_SIGNING_KEY` 的现有做法逐处补齐。只改 compose 环境变量会漏掉生成和主备同步：

| 部署形态 | 需要改的位置 |
|---|---|
| 单机 compose | `deploy/docker-compose/compose/server.yaml` 的 server 环境变量，不写进 `web.yaml`；`deploy/docker-compose/bootstrap.sh` 的生成函数、首次生成与存量补齐（对照 `generate_dashboard_share_signing_key` 及约 928、964 行），以及 `save_common_env` 写入的 `common.env` 和 `generate_dotenv` 写入的 compose `.env` |
| 双机 compose | `deploy/docker-compose-ha/compose/server.yaml`；`deploy/docker-compose-ha/bootstrap.sh` 同上，并沿用「备节点禁止独立生成」的检查（约 918–965 行）；`deploy/docker-compose-ha/bin/ha-validate-shared-env.sh` 必填列表加上该变量，主备必须相同 |
| `wxc` 生成与下发 | `deploy/wxc/internal/envgen/envgen.go` 的生成函数与写入；`deploy/wxc/cmd/init.go` 的托管字段和 HA 读取已有值（对照 `readHADashboardShareSigningKey`）；`deploy/wxc/cmd/upgrade.go` 存量升级时补生成 |
| `wxc` 内置资产 | `deploy/wxc/internal/compose/assets`、`deploy/wxc/internal/bundle/assets` 由 sync 脚本从上面两份模板生成，改源文件后同步 |
| Kubernetes | web 与 server 都通过 `envFrom` 引用 `app-secrets`，私钥不能放进这个 Secret，否则 Next 容器也会拿到。对照 `dashboard-share-secrets`：`deploy/wxc/internal/manifests/generate.go` 渲染独立 Secret 并只在 server 上用 `secretKeyRef` 注入；`deploy/wxc/cmd/k8s_deploy.go` 重部署时复用已有 Secret，不静默轮换 |

私钥轮换只会让轮换瞬间在途的请求失败，客户端遇到 `kid` 不匹配会重新拉公钥并重试一次，影响比分享签名密钥小。但重部署和升级仍应复用已有值，避免无意义的轮换。

## 测试

服务端测试使用 Postgres（`DB_ENGINE=postgresql`，与项目默认一致）。去重测试使用 Redis 缓存替身，并保证 `add` 具备 NX 语义：

- 固定向量：同一 SM2 密钥对、SM4 密钥、IV、nonce、`ts` 和明文，Python 解出与向量一致的查询串和正文。向量同时给前端单测使用，锁住 C1C3C2 和 CBC。MAC 输入包含 `ts` 和 nonce。
- 中间件还原 GET 查询串、JSON 正文和 multipart 正文，视图读到的与加密前一致。同一份合法请求信封只让视图执行一次。视图返回的 JSON 在离开中间件时是响应信封，用同一把 SM4 密钥能解回原文。
- 请求 MAC 失败、过期、重放、缓存不可用时，响应是明文错误，没有响应信封。
- 两份响应对调 nonce 或修改一字节 MAC 后，客户端校验失败。
- 两块 SSE 明文按 seq 1、2 加密后，客户端拼回原来的字节。seq 缺号则停止。
- 同步与异步 SSE 视图各一个，经中间件后逐帧到达，而不是结束后一次到达。
- 改一个 MAC 字节后拒绝，且缓存里没有这个 nonce。紧接着用正确 MAC 提交同一 nonce，视图仍能执行。这锁住「MAC 失败不得占坑」。
- 两份字节相同的信封并发提交，只有一份进入视图。
- `ts` 比服务器快 299 秒的合法请求被接受后，在 300 秒的固定 TTL 会过期、但时间窗仍开放的时刻再提交，仍然拒绝。这锁住 ttl 要算到窗口结束。
- 改 `path`、`ts` 超窗、`kid` 不匹配，均失败。响应与日志中不含明文哨兵、nonce 哨兵和私钥哨兵。
- 默认缓存是 `locmem` 时，带信封的请求返回 `gm_transport_unavailable`，视图不执行。
- 无 `X-Gm-Transport` 的 `/api/v1/` 请求和 `/openapi/v1/` 请求原样到达视图，不写 nonce，响应也保持明文。
- `request.path` 为 `/api/v1/core/api/login/`、信封 `path` 为 `/core/api/login/` 时通过。信封少了尾部斜杠则拒绝。
- `Content-Length` 为 3MB 的合法信封不被默认 2.5MB 挡住。还原后视图读到的 `CONTENT_LENGTH` 是明文长度。超过 280MiB 返回 `gm_transport_too_large`，不写 nonce。
- 公钥接口在开关关闭、开启且就绪、开启但私钥缺失、开启但缓存不是 Redis 四种情况下的响应形状；后两种返回 `enabled = "0"`、`degraded = "1"`，不含原因和公钥。同一原因连续调用只记一次 ERROR。
- 开启前自检：私钥缺失、私钥不合法、缓存不是 Redis 时，`update_sys_set` 拒绝把开关改为 `"1"`，值保持不变；改为 `"0"` 不受自检影响。
- `disable_gm_transport` 把开关从 `"1"` 改为 `"0"`；已经是 `"0"` 时再执行仍成功且值不变。
- 日志断言：失败只记模板和 `error_type`，不出现正文。

前端：

- 开关关闭时 axios 发出的 URL 和正文与现在一致。
- 开关打开时，查询参数从 URL 进入信封，正文为 JSON 信封，并带 `X-Gm-Transport`。连续两次调用的 nonce 不同。响应信封用同一次调用的 SM4 密钥解回明文。
- 登录用的 `fetch` 与 axios 走同一个 `gmTransport`。绕过它直接 `fetch('/api/proxy/...')` 时，开关打开也不带 `X-Gm-Transport`。
- 公钥缓存：并发请求只拉一次；5 分钟后重新拉取；`kid` 不匹配或 `gm_transport_unavailable` 后立即重新拉取并只重发一次；公钥接口拉取失败或返回降级时发明文，且拉取失败的结果不缓存；服务端已就绪而前端加密抛错时不发出请求。
- 使用与后端相同的固定向量做加密结果比对。向量里的 `ts` 和 nonce 固定，只用于密码学比对，不用于中间件的时间窗测试。

## 实施顺序

1. 落地请求信封和响应信封的纯函数和固定向量，先让 Python 侧加解密与 MAC 测试通过。已完成：`enterprise/server/apps/core/enterprise/gm_crypto.py`，测试 `enterprise/server/apps/core/enterprise/tests/test_gm_transport_envelope.py`（不连数据库）。固定向量用 GM/T 0003.5 示例私钥。SM2 的 `ek` 含随机数，向量冻结一份样本密文做解密；SM4 密文和 HMAC 是确定值。HMAC 密钥仍是这把 16 字节 SM4 密钥，不拆成两把。
2. 加中间件、环境变量、开关、公钥接口、nonce 去重和响应加密，补上放行、占坑顺序、ttl、重放和响应往返测试。同一步加上开启前自检、公钥接口降级和 `disable_gm_transport` 命令，保证开关能打开之前就有关闭手段。
3. 前端 `gmTransport` 同时接入 axios 的请求拦截器、响应拦截器，以及登录等没有 token 的 `fetch`。请求加密、响应解密用向量测试锁定与后端一致。重试路径断言每次都是新 nonce。
4. 清点仍直接 `fetch('/api/proxy')` 的调用。业务 JSON 改为同一个 `gmTransport`。漏掉的调用在开关打开后仍是明文，后端会放行。同时清点 `<img src>`、下载链接和 `window.open` 等浏览器原生加载。结果已写回「浏览器原生加载的资源无法加信封」。
5. 安全设置页增加开关。用开关关闭、开关打开下的列表查询、登录、表单提交、一次会返回 JSON 的读取，以及把同一份登录信封再提交一次，做验证。列表或详情的响应在浏览器发出之后、进入页面之前应是信封。文件上传和下载与 SSE 一样属于流式传输，首期不加密，也不做大文件上传检查。另外演练一次故障：开关打开后去掉私钥重启 server，确认页面自动改发明文、安全策略页显示「已开启，未生效」，再执行 `disable_gm_transport` 关闭。
6. 部署仓库按「部署」一节注入私钥。产品仓库不改部署模板。

## 重要但不阻塞的问题

### 浏览器原生加载的资源无法加信封

`<img src>`、`<a href>` 下载、`window.open` 打开的地址由浏览器自己发起请求，`gmTransport` 接不进去：带不上 `X-Gm-Transport`，也无法解开响应信封。这类请求开关打开后仍是明文请求、明文响应，查询串留在 URL 上，会进入 Traefik 访问日志。

当前代码中的典型位置：

- wiki 图片：Markdown 中 `/api/proxy/opspilot/wiki_mgmt/media/...` 作为 `<img src>` 渲染（`web/src/components/markdown/wikiMarkdownImages.ts`、`web/src/app/opspilot/utils/wikiMediaDisplay.ts`）。
- 对话中的下载链接：`web/src/app/opspilot/components/custom-chat-sse/downloadUrl.ts` 把地址规范成 `/api/proxy/...` 后交给链接。
- 各类下载地址：监控插件导出、MLOps 数据集与模型下载、Windows 安装包下载等（`monitor/(pages)/integration/list/page.tsx`、`mlops/components/algorithm-detail/DatasetReleaseList.tsx`、`mlops/components/TrainTaskDrawer.tsx`、`node-manager/.../operationGuidance.tsx`）。其中已经用 `fetch` 取 blob 的可以收进 `gmTransport`，交给链接或新窗口的不行。

处理方式按资源决定：需要保护的改为经 `gmTransport` 取回 blob，再用 `URL.createObjectURL` 交给页面；不需要保护的列为残留明文。

本期清点结果：

- 已收进 `gmFetch` 或 axios 信封的业务 JSON：登录、验证码、密码重置、登录认证、门户品牌、`get_bk_settings`、旧版第三方登录授权，以及其余走 `web/src/utils/request.ts` 的 JSON。这些都在 core 或系统管理。
- 公钥接口 `gm_transport_public` 保持明文。安全策略页直接请求它，用来判断「已开启，未生效」。
- 文件保持明文：附件上传与下载、CMDB 模型导入导出、MLOps 数据集与模型下载。
- SSE 与 WebChat 流保持明文：日志 tail、作业执行流、知识库问答流、对话流、节点试运行流。
- 浏览器原生加载保持明文：上文的 wiki 图片、对话下载链接，以及交给 `<a href>` 或 `window.open` 的地址。
- 旧微信扫码桥的弹窗页、桥接页和 `/api/wechat-popup-login` 已停用，这期不改，微信设置读取保持原来的 `fetch`。主登录在 login-auth。

其他模块仍需收进信封，本次不改：

- OpsPilot 对话停止生成。`useSSEStream.ts` 用裸 `fetch` 向 `interrupt_chat_flow_execution` 发 JSON。使用方是工作室对话、技能对话、技能设置调试。
- OpsPilot 节点试运行的中断。`useNodeExecution.ts` 同样向 `interrupt_chat_flow_execution` 发 JSON。试运行的事件流本身仍明文。
- OpsPilot 审批提交。`custom-chat-sse/ApprovalCard.tsx` 与 `opspilot-approval-card` 向 `submit_approval` 发 JSON。
- OpsPilot 执行详情。`opspilot/api/studio.ts` 读取 `execution_detail`。
- OpsPilot 附件状态查询。`chatAttachments.ts` 的 `fetchChatAttachmentStatus`。上传和下载仍按文件明文处理。
- 运营分析分享令牌。`ops-analysis/api/dashboardShare.ts` 的 `prepareShareToken`。
- WebChat 独立脚本。渠道、会话、消息、删除会话、审批、选项、中断和宽度都是明文。脚本不在 `web/src` 的 axios 包装里。

### 加密与 MAC 共用同一把密钥

当前方案用同一把 16 字节 SM4 密钥既做 SM4-CBC 加密，又做 HMAC-SM3 的密钥，没有密钥分离。目前没有已知可利用的攻击，但不符合密钥单一用途的通行做法，密评审查时可能被问到。

建议：客户端生成 32 字节随机数 `K`，SM2 加密的对象改为 `K`；前 16 字节作 SM4 加密密钥，后 16 字节作 HMAC-SM3 密钥。也可以对 16 字节主密钥用 SM3 KDF（GB/T 32918.4）分别派生两把。请求和响应共用这两把子密钥，响应 MAC 输入首行之后的 `resp` 已经区分了方向。

成本几乎为零：SM2 多加密 16 字节，其余流程不变。若采用，「密码参数」表中 SM4 密钥、HMAC 两行及固定测试向量同步修改。以实际实现情况为准。

### ASGI 下的流式响应写法

服务端以 `uvicorn asgi:application` 运行。现有 SSE 视图同时存在同步生成器（如 `server/apps/opspilot/utils/sse_chat.py` 第 43 行）和异步生成器（同文件 `run_stream`、`generate_stream`）。中间件包装 `StreamingHttpResponse` 时要注意：

- 按 `response.is_async` 分别包装：异步响应用异步生成器包装 `streaming_content`，同步响应用同步生成器包装。混用时 Django 会在同步与异步之间整段转换，可能把流整个收进内存，SSE 失去实时性，或直接报错。
- 每块加密在当前块产出后立即完成，不在中间件里缓冲多块。
- 客户端断开时，包装层要把取消传给内层生成器，不能吞掉，否则后端的 LLM 调用或执行任务继续跑。
- `FileResponse` 也是流式响应，同样走 `streaming_content`，按同一规则处理，并受 200MiB 明文上限约束。

对应测试见「测试」：同步与异步 SSE 视图各一个，断言逐帧到达。

### 密评合规边界

本方案满足的是「前后端通信支持 SM2、SM3、SM4，并可开关」这一功能要求。下列内容不在范围内，客户若按 GB/T 39786 做正式密评，需要另行处理：

- 密码模块未经认证：服务端 `gmssl` 或 `cryptography`、前端 `sm-crypto` 都是开源实现，不是取得商用密码产品认证证书的密码模块。若测评要求使用认证产品，需要换成认证的软件密码模块或密码机。
- 密钥管理：SM2 私钥以环境变量明文注入，没有密码机或 KMS 保护，也没有密钥生命周期管理。
- 网络层：入口 HTTPS 仍是国际算法证书，不提供 TLCP。
- 未加密的部分：请求头和响应头（包括 `Authorization` 中的 Bearer token）、URL 路径、没有信封的请求（直接打到 `/api/v1/` 的脚本、`/openapi/v1/`、NATS、采集端、移动端），以及上文列出的浏览器原生加载资源。
- 存储层：口令哈希仍是 PBKDF2，凭据落库仍是 AES-CBC 和 Fernet，见「非目标」。

## 后续才考虑

- 按 GM/T 0125 使用 SM4-GCM，并更换为 GmSSL 的 C 库绑定。GCM 的认证标签不代替 nonce 去重，防重放仍然需要。
- 一把 SM4 密钥在会话内复用，减少每个请求的 SM2 运算。当前每个请求一把密钥，中间件不需要会话存储。复用之后，每一跳请求仍然要有自己的 nonce 和 `ts`，响应仍用这一把密钥加密。
- 移动端接入同一套信封。出口是 `tauriApiFetch` 和 `tauriApiStream`，加密和解密都在 JS 层。移动端自己的 URL 不加尾部斜杠，MAC 仍用 Next 补斜杠之后的路径，并与 BK-Lite 前端共用公钥和同一份 Redis nonce。
- 强制 `/api/v1/` 拒绝明文。那会打断现有脚本和集成，需单独决定。
