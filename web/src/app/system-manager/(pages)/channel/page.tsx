'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import EntityList from '@/components/entity-list';

const ChannelPage = () => {
  const { t } = useTranslation();
  const router = useRouter();

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
  ]);

  const handleCardClick = (item: any) => {
    const { id, name, description } = item;
    router.push(`/system-manager/channel/detail?id=${id}&name=${name}&desc=${description}`);
  };

  return (
    <div className='w-full'>
      <EntityList
        loading={false}
        data={dataList}
        onCardClick={handleCardClick}
      />
    </div>
  );
};

export default ChannelPage;
