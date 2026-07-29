'use client';

import React, { useMemo } from 'react';
import OperateModal from './components/operateModal';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import Introduction from '@/components/introduction';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { EnrichmentRuleListItem } from '@/app/alarm/types/settings';
import { useSettingApi } from '@/app/alarm/api/settings';
import { STATUS_TEXT } from '@/app/alarm/constants/colors';
import { Button, Input, Switch } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useSettingsTable } from '@/app/alarm/hooks/useSettingsTable';

const AlertEnrichment: React.FC = () => {
  const { t } = useTranslation();
  const { getEnrichmentList, deleteEnrichment, patchEnrichment } = useSettingApi();
  const { convertToLocalizedTime } = useLocalizedTime();

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
  } = useSettingsTable<EnrichmentRuleListItem>({
    fetchList: getEnrichmentList,
    deleteItem: deleteEnrichment,
    patchItem: patchEnrichment,
  });

  const columns = useMemo(
    () => [
      {
        title: t('settings.enrichmentName'),
        dataIndex: 'name',
        key: 'name',
        width: 200,
      },
      {
        title: t('settings.enrichmentProvider'),
        dataIndex: 'provider_type',
        key: 'provider_type',
        width: 120,
      },
      {
        title: t('settings.enrichmentNamespace'),
        dataIndex: 'namespace',
        key: 'namespace',
        width: 140,
        render: (val: string, row: EnrichmentRuleListItem) =>
          val || row.provider_type,
      },
      {
        title: t('settings.assignStatus'),
        key: 'assignStatus',
        width: 100,
        render: (_: unknown, row: EnrichmentRuleListItem) =>
          row.is_active ? (
            <span style={{ color: STATUS_TEXT.ACTIVE_GREEN }}>
              {t('settings.effective')}
            </span>
          ) : (
            <span style={{ color: STATUS_TEXT.INACTIVE_RED }}>
              {t('settings.ineffective')}
            </span>
          ),
      },
      {
        title: t('settings.assignCreateTime'),
        dataIndex: 'created_at',
        key: 'created_at',
        width: 180,
        render: (val: string) =>
          convertToLocalizedTime(val, 'YYYY-MM-DD HH:mm:ss'),
      },
      {
        title: t('settings.assignStartStop'),
        dataIndex: 'is_active',
        key: 'is_active',
        width: 110,
        render: (val: boolean, row: EnrichmentRuleListItem) => (
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
        render: (_: unknown, row: EnrichmentRuleListItem) => (
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
    ],
    [t, loadingIds, handleStatusToggle, handleEdit, handleDelete, convertToLocalizedTime]
  );

  return (
    <>
      <Introduction
        title={t('settings.enrichmentTitle')}
        message={t('settings.enrichmentMessage')}
      />
      <div className="p-4 bg-[var(--color-bg-1)] rounded-lg shadow">
        <div className="nav-box flex justify-between mb-[20px]">
          <div className="flex items-center">
            <Input
              allowClear
              value={searchKey}
              placeholder={t('common.search')}
              style={{ width: 250 }}
              onChange={(e) => setSearchKey(e.target.value)}
              onPressEnter={handleFilterChange}
              onClear={handleFilterClear}
            />
          </div>
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button type="primary" onClick={() => handleEdit('add')}>
              {t('common.addNew')}
            </Button>
          </PermissionWrapper>
        </div>
        <CustomTable
          size="middle"
          rowKey="id"
          loading={tableLoading}
          columns={columns}
          dataSource={dataList}
          pagination={pagination}
          onChange={handleTableChange}
          scroll={{ y: 'calc(100vh - 440px)' }}
        />
        <OperateModal
          open={operateVisible}
          onClose={() => setOperateVisible(false)}
          currentRow={currentRow}
          onSuccess={() => refreshList({ current: 1 })}
        />
      </div>
    </>
  );
};

export default AlertEnrichment;
