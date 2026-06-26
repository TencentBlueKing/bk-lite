'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import TopSection from '@/components/top-section';
import WithSideMenuLayout from '@/components/sub-layout';
import OnelineEllipsisIntro from '@/app/opspilot/components/oneline-ellipsis-intro';
import { MenuItem } from '@/types/index';
import { useWikiApi } from '@/app/opspilot/api/wiki';
import { WikiKnowledgeBase } from '@/app/opspilot/types/wiki';
import BuildRecordTab from '@/app/opspilot/components/wiki/BuildRecordTab';
import CheckTab from '@/app/opspilot/components/wiki/CheckTab';
import KnowledgeTab from '@/app/opspilot/components/wiki/KnowledgeTab';
import MaterialTab from '@/app/opspilot/components/wiki/MaterialTab';
import OverviewTab from '@/app/opspilot/components/wiki/OverviewTab';
import SettingsTab from '@/app/opspilot/components/wiki/SettingsTab';

const WikiDetailPage: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const kbId = Number(searchParams?.get('id'));
  const activeTab = searchParams?.get('tab') || 'overview';
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

  // 首次进入(无 tab)补上 ?tab=overview,使左侧菜单默认高亮"概览"(replace 不污染后退栈)
  useEffect(() => {
    if (kbId && !searchParams?.get('tab')) {
      const p = new URLSearchParams(searchParams?.toString() || '');
      p.set('tab', 'overview');
      router.replace(`/opspilot/wiki/detail?${p.toString()}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, searchParams]);

  // 左侧菜单(统一 opspilot 详情布局,参考智能体/记忆):activeKeyword 模式按 ?tab= 区分页签,
  // 菜单 url 需自带完整查询串(保留 id/name/desc + 设置 tab),激活态匹配 item.name。
  const menuItems: MenuItem[] = useMemo(() => {
    const base = (tab: string) => {
      const p = new URLSearchParams(searchParams?.toString() || '');
      p.set('tab', tab);
      return `/opspilot/wiki/detail?${p.toString()}`;
    };
    return [
      { title: t('wiki.overview'), url: base('overview'), icon: 'tongji', name: 'overview', operation: [] },
      { title: t('wiki.material'), url: base('material'), icon: 'wendang', name: 'material', operation: [] },
      { title: t('wiki.knowledge'), url: base('knowledge'), icon: 'zhishitupu', name: 'knowledge', operation: [] },
      { title: t('wiki.buildRecord'), url: base('build'), icon: 'biangengjilu', name: 'build', operation: [] },
      { title: t('wiki.check'), url: base('check'), icon: 'yichangjiance', name: 'check', operation: [] },
      { title: t('wiki.settings'), url: base('settings'), icon: 'shezhi', name: 'settings', operation: [] },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t, searchParams]);

  if (!kbId) {
    return <div className="p-4 text-gray-500">{t('wiki.empty')}</div>;
  }

  // 仅挂载当前页签 → 切换即重新拉取最新数据(等价于原 Tabs 的 destroyOnHidden)
  const renderTab = () => {
    switch (activeTab) {
      case 'material':
        return <MaterialTab kbId={kbId} />;
      case 'knowledge':
        return <KnowledgeTab kbId={kbId} />;
      case 'build':
        return <BuildRecordTab kbId={kbId} />;
      case 'check':
        return <CheckTab kbId={kbId} />;
      case 'settings':
        return <SettingsTab kbId={kbId} />;
      case 'overview':
      default:
        return <OverviewTab kbId={kbId} />;
    }
  };

  return (
    <WithSideMenuLayout
      topSection={<TopSection title={t('wiki.title')} content={t('wiki.description')} />}
      intro={<OnelineEllipsisIntro name={kb?.name || ''} desc={kb?.introduction || ''} />}
      activeKeyword
      keywordName="tab"
      customMenuItems={menuItems}
      showBackButton
      onBackButtonClick={() => router.push('/opspilot/wiki')}
    >
      {renderTab()}
    </WithSideMenuLayout>
  );
};

export default WikiDetailPage;
