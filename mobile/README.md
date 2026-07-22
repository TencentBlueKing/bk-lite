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
