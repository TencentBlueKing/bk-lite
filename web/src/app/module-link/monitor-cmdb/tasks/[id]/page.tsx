'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, Modal, Space, Table, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import {
  useModuleLinkApi,
  type MonitorCmdbTask,
  type MonitorCmdbTaskItem,
} from '@/app/module-link/api';
import CmdbBindModal from '@/app/module-link/monitor-cmdb/CmdbBindModal';

const STATUS_ORDER = [
  'not_found',
  'conflict',
  'ok',
  'already_linked',
  'failed',
  'skipped_model',
] as const;

const MonitorCmdbTaskPage = () => {
  const { t } = useTranslation();
  const params = useParams();
  const taskId = String(params?.id || '');
  const { getMonitorCmdbTask, cancelMonitorCmdbTask, createMissingCmdbItems } =
    useModuleLinkApi();
  const [task, setTask] = useState<MonitorCmdbTask | null>(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [selectedNotFound, setSelectedNotFound] = useState<string[]>([]);
  const [bindItem, setBindItem] = useState<MonitorCmdbTaskItem | null>(null);

  const loadTask = useCallback(async () => {
    if (!taskId) return;
    setLoading(true);
    try {
      const data = await getMonitorCmdbTask(taskId);
      setTask(data);
    } catch {
      setTask(null);
      message.error(t('ModuleLink.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [getMonitorCmdbTask, taskId, t]);

  useEffect(() => {
    void loadTask();
  }, [loadTask]);

  const items = task?.items || [];
  const summary = task?.summary || {};

  const columns: ColumnsType<MonitorCmdbTaskItem> = useMemo(
    () => [
      { title: t('ModuleLink.instName'), dataIndex: 'inst_name', ellipsis: true },
      { title: t('ModuleLink.model'), dataIndex: 'model_id', width: 140 },
      { title: t('ModuleLink.ip'), dataIndex: 'ip', width: 140 },
      { title: t('ModuleLink.monitorId'), dataIndex: 'monitor_id', ellipsis: true },
      { title: t('ModuleLink.cmdbId'), dataIndex: 'cmdb_id', ellipsis: true },
      { title: t('ModuleLink.rowMessage'), dataIndex: 'message', ellipsis: true },
    ],
    [t],
  );

  const handleCancel = () => {
    Modal.confirm({
      centered: true,
      title: t('ModuleLink.cancelConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        const data = await cancelMonitorCmdbTask(taskId);
        setTask(data);
        message.success(t('ModuleLink.cancelled'));
      },
    });
  };

  const handleCreateMissing = () => {
    if (!selectedNotFound.length) {
      message.warning(t('ModuleLink.selectNotFound'));
      return;
    }
    Modal.confirm({
      centered: true,
      title: t('ModuleLink.createMissingConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      onOk: async () => {
        setCreating(true);
        try {
          const data = await createMissingCmdbItems(taskId, selectedNotFound);
          setTask(data);
          setSelectedNotFound([]);
          message.success(t('ModuleLink.createMissingSuccess'));
        } catch {
          message.error(t('ModuleLink.loadFailed'));
        } finally {
          setCreating(false);
        }
      },
    });
  };

  const statusLabel = (status: string) => {
    const keys: Record<string, string> = {
      ok: 'ModuleLink.statusOk',
      already_linked: 'ModuleLink.statusAlreadyLinked',
      not_found: 'ModuleLink.reverseNotFound',
      conflict: 'ModuleLink.statusConflict',
      failed: 'ModuleLink.statusFailed',
      skipped_model: 'ModuleLink.statusSkipped',
    };
    return t(keys[status] || status);
  };

  const statusHint = (status: string) => {
    const keys: Record<string, string> = {
      ok: 'ModuleLink.reverseOkHint',
      already_linked: 'ModuleLink.reverseAlreadyLinkedHint',
      not_found: 'ModuleLink.reverseNotFoundHint',
    };
    return keys[status] ? t(keys[status]) : '';
  };

  const visibleStatuses = STATUS_ORDER.filter((status) => {
    if (items.some((item) => item.status === status)) return true;
    return Number(summary[status] || 0) > 0;
  });

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-auto bg-[var(--color-bg-1)] p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="m-0 text-lg font-semibold text-[var(--color-text-1)]">
            {t('ModuleLink.reverseTitle')}
          </h1>
          <p className="mt-1 mb-0 text-[var(--color-text-2)]">
            {t('ModuleLink.reverseSubtitle')}
          </p>
        </div>
        <Space>
          <Button onClick={() => void loadTask()} loading={loading}>
            {t('ModuleLink.refresh')}
          </Button>
          <Button danger disabled={!task || task.status === 'cancelled'} onClick={handleCancel}>
            {t('ModuleLink.cancel')}
          </Button>
        </Space>
      </div>
      {visibleStatuses.length > 0 ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {visibleStatuses.map((status) => (
            <Card key={status} size="small">
              <div className="text-[var(--color-text-3)]">{statusLabel(status)}</div>
              <div className="text-xl font-semibold text-[var(--color-text-1)]">
                {Number(summary[status] ?? items.filter((item) => item.status === status).length)}
              </div>
            </Card>
          ))}
        </div>
      ) : null}
      {visibleStatuses.map((status) => {
        const rows = items.filter((item) => item.status === status);
        const extra =
          status === 'not_found' ? (
            <Button
              type="link"
              disabled={!selectedNotFound.length || creating || task?.status === 'cancelled'}
              onClick={handleCreateMissing}
            >
              {t('ModuleLink.createMissing')}
            </Button>
          ) : null;
        return (
          <Card
            key={`table-${status}`}
            size="small"
            title={statusLabel(status)}
            extra={extra}
          >
            {statusHint(status) ? (
              <p className="mt-0 text-[var(--color-text-3)]">{statusHint(status)}</p>
            ) : null}
            <Table
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={rows}
              rowSelection={
                status === 'not_found'
                  ? {
                    selectedRowKeys: selectedNotFound,
                    onChange: (keys) => setSelectedNotFound(keys.map(String)),
                  }
                  : undefined
              }
              columns={
                status === 'conflict'
                  ? [
                    ...columns,
                    {
                      title: '',
                      key: 'bind',
                      width: 120,
                      render: (_: unknown, record: MonitorCmdbTaskItem) => (
                        <Button type="link" onClick={() => setBindItem(record)}>
                          {t('ModuleLink.bind')}
                        </Button>
                      ),
                    },
                  ]
                  : columns
              }
              locale={{ emptyText: t('ModuleLink.empty') }}
            />
          </Card>
        );
      })}
      <CmdbBindModal
        open={Boolean(bindItem)}
        modelId={bindItem?.model_id || ''}
        monitorId={bindItem?.monitor_id || ''}
        onCancel={() => setBindItem(null)}
        onSuccess={() => {
          setBindItem(null);
          void loadTask();
        }}
      />
    </div>
  );
};

export default MonitorCmdbTaskPage;
