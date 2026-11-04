# BK-Lite Mobile

基于 Next.js + Tauri 的跨平台移动应用。

## 技术栈

- **Next.js 15** - React 框架
- **Tauri 2.x** - 跨平台应用框架
- **TypeScript** - 类型安全
- **Ant Design Mobile** - UI 组件库

## 开发

### 浏览器开发（快速迭代）

```bash
pnpm dev
```

访问 http://localhost:3001

### Tauri 桌面开发（测试原生功能）

先在 `.env.local` 中配置 Tauri 后端地址：

```bash
NEXT_PUBLIC_API_URL=https://bklite.example.com
```

```bash
pnpm dev:tauri
```

> 注意：会同时打开浏览器和 Tauri 窗口，使用 Tauri 窗口测试（无地址栏）

## 构建

### H5

```bash
pnpm build:h5
```

H5 固定部署在 `/mobile/h5`，使用同源 `/api/proxy` 和 `/api/auth`，不需要配置 API 地址或 basePath。

### 移动端第三方登录

Mobile 复用系统管理里已经启用的登录认证，不单独建一套应用或用户。登录方式列表看公开绑定的 `client_login.evidence_modes` 是否包含 `oauth`，并再按当前客户端过滤：标准 OAuth（如飞书）在系统浏览器与对应容器都能选；企业微信只在企业微信容器内展示。选中后点主按钮才发起认证，走现有 `start_login_auth` 并带 `login_channel=oauth`。回调地址与 PC 相同：`{域名}/api/v1/core/api/login_auth/callback/`。成功或失败都回到 `/mobile/h5/auth/external`，再建立会话或退回登录页（默认回到账号密码）。

PC 不传 `login_channel`。企业微信因此仍是扫码；飞书、个人微信的授权地址也不因这个参数改变。

#### 飞书

- 工作台免登：飞书或 Lark 客户端打开移动端主页，页面调用 JSAPI `requestAccess` 取 code，再走现有 `login_auth` 换票。客户端低于 6.9 时回退 `requestAuthCode`。
- 免登失败，或不在飞书容器里：登录页显示 OAuth 按钮。
- 飞书开放平台需配置：重定向 URL（上面的回调）、H5 可信域名、移动端主页 `{域名}/mobile/h5/`。
- Server 出网需能访问 `open.feishu.cn` 与 `accounts.feishu.cn`。

#### 企业微信

工作台免登不用 JS-SDK，也不调用 `getAuthCode`。企业微信容器（User-Agent 含 `wxwork`）发现启用的企业微信登录绑定后，自动打开官方网页授权：

`https://open.weixin.qq.com/connect/oauth2/authorize?...&scope=snsapi_base&agentid={AgentId}#wechat_redirect`

`snsapi_base` 在企业微信内静默拿到 `code`。服务端仍用现有 `cgi-bin/auth/getuserinfo` 换成 `userid`，再按登录绑定匹配平台用户。失败时退回登录页，可再点企业微信入口或使用账号密码。个人微信（只有 `MicroMessenger`、没有 `wxwork`）和普通手机浏览器**不会**自动跳转，登录方式选择区也**不展示**企业微信（官方网页授权只能在企业微信内打开）。

企业微信管理后台：

1. 自建应用的网页授权及 JS-SDK 可信域名，覆盖回调域名。
2. OAuth 回调填 `{域名}/api/v1/core/api/login_auth/callback/`，与 PC 扫码是同一个地址。
3. 应用主页填 `{域名}/mobile/h5/`。
4. 可见范围包含要登录的成员。
5. BK-Lite 集成中心填企业 ID、应用 Secret、AgentId，并验证登录认证。私有化部署把「网页授权地址」改成实际地址，缺省是 `https://open.weixin.qq.com/connect/oauth2/authorize`。
6. 系统管理里启用企业微信登录绑定。外部字段用 `userid`。建议先同步用户；未匹配策略为拒绝时，通讯录里没有的成员不能登录。

Server 出网需能访问 `qyapi.weixin.qq.com`（换票和身份）。企业微信内置浏览器要能打开 `open.weixin.qq.com`。

真机自测：

1. 企业微信工作台打开该应用，应静默进入移动端首页，不经过扫码页。
2. 把成员移出可见范围或停用绑定后再打开，应回到登录页并出现失败提示；此时登录方式里可看到企业微信回落入口，账号密码仍可登录。
3. 手机系统浏览器打开 `{域名}/mobile/h5/login`，应只有账号密码和飞书等可在浏览器完成的方式，**不要**出现企业微信。
4. PC 登录页的企业微信仍是扫码。飞书工作台免登和飞书登录页 OAuth 保持可用。

钉钉尚未接入。飞书免登仍是厂商自己的 JSAPI；新增标准 OAuth 厂商声明 `oauth` 后，登录页一般能列出按钮，但企业微信这类只能在对应客户端内授权的厂商仍有容器限制。

### Tauri 前端产物

```bash
pnpm build:tauri
```

完整桌面安装包使用：

```bash
pnpm package:tauri
```

Tauri 开发和打包须在 `.env.local` 或 CI 环境中配置 `NEXT_PUBLIC_API_URL`。外部地址必须使用 HTTPS；仅 localhost 和 loopback 开发地址允许 HTTP。配置缺失或不合法时，命令会直接失败。

