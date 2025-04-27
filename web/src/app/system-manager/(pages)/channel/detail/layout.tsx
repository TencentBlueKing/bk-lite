'use client';

import React from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import WithSideMenuLayout from '@/components/sub-layout';
import TopSection from '@/components/top-section';
import { ChannelType, ChannelTypeMap } from '@/app/system-manager/types/channel'

const ChannelDetailLayout = ({ children }: { children: React.ReactNode }) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const id = (searchParams?.get('id') || 'email') as ChannelType;
  const name = searchParams?.get('name') || null;
  const desc = searchParams?.get('desc') || null;

  const handleBackButtonClick = () => {
    const pathSegments = pathname ? pathname.split('/').filter(Boolean) : [];
    if (pathSegments.length >= 3) {
      if (pathSegments.length === 3) {
        router.push('/system-manager/channel');
      } else if (pathSegments.length > 3) {
        router.push(`/system-manager/channel/detail?id=${id}&name=${name}&desc=${desc}`);
      }
    } else {
      router.back();
    }
  };

  const typeMap: ChannelTypeMap = {
    email: {
      title: t('system.channel.email'),
      desc: t('system.channel.emailDesc'),
      icon: 'youjian'
    },
    enterprise_wechat_bot: {
      title: t('system.channel.weCom'),
      desc: t('system.channel.weComDesc'),
      icon: 'qiwei2'
    }
  }

  const topSection = (
    <TopSection
      title={typeMap[id]?.title || t('system.channel.email')}
      content={typeMap[id]?.desc || t('system.channel.emailDesc')}
      iconType={typeMap[id]?.icon || 'youjian'}
    />
  )

  return (
    <WithSideMenuLayout
      topSection={topSection}
      showBackButton={true}
      onBackButtonClick={handleBackButtonClick}
    >
      {children}
    </WithSideMenuLayout>
  );
};

export default ChannelDetailLayout;
