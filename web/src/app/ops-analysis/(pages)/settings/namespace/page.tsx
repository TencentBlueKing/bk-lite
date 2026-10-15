'use client';

import React, { useState, useEffect } from 'react';
import OperateModal from './operateModal';
import PermissionWrapper from '@/components/permission';
import { Button, message, Modal, Tag, Space } from 'antd';
import { PlusOutlined, UploadOutlined } from '@ant-design/icons';
import OpsAnalysisSettingsListShell from '@/app/ops-analysis/components/ops-analysis-settings-list-shell';
import { useTranslation } from '@/utils/i18n';
import { NamespaceItem } from '@/app/ops-analysis/types/namespace';
import { useNamespaceApi } from '@/app/ops-analysis/api/namespace';
import { useOpsAnalysis } from '@/app/ops-analysis/context/common';
import { useImportExportApi } from '@/app/ops-analysis/api/importExport';
import { ImportModal } from '@/app/ops-analysis/components/importExport';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

const Namespace: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getNamespaceList, deleteNamespace } = useNamespaceApi();
  const { refreshNamespaces } = useOpsAnalysis();
  const { exportObjects, downloadYaml } = useImportExportApi();
  const [searchKey, setSearchKey] = useState('');
  const [searchValue, setSearchValue] = useState('');
  const [filteredList, setFilteredList] = useState<NamespaceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalVisible, setModalVisible] = useState(false);
  const [currentRow, setCurrentRow] = useState<any>(null);
  const [importModalVisible, setImportModalVisible] = useState(false);
  const [exportLoading, setExportLoading] = useState<number | null>(null);
  const [pagination, setPagination] = useState({
    current: 1,
    total: 0,
    pageSize: 20,
  });

  // 获取命名空间列表
  const fetchNamespaces = async (
    searchKeyParam?: string,
    paginationParam?: { current?: number; pageSize?: number }
  ) => {
    try {
      setLoading(true);
      const currentPagination = paginationParam || pagination;
      const params: any = {
        page: currentPagination.current || pagination.current,
        page_size: currentPagination.pageSize || pagination.pageSize,
      };
      const currentSearchKey =
        searchKeyParam !== undefined ? searchKeyParam : searchKey;
      if (currentSearchKey && currentSearchKey.trim()) {
        params.name = currentSearchKey.trim();
      }
      const { items, count } = await getNamespaceList(params);
      if (items && Array.isArray(items)) {
        setFilteredList(items);
        setPagination((prev) => ({
          ...prev,
          current: currentPagination.current || prev.current,
          pageSize: currentPagination.pageSize || prev.pageSize,
          total: count || 0,
        }));
      }
    } catch (error) {
      console.error('获取命名空间列表失败:', error);
      setFilteredList([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNamespaces();
  }, [pagination.current, pagination.pageSize]);

  const handleFilter = (value?: string) => {
    const key = value !== undefined ? value : searchValue;
    setSearchKey(key);
    setSearchValue(key);
    const newPagination = { current: 1, pageSize: pagination.pageSize };
    setPagination((prev) => ({ ...prev, current: 1 }));
    fetchNamespaces(key, newPagination);
  };

  const handleEdit = (type: 'add' | 'edit', row?: NamespaceItem) => {
    if (type === 'edit' && row) {
      setCurrentRow(row);
    } else {
      setCurrentRow(null);
    }
    setModalVisible(true);
  };

  const handleDelete = (row: NamespaceItem) => {
    Modal.confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      okButtonProps: { danger: true },
      centered: true,
      onOk: async () => {
        try {
          await deleteNamespace(row.id);
          message.success(t('opsAnalysis.successfullyDeleted'));
          await refreshNamespaces();

          if (pagination.current > 1 && filteredList.length === 1) {
            setPagination((prev) => ({ ...prev, current: prev.current - 1 }));
            fetchNamespaces(searchKey, {
              current: pagination.current - 1,
              pageSize: pagination.pageSize,
            });
          } else {
            fetchNamespaces();
          }
        } catch (error: any) {
          message.error(error.message);
        }
      },
    });
  };

  const handleExport = async (row: NamespaceItem) => {
    try {
      setExportLoading(row.id);
      const response = await exportObjects({
        object_type: 'namespace',
        object_ids: [row.id],
      });
      if (response.yaml_content) {
        downloadYaml(response.yaml_content, `namespace_${row.name}_export`);
        message.success(t('common.exportSuccess'));
      }
    } catch (error: any) {
      message.error(error?.message || t('common.exportFailed'));
    } finally {
      setExportLoading(null);
    }
  };

  const handleTableChange = (pg: any) => {
    const newPagination = {
      current: pg.current || 1,
      pageSize: pg.pageSize || 20,
    };
    setPagination((prev) => ({
      ...prev,
      ...newPagination,
    }));
    fetchNamespaces(undefined, newPagination);
  };

  const columns = [
    { title: t('namespace.name'), dataIndex: 'name', key: 'name', width: 150 },
    {
      title: t('namespace.account'),
      dataIndex: 'account',
      key: 'account',
      width: 150,
    },
    {
      title: t('namespace.domain'),
      dataIndex: 'domain',
      key: 'domain',
      width: 150,
    },
    {
      title: t('namespace.title'),
      dataIndex: 'namespace',
      key: 'namespace',
      width: 150,
    },
    {
      title: t('namespace.tls'),
      dataIndex: 'enable_tls',
      key: 'enable_tls',
      width: 80,
      render: (enable_tls: boolean) => (
        <Tag color={enable_tls ? 'green' : 'default'}>
          {enable_tls ? t('namespace.tlsEnabled') : t('namespace.tlsDisabled')}
        </Tag>
      ),
    },
    {
      title: t('namespace.describe'),
      dataIndex: 'desc',
      key: 'desc',
      width: 200,
    },
    {
      title: t('namespace.createdTime'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (text: string) => (text ? convertToLocalizedTime(text) : '-'),
    },
    {
      title: t('common.actions'),
      key: 'operation',
      width: 150,
      fixed: 'right' as const,
      render: (_: any, row: NamespaceItem) => (
        <div className="space-x-4">
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              size="small"
              onClick={() => handleEdit('edit', row)}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['View']}>
            <Button
              type="link"
              size="small"
              loading={exportLoading === row.id}
              onClick={() => handleExport(row)}
            >
              {t('common.export')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Button type="link" size="small" danger onClick={() => handleDelete(row)}>
              {t('common.delete')}
            </Button>
          </PermissionWrapper>
        </div>
      ),
    },
  ];

  return (
    <OpsAnalysisSettingsListShell
      introTitle={t('namespace.introTitle')}
      introDescription={t('namespace.introMsg')}
      searchValue={searchValue}
      searchPlaceholder={t('common.search')}
      onSearchValueChange={setSearchValue}
      onSearch={(value) => handleFilter(value)}
      onSearchClear={() => handleFilter('')}
      actions={(
        <Space>
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button
              icon={<UploadOutlined />}
              onClick={() => setImportModalVisible(true)}
            >
              {t('common.import')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => handleEdit('add')}
            >
              {t('common.new')}
            </Button>
          </PermissionWrapper>
        </Space>
      )}
      columns={columns}
      dataSource={filteredList}
      rowKey="id"
      pagination={pagination}
      tableLoading={loading}
      scroll={{ y: 'calc(100vh - 430px)' }}
      tableProps={{ onChange: handleTableChange }}
      modal={(
        <>
          <OperateModal
            open={modalVisible}
            currentRow={currentRow}
            onClose={() => setModalVisible(false)}
            onSuccess={() => {
              setModalVisible(false);
              void refreshNamespaces();
              fetchNamespaces();
            }}
          />
          <ImportModal
            visible={importModalVisible}
            onCancel={() => setImportModalVisible(false)}
            targetDirectoryId={null}
            onSuccess={() => {
              fetchNamespaces();
            }}
          />
        </>
      )}
    />
  );
};

export default Namespace;
