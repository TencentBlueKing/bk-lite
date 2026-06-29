/**
 * useGraphData Hook
 * 
 * 拓扑图数据管理核心 Hook，负责数据持久化、序列化和加载功能
 */

import { useCallback, useState, useRef } from 'react';
import type { Graph as X6Graph, Node, Edge } from '@antv/x6';
import { message } from 'antd';
import { fetchWidgetData, buildDefaultFilterBindings } from '@/app/ops-analysis/utils/widgetDataTransform';
import { getRequestErrorMessage } from '@/app/ops-analysis/utils/requestError';
import { useTranslation } from '@/utils/i18n';
import { useTopologyApi } from '@/app/ops-analysis/api/topology';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import {
  TopologyNodeData,
  SerializedEdge,
  TopologyViewSets,
} from '@/app/ops-analysis/types/topology';
import type { ValueConfig, UnifiedFilterDefinition, FilterValue } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { DirItem } from '@/app/ops-analysis/types';
import { getEdgeStyleWithLabel } from '../utils/topologyUtils';
import { createNodeByType } from '../utils/registerNode';

const DEFAULT_TABLE_QUERY_PARAMS = {
  page: 1,
  page_size: 20,
};

const isTableLikeChartType = (chartType?: string) =>
  chartType === 'table' || chartType === 'eventTable';

