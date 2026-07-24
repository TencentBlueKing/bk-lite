'use client';

import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import { message, Tag } from 'antd';
import { DeleteOutlined, EditOutlined } from '@ant-design/icons';
import type { Graph as X6Graph } from '@antv/x6';
import type { NetworkTopologyProps } from '@/app/ops-analysis/types/networkTopology';
import ViewWorkspace from '@/app/ops-analysis/(pages)/view/components/viewWorkspace';
import {
  AppViewFullscreenExit,
  useAppViewFullscreen,
} from '@/app/ops-analysis/components/appFullscreen';
import {
  useNetworkTopologyApi,
} from '@/app/ops-analysis/api/networkTopology';
import { useNetworkEditor } from './hooks/useNetworkEditor';
import { useNetworkLibrary } from './hooks/useNetworkLibrary';
import { useTranslation } from '@/utils/i18n';
import { useCollapsedState } from '../hooks/useCollapsedState';
import NetworkToolbar from './components/networkToolbar';
import NetworkLibrary, { getModelTagStyle } from './components/networkLibrary';
import NetworkCanvas, { buildDraftLinkId } from './components/networkCanvas';
import NetworkNodeDrawer from './components/networkNodeDrawer';
import NetworkEdgeDrawer from './components/networkEdgeDrawer';
import MonitorSourcePickerModal from './components/modals/monitorSourcePickerModal';
import ConfirmDeleteModal from './components/modals/confirmDeleteModal';
import {
  indexRuntimeNodes,
  runRuntimeTasks,
  selectLinkEndpointNodes,
} from './runtimeRequestPool';
import {
  buildLinkDetailPortRows,
  buildLinkInterfaceMetricRows,
  buildNodeDetailMetricRows,
  DEFAULT_LINK_INTERFACE_METRICS,
  buildNetworkTopologyNode,
  buildNetworkNodeClientId,
  mergeNetworkTopologyRuntimeMetrics,
  mergeNetworkTopologyRuntimeLinks,
  mergeNetworkTopologyRuntimeNodes,
  defaultNodePosition,
  filterLinksByNode,
  updateNetworkTopologyLinkTerminals,
  updateNodeMetrics,
} from './utils/networkTopologyUtils';
import type {
  MonitorSource,
  NetworkInterfaceRef,
  NetworkLinkRuntime,
  NetworkMetricRuntime,
  NetworkNodeLibraryItem,
  NetworkNodeRuntime,
  NetworkPortPair,
  NetworkTopologyConfig,
  NetworkTopologyLink,
  NetworkTopologyMetric,
  NetworkTopologyNode,
} from '@/app/ops-analysis/types/networkTopology';
import './index.module.scss';

/**
 * 网络拓扑大屏入口(design.md §7).
 *
 * 设计准则:
 * - X6 + Drawer + 自写 hooks,代码独立于 topology/,方便整体删除
 * - view_sets JSON 与其他画布一致(Dashboard/Topology/Architecture/Screen/Report)
 * - 节点外层颜色 = 阈值命中聚合结果,通过 inline style / X6 ReactShape data 传入
 * - 查看态不再调用整图 `/runtime/`,先展示配置,再逐节点/连线填充运行态
 */
export interface NetworkTopologyRef {
  hasUnsavedChanges: () => boolean;
}

const emptyConfig: NetworkTopologyConfig = { nodes: [], links: [] };
const DETAIL_POPOVER_WIDTH_PX = 420;
const DETAIL_POPOVER_MAX_HEIGHT_PX = 320;
const DETAIL_POPOVER_MAX_HEIGHT = `${DETAIL_POPOVER_MAX_HEIGHT_PX}px`;
const clampDetailPopoverLeft = (x: number) => {
  const preferredLeft = Math.max(12, x + 28);
  if (typeof window === 'undefined') return preferredLeft;
  const maxLeft = window.innerWidth - DETAIL_POPOVER_WIDTH_PX - 12;
  return Math.max(12, Math.min(preferredLeft, maxLeft));
};
const clampDetailPopoverTop = (y: number) => {
  const preferredTop = Math.max(12, y + 22);
  if (typeof window === 'undefined') return preferredTop;
  const maxTop = window.innerHeight - DETAIL_POPOVER_MAX_HEIGHT_PX - 12;
  return Math.max(12, Math.min(preferredTop, maxTop));
};
const detailPopoverClassName =
  'fixed flex w-[420px] max-w-[calc(100vw-24px)] flex-col overflow-hidden rounded-lg border bg-[var(--color-bg-1,#fff)]';
const detailPopoverFrameStyle = {
  borderColor: '#d8e3ef',
  boxShadow: '0 8px 24px rgba(37, 64, 96, 0.10), 0 0 0 1px rgba(238, 244, 251, 0.9)',
};
const detailPopoverHeaderClassName =
  'flex items-start justify-between gap-3 border-b px-3 py-2.5';
const detailPopoverHeaderStyle = {
  borderBottomColor: '#edf3f9',
};
const detailPopoverBodyClassName =
  'min-h-0 space-y-2 overflow-y-auto px-3 py-2.5 text-[12px]';
const detailSummaryCardClassName =
  'rounded-md border border-[var(--color-border-1,#e3eaf2)] bg-[color-mix(in_srgb,var(--color-fill-1,#f8fafc)_45%,var(--color-bg-1,#ffffff))] p-2.5';
const detailSummaryGridClassName =
  'grid grid-cols-2 gap-x-3 gap-y-1.5 text-[var(--color-text-1,#1f2933)]';
const detailSummaryRowClassName =
  'flex min-w-0 items-center';
const detailLabelClassName =
  'w-[64px] shrink-0 text-right text-[var(--color-text-3,#6b7280)]';
const detailColonClassName =
  'mx-1 shrink-0 text-[var(--color-text-3,#6b7280)]';
const detailSectionTitleClassName =
  'mb-1.5 text-[12px] font-semibold text-[var(--color-text-1,#1f2933)]';
const detailListRowClassName =
  'flex min-h-[28px] items-center justify-between gap-3 rounded-md border border-[var(--color-border-1,#edf1f6)] bg-[var(--color-bg-1,#fbfcfe)] px-2 py-1.5';

const groupLinkMetricRowsByInterface = (
  rows: Array<{ key: string; interfaceName: string; metricLabel: string; value: string }>,
) => {
  const groups = new Map<
    string,
    {
      key: string;
      interfaceName: string;
      metrics: Array<{ key: string; metricLabel: string; value: string }>;
    }
  >();
  rows.forEach((row) => {
    const groupKey = row.interfaceName || '--';
    const group = groups.get(groupKey) ?? {
      key: groupKey,
      interfaceName: groupKey,
      metrics: [],
    };
    group.metrics.push({
      key: row.key,
      metricLabel: row.metricLabel,
      value: row.value,
    });
    groups.set(groupKey, group);
  });
  return Array.from(groups.values());
};

