'use client';

import { useEffect, useState, useCallback } from 'react';
import Script from 'next/script';
import { useRouter, usePathname } from 'next/navigation';
import { AntdRegistry } from '@ant-design/nextjs-registry';
import { SessionProvider, useSession } from 'next-auth/react';
import { LocaleProvider } from '@/context/locale';
import { ThemeProvider } from '@/context/theme';
import { MenusProvider, useMenus } from '@/context/menus';
import { UserInfoProvider } from '@/context/userInfo';
import { ClientProvider } from '@/context/client';
import { PermissionsProvider, usePermissions } from '@/context/permissions';
import AuthProvider from '@/context/auth';
import TopMenu from '@/components/top-menu';
import { ConfigProvider, message } from 'antd';
import Spin from '@/components/spin';
import '@/styles/globals.css';
import { MenuItem } from '@/types/index'

const Loader = () => (
  <div className="flex justify-center items-center h-screen">
    <Spin />
  </div>
);

const LayoutWithProviders = ({ children }: { children: React.ReactNode }) => {
  const { loading: permissionsLoading, hasPermission } = usePermissions();
  const { data: session, status } = useSession();
  const { loading: menusLoading, configMenus } = useMenus();
  const router = useRouter();
  const pathname = usePathname();
  const [isAllowed, setIsAllowed] = useState(false);

  // Consider a user with temporary_pwd as not fully authenticated
  const isAuthenticated = status === 'authenticated' && !!session && !session.user?.temporary_pwd;
  const isAuthLoading = status === 'loading';
  
  const isLoading = isAuthLoading || (isAuthenticated && (permissionsLoading || menusLoading));
  const authPaths = ['/auth/signin', '/auth/signout'];
  const excludedPaths = ['/no-permission', '/no-found', '/', ...authPaths];

  const isPathInMenu = useCallback((path: string, menus: MenuItem[]): boolean => {
    for (const menu of menus) {
      if (menu.url?.startsWith(path)) {
        return true;
      }
      if (menu.children && isPathInMenu(path, menu.children)) {
        return true;
      }
    }
    return false;
  }, []);

  useEffect(() => {
    const checkPermission = async () => {
      if ((pathname && authPaths.includes(pathname)) || !isAuthenticated) {
        setIsAllowed(true);
        return;
      }

      if (!isLoading) {
        if (pathname && excludedPaths.includes(pathname)) {
          setIsAllowed(true);
          return;
        }

        if (pathname && isPathInMenu(pathname, configMenus)) {
          if (hasPermission(pathname)) {
            setIsAllowed(true);
          } else {
            setIsAllowed(false);
            router.replace('/no-permission');
          }
        } else {
          setIsAllowed(false);
          router.replace('/no-found');
        }
      }
    };

    checkPermission();
  }, [isLoading, pathname, isAuthenticated, status, session, router]);

  if (isLoading || (isAuthenticated && !isAllowed && pathname && !excludedPaths.includes(pathname) && !isLoading)) {
    return <Loader />;
  }

  return (
    <div className="flex flex-col min-h-screen">
      {isAuthenticated && (
        <header className="sticky top-0 left-0 right-0 flex justify-between items-center header-bg">
          <TopMenu />
        </header>
      )}
      <main className={`flex-1 p-4 flex text-sm ${!isAuthenticated ? 'h-screen' : ''}`}>
        <AntdRegistry>{children}</AntdRegistry>
      </main>
    </div>
  );
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  useEffect(() => {
    message.config({
      maxCount: 2,
    });
  }, []);

  return (
    <html lang="en">
      <head>
        <title>BlueKing Lite - AI 原生的轻量化运维平台</title>
        <link rel="icon" href="/logo-site.png" type="image/png"/>
        <Script src="/iconfont.js" strategy="afterInteractive"/>
      </head>
      <body>
        {/* 全局 Context Provider 配置 */}
        <SessionProvider refetchInterval={30 * 60}>
          <ConfigProvider>
            <LocaleProvider>
              <ThemeProvider>
                <AuthProvider>
                  <UserInfoProvider>
                    <ClientProvider>
                      <MenusProvider>
                        <PermissionsProvider>
                          {/* 渲染布局 */}
                          <LayoutWithProviders>{children}</LayoutWithProviders>
                        </PermissionsProvider>
                      </MenusProvider>
                    </ClientProvider>
                  </UserInfoProvider>
                </AuthProvider>
              </ThemeProvider>
            </LocaleProvider>
          </ConfigProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
