'use client';

import React from 'react';
import { Typography } from 'antd';
import Icon from '@/components/icon';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';

export interface OpsPilotEntityDetailIntroProps {
  name?: string | null;
  description?: string | null;
  iconType: string;
  fallbackTitle?: string;
  emptyIntroText?: string;
  className?: string;
}

const OpsPilotEntityDetailIntro: React.FC<OpsPilotEntityDetailIntroProps> = ({
  name,
  description,
  iconType,
  fallbackTitle,
  emptyIntroText,
  className = '',
}) => {
  const { t } = useTranslation();
  const displayName = name || fallbackTitle || t('opspilotEntity.detailTitle', '详情');
  const emptyText = emptyIntroText || t('opspilotEntity.noIntro', '暂无简介');

  return (
    <div className={`flex w-full items-center gap-2 ${className}`.trim()}>
      <Icon type={iconType} className="shrink-0 text-base text-[var(--color-primary)]" />
      <div className="min-w-0 flex-1">
        <EllipsisWithTooltip
          text={displayName}
          className="mb-1 block truncate text-sm font-semibold leading-tight text-[var(--color-text-1)]"
        />
        {description ? (
          <Typography.Paragraph
            className="!mb-0 text-xs leading-[18px] text-[var(--color-text-3)]"
            ellipsis={{
              rows: 2,
              tooltip: true,
            }}
          >
            {description}
          </Typography.Paragraph>
        ) : (
          <p className="m-0 text-xs leading-[18px] text-[var(--color-text-4)]">
            {emptyText}
          </p>
        )}
      </div>
    </div>
  );
};

export default OpsPilotEntityDetailIntro;
