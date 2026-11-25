'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Input, Select, Button, message, Drawer, Descriptions, Tag } from 'antd';
import { DownloadOutlined, SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import ReactDiffViewer from 'react-diff-viewer-continued';
import dayjs from 'dayjs';
import type { TableRowSelection } from 'antd/es/table/interface';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useClientData } from '@/context/client';
import { useUserInfoContext } from '@/context/userInfo';
import { useSecurityApi } from '@/app/system-manager/api/security';
import { buildOperationLogParams } from '@/app/system-manager/utils/operationLogParams';
import {
  UNRECORDED,
  buildOperationLogDetailView,
  type OperationLogDetailView,
  type OperationOutcome,
} from '@/app/system-manager/utils/operationLogDetail';
import CustomTable from '@/components/custom-table';
import FilterToolbar from '@/components/filter-toolbar';
import SystemManagerFillTable from '@/app/system-manager/components/system-manager-fill-table';
import TimeSelector from '@/components/time-selector';
import { resolveAppDisplayName } from '@/utils/appDisplayName';

const EMPTY_FILTERS = {
  username: '',
  app: '',
  actionType: '',
  target: '',
  outcome: '',
};

interface OperationLog {
  id: number;
  username: string;
  source_ip: string;
  app: string;
  app_name?: string;
  action_type: string;
  action_type_display: string;
  summary: string;
  domain: string;
  operation_time: string;
  created_at: string;
  target_type?: string;
  target_name?: string;
  target_id?: string;
  outcome?: string;
  failure_reason?: string;
  detail?: Record<string, any>;
}

