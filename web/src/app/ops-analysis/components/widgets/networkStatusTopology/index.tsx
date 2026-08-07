'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Empty, Modal, Spin } from 'antd';
import type { Graph } from '@antv/x6';
import {
  NetworkTopologyX6Canvas,
  layoutNetworkTopology,
} from '@/app/cmdb/components/networkTopology';
import type {
  NetworkTopologyLayoutMode,
  NetworkTopologyLink,
  NetworkTopologyNode,
} from '@/app/cmdb/components/networkTopology';
import { useTranslation } from '@/utils/i18n';
import { useShareMode } from '@/app/ops-analysis/context/shareMode';
import { useNetworkStatusTopologyApi } from '@/app/ops-analysis/api/networkStatusTopology';
import type {
  NetworkStatusTopologyConfig,
  NetworkStatusTopologyLink,
  NetworkStatusTopologyModeLayout,
  NetworkStatusTopologyNode,
  NetworkStatusTopologyResponse,
} from '@/app/ops-analysis/types/sceneWidget';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import {
  isScreenChartThemeMode,
  resolveOpsChartThemeName,
} from '@/app/ops-analysis/utils/chartTheme';
import {
  applyNodePositionsToLayout,
  buildPersistedNetworkStatusTopologyConfig,
  canPersistNetworkStatusTopologyLayout,
  cellPositionToLayoutPoint,
  normalizeNetworkStatusTopologyLayoutMode,
  patchLayoutByMode,
  pruneNetworkStatusTopologyLayout,
  resetNetworkStatusTopologyLayout,
  resolveLayoutGeometry,
} from '@/app/ops-analysis/utils/networkStatusTopologyLayout';
import {
  buildAlertListUrl,
  buildFaultPath,
  buildInstanceDetailUrl,
  getLinkEndpoints,
  getLinkId,
  getNodeResource,
} from './graphModel';
import { assignParallelOffsets } from './parallelEdges';
import {
  buildStatusTopologyX6GraphData,
  ensureStatusTopologyNodeRegistered,
  isStatusTopologyIconHoverTarget,
  STATUS_TOPOLOGY_NODE_SHAPE,
  STATUS_TOPOLOGY_PALETTE_DARK,
  STATUS_TOPOLOGY_PALETTE_LIGHT,
  STATUS_TOPOLOGY_VISUAL,
} from './statusTopologyGraph';
import type { StatusTopologyPositionedLink } from './statusTopologyGraph';
import { resolveNodePopoverPosition } from './popoverPosition';
import { useWidgetViewport } from '@/app/ops-analysis/components/widget-viewport';
import styles from './networkStatusTopology.module.scss';

interface NetworkStatusTopologyProps {
  config?: ValueConfig;
  refreshKey?: string | number;
  onReady?: (ready?: boolean) => void;
  /** 父级画布可编辑且非分享时为 true */
  layoutEditable?: boolean;
  /** 几何相关改动写回组件实例草稿配置 */
  onTopologyLayoutChange?: (next: NetworkStatusTopologyConfig) => void;
}

const stripDevicePrefix = (value?: string, deviceName?: string) => {
  if (!value) return '';
  if (deviceName && value.startsWith(`${deviceName}-`)) {
    return value.slice(deviceName.length + 1);
  }
  return value;
};

const openUrl = (url: string) => {
  window.open(url, '_blank', 'noopener,noreferrer');
};

const getStatusLabelKey = (status?: string) => {
  if (status === 'critical') return 'dashboard.networkTopoStatusCritical';
  if (status === 'error') return 'dashboard.networkTopoStatusCritical';
  if (status === 'warning') return 'dashboard.networkTopoStatusWarning';
  return 'dashboard.networkTopoStatusNormal';
};

const toCanvasNode = (
  node: NetworkStatusTopologyNode,
): NetworkTopologyNode => ({
  id: String(node.id),
  modelId: String(node.model_id),
  name: node.name || String(node.id),
  subtitle: String(node.model_id),
  hop: Number(node.hop || 0),
  status: node.status,
  alertCount: Number(node.alert_count || 0),
  pulse: Boolean(node.pulse),
  icon: typeof node.icon === 'string' ? node.icon : '',
});

