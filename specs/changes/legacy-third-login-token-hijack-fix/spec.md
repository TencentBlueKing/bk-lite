# Legacy 第三方登录任意外域 JWT 劫持修复

## 背景

TSRC 报告（2026-09-07，标题「BlueKing Lite平台存在任意账号劫持凭证导致账号接管漏洞」）：
攻击者构造 `https://<平台>/auth/signin?callbackUrl=http://攻击者主机/cb?third_login_code=<任意值>&thirdLogin=true`
诱导受害者登录，登录成功后受害者的平台 JWT（约 24h 有效）被完整拼进 `callbackUrl`
并整页跳转到攻击者服务器，等于账号接管。

代码根因（两条路径都成立）：

- 密码登录路径：`web/src/app/(core)/auth/signin/SigninClient.tsx` 用
  `getLegacyThirdLoginCode(callbackUrl)` 从**攻击者可控的 URL** 提取 code，即触发 legacy
  分支；`web/src/utils/authRedirect.ts` 的 `buildLegacyThirdLoginCallbackUrl` **只校验协议是
  http/https，不做任何域名校验**，把 `token=<JWT>` 拼上后 `window.location.href` 跳转。
- login-auth v2 路径：`useLoginAuthValidation` 把原始 `callbackUrl` 作为
  `legacy_external_callback_url` 传给 `start_login_auth`；
  `server/apps/core/views/index_view.py` 的 `_is_safe_legacy_external_callback_url`
  同样只校验协议，登录完成后 `login_auth_callback` 原样回填给前端跳转。

合法消费方只有 `bklite-website` 仓库（本机路径 `/Users/lanyu/Work/bklite-website`），
线上部署为**两个站点**：`bklite.ai`（Cloudflare）与 `bklite.cn`（镜像，Dockerfile 构建时
将产物中的 `bklite.ai` 文本替换为 `bklite.cn`；`loginBaseUrl`/`loginInfoUrl` 指向的
`bklite.canway.net` 不受替换影响）。其 `src/lib/playgroundAuth.js` 自生成随机
`third_login_code` 存
sessionStorage 作 state，跳平台登录，回跳后校验 state 一致才收 URL 中的 `token`（存入
非 HttpOnly cookie `bklite_token`，用于 Bearer 直调平台 API，如
`https://bklite.canway.net/api/proxy/core/api/login_info/`）。该 state 只防 CSRF，
防不了平台把 token 送给任意外域。

## 目标架构（P0 白名单 + P1 去 token 化，一次修完）

修复后 legacy 外部登录流程：

1. 外部站点（bklite.ai）生成本地 state（沿用现有 `third_login_code` 机制），跳转
   `/auth/signin?callbackUrl=<外站回调URL>&thirdLogin=true`（参数形态不变，兼容存量链接）。
2. 用户在平台完成登录（密码 / OTP / login-auth v2 任意方式）。
3. **由服务端**校验外站回调 host 命中白名单后，签发一次性授权码 `bk_lite_code`，
   并构建回跳 URL：`<外站回调URL>&third_login_code=<原state>&bk_lite_code=<一次性码>`。
   **URL 中不再出现 `token`**。白名单未命中：不签发、不外跳，回落站内 `PORTAL_HOME_PATH`。
4. 外部站点回调页校验本地 state 后，用 `bk_lite_code` POST 平台兑换接口，**token 只经
   响应体下发**。

### 服务端（server/apps/core）

- **白名单配置**：新增环境变量 `LEGACY_THIRD_LOGIN_ALLOWED_CALLBACK_HOSTS`（逗号分隔，
  host 精确匹配，不含 scheme/port 归一化按 `urlparse().hostname` 小写比较）。
  **默认空 = 完全禁用 legacy 外部回调**。现网 bklite.canway.net 部署需配置为
  `bklite.ai,bklite.cn`（在部署文档/变更说明中登记）。
- **校验函数**：`_is_safe_legacy_external_callback_url` 升级为「http(s) 绝对 URL 且
  hostname 命中白名单」；覆盖协议相对 `//`、`user@host`、大小写、IP 直连等变体
  （统一交给 `urlparse().hostname` 判定，禁止字符串前缀匹配）。
- **一次性授权码**：
  - 生成：`secrets.token_urlsafe(32)` 级别熵；存 Django cache，键
    `legacy_third_login_code:<code>`，值含 `token`、`callback_host`、签发时间；TTL 300s。
  - 不变量：单次消费（并发重复兑换只能成功一次，兑换实现必须原子判定「取到且删除」）；
    过期、不存在、`callback_host` 不匹配一律拒绝；日志不得出现 code 或 token 明文。
