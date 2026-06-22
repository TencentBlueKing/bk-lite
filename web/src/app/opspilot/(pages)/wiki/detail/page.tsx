'use client';

import React from 'react';
import { Tabs } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import MaterialTab from '@/app/opspilot/components/wiki/MaterialTab';

const WikiDetailPage: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const kbId = Number(searchParams?.get('id'));

  if (!kbId) {
    return <div className="p-4 text-gray-500">{t('wiki.empty')}</div>;
  }

  const items = [
    { key: 'material', label: t('wiki.material'), children: <MaterialTab kbId={kbId} /> },
  ];

  return (
    <div className="p-4">
      <Tabs defaultActiveKey="material" items={items} />
    </div>
  );
};

export default WikiDetailPage;
