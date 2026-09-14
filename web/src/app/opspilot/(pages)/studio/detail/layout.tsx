'use client';

import React, { useMemo, useCallback } from 'react';
import WithSideMenuLayout from '@/components/sub-layout';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { usePermissions } from '@/context/permissions';
import { MenuItem } from '@/types/index';
import { StudioProvider, useStudio } from '@/app/opspilot/context/studioContext';
import { pickStableIcon } from '@/app/opspilot/utils/pickStableIcon';
import OpsPilotEntityDetailIntro from '@/app/opspilot/components/opspilot-entity-detail-intro';

const STUDIO_ICON_POOL = ['Chatflow', 'gongzuotai', 'Copilot'];

const LayoutContent = ({ children }: { children: React.ReactNode }) => {
  const { t } = useTranslation();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { menus } = usePermissions();
  const { botInfo, isLoading } = useStudio();

  const id = searchParams?.get('id') || '';
  const queryName = searchParams?.get('name') || '';
  const queryDesc = searchParams?.get('desc') || '';
  const displayName = botInfo.name || queryName;
  const displayIntro = botInfo.introduction || queryDesc;

  const iconType =
    pickStableIcon(id, STUDIO_ICON_POOL, displayName) || 'gongzuotai';

  const processedMenuItems = useMemo(() => {
    const getMenuItemsForPath = (itemsList: MenuItem[], currentPath: string): MenuItem[] => {
      const findMatchedMenu = (items: MenuItem[]): MenuItem | null => {
        for (const menu of items) {
          if (menu.isDirectory) {
            if (menu.children?.length) {
              const found = findMatchedMenu(menu.children);
              if (found) return found;
            }
            continue;
          }

          if (menu.url && menu.url !== currentPath && currentPath.startsWith(menu.url)) {
            return menu;
          }

          if (menu.children?.length) {
            const found = findMatchedMenu(menu.children);
            if (found) return found;
          }
        }
        return null;
      };

      const matchedMenu = findMatchedMenu(itemsList);

      if (matchedMenu?.children?.length) {
        const validChildren = matchedMenu.children.filter((m) => !m.isNotMenuItem);
        return validChildren;
      }

      return [];
    };

    const originalMenuItems = getMenuItemsForPath(menus, pathname ?? '');

    if (isLoading) {
      return [originalMenuItems[0]];
    }

    const botType = botInfo.botType;
    if (botType === 2 && originalMenuItems.length > 0) {
      return originalMenuItems.filter((m) => !['bot_channel', 'bot_api'].includes(m.name));
    }

    if (botType === 3 && originalMenuItems.length > 0) {
      return originalMenuItems.filter((m) => !['bot_statistics', 'bot_channel'].includes(m.name));
    }

    return originalMenuItems.filter((m) => m.name !== 'bot_api');
  }, [menus, pathname, botInfo.botType, isLoading]);

  const handleBackButtonClick = useCallback(() => {
    router.push('/opspilot/studio');
  }, [router]);

  const intro = (
    <OpsPilotEntityDetailIntro
      name={displayName}
      description={displayIntro}
      iconType={iconType}
      fallbackTitle={t('studio.detail.title', '应用详情')}
      emptyIntroText={t('studio.detail.noIntro', '暂无简介')}
    />
  );

  return (
    <WithSideMenuLayout
      intro={intro}
      showBackButton={true}
      onBackButtonClick={handleBackButtonClick}
      layoutType="sideMenu"
      introLayout="unified"
      customMenuItems={processedMenuItems}
    >
      {children}
    </WithSideMenuLayout>
  );
};

const StudioDetailLayout = ({ children }: { children: React.ReactNode }) => {
  return (
    <StudioProvider>
      <LayoutContent>{children}</LayoutContent>
    </StudioProvider>
  );
};

export default StudioDetailLayout;
