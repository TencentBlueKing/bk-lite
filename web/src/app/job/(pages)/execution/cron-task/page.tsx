'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  Button,
  Switch,
  message,
  Popconfirm,
  Tag,
} from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useJobApi from '@/app/job/api';
import { ScheduledTask } from '@/app/job/types';
import { ColumnItem } from '@/types';
import SearchActionBar from '@/components/search-action-bar';
import TopSection from '@/components/top-section';
import Permission from '@/components/permission';
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
  const [searchKey, setSearchKey] = useState('');
  const [togglingIds, setTogglingIds] = useState<Set<number>>(new Set());
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const fetchData = useCallback(
    async (fetchParams: { keyword?: string; current?: number; pageSize?: number } = {}) => {
      setLoading(true);
      try {
        const keyword = (fetchParams.keyword ?? searchKey).trim();
        const queryParams: Record<string, unknown> = {
          page: fetchParams.current ?? pagination.current,
          page_size: fetchParams.pageSize ?? pagination.pageSize,
        };
        if (keyword) {
          queryParams.name = keyword;
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
    [searchKey, pagination.current, pagination.pageSize]
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

  const handleSearch = useCallback((value: string) => {
    setSearchKey(value);
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchData({ keyword: value, current: 1 });
  }, [fetchData]);

  const handleTableChange = (pag: any) => {
    setPagination(pag);
  };

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

  const handleDelete = async (record: ScheduledTask) => {
    await deleteScheduledTask(record.id);
    message.success(t('job.scheduledTask'));
    fetchData();
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
        <Permission requiredPermissions={['Edit']}>
          <Switch
            checked={value}
            onChange={() => handleToggleStatus(record)}
            size="small"
            loading={togglingIds.has(record.id)}
            disabled={togglingIds.has(record.id)}
          />
        </Permission>
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
      fixed: 'right',
      render: (_: unknown, record: ScheduledTask) => (
        <div className="flex items-center gap-3">
          <Permission requiredPermissions={['Edit']}>
            <a
              className="text-[var(--color-primary)] cursor-pointer"
              onClick={() => handleEdit(record)}
            >
              {t('job.editRule')}
            </a>
          </Permission>
          {record.is_enabled && (
            <Permission requiredPermissions={['Edit']}>
              <a
                className="text-[var(--color-primary)] cursor-pointer"
                onClick={() => handleRunNow(record.id)}
              >
                {t('job.runNow')}
              </a>
            </Permission>
          )}
          <Permission requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('job.scheduledTask')}
              description={t('job.deleteTaskConfirm')}
              okText={t('job.confirm')}
              cancelText={t('job.cancel')}
              okButtonProps={{ danger: true }}
              onConfirm={() => handleDelete(record)}
            >
              <a className="text-red-500 cursor-pointer">
                {t('job.deleteRule')}
              </a>
            </Popconfirm>
          </Permission>
        </div>
      ),
    },
  ];

  return (
    <div className="w-full h-full flex flex-col">
      <TopSection
        title={t('job.scheduledTask')}
        content={t('job.scheduledTaskDesc')}
        className="mb-4 shrink-0"
      />

      {/* Table Section */}
      <div className="flex min-h-0 flex-1 flex-col rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] px-6 py-6">
        <SearchActionBar
          searchProps={{
            placeholder: t('common.search'),
            allowClear: true,
            value: searchKey,
            onChange: (event) => setSearchKey(event.target.value),
            onSearch: handleSearch,
          }}
          actions={(
            <Permission requiredPermissions={['Add']}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={handleCreate}
              >
                {t('common.new')}
              </Button>
            </Permission>
          )}
        />

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