const NetworkTopology = forwardRef<NetworkTopologyRef, NetworkTopologyProps>(
  ({ selectedNetworkTopology }, ref) => {
    const api = useNetworkTopologyApi();
    const { t } = useTranslation();
    const canvasId = selectedNetworkTopology?.data_id;
    const [config, setConfig] = useState<NetworkTopologyConfig>(emptyConfig);
    const [savedConfig, setSavedConfig] = useState<NetworkTopologyConfig>(emptyConfig);
    const [metricOptions, setMetricOptions] = useState<
      NetworkNodeDrawerPropsMetric[]
    >([]);
    const [metricOptionsLoading, setMetricOptionsLoading] = useState(false);
    const [dimensionValueOptions, setDimensionValueOptions] = useState<
      Record<string, Array<{ label: string; value: string }>>
    >({});
    const [dimensionValuesLoading, setDimensionValuesLoading] = useState(false);
    const [dimensionLoadError, setDimensionLoadError] = useState<string | null>(null);
    const [sourceInterfaces, setSourceInterfaces] = useState<NetworkInterfaceRef[]>(
      [],
    );
    const [targetInterfaces, setTargetInterfaces] = useState<NetworkInterfaceRef[]>(
      [],
    );
    const [drawingSource, setDrawingSource] = useState<
      | { item: NetworkNodeLibraryItem; position: { x: number; y: number } }
      | null
    >(null);
    const [deleteModal, setDeleteModal] = useState<
      | { kind: 'node'; node: NetworkTopologyNode }
      | { kind: 'link'; link: NetworkTopologyLink }
      | null
    >(null);
    const [nodeContextMenu, setNodeContextMenu] = useState<{
      node: NetworkTopologyNode;
      x: number;
      y: number;
    } | null>(null);
    const [linkContextMenu, setLinkContextMenu] = useState<{
      link: NetworkTopologyLink;
      x: number;
      y: number;
    } | null>(null);
    const [nodeDetailPoint, setNodeDetailPoint] = useState<{
      x: number;
      y: number;
    } | null>(null);
    const [linkDetailPoint, setLinkDetailPoint] = useState<{
      x: number;
      y: number;
    } | null>(null);
    const [linkConfigOpen, setLinkConfigOpen] = useState(false);
    const [saving, setSaving] = useState(false);
    const [viewSetsLoading, setViewSetsLoading] = useState(false);
    const [interfacesLoading, setInterfacesLoading] = useState(false);
    const [interfaceLoadMessage, setInterfaceLoadMessage] = useState<string | null>(null);
    const [runtimeMetricOverrides, setRuntimeMetricOverrides] = useState<
      Record<string, NetworkMetricRuntime[]>
    >({});
    const [runtimeLinkOverrides, setRuntimeLinkOverrides] = useState<
      Record<string, NetworkLinkRuntime>
    >({});
    const [runtimeInterfaceSummaryOverrides, setRuntimeInterfaceSummaryOverrides] =
      useState<Record<string, NonNullable<NetworkNodeRuntime['interface_summary']>>>({});
    const nodeMetricsRequestGenerationRef = useRef(0);
    const linkInterfacesRequestGenerationRef = useRef(0);
    const runtimeLoadGenerationRef = useRef(0);
    const runtimeRefreshPromiseRef = useRef<{
      canvasId: string;
      promise: Promise<void>;
    } | null>(null);
    const [graph, setGraph] = useState<X6Graph | null>(null);
    const [refreshIntervalMs, setRefreshIntervalMs] = useState(0);
    const { isFullscreen, enterFullscreen, exitFullscreen } =
      useAppViewFullscreen();

    const revertConfig = useCallback(
      () => setConfig(savedConfig),
      [savedConfig],
    );

    const editor = useNetworkEditor({ config, savedConfig });
    // 设备库侧栏的展开/收起状态(参考 topology 侧栏的折叠交互)。
    const libraryCollapsed = useCollapsedState(true);

    const loadConfiguredRuntime = useCallback(
      (id: string | number, runtimeConfig: NetworkTopologyConfig): Promise<void> => {
        const runtimeCanvasId = String(id);
        const current = runtimeRefreshPromiseRef.current;
        if (current?.canvasId === runtimeCanvasId) return current.promise;

        const generation = ++runtimeLoadGenerationRef.current;
        const isCurrent = () => runtimeLoadGenerationRef.current === generation;
        const runtimeNodeIndex = indexRuntimeNodes(runtimeConfig.nodes);

        const nodeTasks = runtimeConfig.nodes
          .filter((node) => node.metrics.length > 0)
          .map((node) => async () => {
            const metrics = node.metrics;
            const metricRequests = metrics.map((metric) => {
              const requestId = buildMetricRuntimeRequestId(node.id, metric);
              return {
                request_id: requestId,
                node_ref: nodeRef(node),
                metric_ref: {
                  metric_field: metric.metric_field,
                  result_table_id: metric.result_table_id,
                },
                dimensions: metric.dimensions ?? {},
                condition_filter: metric.condition_filter ?? [],
                display_mode:
                  metric.display_mode ??
                  ((metric.condition_filter ?? []).length > 0 ||
                  Object.keys(metric.dimensions ?? {}).length > 0
                    ? 'dimension'
                    : 'aggregate'),
                aggregate_type: metric.aggregate_type ?? 'sum',
              };
            });
            const loadingMetrics = metrics.map((metric, index) =>
              toRuntimeMetric(
                {
                  request_id: metricRequests[index].request_id,
                  status: 'loading',
                  value: null,
                },
                metric,
                metricRequests[index].request_id,
              ),
            );
            if (isCurrent()) {
              setRuntimeMetricOverrides((prev) => ({
                ...prev,
                [node.id]: mergeNetworkTopologyRuntimeMetrics(
                  prev[node.id] ?? [],
                  loadingMetrics,
                ),
              }));
            }
            try {
              const res = await api.getMetricValues(runtimeCanvasId, metricRequests);
              if (!isCurrent()) return;
              const itemByRequestId = new Map(
                (res.items ?? []).map((item) => [item.request_id, item]),
              );
              const runtimeMetrics = metrics.map((metric, index) => {
                const requestId = metricRequests[index].request_id;
                return toRuntimeMetric(itemByRequestId.get(requestId), metric, requestId);
              });
              setRuntimeMetricOverrides((prev) => ({
                ...prev,
                [node.id]: mergeNetworkTopologyRuntimeMetrics(
                  prev[node.id] ?? [],
                  runtimeMetrics,
                ),
              }));
            } catch (err) {
              if (!isCurrent()) return;
              const errorMetrics = metrics.map((metric, index) =>
                toRuntimeMetric(
                  {
                    request_id: metricRequests[index].request_id,
                    status: 'error',
                    error_message: err instanceof Error ? err.message : String(err),
                  },
                  metric,
                  metricRequests[index].request_id,
                ),
              );
              setRuntimeMetricOverrides((prev) => ({
                ...prev,
                [node.id]: mergeNetworkTopologyRuntimeMetrics(
                  prev[node.id] ?? [],
                  errorMetrics,
                ),
              }));
            }
          });

        const linkTasks = runtimeConfig.links
          .filter((link) => !link.is_draft && link.port_pairs.length > 0)
          .map((link) => async () => {
            try {
              const res = await api.getLinkRuntime(runtimeCanvasId, {
                link,
                nodes: selectLinkEndpointNodes(runtimeNodeIndex, link),
              });
              if (!isCurrent()) return;
              if (res?.link) {
                setRuntimeLinkOverrides((prev) => ({
                  ...prev,
                  [res.link!.id]: res.link!,
                }));
              }
              const summaries = res?.node_interface_summary ?? {};
              if (Object.keys(summaries).length > 0) {
                setRuntimeInterfaceSummaryOverrides((prev) => ({
                  ...prev,
                  ...summaries,
                }));
              }
            } catch {
              // 单条连线失败时保留旧值/未知态,不阻塞其他运行态返回。
            }
          });

        const task = runRuntimeTasks([...nodeTasks, ...linkTasks], { isActive: isCurrent })
          .then(() => undefined)
          .finally(() => {
            if (runtimeRefreshPromiseRef.current?.promise === task) {
              runtimeRefreshPromiseRef.current = null;
            }
          });
        runtimeRefreshPromiseRef.current = { canvasId: runtimeCanvasId, promise: task };
        return task;
      },
      [api],
    );

    // 加载画布 view_sets(GET /config/ 由后端 network_topology_view 提供,
    // 失败时降级到空画布,显示「加载画布失败」toast)。
    useEffect(() => {
      if (!canvasId) {
        nodeMetricsRequestGenerationRef.current += 1;
        linkInterfacesRequestGenerationRef.current += 1;
        runtimeLoadGenerationRef.current += 1;
        runtimeRefreshPromiseRef.current = null;
        setConfig(emptyConfig);
        setSavedConfig(emptyConfig);
        setRuntimeMetricOverrides({});
        setRuntimeLinkOverrides({});
        setRuntimeInterfaceSummaryOverrides({});
        editor.resetConfig(emptyConfig);
        return;
      }
      const id = canvasId;
      let active = true;
      nodeMetricsRequestGenerationRef.current += 1;
      linkInterfacesRequestGenerationRef.current += 1;
      runtimeLoadGenerationRef.current += 1;
      runtimeRefreshPromiseRef.current = null;
      setRuntimeMetricOverrides({});
      setRuntimeLinkOverrides({});
      setRuntimeInterfaceSummaryOverrides({});
      setViewSetsLoading(true);
      api
        .getViewSets(id)
        .then((viewSets) => {
          if (!active) return;
          const next = viewSets ?? emptyConfig;
          setConfig(next);
          setSavedConfig(next);
          setRuntimeMetricOverrides({});
          setRuntimeLinkOverrides({});
          setRuntimeInterfaceSummaryOverrides({});
          editor.resetConfig(next);
          void loadConfiguredRuntime(id, next);
        })
        .catch((err: unknown) => {
          if (!active) return;
          message.error(
            err instanceof Error
              ? err.message
              : t('opsAnalysis.networkTopology.loadFailed'),
          );
        })
        .finally(() => active && setViewSetsLoading(false));
      return () => {
        active = false;
      };
      // 故意省略 api/editor 等稳定依赖,避免画布切换以外的因素触发重新拉取。
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [canvasId]);

    const loadNodeModels = useCallback(
      (id: string | number) => api.getNodeModels(id),
      [api],
    );
    const loadLibraryNodes = useCallback(
      (id: string | number, params?: { bk_obj_id?: string; keyword?: string }) =>
        api.getNodes(id, params),
      [api],
    );
    const library = useNetworkLibrary({
      canvasId,
      enabled: Boolean(canvasId),
      loadModels: loadNodeModels,
      loadNodes: loadLibraryNodes,
    });

    const runtimeLinks = useMemo(() => {
      return mergeNetworkTopologyRuntimeLinks([], runtimeLinkOverrides);
    }, [runtimeLinkOverrides]);

    const nodeById = useMemo(() => {
      const map = new Map<string, NetworkTopologyNode>();
      config.nodes.forEach((node) => map.set(node.id, node));
      return map;
    }, [config.nodes]);

    const runtimeNodes: NetworkNodeRuntime[] = useMemo(() => {
      return mergeNetworkTopologyRuntimeNodes(
        [],
        config.nodes,
        runtimeMetricOverrides,
        runtimeInterfaceSummaryOverrides,
      );
    }, [
      config.nodes,
      runtimeMetricOverrides,
      runtimeInterfaceSummaryOverrides,
    ]);

    const runtimeNodeMap = useMemo(() => {
      const map = new Map<string, NetworkNodeRuntime>();
      runtimeNodes.forEach((node) => map.set(node.id, node));
      return map;
    }, [runtimeNodes]);

    useEffect(() => {
      if (!canvasId || refreshIntervalMs <= 0) return undefined;
      const timer = setInterval(() => {
        void loadConfiguredRuntime(canvasId, config);
      }, refreshIntervalMs);
      return () => clearInterval(timer);
    }, [canvasId, config, loadConfiguredRuntime, refreshIntervalMs]);

    const loadNodeMetrics = useCallback(
      (node: NetworkTopologyNode) => {
        if (!canvasId) return;
        const generation = ++nodeMetricsRequestGenerationRef.current;
        setDimensionValueOptions({});
        setMetricOptionsLoading(true);
        setMetricOptions([]);
        api
          .getNodeMetrics(String(canvasId), nodeRef(node))
          .then((metricsRes) => {
            if (nodeMetricsRequestGenerationRef.current !== generation) return;
            const items = (metricsRes as { items?: unknown[] })?.items ?? [];
            setMetricOptions(
              items.map((item) => {
                const m = item as Record<string, unknown>;
                return {
                  metric_field: String(m.metric_field ?? ''),
                  result_table_id: String(m.result_table_id ?? ''),
                  display_name: String(
                    m.display_name ?? m.field_cn_name ?? m.field_name ?? m.metric_field ?? '',
                  ),
                  unit: String(m.unit ?? ''),
                  supported_dimensions: Array.isArray(m.supported_dimensions)
                    ? (m.supported_dimensions as string[])
                    : [],
                };
              }),
            );
          })
          .catch(() => {
            if (nodeMetricsRequestGenerationRef.current !== generation) return;
            setMetricOptions([]);
          })
          .finally(() => {
            if (nodeMetricsRequestGenerationRef.current === generation) {
              setMetricOptionsLoading(false);
            }
          });
      },
      [api, canvasId],
    );

    const upsertNode = useCallback(
      (
        item: NetworkNodeLibraryItem,
        source: MonitorSource,
        position: { x: number; y: number },
      ) => {
        const newNode = buildNetworkTopologyNode(item, source, position);
        if (nodeById.has(newNode.id)) {
          message.warning(t('opsAnalysis.networkTopology.deviceAlreadyInCanvas'));
        } else {
          setConfig((prev) => ({ ...prev, nodes: [...prev.nodes, newNode] }));
        }
        editor.setSelectedNodeId(newNode.id);
        editor.setSelectedLinkId(null);
        setInterfaceLoadMessage(null);
        loadNodeMetrics(newNode);
      },
      [editor, loadNodeMetrics, nodeById, t],
    );

    const handleLibraryDragStart = useCallback(() => {
      if (!editor.editMode) {
        message.info(t('opsAnalysis.networkTopology.enterEditModeFirstForDrag'));
        return;
      }
      // dragstart 只是触发 dataTransfer(JSON payload 由 NetworkLibrary 写入),
      // 实际插入由 NetworkCanvas.onDropDevice 在 drop 事件中处理。
    }, [editor.editMode, t]);

    const handleCanvasDrop = useCallback(
      (item: NetworkNodeLibraryItem, position: { x: number; y: number }) => {
        if (!editor.editMode) {
          message.info(t('opsAnalysis.networkTopology.enterEditModeFirst'));
          return;
        }
        if (library.isSingleSource(item)) {
          upsertNode(item, item.monitor_sources[0], position);
          return;
        }
        setDrawingSource({ item, position });
      },
      [editor.editMode, library, upsertNode],
    );

    const handleLibraryAdd = useCallback(
      (item: NetworkNodeLibraryItem) => {
        handleCanvasDrop(item, defaultNodePosition(config.nodes.length));
      },
      [config.nodes.length, handleCanvasDrop],
    );

    const handleSelectNode = useCallback(
      (
        id: string | null,
        options?: { point?: { x: number; y: number } },
      ) => {
        editor.setSelectedNodeId(id);
        editor.setSelectedLinkId(null);
        setInterfaceLoadMessage(null);
        setNodeDetailPoint(!editor.editMode && id ? options?.point ?? null : null);
        if (id) {
          const node = nodeById.get(id);
          if (node && canvasId && editor.editMode) {
            loadNodeMetrics(node);
          }
        } else {
          nodeMetricsRequestGenerationRef.current += 1;
          setMetricOptions([]);
          setMetricOptionsLoading(false);
          setDimensionValueOptions({});
          setNodeDetailPoint(null);
        }
      },
      // editMode 必须在依赖中,否则进入编辑模式后会读到旧的 false,
      // 抽屉虽能打开但不会请求指标列表。
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [canvasId, editor.editMode, loadNodeMetrics, nodeById],
    );

    const loadLinkInterfaces = useCallback(
      (link: NetworkTopologyLink) => {
        if (!canvasId) return;
        const sourceNode = nodeById.get(link.source_node_id);
        const targetNode = nodeById.get(link.target_node_id);
        if (!sourceNode || !targetNode) return;
        const generation = ++linkInterfacesRequestGenerationRef.current;
        setInterfaceLoadMessage(null);
        setSourceInterfaces([]);
        setTargetInterfaces([]);
        setInterfacesLoading(true);
        Promise.all([
          api.getNodeInterfaces(String(canvasId), nodeRef(sourceNode)),
          api.getNodeInterfaces(String(canvasId), nodeRef(targetNode)),
        ])
          .then(([src, tgt]) => {
            if (linkInterfacesRequestGenerationRef.current !== generation) return;
            setSourceInterfaces(extractInterfaceItems(src));
            setTargetInterfaces(extractInterfaceItems(tgt));
            setInterfaceLoadMessage(buildInterfaceLoadMessage(src, tgt));
          })
          .catch((err) => {
            if (linkInterfacesRequestGenerationRef.current !== generation) return;
            setInterfaceLoadMessage(
              err instanceof Error
                ? err.message
                : t('opsAnalysis.networkTopology.link.loadInterfacesFailed'),
            );
          })
          .finally(() => {
            if (linkInterfacesRequestGenerationRef.current === generation) {
              setInterfacesLoading(false);
            }
          });
      },
      // 故意省略 api/editor/handleSelectNode 等稳定依赖。
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [canvasId, nodeById],
    );

    const handleSelectLink = useCallback(
      (
        id: string | null,
        options?: {
          point?: { x: number; y: number };
          openConfig?: boolean;
        },
      ) => {
        const link = id ? config.links.find((l) => l.id === id) : null;
        editor.setSelectedLinkId(id);
        editor.setSelectedNodeId(null);
        setNodeDetailPoint(null);
        setLinkDetailPoint(
          link && !options?.openConfig
            ? options?.point ?? { x: 12, y: 12 }
            : null,
        );
        setLinkConfigOpen(Boolean(id && options?.openConfig));
        if (!id || !canvasId || !options?.openConfig) {
          linkInterfacesRequestGenerationRef.current += 1;
          setSourceInterfaces([]);
          setTargetInterfaces([]);
          setInterfacesLoading(false);
          setInterfaceLoadMessage(null);
          return;
        }
        if (!link) return;
        loadLinkInterfaces(link);
      },
      [canvasId, config.links, editor, loadLinkInterfaces],
    );

    const onSaveConfig = useCallback(async () => {
      if (!canvasId) return;
      const configToSave: NetworkTopologyConfig = {
        ...config,
        links: config.links.map((link) => {
          const edge = graph?.getCellById(link.id);
          if (!edge?.isEdge()) return link;
          const vertices = edge
            .getVertices()
            .map((point) => ({ x: point.x, y: point.y }));
          const source = edge.getSource() as { cell?: unknown; port?: unknown };
          const target = edge.getTarget() as { cell?: unknown; port?: unknown };
          return {
            ...link,
            source_node_id:
              typeof source.cell === 'string' ? source.cell : link.source_node_id,
            target_node_id:
              typeof target.cell === 'string' ? target.cell : link.target_node_id,
            source_port_id:
              typeof source.port === 'string' ? source.port : link.source_port_id,
            target_port_id:
              typeof target.port === 'string' ? target.port : link.target_port_id,
            vertices,
          };
        }),
      };
      setSaving(true);
      try {
        const next = await api.saveViewSets(String(canvasId), configToSave);
        setConfig(next);
        setSavedConfig(next);
        editor.resetConfig(next);
        setNodeDetailPoint(null);
        setLinkDetailPoint(null);
        setLinkConfigOpen(false);
        message.success(t('opsAnalysis.networkTopology.saveSuccess'));
      } catch (err) {
        message.error(
          err instanceof Error
            ? err.message
            : t('opsAnalysis.networkTopology.saveFailed'),
        );
      } finally {
        setSaving(false);
      }
    }, [api, canvasId, config, editor, graph, t]);

    const onCancelEdit = useCallback(() => {
      editor.exitEditMode(revertConfig);
      setNodeDetailPoint(null);
      setLinkDetailPoint(null);
      setLinkConfigOpen(false);
    }, [editor, revertConfig]);

    const onEnterEdit = useCallback(() => {
      editor.setSelectedNodeId(null);
      editor.setSelectedLinkId(null);
      setNodeDetailPoint(null);
      setLinkDetailPoint(null);
      setLinkConfigOpen(false);
      setNodeContextMenu(null);
      setLinkContextMenu(null);
      editor.enterEditMode();
    }, [editor]);

    const onSaveNodePosition = useCallback(
      (id: string, position: { x: number; y: number }) => {
        setConfig((prev) => ({
          ...prev,
          nodes: prev.nodes.map((node) =>
            node.id === id ? { ...node, position } : node,
          ),
        }));
      },
      [],
    );

    const onSaveLinkVertices = useCallback(
      (id: string, vertices: Array<{ x: number; y: number }>) => {
        setConfig((prev) => ({
          ...prev,
          links: prev.links.map((link) =>
            link.id === id ? { ...link, vertices } : link,
          ),
        }));
      },
      [],
    );

    const onSaveLinkTerminals = useCallback(
      (
        id: string,
        terminals: {
          source_node_id: string;
          target_node_id: string;
          source_port_id?: string;
          target_port_id?: string;
        },
      ) => {
        setConfig((prev) => ({
          ...prev,
          links: updateNetworkTopologyLinkTerminals(prev.links, id, terminals),
        }));
      },
      [],
    );

    const onNodeContextMenu = useCallback(
      (id: string, point: { x: number; y: number }) => {
        if (!editor.editMode) return;
        const node = nodeById.get(id);
        if (!node) return;
        setNodeContextMenu({ node, x: point.x, y: point.y });
        setLinkContextMenu(null);
      },
      [editor.editMode, nodeById],
    );

    const onLinkContextMenu = useCallback(
      (id: string, point: { x: number; y: number }) => {
        if (!editor.editMode) return;
        const link = config.links.find((item) => item.id === id);
        if (!link) return;
        setLinkContextMenu({ link, x: point.x, y: point.y });
        setNodeContextMenu(null);
      },
      [config.links, editor.editMode],
    );

    // 删除节点 / 连线 — 应用层校验 + 级联
    const onConfirmDelete = useCallback(() => {
      if (!deleteModal) return;
      if (deleteModal.kind === 'node') {
        const nodeId = deleteModal.node.id;
        setConfig((prev) => ({
          nodes: prev.nodes.filter((node) => node.id !== nodeId),
          links: filterLinksByNode(prev.links, nodeId),
        }));
      } else {
        setConfig((prev) => ({
          ...prev,
          links: prev.links.filter((link) => link.id !== deleteModal.link.id),
        }));
      }
      setDeleteModal(null);
    }, [deleteModal]);

    const loadDraftMetricRuntime = useCallback(
      async (node: NetworkTopologyNode, metrics: NetworkTopologyMetric[]) => {
        if (!canvasId || metrics.length === 0) return;
        const metricRequests = metrics.map((metric) => {
          const requestId = buildMetricRuntimeRequestId(node.id, metric);
          return {
            request_id: requestId,
            node_ref: nodeRef(node),
            metric_ref: {
              metric_field: metric.metric_field,
              result_table_id: metric.result_table_id,
            },
            dimensions: metric.dimensions ?? {},
            condition_filter: metric.condition_filter ?? [],
            display_mode:
              metric.display_mode ??
              ((metric.condition_filter ?? []).length > 0 ||
              Object.keys(metric.dimensions ?? {}).length > 0
                ? 'dimension'
                : 'aggregate'),
            aggregate_type: metric.aggregate_type ?? 'sum',
          };
        });
        const loadingMetrics = metrics.map((metric, index) =>
          toRuntimeMetric(
            {
              request_id: metricRequests[index].request_id,
              status: 'loading',
              value: null,
            },
            metric,
            metricRequests[index].request_id,
          ),
        );
        setRuntimeMetricOverrides((prev) => ({
          ...prev,
          [node.id]: mergeNetworkTopologyRuntimeMetrics(prev[node.id] ?? [], loadingMetrics),
        }));
        try {
          const res = await api.getMetricValues(String(canvasId), metricRequests);
          const itemByRequestId = new Map(
            (res.items ?? []).map((item) => [item.request_id, item]),
          );
          const runtimeMetrics = metrics.map((metric, index) => {
            const requestId = metricRequests[index].request_id;
            return toRuntimeMetric(itemByRequestId.get(requestId), metric, requestId);
          });
          setRuntimeMetricOverrides((prev) => ({
            ...prev,
            [node.id]: mergeNetworkTopologyRuntimeMetrics(prev[node.id] ?? [], runtimeMetrics),
          }));
          const failedMetric = runtimeMetrics.find((metric) => metric.status === 'error');
          if (failedMetric) {
            message.warning(
              failedMetric.error_message ||
                failedMetric.error_code ||
                t('opsAnalysis.networkTopology.node.valueNoData'),
            );
          }
        } catch (err) {
          const errorMetrics = metrics.map((metric, index) =>
            toRuntimeMetric(
              {
                request_id: metricRequests[index].request_id,
                status: 'error',
                error_message:
                  err instanceof Error
                    ? err.message
                    : t('opsAnalysis.networkTopology.node.valueFailed'),
              },
              metric,
              metricRequests[index].request_id,
            ),
          );
          setRuntimeMetricOverrides((prev) => ({
            ...prev,
            [node.id]: mergeNetworkTopologyRuntimeMetrics(prev[node.id] ?? [], errorMetrics),
          }));
        }
      },
      [api, canvasId, t],
    );

    // 节点 Drawer handlers: Drawer 内部维护草稿,只有点击底部「确定」
    // 才一次性提交到画布配置,避免删除/编辑指标时画布提前变化。
    const onCommitNodeMetrics = useCallback(
      (nodeId: string, metrics: NetworkTopologyMetric[]) => {
        const node = nodeById.get(nodeId);
        const normalizedMetrics = metrics.map((metric, index) => ({
          ...metric,
          sort_order: index,
        }));
        const committedKeys = new Set(
          normalizedMetrics.map(
            (metric) => buildMetricRuntimeRequestId(nodeId, metric),
          ),
        );
        setConfig((prev) => ({
          ...prev,
          nodes: updateNodeMetrics(prev.nodes, nodeId, normalizedMetrics),
        }));
        setRuntimeMetricOverrides((prev) => ({
          ...prev,
          [nodeId]: (prev[nodeId] ?? []).filter((metric) =>
            committedKeys.has(metricRuntimeKey(metric)),
          ),
        }));
        if (node) {
          void loadDraftMetricRuntime(node, normalizedMetrics);
        }
      },
      [loadDraftMetricRuntime, nodeById],
    );

    const onLoadMetricDimensionValues = useCallback(
      async (
        metric: NetworkNodeDrawerPropsMetric,
        requestedDimensionKeys?: string[],
      ) => {
        if (!canvasId || !editor.selectedNodeId) return;
        const node = nodeById.get(editor.selectedNodeId);
        const dimensionKeys = Array.from(
          new Set(
            (requestedDimensionKeys?.length
              ? requestedDimensionKeys
              : metric.supported_dimensions ?? []
            ).filter(Boolean),
          ),
        );
        if (!node || dimensionKeys.length === 0) {
          setDimensionLoadError(null);
          return;
        }
        setDimensionValuesLoading(true);
        setDimensionLoadError(null);
        try {
          const res = await api.getDimensionValues(String(canvasId), {
            node_ref: nodeRef(node),
            metric_ref: {
              metric_field: metric.metric_field,
              result_table_id: metric.result_table_id,
            },
            dimension_keys: dimensionKeys,
          });
          const next = ((res as { items?: Array<{
            dimension: string;
            list: Array<{ label: string; value: string }>;
          }> })?.items ?? []).reduce<Record<string, Array<{ label: string; value: string }>>>(
            (acc, item) => {
              acc[item.dimension] = item.list ?? [];
              return acc;
            },
            {},
          );
          setDimensionValueOptions((prev) => ({ ...prev, ...next }));
          setDimensionLoadError(null);
        } catch {
          setDimensionLoadError(
            t('opsAnalysis.networkTopology.node.dimensionLoadFailedDescription'),
          );
        } finally {
          setDimensionValuesLoading(false);
        }
      },
      [api, canvasId, editor.selectedNodeId, nodeById, t],
    );

    // 连线 Drawer handlers
    const onCommitLink = useCallback(
      (linkId: string, portPairs: NetworkPortPair[], interfaceMetrics: string[]) => {
        const prev = config;
        let nextLink: NetworkTopologyLink | null = null;
        const nextConfig: NetworkTopologyConfig = {
          ...prev,
          links: prev.links.map((link) => {
            if (link.id !== linkId) return link;
            // 用户完成接口配对：草稿 -> 正式连线。
            // 草稿允许空 port_pairs（拖出画布磁铁但还没选接口的状态），
            // 正式连线必须至少 1 对接口——后端 canvas_config._validate_payload
            // 会强制这个不变量；如果 commit 时还空就保持 is_draft 让
            // 用户看到草稿态继续编辑。
            const isComplete = portPairs.length > 0;
            nextLink = {
              ...link,
              port_pairs: portPairs,
              interface_metrics: interfaceMetrics,
              is_draft: isComplete ? false : true,
            };
            return nextLink;
          }),
        };
        setConfig(nextConfig);
        if (!canvasId || !nextLink || portPairs.length === 0) {
          setRuntimeLinkOverrides((prevOverrides) => {
            const nextOverrides = { ...prevOverrides };
            delete nextOverrides[linkId];
            return nextOverrides;
          });
          return;
        }
        void api
          .getLinkRuntime(String(canvasId), {
            link: nextLink,
            nodes: selectLinkEndpointNodes(indexRuntimeNodes(prev.nodes), nextLink),
          })
          .then((res) => {
            if (res?.link) {
              setRuntimeLinkOverrides((prevOverrides) => ({
                ...prevOverrides,
                [res.link!.id]: res.link!,
              }));
            }
            const summaries = res?.node_interface_summary ?? {};
            if (Object.keys(summaries).length > 0) {
              setRuntimeInterfaceSummaryOverrides((prevOverrides) => ({
                ...prevOverrides,
                ...summaries,
              }));
            }
          })
          .catch((err: unknown) => {
            message.warning(
              err instanceof Error
                ? err.message
                : t('opsAnalysis.networkTopology.link.loadRuntimeFailed'),
            );
          });
      },
      [api, canvasId, config, t],
    );

    const onConnectPorts = useCallback(
      (
        sourceId: string,
        targetId: string,
        sourcePortId?: string,
        targetPortId?: string,
      ) => {
        if (!editor.editMode) return { cancel: true as const };
        if (!nodeById.get(sourceId) || !nodeById.get(targetId)) {
          return { cancel: true as const };
        }
        const linkId = buildDraftLinkId(config.links);
        // 草稿连线必须显式标 is_draft=true，否则后端 canvas_config
        // 校验会 400 拒绝（非草稿连线至少 1 对接口）。
        const newLink: NetworkTopologyLink = {
          id: linkId,
          source_node_id: sourceId,
          target_node_id: targetId,
          source_port_id: sourcePortId,
          target_port_id: targetPortId,
          port_pairs: [],
          interface_metrics: DEFAULT_LINK_INTERFACE_METRICS,
          is_draft: true,
        };
        setConfig((prev) => ({ ...prev, links: [...prev.links, newLink] }));
        editor.setSelectedLinkId(linkId);
        editor.setSelectedNodeId(null);
        setNodeDetailPoint(null);
        setLinkDetailPoint(null);
        setLinkConfigOpen(true);
        // 自动打开 Drawer。新连线还没进入当前 render 的 config.links，
        // 这里按 newLink 直接加载接口，避免读到旧闭包。
        loadLinkInterfaces(newLink);
        return { linkId };
      },
      [config.links, editor, loadLinkInterfaces, nodeById],
    );

    useImperativeHandle(
      ref,
      () => ({
        hasUnsavedChanges: () => editor.isDirty,
      }),
      [editor.isDirty],
    );

    const editingNode = editor.selectedNodeId
      ? nodeById.get(editor.selectedNodeId) ?? null
      : null;
    const editingLink = editor.selectedLinkId
      ? config.links.find((l) => l.id === editor.selectedLinkId) ?? null
      : null;
    const editingLinkRuntime = useMemo(() => {
      if (!editingLink) return undefined;
      return (runtimeLinks ?? []).find((l) => l.id === editingLink.id);
    }, [editingLink, runtimeLinks]);
    const editingLinkSource = editingLink
      ? nodeById.get(editingLink.source_node_id) ?? null
      : null;
    const editingLinkTarget = editingLink
      ? nodeById.get(editingLink.target_node_id) ?? null
      : null;
    const editingLinkPortRows = editingLink
      ? buildLinkDetailPortRows(editingLink, editingLinkRuntime)
      : [];
    const interfaceMetricLabels = useMemo<Record<string, string>>(
      () => ({
        ifInOctets_5min: t('opsAnalysis.networkTopology.link.metricIfInOctets'),
        ifOutOctets_5min: t('opsAnalysis.networkTopology.link.metricIfOutOctets'),
        ifHighSpeed: t('opsAnalysis.networkTopology.link.metricIfHighSpeed'),
        ifOutDiscards_5min: t('opsAnalysis.networkTopology.link.metricIfOutDiscards'),
        ifInDiscards_5min: t('opsAnalysis.networkTopology.link.metricIfInDiscards'),
        ifInErrors_5min: t('opsAnalysis.networkTopology.link.metricIfInErrors'),
        ifOutErrors_5min: t('opsAnalysis.networkTopology.link.metricIfOutErrors'),
      }),
      [t],
    );
    const editingLinkMetricRows = editingLink
      ? buildLinkInterfaceMetricRows(editingLink, editingLinkRuntime, interfaceMetricLabels)
      : [];
    const editingLinkMetricGroups =
      groupLinkMetricRowsByInterface(editingLinkMetricRows);
    const editingNodeRuntime = editingNode
      ? runtimeNodeMap.get(buildNetworkNodeClientId(editingNode))
      : undefined;
    const editingNodeMetricRows = editingNode
      ? buildNodeDetailMetricRows(editingNode, editingNodeRuntime)
      : [];

    const sidebarExtra = (
      <NetworkToolbar
        editMode={editor.editMode}
        dirty={editor.isDirty}
        saving={saving}
        onZoomIn={() => graph?.zoom(0.1)}
        onZoomOut={() => graph?.zoom(-0.1)}
        onFit={() => {
          graph?.zoomToFit({ padding: 32, maxScale: 1 });
          graph?.centerContent();
        }}
        isFullscreen={isFullscreen}
        onFullscreenToggle={() => {
          if (isFullscreen) {
            exitFullscreen();
            return;
          }
          if (editor.editMode) {
            editor.exitEditMode(revertConfig);
          }
          editor.setSelectedNodeId(null);
          editor.setSelectedLinkId(null);
          setNodeDetailPoint(null);
          setLinkDetailPoint(null);
          setLinkConfigOpen(false);
          setNodeContextMenu(null);
          setLinkContextMenu(null);
          setDeleteModal(null);
          enterFullscreen();
        }}
        onRefresh={() => {
          if (canvasId) void loadConfiguredRuntime(canvasId, config);
        }}
        onFrequencyChange={setRefreshIntervalMs}
        onEnterEdit={onEnterEdit}
        onCancelEdit={onCancelEdit}
        onSave={() => void onSaveConfig()}
      />
    );

    // 模态/Drawer 集合 —— 全屏和非全屏两路渲染都需要,提到外层复用

    // 画布主体(左设备库 + 右画布)。
    // 用 flex 而非 grid,这样设备库的宽度变化(w-72 / w-0)能让画布真正自适应。
    // 模板(gridTemplateColumns: '292px minmax(0, 1fr)')会把第一列硬钉 292px,画布不变宽。
    return (
      <>
        <div
          className={`flex flex-col ${
            isFullscreen
              ? 'fixed inset-0 z-[2100] h-screen w-screen overflow-hidden bg-[var(--color-bg-2)]'
              : 'h-full flex-1 overflow-hidden'
          }`}
        >
          <AppViewFullscreenExit
            visible={isFullscreen}
            onExit={exitFullscreen}
          />
          <ViewWorkspace
            selectedItem={selectedNetworkTopology}
            loading={viewSetsLoading}
            titleFallback={t('opsAnalysis.networkTopology.title')}
            emptyDescription={t('opsAnalysis.networkTopology.selectFirst')}
            toolbar={
              isFullscreen
                ? null
                : selectedNetworkTopology
                  ? sidebarExtra
                  : null
            }
            headerVisible={!isFullscreen}
            contentClassName={
              isFullscreen
                ? 'bg-[var(--color-bg-2)] p-0'
                : 'bg-[var(--color-bg-2)] px-4 pb-4'
            }
          >
            <div
              className="flex h-full min-h-0 gap-[10px]"
              data-testid="network-topology-workspace"
            >
              {!isFullscreen && (
                <section
                  className="flex shrink-0 min-h-0 flex-col overflow-visible rounded-lg border border-[var(--color-border-1,#d9e0e8)] bg-[var(--color-bg-1,#fff)] shadow-[0_10px_24px_rgba(34,47,62,0.05)]"
                  data-testid="network-topology-library-panel"
                >
                  <NetworkLibrary
                    models={library.models}
                    nodes={library.nodes}
                    loading={library.loading}
                    error={library.error ?? ''}
                    modelFilter={library.modelFilter}
                    keyword={library.keyword}
                    onModelFilterChange={library.setModelFilter}
                    onKeywordChange={library.setKeyword}
                    onReload={() => void library.reload()}
                    onDragStart={handleLibraryDragStart}
                    onAddClick={handleLibraryAdd}
                    disabled={!editor.editMode}
                    collapsed={libraryCollapsed.collapsed}
                    onCollapsedChange={libraryCollapsed.setCollapsed}
                  />
                </section>
              )}

              <section
                className={`flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-[var(--color-bg-1,#fff)] ${
                  isFullscreen
                    ? ''
                    : 'rounded-lg border border-[var(--color-border-1,#d9e0e8)] shadow-[0_10px_24px_rgba(34,47,62,0.05)]'
                }`}
                data-testid="network-topology-canvas-shell"
              >
                <div className="flex h-full min-h-0 w-full flex-1 flex-col">
                  <NetworkCanvas
                    nodes={config.nodes}
                    links={config.links}
                    runtimeNodes={runtimeNodes}
                    runtimeLinks={runtimeLinks}
                    editMode={editor.editMode}
                    onGraphReady={setGraph}
                    onSelectNode={handleSelectNode}
                    onSelectLink={handleSelectLink}
                    onNodeMoved={onSaveNodePosition}
                    onLinkVerticesChanged={onSaveLinkVertices}
                    onLinkTerminalsChanged={onSaveLinkTerminals}
                    onNodeContextMenu={onNodeContextMenu}
                    onLinkContextMenu={onLinkContextMenu}
                    onDropDevice={handleCanvasDrop}
                    onConnectPorts={onConnectPorts}
                  />
                </div>
              </section>
            </div>
          </ViewWorkspace>
        </div>

        {(nodeContextMenu || linkContextMenu) && (
          <>
            <div
              className="fixed inset-0"
              style={{ zIndex: isFullscreen ? 2199 : 999 }}
              onClick={() => {
                setNodeContextMenu(null);
                setLinkContextMenu(null);
                setNodeDetailPoint(null);
                setLinkDetailPoint(null);
              }}
              onContextMenu={(event) => {
                event.preventDefault();
                setNodeContextMenu(null);
                setLinkContextMenu(null);
                setNodeDetailPoint(null);
                setLinkDetailPoint(null);
              }}
            />
            <div
              className="fixed min-w-[132px] rounded-md py-1 shadow-lg"
              style={{
                left: nodeContextMenu?.x ?? linkContextMenu?.x,
                top: nodeContextMenu?.y ?? linkContextMenu?.y,
                zIndex: isFullscreen ? 2200 : 1000,
                background: 'var(--color-bg-1, #fff)',
                border: '1px solid var(--color-border-2, #e5e6eb)',
              }}
              role="menu"
              onContextMenu={(event) => event.preventDefault()}
            >
              <button
                type="button"
                className="flex h-9 w-full cursor-pointer items-center gap-2 border-0 bg-transparent px-3 text-left text-[13px] text-[var(--color-text-1,#1f2933)] hover:bg-[var(--color-fill-1,#f2f3f5)]"
                role="menuitem"
                onClick={() => {
                  if (nodeContextMenu) {
                    handleSelectNode(nodeContextMenu.node.id);
                  }
                  if (linkContextMenu) {
                    handleSelectLink(linkContextMenu.link.id, {
                      openConfig: true,
                    });
                  }
                  setNodeContextMenu(null);
                  setLinkContextMenu(null);
                }}
              >
                <EditOutlined className="text-[13px]" />
                {t('opsAnalysis.networkTopology.actions.edit')}
              </button>
              {editor.editMode && (
                <button
                  type="button"
                  className="flex h-9 w-full cursor-pointer items-center gap-2 border-0 bg-transparent px-3 text-left text-[13px] text-[var(--color-error,#f53f3f)] hover:bg-[var(--color-fill-1,#f2f3f5)]"
                  role="menuitem"
                  onClick={() => {
                    if (nodeContextMenu) {
                      setDeleteModal({
                        kind: 'node',
                        node: nodeContextMenu.node,
                      });
                    }
                    if (linkContextMenu) {
                      setDeleteModal({
                        kind: 'link',
                        link: linkContextMenu.link,
                      });
                    }
                    setNodeContextMenu(null);
                    setLinkContextMenu(null);
                  }}
                >
                  <DeleteOutlined className="text-[13px]" />
                  {nodeContextMenu
                    ? t('opsAnalysis.networkTopology.actions.deleteNode')
                    : t('opsAnalysis.networkTopology.actions.deleteLink')}
                </button>
              )}
            </div>
          </>
        )}

        {editingLink && linkDetailPoint && !linkConfigOpen && (
          <div
            className={detailPopoverClassName}
            style={{
              ...detailPopoverFrameStyle,
              left: clampDetailPopoverLeft(linkDetailPoint.x),
              top: clampDetailPopoverTop(linkDetailPoint.y),
              maxHeight: DETAIL_POPOVER_MAX_HEIGHT,
              zIndex: isFullscreen ? 2200 : 1000,
            }}
            data-testid="network-link-detail-popover"
          >
            <div
              className={detailPopoverHeaderClassName}
              style={detailPopoverHeaderStyle}
            >
              <div className="min-w-0">
                <div className="truncate text-[14px] font-semibold text-[var(--color-text-1,#1f2933)]">
                  {editingLinkSource?.bk_inst_name || '--'} →{' '}
                  {editingLinkTarget?.bk_inst_name || '--'}
                </div>
                <div className="mt-0.5 truncate text-[12px] text-[var(--color-text-3,#6b7280)]">
                  {editingLinkSource?.ip_addr || editingLink.source_node_id} →{' '}
                  {editingLinkTarget?.ip_addr || editingLink.target_node_id}
                </div>
              </div>
              <Tag
                bordered={false}
                color={
                  editingLinkRuntime?.status === 'critical'
                    ? 'red'
                    : editingLinkRuntime?.status === 'normal'
                      ? 'green'
                      : 'default'
                }
                className="m-0 shrink-0"
              >
                {t(
                  editingLinkRuntime?.status === 'critical'
                    ? 'opsAnalysis.networkTopology.link.statusCritical'
                    : editingLinkRuntime?.status === 'normal'
                      ? 'opsAnalysis.networkTopology.link.statusNormal'
                      : 'opsAnalysis.networkTopology.link.statusUnknown',
                )}
              </Tag>
            </div>
            <div className={detailPopoverBodyClassName}>
              <div className={detailSummaryCardClassName}>
                <div className={detailSummaryGridClassName}>
                  <div className={detailSummaryRowClassName}>
                    <span className={detailLabelClassName}>
                      {t('opsAnalysis.networkTopology.link.labelSourceNode')}
                    </span>
                    <span className={detailColonClassName}>：</span>
                    <span className="min-w-0 truncate font-medium">
                      {editingLinkSource?.bk_inst_name || '--'}
                    </span>
                  </div>
                  <div className={detailSummaryRowClassName}>
                    <span className={detailLabelClassName}>
                      {t('opsAnalysis.networkTopology.link.labelTargetNode')}
                    </span>
                    <span className={detailColonClassName}>：</span>
                    <span className="min-w-0 truncate font-medium">
                      {editingLinkTarget?.bk_inst_name || '--'}
                    </span>
                  </div>
                  <div className={detailSummaryRowClassName}>
                    <span className={detailLabelClassName}>
                      {t('opsAnalysis.networkTopology.link.runtimeStatus')}
                    </span>
                    <span className={detailColonClassName}>：</span>
                    <span className="min-w-0 truncate font-medium">
                      {t(
                        editingLinkRuntime?.status === 'critical'
                          ? 'opsAnalysis.networkTopology.link.statusCritical'
                          : editingLinkRuntime?.status === 'normal'
                            ? 'opsAnalysis.networkTopology.link.statusNormal'
                            : 'opsAnalysis.networkTopology.link.statusUnknown',
                      )}
                    </span>
                  </div>
                  <div className={detailSummaryRowClassName}>
                    <span className={detailLabelClassName}>
                      {t('opsAnalysis.networkTopology.link.labelPairCount')}
                    </span>
                    <span className={detailColonClassName}>：</span>
                    <span className="min-w-0 truncate font-medium">
                      {t(
                        'opsAnalysis.networkTopology.link.pairCount',
                        undefined,
                        {
                          count: editingLink.port_pairs.length,
                        },
                      )}
                    </span>
                  </div>
                </div>
              </div>

              <div>
                <div className={detailSectionTitleClassName}>
                  {t('opsAnalysis.networkTopology.link.labelPairCount')}
                </div>
                <div className="space-y-1">
                  {editingLinkPortRows.length > 0 ? (
                    editingLinkPortRows.map((port) => (
                      <div key={port.key} className={detailListRowClassName}>
                        <span className="min-w-0 truncate text-[var(--color-text-2,#4b5563)]">
                          {port.sourceName}
                          <Tag
                            bordered={false}
                            color={
                              port.sourceStatus === 'up'
                                ? 'green'
                                : port.sourceStatus === 'down'
                                  ? 'red'
                                  : 'default'
                            }
                            className="ml-1 mr-0"
                          >
                            {port.sourceStatus}
                          </Tag>
                        </span>
                        <span className="shrink-0 text-[var(--color-text-3,#6b7280)]">
                          →
                        </span>
                        <span className="min-w-0 truncate text-right text-[var(--color-text-2,#4b5563)]">
                          {port.targetName}
                          <Tag
                            bordered={false}
                            color={
                              port.targetStatus === 'up'
                                ? 'green'
                                : port.targetStatus === 'down'
                                  ? 'red'
                                  : 'default'
                            }
                            className="ml-1 mr-0"
                          >
                            {port.targetStatus}
                          </Tag>
                        </span>
                      </div>
                    ))
                  ) : (
                    <span className="text-[var(--color-text-3,#6b7280)]">
                      {t('opsAnalysis.networkTopology.link.noPortPairs')}
                    </span>
                  )}
                </div>
              </div>

              {editingLinkMetricGroups.length > 0 && (
                <div>
                  <div className={detailSectionTitleClassName}>
                    {t(
                      'opsAnalysis.networkTopology.link.interfaceMetricsTitle',
                    )}
                  </div>
                  <div className="space-y-1.5">
                    {editingLinkMetricGroups.map((group) => (
                      <div
                        key={group.key}
                        className="rounded-md border border-[var(--color-border-1,#edf1f6)] bg-[var(--color-bg-1,#fbfcfe)] px-2 py-1.5"
                      >
                        <div className="mb-1 truncate font-medium text-[var(--color-text-2,#4b5563)]">
                          {group.interfaceName}
                        </div>
                        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[var(--color-text-2,#4b5563)]">
                          {group.metrics.map((metric) => (
                            <span
                              key={metric.key}
                              className="inline-flex min-w-0 items-center gap-1"
                            >
                              <span className="shrink-0 text-[var(--color-text-3,#6b7280)]">
                                {metric.metricLabel}：
                              </span>
                              <span className="shrink-0 font-semibold text-[var(--color-text-1,#1f2933)]">
                                {metric.value}
                              </span>
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {editingNode && !editor.editMode && nodeDetailPoint && (
          <div
            className={detailPopoverClassName}
            style={{
              ...detailPopoverFrameStyle,
              left: clampDetailPopoverLeft(nodeDetailPoint.x),
              top: clampDetailPopoverTop(nodeDetailPoint.y),
              maxHeight: DETAIL_POPOVER_MAX_HEIGHT,
              zIndex: isFullscreen ? 2200 : 1000,
            }}
            data-testid="network-node-detail-popover"
          >
            <div
              className={detailPopoverHeaderClassName}
              style={detailPopoverHeaderStyle}
            >
              <div className="min-w-0">
                <div className="truncate text-[14px] font-semibold text-[var(--color-text-1,#1f2933)]">
                  {editingNode.bk_inst_name || '--'}
                </div>
                <div className="mt-0.5 truncate text-[12px] text-[var(--color-text-3,#6b7280)]">
                  {editingNode.ip_addr || '--'} ·{' '}
                  {editingNode.plugin_template_name ||
                    editingNode.plugin_template_id ||
                    '--'}
                </div>
              </div>
              <Tag
                bordered={false}
                className="m-0 shrink-0"
                style={getModelTagStyle(editingNode.bk_obj_id)}
              >
                {editingNode.bk_obj_id}
              </Tag>
            </div>
            <div className={detailPopoverBodyClassName}>
              <div className={detailSummaryCardClassName}>
                <div className={detailSummaryGridClassName}>
                  <div className={detailSummaryRowClassName}>
                    <span className={detailLabelClassName}>
                      {t('opsAnalysis.networkTopology.node.labelAssetId')}
                    </span>
                    <span className={detailColonClassName}>：</span>
                    <span className="min-w-0 truncate font-medium">
                      {editingNode.bk_inst_id || '--'}
                    </span>
                  </div>
                  <div className={detailSummaryRowClassName}>
                    <span className={detailLabelClassName}>
                      {t('opsAnalysis.networkTopology.node.labelAddress')}
                    </span>
                    <span className={detailColonClassName}>：</span>
                    <span className="min-w-0 truncate font-medium">
                      {editingNode.ip_addr || '--'}
                    </span>
                  </div>
                  <div className={`col-span-2 ${detailSummaryRowClassName}`}>
                    <span className={detailLabelClassName}>
                      {t('opsAnalysis.networkTopology.node.labelTemplate')}
                    </span>
                    <span className={detailColonClassName}>：</span>
                    <span className="min-w-0 truncate font-medium">
                      {editingNode.plugin_template_name ||
                        editingNode.plugin_template_id ||
                        '--'}
                    </span>
                  </div>
                </div>
              </div>

              <div>
                <div className={detailSectionTitleClassName}>
                  {t('opsAnalysis.networkTopology.node.detailMetricsTitle')}
                </div>
                <div className="space-y-1">
                  {editingNodeMetricRows.length > 0 ? (
                    editingNodeMetricRows.map((metric) => (
                      <div key={metric.key} className={detailListRowClassName}>
                        <span className="min-w-0 truncate text-[var(--color-text-2,#4b5563)]">
                          {metric.label}
                        </span>
                        <span
                          className="shrink-0 font-semibold"
                          style={{
                            color:
                              metric.color ?? 'var(--color-text-1,#1f2933)',
                          }}
                        >
                          {metric.value}
                        </span>
                      </div>
                    ))
                  ) : (
                    <span className="text-[var(--color-text-3,#6b7280)]">
                      {t('opsAnalysis.networkTopology.node.detailNoMetrics')}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        <NetworkNodeDrawer
          open={!!editingNode && editor.editMode}
          node={editingNode ?? null}
          metricOptions={metricOptions}
          metricOptionsLoading={metricOptionsLoading}
          dimensionValueOptions={dimensionValueOptions}
          dimensionValuesLoading={dimensionValuesLoading}
          dimensionLoadError={dimensionLoadError}
          onLoadDimensionValues={onLoadMetricDimensionValues}
          readonly={false}
          onClose={() => handleSelectNode(null)}
          onCommitMetrics={(metrics) =>
            editingNode && onCommitNodeMetrics(editingNode.id, metrics)
          }
          zIndex={isFullscreen ? 2300 : undefined}
        />
        <NetworkEdgeDrawer
          open={!!editingLink && linkConfigOpen}
          link={editingLink ?? null}
          sourceNode={editingLinkSource}
          targetNode={editingLinkTarget}
          sourceInterfaces={sourceInterfaces}
          targetInterfaces={targetInterfaces}
          loading={interfacesLoading}
          loadMessage={interfaceLoadMessage}
          readonly={!editor.editMode}
          onCommit={(pairs, interfaceMetrics) =>
            editingLink && onCommitLink(editingLink.id, pairs, interfaceMetrics)
          }
          onClose={() => handleSelectLink(null)}
          zIndex={isFullscreen ? 2300 : undefined}
        />
        <MonitorSourcePickerModal
          open={!!drawingSource}
          item={drawingSource?.item ?? null}
          onCancel={() => setDrawingSource(null)}
          onConfirm={(source) => {
            if (!drawingSource) return;
            const { item, position } = drawingSource;
            upsertNode(item, source, position);
            setDrawingSource(null);
          }}
          zIndex={isFullscreen ? 2400 : undefined}
          testId="network-monitor-source-picker"
        />
        <ConfirmDeleteModal
          open={!!deleteModal}
          title={
            deleteModal?.kind === 'node'
              ? t('opsAnalysis.networkTopology.actions.deleteNode')
              : t('opsAnalysis.networkTopology.actions.deleteLink')
          }
          target={
            deleteModal?.kind === 'node'
              ? deleteModal.node.bk_inst_name
              : deleteModal
                ? `${nodeById.get(deleteModal.link.source_node_id)?.bk_inst_name ?? '-'} → ${
                    nodeById.get(deleteModal.link.target_node_id)
                      ?.bk_inst_name ?? '-'
                  }`
                : undefined
          }
          onCancel={() => setDeleteModal(null)}
          onConfirm={onConfirmDelete}
          zIndex={isFullscreen ? 2400 : undefined}
          testId="network-confirm-delete"
        />
      </>
    );
  },
);

// helpers - 节点 Drawer 的指标项类型(避免把 NetworkNodeDrawer 的
// 入参直接泄露到 NetworkTopology 内部状态类型里)
interface NetworkNodeDrawerPropsMetric {
  metric_field: string;
  result_table_id: string;
  display_name: string;
  unit: string;
  supported_dimensions?: string[];
}

function metricRuntimeKey(
  metric: Pick<NetworkMetricRuntime, 'metric_field' | 'result_table_id' | 'request_id' | 'sort_order'>,
): string {
  if (metric.request_id) return metric.request_id;
  return `${metric.sort_order ?? 0}::${metric.metric_field}::${metric.result_table_id}`;
}

function buildMetricRuntimeRequestId(
  nodeId: string,
  metric: Pick<NetworkTopologyMetric, 'metric_field' | 'result_table_id' | 'sort_order'>,
): string {
  return `${nodeId}::${metric.sort_order ?? 0}::${metric.metric_field}::${metric.result_table_id}`;
}

function toRuntimeMetric(
  item: Partial<NetworkMetricRuntime> | undefined,
  metric: NetworkTopologyMetric,
  requestId?: string,
): NetworkMetricRuntime {
  return {
    request_id: item?.request_id ?? requestId,
    node_id: item?.node_id,
    metric_field: metric.metric_field,
    result_table_id: metric.result_table_id,
    sort_order: item?.sort_order ?? metric.sort_order,
    value: item?.value ?? null,
    unit: item?.unit ?? metric.unit,
    status: item?.status ?? (item?.error_code ? 'error' : 'ok'),
    error_code: item?.error_code,
    error_message: item?.error_message,
    sample_time: item?.sample_time,
    stale: item?.stale,
    freshness_window: item?.freshness_window,
    display_mode: item?.display_mode ?? metric.display_mode,
    aggregate_type: item?.aggregate_type ?? metric.aggregate_type,
    condition_filter: item?.condition_filter ?? metric.condition_filter,
  };
}

NetworkTopology.displayName = 'NetworkTopology';

export default NetworkTopology;

// 帮助函数 - 把当前节点组装为 WeOps node_ref
function nodeRef(node: NetworkTopologyNode): Record<string, unknown> {
  return {
    bk_obj_id: node.bk_obj_id,
    bk_inst_id: node.bk_inst_id,
    network_collect_task_id: node.network_collect_task_id,
    network_collect_instance_id: node.network_collect_instance_id,
    plugin_template_id: node.plugin_template_id,
  };
}

function extractInterfaceItems(res: unknown): NetworkInterfaceRef[] {
  return (res as { items?: NetworkInterfaceRef[] })?.items ?? [];
}

function getInterfaceLoadMessage(res: unknown): string | null {
  const payload = res as {
    items?: NetworkInterfaceRef[];
    status?: string;
    error_message?: string;
    error_code?: string;
  };
  if (payload.status === 'error') {
    return payload.error_message || payload.error_code || null;
  }
  if ((payload.items ?? []).length === 0 && (payload.error_message || payload.error_code)) {
    return payload.error_message || payload.error_code || null;
  }
  return null;
}

function buildInterfaceLoadMessage(...responses: unknown[]): string | null {
  const messages = responses
    .map(getInterfaceLoadMessage)
    .filter((item): item is string => Boolean(item));
  return messages.length > 0 ? Array.from(new Set(messages)).join('；') : null;
}
