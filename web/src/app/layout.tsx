'use client';

import '@ant-design/v5-patch-for-react-19';
import { useEffect, useState, useCallback, useMemo } from 'react';
import Script from 'next/script';
import { useRouter, usePathname } from 'next/navigation';
import { AntdRegistry } from '@ant-design/nextjs-registry';
import { SessionProvider, useSession } from 'next-auth/react';
import { LocaleProvider } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';
import { ThemeProvider } from '@/context/theme';
import { MenusProvider, useMenus } from '@/context/menus';
import { UserInfoProvider } from '@/context/userInfo';
import { ClientProvider } from '@/context/client';
import { PermissionsProvider, usePermissions } from '@/context/permissions';
import AuthProvider from '@/context/auth';
import TopMenu from '@/components/top-menu';
import { ConfigProvider, Watermark, message } from 'antd';
import Spin from '@/components/spin';
import { portalBrandingDefaults, usePortalBranding } from '@/hooks/usePortalBranding';
import { getProfessionalDashboardPermissionPath } from '@/app/monitor/dashboards/registry';
import { isProfessionalDashboardRoute } from '@/app/monitor/dashboards/shared/utils';
import '@/styles/globals.css';
import { MenuItem } from '@/types/index'
import WithSideMenuLayout from '@/components/sub-layout'
import { shouldRenderSecondLayerMenu } from '@/utils/menuHelpers'
import { isSessionExpiredState } from '@/utils/sessionExpiry'
import { useUserInfoContext } from '@/context/userInfo';

const Loader = () => (
  <div className="flex justify-center items-center h-screen">
    <Spin />
  </div>
);

const applyWatermarkTemplate = (template: string, variables: Record<string, string>) => {
  return template.replace(/\$\{([a-zA-Z0-9_]+)\}/g, (match, key) => variables[key] ?? match);
};

const PortalBrandingHead = () => {
  const { portalName, faviconUrl } = usePortalBranding();
  const { t } = useTranslation();

  useEffect(() => {
    const head = document.head;
    let faviconLink = head.querySelector('link[data-portal-favicon="true"]') as HTMLLinkElement | null;

    if (!faviconLink) {
      faviconLink = document.createElement('link');
      faviconLink.rel = 'icon';
      faviconLink.setAttribute('data-portal-favicon', 'true');
      head.appendChild(faviconLink);
    }

    faviconLink.type = 'image/png';
    faviconLink.href = faviconUrl || portalBrandingDefaults.faviconUrl;
  }, [faviconUrl]);

  useEffect(() => {
    const slogan = t('common.portalSlogan', 'AI-Native Lightweight O&M Platform');
    document.title = `${portalName || portalBrandingDefaults.portalName} - ${slogan}`;
  }, [portalName, t]);

  return null;
};

