'use client';

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Button } from 'antd';
import CustomTable from '@/components/custom-table';
import JobDriverBadge from '@/app/job/components/driver-badge';
import OperateFormModal from '@/components/operate-form-modal';
import SearchCombination from '@/components/search-combination';
import type { FieldConfig, SearchFilters } from '@/components/search-combination/types';
import SelectionPreviewLayout from '@/components/selection-preview-layout';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useTranslation } from '@/utils/i18n';
import { ColumnItem } from '@/types';

const DEFAULT_PAGE_SIZE = 20;

export interface HostItem {
  key: string;
  hostName: string;
  ipAddress: string;
  cloudRegion: string;
  osType: string;
  currentDriver: string;
}

export type TargetSourceType = 'node_manager' | 'target_manager';

export interface FetchHostsParams {
  page: number;
  pageSize: number;
  filters?: SearchFilters;
  source: TargetSourceType;
  signal: AbortSignal;
}

export interface FetchHostsResult {
  items: HostItem[];
  total: number;
}

interface HostPaginationChange {
  currentPageSize: number;
  nextPage: number;
  nextPageSize: number;
}

export const resolveHostPaginationChange = ({
  currentPageSize,
  nextPage,
  nextPageSize,
}: HostPaginationChange) => ({
  page: nextPageSize === currentPageSize ? nextPage : 1,
  pageSize: nextPageSize,
});

export const formatHostSelectionLabel = (host: HostItem | undefined, fallbackKey: string) => {
  if (!host) return fallbackKey;
  if (host.hostName && host.ipAddress) return `${host.hostName} (${host.ipAddress})`;
  return host.hostName || host.ipAddress || fallbackKey;
};

export interface JobHostSelectionModalProps {
  open: boolean;
  selectedKeys: string[];
  selectedHosts?: HostItem[];
  source?: TargetSourceType;
  onConfirm: (keys: string[], hosts: HostItem[]) => void;
  onCancel: () => void;
  fetchHosts: (params: FetchHostsParams) => Promise<FetchHostsResult>;
}

export type { JobHostSelectionTarget } from './types';

