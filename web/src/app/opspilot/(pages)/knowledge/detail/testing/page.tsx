'use client';

import React, { useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Input, Button, message, Spin, Empty, Skeleton, List, Segmented, Card, Divider } from 'antd';
import ConfigComponent from '@/app/opspilot/components/knowledge/config';
import { useTranslation } from '@/utils/i18n';
import styles from './index.module.scss';
import ContentDrawer from '@/components/content-drawer';
import PermissionWrapper from '@/components/permission';
import useContentDrawer from '@/app/opspilot/hooks/useContentDrawer';
import KnowledgeResultItem from '@/app/opspilot/components/block-result';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import useFetchConfigData from '@/app/opspilot/hooks/useFetchConfigData';
import Icon from '@/components/icon';
import KnowledgeGraphView from '@/app/opspilot/components/knowledge/knowledgeGraphView';
import NodeDetailDrawer from '@/app/opspilot/components/knowledge/NodeDetailDrawer';
import { GraphData, TestKnowledgeResponse, GraphNode } from '@/app/opspilot/types/knowledge';

const { TextArea } = Input;

const TestingPage: React.FC = () => {
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const id = searchParams ? searchParams.get('id') : null;
  const { updateKnowledgeSettings, testKnowledge } = useKnowledgeApi();
  const { configData, setConfigData, loading: configLoading, knowledgeBasePermissions } = useFetchConfigData(id);
  const [searchText, setSearchText] = useState<string>('');
  const [results, setResults] = useState<TestKnowledgeResponse>({ docs: [], qa_docs: [], graph_data: [] });
  const [loading, setLoading] = useState<boolean>(false);
  const [applyLoading, setApplyLoading] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<string>('docs');
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [nodeDetailVisible, setNodeDetailVisible] = useState(false);

  const {
    drawerVisible,
    drawerContent,
    showDrawer,
    hideDrawer,
  } = useContentDrawer();

  const transformGraphData = (graphData: any): GraphData => {
    if (!graphData || !Array.isArray(graphData)) {
      return { nodes: [], edges: [] };
    }

    const nodesMap = new Map();
    const edges: any[] = [];

    graphData.forEach((relation: any, index: number) => {
      const { source_node, target_node, fact, name } = relation;
      
      if (!source_node || !target_node) {
        return;
      }

      if (source_node.uuid && !nodesMap.has(source_node.uuid)) {
        nodesMap.set(source_node.uuid, {
          id: source_node.uuid,
          label: source_node.name || `节点${source_node.uuid.slice(0, 8)}`,
          type: 'entity',
          labels: source_node.labels || [],
          uuid: source_node.uuid,
          name: source_node.name,
          summary: source_node.summary
        });
      }

      if (target_node.uuid && !nodesMap.has(target_node.uuid)) {
        nodesMap.set(target_node.uuid, {
          id: target_node.uuid,
          label: target_node.name || `节点${target_node.uuid.slice(0, 8)}`,
          type: 'entity',
          labels: target_node.labels || [],
          uuid: target_node.uuid,
          name: target_node.name,
          summary: target_node.summary,
        });
      }

      if (source_node.uuid && target_node.uuid) {
        edges.push({
          id: `edge-${index}`,
          source: source_node.uuid,
          target: target_node.uuid,
          label: name,
          type: 'relation',
          relation_type: name,
          fact: fact
        });
      }
    });

    return {
      nodes: Array.from(nodesMap.values()),
      edges: edges
    };
  };

  const getSegmentedOptions = () => {
    const options = [];
    
    if (configData.enableNaiveRag) {
      options.push({
        value: 'docs',
        label: t('knowledge.chunks'),
      });
    }
    
    if (configData.enableQaRag) {
      options.push({
        value: 'qa_docs',
        label: t('knowledge.qaPairs.title'),
      });
    }
    
    if (configData.enableGraphRag) {
      options.push({
        value: 'graph_data',
        label: t('knowledge.graphRag'),
      });
    }
    
    return options;
  };

  const segmentedOptions = getSegmentedOptions();

  const getConfigParams = () => {
    // Calculate rag_k from enabled RAG types - use the maximum value from enabled types
    let ragK = 10; // default value
    const enabledSizes = [];
    
    if (configData.enableNaiveRag && configData.ragSize > 0) {
      enabledSizes.push(configData.ragSize);
    }
    if (configData.enableQaRag && configData.qaSize > 0) {
      enabledSizes.push(configData.qaSize);
    }
    if (configData.enableGraphRag && configData.graphSize > 0) {
      enabledSizes.push(configData.graphSize);
    }
    
    if (enabledSizes.length > 0) {
      ragK = Math.max(...enabledSizes);
    }

    return {
      embed_model: configData.selectedEmbedModel,
      enable_rerank: configData.rerankModel,
      rerank_model: configData.selectedRerankModel,
      search_type: configData.searchType,
      score_threshold: configData.scoreThreshold,
      rag_k: ragK,
      result_count: configData.resultCount,
      rerank_top_k: configData.rerankTopK,
      enable_naive_rag: configData.enableNaiveRag,
      enable_qa_rag: configData.enableQaRag,
      enable_graph_rag: configData.enableGraphRag,
      rag_size: configData.ragSize,
      qa_size: configData.qaSize,
      graph_size: configData.graphSize,
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
    setLoading(true);
    try {
      const data = await testKnowledge(params);
      message.success(t('knowledge.testingSuccess'));
      const newResults = {
        docs: data.docs || [],
        qa_docs: data.qa_docs || [],
        graph_data: data.graph_data || []
      };
      setResults(newResults);
      
      const availableOptions = getSegmentedOptions();
      if (availableOptions.length > 0) {
        setActiveTab(availableOptions[0].value);
      }
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

  const handleNodeClick = (node: GraphNode) => {
    setSelectedNode(node);
    setNodeDetailVisible(true);
  };

  const handleCloseNodeDetail = () => {
    setNodeDetailVisible(false);
    setSelectedNode(null);
  };

  const renderResults = () => {
    if (loading) {
      return (
        <List
          itemLayout="vertical"
          dataSource={[1, 2, 3]}
          renderItem={() => (
            <List.Item>
              <Skeleton active />
            </List.Item>
          )}
        />
      );
    }

    if (activeTab === 'docs') {
      return results.docs.length > 0 ? (
        results.docs.map((result, index) => (
          <KnowledgeResultItem
            key={result.id}
            result={result}
            index={index}
            onClick={handleContentClick}
          />
        ))
      ) : (
        <Empty description={t('common.noResult')} />
      );
    }

    if (activeTab === 'qa_docs') {
      return results.qa_docs.length > 0 ? (
        <div className="space-y-4">
          {results.qa_docs.map((qaPair) => (
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
        <Empty description={t('knowledge.qaPairs.noData')} />
      );
    }

    if (activeTab === 'graph_data') {
      return results.graph_data.length > 0 ? (
        <KnowledgeGraphView 
          data={transformGraphData(results.graph_data)} 
          onNodeClick={handleNodeClick}
        />
      ) : (
        <Empty description={t('common.noData')} />
      );
    }

    return null;
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
              <PermissionWrapper 
                requiredPermissions={['Edit']}>
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
                <PermissionWrapper 
                  requiredPermissions={['Edit']}
                  instPermissions={knowledgeBasePermissions}>
                  <Button type="primary" onClick={handleApplyConfig} loading={applyLoading}>
                    {t('knowledge.applyConfig')}
                  </Button>
                </PermissionWrapper>
              </div>
            </div>
          </div>
        </div>
        <div className="w-1/2 pl-4">
          <div className="flex justify-between items-center mb-4">
            <h2 className="font-semibold text-base">{t('knowledge.results')}</h2>
            {(results.docs.length > 0 || results.qa_docs.length > 0 || results.graph_data.length > 0) && (
              <Segmented
                options={segmentedOptions}
                value={activeTab}
                onChange={setActiveTab}
                size="small"
              />
            )}
          </div>
          <div className="space-y-4">
            {renderResults()}
          </div>
        </div>
      </div>
      <ContentDrawer
        visible={drawerVisible}
        onClose={hideDrawer}
        content={drawerContent}
      />
      
      <NodeDetailDrawer
        visible={nodeDetailVisible}
        node={selectedNode}
        onClose={handleCloseNodeDetail}
      />
    </Spin>
  );
};

export default TestingPage;
