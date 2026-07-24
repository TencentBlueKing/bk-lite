import '@/styles/globals.css';
import type { Metadata, Viewport } from 'next';
import { withBasePath } from '@/utils/basePath';
import { AppProviders } from './app-providers';

export const metadata: Metadata = {
  title: 'BlueKing Lite - AI 原生的轻量化运维平台',
  description: 'AI 原生的轻量化运维平台',
};

// 只由 Next.js 输出一个 viewport，确保 iOS 将 WebView 铺到安全区边缘。
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  interactiveWidget: 'resizes-content',
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