const OperationLogs: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { clientData } = useClientData();
  const { selectedGroup } = useUserInfoContext();
  const timeSelectorRef = useRef<any>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [dataSource, setDataSource] = useState<OperationLog[]>([]);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [timeRange, setTimeRange] = useState<number[]>([]);
  const [detailVisible, setDetailVisible] = useState(false);
  const [detailRecord, setDetailRecord] = useState<OperationLog | null>(null);

  const { getOperationLogs, exportOperationLogs } = useSecurityApi();

  const fetchOperationLogs = async (
    page = 1,
    pageSize = pagination.pageSize,
    nextFilters = filters,
    nextTimeRange = timeRange,
  ) => {
    setLoading(true);
    try {
      const params = buildOperationLogParams(nextFilters, nextTimeRange, page, pageSize);

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
    if (!selectedGroup?.id) {
      return;
    }
    fetchOperationLogs(1);
  }, [selectedGroup?.id]);

  const handleSearch = () => {
    fetchOperationLogs(1, pagination.pageSize);
  };

  const handleReset = () => {
    setFilters(EMPTY_FILTERS);
    setTimeRange([]);
    if (timeSelectorRef.current?.reset) {
      timeSelectorRef.current.reset();
    }
    fetchOperationLogs(1, pagination.pageSize, EMPTY_FILTERS, []);
  };

  const handleTimeChange = (range: number[]) => {
    setTimeRange(range);
  };

  const buildExportFilters = () => {
    const params = buildOperationLogParams(filters, timeRange, pagination.current, pagination.pageSize);
    delete params.page;
    delete params.page_size;
    return params;
  };

  const handleExport = async () => {
    try {
      setExporting(true);
      const payload =
        selectedRowKeys.length > 0
          ? { selected_ids: selectedRowKeys }
          : buildExportFilters();
      const blob = await exportOperationLogs(payload);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `operation_logs_${dayjs().format('YYYYMMDD_HHmmss')}.xlsx`;
      link.click();
      window.URL.revokeObjectURL(url);
      message.success(t('common.exportSuccess'));
    } catch (error) {
      console.error('Export failed:', error);
      message.error(t('system.security.exportFailed'));
    } finally {
      setExporting(false);
    }
  };

  const rowSelection: TableRowSelection<OperationLog> = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => setSelectedRowKeys(keys),
  };

  const handleOpenDetail = (record: OperationLog) => {
    setDetailRecord(record);
    setDetailVisible(true);
  };

  const handleCloseDetail = () => {
    setDetailVisible(false);
    setDetailRecord(null);
  };

  const formatRecorded = (value: string) =>
    value === UNRECORDED ? t('system.security.outcomeUnrecorded') : value;

  const formatAppName = (record: { app?: string; app_name?: string }) => {
    const label = resolveAppDisplayName(
      { name: record.app, display_name: record.app_name },
      t,
    ).trim();
    return label || UNRECORDED;
  };

  const formatOutcome = (outcome: OperationOutcome) => {
    if (outcome === 'success') return t('system.security.outcomeSuccess');
    if (outcome === 'failure') return t('system.security.outcomeFailure');
    if (outcome === 'accepted') return t('system.security.outcomeAccepted');
    return t('system.security.outcomeUnrecorded');
  };

  const renderChangeSection = (view: OperationLogDetailView) => {
    const { changes } = view;
    if (changes.kind === 'unrecorded') {
      return (
        <div className="rounded-md border border-dashed border-[var(--color-border-2)] p-4 text-center text-xs text-[var(--color-text-3)]">
          {t('system.security.noChangeRecorded')}
        </div>
      );
    }
    if (changes.kind === 'hidden' || changes.kind === 'none') {
      return (
        <div className="rounded-md border border-dashed border-[var(--color-border-2)] p-4 text-center text-xs text-[var(--color-text-3)]">
          {t('system.security.noChangeContent')}
        </div>
      );
    }
    let diffContent: React.ReactNode = null;
    if (changes.kind === 'create') {
      diffContent = (
        <ReactDiffViewer
          oldValue=""
          newValue={JSON.stringify(changes.after, null, 2)}
          splitView
        />
      );
    } else if (changes.kind === 'delete') {
      diffContent = (
        <ReactDiffViewer
          oldValue={JSON.stringify(changes.before, null, 2)}
          newValue=""
          splitView
        />
      );
    } else {
      const beforeObj: Record<string, unknown> = {};
      const afterObj: Record<string, unknown> = {};
      changes.fields.forEach((field) => {
        beforeObj[field.key] = field.before;
        afterObj[field.key] = field.after;
      });
      diffContent = (
        <ReactDiffViewer
          oldValue={JSON.stringify(beforeObj, null, 2)}
          newValue={JSON.stringify(afterObj, null, 2)}
          splitView
        />
      );
    }
    return (
      <div className="overflow-hidden rounded-md border border-[var(--color-border-2)] max-h-[460px] overflow-y-auto">
        {diffContent}
      </div>
    );
  };

  const columns = [
    {
      title: t('system.security.operationTime'),
      dataIndex: 'operation_time',
      key: 'operation_time',
      width: 170,
      render: (time: string) => convertToLocalizedTime(time),
    },
    {
      title: t('system.security.operator'),
      dataIndex: 'username',
      key: 'username',
      width: 130,
    },
    {
      title: t('system.security.sourceIp'),
      dataIndex: 'source_ip',
      key: 'source_ip',
      width: 130,
    },
    {
      title: t('system.security.appName'),
      dataIndex: 'app_name',
      key: 'app_name',
      width: 140,
      render: (_: string, record: OperationLog) => formatRecorded(formatAppName(record)),
    },
    {
      title: t('system.security.operationType'),
      dataIndex: 'action_type_display',
      key: 'action_type_display',
      width: 120,
    },
    {
      title: t('system.security.operationObject'),
      key: 'target',
      width: 150,
      ellipsis: true,
      render: (_: unknown, record: OperationLog) =>
        formatRecorded(buildOperationLogDetailView(record).targetName),
    },
    {
      title: t('system.security.executionResult'),
      key: 'outcome',
      width: 110,
      render: (_: unknown, record: OperationLog) => {
        const outcome = buildOperationLogDetailView(record).outcome;
        const colorMap: Record<OperationOutcome, string> = {
          success: 'success',
          failure: 'error',
          accepted: 'processing',
          unrecorded: 'default',
        };
        return (
          <Tag color={colorMap[outcome] || 'default'} className="m-0">
            {formatOutcome(outcome)}
          </Tag>
        );
      },
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
      width: 80,
      fixed: 'right' as const,
      render: (_: unknown, record: OperationLog) => (
        <Button type="link" size="small" onClick={() => handleOpenDetail(record)}>
          {t('common.detail')}
        </Button>
      ),
    },
  ];

  const detailView = detailRecord ? buildOperationLogDetailView(detailRecord) : null;

  return (
    <div className="flex flex-col h-full w-full">
      <FilterToolbar className="w-full" contentClassName="w-full">
        <Input
          placeholder={t('system.security.operatorPlaceholder')}
          value={filters.username}
          onChange={(e) => setFilters({ ...filters, username: e.target.value })}
          allowClear
          className="w-48"
        />
        <Input
          placeholder={t('system.security.targetPlaceholder')}
          value={filters.target}
          onChange={(e) => setFilters({ ...filters, target: e.target.value })}
          allowClear
          className="w-48"
        />
        <Select
          placeholder={t('system.security.operationModulePlaceholder')}
          value={filters.app || undefined}
          onChange={(value) => setFilters({ ...filters, app: value })}
          allowClear
          className="w-40"
          options={clientData.map((item) => ({
            label: resolveAppDisplayName(item, t),
            value: item.name,
          }))}
        />
        <Select
          placeholder={t('system.security.operationTypePlaceholder')}
          value={filters.actionType || undefined}
          onChange={(value) => setFilters({ ...filters, actionType: value })}
          allowClear
          className="w-36"
          options={[
            { label: t('common.create'), value: 'create' },
            { label: t('common.update'), value: 'update' },
            { label: t('common.delete'), value: 'delete' },
            { label: t('common.execute'), value: 'execute' },
          ]}
        />
        <Select
          placeholder={t('system.security.outcomePlaceholder')}
          value={filters.outcome || undefined}
          onChange={(value) => setFilters({ ...filters, outcome: value })}
          allowClear
          className="w-36"
          options={[
            { label: t('system.security.outcomeSuccess'), value: 'success' },
            { label: t('system.security.outcomeFailure'), value: 'failure' },
            { label: t('system.security.outcomeAccepted'), value: 'accepted' },
            { label: t('system.security.outcomeUnrecorded'), value: 'unrecorded' },
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
        <div className="flex shrink-0 items-center gap-2">
          <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
            {t('common.search')}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={handleReset}>
            {t('common.reset')}
          </Button>
          <Button icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
            {t('common.export')}
          </Button>
        </div>
      </FilterToolbar>

      <SystemManagerFillTable>
        <CustomTable
          columns={columns}
          dataSource={dataSource}
          loading={loading}
          rowKey="id"
          rowSelection={rowSelection}
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
          scroll={{ x: 1300 }}
        />
      </SystemManagerFillTable>

      <Drawer
        title={t('common.detail')}
        width={720}
        open={detailVisible}
        onClose={handleCloseDetail}
        destroyOnHidden
      >
        {detailRecord && detailView && (
          <div className="flex flex-col gap-4">
            <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3.5">
              <div className="flex items-center gap-2 mb-2.5 font-medium text-[var(--color-text-1)] text-sm">
                <span className="w-1 h-3.5 bg-[var(--color-primary)] rounded-full inline-block" />
                {t('system.security.basicInfo')}
              </div>
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label={t('system.security.operator')}>
                  {formatRecorded(detailView.operator)}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.operationTime')}>
                  {detailRecord.operation_time
                    ? convertToLocalizedTime(detailRecord.operation_time)
                    : t('system.security.outcomeUnrecorded')}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.appName')}>
                  {formatRecorded(formatAppName(detailRecord))}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.sourceIp')}>
                  {formatRecorded(detailView.sourceIp)}
                </Descriptions.Item>
              </Descriptions>
            </div>

            <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3.5">
              <div className="flex items-center gap-2 mb-2.5 font-medium text-[var(--color-text-1)] text-sm">
                <span className="w-1 h-3.5 bg-[var(--color-primary)] rounded-full inline-block" />
                {t('system.security.operationObject')}
              </div>
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label={t('system.security.targetType')}>
                  {formatRecorded(detailView.targetType)}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.targetName')}>
                  {formatRecorded(detailView.targetName)}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.targetId')}>
                  {formatRecorded(detailView.targetId)}
                </Descriptions.Item>
              </Descriptions>
            </div>

            <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3.5">
              <div className="flex items-center gap-2 mb-2.5 font-medium text-[var(--color-text-1)] text-sm">
                <span className="w-1 h-3.5 bg-[var(--color-primary)] rounded-full inline-block" />
                {t('system.security.executionResult')}
              </div>
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label={t('system.security.executionResult')}>
                  {formatOutcome(detailView.outcome)}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.failureReason')}>
                  {detailView.outcome === 'failure'
                    ? (detailView.failureReason || t('system.security.outcomeUnrecorded'))
                    : '-'}
                </Descriptions.Item>
              </Descriptions>
              {detailView.showAcceptedHint && (
                <div className="mt-2.5 rounded border border-blue-200 bg-blue-50/50 dark:border-blue-900/50 dark:bg-blue-950/20 px-3 py-1.5 text-xs text-blue-600 dark:text-blue-400">
                  {t('system.security.outcomeAcceptedHint')}
                </div>
              )}
            </div>

            <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3.5">
              <div className="flex items-center gap-2 mb-2.5 font-medium text-[var(--color-text-1)] text-sm">
                <span className="w-1 h-3.5 bg-[var(--color-primary)] rounded-full inline-block" />
                {t('system.security.beforeAfter')}
              </div>
              {renderChangeSection(detailView)}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default OperationLogs;
