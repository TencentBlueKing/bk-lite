'use client';

import '@/styles/globals.css';
import { AuthProvider } from '@/context/auth';
import { LocaleProvider } from '@/context/locale';
import { ThemeProvider } from '@/context/theme';

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <title>BlueKing Lite - AI 原生的轻量化运维平台</title>
        <meta name="description" content="AI 原生的轻量化运维平台" />
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
