'use client';

import React, { useState } from 'react';
import { Button, message, Spin, Tooltip } from 'antd';
import { RelationshipsProvider } from '@/app/cmdb/context/relationships';
import SideMenuLayout, { WithSideMenuLayoutProps } from '../components/sub-layout';
import { useRouter } from 'next/navigation';
import { getIconUrl } from '@/app/cmdb/utils/common';
import Image from 'next/image';
import { useSearchParams } from 'next/navigation';
import attrLayoutStyle from './layout.module.scss';
import { useTranslation } from '@/utils/i18n';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { StarFilled, StarOutlined } from '@ant-design/icons';
import { useFollowedAssets } from '@/app/cmdb/hooks/useFollowedAssets';

const LayoutContent: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [pageLoading] = useState<boolean>(false);
  const objIcon: string = searchParams.get('icn') || '';
  const modelName: string = searchParams.get('model_name') || '';
  const modelId: string = searchParams.get('model_id') || '';
  const instId: string = searchParams.get('inst_id') || '';
  const instName: string = searchParams.get('inst_name') || searchParams.get('ip_addr') || '--';
  const { t } = useTranslation();
  const { isFollowed, followAsset, unfollowAsset, submitting } = useFollowedAssets();
  const followed = modelId && instId ? isFollowed(modelId, instId) : false;

  const handleBackButtonClick = () => {
    router.back();
  };

  const handleFollowClick = async () => {
    if (!modelId || !instId) return;
    if (followed) {
      await unfollowAsset(modelId, instId);
      message.success(t('AssetSearch.unfollowSuccess'));
      return;
    }
    await followAsset({ model_id: modelId, inst_id: instId });
    message.success(t('AssetSearch.followSuccess'));
  };

  const intro = (
    <header className="grid grid-cols-[30px_minmax(0,1fr)_28px] items-start gap-[10px]">
      <Image
        src={getIconUrl({ icn: objIcon, model_id: modelId })}
        className="block"
        alt={t('picture')}
        width={30}
        height={30}
      />
      <div className="min-w-0">
        <EllipsisWithTooltip text={modelName} className="block w-full whitespace-nowrap overflow-hidden text-ellipsis text-[14px] font-[800] mb-[2px] break-all" />
        <EllipsisWithTooltip text={instName} className="block w-full whitespace-nowrap overflow-hidden text-ellipsis break-all" />
      </div>
      <Tooltip title={followed ? t('AssetSearch.unfollow') : t('AssetSearch.follow')}>
        <Button
          type="text"
          size="small"
          loading={submitting}
          icon={followed ? <StarFilled /> : <StarOutlined />}
          className={`shrink-0 ${followed ? 'text-[#fa8c16]' : ''}`}
          onClick={handleFollowClick}
        />
      </Tooltip>
    </header>
  );

  const layoutProps: WithSideMenuLayoutProps = {
    children,
    intro,
    showBackButton: true,
    onBackButtonClick: handleBackButtonClick,
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