const toCanvasLink = (
  link: NetworkStatusTopologyLink,
  nodeNameMap: Map<string, string>,
): NetworkTopologyLink => {
  const endpoints = getLinkEndpoints(link);
  const sourceName = nodeNameMap.get(endpoints.source);
  const targetName = nodeNameMap.get(endpoints.target);
  const sourcePort = link.source_port || link.source_inst_name;
  const targetPort = link.target_port || link.target_inst_name;

  return {
    id: getLinkId(link),
    source: endpoints.source,
    target: endpoints.target,
    sourcePort: stripDevicePrefix(sourcePort, sourceName),
    targetPort: stripDevicePrefix(targetPort, targetName),
  };
};

const NetworkStatusTopology: React.FC<NetworkStatusTopologyProps> = ({
  config,
  refreshKey,
  onReady,
  layoutEditable = false,
  onTopologyLayoutChange,
}) => {
  const { t } = useTranslation();
  const shareMode = useShareMode();
  const { scale: viewportScale } = useWidgetViewport();
  const { getNetworkStatusTopology } = useNetworkStatusTopologyApi();
  const [data, setData] = useState<NetworkStatusTopologyResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [viewLayoutMode, setViewLayoutMode] =
    useState<NetworkTopologyLayoutMode | null>(null);
  const [ephemeralPositions, setEphemeralPositions] = useState<
    Record<string, { x: number; y: number }>
  >({});
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const graphRef = useRef<Graph | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [hoverNodeId, setHoverNodeId] = useState('');
  const [hoverPoint, setHoverPoint] = useState({ x: 0, y: 0 });
  const hoverNodeIdRef = useRef('');
  const [contextNodeId, setContextNodeId] = useState('');
  const [contextPoint, setContextPoint] = useState({ x: 0, y: 0 });

  const topoConfig = config?.networkStatusTopology;
  /** 画布编辑态且非分享：几何写回草稿，随页面保存落库 */
  const canPersistLayout = canPersistNetworkStatusTopologyLayout({
    layoutEditable,
    shareMode,
    hasWriteback: Boolean(onTopologyLayoutChange),
  });
  const savedLayoutMode = normalizeNetworkStatusTopologyLayoutMode(topoConfig?.layoutMode);
  const layoutMode = canPersistLayout
    ? savedLayoutMode
    : (viewLayoutMode ?? savedLayoutMode);
  // 父级 onReady 常随 layout 草稿更新换新引用；不得进入 fetch 依赖，否则拖点会重取数出 loading
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  useEffect(() => {
    if (canPersistLayout) {
      setViewLayoutMode(null);
      setEphemeralPositions({});
    }
  }, [canPersistLayout]);

  useEffect(() => {
    // 拓扑查询身份变化时清空查看态临时摆放
    setEphemeralPositions({});
    setViewLayoutMode(null);
  }, [topoConfig?.modelId, topoConfig?.instId, topoConfig?.depth]);

  const emitLayoutChange = useCallback(
    (next: NetworkStatusTopologyConfig) => {
      onTopologyLayoutChange?.(buildPersistedNetworkStatusTopologyConfig(next));
    },
    [onTopologyLayoutChange],
  );

  const fetchData = useCallback(async () => {
    if (!topoConfig?.modelId || !topoConfig?.instId) {
      setData(null);
      setError(t('dashboard.networkTopoMissingConfig'));
      onReadyRef.current?.(false);
      return;
    }

    try {
      setLoading(true);
      setError('');
      const result = await getNetworkStatusTopology({
        model_id: topoConfig.modelId,
        inst_id: topoConfig.instId,
        depth: topoConfig.depth || 2,
      });
      setData(result);
      setSelectedNodeId('');
      setEphemeralPositions({});
      onReadyRef.current?.((result.nodes || []).length > 0);
    } catch (err) {
      console.error('network status topology fetch failed:', err);
      setData(null);
      setError(t('dashboard.networkTopoLoadFailed'));
      onReadyRef.current?.(false);
    } finally {
      setLoading(false);
    }
    // API hooks return fresh function references; fetching is driven by widget config.
     
  }, [t, topoConfig?.depth, topoConfig?.instId, topoConfig?.modelId]);

  useEffect(() => {
    void fetchData();
  }, [fetchData, refreshKey]);

  useEffect(() => {
    ensureStatusTopologyNodeRegistered();
  }, []);

  const originalNodeMap = useMemo(
    () =>
      new Map(
        (data?.nodes || []).map((node) => [String(node.id), node]),
      ),
    [data?.nodes],
  );

  const nodeNameMap = useMemo(
    () =>
      new Map(
        (data?.nodes || []).map((node) => [
          String(node.id),
          node.name || String(node.id),
        ]),
      ),
    [data?.nodes],
  );

  const canvasNodes = useMemo(
    () => (data?.nodes || []).map(toCanvasNode),
    [data?.nodes],
  );

  const canvasLinks = useMemo(
    () =>
      (data?.links || []).map((link) => toCanvasLink(link, nodeNameMap)),
    [data?.links, nodeNameMap],
  );

  const parallelLinks = useMemo(
    () => assignParallelOffsets(canvasLinks),
    [canvasLinks],
  );

  const faultPath = useMemo(() => {
    const selected = originalNodeMap.get(selectedNodeId);
    if (!data || !selected || !selected.alert_count) {
      return { nodeIds: [], linkIds: [] };
    }
    return buildFaultPath({
      nodes: data.nodes,
      links: data.links,
      centerId: String(data.center_id),
      selectedNodeId,
    });
  }, [data, originalNodeMap, selectedNodeId]);

  const faultNodeIds = useMemo(() => new Set(faultPath.nodeIds), [faultPath.nodeIds]);
  const faultLinkIds = useMemo(
    () => new Set(faultPath.linkIds),
    [faultPath.linkIds],
  );
  const hasFaultPath = faultNodeIds.size > 0 || faultLinkIds.size > 0;
  const usesScreenTheme = isScreenChartThemeMode(config?.chartThemeMode);
  const topologyPalette = (() => {
    if (config?.chartThemeMode === 'screen-dark') return STATUS_TOPOLOGY_PALETTE_DARK;
    if (config?.chartThemeMode === 'screen-light') return STATUS_TOPOLOGY_PALETTE_LIGHT;
    return resolveOpsChartThemeName() === 'dark'
      ? STATUS_TOPOLOGY_PALETTE_DARK
      : STATUS_TOPOLOGY_PALETTE_LIGHT;
  })();

  const bringNodesAboveEdges = useCallback((graph: Graph | null) => {
    if (!graph) return;
    graph.getEdges().forEach((edge) => edge.toBack());
    graph.getNodes().forEach((node) => node.toFront());
  }, []);

  const activeModeGeometry = useMemo(
    () => resolveLayoutGeometry(topoConfig, layoutMode),
    [layoutMode, topoConfig],
  );

  const layout = useMemo(
    () => {
      const computed = layoutNetworkTopology({
        nodes: canvasNodes,
        links: parallelLinks,
        centerId: String(data?.center_id || topoConfig?.instId || ''),
        mode: layoutMode,
        fitToViewport: false,
      });
      const mergedPositions = canPersistLayout
        ? activeModeGeometry.nodePositions
        : {
          ...(activeModeGeometry.nodePositions || {}),
          ...ephemeralPositions,
        };
      return applyNodePositionsToLayout(computed, mergedPositions);
    },
    [
      activeModeGeometry.nodePositions,
      canPersistLayout,
      canvasNodes,
      data?.center_id,
      ephemeralPositions,
      layoutMode,
      parallelLinks,
      topoConfig?.instId,
    ],
  );
  const graphData = useMemo(
    () => {
      const parallelById = new Map(
        parallelLinks.map((link) => [link.id, link]),
      );
      const positionedLinks: StatusTopologyPositionedLink[] = layout.links.map((link) => {
        const withOffset = parallelById.get(link.id);
        return {
          ...link,
          parallelOffset: withOffset?.parallelOffset ?? 0,
          vertices: activeModeGeometry.linkVertices?.[link.id],
        };
      });

      return buildStatusTopologyX6GraphData({
        nodes: layout.nodes,
        links: positionedLinks,
        centerId: String(data?.center_id || topoConfig?.instId || ''),
        selectedNodeId,
        activeNodeIds: faultNodeIds,
        activeLinkIds: faultLinkIds,
        dimInactive: hasFaultPath,
        showStatusDot: false,
        palette: topologyPalette,
      });
    },
    [
      activeModeGeometry.linkVertices,
      data?.center_id,
      faultLinkIds,
      faultNodeIds,
      hasFaultPath,
      layout.links,
      layout.nodes,
      parallelLinks,
      selectedNodeId,
      topoConfig?.instId,
      topologyPalette,
    ],
  );
  const fitViewKey = useMemo(
    () => [
      layoutMode,
      data?.center_id || topoConfig?.instId || '',
      canvasNodes.map((node) => node.id).join(','),
      parallelLinks.map((link) => link.id).join(','),
      // 强制在视觉常量 / shape 版本变更后重建画布
      STATUS_TOPOLOGY_NODE_SHAPE,
      `i${STATUS_TOPOLOGY_VISUAL.iconSize}-n${STATUS_TOPOLOGY_VISUAL.nameFontSize}-y${STATUS_TOPOLOGY_VISUAL.labelNameY}`,
    ].join('|'),
    [canvasNodes, data?.center_id, layoutMode, parallelLinks, topoConfig?.instId],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      bringNodesAboveEdges(graphRef.current);
    }, 80);
    return () => window.clearTimeout(timer);
  }, [bringNodesAboveEdges, fitViewKey, graphData]);

  const closeContextMenu = useCallback(() => setContextNodeId(''), []);

  const commitLayoutPatch = useCallback(
    (
      patch: {
        layoutMode?: NetworkStatusTopologyConfig['layoutMode'];
      } & Partial<NetworkStatusTopologyModeLayout>,
    ) => {
      if (!topoConfig || !onTopologyLayoutChange) return;
      const nextMode = patch.layoutMode ?? layoutMode;
      const geometryPatch =
        patch.nodePositions !== undefined || patch.linkVertices !== undefined
          ? {
            ...(patch.nodePositions !== undefined
              ? { nodePositions: patch.nodePositions }
              : {}),
            ...(patch.linkVertices !== undefined
              ? { linkVertices: patch.linkVertices }
              : {}),
          }
          : undefined;
      const layoutByMode = geometryPatch
        ? patchLayoutByMode(topoConfig, layoutMode, geometryPatch)
        : topoConfig.layoutByMode;
      const nodeIds = canvasNodes.map((node) => node.id);
      const linkIds = canvasLinks.map((link) => link.id);
      const pruned = pruneNetworkStatusTopologyLayout(
        {
          layoutMode: nextMode,
          layoutByMode,
        },
        nodeIds,
        linkIds,
      );
      emitLayoutChange({
        modelId: topoConfig.modelId,
        instId: topoConfig.instId,
        depth: topoConfig.depth || 2,
        ...pruned,
      });
    },
    [
      canvasLinks,
      canvasNodes,
      emitLayoutChange,
      layoutMode,
      onTopologyLayoutChange,
      topoConfig,
    ],
  );

  const handleLayoutModeChange = useCallback(
    (value: string) => {
      const nextMode = normalizeNetworkStatusTopologyLayoutMode(value);
      if (canPersistLayout) {
        // 只切换当前 mode；各 mode 桶保持不变
        commitLayoutPatch({ layoutMode: nextMode });
        return;
      }
      setEphemeralPositions({});
      setViewLayoutMode(nextMode);
    },
    [canPersistLayout, commitLayoutPatch],
  );

  const handleNodeMoved = useCallback(
    (nodeId: string, position: { x: number; y: number }) => {
      const layoutPoint = cellPositionToLayoutPoint(position);
      if (canPersistLayout) {
        commitLayoutPatch({
          nodePositions: {
            ...(activeModeGeometry.nodePositions || {}),
            [nodeId]: layoutPoint,
          },
        });
        return;
      }
      // 查看态：仅本地临时摆放，不写回配置、不落库
      setEphemeralPositions((current) => ({
        ...current,
        [nodeId]: layoutPoint,
      }));
    },
    [activeModeGeometry.nodePositions, canPersistLayout, commitLayoutPatch],
  );

  const handleEdgeVerticesChanged = useCallback(
    (edgeId: string, vertices: Array<{ x: number; y: number }>) => {
      if (!canPersistLayout) return;
      const nextVertices = { ...(activeModeGeometry.linkVertices || {}) };
      if (vertices.length === 0) {
        delete nextVertices[edgeId];
      } else {
        nextVertices[edgeId] = vertices;
      }
      commitLayoutPatch({ linkVertices: nextVertices });
    },
    [activeModeGeometry.linkVertices, canPersistLayout, commitLayoutPatch],
  );

  const handleResetLayout = useCallback(() => {
    if (!canPersistLayout || !topoConfig) return;
    Modal.confirm({
      title: t('dashboard.networkTopoResetLayout'),
      content: t('dashboard.networkTopoResetLayoutConfirm'),
      okText: t('common.confirm'),
      cancelText: t('common.cancel'),
      centered: true,
      onOk: () => {
        setEphemeralPositions({});
        emitLayoutChange(resetNetworkStatusTopologyLayout(topoConfig, layoutMode));
      },
    });
  }, [canPersistLayout, emitLayoutChange, layoutMode, t, topoConfig]);

  const updateNodeHover = useCallback((nodeId: string, event: MouseEvent) => {
    // 双保险：即便 body 全尺寸命中，也只在 SVG image（icon）上展示浮层
    if (!isStatusTopologyIconHoverTarget(event)) {
      hoverNodeIdRef.current = '';
      setHoverNodeId('');
      return;
    }
    // 悬停期间不跟手：仅首次进入或切换节点时锚定 icon 算一次位置
    if (hoverNodeIdRef.current !== nodeId) {
      const next = resolveNodePopoverPosition(
        graphRef.current,
        nodeId,
        canvasRef.current,
        undefined,
        viewportScale,
      );
      if (next) setHoverPoint(next);
    }
    hoverNodeIdRef.current = nodeId;
    setHoverNodeId(nodeId);
  }, [viewportScale]);

  const clearNodeHover = useCallback(() => {
    hoverNodeIdRef.current = '';
    setHoverNodeId('');
  }, []);

  const renderPopover = useCallback(
    (node: NetworkTopologyNode) => {
      const originalNode = originalNodeMap.get(node.id);
      if (!originalNode) return null;
      const alertCount = Number(originalNode.alert_count || 0);
      const status = originalNode.status || 'normal';
      return (
        <div className={styles.popover}>
          <div className={styles.popHeader}>
            <span className={styles.popTitle}>{originalNode.name || node.name}</span>
            <span className={`${styles.statusPill} ${styles[status] || ''}`}>
              {t(getStatusLabelKey(status))}
            </span>
          </div>
          <div className={styles.popLine}>
            <span>{t('dashboard.networkTopoPopoverModel')}:</span>
            <strong>{String(originalNode.model_id)}</strong>
          </div>
          <div className={styles.popLine}>
            <span>{t('dashboard.networkTopoPopoverAlerts')}:</span>
            <strong className={alertCount ? styles.alertCount : styles.noAlertText}>
              {alertCount}
            </strong>
          </div>
          {originalNode.severity && (
            <div className={styles.popLine}>
              <span>{t('dashboard.networkTopoPopoverSeverity')}:</span>
              <strong>{t(getStatusLabelKey(String(originalNode.severity)))}</strong>
            </div>
          )}
        </div>
      );
    },
    [originalNodeMap, t],
  );

  const renderContextMenu = useCallback(
    (node: NetworkTopologyNode, closeMenu: () => void) => {
      const originalNode = originalNodeMap.get(node.id);
      if (!originalNode) return null;
      if (shareMode) {
        return (
          <div className={styles.contextMenu}>
            <button
              type="button"
              className={`${styles.contextMenuItem} ${styles.disabledMenuItem}`}
              disabled
            >
              {t('dashboard.shareNavigationDisabled')}
            </button>
          </div>
        );
      }
      const alertCount = Number(originalNode.alert_count || 0);
      const openInstanceDetail = () => {
        closeMenu();
        openUrl(buildInstanceDetailUrl({
          modelId: String(originalNode.model_id),
          instId: String(originalNode.id),
          instName: originalNode.name,
        }));
      };
      const openAlertList = () => {
        if (!alertCount) return;
        closeMenu();
        const resource = getNodeResource(originalNode);
        openUrl(buildAlertListUrl({
          resourceType: resource.resourceType,
          resourceId: resource.resourceId,
        }));
      };

      return (
        <div className={styles.contextMenu}>
          <button type="button" className={styles.contextMenuItem} onClick={openInstanceDetail}>
            {t('dashboard.networkTopoInstanceDetail')}
          </button>
          <button
            type="button"
            className={`${styles.contextMenuItem} ${!alertCount ? styles.disabledMenuItem : ''}`}
            disabled={!alertCount}
            onClick={openAlertList}
          >
            {t('dashboard.networkTopoViewAlerts')}
          </button>
        </div>
      );
    },
    [originalNodeMap, shareMode, t],
  );

  const hoverCanvasNode = canvasNodes.find((node) => node.id === hoverNodeId);
  const contextCanvasNode = canvasNodes.find((node) => node.id === contextNodeId);
  const isMissingConfig = !topoConfig?.modelId || !topoConfig?.instId;

  return (
    <div
      ref={canvasRef}
      className={`${styles.canvas} ${usesScreenTheme ? styles.screenCanvas : ''}`}
    >
      {data?.truncated && (
        <div className={styles.truncated}>{t('dashboard.networkTopoTruncated')}</div>
      )}
      {graphData.nodes.length ? (
        <NetworkTopologyX6Canvas
          data={graphData}
          centerId={String(data?.center_id || topoConfig?.instId || '')}
          graphRef={graphRef}
          nodeMovable
          edgeVerticesEditable={canPersistLayout}
          fitViewOptions={{ padding: 48, maxScale: 1.08 }}
          fitViewKey={fitViewKey}
          onGraphReady={(graph) => {
            if (graphRef) graphRef.current = graph;
            bringNodesAboveEdges(graph);
          }}
          onNodeMoved={handleNodeMoved}
          onEdgeVerticesChanged={handleEdgeVerticesChanged}
          toolbar={{
            layoutMode,
            onLayoutChange: handleLayoutModeChange,
            layoutOptions: [
              { label: t('dashboard.networkTopoLayoutHierarchical'), value: 'hierarchical' },
              { label: t('dashboard.networkTopoLayoutForce'), value: 'force' },
              { label: t('dashboard.networkTopoLayoutCircular'), value: 'circular' },
            ],
            showResetLayout: canPersistLayout,
            onResetLayout: canPersistLayout ? handleResetLayout : undefined,
            labels: {
              zoomOut: t('dashboard.networkTopoZoomOut'),
              zoomIn: t('dashboard.networkTopoZoomIn'),
              fitView: t('topology.fitView'),
              exportImage: t('dashboard.networkTopoExportImage'),
              refresh: t('dashboard.networkTopoRefresh'),
              resetLayout: t('dashboard.networkTopoResetLayout'),
            },
            exportFileName: 'network-status-topology',
            refreshLoading: loading,
            onRefresh: fetchData,
          }}
          minimap={{
            width: 96,
            height: 56,
            style: {
              right: 14,
              bottom: 14,
              position: 'absolute',
              border: '1px solid #dbe8f6',
              borderRadius: 6,
              background: 'rgba(255,255,255,0.88)',
              boxShadow: '0 8px 18px rgba(42, 72, 116, 0.08)',
            },
          }}
          onBlankClick={() => {
            setSelectedNodeId('');
            hoverNodeIdRef.current = '';
            setHoverNodeId('');
            closeContextMenu();
          }}
          onBlankContextMenu={() => closeContextMenu()}
          onNodeClick={(nodeId) => {
            closeContextMenu();
            setSelectedNodeId((current) => (current === nodeId ? '' : nodeId));
          }}
          onNodeMouseEnter={updateNodeHover}
          onNodeMouseMove={updateNodeHover}
          onNodeMouseLeave={clearNodeHover}
          onNodeContextMenu={(nodeId, event) => {
            setContextNodeId(nodeId);
            setContextPoint({ x: event.offsetX + 8, y: event.offsetY + 8 });
          }}
        />
      ) : (
        !loading && (
          <div className={styles.state}>
            {error && isMissingConfig ? (
              <div className={styles.pendingState}>
                <div className={styles.pendingIcon} aria-hidden="true" />
                <div className={styles.pendingTitle}>
                  {t('dashboard.networkStatusTopology')}
                </div>
                <div className={styles.pendingDesc}>{error}</div>
              </div>
            ) : error ? (
              <Alert
                type="error"
                showIcon
                message={error}
                action={(
                  <Button size="small" onClick={fetchData}>
                    {t('dashboard.networkTopoRefresh')}
                  </Button>
                )}
              />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t('dashboard.networkTopoEmpty')}
              />
            )}
          </div>
        )
      )}
      {loading && (
        <div className={styles.loadingMask}>
          <Spin />
        </div>
      )}
      {hoverCanvasNode && !contextNodeId && (
        <div
          className={styles.popoverLayer}
          style={{ left: hoverPoint.x, top: hoverPoint.y }}
        >
          {renderPopover(hoverCanvasNode)}
        </div>
      )}
      {contextCanvasNode && (
        <div
          className={styles.contextLayer}
          style={{ left: contextPoint.x, top: contextPoint.y }}
        >
          {renderContextMenu(
            contextCanvasNode,
            closeContextMenu,
          )}
        </div>
      )}
    </div>
  );
};

export default NetworkStatusTopology;
