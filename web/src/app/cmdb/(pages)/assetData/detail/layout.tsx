'use client';

import React, { useState } from 'react';
import { Spin } from 'antd';
import { RelationshipsProvider } from '@/app/cmdb/context/relationships';
import SideMenuLayout, { WithSideMenuLayoutProps } from '../components/sub-layout';
import { useRouter } from 'next/navigation';
import { getIconUrl } from '@/app/cmdb/utils/common';
import Image from 'next/image';
import { useSearchParams } from 'next/navigation';
import attrLayoutStyle from './layout.module.scss';
import { useTranslation } from '@/utils/i18n';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';

const LayoutContent: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [pageLoading] = useState<boolean>(false);
  const objIcon: string = searchParams.get('icn') || '';
  const modelName: string = searchParams.get('model_name') || '';
  const modelId: string = searchParams.get('model_id') || '';
  const instName: string = searchParams.get('inst_name') || searchParams.get('ip_addr') || '--';
  const { t } = useTranslation();

  const handleBackButtonClick = () => {
    router.push(`/cmdb/assetData`);
  };

  const intro = (
    <header className="flex items-center">
      <Image
        src={getIconUrl({ icn: objIcon, model_id: modelId })}
        className="block mr-[10px]"
        alt={t('picture')}
        width={30}
        height={30}
      />
      <div>
        <EllipsisWithTooltip text={modelName} className="w-[128px] whitespace-nowrap overflow-hidden text-ellipsis text-[14px] font-[800] mb-[2px] break-all" />
        <EllipsisWithTooltip text={instName} className="w-[128px] whitespace-nowrap overflow-hidden text-ellipsis break-all" />
      </div>
    </header>
  );

  const layoutProps: WithSideMenuLayoutProps = {
    children,
    showBackButton: true,
    onBackButtonClick: handleBackButtonClick,
    intro,
  };

  return (
    <div className={`flex flex-col ${attrLayoutStyle.attrLayout}`}>
      <Spin spinning={pageLoading}>
        <SideMenuLayout {...layoutProps} />
      </Spin>
    </div>
  );
};

const AboutLayout = ({ children }: { children: React.ReactNode }) => {
  return (
    <RelationshipsProvider>
      <LayoutContent>{children}</LayoutContent>
    </RelationshipsProvider>
  );
};

export default AboutLayout;
