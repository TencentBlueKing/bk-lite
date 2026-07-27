import '@/styles/globals.css';
import type { Metadata, Viewport } from 'next';
import { withBasePath } from '@/utils/basePath';
import { AppProviders } from './app-providers';

export const metadata: Metadata = {
  title: 'BlueKing Lite - AI 原生的轻量化运维平台',
  description: 'AI 原生的轻量化运维平台',
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
    <html lang="en">
      <head>
        <link rel="stylesheet" href={withBasePath('/icon/font/iconfont.css')}></link>
        <link rel="icon" href={withBasePath('/logo-site.png')} type="image/png" />
      </head>
      <body className="antialiased">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
