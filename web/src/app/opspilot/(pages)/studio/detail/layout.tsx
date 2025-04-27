'use client';

import React from 'react';
import WithSideMenuLayout from '@/components/sub-layout';
import OnelineEllipsisIntro from '@/app/opspilot/components/oneline-ellipsis-intro';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import TopSection from "@/components/top-section";

const KnowledgeDetailLayout = ({ children }: { children: React.ReactNode }) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const id = searchParams ? searchParams.get('id') : null;
  const name = searchParams ? searchParams.get('name') : null;
  const desc = searchParams ? searchParams.get('desc') : null;


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
    >
      {children}
    </WithSideMenuLayout>
  );
};

export default KnowledgeDetailLayout;
