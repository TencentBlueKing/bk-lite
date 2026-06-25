'use client';

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Alert, Button, Empty, Segmented, Spin, Tooltip } from 'antd';
import {
  DownloadOutlined,
  ReloadOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from '@ant-design/icons';
import { getIconUrl } from '@/app/cmdb/utils/common';
import {
  applyNodePositionOverrides,
  layoutNetworkTopology,
} from './graphModel';
import type {
  NetworkTopologyCanvasProps,
  NetworkTopologyLayoutMode,
  NetworkTopologyNode,
  NetworkTopologyPositionedNode,
} from './types';
import {
  NETWORK_TOPOLOGY_VIEWBOX,
  NETWORK_TOPOLOGY_VISUAL,
} from './visual';
import styles from './networkTopologyCanvas.module.scss';

const toSet = (value?: Set<string> | string[]) =>
  value instanceof Set ? value : new Set(value || []);

const truncateText = (text: string, maxLength: number) => {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1)}...`;
};

const getNodeIcon = (node: NetworkTopologyNode) => {
  if (node.icon && (/^https?:\/\//.test(node.icon) || node.icon.startsWith('/'))) {
    return node.icon;
  }
  return getIconUrl({
    icn: node.icon || '',
    model_id: node.modelId,
  });
};

const getEdgePoint = (
  from: NetworkTopologyPositionedNode,
  to: NetworkTopologyPositionedNode,
) => {
  const visual = NETWORK_TOPOLOGY_VISUAL.node;
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const scale = Math.min(
    Math.abs(dx) ? visual.width / 2 / Math.abs(dx) : Number.POSITIVE_INFINITY,
    Math.abs(dy) ? visual.height / 2 / Math.abs(dy) : Number.POSITIVE_INFINITY,
  );
  const safeScale = Number.isFinite(scale) ? scale : 0;
  return {
    x: from.x + dx * safeScale,
    y: from.y + dy * safeScale,
  };
};

const buildLinkPath = (
  source: NetworkTopologyPositionedNode,
  target: NetworkTopologyPositionedNode,
  curveOffset: number,
) => {
  const start = getEdgePoint(source, target);
  const end = getEdgePoint(target, source);
  const midX = (start.x + end.x) / 2;
  const midY = (start.y + end.y) / 2;
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = Math.hypot(dx, dy) || 1;
  const controlX = midX + (-dy / length) * curveOffset;
  const controlY = midY + (dx / length) * curveOffset;
  return {
    d: `M ${start.x} ${start.y} Q ${controlX} ${controlY} ${end.x} ${end.y}`,
    start,
    end,
    control: { x: controlX, y: controlY },
    length,
  };
};

const pointOnQuadratic = (
  start: { x: number; y: number },
  control: { x: number; y: number },
  end: { x: number; y: number },
  t: number,
) => {
  const oneMinusT = 1 - t;
  return {
    x:
      oneMinusT * oneMinusT * start.x +
      2 * oneMinusT * t * control.x +
      t * t * end.x,
    y:
      oneMinusT * oneMinusT * start.y +
      2 * oneMinusT * t * control.y +
      t * t * end.y,
  };
};

const getPortLabelSize = (text?: string) => {
  const label = truncateText(text || '', 18);
  return {
    label,
    width: Math.max(42, label.length * 7 + 18),
  };
};

const getPortLabelRatio = (
  text: string | undefined,
  linkLength: number,
  fallbackRatio: number,
) => {
  if (!text) return fallbackRatio;
  const { width } = getPortLabelSize(text);
  const clearanceRatio = (width / 2 + 8) / Math.max(linkLength, 1);
  return Math.min(0.45, Math.max(fallbackRatio, clearanceRatio));
};

const getNodeLabelMaxLength = () => (
  Math.max(12, Math.floor(NETWORK_TOPOLOGY_VISUAL.node.labelWidth / 7))
);

const getResponsiveViewport = (rect?: DOMRectReadOnly | null) => {
  if (!rect?.width || !rect.height) return NETWORK_TOPOLOGY_VIEWBOX;
  const widthByRatio = Math.round(
    (rect.width / rect.height) * NETWORK_TOPOLOGY_VIEWBOX.height,
  );
  return {
    width: Math.max(NETWORK_TOPOLOGY_VIEWBOX.width, widthByRatio),
    height: NETWORK_TOPOLOGY_VIEWBOX.height,
  };
};

const PortLabel = ({
  text,
  x,
  y,
  active,
}: {
  text?: string;
  x: number;
  y: number;
  active: boolean;
}) => {
  if (!text) return null;
  const { label, width } = getPortLabelSize(text);
  return (
    <g className={styles.portLabel} transform={`translate(${x} ${y})`}>
      <rect
        className={styles.portLabelBg}
        x={-width / 2}
        y={-12}
        width={width}
        height={24}
        rx={5}
        ry={5}
      />
      <text
        className={`${styles.portLabelText} ${active ? styles.activePortLabelText : ''}`}
        textAnchor="middle"
        dominantBaseline="middle"
      >
        {label}
      </text>
    </g>
  );
};

const loadImageAsDataUrl = async (url: string) => {
  const response = await fetch(url);
  const blob = await response.blob();
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
};

const inlineSvgStyles = (source: SVGSVGElement, target: SVGSVGElement) => {
  const styleProperties = [
    'fill',
    'stroke',
    'stroke-width',
    'stroke-linecap',
    'stroke-linejoin',
    'font-size',
    'font-weight',
    'font-family',
    'opacity',
    'filter',
    'text-anchor',
    'dominant-baseline',
  ];
  const sourceElements = [source, ...Array.from(source.querySelectorAll('*'))];
  const targetElements = [target, ...Array.from(target.querySelectorAll('*'))];

  sourceElements.forEach((element, index) => {
    const targetElement = targetElements[index] as SVGElement | undefined;
    if (!targetElement) return;
    const computedStyle = window.getComputedStyle(element);
    const inlineStyle = styleProperties
      .map((property) => {
        const value = computedStyle.getPropertyValue(property);
        return value ? `${property}:${value}` : '';
      })
      .filter(Boolean)
      .join(';');
    if (inlineStyle) {
      targetElement.setAttribute('style', inlineStyle);
    }
  });
};

const NetworkTopologyCanvas: React.FC<NetworkTopologyCanvasProps> = ({
  nodes,
  links,
  centerId,
  layoutMode,
  labels,
  selectedNodeId,
  activeNodeIds,
  activeLinkIds,
  dimInactive = false,
  loading,
  refreshLoading,
  error,
  emptyText,
  truncatedText,
  exportFileName = 'network-topology.svg',
  onLayoutChange,
  onRefresh,
  onBlankClick,
  onNodeClick,
  renderPopover,
  renderContextMenu,
}) => {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<{ x: number; y: number; offsetX: number; offsetY: number } | null>(null);
  const nodeDragRef = useRef<{
    id: string;
    startClientX: number;
    startClientY: number;
    startX: number;
    startY: number;
    moved: boolean;
  } | null>(null);
  const suppressNodeClickRef = useRef(false);
  const iconDataUrlMapRef = useRef<Map<string, string>>(new Map());
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [nodeDragging, setNodeDragging] = useState(false);
  const [nodePositionOverrides, setNodePositionOverrides] = useState<
    Map<string, { x: number; y: number }>
  >(new Map());
  const [hoverNode, setHoverNode] = useState<NetworkTopologyNode | null>(null);
  const [hoverPoint, setHoverPoint] = useState({ x: 0, y: 0 });
  const [viewport, setViewport] = useState(NETWORK_TOPOLOGY_VIEWBOX);
  const [contextMenu, setContextMenu] = useState<{
    node: NetworkTopologyNode;
    x: number;
    y: number;
  } | null>(null);

  const baseLayout = useMemo(
    () => layoutNetworkTopology({
      nodes,
      links,
      centerId,
      mode: layoutMode,
      viewport,
    }),
    [centerId, layoutMode, links, nodes, viewport],
  );
  const layout = useMemo(
    () => applyNodePositionOverrides(baseLayout, nodePositionOverrides),
    [baseLayout, nodePositionOverrides],
  );
  const positionedNodeMap = useMemo(
    () => new Map(layout.nodes.map((node) => [node.id, node])),
    [layout.nodes],
  );
  const activeNodes = useMemo(() => toSet(activeNodeIds), [activeNodeIds]);
  const activeLinks = useMemo(() => toSet(activeLinkIds), [activeLinkIds]);
  const layoutOptions = useMemo(
    () => [
      { label: labels.layoutHierarchical, value: 'hierarchical' as NetworkTopologyLayoutMode },
      { label: labels.layoutForce, value: 'force' as NetworkTopologyLayoutMode },
      { label: labels.layoutCircular, value: 'circular' as NetworkTopologyLayoutMode },
    ],
    [labels],
  );

  const closeContextMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return undefined;

    const updateViewport = () => {
      const nextViewport = getResponsiveViewport(wrapper.getBoundingClientRect());
      setViewport((current) => (
        current.width === nextViewport.width && current.height === nextViewport.height
          ? current
          : nextViewport
      ));
    };

    updateViewport();
    const observer = new ResizeObserver(updateViewport);
    observer.observe(wrapper);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setNodePositionOverrides(new Map());
    nodeDragRef.current = null;
    suppressNodeClickRef.current = false;
    setNodeDragging(false);
  }, [baseLayout]);

  const zoomByWheel = useCallback(
    (deltaY: number) => {
      closeContextMenu();
      const zoomStep = deltaY > 0 ? -0.08 : 0.08;
      setScale((value) => Math.min(2, Math.max(0.55, value + zoomStep)));
    },
    [closeContextMenu],
  );

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return undefined;
    const handleNativeWheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      zoomByWheel(event.deltaY);
    };
    wrapper.addEventListener('wheel', handleNativeWheel, { passive: false });
    return () => {
      wrapper.removeEventListener('wheel', handleNativeWheel);
    };
  }, [zoomByWheel]);

  useEffect(() => {
    let cancelled = false;
    const iconUrls = Array.from(new Set(nodes.map(getNodeIcon).filter(Boolean)));
    iconUrls.forEach((iconUrl) => {
      if (iconUrl.startsWith('data:') || iconDataUrlMapRef.current.has(iconUrl)) return;
      const absoluteUrl = new URL(iconUrl, window.location.origin).toString();
      if (iconDataUrlMapRef.current.has(absoluteUrl)) return;
      void loadImageAsDataUrl(absoluteUrl)
        .then((dataUrl) => {
          if (cancelled) return;
          iconDataUrlMapRef.current.set(iconUrl, dataUrl);
          iconDataUrlMapRef.current.set(absoluteUrl, dataUrl);
        })
        .catch((error) => {
          console.warn('network topology icon cache failed:', error);
        });
    });
    return () => {
      cancelled = true;
    };
  }, [nodes]);

  const prepareExportSvg = useCallback(() => {
    if (!svgRef.current) return;
    const sourceSvg = svgRef.current;
    const clonedSvg = sourceSvg.cloneNode(true) as SVGSVGElement;
    clonedSvg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clonedSvg.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
    clonedSvg.setAttribute('width', String(viewport.width));
    clonedSvg.setAttribute('height', String(viewport.height));

    inlineSvgStyles(sourceSvg, clonedSvg);
    const sourceImages = Array.from(sourceSvg.querySelectorAll('image'));
    const clonedImages = Array.from(clonedSvg.querySelectorAll('image'));
    sourceImages.forEach((sourceImage, index) => {
      const clonedImage = clonedImages[index];
      const rawHref =
        sourceImage.getAttribute('href') ||
        sourceImage.getAttribute('xlink:href') ||
        '';
      if (!clonedImage || !rawHref || rawHref.startsWith('data:')) return;
      const imageUrl = new URL(rawHref, window.location.origin).toString();
      const dataUrl =
        iconDataUrlMapRef.current.get(rawHref) ||
        iconDataUrlMapRef.current.get(imageUrl);
      if (!dataUrl) return;
      clonedImage.setAttribute('href', dataUrl);
      clonedImage.setAttribute('xlink:href', dataUrl);
    });

    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    defs.innerHTML = `
      <pattern id="network-topology-export-grid" width="18" height="18" patternUnits="userSpaceOnUse">
        <circle cx="1" cy="1" r="1" fill="#7491b5" opacity="0.22" />
      </pattern>
    `;
    const background = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    background.setAttribute('x', '0');
    background.setAttribute('y', '0');
    background.setAttribute('width', String(viewport.width));
    background.setAttribute('height', String(viewport.height));
    background.setAttribute('fill', '#fcfeff');
    const grid = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    grid.setAttribute('x', '0');
    grid.setAttribute('y', '0');
    grid.setAttribute('width', String(viewport.width));
    grid.setAttribute('height', String(viewport.height));
    grid.setAttribute('fill', 'url(#network-topology-export-grid)');
    clonedSvg.insertBefore(defs, clonedSvg.firstChild);
    clonedSvg.insertBefore(grid, clonedSvg.children[1] || null);
    clonedSvg.insertBefore(background, clonedSvg.children[1] || null);

    return new XMLSerializer().serializeToString(clonedSvg);
  }, [viewport]);

  const handleExport = useCallback(() => {
    const svgText = prepareExportSvg();
    if (!svgText) return;
    const blob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = exportFileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, [exportFileName, prepareExportSvg]);

  const clientDeltaToViewBoxDelta = useCallback(
    (deltaX: number, deltaY: number) => {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return { x: 0, y: 0 };
      return {
        x: (deltaX * viewport.width) / rect.width / scale,
        y: (deltaY * viewport.height) / rect.height / scale,
      };
    },
    [scale, viewport],
  );

  const clampNodePosition = useCallback((x: number, y: number) => {
    const visual = NETWORK_TOPOLOGY_VISUAL.node;
    const minX = visual.width / 2;
    const maxX = viewport.width - visual.width / 2;
    const minY = visual.height / 2;
    const maxY = viewport.height - visual.height / 2;
    return {
      x: Math.min(maxX, Math.max(minX, x)),
      y: Math.min(maxY, Math.max(minY, y)),
    };
  }, [viewport]);

  const handleMouseDown = (event: React.MouseEvent<SVGSVGElement>) => {
    closeContextMenu();
    dragRef.current = {
      x: event.clientX,
      y: event.clientY,
      offsetX: offset.x,
      offsetY: offset.y,
    };
    setDragging(true);
  };

  const handleMouseMove = (event: React.MouseEvent<SVGSVGElement>) => {
    if (nodeDragRef.current) {
      const drag = nodeDragRef.current;
      const delta = clientDeltaToViewBoxDelta(
        event.clientX - drag.startClientX,
        event.clientY - drag.startClientY,
      );
      const nextPosition = clampNodePosition(
        drag.startX + delta.x,
        drag.startY + delta.y,
      );
      if (
        !drag.moved &&
        Math.hypot(event.clientX - drag.startClientX, event.clientY - drag.startClientY) > 3
      ) {
        drag.moved = true;
      }
      setNodePositionOverrides((current) => {
        const next = new Map(current);
        next.set(drag.id, nextPosition);
        return next;
      });
      return;
    }
    if (!dragRef.current) return;
    setOffset({
      x: dragRef.current.offsetX + event.clientX - dragRef.current.x,
      y: dragRef.current.offsetY + event.clientY - dragRef.current.y,
    });
  };

  const stopDragging = () => {
    if (nodeDragRef.current) {
      suppressNodeClickRef.current = nodeDragRef.current.moved;
      nodeDragRef.current = null;
      setNodeDragging(false);
    }
    dragRef.current = null;
    setDragging(false);
  };

  const handleNodeHover = (
    node: NetworkTopologyNode,
    event: React.MouseEvent<SVGGElement>,
  ) => {
    if (nodeDragRef.current) return;
    const rect = svgRef.current?.getBoundingClientRect();
    setHoverNode(node);
    setHoverPoint({
      x: event.clientX - (rect?.left || 0) + 32,
      y: event.clientY - (rect?.top || 0) + 24,
    });
  };

  const renderState = () => {
    if (loading && !nodes.length) {
      return (
        <div className={styles.state}>
          <Spin />
        </div>
      );
    }
    if (error) {
      return (
        <div className={styles.state}>
          <Alert
            type="error"
            showIcon
            message={error}
            action={onRefresh ? (
              <Button size="small" onClick={onRefresh}>
                {labels.refresh}
              </Button>
            ) : undefined}
          />
        </div>
      );
    }
    if (!nodes.length) {
      return (
        <div className={styles.state}>
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />
        </div>
      );
    }
    return null;
  };

  return (
    <div ref={wrapperRef} className={styles.wrapper}>
      <div className={styles.grid} />
      <div className={styles.toolbar}>
        <Segmented
          size="small"
          value={layoutMode}
          options={layoutOptions}
          onChange={(value) => onLayoutChange?.(value as NetworkTopologyLayoutMode)}
        />
        <div className={styles.toolbarActions}>
          <Tooltip title={labels.zoomOut}>
            <Button
              aria-label={labels.zoomOut}
              size="small"
              icon={<ZoomOutOutlined />}
              onClick={() => setScale((value) => Math.max(0.55, value - 0.1))}
            />
          </Tooltip>
          <Tooltip title={labels.zoomIn}>
            <Button
              aria-label={labels.zoomIn}
              size="small"
              icon={<ZoomInOutlined />}
              onClick={() => setScale((value) => Math.min(2, value + 0.1))}
            />
          </Tooltip>
          <Tooltip title={labels.exportImage}>
            <Button
              aria-label={labels.exportImage}
              size="small"
              icon={<DownloadOutlined />}
              onClick={handleExport}
            />
          </Tooltip>
          {onRefresh && (
            <Tooltip title={labels.refresh}>
              <Button
                aria-label={labels.refresh}
                size="small"
                icon={<ReloadOutlined />}
                loading={refreshLoading}
                onClick={onRefresh}
              />
            </Tooltip>
          )}
        </div>
      </div>
      {truncatedText && <div className={styles.truncated}>{truncatedText}</div>}
      <svg
        ref={svgRef}
        className={`${styles.svg} ${dragging || nodeDragging ? styles.dragging : ''}`}
        viewBox={`0 0 ${viewport.width} ${viewport.height}`}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={stopDragging}
        onMouseLeave={stopDragging}
      >
        <rect
          width={viewport.width}
          height={viewport.height}
          fill="transparent"
          onClick={() => {
            closeContextMenu();
            onBlankClick?.();
          }}
          onContextMenu={(event) => {
            event.preventDefault();
            closeContextMenu();
          }}
        />
        <g transform={`translate(${offset.x} ${offset.y}) scale(${scale})`}>
          {layout.links.map((link) => {
            const source = positionedNodeMap.get(link.source);
            const target = positionedNodeMap.get(link.target);
            if (!source || !target) return null;
            const linkPath = buildLinkPath(source, target, link.curveOffset);
            const active = activeLinks.has(link.id);
            const selected =
              !active && (selectedNodeId === link.source || selectedNodeId === link.target);
            const dimmed = dimInactive && !active;

            return (
              <g key={link.id} className={dimmed ? styles.dimmed : undefined}>
                <path
                  d={linkPath.d}
                  className={`${styles.linkPath} ${active ? styles.activeLinkPath : ''} ${
                    selected ? styles.selectedLinkPath : ''
                  }`}
                />
              </g>
            );
          })}
          {layout.nodes.map((node) => {
            const active = activeNodes.has(node.id);
            const selected = selectedNodeId === node.id;
            const dimmed = dimInactive && !active;
            const visual = NETWORK_TOPOLOGY_VISUAL.node;
            const statusColor =
              NETWORK_TOPOLOGY_VISUAL.status[node.status || 'normal'];

            return (
              <g
                key={node.id}
                className={`${styles.node} ${dimmed ? styles.dimmed : ''}`}
                transform={`translate(${node.x - visual.width / 2} ${node.y - visual.height / 2})`}
                onClick={(event) => {
                  event.stopPropagation();
                  if (suppressNodeClickRef.current) {
                    suppressNodeClickRef.current = false;
                    return;
                  }
                  closeContextMenu();
                  onNodeClick?.(node);
                }}
                onMouseDown={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  closeContextMenu();
                  setHoverNode(null);
                  nodeDragRef.current = {
                    id: node.id,
                    startClientX: event.clientX,
                    startClientY: event.clientY,
                    startX: node.x,
                    startY: node.y,
                    moved: false,
                  };
                  setNodeDragging(true);
                }}
                onMouseMove={(event) => handleNodeHover(node, event)}
                onMouseLeave={() => setHoverNode(null)}
                onContextMenu={(event) => {
                  if (!renderContextMenu) return;
                  event.preventDefault();
                  event.stopPropagation();
                  const rect = svgRef.current?.getBoundingClientRect();
                  setContextMenu({
                    node,
                    x: event.clientX - (rect?.left || 0) + 8,
                    y: event.clientY - (rect?.top || 0) + 8,
                  });
                }}
              >
                {node.pulse && node.status === 'critical' && (
                  <rect
                    className={styles.pulseHalo}
                    x={-4}
                    y={-4}
                    width={visual.width + 8}
                    height={visual.height + 8}
                    rx={visual.radius + 4}
                    ry={visual.radius + 4}
                    style={{
                      transformBox: 'fill-box',
                      transformOrigin: 'center',
                    }}
                  />
                )}
                <rect
                  className={`${styles.nodeBody} ${
                    selected ? styles.selectedNodeBody : ''
                  } ${active ? styles.activeNodeBody : ''}`}
                  width={visual.width}
                  height={visual.height}
                  rx={visual.radius}
                  ry={visual.radius}
                />
                <rect
                  className={styles.iconColumn}
                  x={1}
                  y={1}
                  width={visual.iconColumnWidth - 1}
                  height={visual.height - 2}
                  rx={visual.radius - 1}
                  ry={visual.radius - 1}
                />
                <line
                  className={styles.iconDivider}
                  x1={visual.iconColumnWidth}
                  y1={9}
                  x2={visual.iconColumnWidth}
                  y2={visual.height - 9}
                />
                <rect
                  className={styles.iconPlate}
                  x={(visual.iconColumnWidth - visual.iconPlateSize) / 2}
                  y={(visual.height - visual.iconPlateSize) / 2}
                  width={visual.iconPlateSize}
                  height={visual.iconPlateSize}
                  rx={11}
                  ry={11}
                />
                <image
                  href={getNodeIcon(node)}
                  x={(visual.iconColumnWidth - visual.iconSize) / 2}
                  y={(visual.height - visual.iconSize) / 2}
                  width={visual.iconSize}
                  height={visual.iconSize}
                  opacity={0.95}
                />
                <text className={styles.label} x={visual.labelX} y={28}>
                  {truncateText(node.name, getNodeLabelMaxLength())}
                </text>
                <text className={styles.subLabel} x={visual.labelX} y={46}>
                  {truncateText(node.subtitle || node.modelId, 20)}
                </text>
                {!!node.alertCount && (
                  <g transform={`translate(${visual.width - 18} 16)`}>
                    <circle
                      className={styles.badgeBg}
                      cx={12}
                      cy={-10}
                      r={11}
                      style={{ fill: statusColor }}
                    />
                    <text
                      className={styles.badgeText}
                      x={12}
                      y={-6}
                      textAnchor="middle"
                    >
                      {node.alertCount > 99 ? '99+' : node.alertCount}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
          {layout.links.map((link) => {
            const source = positionedNodeMap.get(link.source);
            const target = positionedNodeMap.get(link.target);
            if (!source || !target) return null;
            const linkPath = buildLinkPath(source, target, link.curveOffset);
            const active = activeLinks.has(link.id);
            const dimmed = dimInactive && !active;
            const sourceRatio = getPortLabelRatio(link.sourcePort, linkPath.length, 0.24);
            const targetRatio = 1 - getPortLabelRatio(link.targetPort, linkPath.length, 0.24);
            const sourceLabelPoint = pointOnQuadratic(
              linkPath.start,
              linkPath.control,
              linkPath.end,
              sourceRatio,
            );
            const targetLabelPoint = pointOnQuadratic(
              linkPath.start,
              linkPath.control,
              linkPath.end,
              targetRatio,
            );
            const sourceWidth = getPortLabelSize(link.sourcePort).width;
            const targetWidth = getPortLabelSize(link.targetPort).width;
            const separateLabels =
              !!link.sourcePort &&
              !!link.targetPort &&
              linkPath.length < sourceWidth + targetWidth + 24;

            return (
              <g key={`${link.id}-ports`} className={dimmed ? styles.dimmed : undefined}>
                <PortLabel
                  text={link.sourcePort}
                  x={sourceLabelPoint.x}
                  y={sourceLabelPoint.y - (separateLabels ? 16 : 2)}
                  active={active}
                />
                <PortLabel
                  text={link.targetPort}
                  x={targetLabelPoint.x}
                  y={targetLabelPoint.y + (separateLabels ? 16 : -2)}
                  active={active}
                />
              </g>
            );
          })}
        </g>
      </svg>
      <div className={styles.minimap}>
        <svg viewBox={`0 0 ${viewport.width} ${viewport.height}`}>
          {layout.links.map((link) => {
            const source = positionedNodeMap.get(link.source);
            const target = positionedNodeMap.get(link.target);
            if (!source || !target) return null;
            return (
              <line
                key={link.id}
                className={styles.minimapLink}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
              />
            );
          })}
          {layout.nodes.map((node) => (
            <circle
              key={node.id}
              className={styles.minimapNode}
              cx={node.x}
              cy={node.y}
              r={16}
              fill={NETWORK_TOPOLOGY_VISUAL.status[node.status || 'normal']}
            />
          ))}
        </svg>
      </div>
      {hoverNode && !contextMenu && renderPopover && (
        <div
          className={styles.popover}
          style={{ left: hoverPoint.x, top: hoverPoint.y }}
        >
          {renderPopover(hoverNode)}
        </div>
      )}
      {contextMenu && renderContextMenu && (
        <div
          className={styles.contextMenu}
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          {renderContextMenu(contextMenu.node, closeContextMenu)}
        </div>
      )}
      {renderState()}
    </div>
  );
};

export default NetworkTopologyCanvas;
