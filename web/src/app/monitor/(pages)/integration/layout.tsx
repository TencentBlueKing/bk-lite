'use client';

import React from 'react';
import { Tooltip } from 'antd';
import WithSideMenuLayout from '@/components/sub-layout';
import { useRouter, useSearchParams, usePathname } from 'next/navigation';
import Icon from '@/components/icon';

const IntegrationDetailLayout = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pluginDisplayName = searchParams.get('plugin_display_name');
  const desc = searchParams.get('plugin_description');
  const objId = searchParams.get('id') || '';
  const icon = searchParams.get('icon');
  const pathname = usePathname();
  const isDetail = pathname.includes('/detail/');

  const handleBackButtonClick = () => {
    const params = new URLSearchParams({ objId });
    const targetUrl = `/monitor/integration/list?${params.toString()}`;
    router.push(targetUrl);
  };

  const TopSection = () => (
    <div className="p-4 rounded-md w-full h-[95px] flex items-center bg-[var(--color-bg-1)]">
      <Icon type={icon as string} className="text-6xl mr-[10px] min-w-[60px]" />
      <div className="w-full">
        <h2 className="text-lg font-semibold mb-2">{pluginDisplayName}</h2>
        <Tooltip title={desc}>
          <p className="truncate w-[95%] text-sm hide-text">{desc}</p>
        </Tooltip>
      </div>
    </div>
  );

  return (
    <WithSideMenuLayout
      topSection={isDetail ? <TopSection /> : null}
      showBackButton={isDetail}
      onBackButtonClick={handleBackButtonClick}
      layoutType={isDetail ? 'sideMenu' : 'segmented'}
    >
      {children}
    </WithSideMenuLayout>
  );
};

export default IntegrationDetailLayout;
