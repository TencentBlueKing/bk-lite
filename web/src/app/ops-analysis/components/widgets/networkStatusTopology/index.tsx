'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Empty, Alert, Button, Modal, Spin, Table } from 'antd';
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
import { useOpsAnalysis } from '@/app/ops-analysis/context/common';
import { useDataSourceApi } from '@/app/ops-analysis/api/dataSource';
import { useNetworkStatusTopologyApi } from '@/app/ops-analysis/api/networkStatusTopology';
import { getRequestErrorMessage } from '@/app/ops-analysis/utils/requestError';
import { isValidCmdbInstanceUuid } from '@/app/ops-analysis/utils/cmdbInstanceUuid';
import type {
  NetworkStatusTopologyConfig,
  NetworkStatusTopologyLink,
  NetworkStatusTopologyModeLayout,
  NetworkStatusTopologyNode,
  NetworkStatusTopologyResponse,
} from '@/app/ops-analysis/types/sceneWidget';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import {
  beginOwnerRequest,
  finishOwnerRequest,
  isSilentCanvasRuntimeRefresh,
  isStartedOwnerRequest,
  shouldKeepWidgetRuntimeDataOnError,
  shouldShowWidgetRuntimeLoading,
  type CanvasRuntimeRefreshCause,
} from '@/app/ops-analysis/utils/canvasRefreshTimer';
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
  buildFaultPath,
  buildInstanceDetailUrl,
  getLinkEndpoints,
  getLinkId,
} from './graphModel';
import { assignParallelOffsets } from './parallelEdges';
import {
  buildStatusTopologyX6GraphData,
  ensureStatusTopologyNodeRegistered,
  isStatusTopologyIconHoverTarget,
  isStatusTopologyBadgeTarget,
  STATUS_TOPOLOGY_NODE_SHAPE,
  STATUS_TOPOLOGY_PALETTE_DARK,
  STATUS_TOPOLOGY_PALETTE_LIGHT,
  STATUS_TOPOLOGY_VISUAL,
} from './statusTopologyGraph';
import type { StatusTopologyPositionedLink } from './statusTopologyGraph';
import { resolveNodePopoverPosition } from './popoverPosition';
import {
  applyMonitorOverlay,
  canOpenAlertModal,
  pickOverlayDataSourceIds,
  type OverlayDataSource,
} from './overlayModel';
import { useWidgetViewport } from '@/app/ops-analysis/components/widget-viewport';
import styles from './networkStatusTopology.module.scss';
import { useDashboardRuntimeScheduler } from '@/app/ops-analysis/context/dashboardRuntimeScheduler';
import {
  RuntimeRequestCancelledError,
  type RuntimeRequestPriority,
} from '@/app/ops-analysis/utils/dashboardRuntimeScheduler';

interface NetworkStatusTopologyProps {
  config?: ValueConfig;
  refreshKey?: string | number;
  refreshCause?: CanvasRuntimeRefreshCause;
  onReady?: (ready?: boolean) => void;
  /** 父级画布可编辑且非分享时为 true */
  layoutEditable?: boolean;
  /** 几何相关改动写回组件实例草稿配置 */
  onTopologyLayoutChange?: (next: NetworkStatusTopologyConfig) => void;
  runtimeOwnerId?: string;
  runtimeActive?: boolean;
  runtimePriority?: RuntimeRequestPriority;
}

const DEFAULT_RUNTIME_PRIORITY: RuntimeRequestPriority = {
  cause: 1,
  visibility: 0,
  distance: 0,
  order: 0,
};

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
  if (status === 'unknown') return 'dashboard.networkTopoStatusUnknown';
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

interface OverlayAlertItem {
  key: string;
  level: string;
  alert_type: string;
  content: string;
  start_event_time: string;
}

const asRecord = (value: unknown): Record<string, unknown> | null => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
);

const asList = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);

const parseOverlayMappings = (data: unknown) =>
  asList(asRecord(data)?.items).flatMap((item) => {
    const row = asRecord(item);
    if (!row || typeof row.inst_uuid !== 'string') return [];
    return [{
      inst_uuid: row.inst_uuid,
      ...(typeof row.model_id === 'string' ? { model_id: row.model_id } : {}),
      monitor_id: typeof row.monitor_id === 'string' ? row.monitor_id : '',
    }];
  });

