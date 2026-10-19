# 应用接入 RUM

本文只写「把一个已有网站接到已经可用的 RUM」。数据面、NATS 账号、Edge 路由和密钥文件见 [OPS-DEPLOY.md](./OPS-DEPLOY.md)，过不过看 [ACCEPTANCE.md](./ACCEPTANCE.md)。

149 环境上用本机 `web`（`pnpm dev`，`http://localhost:3000`）走过一遍：控制台应用 `aaa` 从「未接入」变成「已接入」，采集请求返回 202，自检为「RUM 已接通」。

## 前提

- 控制台能打开「集成 → 接入」，应用列表能读出来。读不出来时先看控制面，不要改站点。
- 浏览器能访问 `https://<控制台>/rum/v1/collect` 和 `/rum/bklite-rum-sdk.js`。
- 被接入的页面必须是安全上下文。`https://`、`http://localhost`、`http://127.0.0.1` 可以。`http://` 加局域网 IP 不行，SDK 里的 `crypto.randomUUID` 不存在，初始化直接失败。

## 流程

```text
控制台创建应用
  -> 填写精确 Origin 并保存
  -> 确认 Browser Key 和每分钟预算
  -> 把片段放进站点入口
  -> 用允许的 Origin 打开页面
  -> 接入页自检变为「RUM 已接通」
```

### 1. 创建应用

在「集成 → 接入」进入应用。还没有应用时，先到应用页创建。应用名会写进上报，必须和片段里的 `app.name` 一致。

### 2. 填写 Origin

在接入页第 1 步保存「允许的 Origin」。

- 写成 `协议://主机[:端口]`，不要带路径、查询或通配符。
- 浏览器地址栏里的源必须和这里逐字相同。`http://localhost:3000` 和 `http://127.0.0.1:3000` 是两个 Origin，用哪个就填哪个；两个都要访问就两条都保存。
- 保存后再打开被接入的页面。保存前发出的请求会被拒绝。

### 3. 确认密钥和预算

第 2 步的 Browser Key 只属于这个应用，会出现在前端代码里。

第 1 步的每分钟预算里，「请求数」是采集 HTTP 请求次数，不是页面浏览次数。一次打开页面会连续发出多笔 `/rum/v1/collect`。请求数设成 1 时，第一笔可以是 202，同一分钟里其余都是 429。产品默认是每分钟 6000 次请求。真实站点不要留在 1。

### 4. 安装片段

普通第三方站点用接入页第 3 步的 CDN 片段，放进站点入口：

```html
<script src="https://<控制台>/rum/bklite-rum-sdk.js" crossorigin="anonymous"></script>
<script>
  initCoreRum({
    app: { name: "<应用名>", environment: "production" },
    endpoint: "https://<控制台>/rum/v1",
    apiKey: "<Browser Key>",
    replay: false,
  })
</script>
```

本仓库的 `web` 已经在根布局挂了 `RumBootstrap`，不要再贴一段脚本。在 `web/.env.local` 写这三项，然后重启 `pnpm dev`。缺任何一项时接入保持关闭。

| 变量 | 值 |
| --- | --- |
| `NEXT_PUBLIC_RUM_APP` | 控制台里的应用名 |
| `NEXT_PUBLIC_RUM_ENDPOINT` | `https://<控制台>/rum/v1` |
| `NEXT_PUBLIC_RUM_API_KEY` | 该应用的 Browser Key |

`NEXT_PUBLIC_RUM_ENVIRONMENT` 可选，不写时是 `development`。SDK 由本机 `web/public/rum/bklite-rum-sdk.js` 提供，采集仍发到上面的 endpoint。

本地 Next 开发服务器请用 `http://localhost:3000` 打开。用 `http://127.0.0.1:3000` 时，开发资源会被当成跨源拦住，页面停在加载中。

### 5. 打开页面并自检

用第 2 步保存的 Origin 访问一次站点。然后回到接入页第 4 步。

通过时：

- 浏览器里 `/rum/v1/collect` 返回 202。
- 自检文案是「RUM 已接通，已收到并可查询该应用的 RUM 数据」。
- 接入列表状态为「已接入」，「最近接收」是刚才的时间。

「已接入」表示最近 15 分钟内网关接收和落库都成功。超过这个窗口会回到「未接入」，不表示配置被删掉。

## 对不上号时看哪里

| 现象 | 原因 |
| --- | --- |
| 页面能开，但没有发往 `/rum/v1/collect` 的请求 | HTTP 局域网地址不是安全上下文，或本仓库前端三项环境变量没写全 |
| 请求 4xx，且 Origin 与控制台不一致 | Origin 没保存，或打开的地址和保存的源不是同一个 |
| 第一笔 202，随后同一分钟大量 429 | 每分钟请求数太小 |
| 自检一直「等待数据」 | 页面没有用允许的 Origin 访问，或网关还没收到保存后的配置 |
| 登录页提示登录方式失败或登录已过期 | 本机 `NEXTAPI_URL`、`NEXTAUTH_SECRET` 没配。这是控制台自己的登录，不是 RUM 采集 |
