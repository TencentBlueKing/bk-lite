'use client';

import React, { useState, useEffect, useMemo } from 'react';
import WithSideMenuLayout from '@/components/sub-layout';
import OnelineEllipsisIntro from '@/app/opspilot/components/oneline-ellipsis-intro';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import TopSection from "@/components/top-section";
import { useStudioApi } from '@/app/opspilot/api/studio';
import { usePermissions } from '@/context/permissions';
import { MenuItem } from '@/types/index';

const KnowledgeDetailLayout = ({ children }: { children: React.ReactNode }) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const id = searchParams ? searchParams.get('id') : null;
  const name = searchParams ? searchParams.get('name') : null;
  const desc = searchParams ? searchParams.get('desc') : null;
  const { fetchBotDetail } = useStudioApi();
  const { menus } = usePermissions();
  
  const [botType, setBotType] = useState<number | null>(null);
  const [isLoadingBotType, setIsLoadingBotType] = useState(true);

  useEffect(() => {
    if (!id) {
      setIsLoadingBotType(false);
      return;
    }

    const fetchBotData = async () => {
      try {
        setIsLoadingBotType(true);
        const botData = await fetchBotDetail(id);
        setBotType(botData.bot_type);
      } catch (error) {
        console.error('Failed to fetch bot data:', error);
      } finally {
        setIsLoadingBotType(false);
      }
    };

    fetchBotData();
  }, [id]);

  const processedMenuItems = useMemo(() => {
    const getMenuItemsForPath = (menus: MenuItem[], currentPath: string): MenuItem[] => {
      const matchedMenu = menus.find(menu => 
        menu.url && menu.url !== currentPath && currentPath.startsWith(menu.url)
      );

      if (matchedMenu?.children?.length) {
        const validChildren = matchedMenu.children.filter(m => !m.isNotMenuItem);
        return validChildren;
      }

      return [];
    };

    const originalMenuItems = getMenuItemsForPath(menus, pathname ?? '');

    // Return empty array to prevent menu flashing if still loading botType
    if (isLoadingBotType) {
      return [originalMenuItems[0]];
    }
    
    // For bot type 2, only show the first menu item
    if (botType === 2 && originalMenuItems.length > 0) {
      return originalMenuItems.filter(m => !['bot_channel', 'bot_api'].includes(m.name));
    }

    if (botType === 3 && originalMenuItems.length > 0) {
      return originalMenuItems.filter(m => !['bot_statistics', 'bot_channel'].includes(m.name));
    }
    
    return originalMenuItems.filter(m => m.name !== 'bot_api');
  }, [menus, pathname, botType, isLoadingBotType]);

  const handleBackButtonClick = () => {
    const pathSegments = pathname ? pathname.split('/').filter(Boolean) : [];
    if (pathSegments.length >= 3) {
      if (pathSegments.length === 3) {
        router.push('/opspilot/studio');
      } else if (pathSegments.length > 3) {
        router.push(`/opspilot/studio/detail?id=${id}&name=${name}&desc=${desc}`);
      }
    }
    else {
      router.back();
    }
  };

  const intro = (
    <OnelineEllipsisIntro name={name} desc={desc}></OnelineEllipsisIntro>
  );

  const getTopSectionContent = () => {
    switch (pathname) {
      case '/opspilot/studio/detail/settings':
        return (
          <>
            <TopSection
              title={t('studio.settings.title')}
              content={t('studio.settings.description')}
            />
          </>
        );
      case '/opspilot/studio/detail/channel':
        return (
          <>
            <TopSection
              title={t('studio.channel.title')}
              content={t('studio.channel.description')}
            />
          </>
        );
      case '/opspilot/studio/detail/logs':
        return (
          <>
            <TopSection
              title={t('studio.logs.title')}
              content={t('studio.logs.description')}
            />
          </>
        );
      case '/opspilot/studio/detail/statistics':
        return (
          <>
            <TopSection
              title={t('studio.statistics.title')}
              content={t('studio.statistics.description')}
            />
          </>
        );
      default:
        return (
          <>
            <TopSection
              title={t('studio.settings.title')}
              content={t('studio.settings.description')}
            />
          </>
        );
    }
  };

  const topSection = (
    getTopSectionContent()
  );

  return (
    <WithSideMenuLayout
      topSection={topSection}
      intro={intro}
      showBackButton={true}
      onBackButtonClick={handleBackButtonClick}
      customMenuItems={processedMenuItems}
    >
      {children}
    </WithSideMenuLayout>
  );
};

export default KnowledgeDetailLayout;
