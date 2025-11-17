/**
 * useGraphData Hook
 * 
 * 拓扑图数据管理核心 Hook，负责数据持久化、序列化和加载功能
 */

import { useCallback, useState } from 'react';
import type { Graph as X6Graph, Node, Edge } from '@antv/x6';
import { message } from 'antd';
import { fetchWidgetData } from '@/app/ops-analysis/utils/widgetDataTransform';
import { useTranslation } from '@/utils/i18n';
import { useTopologyApi } from '@/app/ops-analysis/api/topology';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { TopologyNodeData, SerializedEdge } from '@/app/ops-analysis/types/topology';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import { DirItem } from '@/app/ops-analysis/types';
import { getEdgeStyleWithLabel } from '../utils/topologyUtils';
import { createNodeByType } from '../utils/registerNode';

const serializeNodeConfig = (nodeData: TopologyNodeData, nodeType: string): Record<string, unknown> | undefined => {
  const styleConfigMapping: Record<string, string[]> = {
    'single-value': ['textColor', 'fontSize', 'backgroundColor', 'borderColor', 'nameColor', 'nameFontSize', 'thresholdColors'],
    'basic-shape': ['width', 'height', 'backgroundColor', 'borderColor', 'borderWidth', 'lineType', 'shapeType', 'renderEffect'],
    icon: ['width', 'height', 'backgroundColor', 'borderColor', 'fontSize', 'textColor', 'iconPadding', 'textDirection'],
    text: ['fontSize', 'fontWeight', 'textColor'],
    chart: ['width', 'height'],
  };

  const fields = styleConfigMapping[nodeType] || [];
  const styleConfig: Record<string, unknown> = {};

  fields.forEach((field) => {
    const styleConfigData = nodeData.styleConfig as Record<string, unknown> | undefined;
    if (styleConfigData?.[field] !== undefined) {
      styleConfig[field] = styleConfigData[field];
    }
  });

  return Object.keys(styleConfig).length > 0 ? styleConfig : undefined;
};