const LayoutWithProviders = ({ children }: { children: React.ReactNode }) => {
  const { loading: permissionsLoading, hasPermission, menus } = usePermissions();
  const { data: session, status } = useSession();
  const { loading: menusLoading, configMenus } = useMenus();
  const { username, displayName } = useUserInfoContext();
  const { portalName, watermarkEnabled, watermarkText } = usePortalBranding();
  const router = useRouter();
  const pathname = usePathname();
  const [isAllowed, setIsAllowed] = useState(false);

  const isAuthenticated = status === 'authenticated' && !!session && !(session.user as any)?.temporary_pwd;
  const isAuthLoading = status === 'loading';

  const isLoading = isAuthLoading || (isAuthenticated && (permissionsLoading || menusLoading));
  const authPaths = ['/auth/signin', '/auth/signout', '/auth/signin/login-auth-result'];
  const excludedPaths = ['/no-permission', '/no-found', '/', ...authPaths];
  const hasResolvedPathname = pathname !== null;
  const isAuthRoute = Boolean(pathname && authPaths.includes(pathname));
  const isDashboardRoute = isProfessionalDashboardRoute(pathname);

  const shouldRenderMenu = useMemo(() => {
    if (pathname?.startsWith('/ops-console') || isDashboardRoute) {
      return false;
    }
    return shouldRenderSecondLayerMenu(pathname, menus);
  }, [pathname, menus, isDashboardRoute]);

  const isPathInMenu = useCallback((path: string, menus: MenuItem[]): boolean => {
    for (const menu of menus) {
      if (path?.startsWith(menu.url)) {
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
      if (isSessionExpiredState()) {
        setIsAllowed(true);
        return;
      }

      if ((pathname && authPaths.includes(pathname)) || !isAuthenticated) {
        setIsAllowed(true);
        return;
      }

      if (!isLoading) {
        if (pathname && excludedPaths.includes(pathname)) {
          setIsAllowed(true);
          return;
        }

        const permissionPath = getProfessionalDashboardPermissionPath(pathname) || pathname;

        if (permissionPath && isPathInMenu(permissionPath, configMenus)) {
          if (hasPermission(permissionPath)) {
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
  }, [isLoading, pathname, isAuthenticated, status, session, router, configMenus, hasPermission]);

  // Show password expiry reminder after login redirect
  useEffect(() => {
    if (isAuthenticated && !isAuthRoute) {
      const reminder = sessionStorage.getItem('password_expiry_reminder');
      if (reminder) {
        sessionStorage.removeItem('password_expiry_reminder');
        message.warning(reminder, 8);
      }
    }
  }, [isAuthenticated, isAuthRoute]);

  const hideTopMenu = useMemo(() => {
    return pathname?.startsWith('/opspilot/studio/chat');
  }, [pathname]);

  const watermarkContent = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return applyWatermarkTemplate(watermarkText || portalBrandingDefaults.watermarkText, {
      portalName: portalName || portalBrandingDefaults.portalName,
      username: username || (session?.user as any)?.username || 'admin',
      chname: displayName || (session?.user as any)?.username || 'admin',
      email: ((session?.user as any)?.email as string | undefined) || 'admin@bklite.local',
      phone: '13800138000',
      date: today,
    });
  }, [displayName, portalName, session, username, watermarkText]);

  if (isLoading || (isAuthenticated && !isAllowed && pathname && !excludedPaths.includes(pathname) && !isLoading)) {
    return <Loader />;
  }

  const layoutContent = (
    <AntdRegistry>
      <div className="flex flex-col min-h-screen">
        {isAuthenticated && hasResolvedPathname && !isAuthRoute && (
          <header className="sticky top-0 left-0 right-0 flex justify-between items-center header-bg">
            <TopMenu hideMainMenu={hideTopMenu} />
          </header>
        )}
        <main className={`main-content flex-1 p-4 flex text-sm ${!isAuthenticated || isAuthRoute ? 'h-screen' : ''}`}>
          {shouldRenderMenu ? (
            <WithSideMenuLayout
              layoutType="segmented"
              menuLevel={1}
            >
              {children}
            </WithSideMenuLayout>
          ) : (
            children
          )}
        </main>
      </div>
    </AntdRegistry>
  );

  if (!isAuthenticated || !watermarkEnabled) {
    return layoutContent;
  }

  return (
    <Watermark
      content={watermarkContent}
      gap={[120, 120]}
      rotate={-24}
      zIndex={20}
      font={{
        color: 'rgba(93,103,121,0.14)',
        fontSize: 14,
      }}
    >
      {layoutContent}
    </Watermark>
  );
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <title>BlueKing Lite</title>
        <link rel="icon" href="/logo-site.png" type="image/png" data-portal-favicon="true" />
        <Script src="/iconfont.js" strategy="afterInteractive"/>
        {/* cache bust: prepare-enterprise.mjs 重写该文件但 next dev 模式 HMR 不重发 script,
            浏览器可能缓存旧版(空数组)→ 22 卡片全显示 VTrak 占位。
            ?v=Date.now() 强制浏览器每次重拉,避免陈旧 brand 数据 */}
        <Script src={`/__enterprise-brands.js?v=${Date.now()}`} strategy="afterInteractive" />
      </head>
      <body>
        {/* 全局 Context Provider 配置 */}
        <SessionProvider refetchInterval={30 * 60}>
          <ConfigProvider>
            <LocaleProvider>
              <ThemeProvider>
                <AuthProvider>
                  <PortalBrandingHead />
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
