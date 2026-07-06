'use client';

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Empty,
  Flex,
  Radio,
  Space,
  Spin,
  Table,
} from 'antd';
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import type { Graph } from '@antv/x6';

import { useInstanceApi } from '@/app/cmdb/api/instance';
import {
  buildNetworkTopologyX6GraphData,
  NetworkTopologyX6Canvas,
  type NetworkTopologyLink as VisualLink,
  type NetworkTopologyNode as VisualNode,
  type NetworkTopologyNodeStatus,
} from '@/app/cmdb/components/networkTopology';
import { useTranslation } from '@/utils/i18n';
import type {
  ApplicationResourceLink,
  ApplicationResourceInstanceListData,
  ApplicationResourceNode,
  ApplicationResourceTopologyData,
} from '@/app/cmdb/types/applicationResourceOverview';

interface Props {
  modelId: string;
  instId: string;
}

type ViewMode = 'topology' | 'resources';
interface OverviewTarget {
  id: string;
  name: string;
  model_id: string;
}

interface NodeContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  nodeId: string;
}

const GROUP_LABELS: Record<string, string> = {
  application: 'ApplicationResourceOverview.groupApplication',
  host: 'ApplicationResourceOverview.groupHost',
  database: 'ApplicationResourceOverview.groupDatabase',
  middleware: 'ApplicationResourceOverview.groupMiddleware',
  cache: 'ApplicationResourceOverview.groupCache',
  message_queue: 'ApplicationResourceOverview.groupMessageQueue',
  hardware: 'ApplicationResourceOverview.groupHardware',
  rack_room: 'ApplicationResourceOverview.groupRackRoom',
  other: 'ApplicationResourceOverview.groupOther',
};

const LAYER_META = {
  root: {
    title: '系统层',
    subtitle: 'System',
    y: 88,
  },
  service: {
    title: '服务层',
    subtitle: 'Service',
    y: 236,
  },
  host: {
    title: '主机层',
    subtitle: 'Host',
    y: 386,
  },
  appService: {
    title: '应用服务层',
    subtitle: 'Application Service',
    y: 556,
  },
  infrastructure: {
    title: '基础设施层',
    subtitle: 'Infrastructure',
    y: 752,
  },
} as const;

type LayerKey = keyof typeof LAYER_META;

const COMPACT_NODE = {
  width: 40,
  height: 40,
  iconSize: 30,
  labelWidth: 120,
} as const;

function getLayerTitle(key: LayerKey, t: (id: string, defaultMessage?: string, values?: Record<string, string | number>) => string) {
  return key === 'root' ? '系统层' : t(LAYER_META[key].title);
}

