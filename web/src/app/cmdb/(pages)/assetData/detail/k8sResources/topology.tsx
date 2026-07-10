'use client';

import React, {
  useCallback,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Button, Empty, Space, Tag } from 'antd';
import {
  EyeOutlined,
  MinusSquareOutlined,
  PlusSquareOutlined,
} from '@ant-design/icons';
import {
  K8S_TOPOLOGY_LAYERS,
  K8sTopologyData,
  K8sTopologyNode,
} from './model';
import {
  buildTopologyPaths,
  getTopologyFocus,
  groupTopologyNodes,
  TopologyNodeBox,
  TopologyPath,
} from './topologyLayout';
import styles from './styles.module.scss';
import { useTranslation } from '@/utils/i18n';

const LAYER_LABELS = {
  cluster: 'Cluster',
  namespace: 'Namespace',
  workload: 'Workload',
  pod: 'Pod',
  node: 'Node',
};

export interface K8sTopologyProps {
  topology: K8sTopologyData;
  expandedWorkloads: Set<string>;
  branchMeta: Record<string, { loaded: number; count: number; status: string }>;
  layers: Record<'namespace' | 'workload' | 'node', { shown: number; count: number; page_size: number }>;
  onToggleWorkload: (id: string) => void;
  onLoadMorePods: (id: string) => void;
  onLoadMoreLayer: (layer: 'namespace' | 'workload' | 'node') => void;
  onOpenList: (kind: string, node?: K8sTopologyNode) => void;
  unownedExpanded?: boolean;
  unownedLoading?: boolean;
  onToggleUnowned?: () => void;
}

