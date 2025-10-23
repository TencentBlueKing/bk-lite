'use client';
import React, { useState, useEffect } from 'react';
import { Card, Input, Spin, Pagination, Divider, Button, message, Tag } from 'antd';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import Icon from '@/components/icon';
import QAEditDrawer from '@/app/opspilot/components/knowledge/qaEditDrawer';
import QADetailDrawer from '@/app/opspilot/components/knowledge/qaDetailDrawer';
import { PlusOutlined } from '@ant-design/icons';

interface QAPair {
  id: string;
  question: string;
  answer: string;
  base_chunk_id: string;
}

interface CreateQAData {
  question: string;
  answer: string;
}

const QAPairResultPage: React.FC = () => {
  const { t } = useTranslation();
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [qaPairsState, setQaPairsState] = useState<QAPair[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(20);
  const [totalItems, setTotalItems] = useState<number>(0);
  const [editDrawerVisible, setEditDrawerVisible] = useState<boolean>(false);
  const [detailDrawerVisible, setDetailDrawerVisible] = useState<boolean>(false);
  const [selectedQAPair, setSelectedQAPair] = useState<QAPair | null>(null);
  const [submitLoading, setSubmitLoading] = useState<boolean>(false);
  const [generateAnswerLoading, setGenerateAnswerLoading] = useState<boolean>(false);
  
  const searchParams = useSearchParams();
  const qaPairId = searchParams ? searchParams.get('qaPairId') : null;
  const knowledgeId = searchParams ? searchParams.get('id') : null;
  const documentId = searchParams ? searchParams.get('documentId') : null;
  
  const { fetchQAPairDetails, createOneQAPair, updateQAPair, deleteOneQAPair, generateAnswerToEs } = useKnowledgeApi();

  const fetchData = async (page: number, pageSize: number, searchValue?: string) => {
    if (qaPairId) {
      setLoading(true);
      try {
        const params = {
          qa_pair_id: parseInt(qaPairId, 10),
          page,
          page_size: pageSize,
          search_text: searchValue || ''
        };
        const data = await fetchQAPairDetails(params);
        setQaPairsState(data.items || []);
        setTotalItems(data.count || 0);
      } catch (error) {
        console.error(`${t('common.errorFetch')}: ${error}`);
      } finally {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    fetchData(currentPage, pageSize, searchTerm);
  }, [qaPairId, currentPage, pageSize, searchTerm]);

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

  const handleCardClick = (qaPair: QAPair) => {
    setSelectedQAPair(qaPair);
    setDetailDrawerVisible(true);
  };

  const handleAddQAClick = () => {
    setEditDrawerVisible(true);
  };

  const handleSubmitQA = async (values: CreateQAData) => {
    if (!qaPairId || !knowledgeId) {
      console.error('Missing required parameters: qaPairId or knowledgeId');
      return;
    }

    setSubmitLoading(true);
    try {
      await createOneQAPair({
        qa_pairs_id: parseInt(qaPairId, 10),
        knowledge_id: parseInt(knowledgeId, 10),
        question: values.question,
        answer: values.answer
      });
      
      fetchData(currentPage, pageSize, searchTerm);
      setEditDrawerVisible(false);
      message.success(t('common.addSuccess'));
    } catch (error) {
      console.error('Failed to create QA pair:', error);
      message.error(t('common.addFailed'));
    } finally {
      setSubmitLoading(false);
    }
  };

  const handleUpdateQA = async (updatedQA: {
    id: string;
    question: string;
    answer: string;
  }) => {
    if (!qaPairId) {
      console.error('Missing required parameter: qaPairId');
      return;
    }

    try {
      await updateQAPair({
        qa_pairs_id: parseInt(qaPairId, 10),
        id: updatedQA.id,
        question: updatedQA.question,
        answer: updatedQA.answer
      });
      
      setQaPairsState(prev => prev.map(item => 
        item.id === updatedQA.id ? { ...item, ...updatedQA } : item
      ));
      
      const updatedFullQA = qaPairsState.find(item => item.id === updatedQA.id);
      if (updatedFullQA) {
        setSelectedQAPair({ ...updatedFullQA, ...updatedQA });
      }
    } catch (error) {
      console.error('Failed to update QA pair:', error);
      throw error;
    }
  };

  const handleDeleteQA = async (id: string) => {
    if (!qaPairId) {
      console.error('Missing required parameter: qaPairId');
      return;
    }

    try {
      await deleteOneQAPair({
        qa_pairs_id: parseInt(qaPairId, 10),
        id: id
      });
      
      setQaPairsState(prev => prev.filter(item => item.id !== id));
      setTotalItems(prev => Math.max(0, prev - 1));
    } catch (error) {
      console.error('Failed to delete QA pair:', error);
      throw error;
    }
  };

  const handleGenerateAnswer = async () => {
    if (!qaPairId || !knowledgeId) {
      console.error('Missing required parameters: qaPairId or knowledgeId');
      return;
    }

    setGenerateAnswerLoading(true);
    try {
      await generateAnswerToEs({
        qa_pairs_id: parseInt(qaPairId, 10)
      });
      
      fetchData(currentPage, pageSize, searchTerm);
      message.success(t('knowledge.qaPairs.answerGenerateSuccess'));
    } catch (error) {
      console.error('Failed to generate answer:', error);
      message.error(t('knowledge.qaPairs.answerGenerateFailed'));
    } finally {
      setGenerateAnswerLoading(false);
    }
  };

  return (
    <div className="w-full h-full">
      <div className="flex justify-between items-center mb-4">
        <div></div>
        <div className="flex gap-2">
          <Input.Search
            placeholder={`${t('common.search')}...`}
            allowClear
            enterButton
            size="middle"
            onSearch={handleSearch}
            style={{ width: '240px' }}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleAddQAClick}
          >
            {t('common.add')}
          </Button>
          <Button
            type="default"
            loading={generateAnswerLoading}
            onClick={handleGenerateAnswer}
          >
            {t('knowledge.qaPairs.generateAnswer')}
          </Button>
        </div>
      </div>
      
      {loading ? (
        <div className="flex justify-center items-center w-full h-full">
          <Spin size="large" />
        </div>
      ) : (
        <>
          <div className="h-[calc(100%-100px)] overflow-auto">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
              {qaPairsState.map((qaPair) => (
                <div key={qaPair.id}>
                  <Card
                    size="small"
                    className="
                      min-h-[170px] cursor-pointer transition-all duration-200 ease-in-out
                      hover:-translate-y-0.5 hover:shadow-lg bg-[var(--color-fill-2)]
                      [&_.ant-card-body]:h-auto [&_.ant-card-body]:min-h-[130px] [&_.ant-card-body]:p-4
                      relative
                    "
                    onClick={() => handleCardClick(qaPair)}
                    hoverable
                  >
                    <div className="flex flex-col h-full">
                      <div className="flex-1 flex flex-col">
                        <div className="flex-1 rounded-md transition-colors duration-200">
                          <div className="flex items-start gap-2">
                            <Icon type="question-circle-fill" className="text-lg mt-1 flex-shrink-0" />
                            <p className="
                              line-clamp-2 text-ellipsis overflow-hidden
                              leading-6 m-0 text-xs text-[var(--color-text-1)] font-medium
                            ">
                              {qaPair.question || '--'}
                            </p>
                          </div>
                        </div>
                      </div>
                      <Divider className="my-3" />
                      <div className="flex-1 flex flex-col">
                        <div className="flex-1 rounded-md transition-colors duration-200">
                          <div className="flex items-start gap-2">
                            <Icon type="answer" className="text-lg mt-1 flex-shrink-0" />
                            <p className="
                              line-clamp-2 text-ellipsis overflow-hidden
                              leading-6 m-0 text-xs text-[var(--color-text-3)]
                            ">
                              {qaPair.answer || '--'}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                    {qaPair.base_chunk_id && (
                      <Tag 
                        color="blue" 
                        className="absolute bottom-2 right-2 font-mini"
                      >
                        chunk
                      </Tag>
                    )}
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
      
      {/* 详情抽屉 - 支持编辑和删除 */}
      <QADetailDrawer
        visible={detailDrawerVisible}
        qaPair={selectedQAPair}
        knowledgeId={documentId ?? undefined}
        onClose={() => setDetailDrawerVisible(false)}
        onUpdate={handleUpdateQA}
        onDelete={handleDeleteQA}
      />
      
      {/* 添加问答对抽屉 */}
      <QAEditDrawer
        visible={editDrawerVisible}
        onClose={() => setEditDrawerVisible(false)}
        onSubmit={handleSubmitQA}
        showContinueButton
        onSubmitAndContinue={async (values) => {
          await handleSubmitQA(values);
          setEditDrawerVisible(true);
        }}
        loading={submitLoading}
      />
    </div>
  );
};

export default QAPairResultPage;