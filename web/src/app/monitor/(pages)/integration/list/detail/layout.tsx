'use client';

import React from 'react';
import { Tooltip } from 'antd';
import WithSideMenuLayout from '@/components/sub-layout';
import TopSection from '@/components/top-section';
import SourceOriginBadge from '@/components/source-origin-badge';
import { useSearchParams } from 'next/navigation';
import { useScreenAwareRouter } from '@/console-layout';
import { useTranslation } from '@/utils/i18n';
import type { MenuItem } from '@/types';
import { getPluginBrandIcon } from '@/app/monitor/utils/common';
import { resolvePluginSourceBadge } from '@/app/monitor/utils/pluginSourceBadge';

const IntegrationDetailLayout = ({
  children
}: {
  children: React.ReactNode;
}) => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const router = useScreenAwareRouter();
  const pluginDisplayName = searchParams.get('plugin_display_name');
  const desc = searchParams.get('plugin_description');
  const objId = searchParams.get('id') || '';
  const icon = searchParams.get('icon');
  const pluginName = searchParams.get('plugin_name') || '';
  const packVersion = searchParams.get('pack_version') || '';
  const resolvedIcon = getPluginBrandIcon(pluginName) || icon || 'cc-default_默认';
  const templateType = searchParams.get('template_type') || '';
  const sourceBadge = resolvePluginSourceBadge({
    template_type: templateType,
    pack_version: packVersion
  });

  const handleBackButtonClick = () => {
    const params = new URLSearchParams({ objId });
    const targetUrl = `/monitor/integration/list?${params.toString()}`;
    router.push(targetUrl);
  };

  const intro = (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {pluginDisplayName}
      {sourceBadge.showPackTag && (
        <Tooltip
          title={
            sourceBadge.packKind === 'pinned'
              ? t('monitor.integrations.pinnedPackHint', '', {
                version: sourceBadge.packVersion
              })
              : t('monitor.integrations.builtinPackHint')
          }
        >
          <SourceOriginBadge
            kind={sourceBadge.packKind === 'pinned' ? 'imported' : 'builtin'}
            label={
              sourceBadge.packKind === 'pinned'
                ? sourceBadge.packVersion
                : t('monitor.integrations.builtinPack')
            }
          />
        </Tooltip>
      )}
      {sourceBadge.showSelfBuilt && (
        <SourceOriginBadge
          kind="custom"
          label={t('monitor.integrations.selfBuilt')}
        />
      )}
    </span>
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
      topSection={(
        <TopSection
          title={intro}
          content={desc || undefined}
          icon={(
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-[var(--color-fill-1)]">
              <img
                src={`/assets/icons/${resolvedIcon}.svg`}
                alt="icon"
                className="h-7 w-7"
                onError={(e) => {
                  (e.target as HTMLImageElement).src =
                    '/assets/icons/cc-default_默认.svg';
                }}
              />
            </div>
          )}
        />
      )}
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
