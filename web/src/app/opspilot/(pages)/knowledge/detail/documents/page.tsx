'use client';

import React, { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Input, Button, Tabs, Tooltip, Radio } from 'antd';
import type { RadioChangeEvent } from 'antd';
import { PlusOutlined, DeleteOutlined, SyncOutlined } from '@ant-design/icons';
import { useAuth } from '@/context/auth';
import { useTranslation } from '@/utils/i18n';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import SelectModal from './selectSourceModal';
import ActionButtons from '@/app/opspilot/components/knowledge/actionButtons';
import KnowledgeGraphPage from '@/app/opspilot/components/knowledge/knowledgeGraphPage';
import { getDocumentColumns, getQAPairColumns } from '@/app/opspilot/components/knowledge/tableColumns';
import { useDocuments } from '@/app/opspilot/context/documentsContext';
import { SOURCE_FILE_OPTIONS, QA_PAIR_OPTIONS } from '@/app/opspilot/constants/knowledge';
import { useDocumentTable, useQAPairTable, useKnowledgeBaseCounts } from './hooks';
import { BatchOperationMenu, QAPairUploadModal } from './components';

const { TabPane } = Tabs;
const { Search } = Input;

const RANDOM_COLORS = ['#ff9214', '#875cff', '#00cba6', '#155aef'];