const JobHostSelectionModal: React.FC<JobHostSelectionModalProps> = ({
  open,
  selectedKeys: initialKeys,
  selectedHosts = [],
  source = 'target_manager',
  onConfirm,
  onCancel,
  fetchHosts,
}) => {
  const { t } = useTranslation();

  const [filters, setFilters] = useState<SearchFilters>({});
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>(initialKeys);
  const [dataSource, setDataSource] = useState<HostItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [selectedHostsMap, setSelectedHostsMap] = useState<Record<string, HostItem>>({});
  const fetchHostsRef = useRef(fetchHosts);
  const requestControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const pendingFilterSignatureRef = useRef<string | null>(null);
  const filterFields = useMemo<FieldConfig[]>(() => [
    {
      name: 'keyword',
      label: t('job.hostNameOrIp'),
      lookup_expr: 'icontains',
    },
    {
      name: 'os_type',
      label: t('job.osType'),
      lookup_expr: 'in',
      options: [
        { id: 'linux', name: t('job.linux') },
        { id: 'windows', name: t('job.windows') },
      ],
    },
  ], [t]);

  useEffect(() => {
    fetchHostsRef.current = fetchHosts;
  }, [fetchHosts]);

  const cancelPendingRequest = useCallback(() => {
    requestIdRef.current += 1;
    requestControllerRef.current?.abort();
    requestControllerRef.current = null;
  }, []);

  const fetchData = useCallback(
    async (page: number, nextPageSize: number, nextFilters?: SearchFilters) => {
      cancelPendingRequest();
      const controller = new AbortController();
      const requestId = requestIdRef.current;
      requestControllerRef.current = controller;
      setLoading(true);
      try {
        const result = await fetchHostsRef.current({
          page,
          pageSize: nextPageSize,
          filters: nextFilters,
          source,
          signal: controller.signal,
        });
        if (requestId !== requestIdRef.current || controller.signal.aborted) return;
        setDataSource(result.items);
        setTotal(result.total);
      } catch {
        if (requestId !== requestIdRef.current || controller.signal.aborted) return;
        setDataSource([]);
        setTotal(0);
      } finally {
        if (requestId === requestIdRef.current) {
          requestControllerRef.current = null;
          setLoading(false);
        }
      }
    },
    [cancelPendingRequest, source],
  );

  useEffect(() => {
    if (!open) {
      setLoading(false);
      return;
    }

    setFilters({});
    setCurrentPage(1);
    setPageSize(DEFAULT_PAGE_SIZE);
    setDataSource([]);
    setTotal(0);
    void fetchData(1, DEFAULT_PAGE_SIZE);

    return cancelPendingRequest;
  }, [cancelPendingRequest, fetchData, open]);

  useEffect(() => {
    if (open) {
      setSelectedRowKeys(initialKeys);
    }
  }, [initialKeys, open]);

  useEffect(() => {
    if (!open) return;

    setSelectedHostsMap(
      selectedHosts.reduce<Record<string, HostItem>>((acc, host) => {
        acc[host.key] = host;
        return acc;
      }, {}),
    );
  }, [open, selectedHosts]);

  const handleFilterChange = (nextFilters: SearchFilters) => {
    const signature = JSON.stringify(nextFilters);
    // tags 模式下 Enter 会在同一轮事件中重复触发相同筛选，只在请求边界合并本轮重复值。
    if (pendingFilterSignatureRef.current === signature) return;

    pendingFilterSignatureRef.current = signature;
    queueMicrotask(() => {
      if (pendingFilterSignatureRef.current === signature) {
        pendingFilterSignatureRef.current = null;
      }
    });
    setFilters(nextFilters);
    setCurrentPage(1);
    fetchData(1, pageSize, nextFilters);
  };

  const handlePageChange = (nextPage: number, nextPageSize: number) => {
    const pagination = resolveHostPaginationChange({
      currentPageSize: pageSize,
      nextPage,
      nextPageSize,
    });
    setCurrentPage(pagination.page);
    setPageSize(pagination.pageSize);
    fetchData(pagination.page, pagination.pageSize, filters);
  };

  const columns: ColumnItem[] = [
    {
      title: t('job.hostName'),
      dataIndex: 'hostName',
      key: 'hostName',
      width: 160,
    },
    {
      title: t('job.ipAddress'),
      dataIndex: 'ipAddress',
      key: 'ipAddress',
      width: 140,
    },
    {
      title: t('job.cloudRegion'),
      dataIndex: 'cloudRegion',
      key: 'cloudRegion',
      width: 100,
    },
    {
      title: t('job.osType'),
      dataIndex: 'osType',
      key: 'osType',
      width: 100,
    },
    ...(source === 'target_manager'
      ? [
        {
          title: t('job.currentDriver'),
          dataIndex: 'currentDriver',
          key: 'currentDriver',
          width: 130,
          render: (_: unknown, record: HostItem) => (
              <JobDriverBadge driver={record.currentDriver} />
          ),
        },
      ]
      : []),
  ];

  const handleSelectAllCurrent = () => {
    const currentKeys = dataSource.map((host) => host.key);
    const merged = Array.from(new Set([...selectedRowKeys, ...currentKeys]));
    setSelectedRowKeys(merged);
    const nextMap = { ...selectedHostsMap };
    dataSource.forEach((host) => {
      nextMap[host.key] = host;
    });
    setSelectedHostsMap(nextMap);
  };

  const handleDeselectAll = () => {
    setSelectedRowKeys([]);
    setSelectedHostsMap({});
  };

  const handleRowSelectionChange = (keys: React.Key[]) => {
    const stringKeys = keys as string[];
    setSelectedRowKeys(stringKeys);
    const nextMap = { ...selectedHostsMap };
    const currentPageKeys = new Set(dataSource.map((host) => host.key));

    currentPageKeys.forEach((key) => {
      if (!stringKeys.includes(key)) {
        delete nextMap[key];
      }
    });

    dataSource.forEach((host) => {
      if (stringKeys.includes(host.key)) {
        nextMap[host.key] = host;
      }
    });

    setSelectedHostsMap(nextMap);
  };

  const handleConfirm = () => {
    const nextSelectedHosts = selectedRowKeys
      .map((key) => selectedHostsMap[key])
      .filter(Boolean);
    onConfirm(selectedRowKeys, nextSelectedHosts);
  };

  return (
    <OperateFormModal
      title={t('job.selectTargetHost')}
      open={open}
      width={960}
      onCancel={onCancel}
      confirmText={t('job.confirm')}
      cancelText={t('job.cancel')}
      primaryFirst={false}
      onConfirm={handleConfirm}
    >
      <SelectionPreviewLayout
        primaryWidth={660}
        listHeight="420px"
        primary={(
          <div className="flex h-[480px] flex-col gap-3">
            <div className="flex items-center justify-between">
              <SearchCombination
                key={`${source}-${open ? 'open' : 'closed'}`}
                fieldConfigs={filterFields}
                fieldWidth={96}
                selectWidth={190}
                onChange={handleFilterChange}
              />
              <div className="flex gap-2">
                <Button size="small" onClick={handleSelectAllCurrent}>
                  {t('job.selectAllCurrent')}
                </Button>
                <Button size="small" onClick={handleDeselectAll}>
                  {t('job.deselectAll')}
                </Button>
              </div>
            </div>
            <div className="flex-1">
              <CustomTable
                dataSource={dataSource}
                columns={columns}
                rowKey="key"
                scroll={{}}
                loading={loading}
                pagination={{
                  current: currentPage,
                  pageSize,
                  total,
                  onChange: handlePageChange,
                  showSizeChanger: true,
                  showTotal: (count: number) =>
                    t('job.totalItems').replace('{total}', String(count)),
                }}
                rowSelection={{
                  selectedRowKeys,
                  onChange: handleRowSelectionChange,
                  preserveSelectedRowKeys: true,
                }}
              />
            </div>
          </div>
        )}
        items={selectedRowKeys.map((key) => ({
          key,
          label: (
            <EllipsisWithTooltip
              text={formatHostSelectionLabel(selectedHostsMap[key], key)}
              className="w-full min-w-0 truncate"
            />
          ),
        }))}
        onClear={handleDeselectAll}
        onRemove={(key) => {
          const nextKeys = selectedRowKeys.filter((item) => item !== key);
          const nextMap = { ...selectedHostsMap };
          delete nextMap[key];
          setSelectedRowKeys(nextKeys);
          setSelectedHostsMap(nextMap);
        }}
      />
    </OperateFormModal>
  );
};

export default JobHostSelectionModal;
