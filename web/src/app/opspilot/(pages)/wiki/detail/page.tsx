'use client';

import React from 'react';
import { Tabs } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import MaterialTab from '@/app/opspilot/components/wiki/MaterialTab';
import OverviewTab from '@/app/opspilot/components/wiki/OverviewTab';
import QaTab from '@/app/opspilot/components/wiki/QaTab';

const WikiDetailPage: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const kbId = Number(searchParams?.get('id'));

  if (!kbId) {
    return <div className="p-4 text-gray-500">{t('wiki.empty')}</div>;
  }

  const items = [
    { key: 'overview', label: t('wiki.overview'), children: <OverviewTab kbId={kbId} /> },
    { key: 'material', label: t('wiki.material'), children: <MaterialTab kbId={kbId} /> },
    { key: 'qa', label: t('wiki.qa'), children: <QaTab kbId={kbId} /> },
  ];

  return (
    <div className="p-4">
      <Tabs defaultActiveKey="overview" items={items} />
    </div>
  );
};

export default WikiDetailPage;
