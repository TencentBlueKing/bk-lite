'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Button, Input, Select, Space, Tag, message } from 'antd';
import { DownloadOutlined, SearchOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { ColumnsType } from 'antd/es/table';
import type { TableRowSelection } from 'antd/es/table/interface';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import TimeSelector from '@/components/time-selector';
import { useSecurityApi } from '@/app/system-manager/api/security';
import {
  formatOpenApiCallRequest,
  formatOpenApiCallResult,
  formatOpenApiCallTokenKind,
  formatOpenApiCallTokenSystemId,
  openApiCallErrorCode,
  openApiCallSucceeded,
  type OpenApiCallLogRow,
} from '@/app/system-manager/utils/openapiCallLogs';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';

const TOKEN_KIND_OPTIONS = [
  { value: 'api_token', labelKey: 'system.security.credentialApiToken' },
  { value: 'system_token', labelKey: 'system.security.credentialSystemToken' },
];

const API_KIND_OPTIONS = [
  { value: 'internal', labelKey: 'system.security.apiKindInternal' },
  { value: 'external', labelKey: 'system.security.apiKindExternal' },
];

const OUTCOME_OPTIONS = [
  { value: 'success', labelKey: 'system.security.loginStatusSuccess' },
  { value: 'failure', labelKey: 'system.security.loginStatusFailed' },
];

const EMPTY_FILTERS = {
  username: '',
  path: '',
  credential_type: undefined as string | undefined,
  api_kind: undefined as string | undefined,
  outcome: undefined as string | undefined,
};

const DEFAULT_RANGE_MINUTES = 7 * 24 * 60;

const freshDefaultRange = () => {
  const end = dayjs().valueOf();
  return [dayjs(end).subtract(DEFAULT_RANGE_MINUTES, 'minute').valueOf(), end];
};

interface TimeSelectorHandle {
  getValue?: () => number[] | null;
}

const OpenApiCallLogs: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getOpenApiCallLogs, exportOpenApiCallLogs } = useSecurityApi();
  const timeSelectorRef = useRef<TimeSelectorHandle>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [logs, setLogs] = useState<OpenApiCallLogRow[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [timeSelectorKey, setTimeSelectorKey] = useState(0);
  const [timeRange, setTimeRange] = useState<number[]>(freshDefaultRange);

  const apiKindLabel = (value?: string) => {
    const option = API_KIND_OPTIONS.find((item) => item.value === value);
    return option ? t(option.labelKey) : '--';
  };

  const resultLabels = {
    success: t('system.security.loginStatusSuccess'),
    failure: t('system.security.loginStatusFailed'),
  };

  const tokenKindLabels = {
    apiToken: t('system.security.credentialApiToken'),
    systemToken: t('system.security.credentialSystemToken'),
  };

  const buildParams = (
    page = 1,
    pageSize = pagination.pageSize,
    nextFilters = filters,
    nextRange = timeRange,
  ) => {
    const params: Record<string, string | number> = {
      page,
      page_size: pageSize,
    };
    (Object.keys(nextFilters) as Array<keyof typeof nextFilters>).forEach((key) => {
      const value = nextFilters[key];
      if (value) {
        params[key] = value;
      }
    });
    if (nextRange?.length === 2) {
      params.created_at_start = dayjs(nextRange[0]).format('YYYY-MM-DD HH:mm:ss');
      params.created_at_end = dayjs(nextRange[1]).format('YYYY-MM-DD HH:mm:ss');
    }
    return params;
  };

  const fetchLogs = async (
    page = 1,
    pageSize = pagination.pageSize,
    next?: { filters?: typeof EMPTY_FILTERS; timeRange?: number[] },
  ) => {
    const nextFilters = next?.filters ?? filters;
    const nextRange = next?.timeRange ?? timeRange;
    try {
      setLoading(true);
      const response = await getOpenApiCallLogs(buildParams(page, pageSize, nextFilters, nextRange));
      setLogs(response.items || []);
      setPagination({
        current: page,
        pageSize,
        total: response.count || 0,
      });
    } catch (error) {
      console.error('Failed to fetch openapi call logs:', error);
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const resolveTimeRange = () => {
    const value = timeSelectorRef.current?.getValue?.();
    if (Array.isArray(value) && value.length === 2 && value[0] && value[1]) {
      return value as number[];
    }
    return timeRange;
  };

  const handleSearch = () => {
    const range = resolveTimeRange();
    setTimeRange(range);
    fetchLogs(1, pagination.pageSize, { timeRange: range });
  };

  const handleReset = () => {
    const range = freshDefaultRange();
    setFilters(EMPTY_FILTERS);
    setTimeRange(range);
    setTimeSelectorKey((key) => key + 1);
    fetchLogs(1, pagination.pageSize, { filters: EMPTY_FILTERS, timeRange: range });
  };

  const handleExport = async () => {
    try {
      setExporting(true);
      const payload =
        selectedRowKeys.length > 0
          ? { selected_ids: selectedRowKeys }
          : buildParams();
      const blob = await exportOpenApiCallLogs(payload);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `openapi_call_logs_${dayjs().format('YYYYMMDD_HHmmss')}.xlsx`;
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

  const rowSelection: TableRowSelection<OpenApiCallLogRow> = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => setSelectedRowKeys(keys),
  };

  const columns: ColumnsType<OpenApiCallLogRow> = [
    {
      title: t('system.security.operationTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (text: string) => convertToLocalizedTime(text),
    },
    {
      title: t('system.user.table.username'),
      dataIndex: 'username',
      key: 'username',
      width: 140,
      render: (text: string) => text || '--',
    },
    {
      title: t('system.security.teamName'),
      dataIndex: 'team_name',
      key: 'team_name',
      width: 140,
      render: (text: string) => text || '--',
    },
    {
      title: t('system.security.sourceIp'),
      dataIndex: 'source_ip',
      key: 'source_ip',
      width: 140,
      render: (text: string) => text || '--',
    },
    {
      title: t('system.security.tokenKind'),
      dataIndex: 'credential_type',
      key: 'credential_type',
      width: 140,
      render: (_: unknown, record: OpenApiCallLogRow) => {
        const systemId = formatOpenApiCallTokenSystemId(record);
        return (
          <div className="min-w-0">
            <div className="truncate">{formatOpenApiCallTokenKind(record, tokenKindLabels)}</div>
            {systemId ? (
              <div className="truncate text-xs text-[var(--color-text-3)]">
                {t('system.security.systemIdPrefix')}:{systemId}
              </div>
            ) : null}
          </div>
        );
      },
    },
    {
      title: t('system.security.secretName'),
      dataIndex: 'token_name',
      key: 'token_name',
      width: 140,
      render: (text: string) => text || '--',
    },
    {
      title: t('system.security.apiCallRequest'),
      key: 'request',
      ellipsis: true,
      render: (_: unknown, record: OpenApiCallLogRow) => (
        <EllipsisWithTooltip
          text={formatOpenApiCallRequest(record)}
          className="overflow-hidden text-ellipsis whitespace-nowrap"
        />
      ),
    },
    {
      title: t('system.security.apiKind'),
      dataIndex: 'api_kind',
      key: 'api_kind',
      width: 120,
      render: (value: string) => apiKindLabel(value),
    },
    {
      title: t('system.security.apiCallResult'),
      key: 'result',
      width: 100,
      render: (_: unknown, record: OpenApiCallLogRow) => (
        <Tag className="m-0" color={openApiCallSucceeded(record) ? 'green' : 'red'}>
          {formatOpenApiCallResult(record, resultLabels)}
        </Tag>
      ),
    },
    {
      title: t('system.security.errorCode'),
      key: 'error_code',
      width: 180,
      render: (_: unknown, record: OpenApiCallLogRow) => openApiCallErrorCode(record) || '--',
    },
  ];

  return (
    <div className="flex flex-col h-full w-full">
      <div className="flex-none flex justify-end mb-3">
        <Space wrap>
          <Input
            placeholder={t('system.user.table.username')}
            className="w-[160px]"
            allowClear
            value={filters.username}
            onChange={(e) => setFilters({ ...filters, username: e.target.value })}
          />
          <Input
            placeholder={t('system.security.apiCallRequest')}
            className="w-[200px]"
            allowClear
            value={filters.path}
            onChange={(e) => setFilters({ ...filters, path: e.target.value })}
          />
          <Select
            placeholder={t('system.security.tokenKind')}
            className="w-[140px]"
            allowClear
            value={filters.credential_type}
            onChange={(value) => setFilters({ ...filters, credential_type: value })}
            options={TOKEN_KIND_OPTIONS.map((item) => ({
              value: item.value,
              label: t(item.labelKey),
            }))}
          />
          <Select
            placeholder={t('system.security.apiKind')}
            className="w-[140px]"
            allowClear
            value={filters.api_kind}
            onChange={(value) => setFilters({ ...filters, api_kind: value })}
            options={API_KIND_OPTIONS.map((item) => ({
              value: item.value,
              label: t(item.labelKey),
            }))}
          />
          <Select
            placeholder={t('system.security.apiCallResult')}
            className="w-[120px]"
            allowClear
            value={filters.outcome}
            onChange={(value) => setFilters({ ...filters, outcome: value })}
            options={OUTCOME_OPTIONS.map((item) => ({
              value: item.value,
              label: t(item.labelKey),
            }))}
          />
          <TimeSelector
            key={timeSelectorKey}
            ref={timeSelectorRef}
            showTime
            clearable
            onlyTimeSelect
            onChange={setTimeRange}
            defaultValue={{
              selectValue: DEFAULT_RANGE_MINUTES,
              rangePickerVaule: null,
            }}
          />
          <Space>
            <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
              {t('common.search')}
            </Button>
            <Button onClick={handleReset}>
              {t('common.reset')}
            </Button>
            <Button icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
              {t('common.export')}
            </Button>
          </Space>
        </Space>
      </div>
      <div className="flex-1 min-h-0 relative">
        <CustomTable
          columns={columns}
          dataSource={logs}
          loading={loading}
          rowKey="id"
          rowSelection={rowSelection}
          scroll={{ x: 1200 }}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            showQuickJumper: true,
            onChange: fetchLogs,
            onShowSizeChange: fetchLogs,
          }}
        />
      </div>
    </div>
  );
};

export default OpenApiCallLogs;
