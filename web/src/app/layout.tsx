'use client';

import '@ant-design/v5-patch-for-react-19';
import { useEffect, useLayoutEffect, useState, useCallback, useMemo } from 'react';
import Script from 'next/script';
import { useRouter, usePathname } from 'next/navigation';
import { AntdRegistry } from '@ant-design/nextjs-registry';
import { SessionProvider, useSession } from 'next-auth/react';
import { LocaleProvider } from '@/context/locale';
import { useTranslation } from '@/utils/i18n';
import { ThemeBootstrap, ThemeProvider } from '@/theme';
import { useMenus } from '@/context/menus';
import { useClientData } from '@/context/client';
import { usePermissions } from '@/context/permissions';
import AuthProvider, { useAuth } from '@/context/auth';
import TopMenu from '@/app/(core)/components/top-menu';
import { Watermark, message } from 'antd';
import Spin from '@/components/spin';
import { portalBrandingDefaults, usePortalBranding } from '@/hooks/usePortalBranding';
import { getProfessionalDashboardPermissionPath } from '@/app/monitor/dashboards/metadata';
import { isProfessionalDashboardRoute } from '@/app/monitor/dashboards/shared/utils';
import '@/styles/globals.css';
import { MenuItem } from '@/types/index'
import WithSideMenuLayout from '@/components/sub-layout'
import { shouldRenderSecondLayerMenu } from '@/utils/menuHelpers'
import {
  PORTAL_TAB_TITLE_BOOTSTRAP_SCRIPT,
  resolvePortalTabTitle,
} from '@/utils/portalTabTitle'
import { resolveAppDisplayName } from '@/utils/appDisplayName';
import { isSessionExpiredState } from '@/utils/sessionExpiry'
import { useUserInfoContext } from '@/context/userInfo';
import { RouteScopedLayout } from '@/app/routeScopedLayout';
import dynamic from 'next/dynamic';

const GlobalWebchat = dynamic(
  () => import('@/app/(core)/components/global-webchat'),
  { ssr: false },
);

const Loader = () => (
  <div className="flex justify-center items-center h-screen">
    <Spin />
  </div>
);

const applyWatermarkTemplate = (template: string, variables: Record<string, string>) => {
  return template.replace(/\$\{([a-zA-Z0-9_]+)\}/g, (match, key) => variables[key] ?? match);
};

const PortalBrandingHead = () => {
  const { faviconUrl } = usePortalBranding();

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

  return null;
};

/**
 * Owns document.title after hydration.
 * Bootstrap script sets the cached title first; React's default <title> would otherwise
 * overwrite it with "BlueKing Lite" before useEffect runs (visible flicker).
 */
const PortalTabTitle = () => {
  const pathname = usePathname();
  const { clientData, appConfigList, loading: clientLoading, appConfigLoading } = useClientData();
  const { portalName, ready: brandingReady } = usePortalBranding();
  const { t } = useTranslation();
  const [title, setTitle] = useState(() => {
    if (typeof window === 'undefined') {
      return portalBrandingDefaults.portalName;
    }

    // Match bootstrap script / session cache on the very first client render so React
    // hydration does not briefly force the default "BlueKing Lite" title into the tab.
    const cachedTitle = resolvePortalTabTitle({
      pathname: window.location.pathname,
      portalName: portalBrandingDefaults.portalName,
      brandingReady: false,
      apps: [],
      clientsLoading: true,
      slogan: 'AI-Native Lightweight O&M Platform',
      fallbackPortalName: portalBrandingDefaults.portalName,
    });

    if (cachedTitle) {
      return cachedTitle;
    }

    if (document.title && document.title !== portalBrandingDefaults.portalName) {
      return document.title;
    }

    return portalBrandingDefaults.portalName;
  });

  useLayoutEffect(() => {
    const apps = (appConfigList.length > 0 ? appConfigList : clientData).map((app) => ({
      ...app,
      display_name: resolveAppDisplayName(app, t),
    }));
    const nextTitle = resolvePortalTabTitle({
      pathname,
      portalName: portalName || portalBrandingDefaults.portalName,
      brandingReady,
      apps,
      clientsLoading: clientLoading || appConfigLoading,
      slogan: t('common.portalSlogan', 'AI-Native Lightweight O&M Platform'),
      fallbackPortalName: portalBrandingDefaults.portalName,
    });

    if (!nextTitle) {
      return;
    }

    document.title = nextTitle;
    setTitle((current) => (current === nextTitle ? current : nextTitle));
  }, [
    appConfigList,
    appConfigLoading,
    brandingReady,
    clientData,
    clientLoading,
    pathname,
    portalName,
    t,
  ]);

  return <title suppressHydrationWarning>{title}</title>;
};