### Android APK

#### 1. 首次构建 - 配置签名密钥

> **说明**：签名密钥文件不会提交到 Git（已在 `.gitignore` 中）。
> - **团队协作**：需要通过安全渠道共享密钥文件和密码
> - **个人开发**：按以下步骤生成自己的密钥

**生成签名密钥**：

```bash
# Windows (PowerShell)
cd src-tauri/gen/android
keytool -genkeypair -v -storetype PKCS12 -keystore ../../../bklite-mobile-release.keystore -alias bklite-mobile -keyalg RSA -keysize 2048 -validity 10000

# 填写以下信息：
# - 密钥库密码（storePassword）
# - 密钥密码（keyPassword）
# - 姓名、组织等信息
```

**创建配置文件** `src-tauri/gen/android/keystore.properties`：

```properties
storeFile=../../../../bklite-mobile-release.keystore
storePassword=你的密钥库密码
keyAlias=bklite-mobile
keyPassword=你的密钥密码
```

> **重要**：
> - 密钥文件和配置不会提交到版本控制，请妥善保管
> - 团队成员需要获取相同的密钥文件才能构建兼容的签名 APK
> - 丢失密钥将无法更新已发布的应用

#### 2. 构建命令

```bash
pnpm build:android-debug    # 调试版 APK（推荐用于测试）
pnpm build:android          # 生产版 APK（已签名）
pnpm build:android-all      # 所有架构 APK (aarch64, armv7, i686, x86_64)
pnpm build:aab              # AAB 格式（Google Play 上架）
```

> **说明**：
> - 构建脚本会自动执行 `pnpm build:tauri` 来构建 Next.js（通过 `tauri.conf.json` 的 `beforeBuildCommand`）
> - 无需手动先运行 `pnpm build`
> - 构建命令已自动配置 Android NDK 路径，无需手动设置环境变量

**APK 输出路径：**
- Debug: `src-tauri/gen/android/app/build/outputs/apk/universal/debug/app-universal-debug.apk`
- Release: `src-tauri/gen/android/app/build/outputs/apk/universal/release/app-universal-release.apk` **(已签名)**

> **重要提示**：
> - 如果遇到 "无法连接" 错误，请确保没有其他开发服务器在运行
> - 构建过程中 Tauri 会自动处理 Next.js 的构建，请勿手动干预

> **注意**：
> - Release APK 会自动使用 `keystore.properties` 中的签名配置
> - 构建前确保已关闭所有开发服务器（`pnpm dev` 等）
> - Tauri 会通过 `tauri.conf.json` 的 `beforeBuildCommand` 自动构建 Next.js

## 环境配置

| 变量 | 使用阶段 | 是否必填 | 说明 |
|---|---|---:|---|
| `NEXT_PUBLIC_API_URL` | Tauri 本地开发、桌面与 Android 打包 | 是 | Web/Nginx 网关绝对地址；外部地址须为 HTTPS，loopback 开发地址可用 HTTP；构建期写入产物，修改后必须重新构建 |
| `TAURI_ALLOWED_HOSTS` | Tauri 本地开发与打包 | 否 | 多后端 host 白名单；默认从 API URL 派生，打包时固化到二进制 |
| `BK_SERVER_DEV_URL` | 浏览器本地开发 | 否 | `/api/proxy` 的本地代理目标，默认 `http://127.0.0.1:8011` |
| `BK_WEB_DEV_URL` | 浏览器本地开发 | 否 | `/api/auth` 的本地代理目标，默认 `http://127.0.0.1:3000` |

以下变量由工具自动注入，不应写入 `.env.local`：

- `BK_MOBILE_BUILD_TARGET`：由 `build:h5` 或 `build:tauri` 注入。
- `NEXT_PUBLIC_BASE_PATH`：H5 固定为 `/mobile/h5`，Tauri 固定为空。
- `TAURI_DEV_HOST`：由 Tauri CLI 在设备开发场景注入。
- `NODE_ENV`：由 Next.js 注入。

Android SDK/NDK、签名密钥以及 Docker 镜像源属于工具链或 CI 配置，不属于 Mobile 应用环境变量。

## 核心特性

- ✅ **CORS 无障碍** - Tauri Rust 后端代理，无跨域问题
- ✅ **自动环境适配** - Tauri 和浏览器环境自动切换
- ✅ **统一 API 客户端** - 所有请求通过 `src/api/request.ts`

## 项目结构

```
src/
├── api/          # API 客户端
├── app/          # Next.js 页面
├── components/   # React 组件
├── utils/        # 工具函数
│   ├── tauriFetch.ts      # 统一请求入口
│   └── tauriApiProxy.ts   # Tauri API 代理
src-tauri/
├── src/
│   ├── lib.rs           # Tauri 应用入口
│   └── api_proxy.rs     # Rust HTTP 代理
└── tauri.conf.json      # Tauri 配置
```

## 环境检测

```typescript
import { isTauriApp } from '@/utils/tauriFetch';

if (isTauriApp()) {
  // Tauri 环境逻辑
} else {
  // 浏览器环境逻辑
}
```
