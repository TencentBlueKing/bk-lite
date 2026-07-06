import React from 'react';
import { Drawer, Tag } from 'antd';
import type { ColumnItem } from '@/types';

import CustomTable from '@/components/custom-table';
import type {
  IMNotificationChannel,
  IMNotificationSyncRun,
} from '@/app/system-manager/types/im-notification';
import {
  getSyncRunStatusColor,
  getSyncRunStatusText,
  getSyncTriggerModeText,
} from '@/app/system-manager/utils/imNotificationUtils';

interface PaginationState {
  current: number;
  total: number;
  pageSize: number;
}

interface IMNotificationRecordsDrawerProps {
  open: boolean;
  channel: IMNotificationChannel | null;
  records: IMNotificationSyncRun[];
  loading: boolean;
  pagination: PaginationState;
  t: (key: string, defaultMessage?: string, values?: Record<string, string | number>) => string;
  renderTime: (value: string | null | undefined) => string;
  onClose: () => void;
  onPageChange: (current: number, pageSize: number) => void;
}

const IMNotificationRecordsDrawer: React.FC<IMNotificationRecordsDrawerProps> = ({
  open,
  channel,
  records,
  loading,
  pagination,
  t,
  renderTime,
  onClose,
  onPageChange,
}) => {
  const columns: ColumnItem[] = [
    {
      key: 'started_at',
      title: t('system.channel.imNotificationPage.recordColumns.startedAt'),
      dataIndex: 'started_at',
      render: (_, record: IMNotificationSyncRun) => <p>{renderTime(record.started_at)}</p>,
    },
    {
      key: 'finished_at',
      title: t('system.channel.imNotificationPage.recordColumns.finishedAt'),
      dataIndex: 'finished_at',
      render: (_, record: IMNotificationSyncRun) => <p>{renderTime(record.finished_at)}</p>,
    },
    {
      key: 'trigger_mode',
      title: t('system.channel.imNotificationPage.recordColumns.triggerMode'),
      dataIndex: 'trigger_mode',
      render: (triggerMode: string) => <span>{getSyncTriggerModeText(triggerMode, t)}</span>,
      width: 100,
    },
    {
      key: 'status',
      title: t('system.channel.imNotificationPage.recordColumns.status'),
      dataIndex: 'status',
      render: (status: string) => (
        <Tag color={getSyncRunStatusColor(status)}>
          {getSyncRunStatusText(status, t)}
        </Tag>
      ),
      width: 100,
    },
    {
      key: 'total_external_user_count',
      title: t('system.channel.imNotificationPage.recordColumns.totalExternalUsers'),
      dataIndex: 'total_external_user_count',
      width: 90,
    },
    {
      key: 'matched_count',
      title: t('system.channel.imNotificationPage.recordColumns.matchedCount'),
      dataIndex: 'matched_count',
      width: 90,
    },
    {
      key: 'unmatched_count',
      title: t('system.channel.imNotificationPage.recordColumns.unmatchedCount'),
      dataIndex: 'unmatched_count',
      width: 100,
    },
    {
      key: 'conflict_count',
      title: t('system.channel.imNotificationPage.recordColumns.conflictCount'),
      dataIndex: 'conflict_count',
      width: 90,
    },
    {
      key: 'summary',
      title: t('system.channel.imNotificationPage.recordColumns.summary'),
      dataIndex: 'summary',
      ellipsis: true,
    },
  ];

  return (
    <Drawer
      title={`${channel?.name ?? ''} — ${t('system.channel.imNotificationPage.recordsTitle')}`}
      open={open}
      onClose={onClose}
      width={980}
    >
      {!loading && records.length === 0 ? (
        <div className="mb-4 text-[13px] text-[var(--color-text-3)]">
          {t('system.channel.imNotificationPage.noSyncRecords')}
        </div>
      ) : null}
      <CustomTable
        rowKey="id"
        scroll={{ x: '100%', y: 'calc(100vh - 205px)' }}
        loading={loading}
        dataSource={records}
        columns={columns}
        pagination={{
          ...pagination,
          onChange: onPageChange,
        }}
      />
    </Drawer>
  );
};

export default IMNotificationRecordsDrawer;
