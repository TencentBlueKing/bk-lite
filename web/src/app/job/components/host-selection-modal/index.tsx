'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Input, Button } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import JobDriverBadge from '@/app/job/components/driver-badge';
import OperateFormModal from '@/components/operate-form-modal';
import SelectionPreviewLayout from '@/components/selection-preview-layout';
import { useTranslation } from '@/utils/i18n';
import { ColumnItem } from '@/types';

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
  search?: string;
  source: TargetSourceType;
}

export interface FetchHostsResult {
  items: HostItem[];
  total: number;
}

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

  const [searchText, setSearchText] = useState('');
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>(initialKeys);
  const [dataSource, setDataSource] = useState<HostItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedHostsMap, setSelectedHostsMap] = useState<Record<string, HostItem>>({});
  const pageSize = 20;

  const fetchData = useCallback(
    async (page: number, search?: string) => {
      setLoading(true);
      try {
        const result = await fetchHosts({ page, pageSize, search, source });
        setDataSource(result.items);
        setTotal(result.total);
      } catch {
        setDataSource([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    },
    [fetchHosts, source],
  );

  useEffect(() => {
    if (open) {
      setSelectedRowKeys(initialKeys);
      setSearchText('');
      setCurrentPage(1);
      fetchData(1);
    }
  }, [fetchData, initialKeys, open]);

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

  const handleSearch = () => {
    setCurrentPage(1);
    fetchData(1, searchText);
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
    if (!e.target.value) {
      setCurrentPage(1);
      fetchData(1);
    }
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    fetchData(page, searchText);
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
      width={800}
      onCancel={onCancel}
      confirmText={t('job.confirm')}
      cancelText={t('job.cancel')}
      primaryFirst={false}
      onConfirm={handleConfirm}
    >
      <SelectionPreviewLayout
        primaryWidth={560}
        listHeight="420px"
        primary={(
          <div className="flex h-[480px] flex-col gap-3">
            <div className="flex items-center justify-between">
              <Input
                className="w-[320px]"
                placeholder={t('job.searchHostPlaceholder')}
                prefix={<SearchOutlined />}
                allowClear
                value={searchText}
                onChange={handleSearchChange}
                onPressEnter={handleSearch}
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
                  showSizeChanger: false,
                  showTotal: (count: number) =>
                    t('job.totalItems').replace('{total}', String(count)),
                }}
                rowSelection={{
                  selectedRowKeys,
                  onChange: handleRowSelectionChange,
                }}
              />
            </div>
          </div>
        )}
        items={selectedRowKeys.map((key) => ({
          key,
          label: selectedHostsMap[key]?.hostName || selectedHostsMap[key]?.ipAddress || key,
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
