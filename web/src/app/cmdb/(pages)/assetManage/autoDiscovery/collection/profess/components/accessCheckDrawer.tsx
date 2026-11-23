'use client';

import React, { useEffect, useState } from 'react';
import { Button, Drawer, Spin, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { useTranslation } from '@/utils/i18n';

export interface AccessCheckRow {
  target: string;
  credential_id: string;
  credential_name: string;
  conclusion: string;
  detail_code: string;
  attempted: boolean;
}

export interface AccessCheckPayload {
  id: number;
  task_id: number;
  status: string;
  total_count: number;
  finished_count: number;
  started_at: string;
  finished_at: string | null;
  error_code: string;
  rows: AccessCheckRow[];
}

const SUCCESS = new Set(['credential_ok']);
const DANGER = new Set(['network_unreachable', 'credential_rejected', 'permission_denied', 'system_error']);
const NEUTRAL = new Set(['pending', 'not_tested', 'no_credential']);
const UNCOUNTED = new Set(['pending', 'not_tested']);

const tagColor = (conclusion: string) => {
  if (SUCCESS.has(conclusion)) {
    return 'success';
  }
  if (DANGER.has(conclusion) || conclusion === 'failed') {
    return 'error';
  }
  if (NEUTRAL.has(conclusion)) {
    return 'default';
  }
  return 'warning';
};

interface AccessCheckDrawerProps {
  open: boolean;
  loading?: boolean;
  taskName: string;
  initial: AccessCheckPayload | null;
  onClose: () => void;
  reload: () => Promise<AccessCheckPayload | null>;
}

const AccessCheckDrawer: React.FC<AccessCheckDrawerProps> = ({
  open,
  loading = false,
  taskName,
  initial,
  onClose,
  reload,
}) => {
  const { t } = useTranslation();
  const [payload, setPayload] = useState<AccessCheckPayload | null>(initial);

  useEffect(() => {
    setPayload(initial);
  }, [initial]);

  useEffect(() => {
    if (!open || payload?.status !== 'running') {
      return undefined;
    }
    const timer = window.setInterval(() => {
      reload()
        .then((next) => {
          if (next) {
            setPayload(next);
          }
        })
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [open, payload?.status, reload]);

  const columns: ColumnsType<AccessCheckRow> = [
    { title: t('Collection.accessCheck.target'), dataIndex: 'target', key: 'target' },
    {
      title: t('Collection.accessCheck.credential'),
      dataIndex: 'credential_name',
      key: 'credential_name',
      render: (value: string) => value || '--',
    },
    {
      title: t('Collection.accessCheck.conclusion'),
      dataIndex: 'conclusion',
      key: 'conclusion',
      render: (value: string) => (
        <Tag color={tagColor(value)}>
          {t(`Collection.accessCheck.${value}`, value)}
        </Tag>
      ),
    },
    {
      title: t('Collection.accessCheck.detail'),
      dataIndex: 'detail_code',
      key: 'detail_code',
      render: (value: string) =>
        value ? t(`Collection.accessCheck.${value}`, '') : '',
    },
  ];

  const summary = () => {
    if (loading || !payload) {
      return null;
    }
    const rows = payload.rows || [];
    const successCount = rows.filter((row) => SUCCESS.has(row.conclusion)).length;
    const failureCount = rows.filter(
      (row) => !SUCCESS.has(row.conclusion) && !UNCOUNTED.has(row.conclusion),
    ).length;
    const testedAt = payload.finished_at || payload.started_at;
    const testedAtText = testedAt ? dayjs(testedAt).format('YYYY-MM-DD HH:mm:ss') : '';
    return { successCount, failureCount, testedAtText };
  };

  const counts = summary();

  return (
    <Drawer
      title={`${t('Collection.accessCheck.title')} ${taskName}`}
      placement="right"
      width={720}
      open={open}
      onClose={onClose}
      footer={
        <div className="flex justify-start">
          <Button onClick={onClose}>{t('Collection.accessCheck.close')}</Button>
        </div>
      }
    >
      {counts ? (
        <div className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-1 text-sm text-[var(--color-text-2)]">
          {payload?.status === 'running' ? (
            <span>
              {t('Collection.accessCheck.running')} {payload.finished_count}/{payload.total_count}
            </span>
          ) : null}
          <span>
            {t('Collection.accessCheck.testedAt')} {counts.testedAtText}
          </span>
          <span>
            {t('Collection.accessCheck.successCount')}{' '}
            <span className="text-[var(--color-success)]">{counts.successCount}</span>
          </span>
          <span>
            {t('Collection.accessCheck.failureCount')}{' '}
            <span className="text-[var(--color-error)]">{counts.failureCount}</span>
          </span>
        </div>
      ) : null}
      {loading ? (
        <div className="flex justify-center py-8">
          <Spin />
        </div>
      ) : payload ? (
        <Table
          rowKey={(row) => `${row.target}-${row.credential_id}`}
          columns={columns}
          dataSource={payload.rows}
          pagination={false}
          size="small"
          scroll={{ y: 'calc(100vh - 220px)' }}
        />
      ) : (
        <div>{t('Collection.accessCheck.empty')}</div>
      )}
    </Drawer>
  );
};

export default AccessCheckDrawer;
