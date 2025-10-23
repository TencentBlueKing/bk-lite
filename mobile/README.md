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

```bash
pnpm dev:tauri
```

> 注意：会同时打开浏览器和 Tauri 窗口，使用 Tauri 窗口测试（无地址栏）

## 构建

### Android APK

```bash
pnpm build:android-debug    # 调试版 APK（推荐用于测试）
pnpm build:android          # 生产版 APK
pnpm build:android-all      # 所有架构 APK (aarch64, armv7, i686, x86_64)
pnpm build:aab              # AAB 格式（Google Play 上架）
```

**APK 输出路径：**
- Debug: `src-tauri/gen/android/app/build/outputs/apk/universal/debug/app-universal-debug.apk`
- Release: `src-tauri/gen/android/app/build/outputs/apk/universal/release/app-universal-release.apk`

> **注意**：构建命令已自动配置 Android NDK 路径，无需手动设置环境变量。

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
