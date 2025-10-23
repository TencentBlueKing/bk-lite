import React, { useState, useEffect, useCallback } from 'react';
import { Segmented, Card, Spin, Divider, Empty } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import Icon from '@/components/icon';

interface ChunkDetailProps {
  chunkContent: string;
  chunkId?: string;
  knowledgeBaseId?: number;
  indexName?: string;
  visible: boolean;
}

interface QAPair {
  id: string;
  question: string;
  answer: string;
}

const ChunkDetail: React.FC<ChunkDetailProps> = ({
  chunkContent,
  chunkId,
  knowledgeBaseId,
  indexName,
  visible
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<string>('chunk');
  const [qaPairs, setQaPairs] = useState<QAPair[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const { fetchChunkQAPairs } = useKnowledgeApi();

  const fetchQAPairData = useCallback(async () => {
    if (!chunkId || !indexName) {
      console.log('Missing parameters:', { chunkId, indexName });
      setQaPairs([]);
      setLoading(false);
      return;
    }
    
    console.log('Fetching QA pairs with params:', { indexName, chunkId });
    setLoading(true);
    try {
      const data = await fetchChunkQAPairs(indexName, chunkId, knowledgeBaseId);
      setQaPairs(data);
    } catch (error) {
      console.error('获取问答对失败:', error);
      setQaPairs([]);
    } finally {
      setLoading(false);
    }
  }, [chunkId, indexName]);

  useEffect(() => {
    if (visible && activeTab === 'qapairs' && chunkId && indexName) {
      fetchQAPairData();
    }
  }, [visible, activeTab, chunkId, indexName]);

  const segmentedOptions = [
    {
      value: 'chunk',
      label: t('knowledge.chunks'),
    },
    {
      value: 'qapairs',
      label: t('knowledge.qaPairs.title'),
    },
  ];

  const renderContent = () => {
    if (activeTab === 'chunk') {
      return (
        <div className="p-4">
          <div className="whitespace-pre-wrap text-sm leading-6 text-gray-700">
            {chunkContent}
          </div>
        </div>
      );
    }

    if (activeTab === 'qapairs') {
      return (
        <div className="p-4">
          {loading ? (
            <div className="flex justify-center items-center h-32">
              <Spin size="large" />
            </div>
          ) : qaPairs.length > 0 ? (
            <div className="space-y-4">
              {qaPairs.map((qaPair) => (
                <Card
                  key={qaPair.id}
                  size="small"
                  className="bg-gray-50 border border-gray-200"
                >
                  <div className="space-y-3">
                    <div>
                      <div className="flex items-start gap-2">
                        <Icon type="question-circle-fill" className="text-lg mt-1 flex-shrink-0" />
                        <div className="flex-1">
                          <div className="text-sm text-[var(--color-text-1)] font-medium leading-6">
                            {qaPair.question}
                          </div>
                        </div>
                      </div>
                    </div>
                    
                    <Divider className="my-3" />
                    
                    <div>
                      <div className="flex items-start gap-2">
                        <Icon type="answer" className="text-lg mt-1 flex-shrink-0" />
                        <div className="flex-1">
                          <div className="text-sm text-[var(--color-text-3)] leading-6">
                            {qaPair.answer}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <Empty 
              description={t('knowledge.qaPairs.noData')}
              className="py-8"
            />
          )}
        </div>
      );
    }

    return null;
  };

  if (!visible) return null;

  return (
    <div className="h-full flex flex-col">
      <div className="p-4 border-b">
        <Segmented
          options={segmentedOptions}
          value={activeTab}
          onChange={setActiveTab}
        />
      </div>
      <div className="flex-1 overflow-auto">
        {renderContent()}
      </div>
    </div>
  );
};

export default ChunkDetail;