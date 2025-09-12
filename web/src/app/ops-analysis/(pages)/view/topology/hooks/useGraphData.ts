/**
 * useGraphData Hook
 * 
 * 拓扑图数据管理核心 Hook，负责数据持久化、序列化和加载功能
 */

import { useCallback, useState } from 'react';
import type { Graph as X6Graph } from '@antv/x6';
import { message } from 'antd';
import { fetchWidgetData } from '@/app/ops-analysis/utils/widgetDataTransform';
import { useTopologyApi } from '@/app/ops-analysis/api/topology';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { TopologyNodeData } from '@/app/ops-analysis/types/topology';
import { DirItem } from '@/app/ops-analysis/types';
import { getEdgeStyleWithLabel } from '../utils/topologyUtils';
import { createNodeByType } from '../utils/registerNode';

const serializeNodeConfig = (nodeData: any, nodeType: string) => {
  const styleConfigMapping: Record<string, string[]> = {
    'single-value': ['textColor', 'fontSize', 'backgroundColor', 'borderColor', 'nameColor', 'nameFontSize'],
    'basic-shape': ['width', 'height', 'backgroundColor', 'borderColor', 'borderWidth', 'lineType', 'shapeType'],
    icon: ['width', 'height', 'borderColor'],
    text: ['fontSize', 'fontWeight', 'textColor'],
    chart: ['width', 'height'],
  };

  const fields = styleConfigMapping[nodeType] || [];
  const styleConfig: any = {};

  fields.forEach((field) => {
    if (nodeData.styleConfig?.[field] !== undefined) {
      styleConfig[field] = nodeData.styleConfig[field];
    }
  });

  return Object.keys(styleConfig).length > 0 ? styleConfig : undefined;
};

export const useGraphData = (
  graphInstance: X6Graph | null,
  updateSingleNodeData: (nodeConfig: TopologyNodeData) => void,
  startLoadingAnimation: (node: any) => void,
  handleSaveCallback?: () => void
) => {
  const [loading, setLoading] = useState(false);
  const { saveTopology, getTopologyDetail } = useTopologyApi();
  const { getSourceDataByApiId } = useDataSourceApi();

  const serializeTopologyData = useCallback(() => {
    if (!graphInstance) return { nodes: [], edges: [] };

    const nodes = graphInstance.getNodes().map((node: any) => {
      const nodeData = node.getData();
      const position = node.getPosition();
      const zIndex = node.getZIndex();

      const serializedNode: TopologyNodeData = {
        id: nodeData.id,
        type: nodeData.type,
        name: nodeData.name,
        unit: nodeData.unit,
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

    const edges = graphInstance.getEdges().map((edge: any) => {
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
      message.error('请先选择要保存的拓扑图');
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
      message.success('拓扑图保存成功');
    } catch (error) {
      console.error('保存拓扑图失败:', error);
      message.error('保存拓扑图失败');
    } finally {
      setLoading(false);
    }
  }, [serializeTopologyData, saveTopology, handleSaveCallback]);

  const loadChartNodeData = useCallback(async (nodeId: string, valueConfig: any) => {
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

  const loadTopologyData = useCallback((data: { nodes: any[], edges: any[] }) => {
    if (!graphInstance) return;

    graphInstance.clearCells();
    const chartNodesToLoad: Array<{ nodeId: string; valueConfig: any }> = [];

    data.nodes?.forEach((nodeConfig) => {
      let nodeData: any;
      const valueConfig = nodeConfig.valueConfig || {};

      if (nodeConfig.type === 'chart') {
        const chartNodeConfig = {
          ...nodeConfig,
          isLoading: !!valueConfig?.dataSource,
          rawData: null,
          hasError: false,
        };

        nodeData = createNodeByType(chartNodeConfig);
        if (valueConfig?.dataSource) {
          chartNodesToLoad.push({
            nodeId: nodeConfig.id,
            valueConfig: chartNodeConfig.valueConfig,
          });
        }
      } else {
        nodeData = createNodeByType(nodeConfig);
      }

      graphInstance.addNode(nodeData);

      if (nodeConfig.type === 'single-value' && valueConfig?.dataSource && valueConfig?.selectedFields?.length) {
        const addedNode = graphInstance.getCellById(nodeConfig.id);
        if (addedNode) {
          startLoadingAnimation(addedNode);
          updateSingleNodeData(nodeConfig);
        }
      }
    });

    data.edges?.forEach((edgeConfig) => {
      const edgeData: any = {
        lineType: edgeConfig.lineType as 'common_line' | 'network_line',
        lineName: edgeConfig.lineName,
        sourceInterface: edgeConfig.sourceInterface,
        targetInterface: edgeConfig.targetInterface,
        vertices: edgeConfig.vertices || [],
        styleConfig: edgeConfig.styleConfig,
        config: edgeConfig.config,
      };

      const edgeStyle = getEdgeStyleWithLabel(edgeData, 'single');

      if (edgeConfig.styleConfig?.lineColor) {
        edgeStyle.attrs = {
          ...edgeStyle.attrs,
          line: {
            ...edgeStyle.attrs?.line,
            stroke: edgeConfig.styleConfig.lineColor,
          },
        };
      }

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