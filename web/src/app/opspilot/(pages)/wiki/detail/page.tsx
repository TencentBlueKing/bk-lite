'use client';

import React from 'react';
import { Tabs } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import BuildRecordTab from '@/app/opspilot/components/wiki/BuildRecordTab';
import CheckTab from '@/app/opspilot/components/wiki/CheckTab';
import MaterialTab from '@/app/opspilot/components/wiki/MaterialTab';
import OverviewTab from '@/app/opspilot/components/wiki/OverviewTab';
import PageTab from '@/app/opspilot/components/wiki/PageTab';
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
    { key: 'page', label: t('wiki.page'), children: <PageTab kbId={kbId} /> },
    { key: 'build', label: t('wiki.buildRecord'), children: <BuildRecordTab kbId={kbId} /> },
    { key: 'check', label: t('wiki.check'), children: <CheckTab kbId={kbId} /> },
    { key: 'qa', label: t('wiki.qa'), children: <QaTab kbId={kbId} /> },
  ];

  return (
    <div className="p-4">
      <Tabs defaultActiveKey="overview" items={items} />
    </div>
  );
};

export default WikiDetailPage;
