'use client';

import React from 'react';
import { useRouter, usePathname, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import WithSideMenuLayout from '@/components/sub-layout';
import TopSection from '@/components/top-section';
import { ChannelTypeMap } from '@/app/system-manager/types/channel';

const ChannelDetailLayout = ({ children }: { children: React.ReactNode }) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const id = searchParams?.get('id') || 'email';
  const name = searchParams?.get('name') || '';
  const desc = searchParams?.get('desc') || '';

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
    },
    nats: {
      title: t('system.channel.nats'),
      desc: t('system.channel.natsDesc'),
      icon: 'dongzuo1'
    },
    sms: {
      title: t('system.channel.sms'),
      desc: t('system.channel.smsDesc'),
      icon: 'wendaduihua'
    },
    voice: {
      title: t('system.channel.voice'),
      desc: t('system.channel.voiceDesc'),
      icon: 'dadianhua'
    }
  };

  const builtin = typeMap[id as keyof ChannelTypeMap];
  const topSection = (
    <TopSection
      title={name || builtin?.title || id}
      content={desc || builtin?.desc || ''}
      iconType={builtin?.icon || 'wendaduihua'}
    />
  );

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
