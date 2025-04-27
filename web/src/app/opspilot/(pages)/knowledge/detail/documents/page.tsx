'use client';
import React, { useState, useEffect, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Input, Button, Modal, message, Tag, Tabs, Tooltip, Dropdown, Menu, Space } from 'antd';
import { PlusOutlined, DeleteOutlined, TrademarkOutlined, SyncOutlined, DownOutlined } from '@ant-design/icons';
import { useAuth } from '@/context/auth';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import type { TableColumnsType, PaginationProps } from 'antd';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import SelectSourceModal from './selectSourceModal';
import { TableData } from '@/app/opspilot/types/knowledge'
import styles from '@/app/opspilot/styles/common.module.scss'
import ActionButtons from '@/app/opspilot/components/knowledge/actionButtons';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';

const { confirm } = Modal;
const { TabPane } = Tabs;
const { Search } = Input;

const DocumentsPage: React.FC = () => {
  const router = useRouter();
  const { t } = useTranslation();
  const authContext = useAuth();
  const { convertToLocalizedTime } = useLocalizedTime();
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;
  const name = searchParams ? searchParams.get('name') : null;
  const desc = searchParams ? searchParams.get('desc') : null;
  const type = searchParams ? searchParams.get('type') : null;
  const [activeTabKey, setActiveTabKey] = useState<string>(type || 'file');
  const [searchText, setSearchText] = useState<string>('');
  const [pagination, setPagination] = useState<PaginationProps>({
    current: 1,
    total: 0,
    pageSize: 20,
  });
  const [loading, setLoading] = useState<boolean>(false);
  const [tableData, setTableData] = useState<TableData[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isTrainLoading, setIsTrainLoading] = useState(false);
  const [singleTrainLoading, setSingleTrainLoading] = useState<{ [key: string]: boolean }>({});

  const { fetchDocuments, batchDeleteDocuments, batchTrainDocuments } = useKnowledgeApi();

  const randomColors = ['#ff9214', '#875cff', '#00cba6', '#155aef'];

  const getRandomColor = () => randomColors[Math.floor(Math.random() * randomColors.length)];

  const columns: TableColumnsType<TableData> = [
    {
      title: t('knowledge.documents.name'),
      dataIndex: 'name',
      key: 'name',
      render: (text, record) => (
        <a
          href="#"
          style={{ color: '#155aef' }}
          onClick={() => router.push(`/opspilot/knowledge/detail/documents/result?id=${id}&name=${name}&desc=${desc}&knowledgeId=${record.id}`)}
        >
          {text}
        </a>
      ),
    },
    {
      title: t('knowledge.documents.chunkSize'),
      dataIndex: 'chunk_size',
      key: 'chunk_size',
    },
    {
      title: t('knowledge.documents.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      render: (text) => convertToLocalizedTime(text),
    },
    {
      title: t('knowledge.documents.createdBy'),
      key: 'created_by',
      dataIndex: 'created_by',
      render: (_, { created_by }) => (
        <div>
          <div
            className='inline-block text-center rounded-full text-white mr-2'
            style={{ width: 20, height: 20, backgroundColor: getRandomColor() }}
          >
            {created_by.charAt(0).toUpperCase()}
          </div>
          {created_by}
        </div>
      ),
    },
    {
      title: t('knowledge.documents.status'),
      key: 'train_status',
      dataIndex: 'train_status',
      render: (_, { train_status, train_status_display }) => {
        const statusColors: { [key: string]: string } = {
          '0': 'orange',
          '1': 'green',
          '2': 'red',
        };

        const color = statusColors[train_status] || 'geekblue';
        const text = train_status_display || '--';

        return <Tag color={color}>{text}</Tag>;
      },
    },
    {
      title: t('knowledge.documents.extractionMethod'),
      key: 'mode',
      dataIndex: 'mode',
      render: (_, { mode }) => {
        const modeMap: { [key: string]: string } = {
          'full': t('knowledge.documents.fullTextExtraction'),
          'paragraph': t('knowledge.documents.chapterExtraction'),
          'excel_full_content_parse': t('knowledge.documents.worksheetExtraction'),
          'excel_header_row_parse': t('knowledge.documents.rowExtraction'),
        };
        const text = modeMap[mode] || t('knowledge.documents.fullTextExtraction');
        return <span>{text}</span>;
      },
    },
    {
      title: t('knowledge.documents.chunkingMethod'),
      key: 'chunk_type',
      dataIndex: 'chunk_type',
      render: (_, { chunk_type }) => {
        const chunkMap: { [key: string]: string } = {
          'fixed_size': t('knowledge.documents.fixedChunk'),
          'recursive': t('knowledge.documents.overlapChunk'),
          'semantic': t('knowledge.documents.semanticChunk'),
          'full': t('knowledge.documents.noChunk'),
        };
        const text = chunkMap[chunk_type] || t('knowledge.documents.fixedChunk');
        return <span>{text}</span>;
      },
    },
    {
      title: t('knowledge.documents.actions'),
      key: 'action',
      render: (_, record) => (
        <ActionButtons
          record={record}
          isFile={activeTabKey === 'file'}
          singleTrainLoading={singleTrainLoading}
          onTrain={handleTrain}
          onDelete={handleDelete}
          onSet={handleSetClick}
          onFileAction={handleFile}
        />
      ),
    }
  ];

  const handleFile = async (record: TableData, type: string) => {
    if (type === 'preview') {
      window.open(`/opspilot/knowledge/preview?id=${record.id}`);
      return;
    }
    try {
      const response = await fetch(`/opspilot/api/docFile?id=${record.id}`, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${authContext?.token}`,
        },
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Failed to download file');
      }
      const blob = await response.blob();
      const fileUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = fileUrl;
      link.download = record.name;
      link.click();
      window.URL.revokeObjectURL(fileUrl);
    } catch (error) {
      console.error('Error downloading file:', error);
      alert('Failed to download file');
    }
  }

  const handleSetClick = (record: any) => {
    router.push(`/opspilot/knowledge/detail/documents/modify?type=${activeTabKey}&id=${id}&name=${name}&desc=${desc}&documentIds=${record.id}`);
  };

  const handleDelete = (keys: React.Key[]) => {
    confirm({
      title: t('common.delConfirm'),
      content: t('common.delConfirmCxt'),
      centered: true,
      onOk: async () => {
        try {
          await batchDeleteDocuments(keys, id);
          fetchData();
          setSelectedRowKeys([]);
          message.success(t('common.delSuccess'));
        } catch {
          message.error(t('common.delFailed'));
        }
      },
    });
  };

  const handleTrain = async (keys: React.Key[]) => {
    if (keys.length === 1) {
      setSingleTrainLoading((prev) => ({ ...prev, [keys[0].toString()]: true }));
    } else {
      setIsTrainLoading(true);
    }
    try {
      await batchTrainDocuments(keys);
      message.success(t('common.training'));
      fetchData();
    } catch {
      message.error(t('common.trainFailed'));
    } finally {
      if (keys.length === 1) {
        setSingleTrainLoading((prev) => ({ ...prev, [keys[0].toString()]: false }));
      } else {
        setIsTrainLoading(false);
      }
    }
  };

  const handleBatchSet = async (keys: React.Key[]) => {
    router.push(`/opspilot/knowledge/detail/documents/modify?type=${activeTabKey}&id=${id}&name=${name}&desc=${desc}&documentIds=${keys.join(',')}`);
  };

  const handleSearch = (value: string) => {
    setSearchText(value);
    setPagination((prev) => ({
      ...prev,
      current: 1,
    }));
  };

  const handleTableChange = (page: number, pageSize?: number) => {
    setPagination((prev) => ({
      ...prev,
      current: page,
      pageSize: pageSize || prev.pageSize,
    }));
  };

  const fetchData = useCallback(async (text = '') => {
    setLoading(true);
    const { current, pageSize } = pagination;
    const params = {
      name: text,
      page: current,
      page_size: pageSize,
      knowledge_source_type: activeTabKey,
      knowledge_base_id: id
    };
    try {
      const res = await fetchDocuments(params);
      const { items: data } = res;
      setTableData(data);
      setPagination(prev => ({
        ...prev,
        total: res.count,
      }));
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  }, [pagination.current, pagination.pageSize, searchText, activeTabKey]);

  useEffect(() => {
    fetchData(searchText);
  }, [fetchData, id]);

  const rowSelection = {
    selectedRowKeys,
    onChange: (newSelectedRowKeys: React.Key[]) => {
      setSelectedRowKeys(newSelectedRowKeys);
    },
    getCheckboxProps: (record: TableData) => ({
      disabled: record.train_status_display === 'Training',
    }),
  };

  const handleTabChange = (key: string) => {
    setPagination({
      current: 1,
      total: 0,
      pageSize: 20,
    });
    setActiveTabKey(key);
  };

  const handleAddClick = () => {
    setIsModalVisible(true);
  };

  const handleModalCancel = () => {
    setIsModalVisible(false);
  };

  const handleModalConfirm = (selectedType: string) => {
    setIsModalVisible(false);
    router.push(`/opspilot/knowledge/detail/documents/modify?type=${selectedType}&id=${id}&name=${name}&desc=${desc}`);
  };

  const batchOperationMenu = (
    <Menu className={styles.batchOperationMenu}>
      <Menu.Item key="batchTrain">
        <PermissionWrapper requiredPermissions={['Train']}>
          <Button
            type="text"
            className="w-full"
            icon={<TrademarkOutlined />}
            onClick={() => handleTrain(selectedRowKeys)}
            disabled={!selectedRowKeys.length}
            loading={isTrainLoading}
          >
            {t('common.batchTrain')}
          </Button>
        </PermissionWrapper>
      </Menu.Item>
      <Menu.Item key="batchDelete">
        <PermissionWrapper requiredPermissions={['Delete']}>
          <Button
            type="text"
            className="w-full"
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(selectedRowKeys)}
            disabled={!selectedRowKeys.length}
          >
            {t('common.batchDelete')}
          </Button>
        </PermissionWrapper>
      </Menu.Item>
      <Menu.Item key="batchSet">
        <PermissionWrapper requiredPermissions={['Set']}>
          <Button
            type="text"
            className="w-full"
            icon={<TrademarkOutlined />}
            onClick={() => handleBatchSet(selectedRowKeys)}
            disabled={!selectedRowKeys.length}
          >
            {t('knowledge.documents.batchSet')}
          </Button>
        </PermissionWrapper>
      </Menu.Item>
    </Menu>
  );

  return (
    <div style={{marginTop: '-10px'}}>
      <Tabs defaultActiveKey={activeTabKey} onChange={handleTabChange}>
        <TabPane tab={t('knowledge.localFile')} key='file' />
        <TabPane tab={t('knowledge.webLink')} key='web_page' />
        <TabPane tab={t('knowledge.cusText')} key='manual' />
      </Tabs>
      <div className='nav-box flex justify-end mb-[20px]'>
        <div className='left-side w-[240px] mr-[8px]'>
          <Search
            placeholder={`${t('common.search')}...`}
            allowClear
            onSearch={handleSearch}
            enterButton
            className="w-60"
          />
        </div>
        <div className='right-side flex'>
          <Tooltip className='mr-[8px]' title={t('common.refresh')}>
            <Button icon={<SyncOutlined />} onClick={() => fetchData()} /> {/* Adjusted here */}
          </Tooltip>
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button
              type='primary'
              className='mr-[8px]'
              icon={<PlusOutlined />}
              onClick={handleAddClick}
            >
              {t('common.add')}
            </Button>
          </PermissionWrapper>
          <Dropdown overlay={batchOperationMenu}>
            <Button>
              <Space>
                {t('common.batchOperation')}
                <DownOutlined />
              </Space>
            </Button>
          </Dropdown>
        </div>
      </div>
      <CustomTable
        rowKey="id"
        rowSelection={rowSelection}
        scroll={{ y: 'calc(100vh - 430px)' }}
        columns={columns}
        dataSource={tableData}
        pagination={{
          ...pagination,
          onChange: handleTableChange
        }}
        loading={loading}
      />
      <SelectSourceModal
        defaultSelected={activeTabKey}
        visible={isModalVisible}
        onCancel={handleModalCancel}
        onConfirm={handleModalConfirm}
      />
    </div>
  );
};

export default DocumentsPage;
