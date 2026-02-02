'use client';

import React, { useMemo } from 'react';
import WithSideMenuLayout from '@/components/sub-layout';
import OnelineEllipsisIntro from '@/app/opspilot/components/oneline-ellipsis-intro';
import { useRouter, usePathname } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import TopSection from "@/components/top-section";
import { usePermissions } from '@/context/permissions';
import { MenuItem } from '@/types/index';
import { StudioProvider, useStudio } from '@/app/opspilot/context/studioContext';

const LayoutContent = ({ children }: { children: React.ReactNode }) => {
  const { t } = useTranslation();
  const pathname = usePathname();
  const router = useRouter();
  const { menus } = usePermissions();
  const { botInfo, isLoading } = useStudio();

  const processedMenuItems = useMemo(() => {
    const getMenuItemsForPath = (menus: MenuItem[], currentPath: string): MenuItem[] => {
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
      
      const matchedMenu = findMatchedMenu(menus);

      if (matchedMenu?.children?.length) {
        const validChildren = matchedMenu.children.filter(m => !m.isNotMenuItem);
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
      return originalMenuItems.filter(m => !['bot_channel', 'bot_api'].includes(m.name));
    }

    if (botType === 3 && originalMenuItems.length > 0) {
      return originalMenuItems.filter(m => !['bot_statistics', 'bot_channel'].includes(m.name));
    }
    
    return originalMenuItems.filter(m => m.name !== 'bot_api');
  }, [menus, pathname, botInfo.botType, isLoading]);

  const handleBackButtonClick = () => {
    router.push('/opspilot/studio');
  };

  const intro = (
    <OnelineEllipsisIntro name={botInfo.name} desc={botInfo.introduction}></OnelineEllipsisIntro>
  );

  const getTopSectionContent = () => {
    switch (pathname) {
      case '/opspilot/studio/detail/settings':
        return (
          <TopSection
            title={t('studio.settings.title')}
            content={t('studio.settings.description')}
          />
        );
      case '/opspilot/studio/detail/channel':
        return (
          <TopSection
            title={t('studio.channel.title')}
            content={t('studio.channel.description')}
          />
        );
      case '/opspilot/studio/detail/logs':
        return (
          <TopSection
            title={t('studio.logs.title')}
            content={t('studio.logs.description')}
          />
        );
      case '/opspilot/studio/detail/statistics':
        return (
          <TopSection
            title={t('studio.statistics.title')}
            content={t('studio.statistics.description')}
          />
        );
      default:
        return (
          <TopSection
            title={t('studio.settings.title')}
            content={t('studio.settings.description')}
          />
        );
    }
  };

  return (
    <WithSideMenuLayout
      topSection={getTopSectionContent()}
      intro={intro}
      showBackButton={true}
      onBackButtonClick={handleBackButtonClick}
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
