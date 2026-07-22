'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Input, Modal, Space, Switch, Tag, Tooltip, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import { useCustomReportingApi } from '@/app/cmdb/api/customReporting';
import { useUserInfoContext } from '@/context/userInfo';
import type { CustomReportingStats, CustomReportingTask } from '@/app/cmdb/types/customReporting';

interface TaskTableProps {
  refreshToken: number;
  onCreate: () => void;
  onEdit: (task: CustomReportingTask) => void;
  onView: (task: CustomReportingTask) => void;
  onOpenBatchReview: (task: CustomReportingTask) => void;
}

const flattenGroupNames = (
  nodes: Array<Record<string, any>> = [],
  nameMap: Record<number, string> = {},
) => {
  nodes.forEach((item) => {
    if (item?.id !== undefined) {
      nameMap[Number(item.id)] = item.name;
    }
    flattenGroupNames(item.subGroups || [], nameMap);
  });
  return nameMap;
};

const renderSparkline = (data: number[] = []) => {
  if (!data.length || data.every((n) => n === 0)) {
    return <span className="text-[var(--color-text-3)]">--</span>;
  }
  const width = 88;
  const height = 24;
  const max = Math.max(...data, 1);
  const step = data.length > 1 ? width / (data.length - 1) : width;
  const points = data
    .map(
      (v, i) =>
        `${(i * step).toFixed(1)},${(height - (v / max) * (height - 2) - 1).toFixed(1)}`,
    )
    .join(' ');
  return (
    <svg width={width} height={height} className="block">
      <polyline
        points={points}
        fill="none"
        stroke="var(--color-primary)"
        strokeWidth="1.5"
      />
    </svg>
  );
};

