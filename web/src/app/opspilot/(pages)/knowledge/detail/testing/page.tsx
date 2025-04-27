'use client';

import React, { useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Input, Button, message, Spin, Empty, Skeleton, List } from 'antd';
import ConfigComponent from '@/app/opspilot/components/knowledge/config';
import { ResultItem } from '@/app/opspilot/types/global';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';
import ContentDrawer from '@/components/content-drawer';
import PermissionWrapper from '@/components/permission';
import useContentDrawer from '@/app/opspilot/hooks/useContentDrawer';
import KnowledgeResultItem from '@/app/opspilot/components/block-result';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import useFetchConfigData from '@/app/opspilot/hooks/useFetchConfigData';

const { TextArea } = Input;

const TestingPage: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;
  const { updateKnowledgeSettings, testKnowledge } = useKnowledgeApi();
  const { configData, setConfigData, loading: configLoading } = useFetchConfigData(id);
  const [searchText, setSearchText] = useState<string>('');
  const [results, setResults] = useState<ResultItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [applyLoading, setApplyLoading] = useState<boolean>(false);

  const {
    drawerVisible,
    drawerContent,
    showDrawer,
    hideDrawer,
  } = useContentDrawer();

  const getConfigParams = () => {
    return {
      embed_model: configData.selectedEmbedModel,
      enable_rerank: configData.rerankModel,
      rerank_model: configData.selectedRerankModel,
      enable_text_search: configData.selectedSearchTypes.includes('textSearch'),
      text_search_weight: configData.textSearchWeight,
      text_search_mode: configData.textSearchMode,
      enable_vector_search: configData.selectedSearchTypes.includes('vectorSearch'),
      vector_search_weight: configData.vectorSearchWeight,
      rag_k: configData.quantity,
      rag_num_candidates: configData.candidate,
      result_count: configData.resultCount,
      rerank_top_k: configData.rerankTopK,
    };
  };

  const handleTesting = async () => {
    const params = {
      knowledge_base_id: id,
      query: searchText,
      ...getConfigParams(),
    };
    if (!searchText.trim()) {
      message.error(t('common.fieldRequired'));
      return false;
    }
    if (configData.candidate < configData.quantity) {
      message.error(t('knowledge.returnQuanityTip'));
      return false;
    }
    setLoading(true);
    try {
      const data = await testKnowledge(params);
      message.success(t('knowledge.testingSuccess'));
      setResults(data);
    } catch (error) {
      message.error(t('knowledge.testingFailed'));
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleApplyConfig = async () => {
    const params = getConfigParams();
    setApplyLoading(true);
    try {
      await updateKnowledgeSettings(id, params);
      message.success('Configuration applied successfully!');
    } catch (error) {
      message.error(t('knowledge.applyFailed'));
      console.error(error);
    } finally {
      setApplyLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && searchText.trim()) {
      e.preventDefault();
      handleTesting();
    }
  };

  const handleContentClick = (content: string) => {
    showDrawer(content);
  };

  return (
    <Spin spinning={configLoading}>
      <div className="flex">
        <div className="w-1/2 pr-4">
          <div className={`mb-4 border rounded-md ${styles.testingHeader}`}>
            <h2 className="font-semibold text-base">{t('knowledge.testing.text')}</h2>
            <div className="relative">
              <TextArea
                placeholder="Enter text to search"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                onKeyPress={handleKeyPress}
                rows={6}
              />
              <PermissionWrapper requiredPermissions={['Edit']}>
                <Button
                  type="primary"
                  className="absolute bottom-2 right-2"
                  disabled={!searchText.trim()}
                  onClick={handleTesting}
                  loading={loading}
                >
                  {t('knowledge.testing.title')}
                </Button>
              </PermissionWrapper>
            </div>
          </div>
          <div className={`border rounded-md ${styles.testingHeader}`}>
            <h2 className="font-semibold mb-2 text-base">{t('knowledge.config')}</h2>
            <div className="p-4">
              <ConfigComponent
                configData={configData}
                setConfigData={setConfigData}
              />
              <div className="flex justify-end mt-4">
                <PermissionWrapper requiredPermissions={['Edit']}>
                  <Button type="primary" onClick={handleApplyConfig} loading={applyLoading}>
                    {t('knowledge.applyConfig')}
                  </Button>
                </PermissionWrapper>
              </div>
            </div>
          </div>
        </div>
        <div className="w-1/2 pl-4">
          <h2 className="font-semibold mb-2 text-base">{t('knowledge.results')}</h2>
          <div className="space-y-4">
            {loading ? (
              <>
                <List
                  itemLayout="vertical"
                  dataSource={[1, 2, 3]}
                  renderItem={() => (
                    <List.Item>
                      <Skeleton active />
                    </List.Item>
                  )}
                />
              </>
            ) : results.length > 0 ? (
              results.map((result, index) => (
                <KnowledgeResultItem
                  key={result.id}
                  result={result}
                  index={index}
                  onClick={handleContentClick}
                />
              ))
            ) : (
              <Empty description={t('common.noResult')} />
            )}
          </div>
        </div>
      </div>
      <ContentDrawer
        visible={drawerVisible}
        onClose={hideDrawer}
        content={drawerContent}
      />
    </Spin>
  );
};

export default TestingPage;
