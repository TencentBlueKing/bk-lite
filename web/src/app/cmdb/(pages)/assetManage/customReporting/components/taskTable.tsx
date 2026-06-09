'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Modal, Space, Switch, Tag, Tooltip, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import CustomTable from '@/components/custom-table';
import { useTranslation } from '@/utils/i18n';
import { useCustomReportingApi } from '@/app/cmdb/api/customReporting';
import { useUserInfoContext } from '@/context/userInfo';
import type { CustomReportingTask } from '@/app/cmdb/types/customReporting';

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

export default function TaskTable({
  refreshToken,
  onCreate,
  onEdit,
  onView,
  onOpenBatchReview,
}: TaskTableProps) {
  const { t } = useTranslation();
  const { groupTree } = useUserInfoContext();
  const { getTaskList, deleteTask, updateTask } = useCustomReportingApi();
  const [loading, setLoading] = useState(false);
  const [dataSource, setDataSource] = useState<CustomReportingTask[]>([]);
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

  const loadTasks = useCallback(
    async (nextPagination = pagination) => {
      try {
        setLoading(true);
        const data = await getTaskList({
          page: nextPagination.current,
          page_size: nextPagination.pageSize,
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
    [getTaskList, pagination],
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
      title: t('action'),
      key: 'action',
      width: 240,
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
          <Button danger type="link" onClick={() => handleDelete(task)}>
            {t('common.delete')}
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div className="flex-1 min-h-0 rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-[16px]">
      <div className="mb-[12px] flex items-center justify-between gap-[12px]">
        <div className="text-[14px] font-[600]">{t('CustomReporting.taskList')}</div>
        <Space>
          <Button onClick={() => void loadTasks()}>{t('common.refresh')}</Button>
          <Button type="primary" onClick={onCreate}>
            {t('CustomReporting.createTask')}
          </Button>
        </Space>
      </div>
      <div className="h-[calc(100%-48px)]">
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
          scroll={{ x: 1560, y: 'calc(100vh - 330px)' }}
        />
      </div>
    </div>
  );
}