const serializeNodeConfig = (nodeData: TopologyNodeData, nodeType: string): Record<string, unknown> | undefined => {
  const styleConfigMapping: Record<string, string[]> = {
    'single-value': ['textColor', 'fontSize', 'backgroundColor', 'borderColor', 'nameColor', 'nameFontSize', 'thresholdColors'],
    'basic-shape': ['width', 'height', 'backgroundColor', 'borderColor', 'borderWidth', 'lineType', 'shapeType'],
    icon: ['width', 'height', 'backgroundColor', 'borderColor', 'fontSize', 'textColor', 'iconPadding', 'textDirection'],
    text: ['width', 'height', 'fontSize', 'fontWeight', 'textColor', 'backgroundColor', 'borderColor'],
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
  
  const tableQueryParamsRef = useRef<Map<string, Record<string, any>>>(new Map());

  const getEffectiveTableQueryParams = useCallback((
    valueConfig: ValueConfig,
    queryParams?: Record<string, any>,
  ) => {
    if (!isTableLikeChartType(valueConfig.chartType)) {
      return queryParams;
    }

    return queryParams || DEFAULT_TABLE_QUERY_PARAMS;
  }, []);

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

  const handleSaveTopology = useCallback(async (
    selectedTopology: DirItem,
    filters?: UnifiedFilterDefinition[],
  ) => {
    if (!selectedTopology?.data_id) {
      message.error(t('topology.saveTopologySelectMsg'));
      return;
    }

    setLoading(true);
    try {
      const topologyData = serializeTopologyData();
      const saveData: Record<string, unknown> = {
        name: selectedTopology.name,
        view_sets: {
          nodes: topologyData.nodes,
          edges: topologyData.edges,
          ...(filters && filters.length > 0 ? { filters } : {}),
        },
      };

      await saveTopology(selectedTopology.data_id, saveData);
      handleSaveCallback?.();
      message.success(t('topology.saveTopologySuccess'));
    } catch (error) {
      message.error(t('topology.saveTopologyFailed') + String(error));
    } finally {
      setLoading(false);
    }
  }, [serializeTopologyData, saveTopology, handleSaveCallback]);

  const loadChartNodeData = useCallback(async (
    nodeId: string,
    valueConfig: ValueConfig,
    unifiedFilterValues?: Record<string, FilterValue>,
    filterDefinitions?: UnifiedFilterDefinition[],
    dataSource?: DatasourceItem,
    namespaceId?: number,
    tableQueryParams?: Record<string, any>
  ) => {
    if (!graphInstance || !valueConfig.dataSource) return;

    const node = graphInstance.getCellById(nodeId);
    if (!node) return;

    try {
      const effectiveFilterBindings = valueConfig.filterBindings || 
        buildDefaultFilterBindings(valueConfig.dataSourceParams || [], filterDefinitions || [], undefined);
      
      const extraParams: Record<string, any> = {};
      if (namespaceId !== undefined) {
        extraParams.namespace_id = namespaceId;
      }
      if (tableQueryParams) {
        Object.assign(extraParams, tableQueryParams);
      }
      
      const chartData = await fetchWidgetData({
        config: valueConfig,
        getSourceDataByApiId,
        unifiedFilterValues,
        filterBindings: effectiveFilterBindings,
        filterDefinitions,
        extraParams: Object.keys(extraParams).length > 0 ? extraParams : undefined,
        throwError: true,
      });

      const currentNodeData = node.getData();
      node.setData({
        ...currentNodeData,
        isLoading: false,
        rawData: chartData,
        hasError: false,
        errorMessage: undefined,
        dataSource,
      }, { overwrite: true });
    } catch (error) {
      const currentNodeData = node.getData();
      node.setData({
        ...currentNodeData,
        isLoading: false,
        rawData: null,
        hasError: true,
        errorMessage: getRequestErrorMessage(error, t('dashboard.dataFetchFailed')),
      }, { overwrite: true });
    }
  }, [graphInstance, getSourceDataByApiId, t]);

  const handleTableQueryChange = useCallback((
    nodeId: string,
    queryParams: Record<string, any>,
    unifiedFilterValues?: Record<string, FilterValue>,
    filterDefinitions?: UnifiedFilterDefinition[],
    dataSources?: DatasourceItem[],
    namespaceId?: number
  ) => {
    if (!graphInstance) return;

    const node = graphInstance.getCellById(nodeId);
    if (!node) return;

    const nodeData = node.getData();
    if (
      nodeData.type !== 'chart' ||
      !isTableLikeChartType(nodeData.valueConfig?.chartType)
    ) return;

    const nextQueryParams = getEffectiveTableQueryParams(
      nodeData.valueConfig,
      queryParams,
    );
    const previousQueryParams = tableQueryParamsRef.current.get(nodeId);
    if (
      previousQueryParams &&
      JSON.stringify(previousQueryParams) === JSON.stringify(nextQueryParams)
    ) {
      return;
    }

    tableQueryParamsRef.current.set(nodeId, nextQueryParams);

    node.setData({ ...nodeData, isLoading: true, hasError: false, errorMessage: undefined }, { overwrite: true });

    const dataSource = dataSources?.find(
      (ds) => ds.id === nodeData.valueConfig.dataSource
    );

    loadChartNodeData(
      nodeId,
      nodeData.valueConfig,
      unifiedFilterValues,
      filterDefinitions,
      dataSource,
      namespaceId,
      nextQueryParams
    );
  }, [graphInstance, loadChartNodeData, getEffectiveTableQueryParams]);

  const createTableQueryHandler = useCallback((
    unifiedFilterValues?: Record<string, FilterValue>,
    filterDefinitions?: UnifiedFilterDefinition[],
    dataSources?: DatasourceItem[],
    namespaceId?: number
  ) => {
    return (nodeId: string, queryParams: Record<string, any>) => {
      handleTableQueryChange(nodeId, queryParams, unifiedFilterValues, filterDefinitions, dataSources, namespaceId);
    };
  }, [handleTableQueryChange]);

  const loadTopologyData = useCallback((data: TopologyViewSets) => {
    if (!graphInstance) return;

    graphInstance.clearCells();

    const nodes = data.nodes || [];
    const nodeIds = new Set(nodes.map((nodeConfig) => nodeConfig.id).filter(Boolean));

    nodes.forEach((nodeConfig) => {
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
      } else if (nodeConfig.type === 'single-value' && valueConfig?.dataSource && valueConfig?.selectedFields?.length) {
        nodeData = createNodeByType(nodeConfig);
        // Mark single-value nodes as loading; actual data fetch deferred to after filters are ready
        graphInstance.addNode(nodeData as any);
        const addedNode = graphInstance.getCellById(nodeConfig.id!);
        if (addedNode && addedNode.isNode()) {
          startLoadingAnimation(addedNode as Node);
        }
        return;
      } else {
        nodeData = createNodeByType(nodeConfig);
      }

      graphInstance.addNode(nodeData as any);
    });

    (data.edges || [])
      .filter((edgeConfig) => (
        nodeIds.has(edgeConfig.source) &&
        nodeIds.has(edgeConfig.target)
      ))
      .forEach((edgeConfig) => {
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
  }, [graphInstance, startLoadingAnimation]);

  const handleLoadTopology = useCallback(async (topologyId: string | number): Promise<{
    filters: UnifiedFilterDefinition[];
  }> => {
    if (!graphInstance) {
      return {
        filters: [],
      };
    }

    setLoading(true);
    try {
      const topologyData = await getTopologyDetail(topologyId);
      const viewSets = topologyData.view_sets || {};

      loadTopologyData(viewSets);
      graphInstance.zoomToFit({ padding: 20, maxScale: 1 });

      const rawFilters = viewSets.filters;
      const loadedFilters: UnifiedFilterDefinition[] = Array.isArray(rawFilters) ? rawFilters : [];
      return {
        filters: loadedFilters,
      };
    } catch (error) {
      console.error('加载拓扑图失败:', error);
      return {
        filters: [],
      };
    } finally {
      setLoading(false);
    }
  }, [graphInstance, getTopologyDetail, loadTopologyData]);

  const refreshAllChartNodes = useCallback((
    unifiedFilterValues?: Record<string, FilterValue>,
    filterDefinitions?: UnifiedFilterDefinition[],
    dataSources?: DatasourceItem[],
    namespaceId?: number,
    shouldRefreshNode?: (nodeData: TopologyNodeData, dataSource?: DatasourceItem) => boolean,
  ) => {
    if (!graphInstance) return;

    const tableQueryHandler = createTableQueryHandler(
      unifiedFilterValues,
      filterDefinitions,
      dataSources,
      namespaceId
    );

    const nodes = graphInstance.getNodes();
    nodes.forEach((node: Node) => {
      const nodeData = node.getData();
      if (nodeData.type === 'chart' && nodeData.valueConfig?.dataSource) {
        const dataSource = dataSources?.find(
          (ds) => ds.id === nodeData.valueConfig.dataSource
        );
        if (shouldRefreshNode && !shouldRefreshNode(nodeData, dataSource)) {
          return;
        }
        node.setData({ 
          ...nodeData, 
          isLoading: true, 
          hasError: false,
          errorMessage: undefined,
          onTableQueryChange: tableQueryHandler,
        }, { overwrite: true });
        const storedQueryParams = getEffectiveTableQueryParams(
          nodeData.valueConfig,
          tableQueryParamsRef.current.get(node.id),
        );
        if (isTableLikeChartType(nodeData.valueConfig?.chartType)) {
          tableQueryParamsRef.current.set(node.id, storedQueryParams);
        }
        loadChartNodeData(
          node.id,
          nodeData.valueConfig,
          unifiedFilterValues,
          filterDefinitions,
          dataSource,
          namespaceId,
          storedQueryParams
        );
      }
    });
  }, [graphInstance, loadChartNodeData, createTableQueryHandler, getEffectiveTableQueryParams]);

  return {
    loading,
    setLoading,
    handleSaveTopology,
    handleLoadTopology,
    loadTopologyData: loadTopologyData as (data: TopologyViewSets) => void,
    loadChartNodeData,
    refreshAllChartNodes,
  };
};