const LayoutWithProviders = ({ children }: { children: React.ReactNode }) => {
  const { loading: permissionsLoading, hasPermission, menus } = usePermissions();
  const { data: session, status } = useSession();
  const { isAuthenticated: authContextAuthenticated } = useAuth();
  const { loading: menusLoading, configMenus } = useMenus();
  const {
    username,
    displayName,
    loading: userInfoLoading,
  } = useUserInfoContext();
  const { portalName, watermarkEnabled, watermarkText } = usePortalBranding();
  const router = useRouter();
  const pathname = usePathname();
  const [isAllowed, setIsAllowed] = useState(false);
  const [isHeaderScrolled, setIsHeaderScrolled] = useState(false);

  useEffect(() => {
    const updateHeaderBackground = () => {
      setIsHeaderScrolled(window.scrollY > 0);
    };

    updateHeaderBackground();
    window.addEventListener('scroll', updateHeaderBackground, { passive: true });

    return () => window.removeEventListener('scroll', updateHeaderBackground);
  }, []);

  const isAuthenticated = authContextAuthenticated
    && !(session?.user as any)?.temporary_pwd;
  const isAuthLoading = status === 'loading' && !authContextAuthenticated;

  const authPaths = ['/auth/signin', '/auth/signout', '/auth/signin/login-auth-result'];
  const excludedPaths = ['/no-permission', '/no-found', '/', ...authPaths];
  const hasResolvedPathname = pathname !== null;
  const isAuthRoute = Boolean(pathname && authPaths.includes(pathname));
  const isDashboardRoute = isProfessionalDashboardRoute(pathname);
  const isResponsiveAppRoute = pathname?.startsWith('/apm') || isDashboardRoute;
  const isDashboardShareRoute = pathname?.startsWith('/ops-analysis/share/');
  const isDashboardRenderRoute = pathname?.startsWith(
    '/ops-analysis/render/execution/',
  );
  const isStandaloneDashboardRoute = (
    isDashboardShareRoute || isDashboardRenderRoute
  );
  const isLoading = isAuthLoading || (
    isAuthenticated
    && (
      isDashboardRenderRoute
        ? userInfoLoading || !username
        : permissionsLoading || menusLoading
    )
  );

  const shouldRenderMenu = useMemo(() => {
    if (
      pathname?.startsWith('/ops-console')
      || isDashboardRoute
      || isStandaloneDashboardRoute
    ) {
      return false;
    }
    return shouldRenderSecondLayerMenu(pathname, menus);
  }, [
    pathname,
    menus,
    isDashboardRoute,
    isStandaloneDashboardRoute,
  ]);

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
        if (
          (pathname && excludedPaths.includes(pathname))
          || isStandaloneDashboardRoute
        ) {
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
  }, [
    isLoading,
    pathname,
    isAuthenticated,
    status,
    session,
    router,
    configMenus,
    hasPermission,
    isStandaloneDashboardRoute,
  ]);

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

  if (
    isLoading
    || (
      isAuthenticated
      && !isAllowed
      && pathname
      && !excludedPaths.includes(pathname)
      && !isStandaloneDashboardRoute
      && !isLoading
    )
  ) {
    return <Loader />;
  }

  const layoutContent = (
    <div className={`flex flex-col pr-[var(--bk-webchat-dock-width)] transition-[padding-right] duration-200 ease-out ${isDashboardShareRoute ? 'h-screen overflow-hidden' : 'min-h-screen'} ${!isAuthRoute && !isResponsiveAppRoute ? 'min-w-[1280px]' : ''}`}>
      {isAuthenticated && hasResolvedPathname && !isAuthRoute && (
        <header
          className={`sticky top-0 left-0 right-0 flex justify-between items-center header-bg ${isHeaderScrolled ? 'header-bg-scrolled' : ''}`}
        >
          <TopMenu hideMainMenu={hideTopMenu} />
        </header>
      )}
      <main className={`main-content flex-1 p-4 flex text-sm ${isDashboardShareRoute ? 'min-h-0 overflow-hidden' : ''} ${!isAuthenticated || isAuthRoute ? 'h-screen' : ''}`}>
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
  );

  if (!isAuthenticated || !watermarkEnabled || isDashboardRenderRoute) {
    return (
      <>
        {layoutContent}
        {isAuthenticated && !isAuthRoute && <GlobalWebchat />}
      </>
    );
  }

  return (
    <>
      <Watermark
        content={watermarkContent}
        gap={[120, 120]}
        rotate={-24}
        zIndex={20}
        style={{ overflow: 'visible' }}
        font={{
          color: 'rgba(93,103,121,0.14)',
          fontSize: 14,
        }}
      >
        {layoutContent}
      </Watermark>
      {isAuthenticated && !isAuthRoute && <GlobalWebchat />}
    </>
  );
};

const StandardRouteLayout = ({ children }: { children: React.ReactNode }) => (
  <>
    <PortalTabTitle />
    <LayoutWithProviders>{children}</LayoutWithProviders>
  </>
);

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <ThemeBootstrap />
        {/* Tab title is owned by bootstrap script + PortalTabTitle (avoid a second React <title> overwrite). */}
        <script dangerouslySetInnerHTML={{ __html: PORTAL_TAB_TITLE_BOOTSTRAP_SCRIPT }} />
        <link rel="icon" href="/logo-site.png" type="image/png" data-portal-favicon="true" />
        <Script src="/iconfont.js" strategy="afterInteractive"/>
        {/* 企业品牌映射必须在 hydration 前加载；src 保持稳定，避免 SSR/客户端生成不同地址。 */}
        <Script src="/__enterprise-brands.js" strategy="beforeInteractive" />
      </head>
      <body>
        <AntdRegistry>
          {/* 全局 Context Provider 配置 */}
          <SessionProvider refetchInterval={30 * 60} refetchOnWindowFocus={false}>
            <LocaleProvider>
              <ThemeProvider>
                <AuthProvider>
                  <PortalBrandingHead />
                  <RouteScopedLayout StandardLayout={StandardRouteLayout}>
                    {children}
                  </RouteScopedLayout>
                </AuthProvider>
              </ThemeProvider>
            </LocaleProvider>
          </SessionProvider>
        </AntdRegistry>
      </body>
    </html>
  );
}
