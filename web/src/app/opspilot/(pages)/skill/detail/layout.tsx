'use client';

import React from 'react';
import { useTranslation } from '@/utils/i18n';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import TopSection from '@/components/top-section';
import WithSideMenuLayout from '@/components/sub-layout';
import OnelineEllipsisIntro from '@/app/opspilot/components/oneline-ellipsis-intro';

const SkillSettingsLayout = ({ children }: { children: React.ReactNode }) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const id = searchParams?.get('id') || '';
  const name = searchParams?.get('name') || '';
  const desc = searchParams?.get('desc') || '';


  const handleBackButtonClick = () => {
    const pathSegments = pathname ? pathname.split('/').filter(Boolean) : [];
    
    if (pathname === '/auth/signin') {
      return;
    }
    
    if (pathSegments.length >= 3) {
      if (pathSegments.length === 3) {
        router.push('/knowledge');
      } else if (pathSegments.length > 3) {
        if (id) {
          router.push(`/opspilot/knowledge/detail?id=${id}${name ? `&name=${name}` : ''}${desc ? `&desc=${desc}` : ''}`);
        } else {
          router.push('/opspilot/knowledge');
        }
      }
    }
    else {
      router.back();
    }
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
