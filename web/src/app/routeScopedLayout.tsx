'use client';

import type { ComponentType, ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { AntdRegistry } from '@ant-design/nextjs-registry';

import Spin from '@/components/spin';
import { UserInfoProvider } from '@/context/userInfo';
import { ClientProvider } from '@/context/client';
import { MenusProvider } from '@/context/menus';
import { PermissionsProvider } from '@/context/permissions';
import { isDashboardExecutionRenderRoute } from '@/app/routeScope';
import { EffectiveHomepageProvider } from '@/app/ops-analysis/context/effectiveHomepage';
import { HomepagePreferenceProvider } from '@/app/ops-analysis/context/homepagePreference';

const Loader = () => <Spin fullscreen />;

const DashboardExecutionRenderLayout = ({ children }: { children: ReactNode }) => {
  const { status } = useSession();

  // Chromium exchanges its one-time token for a scoped NextAuth session before
  // navigating here. Wait for that session only; ordinary user/menu providers
  // call APIs which are intentionally unavailable to a render identity.
  if (status === 'loading') {
    return <Loader />;
  }

  return (
    <AntdRegistry>
      <div className="flex min-h-screen flex-col overflow-visible min-w-[1280px]">
        <main className="main-content flex min-h-screen flex-1 overflow-visible p-0 text-sm">
          {children}
        </main>
      </div>
    </AntdRegistry>
  );
};

interface RouteScopedLayoutProps {
  children: ReactNode;
  StandardLayout: ComponentType<{ children: ReactNode }>;
}

export const RouteScopedLayout = ({
  children,
  StandardLayout,
}: RouteScopedLayoutProps) => {
  const pathname = usePathname();

  if (isDashboardExecutionRenderRoute(pathname)) {
    return (
      <DashboardExecutionRenderLayout>
        {children}
      </DashboardExecutionRenderLayout>
    );
  }

  return (
    <UserInfoProvider>
      <EffectiveHomepageProvider>
        <HomepagePreferenceProvider>
          <ClientProvider>
            <MenusProvider>
              <PermissionsProvider>
                <StandardLayout>{children}</StandardLayout>
              </PermissionsProvider>
            </MenusProvider>
          </ClientProvider>
        </HomepagePreferenceProvider>
      </EffectiveHomepageProvider>
    </UserInfoProvider>
  );
};
