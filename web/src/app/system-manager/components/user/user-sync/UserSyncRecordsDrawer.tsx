import React from 'react';
import { Drawer, Tag } from 'antd';
import CustomTable from '@/components/custom-table';
import { useLocalizedTime } from "@/hooks/useLocalizedTime";

import type { RunStatus } from '@/app/system-manager/types/user-sync';
import {
  type RecordRow,
  RUN_STATUS_TEXT_STYLE,
} from '@/app/system-manager/utils/userSyncPageUtils';

interface UserSyncRecordsDrawerProps {
  open: boolean;
  loading: boolean;
  records: RecordRow[];
  pagination: {
    current: number;
    total: number;
    pageSize: number;
  };
  t: (key: string, fallback?: string) => string;
  onPageChange: (current: number, pageSize: number) => void;
  onClose: () => void;
}

const UserSyncRecordsDrawer: React.FC<UserSyncRecordsDrawerProps> = ({
  open,
  loading,
  records,
  pagination,
  t,
  onPageChange,
  onClose,
}) => {
  const { convertToLocalizedTime } = useLocalizedTime();

  const columns = [
    {
      title: t('common.name'),
      dataIndex: 'source_name',
      key: 'source_name',
    },
    {
      title: t('system.user.userSyncPage.recordColumns.startedAt'),
      dataIndex: 'started_at',
      key: 'started_at',
      render: (_, record) => {
        return (<p>{convertToLocalizedTime(record.started_at, 'YYYY-MM-DD HH:mm:ss')}</p>)
      }
    },
    {
      title: t('system.user.userSyncPage.recordColumns.status'),
      dataIndex: 'status',
      key: 'status',
      render: (status: RunStatus) => (
        <Tag color={RUN_STATUS_TEXT_STYLE[status]}>{t(`system.user.userSyncPage.runStatus.${status}`)}</Tag>
      ),
      width: 80
    },
    {
      title: t('system.user.userSyncPage.recordColumns.syncedUsers'),
      dataIndex: 'synced_user_count',
      key: 'synced_user_count',
      width: 80
    },
    {
      title: t('system.user.userSyncPage.recordColumns.syncedGroups'),
      dataIndex: 'synced_group_count',
      key: 'synced_group_count',
      width: 80
    },
    {
      title: t('system.user.userSyncPage.recordColumns.summary'),
      dataIndex: 'summary',
      key: 'summary',
      ellipsis: true,
    },
  ];

  return (
    <Drawer
      title={t('system.user.userSyncPage.records')}
      open={open}
      onClose={onClose}
      width={980}
    >
      <CustomTable
        rowKey="id"
        scroll={{ x: '100%', y: 'calc(100vh - 220px)' }}
        dataSource={records}
        columns={columns}
        loading={loading}
        pagination={{
          ...pagination,
          onChange: onPageChange,
        }}
      />
    </Drawer>
  );
};

export default UserSyncRecordsDrawer;
