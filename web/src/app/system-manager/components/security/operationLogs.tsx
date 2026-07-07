'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Input, Select, Button, message, Drawer, Descriptions } from 'antd';
import ReactDiffViewer from 'react-diff-viewer-continued';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useClientData } from '@/context/client';
import { useSecurityApi } from '@/app/system-manager/api/security';
import { buildOperationLogParams } from '@/app/system-manager/utils/operationLogParams';
import { hasOperationDetail } from '@/app/system-manager/utils/operationLogDetail';
import CustomTable from '@/components/custom-table';
import TimeSelector from '@/components/time-selector';

const { Search } = Input;

interface OperationLog {
  id: number;
  username: string;
  source_ip: string;
  app: string;
  action_type: string;
  action_type_display: string;
  summary: string;
  domain: string;
  operation_time: string;
  created_at: string;
  target_type?: string;
  target_id?: string;
  detail?: Record<string, any>;
}

const OperationLogs: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { clientData } = useClientData();
  const timeSelectorRef = useRef<any>(null);
  const [loading, setLoading] = useState(false);
  const [dataSource, setDataSource] = useState<OperationLog[]>([]);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });
  const [filters, setFilters] = useState({
    username: '',
    app: '',
    actionType: '',
  });
  const [timeRange, setTimeRange] = useState<number[]>([]);
  const [detailVisible, setDetailVisible] = useState(false);
  const [detailRecord, setDetailRecord] = useState<OperationLog | null>(null);

  const { getOperationLogs } = useSecurityApi();

  const fetchOperationLogs = async (page = 1, pageSize = pagination.pageSize) => {
    setLoading(true);
    try {
      const params = buildOperationLogParams(filters, timeRange, page, pageSize);

      const response = await getOperationLogs(params);
      setDataSource(response.items || []);
      setPagination(prev => ({
        ...prev,
        current: page,
        pageSize,
        total: response.count || 0,
      }));
    } catch (error) {
      message.error(t('common.fetchFailed'));
      console.error('Failed to fetch operation logs:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOperationLogs(1);
  }, []);

  const handleSearch = () => {
    fetchOperationLogs(1, pagination.pageSize);
  };

  const handleReset = () => {
    setFilters({
      username: '',
      app: '',
      actionType: '',
    });
    setTimeRange([]);
    if (timeSelectorRef.current?.reset) {
      timeSelectorRef.current.reset();
    }
    setTimeout(() => {
      fetchOperationLogs(1, pagination.pageSize);
    }, 0);
  };

  const handleTimeChange = (range: number[]) => {
    setTimeRange(range);
  };

  const handleOpenDetail = (record: OperationLog) => {
    setDetailRecord(record);
    setDetailVisible(true);
  };

  const handleCloseDetail = () => {
    setDetailVisible(false);
    setDetailRecord(null);
  };

  const detail = detailRecord?.detail || {};
  const hasDiff =
    detail.before_data !== undefined || detail.after_data !== undefined;

  const columns = [
    {
      title: t('system.security.operationTime'),
      dataIndex: 'operation_time',
      key: 'operation_time',
      render: (time: string) => convertToLocalizedTime(time),
    },
    {
      title: t('system.security.operator'),
      dataIndex: 'username',
      key: 'username',
    },
    {
      title: t('system.security.sourceIp'),
      dataIndex: 'source_ip',
      key: 'source_ip',
    },
    {
      title: t('system.security.operationModule'),
      dataIndex: 'app',
      key: 'app',
    },
    {
      title: t('system.security.operationType'),
      dataIndex: 'action_type_display',
      key: 'action_type_display',
    },
    {
      title: t('system.security.operationDetail'),
      dataIndex: 'summary',
      key: 'summary',
      ellipsis: true,
    },
    {
      title: t('common.actions'),
      key: 'detail',
      width: 100,
      fixed: 'right' as const,
      render: (_: unknown, record: OperationLog) =>
        hasOperationDetail(record) ? (
          <Button type="link" size="small" onClick={() => handleOpenDetail(record)}>
            {t('common.detail')}
          </Button>
        ) : (
          '--'
        ),
    },
  ];

  return (
    <div className="flex flex-col h-full w-full">
      {/* Filter Section */}
      <div className="flex-none mb-3">
        <div className="flex items-center justify-end gap-3">
          <Search
            placeholder={t('system.security.operatorPlaceholder')}
            value={filters.username}
            onChange={(e) => setFilters({ ...filters, username: e.target.value })}
            onSearch={handleSearch}
            allowClear
            className="w-48"
          />
          <Select
            placeholder={t('system.security.operationModulePlaceholder')}
            value={filters.app || undefined}
            onChange={(value) => setFilters({ ...filters, app: value })}
            allowClear
            className="w-48"
            options={clientData.map((item) => ({
              label: item.display_name,
              value: item.name,
            }))}
          />
          <Select
            placeholder={t('system.security.operationTypePlaceholder')}
            value={filters.actionType || undefined}
            onChange={(value) => setFilters({ ...filters, actionType: value })}
            allowClear
            className="w-48"
            options={[
              { label: t('common.create'), value: 'create' },
              { label: t('common.update'), value: 'update' },
              { label: t('common.delete'), value: 'delete' },
              { label: t('common.execute'), value: 'execute' },
            ]}
          />
          <TimeSelector
            ref={timeSelectorRef}
            showTime
            clearable
            onlyTimeSelect
            onChange={handleTimeChange}
            defaultValue={{
              selectValue: 7 * 24 * 60,
              rangePickerVaule: null
            }}
          />
          <Button type="primary" onClick={handleSearch}>
            {t('common.search')}
          </Button>
          <Button onClick={handleReset}>{t('common.reset')}</Button>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 min-h-0 relative">
        <CustomTable
          columns={columns}
          dataSource={dataSource}
          loading={loading}
          rowKey="id"
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `${t('common.total')} ${total} ${t('common.items')}`,
            onChange: (page: number, pageSize?: number) => {
              const nextPageSize = pageSize || pagination.pageSize;
              setPagination((prev) => ({ ...prev, current: page, pageSize: nextPageSize }));
              fetchOperationLogs(page, nextPageSize);
            },
          }}
          scroll={{ x: 1200 }}
        />
      </div>

      <Drawer
        title={t('common.detail')}
        width={720}
        open={detailVisible}
        onClose={handleCloseDetail}
        destroyOnHidden
      >
        {detailRecord && (
          <div className="flex flex-col gap-4">
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label={t('system.security.targetType') || '对象类型'}>
                {detailRecord.target_type || '--'}
              </Descriptions.Item>
              <Descriptions.Item label={t('system.security.targetId') || '对象ID'}>
                {detailRecord.target_id || '--'}
              </Descriptions.Item>
              {detail.scenario && (
                <Descriptions.Item label={t('system.security.scenario') || '场景'}>
                  {detail.scenario}
                </Descriptions.Item>
              )}
              {detail.model_object && (
                <Descriptions.Item label={t('system.security.modelObject') || '模型'}>
                  {detail.model_object}
                </Descriptions.Item>
              )}
              {detail.operator_object && (
                <Descriptions.Item label={t('system.security.operatorObject') || '操作对象'}>
                  {detail.operator_object}
                </Descriptions.Item>
              )}
            </Descriptions>

            {hasDiff && (
              <div>
                <div className="mb-2 font-medium">
                  {t('system.security.beforeAfter') || '变更前后对比'}
                </div>
                <ReactDiffViewer
                  oldValue={JSON.stringify(detail.before_data ?? {}, null, 2)}
                  newValue={JSON.stringify(detail.after_data ?? {}, null, 2)}
                  splitView
                />
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default OperationLogs;
