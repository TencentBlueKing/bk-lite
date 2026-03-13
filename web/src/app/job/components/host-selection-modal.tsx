'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Input, Button, Tag } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import useJobApi from '@/app/job/api';
import { Target } from '@/app/job/types';
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

const DRIVER_COLORS: Record<string, string> = {
  'nats-executor': 'blue',
  'ansible': 'green',
  'ssh': 'orange',
  'sidecar': 'geekblue',
};

const targetToHostItem = (target: Target): HostItem => ({
  key: String(target.id),
  hostName: target.name,
  ipAddress: target.ip,
  cloudRegion: target.cloud_region_name || '-',
  osType: target.os_type_display || target.os_type || '-',
  currentDriver: target.driver,
});

interface HostSelectionModalProps {
  open: boolean;
  selectedKeys: string[];
  source?: TargetSourceType;
  onConfirm: (keys: string[], hosts: HostItem[]) => void;
  onCancel: () => void;
}

const HostSelectionModal: React.FC<HostSelectionModalProps> = ({
  open,
  selectedKeys: initialKeys,
  source = 'target_manager',
  onConfirm,
  onCancel,
}) => {
  const { t } = useTranslation();
  const { isLoading: isApiReady } = useApiClient();
  const { getTargetList, queryNodes } = useJobApi();

  const [searchText, setSearchText] = useState('');
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>(initialKeys);
  const [dataSource, setDataSource] = useState<HostItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 20;

  // Track all selected hosts across pages
  const [selectedHostsMap, setSelectedHostsMap] = useState<Record<string, HostItem>>({});

  const fetchData = useCallback(async (page: number, search?: string) => {
    setLoading(true);
    try {
      if (source === 'node_manager') {
        const res = await queryNodes({
          page,
          page_size: pageSize,
          name: search || undefined,
        });
        const items: HostItem[] = (res.data?.items || []).map((node) => ({
          key: node.id,
          hostName: node.name,
          ipAddress: node.ip,
          cloudRegion: node.cloud_region_name || '-',
          osType: node.os_type || '-',
          currentDriver: '-',
        }));
        setDataSource(items);
        setTotal(res.data?.count || 0);
      } else {
        const res = await getTargetList({
          page,
          page_size: pageSize,
          search: search || undefined,
        });
        const items = (res.items || []).map(targetToHostItem);
        setDataSource(items);
        setTotal(res.count || 0);
      }
    } catch {
      setDataSource([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [getTargetList, queryNodes, source]);

  useEffect(() => {
    if (open && !isApiReady) {
      setSelectedRowKeys(initialKeys);
      setSearchText('');
      setCurrentPage(1);
      fetchData(1);
    }
  }, [open, isApiReady]);

  useEffect(() => {
    if (open) {
      setSelectedRowKeys(initialKeys);
    }
  }, [initialKeys, open]);

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
    ...(source === 'target_manager' ? [{
      title: t('job.currentDriver'),
      dataIndex: 'currentDriver',
      key: 'currentDriver',
      width: 130,
      render: (_: unknown, record: HostItem) => (
        <Tag color={DRIVER_COLORS[record.currentDriver] || 'default'}>
          {record.currentDriver}
        </Tag>
      ),
    }] : []),
  ];

  const handleSelectAllCurrent = () => {
    const currentKeys = dataSource.map((h) => h.key);
    const merged = Array.from(new Set([...selectedRowKeys, ...currentKeys]));
    setSelectedRowKeys(merged);
    // Track hosts
    const newMap = { ...selectedHostsMap };
    dataSource.forEach((h) => { newMap[h.key] = h; });
    setSelectedHostsMap(newMap);
  };

  const handleDeselectAll = () => {
    setSelectedRowKeys([]);
    setSelectedHostsMap({});
  };

  const handleRowSelectionChange = (keys: React.Key[]) => {
    const stringKeys = keys as string[];
    setSelectedRowKeys(stringKeys);
    // Update map: add newly selected from current page, remove deselected from current page
    const newMap = { ...selectedHostsMap };
    const currentPageKeys = new Set(dataSource.map((h) => h.key));
    // Remove deselected items from current page
    currentPageKeys.forEach((k) => {
      if (!stringKeys.includes(k)) {
        delete newMap[k];
      }
    });
    // Add selected items from current page
    dataSource.forEach((h) => {
      if (stringKeys.includes(h.key)) {
        newMap[h.key] = h;
      }
    });
    setSelectedHostsMap(newMap);
  };

  const handleConfirm = () => {
    const selectedHosts = selectedRowKeys
      .map((k) => selectedHostsMap[k])
      .filter(Boolean);
    onConfirm(selectedRowKeys, selectedHosts);
  };

  return (
    <OperateModal
      title={t('job.selectTargetHost')}
      open={open}
      width={800}
      onCancel={onCancel}
      footer={
        <div className="flex justify-end gap-2">
          <Button onClick={onCancel}>{t('job.cancel')}</Button>
          <Button type="primary" onClick={handleConfirm}>
            {t('job.confirm')}
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-3 h-[480px]">
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
            showTotal: (total: number) => t('job.totalItems').replace('{total}', String(total)),
          }}
          rowSelection={{
            selectedRowKeys,
            onChange: handleRowSelectionChange,
          }}
        />
        </div>
      </div>
    </OperateModal>
  );
};

export default HostSelectionModal;
