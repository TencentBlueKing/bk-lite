'use client';

import '@/polyfills/react-dom';
import '@/styles/globals.css';
import { AuthProvider } from '@/context/auth';
import { LocaleProvider } from '@/context/locale';
import { ThemeProvider } from '@/context/theme';
import { useEffect } from 'react';

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  useEffect(() => {
    // 禁用双指缩放和双击缩放
    const preventZoom = (e: TouchEvent) => {
      if (e.touches.length > 1) {
        e.preventDefault();
      }
    };

    let lastTouchEnd = 0;
    const preventDoubleTapZoom = (e: TouchEvent) => {
      const now = Date.now();
      if (now - lastTouchEnd <= 300) {
        e.preventDefault();
      }
      lastTouchEnd = now;
    };

    document.addEventListener('touchstart', preventZoom, { passive: false });
    document.addEventListener('touchend', preventDoubleTapZoom, { passive: false });
    document.addEventListener('gesturestart', (e) => e.preventDefault());

    return () => {
      document.removeEventListener('touchstart', preventZoom);
      document.removeEventListener('touchend', preventDoubleTapZoom);
      document.removeEventListener('gesturestart', (e) => e.preventDefault());
    };
  }, []);
  return (
    <html lang="en">
      <head>
        <title>BlueKing Lite - AI 原生的轻量化运维平台</title>
        <meta name="description" content="AI 原生的轻量化运维平台" />
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1.0, maximum-scale=1, viewport-fit=cover, user-scalable=no"
        />
        <link rel="stylesheet" href="/icon/font/iconfont.css"></link>
        <link rel="icon" href="/logo-site.png" type="image/png" />
      </head>
      <body className="antialiased">
        <ThemeProvider>
          <LocaleProvider>
            <AuthProvider>{children}</AuthProvider>
          </LocaleProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
