'use client';

import React from 'react';
import { Button, message, Tooltip } from 'antd';
import { RelationshipsProvider } from '@/app/cmdb/context/relationships';
import SideMenuLayout, { WithSideMenuLayoutProps } from '../components/sub-layout';
import { useRouter } from 'next/navigation';
import ModelIcon from '@/app/cmdb/components/model-icon';
import { useSearchParams } from 'next/navigation';
import attrLayoutStyle from './layout.module.scss';
import { useTranslation } from '@/utils/i18n';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { StarFilled, StarOutlined } from '@ant-design/icons';
import { useFollowedAssets } from '@/app/cmdb/hooks/useFollowedAssets';

const LayoutContent: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const router = useRouter();
  const searchParams = useSearchParams();
  const objIcon: string = searchParams.get('icn') || '';
  const modelName: string = searchParams.get('model_name') || '';
  const modelId: string = searchParams.get('model_id') || '';
  const instUuid: string = searchParams.get('inst_uuid') || '';
  const instName: string = searchParams.get('inst_name') || searchParams.get('ip_addr') || '--';
  const { t } = useTranslation();
  const { isFollowed, followAsset, unfollowAsset, submitting } = useFollowedAssets();
  const followed = modelId && instUuid ? isFollowed(modelId, instUuid) : false;

  const handleBackButtonClick = () => {
    router.back();
  };

  const handleFollowClick = async () => {
    if (!modelId || !instUuid) return;
    if (followed) {
      await unfollowAsset(modelId, instUuid);
      message.success(t('AssetSearch.unfollowSuccess'));
      return;
    }
    await followAsset({ model_id: modelId, inst_uuid: instUuid });
    message.success(t('AssetSearch.followSuccess'));
  };

  const intro = (
    <header className="grid grid-cols-[40px_minmax(0,1fr)_28px] items-start gap-3">
      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-[var(--color-fill-1)]">
        <ModelIcon
          icon={objIcon}
          modelId={modelId}
          className="block"
          alt={t('picture')}
          width={28}
          height={28}
        />
      </div>
      <div className="min-w-0">
        <EllipsisWithTooltip text={modelName} className="mb-0.5 block w-full overflow-hidden text-ellipsis whitespace-nowrap break-all text-base font-semibold text-[var(--color-text-1)]" />
        <EllipsisWithTooltip text={instName} className="block w-full overflow-hidden text-ellipsis whitespace-nowrap break-all text-xs text-[var(--color-text-3)]" />
      </div>
      <Tooltip title={followed ? t('AssetSearch.unfollow') : t('AssetSearch.follow')}>
        <Button
          type="text"
          size="small"
          loading={submitting}
          icon={followed ? <StarFilled /> : <StarOutlined />}
          className={`shrink-0 ${followed ? 'text-[var(--color-warning)]' : 'text-[var(--color-text-3)]'}`}
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
    <div className={`flex flex-col h-full min-h-0 w-full min-w-0 ${attrLayoutStyle.attrLayout}`}>
      <SideMenuLayout {...layoutProps} />
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
