'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Modal, Progress, Space, Tag, message } from 'antd';
import type { TablePaginationConfig } from 'antd';
import Introduction from '@/components/introduction';
import CustomTable from '@/components/custom-table';
import ExecutionStatusBadge from '@/components/execution-status-badge';
import PermissionWrapper from '@/components/permission';
import SearchActionBar from '@/components/search-action-bar';
import { useScanApi } from '@/app/cmdb/api';
import { useTranslation } from '@/utils/i18n';
import ScanTaskDrawer, { SCAN_FAMILIES } from './ScanTaskDrawer';
import ScanHitsDrawer, { type ScanExecutionSummary } from './ScanHitsDrawer';
import { isScanExecuteDisabled, isScanExecutionBusy } from './scanExecutionStatus';

interface ScanTaskItem {
  id: number;
  name: string;
  families: string[];
  updated_at: string;
  latest_execution?: ScanExecutionSummary | null;
}

const FAMILY_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  network: {
    bg: 'color-mix(in srgb, var(--color-primary) 10%, transparent)',
    text: 'var(--color-primary)',
    border: 'color-mix(in srgb, var(--color-primary) 24%, transparent)',
  },
  host: {
    bg: 'color-mix(in srgb, var(--color-success) 10%, transparent)',
    text: 'var(--color-success)',
    border: 'color-mix(in srgb, var(--color-success) 24%, transparent)',
  },
  physcial_server: {
    bg: 'color-mix(in srgb, var(--color-warning) 10%, transparent)',
    text: 'var(--color-warning)',
    border: 'color-mix(in srgb, var(--color-warning) 24%, transparent)',
  },
  database: {
    bg: 'color-mix(in srgb, var(--color-primary) 15%, transparent)',
    text: 'var(--color-primary)',
    border: 'color-mix(in srgb, var(--color-primary) 30%, transparent)',
  },
  influxdb: {
    bg: 'color-mix(in srgb, var(--color-text-2) 10%, transparent)',
    text: 'var(--color-text-1)',
    border: 'color-mix(in srgb, var(--color-border-2) 60%, transparent)',
  },
};

