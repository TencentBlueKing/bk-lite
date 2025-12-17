'use client';
import React, { useState, useEffect, useRef } from 'react';
import { Button, Empty, message, Modal } from 'antd';
import { SettingOutlined, ReloadOutlined, BuildOutlined, FrownOutlined } from '@ant-design/icons';
import { useRouter } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import { useKnowledgeApi } from '@/app/opspilot/api/knowledge';
import KnowledgeGraphView from './knowledgeGraphView';
import NodeDetailDrawer from './NodeDetailDrawer';
import EdgeDetailDrawer from './EdgeDetailDrawer';
import { GraphData, GraphNode, GraphEdge } from '@/app/opspilot/types/knowledge';

interface KnowledgeGraphPageProps {
  knowledgeBaseId: string | null;
  name: string | null;
  desc: string | null;
  type: string | null;
}

const transformApiDataToGraphData = (data: any): GraphData => {
  if (!data) {
    return { nodes: [], edges: [] };
  }

  if (data.nodes && data.edges) {
    const nodes: GraphNode[] = [];
    const edges: GraphEdge[] = [];

    if (Array.isArray(data.nodes)) {
      data.nodes.forEach((node: any) => {
        if (node.uuid && node.name) {
          nodes.push({
            id: node.uuid,
            label: node.name,
            labels: node.labels,
            node_id: node.node_id,
            group_id: node.group_id,
            name: node.name,
            uuid: node.uuid,
            fact: node.fact,
            summary: node.summary
          });
        }
      });
    }

    if (Array.isArray(data.edges)) {
      data.edges.forEach((edge: any) => {
        if (edge.source && edge.target) {
          edges.push({
            id: `${edge.source}-${edge.target}-${edge.fact}`,
            source: edge.source,
            target: edge.target,
            label: edge.relation_type || '关联',
            type: 'relation',
            relation_type: edge.relation_type,
            source_name: edge.source_name,
            target_name: edge.target_name,
            source_id: edge.source_id,
            target_id: edge.target_id,
            fact: edge.fact || '-',
          });
        }
      });
    }

    return { nodes, edges };
  }

  return { nodes: [], edges: [] };
};

