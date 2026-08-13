'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CompressOutlined } from '@ant-design/icons';
import { Button, Empty, Spin, Tooltip } from 'antd';
import { Graph } from '@antv/x6';
import { useTranslation } from '@/utils/i18n';
import {
  isEmptyTopologyMapPayload,
  layoutTopologyMap,
  parseTopologyMapPayload,
} from '@/app/ops-analysis/utils/topologyMapData';
import type { TopologyMapPayload } from '@/app/ops-analysis/utils/topologyMapData';
import {
  buildTopologyMapEdgeCells,
  buildTopologyMapNodeCell,
  ensureTopologyMapNodeRegistered,
  getTopologyMapAlertStatus,
} from './topologyMapGraph';
import {
  applyPreservedNodePosition,
  buildTopologyMapStructureSignature,
} from './topologyMapViewerSession';
import WidgetErrorState from '@/app/ops-analysis/components/widgetErrorState';
import styles from './topologyMap.module.scss';

interface TopologyMapProps {
  rawData: unknown;
  loading?: boolean;
  onReady?: (hasData?: boolean) => void;
  onError?: (message: string) => void;
}

const POPOVER_SIZE = { width: 232, height: 156 };
const POPOVER_GAP = 12;
const POPOVER_PADDING = 8;

const resolvePopoverPosition = (event: MouseEvent, container: HTMLElement) => {
  const rect = container.getBoundingClientRect();
  let x = event.clientX - rect.left + POPOVER_GAP;
  let y = event.clientY - rect.top + POPOVER_GAP;
  if (x + POPOVER_SIZE.width > container.clientWidth - POPOVER_PADDING) {
    x = event.clientX - rect.left - POPOVER_SIZE.width - POPOVER_GAP;
  }
  if (y + POPOVER_SIZE.height > container.clientHeight - POPOVER_PADDING) {
    y = event.clientY - rect.top - POPOVER_SIZE.height - POPOVER_GAP;
  }
  return {
    x: Math.max(POPOVER_PADDING, x),
    y: Math.max(POPOVER_PADDING, y),
  };
};

