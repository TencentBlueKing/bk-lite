'use client';

import React, { useState } from 'react';
import { useScreenAwareRouter } from '@/console-layout';
import { useTranslation } from '@/utils/i18n';
import SystemManagerEntityGrid from '@/app/system-manager/components/system-manager-entity-grid';
import SystemManagerUnifiedCard from '@/app/system-manager/components/system-manager-unified-card';

const ChannelPage = () => {
  const { t } = useTranslation();
  const router = useScreenAwareRouter();

  const [dataList] = useState([
    {
      id: 'email',
      name: t('system.channel.email'),
      icon: 'youjian',
      description: t('system.channel.emailDesc')
    },
    {
      id: 'enterprise_wechat_bot',
      name: t('system.channel.weCom'),
      icon: 'qiwei2',
      description: t('system.channel.weComDesc')
    },
    {
      id: 'nats',
      name: t('system.channel.nats'),
      icon: 'dongzuo1',
      description: t('system.channel.natsDesc')
    },
    {
      id: 'im_notification',
      name: t('system.channel.imNotification'),
      icon: 'liaotian',
      description: t('system.channel.imNotificationDesc'),
      url: '/system-manager/channel/im-notification',
    },
  ]);

  const handleCardClick = (item: typeof dataList[number]) => {
    if (item.url) {
      router.push(item.url);
      return;
    }
    const { id, name, description } = item;
    router.push(`/system-manager/channel/detail?id=${id}&name=${name}&desc=${description}`);
  };

  return (
    <div className="w-full">
      <SystemManagerEntityGrid
        title={t('system.channel.pageTitle')}
        description={t('system.channel.pageDesc')}
        items={dataList}
        loading={false}
        compactSkeleton
        getItemKey={(item) => item.id}
        renderCard={(item) => (
          <SystemManagerUnifiedCard
            name={item.name}
            description={item.description}
            icon={item.icon}
            onClick={() => handleCardClick(item)}
          />
        )}
      />
    </div>
  );
};

export default ChannelPage;