const ScanPage: React.FC = () => {
  const { t } = useTranslation();
  const { getScanList, executeScan, deleteScan } = useScanApi();
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [tasks, setTasks] = useState<ScanTaskItem[]>([]);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [hitsOpen, setHitsOpen] = useState(false);
  const [activeExecution, setActiveExecution] = useState<ScanExecutionSummary | null>(null);
  const [executingTaskId, setExecutingTaskId] = useState<number | null>(null);
  const executeLockRef = useRef(false);

  const statusLabel = useMemo(
    () => ({
      pending: t('Scan.statusPending'),
      running: t('Scan.statusRunning'),
      finalizing: t('Scan.statusFinalizing'),
      completed: t('Scan.statusCompleted'),
      failed: t('Scan.statusFailed'),
      timed_out: t('Scan.statusTimedOut'),
    }),
    [t]
  );

  const familyLabel = useCallback(
    (modelId: string) => {
      const family = SCAN_FAMILIES.find((item) => item.modelId === modelId);
      return family ? t(family.labelKey) : modelId;
    },
    [t]
  );

  const fetchTasks = useCallback(
    async (
      page = pagination.current,
      pageSize = pagination.pageSize,
      search = keyword,
      options?: { silent?: boolean }
    ) => {
      if (!options?.silent) {
        setLoading(true);
      }
      try {
        const data = await getScanList({
          page,
          page_size: pageSize,
          search,
        });
        setTasks(data.items || []);
        setPagination({
          current: page,
          pageSize,
          total: data.count || 0,
        });
      } finally {
        if (!options?.silent) {
          setLoading(false);
        }
      }
    },
    [getScanList, keyword, pagination.current, pagination.pageSize]
  );

  useEffect(() => {
    fetchTasks(1, pagination.pageSize, '');
  }, []);

  useEffect(() => {
    const hasBusyTask = tasks.some((task) => isScanExecutionBusy(task.latest_execution?.status));
    if (!hasBusyTask) {
      return;
    }
    const timer = window.setInterval(() => {
      fetchTasks(pagination.current, pagination.pageSize, keyword, { silent: true }).catch((error) => {
        console.error(error);
      });
    }, 5000);
    return () => window.clearInterval(timer);
  }, [fetchTasks, keyword, pagination.current, pagination.pageSize, tasks]);

  const openHits = (execution?: ScanExecutionSummary | null) => {
    if (!execution?.id) {
      return;
    }
    setActiveExecution(execution);
    setHitsOpen(true);
  };

  const handleExecute = async (task: ScanTaskItem) => {
    if (
      executeLockRef.current ||
      isScanExecuteDisabled({
        taskId: task.id,
        executingTaskId,
        executionStatus: task.latest_execution?.status,
      })
    ) {
      return;
    }
    executeLockRef.current = true;
    setExecutingTaskId(task.id);
    try {
      const execution = await executeScan(task.id);
      message.success(t('Scan.executeStarted'));
      await fetchTasks();
      openHits({
        id: execution.id,
        status: execution.status,
        target_count: execution.target_count,
        received_count: execution.received_count,
      });
    } catch (error) {
      console.error(error);
      message.error(t('Scan.statusFailed'));
    } finally {
      executeLockRef.current = false;
      setExecutingTaskId(null);
    }
  };

  const handleDelete = (task: ScanTaskItem) => {
    Modal.confirm({
      title: t('deleteTitle'),
      content: t('deleteContent'),
      okButtonProps: { danger: true },
      onOk: async () => {
        await deleteScan(task.id);
        message.success(t('successfullyDeleted'));
        fetchTasks();
      },
    });
  };

  const columns = [
    {
      title: t('Scan.taskName'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: ScanTaskItem) => (
        <span
          className="cursor-pointer font-medium text-[var(--color-text-1)] hover:text-[var(--color-primary)] transition-colors"
          onClick={() => {
            setEditId(record.id);
            setDrawerOpen(true);
          }}
        >
          {name || '--'}
        </span>
      ),
    },
    {
      title: t('Scan.families'),
      dataIndex: 'families',
      key: 'families',
      render: (families: string[] = []) => (
        <div className="flex flex-wrap gap-1.5">
          {families.map((item) => {
            const custom = FAMILY_COLORS[item];
            return (
              <Tag
                key={item}
                className="!m-0 !rounded !px-2 !py-0.5 !text-xs font-normal"
                style={
                  custom
                    ? {
                      backgroundColor: custom.bg,
                      color: custom.text,
                      borderColor: custom.border,
                    }
                    : {
                      backgroundColor: 'var(--color-fill-1)',
                      color: 'var(--color-text-2)',
                      borderColor: 'var(--color-border-2)',
                    }
                }
              >
                {familyLabel(item)}
              </Tag>
            );
          })}
        </div>
      ),
    },
    {
      title: t('Scan.progress'),
      key: 'progress',
      width: 180,
      render: (_: unknown, record: ScanTaskItem) => {
        const execution = record.latest_execution;
        if (!execution) {
          return <span className="text-[var(--color-text-4)]">--</span>;
        }
        const target = execution.target_count || 0;
        const received = execution.received_count || 0;
        const percent = target ? Math.min(100, Math.round((received / target) * 100)) : 0;
        const isRunning = execution.status === 'running' || execution.status === 'finalizing';
        return (
          <div className="flex min-w-[130px] flex-col gap-1">
            <div className="flex items-center justify-between text-xs text-[var(--color-text-3)] font-mono">
              <span>
                {received}/{target}
              </span>
              <span>{percent}%</span>
            </div>
            <Progress
              percent={percent}
              size="small"
              status={isRunning ? 'active' : undefined}
              strokeColor={execution.status === 'failed' ? 'var(--color-error)' : 'var(--color-primary)'}
              showInfo={false}
              className="!mb-0"
            />
          </div>
        );
      },
    },
    {
      title: t('Scan.status'),
      key: 'status',
      width: 130,
      render: (_: unknown, record: ScanTaskItem) => {
        const status = record.latest_execution?.status;
        if (!status) {
          return <span className="text-[var(--color-text-4)]">--</span>;
        }
        return (
          <ExecutionStatusBadge
            status={status}
            label={statusLabel[status as keyof typeof statusLabel] || status}
          />
        );
      },
    },
    {
      title: t('common.actions'),
      key: 'actions',
      width: 220,
      render: (_: unknown, record: ScanTaskItem) => (
        <Space size="middle">
          <PermissionWrapper requiredPermissions={['Execute']} permissionPath="/cmdb/assetManage/autoDiscovery/collection">
            <Button
              type="link"
              size="small"
              className="!px-0"
              loading={executingTaskId === record.id}
              disabled={isScanExecuteDisabled({
                taskId: record.id,
                executingTaskId,
                executionStatus: record.latest_execution?.status,
              })}
              onClick={() => handleExecute(record)}
            >
              {t('Scan.execute')}
            </Button>
          </PermissionWrapper>
          <Button
            type="link"
            size="small"
            className="!px-0"
            onClick={() => openHits(record.latest_execution)}
          >
            {t('Scan.hits')}
          </Button>
          <PermissionWrapper requiredPermissions={['Edit']} permissionPath="/cmdb/assetManage/autoDiscovery/collection">
            <Button
              type="link"
              size="small"
              className="!px-0"
              onClick={() => {
                setEditId(record.id);
                setDrawerOpen(true);
              }}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']} permissionPath="/cmdb/assetManage/autoDiscovery/collection">
            <Button
              type="link"
              size="small"
              danger
              className="!px-0"
              onClick={() => handleDelete(record)}
            >
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        </Space>
      ),
    },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="shrink-0">
        <Introduction title={t('Scan.title')} message={t('Scan.message')} />
      </div>
      <div className="min-h-0 flex-1 overflow-hidden px-4 pt-3 flex flex-col">
        <SearchActionBar
          searchProps={{
            placeholder: t('Collection.inputTaskPlaceholder'),
            allowClear: true,
            onSearch: (value) => {
              setKeyword(value);
              fetchTasks(1, pagination.pageSize, value);
            },
          }}
          actions={
            <PermissionWrapper requiredPermissions={['Add']} permissionPath="/cmdb/assetManage/autoDiscovery/collection">
              <Button
                type="primary"
                onClick={() => {
                  setEditId(null);
                  setDrawerOpen(true);
                }}
              >
                {t('Scan.addTask')}
              </Button>
            </PermissionWrapper>
          }
        />
        <div className="min-h-0 flex-1 overflow-hidden">
          <CustomTable
            loading={loading}
            rowKey="id"
            columns={columns}
            dataSource={tasks}
            pagination={{
              ...pagination,
              showSizeChanger: true,
              onChange: (page: number, pageSize: number) => fetchTasks(page, pageSize, keyword),
            } as TablePaginationConfig}
          />
        </div>
      </div>
      <ScanTaskDrawer
        open={drawerOpen}
        editId={editId}
        onClose={() => setDrawerOpen(false)}
        onSuccess={() => fetchTasks()}
      />
      <ScanHitsDrawer open={hitsOpen} execution={activeExecution} onClose={() => setHitsOpen(false)} />
    </div>
  );
};

export default ScanPage;
