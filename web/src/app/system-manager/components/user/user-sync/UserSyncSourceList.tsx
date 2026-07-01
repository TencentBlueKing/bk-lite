'use client';

import React, { useMemo, useState } from 'react';
import { Button, Dropdown, Empty, Input, Menu, Space, Spin } from 'antd';
import type { MenuProps } from 'antd';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import styles from './UserSyncSourceList.module.scss';

const { Search } = Input;

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

const statusToneClassName: Record<UserSyncStatusTone, string> = {
  success: styles.statusSuccess,
  error: styles.statusError,
  processing: styles.statusProcessing,
  waiting: styles.statusWaiting,
  default: styles.statusDefault,
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
  const [searchTerm, setSearchTerm] = useState('');

  const handleSearch = (value: string) => {
    setSearchTerm(value);
    onSearch?.(value);
  };

  const filteredItems = useMemo(() => {
    const keyword = searchTerm.trim().toLowerCase();
    if (!keyword) {
      return data;
    }
    return data.filter((item) => item.name.toLowerCase().includes(keyword));
  }, [data, searchTerm]);

  const renderMenu = (item: T) => {
    const menuItems: MenuProps['items'] = [
      {
        key: 'edit',
        label: t('common.edit'),
        onClick: () => onEdit(item),
      },
      {
        key: 'config',
        label: t('system.user.userSyncPage.accessConfig'),
        onClick: () => onConfig(item),
      },
      {
        key: 'delete',
        label: t('common.delete'),
        onClick: () => onDelete(item),
      },
    ];

    return <Menu items={menuItems} />;
  };

  return (
    <div className="h-full w-full">
      <div className="mb-4 flex justify-end">
        <Space.Compact>
          <Search
            size="middle"
            allowClear
            enterButton
            placeholder={`${t('common.search')}...`}
            className="w-60"
            onSearch={handleSearch}
          />
        </Space.Compact>
        {operateSection && <>{operateSection}</>}
      </div>

      {loading ? (
        <div className="flex min-h-[300px] items-center justify-center">
          <Spin spinning={loading} />
        </div>
      ) : filteredItems.length === 0 ? (
        <Empty description={t('common.noData')} />
      ) : (
        <div className="flex flex-wrap gap-5">
          {filteredItems.map((item) => (
            <div
              key={item.id}
              className={`${styles.card} flex min-h-[168px] w-full max-w-[400px] flex-col gap-1.5 rounded-xl p-3`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-start gap-2">
                  <div className={styles.providerIcon}>
                    <Icon type={item.providerIcon} className="text-[19px]" />
                  </div>
                  <div className="min-w-0">
                    <h3
                      className="truncate text-[12px] font-semibold text-[var(--color-text)]"
                      title={item.name}
                    >
                      {item.name}
                    </h3>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[10px] text-[var(--color-text-3)]">
                      <span className="truncate">{item.integrationSystemName}</span>
                      <span>&middot;</span>
                      <span className="truncate">
                        {t('system.user.userSyncPage.rootGroupPrefix')}
                        {item.rootGroupName}
                      </span>
                    </div>
                  </div>
                </div>

                <Dropdown overlay={renderMenu(item)} trigger={['click']} placement="bottomRight">
                  <button
                    type="button"
                    className="cursor-pointer border-none bg-transparent p-0.5 text-[var(--color-text-3)]"
                  >
                    <Icon type="sangedian-copy" className="text-sm" />
                  </button>
                </Dropdown>
              </div>

              <p className={`${styles.description} text-[11px]`}>{item.description || '--'}</p>

              <div className="flex flex-wrap gap-2 pt-0.5">
                <div className={`${styles.metricCard} w-[172px] rounded-lg px-3 py-2`}>
                  <div className="text-[19px] font-semibold leading-none text-[var(--color-text)]">
                    {item.syncedUsersText}
                  </div>
                  <div className="mt-2 text-[10px] text-[var(--color-text-3)]">
                    {t('system.user.userSyncPage.syncedUsers')}
                  </div>
                </div>
                <div className={`${styles.metricCard} w-[172px] rounded-lg px-3 py-2`}>
                  <div className="text-[19px] font-semibold leading-none text-[var(--color-text)]">
                    {item.syncCycleText}
                  </div>
                  <div className="mt-2 text-[10px] text-[var(--color-text-3)]">
                    {t('system.user.userSyncPage.syncCycle')}
                  </div>
                </div>
              </div>

              <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-0.5">
                <div className="min-w-0 text-[11px] text-[var(--color-text-3)]">
                  <span>{t('system.user.userSyncPage.latestSyncLabel')}</span>
                  <span>{item.latestSyncTimeText}</span>
                  <span className="mx-0.5">&middot;</span>
                  <span className={statusToneClassName[item.latestStatusTone]}>{item.latestStatusText}</span>
                </div>

                <Space size={4}>
                  <Button size="small" className='font-mini' onClick={() => onStrategy(item)}>
                    {t('system.user.userSyncPage.syncStrategy')}
                  </Button>
                  <Button type="primary" size="small" className='font-mini' disabled={item.syncDisabled} onClick={() => onSyncNow(item)}>
                    {t('system.user.userSyncPage.syncNow')}
                  </Button>
                </Space>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default UserSyncSourceList;