- **签发点一：密码登录路径**。新增授权端点（与现有 core 登录端点同模式，`api_exempt`
  之外需 Bearer 认证）：`POST /api/proxy/core/api/legacy_third_login/authorize/`，
  body `{callback_url, third_login_code}`，服务端做白名单校验 + 签发 code + 拼接回跳
  URL，返回 `{redirect_url}`；未命中白名单返回 4xx。**跳转目标由后端决定**（对应报告
  修复建议 2）。
- **签发点二：login-auth v2 路径**。`start_login_auth` 对
  `legacy_external_callback_url` 做白名单校验（未命中返回 400）；`login_auth_callback`
  成功后由服务端签发 code、构建 `legacy_redirect_url` 写入 `login_result`，
  `LOGIN_AUTH_RESULT_ALLOWED_FIELDS`（`login_auth_request_service.py`）中
  `legacy_external_callback_url`/`legacy_third_login_code` 两个字段改为
  `legacy_redirect_url`；回填前基于缓存中的 auth_request 再做一次白名单校验（防旧缓存
  绕过）。
- **兑换端点**：`POST /api/proxy/core/api/legacy_third_login/exchange/`，`api_exempt`
  （凭 code 本身认证），body `{code}`，成功返回 `{result: true, data: {token}}`；
  失败（过期/已用/不存在）统一 4xx 且响应不区分具体原因。需允许白名单 origin
  （`https://bklite.ai` 与 `https://bklite.cn` 两个）的 CORS 预检与跨域 POST
  （参照现网 `login_info/` 已被两站跨域调用的现状核对 CORS 配置位置）。**该端点属登录链路而非业务 OpenAPI，不走 openapi 网关**，实现前
  与 `specs/capabilities/openapi-gateway.md` 的边界描述核对一次。
- 日志遵守仓库红线：稳定模板 + 惰性参数；只记录 host、结果与关联 ID，不记录
  code/token/完整 URL。

### 平台前端（web/src）

- `SigninClient.tsx`：
  - 删除「`callbackUrl` query 里出现 `third_login_code` 即触发外跳」的隐式授权。
    legacy 分支改为：登录成功后携带 Bearer token 调 `legacy_third_login/authorize/`，
    成功则 `finishAuthentication(响应中的 redirect_url)`，4xx 则回落
    `PORTAL_HOME_PATH`（正常完成站内登录，不报错阻断）。
  - login-auth v2 结果改用 `login_result.legacy_redirect_url`。
- `web/src/utils/authRedirect.ts`：
  - **删除** `buildLegacyThirdLoginCallbackUrl`（前端不再拼接任何带凭据的外域 URL）。
  - `getLegacyThirdLoginCode` 仅保留「识别当前是 legacy 流程 + 提取 state 供
    authorize 请求使用」的职责，不再决定跳转目标。
- `useLoginAuthValidation.ts`：继续上送 `legacy_external_callback_url`/
  `legacy_third_login_code`（由服务端校验），透传 `legacy_redirect_url`。
- 同源 `buildThirdLoginCallbackUrl` 的 `?token=`（浏览器历史/日志残留）**不在本次范围**：
  它有同源校验、非本漏洞攻击面，且站内消费方（wechat-popup、crossDomainAuth 等）依赖
  形态未梳理，单独立项跟进，本 spec 记录为已知残留。

### 外部站点（/Users/lanyu/Work/bklite-website）

- `src/lib/playgroundAuth.js`：`verifyLoginCallback` 不再从 URL 读 `token`，改为：
  校验本地 state 与 URL `third_login_code` 一致 → 读 `bk_lite_code` → POST 平台兑换
  接口 → 用响应体中的 token 写 `bklite_token` cookie。函数从同步改异步，调用方
  （`src/pages/playground/index.js`）随之调整；`cleanUrlParams` 增删 `bk_lite_code`。
- `docusaurus.config.js` `customFields` 新增 `tokenExchangeUrl`
  （`https://bklite.canway.net/api/proxy/core/api/legacy_third_login/exchange/`）。
  该 URL 不含 `bklite.ai` 字样，不受 Dockerfile 镜像替换影响，两站共用；如未来配置里
  出现 `bklite.ai` 域名的新字段，需确认镜像替换后的行为符合预期。
- 兑换失败展示现有 `callbackErrorMessage` 重新登录引导。

## 兼容与发布顺序

