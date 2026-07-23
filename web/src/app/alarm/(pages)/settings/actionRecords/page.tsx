'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import CustomTable from '@/components/custom-table';
import Introduction from '@/components/introduction';
import { ActionExecutionItem } from '@/app/alarm/types/settings';
import { useSettingApi } from '@/app/alarm/api/settings';
import { Select, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ACTION_EXEC_STATUS, ACTION_TRIGGER_EVENTS } from '@/app/alarm/constants/settings';

interface Pagination {
  current: number;
  total: number;
  pageSize: number;
}

const ActionRecords: React.FC = () => {
  const { t } = useTranslation();
  const { getActionExecutions } = useSettingApi();

  const [tableLoading, setTableLoading] = useState<boolean>(false);
  const [dataList, setDataList] = useState<ActionExecutionItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [pagination, setPagination] = useState<Pagination>({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  const triggerEventLabelMap = useMemo(
    () => Object.fromEntries(ACTION_TRIGGER_EVENTS.map(({ value, label }) => [value, label])),
    []
  );

  const statusOptions = useMemo(
    () => [
      { label: '全部', value: '' },
      ...Object.entries(ACTION_EXEC_STATUS).map(([key, { text }]) => ({
        label: text,
        value: key,
      })),
    ],
    []
  );

  const fetchList = useCallback(
    async (params: { current?: number; pageSize?: number; status?: string }) => {
      try {
        setTableLoading(true);
        const queryParams: Record<string, unknown> = {
          page: params.current ?? pagination.current,
          page_size: params.pageSize ?? pagination.pageSize,
        };
        const statusVal = params.status !== undefined ? params.status : statusFilter;
        if (statusVal) {
          queryParams.status = statusVal;
        }
        const data = await getActionExecutions(queryParams);
        setDataList(data?.items ?? []);
        setPagination((prev) => ({
          ...prev,
          current: params.current ?? prev.current,
          pageSize: params.pageSize ?? prev.pageSize,
          total: data?.count ?? 0,
        }));
      } catch {
        // error handled by request interceptor
      } finally {
        setTableLoading(false);
      }
    },
    [getActionExecutions, pagination.current, pagination.pageSize, statusFilter]
  );

  useEffect(() => {
    fetchList({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleStatusChange = useCallback(
    (value: string) => {
      const newStatus = value || undefined;
      setStatusFilter(newStatus);
      setPagination((prev) => ({ ...prev, current: 1 }));
      fetchList({ current: 1, status: value });
    },
    [fetchList]
  );

  const handleTableChange = useCallback(
    (newPagination: Pagination) => {
      setPagination(newPagination);
      fetchList({ current: newPagination.current, pageSize: newPagination.pageSize });
    },
    [fetchList]
  );

  const columns = useMemo(
    () => [
      {
        title: '规则名',
        dataIndex: 'rule_name',
        key: 'rule_name',
        width: 160,
        render: (val: string | null) => val || '-',
      },
      {
        title: '告警',
        dataIndex: 'alert_title',
        key: 'alert_title',
        width: 200,
        render: (val: string | null) => val || '-',
      },
      {
        title: '触发方式',
        dataIndex: 'trigger_type',
        key: 'trigger_type',
        width: 100,
        render: (val: ActionExecutionItem['trigger_type']) => (
          <Tag color={val === 'auto' ? 'blue' : 'default'}>
            {val === 'auto' ? '自动' : '手动'}
          </Tag>
        ),
      },
      {
        title: '触发事件',
        dataIndex: 'trigger_event',
        key: 'trigger_event',
        width: 120,
        render: (val: string) =>
          triggerEventLabelMap[val] ?? val ?? '-',
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 100,
        render: (val: ActionExecutionItem['status']) => {
          const statusConf = ACTION_EXEC_STATUS[val];
          if (statusConf) {
            return <Tag color={statusConf.color}>{statusConf.text}</Tag>;
          }
          return <Tag>{val}</Tag>;
        },
      },
      {
        title: '作业',
        dataIndex: 'job_detail_url',
        key: 'job_detail_url',
        width: 100,
        render: (url: string | null) =>
          url ? (
            <a href={url} target="_blank" rel="noopener noreferrer">
              查看作业
            </a>
          ) : (
            '-'
          ),
      },
      {
        title: '时间',
        dataIndex: 'created_at',
        key: 'created_at',
        width: 180,
      },
    ],
    [triggerEventLabelMap]
  );

  return (
    <>
      <Introduction
        title={t('settings.actionRecordsTitle')}
        message={t('settings.actionRecordsTitle')}
      />
      <div className="oid-library-container p-4 bg-[var(--color-bg-1)] rounded-lg shadow">
        <div className="nav-box flex justify-between mb-[20px]">
          <div className="flex items-center">
            <Select
              style={{ width: 160 }}
              value={statusFilter ?? ''}
              options={statusOptions}
              onChange={handleStatusChange}
            />
          </div>
        </div>
        <CustomTable
          size="middle"
          rowKey="id"
          loading={tableLoading}
          columns={columns}
          dataSource={dataList}
          pagination={pagination}
          onChange={handleTableChange}
          scroll={{ y: 'calc(100vh - 440px)' }}
        />
      </div>
    </>
  );
};

export default ActionRecords;