export default function TaskTable({
  refreshToken,
  onCreate,
  onEdit,
  onView,
  onOpenBatchReview,
}: TaskTableProps) {
  const { t } = useTranslation();
  const { groupTree } = useUserInfoContext();
  const { getTaskList, getStats, deleteTask, updateTask, rotateCredential } =
    useCustomReportingApi();
  const [loading, setLoading] = useState(false);
  const [searchName, setSearchName] = useState('');
  const [dataSource, setDataSource] = useState<CustomReportingTask[]>([]);
  const [stats, setStats] = useState<CustomReportingStats>({
    total: 0,
    receiving: 0,
    pending_review: 0,
  });
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });

  const groupNameMap = useMemo(
    () => flattenGroupNames(groupTree as Array<Record<string, any>>),
    [groupTree],
  );

  const getGroupLabels = useCallback(
    (groupIds: number[] = []) =>
      groupIds.map((item) => groupNameMap[item] || `${item}`),
    [groupNameMap],
  );

  const loadStats = useCallback(async () => {
    try {
      const data = await getStats();
      setStats(
        data || { total: 0, receiving: 0, pending_review: 0 },
      );
    } catch {
      // 统计失败不阻塞列表
    }
  }, [getStats]);

  const loadTasks = useCallback(
    async (nextPagination = pagination, name = searchName) => {
      try {
        setLoading(true);
        void loadStats();
        const data = await getTaskList({
          page: nextPagination.current,
          page_size: nextPagination.pageSize,
          ...(name ? { name } : {}),
        });
        setDataSource(data?.results || []);
        setPagination((prev) => ({
          ...prev,
          current: nextPagination.current,
          pageSize: nextPagination.pageSize,
          total: data?.count || 0,
        }));
      } finally {
        setLoading(false);
      }
    },
    [getTaskList, loadStats, pagination, searchName],
  );

  useEffect(() => {
    loadTasks({ ...pagination, current: 1 });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshToken]);

  const handleDelete = (task: CustomReportingTask) => {
    Modal.confirm({
      title: t('deleteTitle'),
      content: t('deleteContent'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      centered: true,
      onOk: async () => {
        await deleteTask(task.id);
        message.success(t('successfullyDeleted'));
        await loadTasks({
          ...pagination,
          current: dataSource.length === 1 && pagination.current > 1
            ? pagination.current - 1
            : pagination.current,
        });
      },
    });
  };

  const handleEnabledChange = async (
    checked: boolean,
    task: CustomReportingTask,
  ) => {
    await updateTask(task.id, {
      is_enabled: checked,
      name: task.name,
      team: task.team,
      config: task.config,
    });
    message.success(t('successfulSetted'));
    await loadTasks();
  };

  const handleRotateCredential = (task: CustomReportingTask) => {
    const credentialId = task.credential?.id;
    if (!credentialId) {
      message.warning(t('CustomReporting.noCredential'));
      return;
    }
    Modal.confirm({
      title: t('CustomReporting.rotateCredential'),
      content: t('CustomReporting.rotateConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: async () => {
        const data = await rotateCredential(task.id, credentialId);
        if (data?.token) {
          Modal.success({
            title: t('CustomReporting.rotateCredential'),
            content: (
              <Typography.Text copyable={{ text: data.token }}>
                {data.token}
              </Typography.Text>
            ),
          });
        }
        await loadTasks();
      },
    });
  };

  const columns: ColumnsType<CustomReportingTask> = [
    {
      title: t('id'),
      dataIndex: 'id',
      key: 'id',
      width: 80,
    },
    {
      title: t('name'),
      dataIndex: 'name',
      key: 'name',
      width: 220,
    },
    {
      title: t('CustomReporting.teamScope'),
      dataIndex: 'team',
      key: 'team',
      width: 240,
      render: (team: number[]) => {
        const labels = getGroupLabels(team);
        return (
          <Space size={[4, 4]} wrap>
            {labels.length ? labels.map((item) => <Tag key={item}>{item}</Tag>) : '--'}
          </Space>
        );
      },
    },
    {
      title: t('CustomReporting.mode'),
      key: 'mode',
      width: 120,
      render: (_, task) =>
        task.config?.mode === 'quick'
          ? t('CustomReporting.modeQuick')
          : t('CustomReporting.modeStandard'),
    },
    {
      title: t('CustomReporting.targetModel'),
      key: 'model',
      width: 220,
      render: (_, task) =>
        task.config?.mode === 'quick'
          ? task.config?.quick_model?.model_name || task.config?.quick_model?.model_id || '--'
          : task.config?.model_id || '--',
    },
    {
      title: t('CustomReporting.cleanupStrategy'),
      key: 'cleanup_strategy',
      width: 160,
      render: (_, task) => {
        const strategy = task.config?.cleanup_strategy || 'none';
        return t(`CustomReporting.cleanupLabel.${strategy}`);
      },
    },
    {
      title: t('CustomReporting.lastReportedAt'),
      dataIndex: 'last_reported_at',
      key: 'last_reported_at',
      width: 180,
      render: (value: string) =>
        value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '--',
    },
    {
      title: t('CustomReporting.recentBatches24h'),
      key: 'trend',
      width: 140,
      render: (_, task) => renderSparkline(task.recent_batch_trend),
    },
    {
      title: t('CustomReporting.status'),
      key: 'status',
      width: 120,
      render: (_, task) => {
        const status = task.status || 'no_report';
        const color =
          status === 'receiving'
            ? 'success'
            : status === 'pending_review'
              ? 'warning'
              : 'default';
        return (
          <Tag color={color}>{t(`CustomReporting.taskStatusLabel.${status}`)}</Tag>
        );
      },
    },
    {
      title: t('CustomReporting.enabled'),
      key: 'is_enabled',
      width: 120,
      render: (_, task) => (
        <Switch
          checked={task.is_enabled}
          onChange={(checked) => void handleEnabledChange(checked, task)}
        />
      ),
    },
    {
      title: t('updateTime'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (value: string) =>
        value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '--',
    },
    {
      title: t('common.actions'),
      key: 'action',
      width: 320,
      fixed: 'right',
      render: (_, task) => (
        <Space size={0} wrap>
          <Button type="link" onClick={() => onView(task)}>
            {t('common.detail')}
          </Button>
          <Button type="link" onClick={() => onEdit(task)}>
            {t('common.edit')}
          </Button>
          <Tooltip title={t('CustomReporting.batchReview')}>
            <Button type="link" onClick={() => onOpenBatchReview(task)}>
              {t('CustomReporting.batch')}
            </Button>
          </Tooltip>
          <Button type="link" onClick={() => handleRotateCredential(task)}>
            {t('CustomReporting.rotateCredential')}
          </Button>
          <Button danger type="link" onClick={() => handleDelete(task)}>
            {t('common.delete')}
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-[16px]">
      <div className="mb-[16px] grid shrink-0 grid-cols-3 gap-[12px]">
        <div className="rounded border border-[var(--color-border)] p-[16px]">
          <div className="text-[13px] text-[var(--color-text-3)]">
            {t('CustomReporting.statTotal')}
          </div>
          <div className="mt-[4px] text-[24px] font-[600]">
            {stats.total}
          </div>
        </div>
        <div className="rounded border border-[var(--color-border)] p-[16px]">
          <div className="text-[13px] text-[var(--color-text-3)]">
            {t('CustomReporting.statReceiving')}
          </div>
          <div className="mt-[4px] text-[24px] font-[600] text-[var(--color-success)]">
            {stats.receiving}
          </div>
        </div>
        <div className="rounded border border-[var(--color-border)] p-[16px]">
          <div className="text-[13px] text-[var(--color-text-3)]">
            {t('CustomReporting.statPendingReview')}
          </div>
          <div className="mt-[4px] text-[24px] font-[600] text-[var(--color-warning)]">
            {stats.pending_review}
          </div>
        </div>
      </div>
      <div className="mb-[12px] flex shrink-0 items-center justify-between gap-[12px]">
        <Space>
          <div className="text-[14px] font-[600]">
            {t('CustomReporting.taskList')}
          </div>
          <Input.Search
            allowClear
            className="w-[240px]"
            placeholder={t('CustomReporting.searchPlaceholder')}
            onSearch={(value) => {
              const next = value.trim();
              setSearchName(next);
              void loadTasks({ ...pagination, current: 1 }, next);
            }}
          />
        </Space>
        <Space>
          <Button onClick={() => void loadTasks()}>
            {t('common.refresh')}
          </Button>
          <Button type="primary" onClick={onCreate}>
            {t('CustomReporting.createTask')}
          </Button>
        </Space>
      </div>
      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
        <CustomTable<CustomReportingTask>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={dataSource}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            onChange: (current, pageSize) =>
              void loadTasks({
                ...pagination,
                current,
                pageSize,
              }),
          }}
          scroll={{ x: 1560 }}
        />
      </div>
    </div>
  );
}
