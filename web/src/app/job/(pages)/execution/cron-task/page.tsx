'use client';

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Button,
  Switch,
  message,
  Modal,
  Tag,
} from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useJobApi from '@/app/job/api';
import { ScheduledTask } from '@/app/job/types';
import { ColumnItem } from '@/types';
import SearchCombination from '@/components/search-combination';
import { SearchFilters, FieldConfig } from '@/components/search-combination/types';
import { useRouter } from 'next/navigation';
import dayjs from 'dayjs';

const CronTaskPage = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const { isLoading: isApiReady } = useApiClient();
  const {
    getScheduledTaskList,
    patchScheduledTask,
    deleteScheduledTask,
    runScheduledTaskNow,
  } = useJobApi();

  const [data, setData] = useState<ScheduledTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchFilters, setSearchFilters] = useState<SearchFilters>({});
  const [togglingIds, setTogglingIds] = useState<Set<number>>(new Set());
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const fetchData = useCallback(
    async (fetchParams: { filters?: SearchFilters; current?: number; pageSize?: number } = {}) => {
      setLoading(true);
      try {
        const filters = fetchParams.filters ?? searchFilters;
        const queryParams: Record<string, unknown> = {
          page: fetchParams.current ?? pagination.current,
          page_size: fetchParams.pageSize ?? pagination.pageSize,
        };
        if (filters && Object.keys(filters).length > 0) {
          Object.entries(filters).forEach(([field, conditions]) => {
            conditions.forEach((condition) => {
              if (condition.lookup_expr === 'in' && Array.isArray(condition.value)) {
                queryParams[field] = (condition.value as string[]).join(',');
              } else {
                queryParams[field] = condition.value;
              }
            });
          });
        }
        const res = await getScheduledTaskList(queryParams as any);
        setData(res.items || []);
        setPagination((prev) => ({
          ...prev,
          total: res.count || 0,
        }));
      } finally {
        setLoading(false);
      }
    },
    [searchFilters, pagination.current, pagination.pageSize]
  );

  useEffect(() => {
    if (!isApiReady) {
      fetchData();
    }
  }, [isApiReady]);

  useEffect(() => {
    if (!isApiReady) {
      fetchData();
    }
  }, [pagination.current, pagination.pageSize]);

  const handleSearchChange = useCallback((filters: SearchFilters) => {
    setSearchFilters(filters);
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchData({ filters, current: 1 });
  }, [fetchData]);

  const handleTableChange = (pag: any) => {
    setPagination(pag);
  };

  const fieldConfigs: FieldConfig[] = useMemo(() => [
    {
      name: 'name',
      label: t('job.taskName'),
      lookup_expr: 'icontains',
    },
    {
      name: 'job_type',
      label: t('job.jobType'),
      lookup_expr: 'in',
      options: [
        { id: 'script', name: t('job.scriptExecution') },
        { id: 'playbook', name: t('job.playbook') },
        { id: 'file', name: t('job.fileDistribution') },
      ],
    },
    {
      name: 'schedule_type',
      label: t('job.executionStrategy'),
      lookup_expr: 'in',
      options: [
        { id: 'once', name: t('job.executeOnce') },
        { id: 'cron', name: t('job.cronExpression') },
      ],
    },
    {
      name: 'is_enabled',
      label: t('job.enableStatus'),
      lookup_expr: 'bool',
      options: [
        { id: 'true', name: t('common.enabled') },
        { id: 'false', name: t('common.disabled') },
      ],
    },
  ], [t]);

  const handleToggleStatus = async (record: ScheduledTask) => {
    setTogglingIds((prev) => new Set(prev).add(record.id));
    try {
      await patchScheduledTask(record.id, { is_enabled: !record.is_enabled });
      message.success(t(record.is_enabled ? 'job.taskDisabled' : 'job.taskEnabled'));
      fetchData();
    } catch {
      // error handled by interceptor
    } finally {
      setTogglingIds((prev) => {
        const next = new Set(prev);
        next.delete(record.id);
        return next;
      });
    }
  };

  const handleDelete = (record: ScheduledTask) => {
    Modal.confirm({
      title: t('job.scheduledTask'),
      content: t('job.deleteTaskConfirm'),
      okText: t('job.confirm'),
      cancelText: t('job.cancel'),
      centered: true,
      onOk: async () => {
        await deleteScheduledTask(record.id);
        message.success(t('job.scheduledTask'));
        fetchData();
      },
    });
  };

  const handleRunNow = async (id: number) => {
    try {
      await runScheduledTaskNow(id);
      message.success(t('job.taskTriggered'));
      fetchData();
    } catch {
      // error handled by interceptor
    }
  };

  const handleEdit = (record: ScheduledTask) => {
    router.push(`/job/execution/cron-task/edit?id=${record.id}`);
  };

  const handleCreate = () => {
    router.push('/job/execution/cron-task/create');
  };

  const formatTime = (timeStr: string | null) => {
    if (!timeStr) return '-';
    return dayjs(timeStr).format('YYYY-MM-DD HH:mm:ss');
  };

  const columns: ColumnItem[] = [
    {
      title: t('job.taskName'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: t('job.jobType'),
      dataIndex: 'job_type_display',
      key: 'job_type',
      width: 120,
      render: (text: string, record: ScheduledTask) => {
        const colorMap: Record<string, string> = {
          script: 'blue',
          playbook: 'purple',
          file: 'green',
        };
        return <Tag color={colorMap[record.job_type] || 'default'}>{text}</Tag>;
      },
    },
    {
      title: t('job.executionStrategy'),
      dataIndex: 'cron_expression',
      key: 'schedule',
      width: 220,
      render: (text: string, record: ScheduledTask) => {
        if (record.schedule_type === 'once') {
          return <span>{record.scheduled_time ? dayjs(record.scheduled_time).format('YYYY-MM-DD HH:mm:ss') : '-'}</span>;
        }
        return <span>{text || '-'}</span>;
      },
    },
    {
      title: t('job.enableStatus'),
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      width: 80,
      render: (value: boolean, record: ScheduledTask) => (
        <Switch
          checked={value}
          onChange={() => handleToggleStatus(record)}
          size="small"
          loading={togglingIds.has(record.id)}
          disabled={togglingIds.has(record.id)}
        />
      ),
    },
    {
      title: t('job.nextRunTime'),
      dataIndex: 'next_run_at',
      key: 'next_run_at',
      width: 180,
      render: (text: string | null, record: ScheduledTask) => {
        if (!record.is_enabled) return <span>-</span>;
        return <span>{formatTime(text)}</span>;
      },
    },
    {
      title: t('job.operation'),
      dataIndex: 'action',
      key: 'action',
      width: 200,
      render: (_: unknown, record: ScheduledTask) => (
        <div className="flex items-center gap-3">
          <a
            className="text-[var(--color-primary)] cursor-pointer"
            onClick={() => handleEdit(record)}
          >
            {t('job.editRule')}
          </a>
          {record.is_enabled && (
            <a
              className="text-[var(--color-primary)] cursor-pointer"
              onClick={() => handleRunNow(record.id)}
            >
              {t('job.runNow')}
            </a>
          )}
          <a
            className="text-red-500 cursor-pointer"
            onClick={() => handleDelete(record)}
          >
            {t('job.deleteRule')}
          </a>
        </div>
      ),
    },
  ];

  return (
    <div className="w-full h-full flex flex-col">
      {/* Header */}
      <div
        className="rounded-lg px-6 py-4 mb-4 flex-shrink-0"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        <h2
          className="text-base font-medium m-0 mb-1"
          style={{ color: 'var(--color-text-1)' }}
        >
          {t('job.scheduledTask')}
        </h2>
        <p className="text-sm m-0" style={{ color: 'var(--color-text-3)' }}>
          {t('job.scheduledTaskDesc')}
        </p>
      </div>

      {/* Table Section */}
      <div
        className="rounded-lg px-6 py-6 flex-1 flex flex-col min-h-0"
        style={{
          background: 'var(--color-bg-1)',
          border: '1px solid var(--color-border-1)',
        }}
      >
        {/* Toolbar */}
        <div className="flex justify-between items-center mb-4 flex-shrink-0">
          <SearchCombination
            fieldConfigs={fieldConfigs}
            onChange={handleSearchChange}
            fieldWidth={120}
            selectWidth={300}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleCreate}
          >
            {t('job.createTask')}
          </Button>
        </div>

        {/* Table */}
        <div className="flex-1 min-h-0">
          <CustomTable
            columns={columns}
            dataSource={data}
            loading={loading}
            rowKey="id"
            pagination={{
              ...pagination,
              onChange: (current, pageSize) => handleTableChange({ current, pageSize, total: pagination.total }),
            }}
          />
        </div>
      </div>
    </div>
  );
};

export default CronTaskPage;