const parseOverlaySummaries = (data: unknown) =>
  asList(asRecord(data)?.instance_summaries).flatMap((item) => {
    const row = asRecord(item);
    if (!row || typeof row.instance_id !== 'string') return [];
    return [{
      instance_id: row.instance_id,
      count: Number(row.count || 0),
      max_level: typeof row.max_level === 'string' ? row.max_level : null,
    }];
  });

const parseOverlayAlertItems = (data: unknown): OverlayAlertItem[] =>
  asList(asRecord(data)?.items).map((item, index) => {
    const row = asRecord(item) || {};
    return {
      key: String(row.id ?? index),
      level: typeof row.level === 'string' ? row.level : '',
      alert_type: typeof row.alert_type === 'string' ? row.alert_type : '',
      content: typeof row.content === 'string' ? row.content : '',
      start_event_time: typeof row.start_event_time === 'string' ? row.start_event_time : '',
    };
  });

const parseOverlayAlertCount = (data: unknown, fallback: number) => {
  const count = Number(asRecord(data)?.count);
  return Number.isFinite(count) ? count : fallback;
};

const normalizeDataSourceList = (value: unknown): OverlayDataSource[] => {
  if (Array.isArray(value)) return value as OverlayDataSource[];
  const record = asRecord(value);
  const items = record?.items ?? record?.results;
  return Array.isArray(items) ? (items as OverlayDataSource[]) : [];
};

const paintNodesUnknown = (nodes: NetworkStatusTopologyNode[]) =>
  applyMonitorOverlay({
    nodes,
    mappings: [],
    summaries: [],
  });

const OVERLAY_HOVER_LEAVE_DELAY_MS = 160;

const overlaySourceIdsReady = (
  ids: { cmdbId?: number; monitorId?: number },
): ids is { cmdbId: number; monitorId: number } =>
  ids.cmdbId != null && ids.monitorId != null;

