# 国密传输

> 给其他模块看的边界。信封字段、MAC、防重放和测试以
> [`specs/changes/gm-transport/spec.md`](../changes/gm-transport/spec.md) 为准。
> 改自己模块的浏览器请求前先看本文，再决定要不要接入。

## 边界

开关 `enable_gm_transport` 打开后，已经走统一封装的 BK-Lite 浏览器业务 JSON，查询串和正文用 SM2、SM3、SM4 信封保护。统一封装是 `web/src/utils/request.ts` 的 axios，以及 `web/src/utils/gmTransport.ts` 的 `gmFetch`。算法、中间件、公钥接口和浏览器加密实现在企业包。社区没有企业包时不注册中间件和公钥接口，`gmFetch` 就是普通 `fetch`，安全页不出现开关，也不能把开关写成开启。库里已经是开启的值保持不动，没有中间件时请求仍是明文。

中间件只处理带 `X-Gm-Transport: 1` 的 `/api/v1/` 请求：先解开请求，视图仍看到原来的方法、查询串和正文，再加密 JSON 响应。没有这个头的请求原样进入视图。开关打开也不拒绝明文。

本期接入的是 core 和系统管理里的这类 JSON。安全策略页提供开关。打开前自检私钥、Redis 和算法往返；私钥或 Redis 未就绪时，公钥接口降级，页面显示「已开启，未生效」。`disable_gm_transport` 把开关写成关闭。

私钥只来自 server 环境变量 `GM_SM2_PRIVATE_KEY`，不写入 `SystemSettings`，不写入日志。部署仓库 `bklite-website` 负责注入，本仓库不改部署模板。HTTPS、Traefik 证书、口令哈希和凭据落库加密保持原样。

## 其他模块接下来怎么接

业务 JSON 要接入时，把本模块里直接打 `/api/proxy/...` 的 `fetch` 换成 `gmFetch`。加密发生在浏览器，Next.js `/api/proxy` 只转发，不在代理里加解密。

上传、下载和 SSE 不要塞进现在这一份请求信封。现有请求信封按一次 HTTP 请求计算一个 MAC，文件要等整段正文到齐才能解开。后续若加密流式传输，另做按块加密。

各模块不要在自己的视图里按开关拒绝明文。公钥接口、降级后的页面请求，以及 Sidecar 直接打到 `/api/v1/` 的请求，都还要能以明文到达视图。