export const useGraphData = (
  graphInstance: X6Graph | null,
  updateSingleNodeData: (nodeConfig: TopologyNodeData) => void,
  startLoadingAnimation: (node: Node) => void,
  handleSaveCallback?: () => void
) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const { saveTopology, getTopologyDetail } = useTopologyApi();
  const { getSourceDataByApiId } = useDataSourceApi();

  const serializeTopologyData = useCallback((): { nodes: TopologyNodeData[]; edges: SerializedEdge[] } => {
    if (!graphInstance) return { nodes: [], edges: [] };

    const nodes = graphInstance.getNodes().map((node: Node) => {
      const nodeData = node.getData();
      const position = node.getPosition();
      const zIndex = node.getZIndex();

      const serializedNode: TopologyNodeData = {
        id: nodeData.id,
        type: nodeData.type,
        name: nodeData.name,
        unit: nodeData.unit,
        conversionFactor: nodeData.conversionFactor,
        decimalPlaces: nodeData.decimalPlaces,
        description: nodeData.description || '',
        position,
        zIndex: zIndex || 0,
        logoType: nodeData.logoType,
        logoIcon: nodeData.logoIcon,
        logoUrl: nodeData.logoUrl,
        valueConfig: nodeData.valueConfig,
        styleConfig: serializeNodeConfig(nodeData, nodeData.type),
      };

      return serializedNode;
    });

    const edges = graphInstance.getEdges().map((edge: Edge): SerializedEdge => {
      const edgeData = edge.getData();
      const vertices = edge.getVertices();

      return {
        id: edge.id,
        source: edge.getSourceCellId(),
        target: edge.getTargetCellId(),
        sourcePort: edge.getSourcePortId(),
        targetPort: edge.getTargetPortId(),
        lineType: edgeData?.lineType || 'common_line',
        lineName: edgeData?.lineName || '',
        arrowDirection: edgeData?.arrowDirection || 'single',
        sourceInterface: edgeData?.sourceInterface,
        targetInterface: edgeData?.targetInterface,
        vertices: vertices || [],
        styleConfig: edgeData?.styleConfig,
        config: edgeData?.config ? {
          strokeColor: edgeData.config.strokeColor,
          strokeWidth: edgeData.config.strokeWidth,
        } : undefined,
      };
    });

    return { nodes, edges };
  }, [graphInstance]);

  const handleSaveTopology = useCallback(async (selectedTopology: DirItem) => {
    if (!selectedTopology?.data_id) {
      message.error(t('topology.saveTopologySelectMsg'));
      return;
    }

    setLoading(true);
    try {
      const topologyData = serializeTopologyData();
      const saveData = {
        name: selectedTopology.name,
        view_sets: {
          nodes: topologyData.nodes,
          edges: topologyData.edges,
        },
      };

      await saveTopology(selectedTopology.data_id, saveData);
      handleSaveCallback?.();
      message.success(t('topology.saveTopologySuccess'));
    } catch (error) {
      message.error(t('topology.saveTopologyFailed' + error));
    } finally {
      setLoading(false);
    }
  }, [serializeTopologyData, saveTopology, handleSaveCallback]);

  const loadChartNodeData = useCallback(async (nodeId: string, valueConfig: ValueConfig) => {
    if (!graphInstance || !valueConfig.dataSource) return;

    const node = graphInstance.getCellById(nodeId);
    if (!node) return;

    try {
      const chartData = await fetchWidgetData({
        config: valueConfig,
        globalTimeRange: undefined,
        getSourceDataByApiId,
      });

      if (chartData) {
        const currentNodeData = node.getData();
        node.setData({
          ...currentNodeData,
          isLoading: false,
          rawData: chartData,
          hasError: false,
        });
      }
    } catch {
      const currentNodeData = node.getData();
      node.setData({
        ...currentNodeData,
        isLoading: false,
        hasError: true,
      });
    }
  }, [graphInstance, getSourceDataByApiId]);

  const loadTopologyData = useCallback((data: { nodes: TopologyNodeData[]; edges: SerializedEdge[] }) => {
    if (!graphInstance) return;

    graphInstance.clearCells();
    const chartNodesToLoad: Array<{ nodeId: string; valueConfig: ValueConfig }> = [];

    data.nodes?.forEach((nodeConfig) => {
      let nodeData: ReturnType<typeof createNodeByType>;
      const valueConfig = nodeConfig.valueConfig || {};

      if (nodeConfig.type === 'chart') {
        const chartNodeConfig = {
          ...nodeConfig,
          isLoading: !!valueConfig?.dataSource,
          rawData: null,
          hasError: false,
        };

        nodeData = createNodeByType(chartNodeConfig);
        if (valueConfig?.dataSource && nodeConfig.id && chartNodeConfig.valueConfig) {
          chartNodesToLoad.push({
            nodeId: nodeConfig.id,
            valueConfig: chartNodeConfig.valueConfig as ValueConfig,
          });
        }
      } else {
        nodeData = createNodeByType(nodeConfig);
      }

      graphInstance.addNode(nodeData as any);

      if (nodeConfig.type === 'single-value' && valueConfig?.dataSource && valueConfig?.selectedFields?.length && nodeConfig.id) {
        const addedNode = graphInstance.getCellById(nodeConfig.id);
        if (addedNode && addedNode.isNode()) {
          startLoadingAnimation(addedNode as Node);
          updateSingleNodeData(nodeConfig);
        }
      }
    });

    data.edges?.forEach((edgeConfig) => {
      const connectionType = (edgeConfig as any).arrowDirection || 'single';
      const edgeData: any = {
        lineType: edgeConfig.lineType as 'common_line' | 'network_line',
        lineName: edgeConfig.lineName,
        arrowDirection: connectionType,
        sourceInterface: edgeConfig.sourceInterface,
        targetInterface: edgeConfig.targetInterface,
        vertices: edgeConfig.vertices || [],
        styleConfig: edgeConfig.styleConfig,
        config: edgeConfig.config,
      };

      const edgeStyle = getEdgeStyleWithLabel(edgeData, connectionType, edgeConfig.styleConfig);

      const edge = graphInstance.createEdge({
        id: edgeConfig.id,
        source: edgeConfig.source,
        target: edgeConfig.target,
        sourcePort: edgeConfig.sourcePort,
        targetPort: edgeConfig.targetPort,
        shape: 'edge',
        ...edgeStyle,
        data: edgeData,
      });

      graphInstance.addEdge(edge);

      // 恢复拐点数据
      if (edgeConfig.vertices && edgeConfig.vertices.length > 0) {
        edge.setVertices(edgeConfig.vertices);
      }
    });

    chartNodesToLoad.forEach(({ nodeId, valueConfig }) => {
      loadChartNodeData(nodeId, valueConfig);
    });
  }, [graphInstance, updateSingleNodeData, loadChartNodeData, startLoadingAnimation]);

  const handleLoadTopology = useCallback(async (topologyId: string | number) => {
    if (!graphInstance) return;

    setLoading(true);
    try {
      const topologyData = await getTopologyDetail(topologyId);
      const viewSets = topologyData.view_sets || {};

      loadTopologyData(viewSets);
      graphInstance.zoomToFit({ padding: 20, maxScale: 1 });
    } catch (error) {
      console.error('加载拓扑图失败:', error);
    } finally {
      setLoading(false);
    }
  }, [graphInstance, getTopologyDetail, loadTopologyData]);

  return {
    loading,
    setLoading,
    handleSaveTopology,
    handleLoadTopology,
    loadChartNodeData,
  };
};