const NetworkStatusTopology: React.FC<NetworkStatusTopologyProps> = ({
  config,
  refreshKey,
  refreshCause = 'manual',
  onReady,
  layoutEditable = false,
  onTopologyLayoutChange,
  runtimeOwnerId = 'network-status-topology',
  runtimeActive = true,
  runtimePriority = DEFAULT_RUNTIME_PRIORITY,
}) => {
  const { t } = useTranslation();
  const shareMode = useShareMode();
  const shareModeRef = useRef(shareMode);
  shareModeRef.current = shareMode;
  const { dataSources } = useOpsAnalysis();
  const { getSourceDataByApiId, getDataSourceBriefList } = useDataSourceApi();
  const { scale: viewportScale } = useWidgetViewport();
  const { getNetworkStatusTopology } = useNetworkStatusTopologyApi();
  // API hooks may expose a fresh function on every render. Keep the latest
  // implementation without turning it into a fetch trigger.
  const getNetworkStatusTopologyRef = useRef(getNetworkStatusTopology);
  getNetworkStatusTopologyRef.current = getNetworkStatusTopology;
  const getSourceDataByApiIdRef = useRef(getSourceDataByApiId);
  getSourceDataByApiIdRef.current = getSourceDataByApiId;
  const getDataSourceBriefListRef = useRef(getDataSourceBriefList);
  getDataSourceBriefListRef.current = getDataSourceBriefList;
  const dataSourcesRef = useRef(dataSources);
  dataSourcesRef.current = dataSources;
  const runtimeScheduler = useDashboardRuntimeScheduler();
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
  const fetchIdRef = useRef(0);
  const inflightCountRef = useRef(0);
  const physicalSequenceRef = useRef(0);
  const fulfilledRequestKeyRef = useRef<string | null>(null);
  const mountedRef = useRef(true);
  const lifecycleRef = useRef(0);
  const runtimeActiveRef = useRef(runtimeActive);
  runtimeActiveRef.current = runtimeActive;
  const runtimePriorityRef = useRef(runtimePriority);
  runtimePriorityRef.current = runtimePriority;
  const [hoverNodeId, setHoverNodeId] = useState('');
  const [hoverPoint, setHoverPoint] = useState({ x: 0, y: 0 });
  const hoverNodeIdRef = useRef('');
  const hoverLeaveTimerRef = useRef<number | null>(null);
  const alertModalFetchRef = useRef(0);
  const [contextNodeId, setContextNodeId] = useState('');
  const [contextPoint, setContextPoint] = useState({ x: 0, y: 0 });
  const [overlayError, setOverlayError] = useState('');
  const [alertModalNodeId, setAlertModalNodeId] = useState('');
  const [alertItems, setAlertItems] = useState<OverlayAlertItem[]>([]);
  const [alertModalCount, setAlertModalCount] = useState(0);
  const [alertModalLoading, setAlertModalLoading] = useState(false);
  const [alertModalError, setAlertModalError] = useState('');
  const structureRef = useRef<NetworkStatusTopologyResponse | null>(null);
  const overlayGenerationRef = useRef(0);
  const overlaySourceIdsRef = useRef<{ cmdbId?: number; monitorId?: number }>({});
  const originalNodeMapRef = useRef<Map<string, NetworkStatusTopologyNode>>(new Map());

  const topoConfig = config?.networkStatusTopology;
  const hasValidInstanceUuid = isValidCmdbInstanceUuid(topoConfig?.instUuid);
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
  const refreshCauseRef = useRef(refreshCause);
  refreshCauseRef.current = refreshCause;
  const dataRef = useRef(data);
  dataRef.current = data;

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
  }, [topoConfig?.modelId, topoConfig?.instUuid, topoConfig?.depth]);

  const emitLayoutChange = useCallback(
    (next: NetworkStatusTopologyConfig) => {
      onTopologyLayoutChange?.(buildPersistedNetworkStatusTopologyConfig(next));
    },
    [onTopologyLayoutChange],
  );

  const resolveOverlaySourceIds = useCallback(async () => {
    let ids = overlaySourceIdsRef.current;
    if (overlaySourceIdsReady(ids)) return ids;
    ids = pickOverlayDataSourceIds(dataSourcesRef.current || []);
    if (!overlaySourceIdsReady(ids) && !shareModeRef.current) {
      const brief = await getDataSourceBriefListRef.current({ page_size: -1 });
      ids = pickOverlayDataSourceIds([
        ...(dataSourcesRef.current || []),
        ...normalizeDataSourceList(brief),
      ]);
    }
    if (overlaySourceIdsReady(ids)) {
      overlaySourceIdsRef.current = ids;
    }
    return ids;
  }, []);
  const resolveOverlaySourceIdsRef = useRef(resolveOverlaySourceIds);
  resolveOverlaySourceIdsRef.current = resolveOverlaySourceIds;

  const fetchOverlay = useCallback(async (
    structure: NetworkStatusTopologyResponse,
    ownerFetchId: number,
  ) => {
    const overlayGeneration = ++overlayGenerationRef.current;
    const isStale = () => (
      !mountedRef.current
      || ownerFetchId !== fetchIdRef.current
      || overlayGeneration !== overlayGenerationRef.current
    );
    setOverlayError('');
    try {
      const ids = await resolveOverlaySourceIdsRef.current();
      if (isStale()) return;
      if (!overlaySourceIdsReady(ids)) {
        throw new Error('overlay sources missing');
      }
      const instUuids = (structure.nodes || []).map((node) => String(node.id));
      const mappingResult = await getSourceDataByApiIdRef.current(ids.cmdbId, {
        inst_uuids: instUuids,
      });
      if (isStale()) return;
      const mappings = parseOverlayMappings(mappingResult.data);
      const monitorIds = Array.from(
        new Set(
          mappings
            .map((mapping) => mapping.monitor_id.trim())
            .filter(Boolean),
        ),
      );
      let summaries: ReturnType<typeof parseOverlaySummaries> = [];
      if (monitorIds.length) {
        const monitorResult = await getSourceDataByApiIdRef.current(ids.monitorId, {
          instance_ids: monitorIds,
          limit: 1,
        });
        if (isStale()) return;
        summaries = parseOverlaySummaries(monitorResult.data);
      }
      if (isStale()) return;
      setData({
        ...structure,
        nodes: applyMonitorOverlay({
          nodes: structure.nodes || [],
          mappings,
          summaries,
        }),
      });
      setOverlayError('');
    } catch (err) {
      if (isStale()) return;
      console.error('network status topology overlay failed:', err);
      setData({
        ...structure,
        nodes: paintNodesUnknown(structure.nodes || []),
      });
      setOverlayError(t('dashboard.networkTopoStatusLoadFailed'));
    }
  }, [t]);
  const fetchOverlayRef = useRef(fetchOverlay);
  fetchOverlayRef.current = fetchOverlay;

  const fetchData = useCallback(async (options?: { force?: boolean }) => {
    if (!runtimeActiveRef.current) return;
    if (!topoConfig?.modelId || !hasValidInstanceUuid) {
      structureRef.current = null;
      overlaySourceIdsRef.current = {};
      setOverlayError('');
      setData(null);
      setError(t('dashboard.networkTopoMissingConfig'));
      onReadyRef.current?.(false);
      return;
    }
    const request = {
      model_id: topoConfig.modelId,
      inst_uuid: topoConfig.instUuid,
      depth: topoConfig.depth || 2,
    };
    const physicalKey = `scene:${refreshKey ?? '0'}:${JSON.stringify(request)}`;
    if (!options?.force && fulfilledRequestKeyRef.current === physicalKey) return;

    const cause = refreshCauseRef.current;
    const silent = isSilentCanvasRuntimeRefresh(cause);
    const gate = beginOwnerRequest({
      silent,
      latestGeneration: fetchIdRef.current,
      inflightCount: inflightCountRef.current,
    });
    if (!isStartedOwnerRequest(gate)) {
      return;
    }
    const currentFetchId = gate.generation;
    fetchIdRef.current = currentFetchId;
    inflightCountRef.current += 1;
    runtimeScheduler?.cancelQueuedForOwner(runtimeOwnerId);
    const hasSuccessfulPayload = dataRef.current !== null;
    try {
      if (shouldShowWidgetRuntimeLoading(cause)) {
        setLoading(true);
        setError('');
      }
      const result = runtimeScheduler
        ? await runtimeScheduler.schedule({
          consumerId: `${runtimeOwnerId}:${currentFetchId}:${++physicalSequenceRef.current}`,
          ownerId: runtimeOwnerId,
          physicalKey,
          priority: {
            ...runtimePriorityRef.current,
            cause: silent ? 2 : cause === 'initial' ? 1 : 0,
          },
          start: () => getNetworkStatusTopologyRef.current(request),
        })
        : await getNetworkStatusTopologyRef.current(request);
      if (!mountedRef.current || currentFetchId !== fetchIdRef.current) return;
      fulfilledRequestKeyRef.current = physicalKey;
      const structure: NetworkStatusTopologyResponse = {
        ...result,
        nodes: result.nodes || [],
      };
      structureRef.current = structure;
      overlayGenerationRef.current += 1;
      setOverlayError('');
      setData({
        ...structure,
        nodes: paintNodesUnknown(structure.nodes),
      });
      if (shouldShowWidgetRuntimeLoading(cause)) {
        setSelectedNodeId('');
        setEphemeralPositions({});
      }
      onReadyRef.current?.(structure.nodes.length > 0);
      if (structure.nodes.length > 0) {
        void fetchOverlayRef.current(structure, currentFetchId);
      }
    } catch (err) {
      if (err instanceof RuntimeRequestCancelledError) return;
      if (!mountedRef.current || currentFetchId !== fetchIdRef.current) return;
      fulfilledRequestKeyRef.current = physicalKey;
      console.error('network status topology fetch failed:', err);
      if (
        !shouldKeepWidgetRuntimeDataOnError({
          cause,
          hasSuccessfulPayload,
        })
      ) {
        structureRef.current = null;
        overlaySourceIdsRef.current = {};
        setOverlayError('');
        setData(null);
        setError(getRequestErrorMessage(err, t('dashboard.networkTopoLoadFailed')));
        onReadyRef.current?.(false);
      }
    } finally {
      inflightCountRef.current = finishOwnerRequest({
        inflightCount: inflightCountRef.current,
      }).inflightCount;
      if (!mountedRef.current || currentFetchId !== fetchIdRef.current) return;
      setLoading(false);
    }
    // API hooks return fresh function references; fetching is driven by widget config.
  }, [
    hasValidInstanceUuid,
    refreshKey,
    runtimeOwnerId,
    runtimeScheduler,
    t,
    topoConfig?.depth,
    topoConfig?.instUuid,
    topoConfig?.modelId,
  ]);

  const handleExplicitRefresh = useCallback(() => {
    void fetchData({ force: true });
  }, [fetchData]);

  useEffect(() => {
    void fetchData();
  }, [fetchData, refreshKey, runtimeActive]);

  useEffect(() => {
    if (runtimeActive) {
      runtimeScheduler?.updateOwnerPriority(runtimeOwnerId, runtimePriority);
      return;
    }
    runtimeScheduler?.cancelQueuedForOwner(runtimeOwnerId);
  }, [runtimeActive, runtimeOwnerId, runtimePriority, runtimeScheduler]);

  useEffect(() => {
    const lifecycle = ++lifecycleRef.current;
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      queueMicrotask(() => {
        if (lifecycleRef.current === lifecycle) {
          runtimeScheduler?.cancelQueuedForOwner(runtimeOwnerId);
        }
      });
    };
  }, [runtimeOwnerId, runtimeScheduler]);

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
  originalNodeMapRef.current = originalNodeMap;

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
    if (!data || !selected || !canOpenAlertModal(selected)) {
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
        centerId: String(data?.center_id || topoConfig?.instUuid || ''),
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
      topoConfig?.instUuid,
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
        centerId: String(data?.center_id || topoConfig?.instUuid || ''),
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
      topoConfig?.instUuid,
      topologyPalette,
    ],
  );
  const fitViewKey = useMemo(
    () => [
      layoutMode,
      data?.center_id || topoConfig?.instUuid || '',
      canvasNodes.map((node) => node.id).join(','),
      parallelLinks.map((link) => link.id).join(','),
      // 强制在视觉常量 / shape 版本变更后重建画布
      STATUS_TOPOLOGY_NODE_SHAPE,
      `i${STATUS_TOPOLOGY_VISUAL.iconSize}-n${STATUS_TOPOLOGY_VISUAL.nameFontSize}-y${STATUS_TOPOLOGY_VISUAL.labelNameY}`,
    ].join('|'),
    [canvasNodes, data?.center_id, layoutMode, parallelLinks, topoConfig?.instUuid],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      bringNodesAboveEdges(graphRef.current);
    }, 80);
    return () => window.clearTimeout(timer);
  }, [bringNodesAboveEdges, fitViewKey, graphData]);

  const closeContextMenu = useCallback(() => setContextNodeId(''), []);

  const handleOverlayRetry = useCallback(() => {
    const structure = structureRef.current;
    if (!structure?.nodes?.length) return;
    void fetchOverlayRef.current(structure, fetchIdRef.current);
  }, []);

  const fetchAlertItems = useCallback(async (monitorId: string) => {
    const requestId = ++alertModalFetchRef.current;
    setAlertModalLoading(true);
    setAlertModalError('');
    try {
      const ids = await resolveOverlaySourceIdsRef.current();
      if (requestId !== alertModalFetchRef.current) return;
      if (ids.monitorId == null) {
        throw new Error('overlay sources missing');
      }
      const result = await getSourceDataByApiIdRef.current(ids.monitorId, {
        instance_ids: [monitorId],
        limit: 10,
      });
      if (requestId !== alertModalFetchRef.current) return;
      const items = parseOverlayAlertItems(result.data);
      setAlertItems(items);
      setAlertModalCount(parseOverlayAlertCount(result.data, items.length));
      setAlertModalError('');
    } catch (err) {
      if (requestId !== alertModalFetchRef.current) return;
      console.error('network status topology alert modal failed:', err);
      setAlertModalError(t('dashboard.networkTopoStatusLoadFailed'));
    } finally {
      if (requestId === alertModalFetchRef.current) {
        setAlertModalLoading(false);
      }
    }
  }, [t]);

  const openAlertModal = useCallback((nodeId: string) => {
    const originalNode = originalNodeMapRef.current.get(nodeId);
    if (!originalNode || !canOpenAlertModal(originalNode)) return;
    const monitorId = String(originalNode.monitor_id || '').trim();
    if (!monitorId) return;
    closeContextMenu();
    setAlertModalNodeId(nodeId);
    setAlertItems([]);
    setAlertModalCount(Number(originalNode.alert_count || 0));
    void fetchAlertItems(monitorId);
  }, [closeContextMenu, fetchAlertItems]);

  const closeAlertModal = useCallback(() => {
    alertModalFetchRef.current += 1;
    setAlertModalNodeId('');
    setAlertModalError('');
    setAlertModalLoading(false);
  }, []);

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
        instUuid: topoConfig.instUuid,
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

  const cancelHoverLeave = useCallback(() => {
    if (hoverLeaveTimerRef.current != null) {
      window.clearTimeout(hoverLeaveTimerRef.current);
      hoverLeaveTimerRef.current = null;
    }
  }, []);

  const scheduleClearNodeHover = useCallback(() => {
    cancelHoverLeave();
    hoverLeaveTimerRef.current = window.setTimeout(() => {
      hoverLeaveTimerRef.current = null;
      hoverNodeIdRef.current = '';
      setHoverNodeId('');
    }, OVERLAY_HOVER_LEAVE_DELAY_MS);
  }, [cancelHoverLeave]);

  const updateNodeHover = useCallback((nodeId: string, event: MouseEvent) => {
    // 双保险：即便 body 全尺寸命中，也只在 SVG image（icon）上展示浮层
    if (!isStatusTopologyIconHoverTarget(event)) {
      scheduleClearNodeHover();
      return;
    }
    cancelHoverLeave();
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
  }, [cancelHoverLeave, scheduleClearNodeHover, viewportScale]);

  const clearNodeHover = useCallback(() => {
    scheduleClearNodeHover();
  }, [scheduleClearNodeHover]);

  useEffect(() => () => {
    if (hoverLeaveTimerRef.current != null) {
      window.clearTimeout(hoverLeaveTimerRef.current);
    }
  }, []);

  const renderPopover = useCallback(
    (node: NetworkTopologyNode) => {
      const originalNode = originalNodeMap.get(node.id);
      if (!originalNode) return null;
      const alertCount = Number(originalNode.alert_count || 0);
      const status = originalNode.status || 'unknown';
      const canOpen = canOpenAlertModal(originalNode);
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
          <div className={styles.popLine} data-testid="status-topo-popover-alerts">
            <span>{t('dashboard.networkTopoPopoverAlerts')}:</span>
            {status === 'unknown' ? (
              <strong className={styles.noAlertText}>
                {t('dashboard.networkTopoUnmonitored')}
              </strong>
            ) : canOpen ? (
              <button
                type="button"
                className={`${styles.alertCount} cursor-pointer border-0 bg-transparent p-0`}
                onClick={() => openAlertModal(node.id)}
              >
                {alertCount}
              </button>
            ) : (
              <strong className={styles.noAlertText}>{alertCount}</strong>
            )}
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
    [openAlertModal, originalNodeMap, t],
  );

  const renderContextMenu = useCallback(
    (node: NetworkTopologyNode, closeMenu: () => void) => {
      const originalNode = originalNodeMap.get(node.id);
      if (!originalNode) return null;
      const canViewAlerts = canOpenAlertModal(originalNode);
      const openInstanceDetail = () => {
        if (shareMode) return;
        closeMenu();
        openUrl(buildInstanceDetailUrl({
          modelId: String(originalNode.model_id),
          instUuid: String(originalNode.id),
          instName: originalNode.name,
        }));
      };
      const openAlertList = () => {
        if (!canViewAlerts) return;
        closeMenu();
        openAlertModal(String(originalNode.id));
      };

      return (
        <div className={styles.contextMenu}>
          <button
            type="button"
            className={`${styles.contextMenuItem} ${shareMode ? styles.disabledMenuItem : ''}`}
            disabled={shareMode}
            onClick={openInstanceDetail}
          >
            {t('dashboard.networkTopoInstanceDetail')}
          </button>
          <button
            type="button"
            className={`${styles.contextMenuItem} ${!canViewAlerts ? styles.disabledMenuItem : ''}`}
            disabled={!canViewAlerts}
            onClick={openAlertList}
          >
            {t('dashboard.networkTopoViewAlerts')}
          </button>
        </div>
      );
    },
    [openAlertModal, originalNodeMap, shareMode, t],
  );

  const hoverCanvasNode = canvasNodes.find((node) => node.id === hoverNodeId);
  const contextCanvasNode = canvasNodes.find((node) => node.id === contextNodeId);
  const isMissingConfig = !topoConfig?.modelId || !hasValidInstanceUuid;
  const alertModalNode = originalNodeMap.get(alertModalNodeId);
  const alertModalTitle = alertModalNode
    ? `${alertModalNode.name || alertModalNode.id} · ${t('dashboard.networkTopoPopoverAlerts')} ${alertModalCount}（${t('dashboard.networkTopoLatestItems', undefined, { n: alertItems.length })}）`
    : '';
  const alertModalColumns = [
    {
      title: t('dashboard.networkTopoAlertLevel', '级别'),
      dataIndex: 'level',
      key: 'level',
    },
    {
      title: t('dashboard.networkTopoAlertType', '类型'),
      dataIndex: 'alert_type',
      key: 'alert_type',
    },
    {
      title: t('dashboard.networkTopoAlertContent', '内容'),
      dataIndex: 'content',
      key: 'content',
    },
    {
      title: t('dashboard.networkTopoAlertStartTime', '开始时间'),
      dataIndex: 'start_event_time',
      key: 'start_event_time',
    },
  ];
  
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
          centerId={String(data?.center_id || topoConfig?.instUuid || '')}
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
            onRefresh: handleExplicitRefresh,
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
            cancelHoverLeave();
            hoverNodeIdRef.current = '';
            setHoverNodeId('');
            closeContextMenu();
          }}
          onBlankContextMenu={() => closeContextMenu()}
          onNodeClick={(nodeId, event) => {
            closeContextMenu();
            if (event && isStatusTopologyBadgeTarget(event)) {
              openAlertModal(nodeId);
              return;
            }
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
                  <Button size="small" onClick={handleExplicitRefresh}>
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
      {overlayError && graphData.nodes.length > 0 && (
        <div
          className="absolute top-3 right-3 z-[8] max-w-[min(420px,72%)]"
          data-testid="status-topo-overlay-error"
        >
          <Alert
            type="error"
            showIcon
            message={t('dashboard.networkTopoStatusLoadFailed')}
            action={(
              <Button size="small" onClick={handleOverlayRetry}>
                {t('dashboard.networkTopoRefresh')}
              </Button>
            )}
          />
        </div>
      )}
      {hoverCanvasNode && !contextNodeId && (
        <div
          className={styles.popoverLayer}
          data-testid="status-topo-popover-layer"
          style={{ left: hoverPoint.x, top: hoverPoint.y }}
          onMouseEnter={cancelHoverLeave}
          onMouseLeave={scheduleClearNodeHover}
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
      <Modal
        open={Boolean(alertModalNodeId)}
        title={alertModalTitle}
        footer={null}
        onCancel={closeAlertModal}
        destroyOnHidden
        width={720}
      >
        {alertModalError ? (
          <Alert
            type="error"
            showIcon
            message={alertModalError}
            action={(
              <Button
                size="small"
                onClick={() => {
                  const monitorId = String(alertModalNode?.monitor_id || '').trim();
                  if (monitorId) void fetchAlertItems(monitorId);
                }}
              >
                {t('dashboard.networkTopoAlertModalRetry')}
              </Button>
            )}
          />
        ) : (
          <div className="max-h-[420px] overflow-auto">
            <Table
              size="small"
              rowKey="key"
              pagination={false}
              loading={alertModalLoading}
              columns={alertModalColumns}
              dataSource={alertItems}
            />
          </div>
        )}
      </Modal>
    </div>
  );
};

export default NetworkStatusTopology;