const DocumentsPage: React.FC = () => {
  const router = useRouter();
  const { t } = useTranslation();
  const authContext = useAuth();
  const { convertToLocalizedTime } = useLocalizedTime();
  const searchParams = useSearchParams();
  
  const id = searchParams?.get('id') ?? null;
  const name = searchParams?.get('name') ?? null;
  const desc = searchParams?.get('desc') ?? null;
  const type = searchParams?.get('type') ?? null;

  const { activeTabKey, setActiveTabKey, mainTabKey, setMainTabKey } = useDocuments();
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isQAPairModalVisible, setIsQAPairModalVisible] = useState(false);

  const { counts, permissions, fetchCounts } = useKnowledgeBaseCounts({ knowledgeBaseId: id });

  const {
    tableData,
    loading,
    pagination,
    selectedRowKeys,
    searchText,
    isTrainLoading,
    singleTrainLoading,
    handleSearch,
    handleTableChange,
    handleDelete,
    handleTrain,
    handleBatchSet,
    fetchData,
    rowSelection,
  } = useDocumentTable({
    knowledgeBaseId: id,
    activeTabKey,
    mainTabKey,
    t,
    onCountsChange: fetchCounts,
  });

  const {
    qaPairData,
    qaPairLoading,
    qaPairPagination,
    selectedQAPairKeys,
    exportLoadingMap,
    uploadModalVisible,
    confirmLoading,
    uploadedFiles,
    uploadingFiles,
    setUploadModalVisible,
    handleQAPairTableChange,
    handleDeleteSingleQAPair,
    handleBatchDeleteQAPairs,
    handleExportQAPair,
    handleImportClick,
    handleUploadModalConfirm,
    handleFileUpload,
    handleRemoveFile,
    handleDownloadTemplate,
    fetchQAPairData,
    qaPairRowSelection,
  } = useQAPairTable({
    knowledgeBaseId: id,
    mainTabKey,
    t,
    onCountsChange: fetchCounts,
  });

  useEffect(() => {
    if (type === 'knowledge_graph') {
      setMainTabKey(type);
      setActiveTabKey(type);
    } else if (['file', 'web_page', 'manual'].includes(type || '')) {
      setMainTabKey('source_files');
      setActiveTabKey(type || 'file');
    } else if (type === 'qa_pairs' || type === 'qa_custom') {
      setMainTabKey('qa_pairs');
      setActiveTabKey('qa_pairs');
    } else {
      setMainTabKey('source_files');
      setActiveTabKey('file');
    }
  }, [type, setActiveTabKey, setMainTabKey]);

  const getRandomColor = () => RANDOM_COLORS[Math.floor(Math.random() * RANDOM_COLORS.length)];

  const handleFile = async (record: { id: string | number; name: string }, actionType: string) => {
    if (actionType === 'preview') {
      window.open(`/opspilot/knowledge/preview?id=${record.id}`);
      return;
    }
    try {
      const response = await fetch(`/opspilot/api/docFile?id=${record.id}`, {
        method: 'GET',
        headers: { Authorization: `Bearer ${authContext?.token}` },
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
  };

  const handleSetClick = (record: { id: string | number }) => {
    router.push(`/opspilot/knowledge/detail/documents/modify?type=${activeTabKey}&id=${id}&name=${name}&desc=${desc}&documentIds=${record.id}`);
  };

  const handleMainTabChange = (key: string) => {
    setMainTabKey(key);
    if (key === 'source_files') {
      setActiveTabKey('file');
    } else if (key === 'qa_pairs') {
      setActiveTabKey('qa_pairs');
    } else if (key === 'knowledge_graph') {
      setActiveTabKey('knowledge_graph');
    }
  };

  const handleSourceFileTypeChange = (e: RadioChangeEvent) => {
    setActiveTabKey(e.target.value);
  };

  const handleAddClick = () => setIsModalVisible(true);
  const handleModalCancel = () => setIsModalVisible(false);
  const handleModalConfirm = (selectedType: string) => {
    setIsModalVisible(false);
    router.push(`/opspilot/knowledge/detail/documents/modify?type=${selectedType}&id=${id}&name=${name}&desc=${desc}`);
  };

  const handleQAPairAddClick = () => setIsQAPairModalVisible(true);
  const handleQAPairModalCancel = () => setIsQAPairModalVisible(false);
  const handleQAPairModalConfirm = (selectedType: string) => {
    setIsQAPairModalVisible(false);
    if (selectedType === 'documents') {
      router.push(`/opspilot/knowledge/detail/documents/modify?type=qa_pairs&id=${id}&name=${name}&desc=${desc}`);
    } else if (selectedType === 'import') {
      handleImportClick();
    } else if (selectedType === 'custom') {
      router.push(`/opspilot/knowledge/detail/documents/modify?type=qa_custom&id=${id}&name=${name}&desc=${desc}`);
    }
  };

  const handleRefresh = () => {
    if (mainTabKey === 'qa_pairs') {
      fetchQAPairData(searchText);
    } else if (mainTabKey === 'source_files') {
      fetchData(searchText);
    }
  };

  const handleBatchSetClick = (keys: React.Key[]) => {
    const url = handleBatchSet(keys, { id, name, desc });
    router.push(url);
  };

  const columns = getDocumentColumns(
    t,
    activeTabKey,
    convertToLocalizedTime,
    getRandomColor,
    permissions,
    singleTrainLoading,
    handleTrain,
    handleDelete,
    handleSetClick,
    handleFile,
    router,
    id,
    name,
    desc,
    ActionButtons
  );

  const qaPairColumns = getQAPairColumns(
    t,
    convertToLocalizedTime,
    getRandomColor,
    permissions,
    handleDeleteSingleQAPair,
    handleExportQAPair,
    router,
    id,
    name,
    desc,
    exportLoadingMap
  );

  return (
    <div style={{ marginTop: '-10px' }}>
      <Tabs activeKey={mainTabKey} onChange={handleMainTabChange}>
        <TabPane tab={`${t('knowledge.sourceFiles')} (${counts.document_count})`} key='source_files' />
        <TabPane tab={`${t('knowledge.qaPairs.title')} (${counts.qa_count})`} key='qa_pairs' />
        <TabPane tab={`${t('knowledge.knowledgeGraph.title')} (${counts.graph_count})`} key='knowledge_graph' />
      </Tabs>
      
      <div className='nav-box flex justify-between mb-[20px]'>
        <div className='left-side'>
          {mainTabKey === 'source_files' && (
            <Radio.Group value={activeTabKey} onChange={handleSourceFileTypeChange}>
              <Radio.Button value="file">{t('knowledge.localFile')} ({counts.file_count})</Radio.Button>
              <Radio.Button value="web_page">{t('knowledge.webLink')} ({counts.web_page_count})</Radio.Button>
              <Radio.Button value="manual">{t('knowledge.cusText')} ({counts.manual_count})</Radio.Button>
            </Radio.Group>
          )}
        </div>
        
        <div className='right-side flex items-center'>
          {mainTabKey !== 'knowledge_graph' && (
            <>
              <Search
                placeholder={`${t('common.search')}...`}
                allowClear
                onSearch={handleSearch}
                enterButton
                className="w-60 mr-[8px]"
              />
              <Tooltip className='mr-[8px]' title={t('common.refresh')}>
                <Button icon={<SyncOutlined />} onClick={handleRefresh} />
              </Tooltip>
              
              {activeTabKey !== 'qa_pairs' && (
                <>
                  <PermissionWrapper requiredPermissions={['Add']} instPermissions={permissions}>
                    <Button
                      type='primary'
                      className='mr-[8px]'
                      icon={<PlusOutlined />}
                      onClick={handleAddClick}
                    >
                      {t('common.add')}
                    </Button>
                  </PermissionWrapper>
                  <BatchOperationMenu
                    selectedRowKeys={selectedRowKeys}
                    permissions={permissions}
                    isTrainLoading={isTrainLoading}
                    onTrain={handleTrain}
                    onDelete={handleDelete}
                    onBatchSet={handleBatchSetClick}
                    t={t}
                  />
                </>
              )}
              
              {activeTabKey === 'qa_pairs' && (
                <>
                  <PermissionWrapper requiredPermissions={['Add']} instPermissions={permissions}>
                    <Button
                      type='primary'
                      className='mr-[8px]'
                      icon={<PlusOutlined />}
                      onClick={handleQAPairAddClick}
                    >
                      {t('common.add')}
                    </Button>
                  </PermissionWrapper>
                  <PermissionWrapper requiredPermissions={['Delete']} instPermissions={permissions}>
                    <Button
                      danger
                      icon={<DeleteOutlined />}
                      onClick={handleBatchDeleteQAPairs}
                    >
                      {t('common.batchDelete')}{selectedQAPairKeys.length > 0 && ` (${selectedQAPairKeys.length})`}
                    </Button>
                  </PermissionWrapper>
                </>
              )}
            </>
          )}
        </div>
      </div>

      {activeTabKey === 'knowledge_graph' ? (
        <KnowledgeGraphPage 
          knowledgeBaseId={id} 
          name={name}
          desc={desc}
          type={activeTabKey}
        />
      ) : activeTabKey === 'qa_pairs' ? (
        <CustomTable
          rowKey="id"
          rowSelection={qaPairRowSelection}
          scroll={{ y: 'calc(100vh - 430px)' }}
          columns={qaPairColumns}
          dataSource={qaPairData}
          pagination={{
            ...qaPairPagination,
            onChange: handleQAPairTableChange
          }}
          loading={qaPairLoading}
        />
      ) : (
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
      )}

      {mainTabKey === 'source_files' && (
        <SelectModal
          defaultSelected={activeTabKey}
          visible={isModalVisible}
          onCancel={handleModalCancel}
          onConfirm={handleModalConfirm}
          title={`${t('common.select')}${t('knowledge.source')}`}
          options={SOURCE_FILE_OPTIONS}
        />
      )}
      
      {mainTabKey === 'qa_pairs' && (
        <SelectModal
          visible={isQAPairModalVisible}
          onCancel={handleQAPairModalCancel}
          onConfirm={handleQAPairModalConfirm}
          title={`${t('common.select')}${t('knowledge.qaPairs.addMethod')}`}
          options={QA_PAIR_OPTIONS}
        />
      )}

      <QAPairUploadModal
        visible={uploadModalVisible}
        confirmLoading={confirmLoading}
        uploadedFiles={uploadedFiles}
        uploadingFiles={uploadingFiles}
        onOk={handleUploadModalConfirm}
        onCancel={() => setUploadModalVisible(false)}
        onFileUpload={handleFileUpload}
        onRemoveFile={handleRemoveFile}
        onDownloadTemplate={handleDownloadTemplate}
        t={t}
      />
    </div>
  );
};

export default DocumentsPage;