function buildCompactGraphData(graphData: ReturnType<typeof buildNetworkTopologyX6GraphData>) {
  return {
    nodes: graphData.nodes.map((node) => {
      const centerX = node.x + node.width / 2;
      const centerY = node.y + node.height / 2;
      const iconX = (COMPACT_NODE.width - COMPACT_NODE.iconSize) / 2;
      const iconY = (COMPACT_NODE.height - COMPACT_NODE.iconSize) / 2;

      return {
        ...node,
        x: centerX - COMPACT_NODE.width / 2,
        y: centerY - COMPACT_NODE.height / 2,
        width: COMPACT_NODE.width,
        height: COMPACT_NODE.height,
        attrs: {
          ...node.attrs,
          pulseHalo: {
            ...(node.attrs?.pulseHalo || {}),
            x: 0,
            y: 0,
            width: 0,
            height: 0,
            opacity: 0,
          },
          body: {
            ...(node.attrs?.body || {}),
            fill: 'rgba(255, 255, 255, 0.001)',
            stroke: 'transparent',
            filter: 'none',
            cursor: 'pointer',
            pointerEvents: 'all',
          },
          iconColumn: {
            ...(node.attrs?.iconColumn || {}),
            fill: 'transparent',
            stroke: 'transparent',
            width: 0,
            height: 0,
          },
          divider: {
            ...(node.attrs?.divider || {}),
            opacity: 0,
          },
          iconPlate: {
            ...(node.attrs?.iconPlate || {}),
            fill: 'transparent',
            stroke: 'transparent',
            width: 0,
            height: 0,
          },
          img: {
            ...(node.attrs?.img || {}),
            width: COMPACT_NODE.iconSize,
            height: COMPACT_NODE.iconSize,
            x: iconX,
            y: iconY,
          },
          statusDot: {
            ...(node.attrs?.statusDot || {}),
            cx: COMPACT_NODE.width - 7,
            cy: 7,
            r: 2,
          },
          alertBadge: {
            ...(node.attrs?.alertBadge || {}),
            cx: COMPACT_NODE.width - 1,
            cy: 1,
            r: 8,
          },
          alertBadgeText: {
            ...(node.attrs?.alertBadgeText || {}),
            refX: COMPACT_NODE.width - 1,
            refY: 1,
            fontSize: 9,
          },
          lbl: {
            ...(node.attrs?.lbl || {}),
            refX: null,
            refY: null,
            x: COMPACT_NODE.width / 2,
            y: COMPACT_NODE.height + 1,
            textAnchor: 'middle',
            textVerticalAnchor: 'top',
            fontSize: 10,
            fontWeight: 500,
            textWrap: {
              width: COMPACT_NODE.labelWidth,
              height: 20,
              ellipsis: true,
            },
          },
          subLbl: {
            ...(node.attrs?.subLbl || {}),
            text: '',
            opacity: 0,
          },
        },
      };
    }),
    edges: graphData.edges.map((edge) => {
      const sourceCell = typeof edge.source === 'string' ? edge.source : (edge.source as any)?.cell;
      const targetCell = typeof edge.target === 'string' ? edge.target : (edge.target as any)?.cell;
      return {
        ...edge,
        source: {
          cell: sourceCell,
          anchor: { name: 'center', args: { dx: COMPACT_NODE.width / 2, dy: COMPACT_NODE.height / 2 } },
          connectionPoint: { name: 'boundary' },
        },
        target: {
          cell: targetCell,
          anchor: { name: 'center', args: { dx: COMPACT_NODE.width / 2, dy: COMPACT_NODE.height / 2 } },
          connectionPoint: { name: 'boundary' },
        },
        attrs: {
          ...edge.attrs,
          line: {
            ...(edge.attrs?.line || {}),
            stroke: 'rgba(159, 184, 213, 0.58)',
            strokeWidth: 0.95,
            filter: 'none',
          },
        },
        labels: [],
      };
    }),
  };
}

function resolveRootNode(topology: ApplicationResourceTopologyData): ApplicationResourceNode {
  const systemNode = [...(topology.nodes || [])]
    .filter((node) => node.model_id === 'system')
    .sort((a, b) => a.hop - b.hop || a.name.localeCompare(b.name))[0];
  return systemNode || topology.center;
}

function resolveLayer(
  topology: ApplicationResourceTopologyData,
  node: ApplicationResourceNode,
  rootNode: ApplicationResourceNode
): LayerKey {
  if (node.id === rootNode.id) return 'root';
  if (node.category === 'application') return 'service';
  if (node.model_id === 'host') return 'host';
  if (
    node.category === 'middleware' ||
    node.category === 'database' ||
    node.category === 'cache' ||
    node.category === 'message_queue'
  ) {
    return 'appService';
  }
  if (node.category === 'host') {
    const linkedToHost = topology.links.some((link) => {
      if (link.source === node.id) {
        return topology.nodes.find((item) => item.id === link.target)?.model_id === 'host';
      }
      if (link.target === node.id) {
        return topology.nodes.find((item) => item.id === link.source)?.model_id === 'host';
      }
      return false;
    });
    if (linkedToHost) return 'infrastructure';
  }
  return 'infrastructure';
}