export const K8sTopology: React.FC<K8sTopologyProps> = ({
  topology,
  expandedWorkloads,
  branchMeta,
  layers,
  onToggleWorkload,
  onLoadMorePods,
  onLoadMoreLayer,
  onOpenList,
  unownedExpanded,
  unownedLoading,
  onToggleUnowned,
}) => {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef(new Map<string, HTMLDivElement>());
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [paths, setPaths] = useState<TopologyPath[]>([]);
  const [menu, setMenu] = useState({ open: false, x: 0, y: 0, nodeId: '' });
  const nodeMap = useMemo(
    () => new Map(topology.nodes.map((node) => [node.id, node])),
    [topology.nodes]
  );
  const groupedNodes = useMemo(
    () => groupTopologyNodes(topology.nodes),
    [topology.nodes]
  );
  const active = useMemo(
    () => getTopologyFocus(selectedId, topology),
    [selectedId, topology]
  );

  const updatePaths = useCallback(() => {
    const content = contentRef.current;
    if (!content) return;
    const contentRect = content.getBoundingClientRect();
    const boxes = new Map<string, TopologyNodeBox>();
    nodeRefs.current.forEach((element, nodeId) => {
      if (!element.isConnected) return;
      const rect = element.getBoundingClientRect();
      boxes.set(nodeId, {
        left: rect.left - contentRect.left,
        top: rect.top - contentRect.top,
        width: rect.width,
        height: rect.height,
      });
    });
    setPaths(buildTopologyPaths(topology.edges, boxes));
  }, [topology.edges]);

  useLayoutEffect(() => {
    const content = contentRef.current;
    if (!content) return;
    let frame = 0;
    const scheduleUpdate = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(updatePaths);
    };
    const observer = new ResizeObserver(scheduleUpdate);
    observer.observe(content);
    nodeRefs.current.forEach((element) => observer.observe(element));
    scheduleUpdate();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [topology.nodes, updatePaths]);

  const openMenu = (nodeId: string, x?: number, y?: number) => {
    const rect = containerRef.current?.getBoundingClientRect();
    setMenu({
      open: true,
      nodeId,
      x: Math.max(
        12,
        Math.min(
          (x ?? (rect?.left || 0) + 120) - (rect?.left || 0),
          (rect?.width || 320) - 200
        )
      ),
      y: Math.max(
        56,
        Math.min(
          (y ?? (rect?.top || 0) + 100) - (rect?.top || 0),
          (rect?.height || 300) - 160
        )
      ),
    });
  };

  const selectNode = (nodeId: string) => {
    setSelectedId((current) => current === nodeId ? null : nodeId);
    setMenu((value) => ({ ...value, open: false }));
  };

  const handleNodeKeyDown = (
    event: React.KeyboardEvent<HTMLDivElement>,
    nodeId: string
  ) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      event.stopPropagation();
      selectNode(nodeId);
    }
    if ((event.shiftKey && event.key === 'F10') || event.key === 'ContextMenu') {
      event.preventDefault();
      event.stopPropagation();
      setSelectedId(nodeId);
      openMenu(nodeId);
    }
  };

  const subtitle = (node: K8sTopologyNode) => {
    if (node.layer !== 'workload') return LAYER_LABELS[node.layer];
    const branch = branchMeta[node.id];
    const branchStatus = branch?.status === 'waiting'
      ? ` · ${t('K8sResourceOverview.states.waiting')}`
      : branch?.status === 'loading'
        ? ` · ${t('K8sResourceOverview.states.loading')}`
        : branch?.status === 'error'
          ? ` · ${t('K8sResourceOverview.states.failed')}`
          : branch
            ? ` · ${t('K8sResourceOverview.states.shown', undefined, {
              loaded: branch.loaded,
              count: branch.count,
            })}`
            : '';
    return `${node.workload_type || 'Workload'} · Pod ${node.pod_count ?? 0}${branchStatus}`;
  };

  const menuNode = nodeMap.get(menu.nodeId);

  if (!topology.nodes.length) {
    return <Empty description={t('K8sResourceOverview.states.emptyTopology')} />;
  }

  return (
    <div
      ref={containerRef}
      className={styles.topologyShell}
      role="application"
      aria-label={t('K8sResourceOverview.accessibility.topology')}
      onClick={() => {
        setSelectedId(null);
        setMenu((value) => ({ ...value, open: false }));
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          setMenu((value) => ({ ...value, open: false }));
        }
      }}
    >
      {onToggleUnowned ? (
        <div className={styles.topologyActions}>
          <Button size="small" loading={unownedLoading} onClick={onToggleUnowned}>
            {t(
              unownedExpanded
                ? 'K8sResourceOverview.actions.collapseUnowned'
                : 'K8sResourceOverview.actions.expandUnowned'
            )}
          </Button>
        </div>
      ) : null}
      <div className={styles.layerHeaders}>
        {K8S_TOPOLOGY_LAYERS.map((layer) => (
          <div key={layer}>{LAYER_LABELS[layer]}</div>
        ))}
      </div>
      <div className={styles.topologyViewport}>
        <div ref={contentRef} className={styles.topologyContent}>
          <svg className={styles.topologyEdges} aria-hidden="true">
            {paths.map((path) => (
              <path
                key={path.id}
                d={path.d}
                className={`${styles.topologyEdge} ${
                  selectedId
                    ? active.edges.has(path.id)
                      ? styles.activeEdge
                      : styles.dimmedEdge
                    : ''
                }`}
              />
            ))}
          </svg>
          <div className={styles.topologyGrid}>
            {K8S_TOPOLOGY_LAYERS.map((layer) => (
              <div className={styles.topologyColumn} key={layer}>
                {groupedNodes[layer].map((node) => (
                  <div
                    key={node.id}
                    ref={(element) => {
                      if (element) nodeRefs.current.set(node.id, element);
                      else nodeRefs.current.delete(node.id);
                    }}
                    data-topology-node
                    data-node-id={node.id}
                    data-layer={node.layer}
                    role="button"
                    tabIndex={0}
                    aria-pressed={selectedId === node.id}
                    className={`${styles.topologyNode} ${
                      selectedId === node.id ? styles.selectedNode : ''
                    } ${
                      selectedId && !active.nodes.has(node.id) ? styles.dimmedNode : ''
                    } ${node.model_id === 'virtual' ? styles.virtualNode : ''}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      selectNode(node.id);
                    }}
                    onContextMenu={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      setSelectedId(node.id);
                      openMenu(node.id, event.clientX, event.clientY);
                    }}
                    onKeyDown={(event) => handleNodeKeyDown(event, node.id)}
                  >
                    <span className={styles.nodeTypeMark} aria-hidden="true" />
                    <span className={styles.nodeText}>
                      <strong className={styles.nodeName}>{node.name}</strong>
                      <span className={styles.nodeSubtitle}>{subtitle(node)}</span>
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className={styles.layerFooters}>
        {(['namespace', 'workload', 'node'] as const).map((layer) => (
          <Space key={layer} size={6}>
            <span>
              {t('K8sResourceOverview.states.layerShown', undefined, {
                shown: layers[layer].shown,
                count: layers[layer].count,
              })}
            </span>
            {layers[layer].shown < layers[layer].count ? (
              <Button
                type="link"
                size="small"
                onClick={() => onLoadMoreLayer(layer)}
              >
                {t('K8sResourceOverview.actions.loadMore')}
              </Button>
            ) : null}
          </Space>
        ))}
      </div>
      <div
        className={styles.legend}
        aria-label={t('K8sResourceOverview.accessibility.legend')}
      >
        {K8S_TOPOLOGY_LAYERS.map((layer) => (
          <Tag
            key={layer}
            color={layer === 'pod' ? 'blue' : layer === 'node' ? 'cyan' : 'geekblue'}
          >
            {LAYER_LABELS[layer]}
          </Tag>
        ))}
      </div>
      {menu.open && menuNode ? (
        <div
          className={styles.contextMenu}
          style={{ left: menu.x, top: menu.y }}
          role="menu"
          onClick={(event) => event.stopPropagation()}
        >
          {menuNode.layer === 'workload' ? (
            <button
              role="menuitem"
              onClick={() => {
                onToggleWorkload(menuNode.id);
                setMenu({ ...menu, open: false });
              }}
            >
              {expandedWorkloads.has(menuNode.id)
                ? <MinusSquareOutlined />
                : <PlusSquareOutlined />}
              {t(
                expandedWorkloads.has(menuNode.id)
                  ? 'K8sResourceOverview.actions.collapsePods'
                  : 'K8sResourceOverview.actions.expandPods'
              )}
            </button>
          ) : null}
          {menuNode.layer === 'workload'
            && branchMeta[menuNode.id]?.loaded < branchMeta[menuNode.id]?.count ? (
              <button
                role="menuitem"
                onClick={() => onLoadMorePods(menuNode.id)}
              >
                {t('K8sResourceOverview.actions.loadMorePods')}
              </button>
            ) : null}
          {menuNode.layer === 'workload'
            && branchMeta[menuNode.id]?.status === 'error' ? (
              <button
                role="menuitem"
                onClick={() => onLoadMorePods(menuNode.id)}
              >
                {t('K8sResourceOverview.actions.retryPods')}
              </button>
            ) : null}
          <button
            role="menuitem"
            onClick={() => onOpenList(
              menuNode.layer === 'cluster' ? 'namespace' : menuNode.layer,
              menuNode
            )}
          >
            <EyeOutlined />
            {t('K8sResourceOverview.actions.viewResources')}
          </button>
        </div>
      ) : null}
    </div>
  );
};
