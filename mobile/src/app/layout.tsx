import '@/styles/globals.css';
import type { Metadata, Viewport } from 'next';
import { MobilePolyfills } from '@/polyfills';
import { withBasePath } from '@/utils/basePath';
import zhMessages from '@/locales/zh.json';
import { AppProviders } from './app-providers';

export const metadata: Metadata = {
  title: zhMessages.common.portalTitle,
  description: zhMessages.common.portalDescription,
};

const isTauriBuild = process.env.BK_MOBILE_BUILD_TARGET === 'tauri';

// H5 保留浏览器缩放；Tauri 构建从首屏开始使用 App 级禁缩放策略。
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  interactiveWidget: 'resizes-content',
  ...(isTauriBuild ? {
    maximumScale: 1,
    userScalable: false,
  } : {}),
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hans">
      <head>
        <link rel="stylesheet" href={withBasePath('/icon/font/iconfont.css')}></link>
        <link rel="icon" href={withBasePath('/logo-site.png')} type="image/png" />
      </head>
      <body className="antialiased">
        <MobilePolyfills />
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