function buildLayeredGraphData(params: {
  topology: ApplicationResourceTopologyData;
  t: (id: string, defaultMessage?: string, values?: Record<string, string | number>) => string;
}) {
  const { topology, t } = params;
  const rootNode = resolveRootNode(topology);
  const orderedNodes = [...topology.nodes].sort(
    (a, b) => a.hop - b.hop || a.name.localeCompare(b.name)
  );
  const byLayer = new Map<LayerKey, ApplicationResourceNode[]>();
  orderedNodes.forEach((node) => {
    const layer = resolveLayer(topology, node, rootNode);
    const list = byLayer.get(layer) || [];
    list.push(node);
    byLayer.set(layer, list);
  });

  const layerSpacing: Record<LayerKey, number> = {
    root: 0,
    service: 320,
    host: 260,
    appService: 220,
    infrastructure: 220,
  };

  const resolveLaneX = (layer: LayerKey, index: number) => {
    if (layer === 'root') return 0;
    return 220 + index * layerSpacing[layer];
  };

  const serviceNodes = byLayer.get('service') || [];
  const serviceCenterX = serviceNodes.length
    ? serviceNodes
      .map((item, index) => resolveLaneX('service', index))
      .reduce((sum, value) => sum + value, 0) / serviceNodes.length
    : 620;

  const positionedNodes = orderedNodes.map((node) => {
    const layer = resolveLayer(topology, node, rootNode);
    const laneNodes = byLayer.get(layer) || [];
    const index = laneNodes.findIndex((item) => item.id === node.id);
    const x = layer === 'root' ? serviceCenterX : resolveLaneX(layer, index);
    return {
      id: node.id,
      modelId: node.model_id,
      name: node.name,
      subtitle: `${node.model_id} · ${t(GROUP_LABELS[node.category] || GROUP_LABELS.other)}`,
      hop: node.hop,
      status: 'normal' as NetworkTopologyNodeStatus,
      x,
      y: LAYER_META[layer].y,
    };
  });

  const links: Array<VisualLink & { curveOffset: number }> = topology.links.map((link) => ({
    id: link.id,
    source: link.source,
    target: link.target,
    sourcePort: link.asst_id || '',
    targetPort: link.model_asst_id || '',
    curveOffset: 0,
  }));

  return buildNetworkTopologyX6GraphData({
    nodes: positionedNodes,
    links,
    centerId: undefined,
    selectedNodeId: undefined,
    activeNodeIds: new Set(),
    activeLinkIds: new Set(),
    dimInactive: false,
    showStatusDot: false,
  });
}

function mergeTopology(
  current: ApplicationResourceTopologyData | null,
  incoming: ApplicationResourceTopologyData
): ApplicationResourceTopologyData {
  if (!current) return incoming;

  const nodes = new Map<string, ApplicationResourceNode>();
  for (const node of current.nodes) nodes.set(node.id, node);
  for (const node of incoming.nodes) {
    const existing = nodes.get(node.id);
    if (!existing || node.hop < existing.hop) {
      nodes.set(node.id, node);
    }
  }

  const links = new Map<string, ApplicationResourceLink>();
  for (const link of current.links) links.set(link.id, link);
  for (const link of incoming.links) links.set(link.id, link);

  return {
    center: current.center,
    nodes: Array.from(nodes.values()).sort((a, b) => a.hop - b.hop || a.name.localeCompare(b.name)),
    links: Array.from(links.values()),
    truncated: current.truncated || incoming.truncated,
  };
}