const KnowledgeGraphPage: React.FC<KnowledgeGraphPageProps> = ({ knowledgeBaseId, desc, name, type }) => {
  const { t } = useTranslation();
  const router = useRouter();
  const { fetchKnowledgeGraphDetails, rebuildKnowledgeGraphCommunity } = useKnowledgeApi();
  
  const [hasGraph, setHasGraph] = useState(false);
  const [loading, setLoading] = useState(true);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [graphExists, setGraphExists] = useState(false);
  const [status, setStatus] = useState<string>('');
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [nodeDetailVisible, setNodeDetailVisible] = useState(false);
  const [edgeDetailVisible, setEdgeDetailVisible] = useState(false);
  const [selectedEdge, setSelectedEdge] = useState<any | null>(null);
  
  // 添加定时器引用和页面可见性状态
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const [isPageVisible, setIsPageVisible] = useState(true);

  const initializeGraph = async (isBackgroundRefresh = false) => {
    // 如果是后台刷新且正在轮询中，不显示loading
    if (!isBackgroundRefresh) {
      setLoading(true);
      setHasGraph(false);
      setGraphData(null);
    }
    
    try {
      if (!knowledgeBaseId) {
        throw new Error(t('knowledge.knowledgeGraph.knowledgeBaseIdNotFound'));
      }

      const response = await fetchKnowledgeGraphDetails(parseInt(knowledgeBaseId));
      
      setGraphExists(response.is_exists || false);
      setStatus(response.status || '');
      
      const transformedData: GraphData = transformApiDataToGraphData(response.graph);
      setGraphData(transformedData);
      
      // 只有status为completed时才展示图谱，其他状态显示状态文本
      if (response.status === 'completed') {
        setHasGraph(true);
      } else {
        setHasGraph(false);
      }
      
    } catch (error: any) {
      console.error('Failed to load knowledge graph:', error);
      setHasGraph(false);
      setGraphData(null);
      setGraphExists(false);
      setStatus('');
    } finally {
      if (!isBackgroundRefresh) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    if (knowledgeBaseId) {
      initializeGraph();
    } else {
      setLoading(false);
    }
  }, [knowledgeBaseId]);

  // 页面可见性检测
  useEffect(() => {
    const handleVisibilityChange = () => {
      setIsPageVisible(!document.hidden);
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  useEffect(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }

    if (isPageVisible && (['training', 'rebuilding', 'pending'].includes(status))) {
      pollingIntervalRef.current = setInterval(() => {
        initializeGraph(true);
      }, 15000);
    }

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [status, knowledgeBaseId, isPageVisible]);

  const handleSettingsClick = () => {
    router.push(`/opspilot/knowledge/detail/documents/graph/edit?id=${knowledgeBaseId}&name=${name}&desc=${desc}&type=${type}`);
  };

  const handleNodeClick = (node: GraphNode) => {
    setSelectedNode(node);
    setNodeDetailVisible(true);
  };

  const handleCloseNodeDetail = () => {
    setNodeDetailVisible(false);
    setSelectedNode(null);
  };

  const handleEdgeClick = (edge: any) => {
    setSelectedEdge(edge);
    setEdgeDetailVisible(true);
  };

  const handleCloseEdgeDetail = () => {
    setEdgeDetailVisible(false);
    setSelectedEdge(null);
  };

  const handleRefresh = () => {
    initializeGraph();
  };

  const handleRebuildCommunity = async () => {
    if (!knowledgeBaseId) {
      message.error(t('knowledge.knowledgeGraph.knowledgeBaseIdNotFound'));
      return;
    }

    Modal.confirm({
      title: t('knowledge.knowledgeGraph.rebuildCommunity'),
      content: t('knowledge.knowledgeGraph.rebuildCommunityConfirm'),
      onOk: async () => {
        try {
          await rebuildKnowledgeGraphCommunity(parseInt(knowledgeBaseId));
          message.success(t('knowledge.knowledgeGraph.rebuildCommunitySuccess'));
          
          initializeGraph();
        } catch (error: any) {
          console.error('Failed to rebuild community:', error);
          message.error(t('knowledge.knowledgeGraph.rebuildCommunityFailed'));
        }
      }
    });
  };

  const canClickSettings = () => {
    return status === 'completed' || status === 'failed' || !graphExists;
  };

  const canRebuildCommunity = () => {
    return status === 'completed' || status === 'failed';
  };

  const getStatusText = (status: string) => {
    if (!status) return '';
    return t(`knowledge.knowledgeGraph.status.${status}`);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'text-green-600';
      case 'failed':
        return 'text-red-600';
      case 'training':
      case 'rebuilding':
        return 'text-blue-600';
      case 'pending':
        return 'text-yellow-600';
      default:
        return 'text-gray-600';
    }
  };

  if (!knowledgeBaseId) {
    return (
      <div className="knowledge-graph-container h-96 flex items-center justify-center">
        <Empty
          description={t('knowledge.knowledgeGraph.pleaseSelectKnowledgeBase')}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </div>
    );
  }

  return (
    <div className="knowledge-graph-container relative" style={{ height: 'calc(100vh - 300px)', minHeight: '600px' }}>
      <div className="absolute top-4 right-4 z-50 flex gap-2">
        <Button
          icon={loading ? undefined : <ReloadOutlined />}
          onClick={handleRefresh}
          title={t('knowledge.knowledgeGraph.refreshGraph')}
          loading={loading}
          className="shadow-lg"
        />
        {graphExists && canRebuildCommunity() && (
          <Button
            icon={<BuildOutlined />}
            onClick={handleRebuildCommunity}
            title={t('knowledge.knowledgeGraph.rebuildCommunity')}
            className="shadow-lg"
          >
            {t('knowledge.knowledgeGraph.rebuildCommunity')}
          </Button>
        )}
        <Button
          type="primary"
          icon={<SettingOutlined />}
          onClick={handleSettingsClick}
          disabled={!canClickSettings()}
          className="shadow-lg"
        >
          {t('knowledge.knowledgeGraph.settings')}
        </Button>
      </div>

      {hasGraph && graphData ? (
        <div className="graph-display h-full relative">
          <KnowledgeGraphView
            data={graphData}
            loading={loading}
            height={600}
            onNodeClick={handleNodeClick}
            onEdgeClick={handleEdgeClick}
          />
          
          <div className="absolute bottom-4 left-4 bg-white/90 px-3 py-2 rounded-md text-xs text-gray-600 shadow-lg">
            <div>{t('knowledge.knowledgeGraph.nodes')}: {graphData.nodes?.length || 0}</div>
            <div>{t('knowledge.knowledgeGraph.relationships')}: {graphData.edges?.length || 0}</div>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-center h-full">
          {loading ? (
            <div className="text-center">
              <div className="mb-4">
                <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
              </div>
              <div className="text-gray-600">{t('knowledge.knowledgeGraph.loading')}</div>
            </div>
          ) : status ? (
            <div className="text-center">
              <div className={`flex items-center justify-center gap-2 text-sm font-medium mb-2 ${getStatusColor(status)}`}>
                {(status === 'training' || status === 'rebuilding' || status === 'pending') && (
                  <div className="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-current"></div>
                )}
                {status === 'failed' && (
                  <FrownOutlined />
                )}
                {getStatusText(status)}
              </div>
            </div>
          ) : (
            <Empty
              description={t('knowledge.knowledgeGraph.noGraphData')}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          )}
        </div>
      )}

      <NodeDetailDrawer
        visible={nodeDetailVisible}
        node={selectedNode}
        onClose={handleCloseNodeDetail}
      />
      <EdgeDetailDrawer
        visible={edgeDetailVisible}
        edge={selectedEdge}
        onClose={handleCloseEdgeDetail}
      />
    </div>
  );
};

export default KnowledgeGraphPage;