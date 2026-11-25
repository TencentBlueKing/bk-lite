'use client';

import React, { useEffect, useState } from 'react';
import dayjs from 'dayjs';
import { Button, Drawer, Descriptions, Input, message, Select, Typography } from 'antd';
import { DownloadOutlined, SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import type { TableRowSelection } from 'antd/es/table/interface';
import { useSecurityApi } from '@/app/system-manager/api/security';
import CustomTable from '@/components/custom-table';
import FilterToolbar from '@/components/filter-toolbar';
import SystemManagerFillTable from '@/app/system-manager/components/system-manager-fill-table';
import HttpMethodBadge from '@/components/http-method-badge';
import TimeSelector from '@/components/time-selector';
import { useClientData } from '@/context/client';
import { useUserInfoContext } from '@/context/userInfo';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import { resolveAppDisplayName } from '@/utils/appDisplayName';

const EMPTY_FILTERS = {
  keyword: '',
  username: '',
  app: [] as string[],
};

const lastSevenDays = (): number[] => {
  const end = Date.now();
  return [end - 7 * 24 * 60 * 60 * 1000, end];
};

interface ErrorLog {
  id: number;
  username: string;
  app: string;
  app_name?: string;
  module: string;
  error_message: string;
  recorded_text: string;
  parsed: boolean;
  method: string;
  path: string;
  exception_type: string;
  reason: string;
  stack_text: string;
  stack_trace?: string;
  domain: string;
  created_at: string;
}

const ErrorLogsPage: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { clientData } = useClientData();
  const { selectedGroup } = useUserInfoContext();
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [dataSource, setDataSource] = useState<ErrorLog[]>([]);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [timeRange, setTimeRange] = useState<number[]>(lastSevenDays);
  const [timeSelectorKey, setTimeSelectorKey] = useState(0);
  const [detailVisible, setDetailVisible] = useState(false);
  const [detailRecord, setDetailRecord] = useState<ErrorLog | null>(null);

  const { getErrorLogs, exportErrorLogs } = useSecurityApi();
  const unrecorded = t('system.security.outcomeUnrecorded');
  const stackUnrecorded = t('system.security.stackUnrecorded');

  const formatRecorded = (value?: string) => (value ? value : unrecorded);

  const fetchErrorLogs = async (
    page = 1,
    pageSize = pagination.pageSize,
    nextFilters = filters,
    nextTimeRange = timeRange,
  ) => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = {
        page,
        page_size: pageSize,
      };

      if (nextFilters.keyword) {
        params.keyword = nextFilters.keyword;
      }
      if (nextFilters.username) {
        params.username = nextFilters.username;
      }
      if (nextFilters.app && nextFilters.app.length > 0) {
        params.app = nextFilters.app.join(',');
      }
      if (nextTimeRange && nextTimeRange.length === 2) {
        params.time_start = dayjs(nextTimeRange[0]).toISOString();
        params.time_end = dayjs(nextTimeRange[1]).toISOString();
      }

      const response = await getErrorLogs(params);
      setDataSource(response.items || []);
      setPagination((prev) => ({
        ...prev,
        current: page,
        pageSize,
        total: response.count || 0,
      }));
    } catch (error) {
      message.error(t('common.fetchFailed'));
      console.error('Failed to fetch error logs:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedGroup?.id) {
      return;
    }
    fetchErrorLogs(1);
  }, [selectedGroup?.id]);

  const handleSearch = () => {
    fetchErrorLogs(1, pagination.pageSize);
  };

  const handleReset = () => {
    const nextFilters = { ...EMPTY_FILTERS, app: [] as string[] };
    const nextTimeRange = lastSevenDays();
    setFilters(nextFilters);
    setTimeRange(nextTimeRange);
    setTimeSelectorKey((key) => key + 1);
    fetchErrorLogs(1, pagination.pageSize, nextFilters, nextTimeRange);
  };

  const handleTimeChange = (range: number[]) => {
    setTimeRange(range);
  };

  const buildExportFilters = () => {
    const params: Record<string, string> = {};
    if (filters.keyword) {
      params.keyword = filters.keyword;
    }
    if (filters.username) {
      params.username = filters.username;
    }
    if (filters.app && filters.app.length > 0) {
      params.app = filters.app.join(',');
    }
    if (timeRange && timeRange.length === 2) {
      params.time_start = dayjs(timeRange[0]).toISOString();
      params.time_end = dayjs(timeRange[1]).toISOString();
    }
    return params;
  };

  const handleExport = async () => {
    try {
      setExporting(true);
      const payload =
        selectedRowKeys.length > 0
          ? { selected_ids: selectedRowKeys }
          : buildExportFilters();
      const blob = await exportErrorLogs(payload);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `error_logs_${dayjs().format('YYYYMMDD_HHmmss')}.xlsx`;
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

  const handleOpenDetail = (record: ErrorLog) => {
    setDetailRecord(record);
    setDetailVisible(true);
  };

  const handleCloseDetail = () => {
    setDetailVisible(false);
    setDetailRecord(null);
  };

  const rowSelection: TableRowSelection<ErrorLog> = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => setSelectedRowKeys(keys),
  };

  const columns = [
    {
      title: t('system.security.operationTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (time: string) => convertToLocalizedTime(time),
    },
    {
      title: t('system.security.businessModule'),
      dataIndex: 'app_name',
      key: 'app_name',
      width: 160,
      render: (_: string, record: ErrorLog) => record.app_name || record.app,
    },
    {
      title: t('system.security.errorInfo'),
      key: 'error_info',
      render: (_: unknown, record: ErrorLog) => {
        if (record.parsed) {
          const meta = [record.exception_type, record.method, record.path]
            .filter(Boolean)
            .join(' · ');
          return (
            <button
              type="button"
              className="group w-full text-left rounded p-1 hover:bg-[var(--color-fill-1)]/50 transition-colors"
              onClick={() => handleOpenDetail(record)}
            >
              <div className="truncate font-medium text-[var(--color-text-1)] group-hover:text-[var(--color-primary)]">
                {formatRecorded(record.reason)}
              </div>
              <div className="truncate text-xs font-mono text-[var(--color-text-3)]">{meta}</div>
            </button>
          );
        }
        return (
          <button
            type="button"
            className="w-full truncate text-left rounded p-1 hover:bg-[var(--color-fill-1)]/50 transition-colors hover:text-[var(--color-primary)]"
            onClick={() => handleOpenDetail(record)}
          >
            {record.recorded_text}
          </button>
        );
      },
    },
    {
      title: t('system.security.relatedUser'),
      dataIndex: 'username',
      key: 'username',
      width: 140,
    },
    {
      title: t('common.actions'),
      key: 'detail',
      width: 100,
      fixed: 'right' as const,
      render: (_: unknown, record: ErrorLog) => (
        <Button type="link" size="small" onClick={() => handleOpenDetail(record)}>
          {t('common.detail')}
        </Button>
      ),
    },
  ];

  return (
    <div className="flex flex-col h-full w-full bg-[var(--color-bg)] p-4 overflow-hidden">
      <FilterToolbar className="w-full" contentClassName="w-full">
        <Input
          placeholder={t('system.security.errorKeywordPlaceholder')}
          value={filters.keyword}
          onChange={(e) => setFilters({ ...filters, keyword: e.target.value })}
          allowClear
          className="w-48"
        />
        <Input
          placeholder={t('system.security.relatedUserPlaceholder')}
          value={filters.username}
          onChange={(e) => setFilters({ ...filters, username: e.target.value })}
          allowClear
          className="w-48"
        />
        <Select
          mode="multiple"
          placeholder={t('system.security.operationModulePlaceholder')}
          value={filters.app}
          onChange={(value) => setFilters({ ...filters, app: value })}
          allowClear
          className="w-48"
          maxTagCount="responsive"
          options={clientData.map((item) => ({
            label: resolveAppDisplayName(item, t),
            value: item.name,
          }))}
        />
        <TimeSelector
          key={timeSelectorKey}
          showTime
          clearable
          onlyTimeSelect
          onChange={handleTimeChange}
          defaultValue={{
            selectValue: 7 * 24 * 60,
            rangePickerVaule: null,
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
              fetchErrorLogs(page, nextPageSize);
            },
          }}
          scroll={{ x: 1200 }}
        />
      </SystemManagerFillTable>

      <Drawer
        title={t('common.detail')}
        width={720}
        open={detailVisible}
        onClose={handleCloseDetail}
        destroyOnHidden
      >
        {detailRecord && (
          <div className="flex flex-col gap-4">
            <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3.5">
              <div className="flex items-center gap-2 mb-2.5 font-medium text-[var(--color-text-1)] text-sm">
                <span className="w-1 h-3.5 bg-[var(--color-primary)] rounded-full inline-block" />
                {t('system.security.basicInfo')}
              </div>
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label={t('system.security.operationTime')}>
                  {detailRecord.created_at
                    ? convertToLocalizedTime(detailRecord.created_at)
                    : unrecorded}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.relatedUser')}>
                  {formatRecorded(detailRecord.username)}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.businessModule')}>
                  {formatRecorded(detailRecord.app_name || detailRecord.app)}
                </Descriptions.Item>
              </Descriptions>
            </div>

            <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3.5">
              <div className="flex items-center gap-2 mb-2.5 font-medium text-[var(--color-text-1)] text-sm">
                <span className="w-1 h-3.5 bg-[var(--color-primary)] rounded-full inline-block" />
                {t('system.security.requestInfo')}
              </div>
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label={t('system.security.requestMethod')}>
                  {detailRecord.method ? (
                    <HttpMethodBadge method={detailRecord.method} />
                  ) : (
                    formatRecorded(detailRecord.method)
                  )}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.requestPath')}>
                  {detailRecord.path ? (
                    <Typography.Text copyable>{detailRecord.path}</Typography.Text>
                  ) : (
                    formatRecorded(detailRecord.path)
                  )}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.errorModule')}>
                  {formatRecorded(detailRecord.module)}
                </Descriptions.Item>
              </Descriptions>
            </div>

            <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3.5">
              <div className="flex items-center gap-2 mb-2.5 font-medium text-[var(--color-text-1)] text-sm">
                <span className="w-1 h-3.5 bg-[var(--color-primary)] rounded-full inline-block" />
                {t('system.security.errorInfo')}
              </div>
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label={t('system.security.exceptionType')}>
                  {formatRecorded(detailRecord.exception_type)}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.errorReason')}>
                  {formatRecorded(detailRecord.reason)}
                </Descriptions.Item>
                <Descriptions.Item label={t('system.security.recordedErrorText')}>
                  <Typography.Text copyable={{ text: detailRecord.recorded_text }}>
                    {detailRecord.recorded_text}
                  </Typography.Text>
                </Descriptions.Item>
              </Descriptions>
            </div>

            <div className="rounded-lg border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3.5">
              <div className="flex items-center gap-2 mb-2.5 font-medium text-[var(--color-text-1)] text-sm">
                <span className="w-1 h-3.5 bg-[var(--color-primary)] rounded-full inline-block" />
                {t('system.security.stackInfo')}
              </div>
              {detailRecord.stack_text ? (
                <div className="rounded-md border border-[var(--color-border-2)] bg-[var(--color-fill-1)]/40 p-3 max-h-[380px] overflow-auto">
                  <Typography.Paragraph
                    copyable={{ text: detailRecord.stack_text }}
                    className="!mb-0 font-mono text-xs leading-relaxed whitespace-pre text-[var(--color-text-2)]"
                  >
                    {detailRecord.stack_text}
                  </Typography.Paragraph>
                </div>
              ) : (
                <div className="rounded-md border border-dashed border-[var(--color-border-2)] p-4 text-center text-xs text-[var(--color-text-3)]">
                  {stackUnrecorded}
                </div>
              )}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default ErrorLogsPage;
