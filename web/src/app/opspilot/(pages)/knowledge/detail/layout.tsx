'use client';

import React from 'react';
import { useTranslation } from '@/utils/i18n';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import TopSection from '@/components/top-section';
import WithSideMenuLayout from '@/components/sub-layout';
import TaskProgress from '@/app/opspilot/components/task-progress'
import OnelineEllipsisIntro from '@/app/opspilot/components/oneline-ellipsis-intro';

const KnowledgeDetailLayout = ({ children }: { children: React.ReactNode }) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const id = searchParams?.get('id') || '';
  const name = searchParams?.get('name') || '';
  const desc = searchParams?.get('desc') || '';


  const handleBackButtonClick = () => {
    const pathSegments = pathname ? pathname.split('/').filter(Boolean) : [];
    if (pathSegments.length >= 3) {
      if (pathSegments.length === 3) {
        router.push('/knowledge');
      } else if (pathSegments.length > 3) {
        router.push(`/opspilot/knowledge/detail?id=${id}&name=${name}&desc=${desc}`);
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
      case '/opspilot/knowledge/detail/documents':
        return (
          <>
            <TopSection
              title={t('knowledge.documents.title')}
              content={t('knowledge.documents.description')}
            />
          </>
        );
      case '/opspilot/knowledge/detail/testing':
        return (
          <>
            <TopSection
              title={t('knowledge.testing.title')}
              content={t('knowledge.testing.description')}
            />
          </>
        );
      case '/opspilot/knowledge/detail/settings':
        return (
          <>
            <TopSection
              title={t('knowledge.settings.title')}
              content={t('knowledge.testing.description')}
            />
          </>
        );
      default:
        return (
          <>
            <TopSection
              title={t('knowledge.documents.title')}
              content={t('knowledge.documents.description')}
            />
          </>
        );
    }
  };

  const topSection = (
    getTopSectionContent()
  );

  return (
    <>
      <WithSideMenuLayout
        topSection={topSection}
        intro={intro}
        showBackButton={true}
        showProgress={true}
        taskProgressComponent={<TaskProgress />}
        onBackButtonClick={handleBackButtonClick}
      >
        {children}
      </WithSideMenuLayout>
    </>
  );
};

export default KnowledgeDetailLayout;
