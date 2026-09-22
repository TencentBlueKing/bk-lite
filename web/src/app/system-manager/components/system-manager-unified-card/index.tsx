'use client';

import React, { type ReactNode } from 'react';
import { Tooltip } from 'antd';
import Icon from '@/components/icon';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
import GridEntityCard, {
  type GridEntityCardStatusTone,
} from '@/components/grid-entity-card';
import { useTranslation } from '@/utils/i18n';

export type SystemManagerCardStatusTone = GridEntityCardStatusTone;

export interface SystemManagerUnifiedCardProps {
  name: string;
  description?: string;
  icon?: string;
  statusTone?: SystemManagerCardStatusTone;
  statusLabel?: string;
  updatedAt?: string;
  origin?: 'builtin' | 'external';
  warningLabel?: string;
  warningTooltip?: ReactNode;
  caption?: ReactNode;
  meta?: string[];
  body?: ReactNode;
  owner?: string;
  team?: string | string[];
  footer?: 'entity' | 'none' | 'custom';
  footerLeft?: ReactNode;
  footerActions?: ReactNode;
  menuItems?: MoreActionsDropdownItem[];
  onClick?: () => void;
  className?: string;
}

export default function SystemManagerUnifiedCard({
  name,
  description,
  icon,
  statusTone,
  statusLabel,
  updatedAt,
  origin,
  warningLabel,
  warningTooltip,
  caption,
  meta = [],
  body,
  owner = '--',
  team,
  footer = 'none',
  footerLeft,
  footerActions,
  menuItems,
  onClick,
  className = '',
}: SystemManagerUnifiedCardProps) {
  const { t } = useTranslation();
  const showCustomFooter = footer === 'custom' || Boolean(footerLeft || footerActions);
  const footerSlot = footer === 'entity'
    ? 'entity'
    : showCustomFooter
      ? (
        <>
          {footerLeft ? (
            <div className="w-full overflow-hidden text-ellipsis whitespace-nowrap">
              {footerLeft}
            </div>
          ) : null}
          {footerActions ? (
            <div
              className="flex items-center"
              onClick={(event) => event.stopPropagation()}
            >
              {footerActions}
            </div>
          ) : null}
        </>
      )
      : 'none';

  const sublineExtra = (caption || warningLabel) ? (
    <>
      {caption ? (
        <div className="min-w-0 truncate text-xs leading-5 text-[var(--color-text-3)]">
          {caption}
        </div>
      ) : null}
      {warningLabel ? (
        <Tooltip title={warningTooltip}>
          <span
            className="inline-flex h-5 shrink-0 items-center rounded-md bg-[color-mix(in_srgb,var(--color-warning)_12%,transparent)] px-1.5 text-[11px] font-medium text-[var(--color-warning)]"
            onClick={(event) => event.stopPropagation()}
          >
            {warningLabel}
          </span>
        </Tooltip>
      ) : null}
    </>
  ) : null;

  return (
    <GridEntityCard
      name={name}
      description={description}
      icon={icon ? <Icon type={icon} className="text-xl text-[var(--color-primary)]" /> : null}
      statusTone={statusTone}
      statusLabel={statusLabel}
      updatedAt={updatedAt}
      sublineExtra={sublineExtra}
      origin={origin}
      metaLabels={meta}
      body={body}
      menuItems={menuItems}
      footer={footerSlot}
      footerClassName={showCustomFooter
        ? (footerLeft ? 'flex-col items-start gap-2' : 'items-center justify-end gap-2')
        : undefined}
      owner={owner}
      team={team}
      ownerLabel={t('system.listCard.owner')}
      teamLabel={t('system.listCard.team')}
      onClick={onClick}
      className={className}
      wash
    />
  );
}
