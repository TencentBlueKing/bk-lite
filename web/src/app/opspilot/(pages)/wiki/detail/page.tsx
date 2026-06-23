'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { Tabs } from 'antd';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import TopSection from '@/components/top-section';
import WithSideMenuLayout from '@/components/sub-layout';
import OnelineEllipsisIntro from '@/app/opspilot/components/oneline-ellipsis-intro';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { WikiKnowledgeBase } from '@/app/opspilot/types/wiki';
import BuildRecordTab from '@/app/opspilot/components/wiki/BuildRecordTab';
import CheckTab from '@/app/opspilot/components/wiki/CheckTab';
import GraphTab from '@/app/opspilot/components/wiki/GraphTab';
import MaterialTab from '@/app/opspilot/components/wiki/MaterialTab';
import OverviewTab from '@/app/opspilot/components/wiki/OverviewTab';
import PageTab from '@/app/opspilot/components/wiki/PageTab';
import QaTab from '@/app/opspilot/components/wiki/QaTab';

const WikiDetailPage: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const kbId = Number(searchParams?.get('id'));
  const { fetchKnowledgeBase } = useWikiApi();
  const [kb, setKb] = useState<WikiKnowledgeBase | null>(null);

  const loadKb = useCallback(() => {
    if (kbId) fetchKnowledgeBase(kbId).then(setKb).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  useEffect(() => {
    loadKb();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  if (!kbId) {
    return <div className="p-4 text-gray-500">{t('wiki.empty')}</div>;
  }

  const items = [
    { key: 'overview', label: t('wiki.overview'), children: <OverviewTab kbId={kbId} /> },
    { key: 'material', label: t('wiki.material'), children: <MaterialTab kbId={kbId} /> },
    { key: 'page', label: t('wiki.page'), children: <PageTab kbId={kbId} /> },
    { key: 'build', label: t('wiki.buildRecord'), children: <BuildRecordTab kbId={kbId} /> },
    { key: 'check', label: t('wiki.check'), children: <CheckTab kbId={kbId} /> },
    { key: 'graph', label: t('wiki.graph'), children: <GraphTab kbId={kbId} /> },
    { key: 'qa', label: t('wiki.qa'), children: <QaTab kbId={kbId} /> },
  ];

  return (
    <WithSideMenuLayout
      topSection={<TopSection title={t('wiki.title')} content={t('wiki.description')} />}
      intro={<OnelineEllipsisIntro name={kb?.name || ''} desc={kb?.introduction || ''} />}
      showSideMenu={false}
      showBackButton
      onBackButtonClick={() => router.push('/opspilot/wiki')}
    >
      {/* destroyOnHidden:切到某个 Tab 时重新挂载,使各 Tab 的 useEffect 重新拉取最新数据
          (否则首个 Tab 挂载后常驻,再次进入"资料"等页签不会重新请求,导致看到过期/空列表) */}
      <Tabs defaultActiveKey="overview" items={items} destroyOnHidden />
    </WithSideMenuLayout>
  );
};

export default WikiDetailPage;
