'use client';

import React from 'react';
import { useTranslation } from '@/utils/i18n';
import { useRouter, useSearchParams } from 'next/navigation';
import TopSection from '@/components/top-section';
import WithSideMenuLayout from '@/components/sub-layout';
import OnelineEllipsisIntro from '@/app/opspilot/components/oneline-ellipsis-intro';

const SkillSettingsLayout = ({ children }: { children: React.ReactNode }) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const router = useRouter();
  const name = searchParams?.get('name') || '';
  const desc = searchParams?.get('desc') || '';


  const handleBackButtonClick = () => {
    router.push('/opspilot/skill');
  };

  const intro = (
    <OnelineEllipsisIntro name={name} desc={desc}></OnelineEllipsisIntro>
  );

  return (
    <WithSideMenuLayout
      topSection={<TopSection title={t('skill.settings.title')} content={t('skill.settings.description')} />}
      intro={intro}
      showBackButton={true}
      onBackButtonClick={handleBackButtonClick}
    >
      {children}
    </WithSideMenuLayout>
  );
};

export default SkillSettingsLayout;
