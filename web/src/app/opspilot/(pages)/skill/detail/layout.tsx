'use client';

import React from 'react';
import { useTranslation } from '@/utils/i18n';
import { useRouter } from 'next/navigation';
import TopSection from '@/components/top-section';
import WithSideMenuLayout from '@/components/sub-layout';
import OnelineEllipsisIntro from '@/app/opspilot/components/oneline-ellipsis-intro';
import { SkillProvider, useSkill } from '@/app/opspilot/context/skillContext';

const LayoutContent = ({ children }: { children: React.ReactNode }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const { skillInfo } = useSkill();

  const handleBackButtonClick = () => {
    router.push('/opspilot/skill');
  };

  const intro = (
    <OnelineEllipsisIntro name={skillInfo.name} desc={skillInfo.introduction}></OnelineEllipsisIntro>
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

const SkillSettingsLayout = ({ children }: { children: React.ReactNode }) => {
  return (
    <SkillProvider>
      <LayoutContent>{children}</LayoutContent>
    </SkillProvider>
  );
};

export default SkillSettingsLayout;