- 平台先发（authorize/exchange 端点 + 白名单 + 前端去 token 化），此时旧版 website
  的 `verifyLoginCallback` 收不到 `token` 参数会判定登录失败并引导重新登录——**这是
  可接受的一次性中断**（安全修复优先），website 侧尽快跟发。
- 白名单默认空即禁用，私有化部署未配置时 legacy 外跳整体失效、站内登录不受影响，
  符合「非白名单一律拒绝」的安全默认。
- 回滚只允许回退 website 消费方式，**不得**恢复「URL 携带 token」或去掉白名单校验。

## 测试要求

- server（新增/扩展 `apps/core/tests/`）：
  - 白名单：未配置一律 400；配置多值（`bklite.ai,bklite.cn`）后两域名均放行、
    未命中 400；`//attacker.com`、`https://bklite.ai@attacker.com`、`HTTPS://BKLITE.AI`、
    `bklite.ai.attacker.com`（后缀伪装）、IP 直连、带端口等向量。
  - code 生命周期：签发→兑换成功一次→二次兑换 4xx；过期 4xx；callback_host 不匹配 4xx。
  - `login_auth_callback`：白名单命中时 `login_result` 含 `legacy_redirect_url` 且
    不含 token 参数；缓存中旧 auth_request 携带非白名单 URL 时不回填。
  - 日志回归：断言日志输出不含 code/token 哨兵值。
- web：`signin/__tests__/` 与 `web/scripts/auth-callback-url-test.ts` 补攻击向量用例；
  断言仓库内不再存在把 token 拼入非同源 URL 的代码路径（删除
  `buildLegacyThirdLoginCallbackUrl` 后其测试同步更新）。
- website：`verifyLoginCallback` 单测（state 不一致拒绝、兑换失败处理、成功写 cookie）；
  `pnpm build` 通过。

## 验收（由发起会话执行，实现方需保证以下全部通过）

1. 原始 PoC 复验：构造
   `/auth/signin?callbackUrl=http://<非白名单主机>/cb?third_login_code=x&thirdLogin=true`，
   密码登录与 v2 三方登录两条路径完成后均停留站内 `PORTAL_HOME_PATH`，外域收不到
   任何请求参数中的 token 或 code。
2. 白名单命中路径（bklite.ai 与 bklite.cn 两个回调 host 分别模拟）端到端可登录：
   回跳 URL 仅含 `third_login_code` + `bk_lite_code`，兑换接口响应体返回 token，
   二次兑换失败；兑换接口对两个站点 origin 的 CORS 预检均放行。
3. `rg -n "searchParams.set\('token'" web/src` 仅剩同源 `buildThirdLoginCallbackUrl`
   一处（已记录的残留）。
4. 新增/修改代码测试全绿：
   `cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/core/tests/ --no-cov`；
   `cd web && pnpm lint && pnpm type-check` 及相关 jest/脚本测试；
   website 仓库 `pnpm build`。
5. 不触碰两仓库中与本修复无关的未提交工作（bk-lite 工作区存在进行中的
   credential-vault 变更，保持原样）。
6. 运维项（代码外，验收时核对已登记到变更说明）：现网需配置
   `LEGACY_THIRD_LOGIN_ALLOWED_CALLBACK_HOSTS=bklite.ai,bklite.cn`；修复上线时强制全员会话失效
   （轮换 JWT 签名密钥），并排查 access log 中外域 `callbackUrl` 带 `third_login_code`
   的历史请求。

## 变更说明（运维）

- 现网 `bklite.canway.net` 的 **Server** 必须设置
  `LEGACY_THIRD_LOGIN_ALLOWED_CALLBACK_HOSTS=bklite.ai,bklite.cn`。默认空则
  legacy 外跳整段禁用，站内登录不受影响。
- 兑换接口 CORS 由 Server 的 `legacy_third_login/exchange/` 按同一白名单回写
  `Access-Control-Allow-Origin`。Web `/api/proxy` **只转发该路径的 OPTIONS 预检**，
  不把整站 proxy 对白名单 origin 放开。私有化未配白名单时预检也没有 ACAO。
- 上线时轮换 JWT 签名密钥以失效存量会话；并排查历史 access log 中外域
  `callbackUrl` 且带 `third_login_code` 的请求。

## 实现状态（bk-lite）

- Server authorize/exchange、白名单、一次性码、login-auth v2 `legacy_redirect_url` 已落地。
- Web 已删除 `buildLegacyThirdLoginCallbackUrl`；登录成功改调 authorize；已登录直跳走
  `LegacyThirdLoginAuthorizeBridge`。
- website 仓库消费方已改为 `bk_lite_code` POST 兑换；回跳 URL 不再读取 `token`。
