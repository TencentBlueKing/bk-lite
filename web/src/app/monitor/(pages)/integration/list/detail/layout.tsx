'use client';

import React from 'react';
import { Typography } from 'antd';
import WithSideMenuLayout from '@/components/sub-layout';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import type { MenuItem } from '@/types';

const IntegrationDetailLayout = ({
  children
}: {
  children: React.ReactNode;
}) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pluginDisplayName = searchParams.get('plugin_display_name');
  const desc = searchParams.get('plugin_description');
  const objId = searchParams.get('id') || '';
  const icon = searchParams.get('icon');
  const templateType = searchParams.get('template_type') || '';

  const handleBackButtonClick = () => {
    const params = new URLSearchParams({ objId });
    const targetUrl = `/monitor/integration/list?${params.toString()}`;
    router.push(targetUrl);
  };

  const TopSection = () => (
    <div className="p-4 rounded-md w-full min-h-[95px] flex items-start bg-[var(--color-bg-2)]">
      <div className="w-[72px] h-[72px] mr-[10px] min-w-[72px] rounded-lg flex items-center justify-center bg-[var(--color-fill-1)]">
        <img
          src={`/assets/icons/${icon}.svg`}
          alt="icon"
          className="w-[60px] h-[60px]"
          onError={(e) => {
            (e.target as HTMLImageElement).src =
              '/assets/icons/cc-default_默认.svg';
          }}
        />
      </div>
      <div className="w-full min-w-0">
        <h2 className="text-lg font-semibold mb-2">{pluginDisplayName}</h2>
        <Typography.Paragraph
          className="!mb-0 text-sm text-[var(--color-text-3)]"
          ellipsis={{
            rows: 2,
            expandable: 'collapsible',
            symbol: (expanded: boolean) =>
              expanded ? t('common.collapse') : t('common.expand')
          }}
        >
          {desc}
        </Typography.Paragraph>
      </div>
    </div>
  );

  const detailMenuItems: MenuItem[] = [
    {
      name: 'integration_configure',
      title: t('monitor.integrations.configure'),
      url: '/monitor/integration/list/detail/configure',
      icon: 'settings-fill',
      operation: []
    },
    {
      name: 'integration_metric',
      title: t('monitor.metric'),
      url: '/monitor/integration/list/detail/metric',
      icon: 'guanli',
      operation: []
    },
    ...(templateType === 'snmp'
      ? [
        {
          name: 'integration_collect',
          title: t('monitor.integrations.collect'),
          url: '/monitor/integration/list/detail/collect',
          icon: 'caijiqi',
          operation: []
        }
      ]
      : [])
  ];

  return (
    <WithSideMenuLayout
      topSection={<TopSection />}
      showBackButton={true}
      onBackButtonClick={handleBackButtonClick}
      layoutType="sideMenu"
      customMenuItems={detailMenuItems}
    >
      {children}
    </WithSideMenuLayout>
  );
};

export default IntegrationDetailLayout;
