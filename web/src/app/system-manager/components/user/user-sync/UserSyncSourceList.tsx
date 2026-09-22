'use client';

import React from 'react';
import { Button, Tooltip } from 'antd';
import type { MoreActionsDropdownItem } from '@/components/more-actions-dropdown';
import { useTranslation } from '@/utils/i18n';
import SystemManagerEntityGrid from '@/app/system-manager/components/system-manager-entity-grid';
import SystemManagerUnifiedCard from '@/app/system-manager/components/system-manager-unified-card';

export type UserSyncStatusTone = 'success' | 'error' | 'processing' | 'waiting' | 'default';

export interface UserSyncSourceCardItem {
  id: number;
  name: string;
  description: string;
  providerIcon: string;
  integrationSystemName: string;
  rootGroupName: string;
  syncedUsersText: string;
  syncCycleText: string;
  latestSyncTimeText: string;
  latestStatusText: string;
  latestStatusTone: UserSyncStatusTone;
  syncDisabled: boolean;
  deleteDisabled?: boolean;
  deleteDisabledReason?: string;
  dependencyStatusText?: string;
}

interface UserSyncSourceListProps<T extends UserSyncSourceCardItem> {
  data: T[];
  loading: boolean;
  operateSection?: React.ReactNode;
  onSearch?: (value: string) => void;
  onEdit: (item: T) => void;
  onConfig: (item: T) => void;
  onStrategy: (item: T) => void;
  onDelete: (item: T) => void;
  onSyncNow: (item: T) => void;
}

const STATUS_TEXT: Record<UserSyncStatusTone, string> = {
  success: 'text-[var(--color-success)]',
  error: 'text-[var(--color-fail)]',
  processing: 'text-[var(--color-primary)]',
  waiting: 'text-[var(--color-warning)]',
  default: 'text-[var(--color-text-3)]',
};

const UserSyncSourceList = <T extends UserSyncSourceCardItem>({
  data,
  loading,
  operateSection,
  onSearch,
  onEdit,
  onConfig,
  onStrategy,
  onDelete,
  onSyncNow,
}: UserSyncSourceListProps<T>) => {
  const { t } = useTranslation();

  const actionItemsFor = (item: T): MoreActionsDropdownItem[] => [
    {
      key: 'edit',
      label: t('system.user.userSyncPage.basicConfig'),
      onClick: () => onEdit(item),
    },
    {
      key: 'config',
      label: t('system.user.userSyncPage.accessConfig'),
      onClick: () => onConfig(item),
    },
    {
      key: 'strategy',
      label: t('system.user.userSyncPage.syncStrategy'),
      onClick: () => onStrategy(item),
    },
    {
      key: 'delete',
      label: item.deleteDisabled && item.deleteDisabledReason ? (
        <Tooltip title={item.deleteDisabledReason}>
          <span>{t('common.delete')}</span>
        </Tooltip>
      ) : (
        t('common.delete')
      ),
      danger: true,
      disabled: Boolean(item.deleteDisabled),
      onClick: () => onDelete(item),
    },
  ];

  return (
    <SystemManagerEntityGrid
      items={data}
      loading={loading}
      onSearch={onSearch}
      actions={operateSection}
      getItemKey={(item) => item.id}
      renderCard={(item) => {
        return (
          <SystemManagerUnifiedCard
            name={item.name}
            description={item.description}
            icon={item.providerIcon}
            warningLabel={item.dependencyStatusText ? t('system.user.userSyncPage.dependencyPaused') : undefined}
            warningTooltip={item.dependencyStatusText}
            caption={(
              <>
                <span>{item.integrationSystemName}</span>
                <span className="mx-1">·</span>
                <span>
                  {t('system.user.userSyncPage.rootGroupPrefix')}
                  {item.rootGroupName}
                </span>
              </>
            )}
            menuItems={actionItemsFor(item)}
            body={(
              <div className="flex flex-col gap-2">
                <div className="grid grid-cols-2 gap-1">
                  <div className="rounded-md bg-[var(--color-fill-1)] px-3 py-2.5">
                    <div className="text-sm font-medium leading-none tabular-nums text-[var(--color-text-1)]">
                      {item.syncedUsersText}
                    </div>
                    <div className="mt-1.5 text-xs text-[var(--color-text-3)]">
                      {t('system.user.userSyncPage.syncedUsers')}
                    </div>
                  </div>
                  <div className="rounded-md bg-[var(--color-fill-1)] px-3 py-2.5">
                    <div className="text-sm font-medium leading-none text-[var(--color-text-1)]">
                      {item.syncCycleText}
                    </div>
                    <div className="mt-1.5 text-xs text-[var(--color-text-3)]">
                      {t('system.user.userSyncPage.syncCycle')}
                    </div>
                  </div>
                </div>
                <div
                  className="flex min-w-0 items-center justify-between gap-2"
                  onClick={(event) => event.stopPropagation()}
                >
                  <div className="min-w-0 truncate text-xs leading-5 text-[var(--color-text-3)]">
                    <span>{t('system.user.userSyncPage.latestSyncLabel')}</span>
                    <span className="tabular-nums">{item.latestSyncTimeText}</span>
                    <span className="mx-1">·</span>
                    <span className={STATUS_TEXT[item.latestStatusTone]}>{item.latestStatusText}</span>
                  </div>
                  <Tooltip title={item.dependencyStatusText}>
                    <Button
                      type="primary"
                      size="small"
                      className="shrink-0 font-mini"
                      disabled={item.syncDisabled}
                      onClick={() => onSyncNow(item)}
                    >
                      {t('system.user.userSyncPage.syncNow')}
                    </Button>
                  </Tooltip>
                </div>
              </div>
            )}
          />
        );
      }}
    />
  );
};

export default UserSyncSourceList;
