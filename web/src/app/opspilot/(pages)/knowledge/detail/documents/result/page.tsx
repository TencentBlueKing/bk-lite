'use client';
import React, { useState, useEffect, useRef } from 'react';
import { Card, Input, Spin, Pagination, Drawer, Button, Checkbox, Tag, Tooltip, message } from 'antd';
import { MessageOutlined, DeleteOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';
import ChunkDetail from '@/app/opspilot/components/chunk-detail';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import OperateModal from '@/components/operate-modal';
import GenerateQAPairModal from '@/app/opspilot/components/knowledge/generateQAPairModal';

interface Paragraph {
  id: string;
  content: string;
  chunk_id?: string;
  index_name?: string;
  qa_count?: number;
  document_id?: string;
}

interface ModalRef {
  showModal: (config: {
    documentId: string;
    selectedChunkIds: string[];
    selectedChunks?: ChunkItem[];
  }) => void;
}

interface ChunkItem {
  id: string;
  content: string;
}

const DocsResultPage: React.FC = () => {
  const { t } = useTranslation();
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [paragraphsState, setParagraphsState] = useState<Paragraph[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(20);
  const [totalItems, setTotalItems] = useState<number>(0);
  const [selectedItems, setSelectedItems] = useState<string[]>([]);

  const [drawerVisible, setDrawerVisible] = useState<boolean>(false);
  const [selectedChunk, setSelectedChunk] = useState<Paragraph | null>(null);
  const [deleteModalVisible, setDeleteModalVisible] = useState<boolean>(false);
  const [deleteMode, setDeleteMode] = useState<'single' | 'batch'>('single');
  const [currentDeleteItem, setCurrentDeleteItem] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState<boolean>(false);

  const generateQAModalRef = useRef<ModalRef>(null);

  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('documentId') : null;
  const knowledgeBaseId = searchParams ? searchParams.get('id') : null;
  const { fetchDocumentDetails, deleteChunks } = useKnowledgeApi();

  const tagColors = ['lime', 'green', 'blue', 'geekblue', 'purple'];
  
  const getRandomColor = () => {
    return tagColors[Math.floor(Math.random() * tagColors.length)];
  };

  const fetchData = async (page: number, pageSize: number, searchValue?: string) => {
    if (id) {
      setLoading(true);
      try {
        const { count, items } = await fetchDocumentDetails(id, page, pageSize, searchValue || '');
        setParagraphsState(items);
        setTotalItems(count);
      } catch (error) {
        console.error(`${t('common.errorFetch')}: ${error}`);
      } finally {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    fetchData(currentPage, pageSize, searchTerm);
  }, [id]);

  const handleSearch = (value: string) => {
    setSearchTerm(value);
    setCurrentPage(1);
    fetchData(1, pageSize, value);
  };

  const handlePageChange = (page: number, pageSize?: number) => {
    setCurrentPage(page);
    if (pageSize) {
      setPageSize(pageSize);
    }
    fetchData(page, pageSize || 20, searchTerm);
  };

  const handleContentClick = (paragraph: Paragraph) => {
    setSelectedChunk(paragraph);
    setDrawerVisible(true);
  };

  const handleDrawerClose = () => {
    setDrawerVisible(false);
    setSelectedChunk(null);
  };

  const handleCheckboxChange = (paragraphId: string, checked: boolean) => {
    if (checked) {
      setSelectedItems(prev => [...prev, paragraphId]);
    } else {
      setSelectedItems(prev => prev.filter(id => id !== paragraphId));
    }
  };

  const handleDelete = (items: string[] | string, isBatch: boolean = false) => {
    const itemsArray = Array.isArray(items) ? items : [items];
    
    setDeleteMode(isBatch ? 'batch' : 'single');
    setCurrentDeleteItem(isBatch ? null : itemsArray[0]);
    setDeleteModalVisible(true);
  };

  const handleDeleteConfirm = async (deleteAll: boolean) => {
    setDeleteLoading(true);
    try {
      const itemsToDelete = deleteMode === 'batch' ? selectedItems : [currentDeleteItem!];
      
      await deleteChunks({
        knowledge_base_id: Number(knowledgeBaseId),
        ids: itemsToDelete,
        delete_all: deleteAll
      });

      if (deleteMode === 'batch') {
        setSelectedItems([]);
      }
      fetchData(currentPage, pageSize, searchTerm);
      setDeleteModalVisible(false);
      
      message.success(t('knowledge.documents.result.deleteSuccess'));
    } catch (error) {
      console.error('删除失败:', error);
      message.error(t('knowledge.documents.result.deleteFailed'));
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleBatchGenerateQA = () => {
    if (!id || selectedItems.length === 0) {
      message.warning('请先选择要生成问答对的分块');
      return;
    }

    const selectedChunks = paragraphsState
      .filter(paragraph => selectedItems.includes(paragraph.id))
      .map(paragraph => ({
        id: paragraph.id,
        content: paragraph.content
      }));

    generateQAModalRef.current?.showModal({
      documentId: id,
      selectedChunkIds: selectedItems,
      selectedChunks: selectedChunks
    });
  };

  const handleGenerateQA = (paragraph: Paragraph, event: React.MouseEvent) => {
    event.stopPropagation();
    
    if (!id) {
      message.error('知识库ID不存在');
      return;
    }

    generateQAModalRef.current?.showModal({
      documentId: id,
      selectedChunkIds: [paragraph.id],
      selectedChunks: [{
        id: paragraph.id,
        content: paragraph.content
      }]
    });
  };

  const handleGenerateQASuccess = () => {
    message.success(t('knowledge.qaPairs.generateSuccess'));
    fetchData(currentPage, pageSize, searchTerm);
    setSelectedItems([]);
  };

  const handleBatchDelete = () => {
    handleDelete(selectedItems, true);
  };

  const handleDeleteChunk = (paragraph: Paragraph, event: React.MouseEvent) => {
    event.stopPropagation();
    handleDelete(paragraph.id, false);
  };

  return (
    <div className="w-full h-full">
      <div className="flex justify-between items-center mb-4">
        <div className="flex items-center gap-2">
          <Checkbox
            indeterminate={selectedItems.length > 0 && selectedItems.length < paragraphsState.length}
            checked={selectedItems.length === paragraphsState.length && paragraphsState.length > 0}
            onChange={(e) => {
              if (e.target.checked) {
                setSelectedItems(paragraphsState.map(item => item.id));
              } else {
                setSelectedItems([]);
              }
            }}
          >
            {t('common.selectAll')}
          </Checkbox>
          <span className="text-gray-500">
            {t('common.selected')}: {selectedItems.length} {t('common.items')}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button 
            type="primary" 
            icon={<MessageOutlined />}
            disabled={selectedItems.length === 0}
            onClick={handleBatchGenerateQA}
          >
            {t('knowledge.documents.result.batchGenerateQA')}
          </Button>
          <Button 
            danger
            icon={<DeleteOutlined />}
            disabled={selectedItems.length === 0}
            onClick={handleBatchDelete}
          >
            {t('common.batchDelete')}
          </Button>
          <Input.Search
            placeholder={`${t('common.search')}...`}
            allowClear
            enterButton
            size="middle"
            onSearch={handleSearch}
            style={{ width: '240px' }}
          />
        </div>
      </div>
      
      {loading ? (
        <div className="flex justify-center items-center w-full h-full">
          <Spin size="large" />
        </div>
      ) : (
        <>
          <div className={styles.resultWrap}>
            <div className='grid grid-cols-4 gap-4'>
              {paragraphsState.map((paragraph, index) => (
                <div key={paragraph.id} className="cursor-pointer relative" onClick={() => handleContentClick(paragraph)}>
                  <Card
                    size="small"
                    className={`rounded-lg ${styles.resultCard} ${selectedItems.includes(paragraph.id) ? styles.selectedCard : ''}`}
                    title={
                      <div className="flex justify-between items-center">
                        <div className="flex items-center gap-2">
                          <Checkbox
                            checked={selectedItems.includes(paragraph.id)}
                            onChange={(e) => {
                              e.stopPropagation();
                              handleCheckboxChange(paragraph.id, e.target.checked);
                            }}
                            onClick={(e) => e.stopPropagation()}
                          />
                          <span className={`text-xs ${styles.number}`}>
                            #{(index + 1).toString().padStart(3, '0')}
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Tooltip title={t('knowledge.documents.result.generateQA')}>
                            <Button
                              type="text"
                              size="small"
                              icon={<MessageOutlined />}
                              onClick={(e) => handleGenerateQA(paragraph, e)}
                              className="p-1 w-6 h-6 flex items-center justify-center"
                            />
                          </Tooltip>
                          <Tooltip title={t('common.delete')}>
                            <Button
                              type="text"
                              size="small"
                              icon={<DeleteOutlined />}
                              onClick={(e) => handleDeleteChunk(paragraph, e)}
                              className="p-1 w-6 h-6 flex items-center justify-center text-red-500 hover:text-red-600"
                            />
                          </Tooltip>
                        </div>
                      </div>
                    }
                  >
                    <div className="flex flex-col h-full relative">
                      <p className={styles.truncateLines}>
                        {paragraph.content || '--'}
                      </p>
                      <div className="absolute bottom-0 right-0 flex gap-1">
                        <Tag color={getRandomColor()} className="font-mini">
                          {paragraph.content ? `${paragraph.content.length} chars` : '0 chars'}
                        </Tag>
                        <Tag color={getRandomColor()} className="font-mini">
                          {paragraph.qa_count || 0} Q&A
                        </Tag>
                      </div>
                    </div>
                  </Card>
                </div>
              ))}
            </div>
          </div>
          <div className="flex justify-end mt-4">
            <Pagination
              current={currentPage}
              pageSize={pageSize}
              total={totalItems}
              onChange={handlePageChange}
              showSizeChanger
              pageSizeOptions={['10', '20', '50', '100']}
            />
          </div>
        </>
      )}
      
      <Drawer
        title={t('knowledge.chunkDetail')}
        placement="right"
        size="large"
        open={drawerVisible}
        onClose={handleDrawerClose}
        className="[&_.ant-drawer-body]:p-0"
      >
        {selectedChunk && (
          <ChunkDetail
            chunkContent={selectedChunk.content}
            chunkId={selectedChunk.id}
            knowledgeBaseId={knowledgeBaseId ? Number(knowledgeBaseId) : undefined}
            indexName={selectedChunk.index_name}
            visible={drawerVisible}
          />
        )}
      </Drawer>

      <OperateModal
        title={t('knowledge.documents.result.deleteOptions')}
        visible={deleteModalVisible}
        onCancel={() => setDeleteModalVisible(false)}
        footer={[
          <Button key="cancel" onClick={() => setDeleteModalVisible(false)} disabled={deleteLoading}>
            {t('common.cancel')}
          </Button>,
          <Button 
            key="deleteChunkOnly" 
            type="primary"
            loading={deleteLoading}
            onClick={() => handleDeleteConfirm(false)}
          >
            {t('knowledge.documents.result.deleteChunkOnly')}
          </Button>,
          <Button 
            key="deleteAll" 
            type="primary" 
            danger
            loading={deleteLoading}
            onClick={() => handleDeleteConfirm(true)}
          >
            {t('knowledge.documents.result.deleteWithQA')}
          </Button>
        ]}
      >
        <div className="flex items-start gap-3">
          <ExclamationCircleOutlined className="text-orange-500 text-lg mt-1" />
          <div>
            <p className="mb-2">{t('knowledge.documents.result.selectDeleteMethod')}</p>
            <div className="space-y-2 text-sm text-gray-600">
              <div>• <strong>{t('knowledge.documents.result.deleteChunkOnly')}</strong>：{t('knowledge.documents.result.deleteChunkOnlyDesc')}</div>
              <div>• <strong>{t('knowledge.documents.result.deleteWithQA')}</strong>：{t('knowledge.documents.result.deleteWithQADesc')}</div>
            </div>
          </div>
        </div>
      </OperateModal>

      {/* 生成问答对弹窗 */}
      <GenerateQAPairModal
        ref={generateQAModalRef}
        onSuccess={handleGenerateQASuccess}
      />
    </div>
  );
};

export default DocsResultPage;
