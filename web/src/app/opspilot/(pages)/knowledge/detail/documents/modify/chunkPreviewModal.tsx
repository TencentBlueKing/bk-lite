import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { Drawer, Button, Input, message, Tag } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import CustomTable from '@/components/custom-table';

interface ChunkPreviewModalProps {
  visible: boolean;
  onClose: () => void;
  selectedDocuments: string[];
  getSelectedDocumentInfo: (docKey: string) => { title: string; type: string } | null;
  getDocumentTypeLabel: (type: string) => string;
  onConfirm: (selectedChunks: string[], chunksData: Array<{chunk_id: string; content: string; knowledge_id: string}>) => void;
  initialSelectedChunks?: string[];
}

const ChunkPreviewModal: React.FC<ChunkPreviewModalProps> = ({
  visible,
  onClose,
  selectedDocuments,
  getSelectedDocumentInfo,
  getDocumentTypeLabel,
  onConfirm,
  initialSelectedChunks = []
}) => {
  const { t } = useTranslation();
  const { fetchDocumentDetails } = useKnowledgeApi();

  const [selectedPreviewDoc, setSelectedPreviewDoc] = useState<string>('');
  const [documentChunks, setDocumentChunks] = useState<{[key: string]: any[]}>({});
  const [selectedChunks, setSelectedChunks] = useState<string[]>(initialSelectedChunks);
  const [chunksLoading, setChunksLoading] = useState<boolean>(false);
  const [chunkSearchTerm, setChunkSearchTerm] = useState<string>('');
  const [chunkPage, setChunkPage] = useState<number>(1);
  const [chunkPageSize, setChunkPageSize] = useState<number>(20);
  const [chunkTotalCount, setChunkTotalCount] = useState<number>(0);

  // 同步 initialSelectedChunks 变化到内部 state
  useEffect(() => {
    setSelectedChunks(initialSelectedChunks);
  }, [initialSelectedChunks]);

  useEffect(() => {
    if (visible && selectedDocuments.length > 0 && !selectedPreviewDoc) {
      const firstDoc = selectedDocuments[0];
      setSelectedPreviewDoc(firstDoc);
      fetchChunksForDocument(firstDoc);
    }
  }, [visible, selectedDocuments]);

  const fetchChunksForDocument = useCallback(async (docId: string, page = 1, pageSize = 20, search = '') => {
    if (!docId) return;
    
    setChunksLoading(true);
    try {
      const result = await fetchDocumentDetails(docId, page, pageSize, search);
      
      setDocumentChunks(prev => ({
        ...prev,
        [docId]: result.items || []
      }));
      setChunkTotalCount(result.count || 0);
    } catch (error) {
      message.error(t('common.fetchFailed'));
      console.error('Fetch chunks error:', error);
    } finally {
      setChunksLoading(false);
    }
  }, []);

  const handlePreviewDocChange = useCallback((docId: string) => {
    setSelectedPreviewDoc(docId);
    setChunkPage(1);
    setChunkSearchTerm('');
    fetchChunksForDocument(docId, 1, chunkPageSize, '');
  }, [chunkPageSize]);

  const handleChunkSelect = useCallback((keys: React.Key[]) => {
    setSelectedChunks(keys.map(key => key.toString()));
  }, []);

  const handleChunkSearch = useCallback((value: string) => {
    setChunkSearchTerm(value);
    setChunkPage(1);
    fetchChunksForDocument(selectedPreviewDoc, 1, chunkPageSize, value);
  }, [selectedPreviewDoc, chunkPageSize]);

  const handleChunkPaginationChange = useCallback((page: number, size: number) => {
    setChunkPage(page);
    if (size !== chunkPageSize) {
      setChunkPageSize(size);
      setChunkPage(1);
      fetchChunksForDocument(selectedPreviewDoc, 1, size, chunkSearchTerm);
    } else {
      fetchChunksForDocument(selectedPreviewDoc, page, size, chunkSearchTerm);
    }
  }, [selectedPreviewDoc, chunkPageSize, chunkSearchTerm]);

  const totalSelectedChunks = useMemo(() => {
    return selectedChunks.length;
  }, [selectedChunks]);

  const handleConfirm = () => {
    // 构建选中的chunks完整数据
    const chunksData: Array<{chunk_id: string; content: string; knowledge_id: string}> = [];
    
    selectedChunks.forEach(chunkId => {
      // 从所有文档的chunks中查找
      for (const docId in documentChunks) {
        const chunk = documentChunks[docId].find((c: any) => (c.id || c.chunk_id) === chunkId);
        if (chunk) {
          chunksData.push({
            chunk_id: chunkId,
            content: chunk.content || '',
            knowledge_id: docId
          });
          break;
        }
      }
    });
    
    onConfirm(selectedChunks, chunksData);
    onClose();
  };

  const handleClose = () => {
    setSelectedPreviewDoc('');
    setChunkSearchTerm('');
    setChunkPage(1);
    onClose();
  };

  return (
    <Drawer
      title={`${t('knowledge.qaPairs.preview')} - ${t('knowledge.qaPairs.selectedChunks')}`}
      placement="right"
      width={1000}
      onClose={handleClose}
      open={visible}
      footer={
        <div className="flex justify-end space-x-2">
          <Button onClick={handleClose}>
            {t('common.cancel')}
          </Button>
          <Button 
            type="primary" 
            onClick={handleConfirm}
          >
            {t('common.confirm')} ({totalSelectedChunks})
          </Button>
        </div>
      }
    >
      <div className="flex gap-4 h-full">
        <div className="w-1/4 border rounded-lg p-4">
          <h4 className="text-sm font-medium mb-3">{t('knowledge.qaPairs.selectedDocuments')}</h4>
          <div className="space-y-2">
            {selectedDocuments.map(docKey => {
              const docInfo = getSelectedDocumentInfo(docKey);
              const isActive = selectedPreviewDoc === docKey;
              return (
                <div
                  key={docKey}
                  className={`relative p-4 rounded-lg cursor-pointer transition-all ${
                    isActive
                      ? 'bg-blue-50/50 border border-blue-200 shadow-sm'
                      : 'bg-white hover:bg-gray-50 border border-gray-200 hover:border-blue-200'
                  }`}
                  onClick={() => handlePreviewDocChange(docKey)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900 truncate mb-2" title={docInfo?.title}>
                        {docInfo?.title || `${t('knowledge.qaPairs.documentPrefix')}${docKey}`}
                      </div>
                      <Tag 
                        color={isActive ? 'blue' : 'default'} 
                        className="m-0 px-1.5 py-0 text-[10px] leading-4 rounded"
                      >
                        {getDocumentTypeLabel(docInfo?.type || 'file')}
                      </Tag>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="flex-1 border rounded-lg p-4">
          <div className="mb-3 flex items-center justify-between">
            <h4 className="text-sm font-medium m-0">{t('knowledge.chunkDetail')}</h4>
            <Input.Search
              placeholder={t('common.search')}
              onSearch={handleChunkSearch}
              style={{ width: 200 }}
              allowClear
            />
          </div>
          
          <CustomTable
            size="small"
            columns={[
              {
                title: t('knowledge.chunkDetail'),
                dataIndex: 'content',
                key: 'content',
                render: (text: string) => (
                  <div className="text-sm max-w-2xl">
                    <p className="line-clamp-3 m-0">{text || '--'}</p>
                  </div>
                ),
              },
            ]}
            dataSource={(documentChunks[selectedPreviewDoc] || []).map(chunk => ({
              ...chunk,
              key: chunk.id || chunk.chunk_id,
            }))}
            rowSelection={{
              type: 'checkbox',
              selectedRowKeys: selectedChunks,
              onChange: handleChunkSelect,
              preserveSelectedRowKeys: true,
            }}
            pagination={{
              current: chunkPage,
              total: chunkTotalCount,
              pageSize: chunkPageSize,
              showSizeChanger: true,
              onChange: handleChunkPaginationChange,
            }}
            loading={chunksLoading}
            scroll={{ y: 'calc(80vh - 150px)' }}
          />
        </div>
      </div>
    </Drawer>
  );
};

export default ChunkPreviewModal;