export default function ApplicationResourceOverview({ modelId, instId }: Props) {
  const { t } = useTranslation();
  const {
    getApplicationResourceTopology,
    getApplicationResourceInstances,
    exportApplicationResourceInstances,
  } = useInstanceApi();
  const [loading, setLoading] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState<OverviewTarget | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('topology');
  const [topology, setTopology] = useState<ApplicationResourceTopologyData | null>(null);
  const [resources, setResources] = useState<ApplicationResourceInstanceListData | null>(null);
  const [nodeContextMenu, setNodeContextMenu] = useState<NodeContextMenuState>({
    visible: false,
    x: 0,
    y: 0,
    nodeId: '',
  });
  const graphRef = useRef<Graph | null>(null);
  const topologyCardRef = useRef<HTMLDivElement | null>(null);
  const [graphInstance, setGraphInstance] = useState<Graph | null>(null);
  const [graphViewportTransform, setGraphViewportTransform] = useState('matrix(1,0,0,1,0,0)');
  const initialDepth = modelId === 'system' ? 2 : 1;

  useEffect(() => {
    let cancelled = false;
    async function bootstrap() {
      setLoading(true);
      try {
        if (!cancelled) {
          setSelectedTarget({ id: instId, name: instId, model_id: modelId });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    bootstrap();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [instId, modelId]);

  useEffect(() => {
    let cancelled = false;
    async function loadApplicationData() {
      if (!selectedTarget) return;
      setLoading(true);
      try {
        const topologyRes = await getApplicationResourceTopology(selectedTarget.model_id, selectedTarget.id, initialDepth);
        const resourceRes = await getApplicationResourceInstances(
          selectedTarget.model_id,
          selectedTarget.id,
          (topologyRes?.nodes || []).map((node: ApplicationResourceNode) => node.id)
        );
        if (cancelled) return;
        setSelectedTarget((current) =>
          current ? { ...current, name: topologyRes?.center?.name || current.name } : current
        );
        setTopology(topologyRes);
        setResources(resourceRes);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    if (selectedTarget) loadApplicationData();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialDepth, selectedTarget?.id, selectedTarget?.model_id]);

  const topologyNodeMap = useMemo(() => {
    return new Map((topology?.nodes || []).map((node) => [node.id, node]));
  }, [topology]);

  const topologyNodesForCanvas = useMemo<VisualNode[]>(() => {
    return (topology?.nodes || []).map((node) => ({
      id: node.id,
      modelId: node.model_id,
      name: node.name,
      subtitle: `${node.model_id} · ${t(GROUP_LABELS[node.category] || GROUP_LABELS.other)}`,
      hop: node.hop,
      status: 'normal',
    }));
  }, [t, topology]);

  const graphData = useMemo(() => {
    if (!topologyNodesForCanvas.length) return { nodes: [], edges: [] };
    return buildCompactGraphData(
      buildLayeredGraphData({
        topology: topology as ApplicationResourceTopologyData,
        t,
      })
    );
  }, [
    topology,
    topologyNodesForCanvas,
  ]);

  useEffect(() => {
    const graph = graphInstance;
    if (!graph) return undefined;

    const syncViewport = () => {
      const matrix = graph.matrix();
      setGraphViewportTransform(
        `matrix(${matrix.a}, ${matrix.b}, ${matrix.c}, ${matrix.d}, ${matrix.e}, ${matrix.f})`
      );
    };

    syncViewport();
    graph.on('scale', syncViewport);
    graph.on('translate', syncViewport);

    return () => {
      graph.off('scale', syncViewport);
      graph.off('translate', syncViewport);
    };
  }, [graphInstance]);

  const handleReset = async () => {
    if (!selectedTarget) return;
    setNodeContextMenu((current) => ({ ...current, visible: false }));
    setLoading(true);
    try {
      const res = await getApplicationResourceTopology(selectedTarget.model_id, selectedTarget.id, initialDepth);
      setTopology(res);
      const resourceRes = await getApplicationResourceInstances(
        selectedTarget.model_id,
        selectedTarget.id,
        (res?.nodes || []).map((node: ApplicationResourceNode) => node.id)
      );
      setResources(resourceRes);
    } finally {
      setLoading(false);
    }
  };

  const handleExpandNode = async (node: ApplicationResourceNode, depth: number) => {
    setNodeContextMenu((current) => ({ ...current, visible: false }));
    setLoading(true);
    try {
      const res = await getApplicationResourceTopology(node.model_id, node.id, depth);
      const mergedTopology = mergeTopology(topology, res);
      setTopology(mergedTopology);
      const resourceRes = await getApplicationResourceInstances(
        selectedTarget?.model_id || modelId,
        selectedTarget?.id || instId,
        (mergedTopology?.nodes || []).map((item: ApplicationResourceNode) => item.id)
      );
      setResources(resourceRes);
    } finally {
      setLoading(false);
    }
  };

  const closeNodeContextMenu = () => {
    setNodeContextMenu((current) => ({ ...current, visible: false }));
  };

  if (loading && !selectedTarget) {
    return <Spin spinning />;
  }

  if (!selectedTarget) {
    return <Empty description={t('ApplicationResourceOverview.emptyApps')} />;
  }

  return (
    <Spin spinning={loading}>
      <Space direction="vertical" style={{ width: '100%', paddingTop: 6 }} size={16}>
        <Radio.Group
          value={viewMode}
          onChange={(event) => setViewMode(event.target.value)}
          size="small"
          optionType="button"
          buttonStyle="solid"
          style={{ alignSelf: 'flex-start' }}
          options={[
            { label: t('ApplicationResourceOverview.topologyTab'), value: 'topology' },
            { label: t('ApplicationResourceOverview.resourcesTab'), value: 'resources' },
          ]}
        />

        {viewMode === 'topology' && (
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            {topology?.truncated && (
              <Alert type="warning" showIcon message={t('ApplicationResourceOverview.truncated')} />
            )}

            <Card
              size="small"
              bodyStyle={{ padding: 12 }}
            >
              {!topology?.nodes?.length ? (
                <Empty description={t('ApplicationResourceOverview.emptyLinks')} />
              ) : (
                <div
                  ref={topologyCardRef}
                  style={{
                    position: 'relative',
                    height: 900,
                    border: '1px solid var(--color-border)',
                    borderRadius: 10,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      position: 'absolute',
                      inset: 0,
                      zIndex: 6,
                      pointerEvents: 'none',
                      transformOrigin: '0 0',
                      transform: graphViewportTransform,
                    }}
                  >
                    {Object.entries(LAYER_META).map(([key, meta]) => (
                      <div
                        key={key}
                        style={{
                          position: 'absolute',
                          left: 0,
                          right: 0,
                          top: meta.y - (key === 'root' ? 32 : 68),
                          height: key === 'root' ? 64 : 136,
                          borderTop: '1px dashed rgba(191, 204, 220, 0.95)',
                          background:
                            key === 'root'
                              ? 'linear-gradient(90deg, rgba(21,90,239,0.028) 0%, rgba(21,90,239,0.004) 14%, rgba(255,255,255,0) 35%)'
                              : key === 'service'
                                ? 'linear-gradient(90deg, rgba(21,90,239,0.04) 0%, rgba(21,90,239,0.008) 14%, rgba(255,255,255,0) 35%)'
                                : key === 'host'
                                  ? 'linear-gradient(90deg, rgba(21,90,239,0.03) 0%, rgba(21,90,239,0.006) 14%, rgba(255,255,255,0) 35%)'
                                  : key === 'appService'
                                    ? 'linear-gradient(90deg, rgba(21,90,239,0.026) 0%, rgba(21,90,239,0.005) 14%, rgba(255,255,255,0) 35%)'
                                    : 'linear-gradient(90deg, rgba(21,90,239,0.022) 0%, rgba(21,90,239,0.004) 14%, rgba(255,255,255,0) 35%)',
                        }}
                      />
                    ))}
                    <div
                      style={{
                        position: 'absolute',
                        left: 18,
                        top: 0,
                        width: 94,
                      }}
                    >
                      {(Object.keys(LAYER_META) as LayerKey[]).map((key) => (
                        <div
                          key={key}
                          style={{
                            position: 'absolute',
                            top: LAYER_META[key].y,
                            left: 0,
                            transform: 'translateY(-50%)',
                            padding: '8px 10px 6px',
                            background: 'rgba(255, 255, 255, 0.72)',
                            borderLeft: '3px solid #94baf7',
                            boxShadow: '0 2px 10px rgba(64, 96, 138, 0.06)',
                          }}
                        >
                          <div
                            style={{
                              fontSize: 12,
                              fontWeight: 600,
                              lineHeight: 1.3,
                              color: '#47648a',
                              marginBottom: 2,
                            }}
                          >
                            {getLayerTitle(key, t)}
                          </div>
                        </div>
                      ))}
                  </div>
                  </div>
                  <NetworkTopologyX6Canvas
                    data={graphData}
                    centerId={topology.center.id}
                    graphRef={graphRef}
                    nodeMovable={false}
                    fitViewKey={`app-topology-${graphData.nodes.length}-${graphData.edges.length}`}
                    onGraphReady={setGraphInstance}
                    onNodeClick={() => {
                      closeNodeContextMenu();
                    }}
                    onNodeContextMenu={(nodeId, event) => {
                      const node = topologyNodeMap.get(nodeId);
                      if (!node) return;
                      const containerRect = topologyCardRef.current?.getBoundingClientRect();
                      const relativeX = containerRect ? event.clientX - containerRect.left : event.clientX;
                      const relativeY = containerRect ? event.clientY - containerRect.top : event.clientY;
                      setNodeContextMenu({
                        visible: true,
                        x: Math.max(12, Math.min(relativeX, (containerRect?.width || 0) - 176)),
                        y: Math.max(12, Math.min(relativeY, (containerRect?.height || 0) - 164)),
                        nodeId,
                      });
                    }}
                    onBlankClick={closeNodeContextMenu}
                    onBlankContextMenu={closeNodeContextMenu}
                    toolbar={{
                      align: 'split',
                      labels: {
                        zoomOut: t('Model.networkTopoZoomOut'),
                        zoomIn: t('Model.networkTopoZoomIn'),
                        fitView: t('Model.networkTopoFitView'),
                        exportImage: t('Model.exportImage'),
                        refresh: t('ApplicationResourceOverview.reset'),
                      },
                      prefix: (
                        <Space wrap>
                          <Button size="small" icon={<ReloadOutlined />} onClick={handleReset}>
                            {t('ApplicationResourceOverview.reset')}
                          </Button>
                        </Space>
                      ),
                      onRefresh: handleReset,
                      refreshLoading: loading,
                    }}
                  />
                  {nodeContextMenu.visible && topologyNodeMap.get(nodeContextMenu.nodeId) && (
                    <div
                      style={{
                        position: 'absolute',
                        left: nodeContextMenu.x,
                        top: nodeContextMenu.y,
                        zIndex: 40,
                        minWidth: 156,
                        padding: 8,
                        borderRadius: 10,
                        border: '1px solid rgba(214, 226, 240, 0.95)',
                        background: 'rgba(255, 255, 255, 0.98)',
                        boxShadow: '0 14px 30px rgba(31, 54, 88, 0.16)',
                        backdropFilter: 'blur(8px)',
                      }}
                    >
                      <div
                        style={{
                          marginBottom: 8,
                          paddingBottom: 8,
                          borderBottom: '1px solid rgba(228, 235, 244, 0.95)',
                          fontSize: 12,
                          fontWeight: 600,
                          color: '#4b6486',
                        }}
                      >
                        {topologyNodeMap.get(nodeContextMenu.nodeId)?.name}
                      </div>
                      <Space direction="vertical" size={6} style={{ width: '100%' }}>
                        <Button
                          block
                          size="small"
                          onClick={() => handleExpandNode(topologyNodeMap.get(nodeContextMenu.nodeId) as ApplicationResourceNode, 1)}
                        >
                          向下展开 1 层
                        </Button>
                        <Button
                          block
                          size="small"
                          onClick={() => handleExpandNode(topologyNodeMap.get(nodeContextMenu.nodeId) as ApplicationResourceNode, 2)}
                        >
                          向下展开 2 层
                        </Button>
                        <Button
                          block
                          size="small"
                          onClick={() => handleExpandNode(topologyNodeMap.get(nodeContextMenu.nodeId) as ApplicationResourceNode, 3)}
                        >
                          向下展开 3 层
                        </Button>
                      </Space>
                    </div>
                  )}
                </div>
              )}
            </Card>

            <Card size="small" title={t('ApplicationResourceOverview.linksTitle')}>
              {!topology?.links?.length ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('ApplicationResourceOverview.emptyLinks')} />
              ) : (
                <Table
                  rowKey="id"
                  size="small"
                  pagination={false}
                  dataSource={topology.links}
                  columns={[
                    {
                      title: t('ApplicationResourceOverview.linkSource'),
                      dataIndex: 'source',
                      render: (value: string) => topologyNodeMap.get(value)?.name || value,
                    },
                    { title: t('ApplicationResourceOverview.linkType'), dataIndex: 'asst_id' },
                    {
                      title: t('ApplicationResourceOverview.linkTarget'),
                      dataIndex: 'target',
                      render: (value: string) => topologyNodeMap.get(value)?.name || value,
                    },
                  ]}
                />
              )}
            </Card>
          </Space>
        )}

        {viewMode === 'resources' && (
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            <Flex justify="end">
              <Button
                icon={<DownloadOutlined />}
                onClick={async () => {
                  if (!topology?.nodes?.length || !selectedTarget) return;
                  const blob = await exportApplicationResourceInstances(
                    selectedTarget.model_id,
                    selectedTarget.id,
                    topology.nodes.map((node) => node.id)
                  );
                  const url = window.URL.createObjectURL(new Blob([blob]));
                  const link = document.createElement('a');
                  link.href = url;
                  link.download = 'application_topology_instances.xlsx';
                  link.click();
                  window.URL.revokeObjectURL(url);
                }}
                disabled={!topology?.nodes?.length}
              >
                {t('ApplicationResourceOverview.export')}
              </Button>
            </Flex>

            {!resources?.groups?.length ? (
              <Empty description={t('ApplicationResourceOverview.emptyResources')} />
            ) : (
              resources.groups.map((group) => (
                <Card
                  key={group.model_id}
                  size="small"
                  title={`${group.model_id} (${group.count})`}
                >
                  <Table<Record<string, string>>
                    rowKey={(record, index) => `${group.model_id}-${record.inst_name || index}`}
                    size="small"
                    pagination={false}
                    scroll={{ x: 'max-content' }}
                    dataSource={group.items}
                    columns={group.column_defs.map((column) => ({
                      title: column.title,
                      dataIndex: column.key,
                      key: column.key,
                      render: (value: string) => {
                        const text = value == null ? '' : String(value);
                        return (
                          <span title={text}>
                            {text}
                          </span>
                        );
                      },
                    }))}
                  />
                </Card>
              ))
            )}
          </Space>
        )}
      </Space>
    </Spin>
  );
}
