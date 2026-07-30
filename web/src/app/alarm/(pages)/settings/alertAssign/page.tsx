'use client';

import React, { useMemo } from 'react';
import dayjs from 'dayjs';
import OperateModal from './components/operateModal';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import UserAvatar from '@/components/user-avatar';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import Introduction from '@/components/introduction';
import { STATUS_TEXT } from '@/app/alarm/constants/colors';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { AlertAssignListItem } from '@/app/alarm/types/settings';
import { useSettingApi } from '@/app/alarm/api/settings';
import { Button, Input, Switch, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { typeLabel, weekMap } from '@/app/alarm/constants/settings';
import { useSettingsTable } from '@/app/alarm/hooks/useSettingsTable';
import { useUserInfoContext } from '@/context/userInfo';
import {
  getNotificationTargetFormValue,
  getOrganizationTargetLabels,
} from './components/notificationTarget';

const AlertAssign: React.FC = () => {
  const { t } = useTranslation();
  const { groupTree } = useUserInfoContext();
  const { getAssignmentList, deleteAssignment, patchAssignment } = useSettingApi();
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
  } = useSettingsTable<AlertAssignListItem>({
    fetchList: getAssignmentList,
    deleteItem: deleteAssignment,
    patchItem: patchAssignment,
  });

  const columns = useMemo(() => [
    {
      title: t('settings.assignName'),
      dataIndex: 'name',
      key: 'name',
      width: 150,
    },
    {
      title: t('settings.assignPersonnel'),
      dataIndex: 'personnel',
      key: 'personnel',
      width: 180,
      shouldCellUpdate: (
        prev: AlertAssignListItem,
        next: AlertAssignListItem
      ) =>
        prev?.personnel?.join(',') !== next?.personnel?.join(',') ||
        JSON.stringify(prev.config?.notification_target) !==
          JSON.stringify(next.config?.notification_target),
      render: (_: unknown, row: AlertAssignListItem) => {
        const target = getNotificationTargetFormValue(
          row.config?.notification_target,
          row.personnel,
        );
        if (target.target_type === 'user') {
          return target.personnel.length > 0 ? (
            <UserAvatar userName={target.personnel.join(',')} />
          ) : '--';
        }
        const labels = getOrganizationTargetLabels(
          groupTree,
          target.organization_ids,
          (id) =>
            t('settings.assignStrategy.invalidOrganization', undefined, {
              id: String(id),
            }),
        );
        return (
          <div className="flex flex-wrap gap-1">
            {labels.map((label) => (
              <Tag key={label}>
                <EllipsisWithTooltip
                  text={label}
                  className="max-w-[140px] overflow-hidden text-ellipsis whitespace-nowrap"
                />
              </Tag>
            ))}
            {target.include_children ? (
              <Tag>
                {t('settings.assignStrategy.includesChildren')}
              </Tag>
            ) : null}
          </div>
        );
      },
    },
    {
      title: t('settings.assignTime'),
      key: 'assignTime',
      width: 220,
      render: (_: unknown, row: AlertAssignListItem) => {
        const config = row.config as Record<string, unknown>;
        const type = config.type as string;
        const start_time = config.start_time as string;
        const end_time = config.end_time as string;
        const week_month = config.week_month as number[] | undefined;
        let label = typeLabel[type] || '';

        const fmt = (time: string, pattern = 'HH:mm:ss') =>
          dayjs(time, pattern).format(pattern);

        if (type === 'one') {
          return `${fmt(start_time, 'YYYY-MM-DD HH:mm:ss')}-${fmt(end_time, 'YYYY-MM-DD HH:mm:ss')}`;
        } else if (type === 'week') {
          label += ` ${(week_month || []).map((d: number) => weekMap[d]).join(',')}`;
        } else if (type === 'month') {
          label += ` ${(week_month || []).map((d: number) => `${d}日`).join(',')}`;
        }
        return `${label} ${fmt(start_time)} - ${fmt(end_time)}`;
      },
    },
    {
      title: t('settings.assignStatus'),
      dataIndex: 'assignStatus',
      key: 'assignStatus',
      width: 100,
      render: (_: unknown, row: AlertAssignListItem) => {
        const { is_active } = row;
        return is_active ? (
          <span style={{ color: STATUS_TEXT.ACTIVE_GREEN }}>{t('settings.effective')}</span>
        ) : (
          <span style={{ color: STATUS_TEXT.INACTIVE_RED }}>
            {t('settings.ineffective')}
          </span>
        );
      },
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
      render: (val: boolean, row: AlertAssignListItem) => (
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
      render: (_: unknown, row: AlertAssignListItem) => (
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
  ], [t, groupTree, loadingIds, handleStatusToggle, handleEdit, handleDelete, convertToLocalizedTime]);

  return (
    <>
      <Introduction
        title={t('settings.alertAssign')}
        message={t('settings.assignStrategyMessage')}
      />
      <div className="oid-library-container p-4 bg-[var(--color-bg-1)] rounded-lg shadow">
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
          scroll={{ y: 'calc(100vh - 460px)' }}
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

export default AlertAssign;
