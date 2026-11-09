'use client';

import React, { useMemo } from 'react';
import OperateModal from './components/operateModal';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import TopSection from '@/components/top-section';
import SearchActionBar from '@/components/search-action-bar';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { AlertShieldListItem } from '@/app/alarm/types/settings';
import { useSettingApi } from '@/app/alarm/api/settings';
import { STATUS_TEXT } from '@/app/alarm/constants/colors';
import { Button, Switch } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { useSettingsTable } from '@/app/alarm/hooks/useSettingsTable';
import { useCommon } from '@/app/alarm/context/common';
import { formatUserDisplayName, UserDisplayItem } from '@/utils/userDisplay';
import { formatSuppressionTime, shieldRuntimeColor, shieldRuntimeLabelKey } from '@/app/alarm/utils/shieldDisplay';

const ShieldStrategy: React.FC = () => {
  const { t } = useTranslation();
  const { userList } = useCommon();
  const { getShieldList, deleteShield, patchShield } = useSettingApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const creators = userList as UserDisplayItem[];

  const {
    tableLoading,
    loadingIds,
    operateVisible,
    setOperateVisible,
    searchKey,
    setSearchKey,
    dataList,
    currentRow,
    pagination,
    handleEdit,
    handleDelete,
    handleFilterChange,
    handleFilterClear,
    handleTableChange,
    handleStatusToggle,
    refreshList,
  } = useSettingsTable<AlertShieldListItem>({
    fetchList: getShieldList,
    deleteItem: deleteShield,
    patchItem: patchShield,
  });

  const columns = useMemo(() => [
    {
      title: t('settings.assignName'),
      dataIndex: 'name',
      key: 'name',
      width: 150,
    },
    {
      title: t('settings.assignTime'),
      key: 'suppression_time',
      width: 280,
      render: (_: unknown, row: AlertShieldListItem) => formatSuppressionTime(row.suppression_time),
    },
    {
      title: t('settings.shieldDisplay.runtimeStatus'),
      dataIndex: 'runtime_status',
      key: 'runtime_status',
      width: 110,
      render: (val: string) => {
        const labelKey = shieldRuntimeLabelKey(val);
        return (
          <span style={{ color: shieldRuntimeColor(val) }}>
            {labelKey ? t(labelKey) : '--'}
          </span>
        );
      },
    },
    {
      title: t('settings.shieldDisplay.enableStatus'),
      dataIndex: 'enableStatus',
      key: 'enableStatus',
      width: 100,
      render: (_: unknown, row: AlertShieldListItem) => (
        row.is_active ? (
          <span style={{ color: STATUS_TEXT.ACTIVE_GREEN }}>{t('settings.shieldDisplay.enabled')}</span>
        ) : (
          <span style={{ color: STATUS_TEXT.INACTIVE_RED }}>{t('settings.shieldDisplay.disabled')}</span>
        )
      ),
    },
    {
      title: t('settings.shieldDisplay.creator'),
      dataIndex: 'created_by',
      key: 'created_by',
      width: 160,
      render: (val: string) => formatUserDisplayName(val, creators),
    },
    {
      title: t('settings.assignCreateTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (val: string) => {
        return convertToLocalizedTime(val, 'YYYY-MM-DD HH:mm:ss');
      },
    },
    {
      title: t('settings.assignStartStop'),
      dataIndex: 'is_active',
      key: 'is_active',
      width: 110,
      render: (val: boolean, row: AlertShieldListItem) => (
        <Switch
          loading={!!loadingIds[row.id]}
          checked={val}
          onChange={(checked) => handleStatusToggle(row, checked)}
        />
      ),
    },
    {
      title: t('settings.assignActions'),
      key: 'operation',
      width: 130,
      render: (_: unknown, row: AlertShieldListItem) => (
        <div className="flex gap-4">
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              size="small"
              onClick={() => handleEdit('edit', row)}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Button
              type="link"
              size="small"
              danger
              onClick={() => handleDelete(row)}
            >
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        </div>
      ),
    },
  ], [t, creators, loadingIds, handleStatusToggle, handleEdit, handleDelete, convertToLocalizedTime]);

  return (
    <div className="flex h-full min-h-0 w-full flex-1 flex-col">
      <TopSection
        className="mb-4"
        title={t('settings.shieldStrategy')}
        content={t('settings.shieldStrategyMessage')}
      />
      <div className="flex min-h-0 flex-1 flex-col rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)] p-4">
        <SearchActionBar
          searchProps={{
            placeholder: t('common.search'),
            allowClear: true,
            value: searchKey,
            onChange: (e) => setSearchKey(e.target.value),
            onPressEnter: handleFilterChange,
            onSearch: handleFilterChange,
            onClear: handleFilterClear,
          }}
          actions={(
            <PermissionWrapper requiredPermissions={['Add']}>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => handleEdit('add')}>
                {t('common.new')}
              </Button>
            </PermissionWrapper>
          )}
        />
        <div className="min-h-0 flex-1 overflow-hidden">
          <CustomTable
            size="middle"
            rowKey="id"
            loading={tableLoading}
            columns={columns}
            dataSource={dataList}
            pagination={pagination}
            onChange={handleTableChange}
          />
        </div>
        <OperateModal
          open={operateVisible}
          onClose={() => setOperateVisible(false)}
          currentRow={currentRow}
          onSuccess={() => refreshList({ current: 1 })}
        />
      </div>
    </div>
  );
};

export default ShieldStrategy;
