'use client';

import React, { useEffect, useRef, useState } from 'react';
import { Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useLogApi from '@/app/log/api/integration';
import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import SearchActionBar from '@/components/search-action-bar';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { ColumnItem } from '@/types';
import { SyslogSourceDeviceRow } from '@/app/log/types/syslogSourceDevice';
import { buildSourceDeviceSearchUrl } from '@/app/log/(pages)/integration/list/detail/source-device/sourceDeviceSearch';

interface SourceDeviceQuery {
  keyword: string;
  status?: 'active' | 'silent';
}

const EMPTY_QUERY: SourceDeviceQuery = {
  keyword: ''
};

const SyslogSourceDevicePane = ({
  refreshKey = 0,
  onUnfilteredCount
}: {
  refreshKey?: number;
  onUnfilteredCount?: (count: number) => void;
}) => {
  const { t } = useTranslation();
  const { isLoading } = useApiClient();
  const { getSyslogSourceDevices } = useLogApi();
  const { convertToLocalizedTime } = useLocalizedTime();
  const onCountRef = useRef(onUnfilteredCount);
  onCountRef.current = onUnfilteredCount;
  const [keywordDraft, setKeywordDraft] = useState('');
  const [applied, setApplied] = useState<SourceDeviceQuery>(EMPTY_QUERY);
  const [tableData, setTableData] = useState<SyslogSourceDeviceRow[]>([]);
  const [tableLoading, setTableLoading] = useState(false);
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20
  });

  useEffect(() => {
    if (isLoading) return;
    let cancelled = false;
    const load = async () => {
      setTableLoading(true);
      try {
        const data = await getSyslogSourceDevices({
          page: pagination.current,
          page_size: pagination.pageSize,
          ...(applied.keyword ? { keyword: applied.keyword } : {}),
          ...(applied.status ? { status: applied.status } : {})
        });
        if (cancelled) return;
        setTableData(data?.items || []);
        setPagination((prev) => ({ ...prev, total: data?.count || 0 }));
        const unfiltered = !applied.keyword && !applied.status;
        if (unfiltered) onCountRef.current?.(data?.count || 0);
      } finally {
        if (!cancelled) setTableLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [applied, isLoading, pagination.current, pagination.pageSize, refreshKey]);

  const resetPage = () => {
    setPagination((prev) => ({ ...prev, current: 1 }));
  };

  const applyKeyword = (value: string) => {
    const keyword = value.trim();
    setKeywordDraft(value);
    setApplied((prev) => ({ ...prev, keyword }));
    resetPage();
  };

  const applyStatus = (status?: SourceDeviceQuery['status']) => {
    setApplied((prev) => ({ ...prev, status }));
    resetPage();
  };

  const columns: ColumnItem[] = [
    {
      title: t('log.sourceDevice.cloudRegion'),
      dataIndex: 'cloud_region_id',
      key: 'cloud_region_id',
      render: (_, record: SyslogSourceDeviceRow) => (
        <EllipsisWithTooltip
          className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          text={record.cloud_region_name || record.cloud_region_id}
        />
      )
    },
    {
      title: t('log.sourceDevice.sourceIp'),
      dataIndex: 'source_ip',
      key: 'source_ip',
      render: (value: string) => (
        <EllipsisWithTooltip
          className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          text={value}
        />
      )
    },
    {
      title: t('log.sourceDevice.hostname'),
      dataIndex: 'hostname',
      key: 'hostname',
      render: (value: string) => (
        <EllipsisWithTooltip
          className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
          text={value}
        />
      )
    },
    {
      title: t('log.sourceDevice.firstSeen'),
      dataIndex: 'first_seen',
      key: 'first_seen',
      render: (value: string) =>
        convertToLocalizedTime(value, 'YYYY-MM-DD HH:mm:ss')
    },
    {
      title: t('log.sourceDevice.lastSeen'),
      dataIndex: 'last_seen',
      key: 'last_seen',
      render: (value: string) =>
        convertToLocalizedTime(value, 'YYYY-MM-DD HH:mm:ss')
    },
    {
      title: t('log.sourceDevice.status'),
      dataIndex: 'status',
      key: 'status',
      filters: [
        { text: t('log.sourceDevice.active'), value: 'active' },
        { text: t('log.sourceDevice.silent'), value: 'silent' }
      ],
      filterMultiple: false,
      filteredValue: applied.status ? [applied.status] : null,
      render: (status: SyslogSourceDeviceRow['status']) => (
        <Tag
          color={
            status === 'active'
              ? 'var(--color-success)'
              : 'var(--color-text-4)'
          }
        >
          {t(
            status === 'active'
              ? 'log.sourceDevice.active'
              : 'log.sourceDevice.silent'
          )}
        </Tag>
      )
    }
  ];

  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-col">
      <div className="mb-4">
        <SearchActionBar
          spacing="flush"
          searchProps={{
            allowClear: true,
            placeholder: t('log.sourceDevice.searchPlaceholder'),
            value: keywordDraft,
            onChange: (event) => {
              const value = event.target.value;
              setKeywordDraft(value);
              if (!value) applyKeyword('');
            },
            onSearch: applyKeyword
          }}
        />
      </div>
      <CustomTable
        rowKey={(record: SyslogSourceDeviceRow) =>
          `${record.cloud_region_id}\u0000${record.source_ip}\u0000${record.hostname}`
        }
        columns={columns}
        dataSource={tableData}
        loading={tableLoading}
        scroll={{ y: 'calc(100vh - 340px)', x: 'max-content' }}
        pagination={{
          ...pagination,
          showSizeChanger: true,
          pageSizeOptions: ['10', '20', '50', '100']
        }}
        onChange={(pager, tableFilters, _sorter, extra) => {
          if (extra?.action === 'filter') {
            const value = tableFilters?.status?.[0];
            applyStatus(
              value === 'active' || value === 'silent' ? value : undefined
            );
            return;
          }
          setPagination((prev) => ({
            ...prev,
            current: pager.current || 1,
            pageSize: pager.pageSize || prev.pageSize
          }));
        }}
        onRow={(record: SyslogSourceDeviceRow) => ({
          onClick: () => {
            window.open(
              buildSourceDeviceSearchUrl(record),
              '_blank',
              'noopener,noreferrer'
            );
          }
        })}
        rowClassName="cursor-pointer"
      />
    </div>
  );
};

export default SyslogSourceDevicePane;