const TopologyMap: React.FC<TopologyMapProps> = ({
  rawData,
  loading = false,
  onReady,
  onError,
}) => {
  const { t } = useTranslation();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const onReadyRef = useRef(onReady);
  const onErrorRef = useRef(onError);
  const payloadRef = useRef<TopologyMapPayload | null>(null);
  const [rendering, setRendering] = useState(false);
  const [renderError, setRenderError] = useState('');
  const [hoverNodeId, setHoverNodeId] = useState('');
  const [hoverPoint, setHoverPoint] = useState({ x: 0, y: 0 });
  onReadyRef.current = onReady;
  onErrorRef.current = onError;

  const parsed = useMemo(() => parseTopologyMapPayload(rawData), [rawData]);
  const isEmpty = parsed.ok && isEmptyTopologyMapPayload(parsed.data);
  const payload = parsed.ok ? parsed.data : null;
  payloadRef.current = payload;
  const structureSignature = useMemo(
    () => (payload ? buildTopologyMapStructureSignature(payload) : ''),
    [payload],
  );

  const syncGraphSize = useCallback((graph: Graph | null = graphRef.current) => {
    const viewport = rootRef.current;
    if (!graph || !viewport?.clientWidth || !viewport.clientHeight) return false;
    graph.resize(viewport.clientWidth, viewport.clientHeight);
    return true;
  }, []);

  const fitGraph = useCallback(() => {
    const graph = graphRef.current;
    if (!graph) return;
    syncGraphSize(graph);
    graph.zoomToFit({ padding: 28, maxScale: 1.5 });
  }, [syncGraphSize]);

  useEffect(() => {
    const initialPayload = payloadRef.current;
    if (!initialPayload || initialPayload.nodes.length === 0) {
      graphRef.current?.dispose();
      graphRef.current = null;
      setRendering(false);
      setRenderError('');
      if (initialPayload) onReadyRef.current?.(false);
      return;
    }

    const host = hostRef.current;
    const viewport = rootRef.current;
    if (!host || !viewport) return;

    let cancelled = false;
    let readyFrame = 0;
    setRendering(true);
    setRenderError('');
    ensureTopologyMapNodeRegistered(Graph);

    const graph = new Graph({
      container: host,
      width: Math.max(viewport.clientWidth, 1),
      height: Math.max(viewport.clientHeight, 1),
      background: { color: 'transparent' },
      panning: { enabled: true },
      mousewheel: {
        enabled: true,
        minScale: 0.2,
        maxScale: 2.5,
      },
      interacting: {
        nodeMovable: true,
        edgeMovable: false,
        edgeLabelMovable: false,
        arrowheadMovable: false,
        vertexMovable: false,
      },
    });
    graphRef.current = graph;

    const updateNodeHover = ({ node, e }: { node: { id: string }; e: MouseEvent }) => {
      const root = rootRef.current;
      if (!root) return;
      setHoverPoint(resolvePopoverPosition(e, root));
      setHoverNodeId(String(node.id));
    };
    const clearNodeHover = () => setHoverNodeId('');
    graph.on('node:mouseenter', updateNodeHover);
    graph.on('node:mousemove', updateNodeHover);
    graph.on('node:mouseleave', clearNodeHover);
    graph.on('blank:mouseenter', clearNodeHover);

    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => {
          // Resize updates canvas size only — never fit/relayout here.
          syncGraphSize(graph);
        });
    observer?.observe(viewport);

    let graphReleased = false;
    const releaseGraph = () => {
      if (graphReleased) return;
      graphReleased = true;
      observer?.disconnect();
      setHoverNodeId('');
      graph.dispose();
      if (graphRef.current === graph) graphRef.current = null;
    };

    void layoutTopologyMap(initialPayload)
      .then((layout) => {
        if (cancelled) return;
        const latestPayload = payloadRef.current || initialPayload;
        const latestNodes = new Map(
          latestPayload.nodes.map((node) => [node.id, node]),
        );
        const positionedNodes = layout.nodes.map((node) => ({
          ...(latestNodes.get(node.id) || node),
          x: node.x,
          y: node.y,
        }));
        graph.addNodes(positionedNodes.map(buildTopologyMapNodeCell));
        graph.addEdges(buildTopologyMapEdgeCells(latestPayload.edges, positionedNodes));
        fitGraph();
        readyFrame = window.requestAnimationFrame(() => {
          setRendering(false);
          onReadyRef.current?.(true);
        });
      })
      .catch(() => {
        if (cancelled) return;
        const message = t('dashboard.topologyMapRenderFailed');
        setRendering(false);
        setRenderError(message);
        releaseGraph();
        onErrorRef.current?.(message);
      });

    return () => {
      cancelled = true;
      if (readyFrame) window.cancelAnimationFrame(readyFrame);
      releaseGraph();
    };
  }, [fitGraph, structureSignature, syncGraphSize, t]);

  useEffect(() => {
    const graph = graphRef.current;
    if (!graph || !payload) return;
    payload.nodes.forEach((node) => {
      const cell = graph.getCellById(node.id);
      if (!cell?.isNode()) return;
      const position = cell.position();
      const metadata = buildTopologyMapNodeCell(
        applyPreservedNodePosition(node, position),
      );
      cell.attr(metadata.attrs);
      cell.setData(node);
    });
    payload.edges.forEach((edge, index) => {
      const cell = graph.getCellById(`topology-map-edge-${index}`);
      if (!cell?.isEdge()) return;
      const metadata = buildTopologyMapEdgeCells([edge], [])[0];
      cell.attr(metadata.attrs);
      cell.setLabels(metadata.labels);
      cell.setData(edge);
    });
  }, [payload]);

  const hoverNode = payload?.nodes.find((node) => node.id === hoverNodeId);
  const hoverStatus = hoverNode
    ? getTopologyMapAlertStatus(hoverNode.alert_level, hoverNode.alert_count)
    : 'normal';
  const hoverStatusLabel = t(`dashboard.topologyMapStatus.${hoverStatus}`);

  if (loading && !payload) {
    return (
      <div className={styles.centered}>
        <Spin />
      </div>
    );
  }

  if (!parsed.ok) return null;

  if (renderError) return <WidgetErrorState message={renderError} />;

  if (isEmpty) {
    return (
      <div className={styles.centered}>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('dashboard.topologyMapEmpty')} />
      </div>
    );
  }

  return (
    <div ref={rootRef} className={styles.root}>
      <div ref={hostRef} className={styles.canvas} />
      <div className={styles.toolbar}>
        <Tooltip title={t('dashboard.topologyMapFit')}>
          <Button
            aria-label={t('dashboard.topologyMapFit')}
            icon={<CompressOutlined />}
            size="small"
            onClick={fitGraph}
          />
        </Tooltip>
      </div>
      {rendering || loading ? (
        <div className={`${styles.centered} absolute inset-0 pointer-events-none`}>
          <Spin size="small" />
        </div>
      ) : null}
      {hoverNode ? (
        <div
          className={styles.popoverLayer}
          style={{ left: hoverPoint.x, top: hoverPoint.y }}
          role="tooltip"
        >
          <div className={styles.popover}>
            <div className={styles.popTitle} title={hoverNode.instance_name}>
              {hoverNode.instance_name}
            </div>
            <div className={styles.popLine}>
              <span>{t('dashboard.topologyMapPopoverModel')}:</span>
              <strong title={hoverNode.model_name}>{hoverNode.model_name}</strong>
            </div>
            {hoverNode.subtitle ? (
              <div className={styles.popLine}>
                <span>{t('dashboard.topologyMapPopoverSubtitle')}:</span>
                <strong title={hoverNode.subtitle}>{hoverNode.subtitle}</strong>
              </div>
            ) : null}
            <div className={styles.popLine}>
              <span>{t('dashboard.topologyMapPopoverAlerts')}:</span>
              <strong className={hoverNode.alert_count > 0 ? styles.alertCount : ''}>
                {hoverNode.alert_count}
              </strong>
            </div>
            {hoverNode.alert_count > 0 ? (
              <div className={styles.popLine}>
                <span>{t('dashboard.topologyMapPopoverSeverity')}:</span>
                <strong className={`${styles.statusPill} ${styles[hoverStatus]}`}>
                  {hoverStatusLabel}
                </strong>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default TopologyMap;
