import type { Graph } from '@antv/x6';

export type PopoverPoint = { x: number; y: number };
export type PopoverSize = { width: number; height: number };
export type PopoverRect = PopoverPoint & PopoverSize;

export type IconLayout = {
  nodeWidth: number;
  iconSize: number;
  iconTop: number;
};

/** 与 STATUS_TOPOLOGY_VISUAL 对齐；本地常量避免测试拉入重依赖 */
export const NODE_ICON_LAYOUT: IconLayout = {
  nodeWidth: 160,
  iconSize: 72,
  iconTop: 4,
};

export const POPOVER_GAP = 10;
export const POPOVER_PADDING = 8;
export const CURSOR_OFFSET = { x: 12, y: 12 };

/** 节点浮层预估尺寸（用于边缘翻转，略大于实际卡片） */
export const NODE_POPOVER_ESTIMATE: PopoverSize = { width: 220, height: 96 };
/** 边浮层预估尺寸 */
export const EDGE_POPOVER_ESTIMATE: PopoverSize = { width: 260, height: 140 };

/** 与 widget-viewport.toCanvasPixels 一致：屏幕像素 → 缩放前本地像素 */
export const normalizeViewportScale = (scale?: number) =>
  Number.isFinite(scale) && Number(scale) > 0 ? Number(scale) : 1;

export const toLocalPixels = (screenPixels: number, viewportScale = 1) =>
  screenPixels / normalizeViewportScale(viewportScale);

export const clampPopoverInContainer = (
  candidate: PopoverPoint,
  popover: PopoverSize,
  container: PopoverSize,
  padding = POPOVER_PADDING,
): PopoverPoint => {
  const maxX = Math.max(padding, container.width - popover.width - padding);
  const maxY = Math.max(padding, container.height - popover.height - padding);
  return {
    x: Math.min(Math.max(padding, candidate.x), maxX),
    y: Math.min(Math.max(padding, candidate.y), maxY),
  };
};

/**
 * 默认贴在 icon 右上侧：水平在 icon 右侧，垂直顶边略高于 icon，
 * 避免整块悬在正上方造成过大空隙。右侧不够改左侧，再夹紧进容器。
 */
export const placeBesideIcon = (
  icon: PopoverRect,
  popover: PopoverSize,
  container: PopoverSize,
  gap = POPOVER_GAP,
): PopoverPoint => {
  let x = icon.x + icon.width + gap;
  // 顶边略高于 icon，主体落在 icon 旁侧，而不是整卡抬到正上方
  let y = icon.y - gap;

  if (x + popover.width > container.width - POPOVER_PADDING) {
    x = icon.x - popover.width - gap;
  }
  // 底部越界时改到 icon 上方内侧仍保持贴近（仅上移，不整段拉开）
  if (y + popover.height > container.height - POPOVER_PADDING) {
    y = Math.max(
      POPOVER_PADDING,
      container.height - popover.height - POPOVER_PADDING,
    );
  }

  return clampPopoverInContainer({ x, y }, popover, container);
};

/** 相对光标小偏移 + 容器夹紧（边浮层） */
export const placeNearCursor = (
  cursor: PopoverPoint,
  popover: PopoverSize,
  container: PopoverSize,
  offset: PopoverPoint = CURSOR_OFFSET,
): PopoverPoint =>
  clampPopoverInContainer(
    { x: cursor.x + offset.x, y: cursor.y + offset.y },
    popover,
    container,
  );

/**
 * getBoundingClientRect 差值为屏幕像素；大屏 CSS scale 下需还原为本地像素，
 * 才能赋给 position:absolute 的 left/top。
 */
export const clientToContainerPoint = (
  client: PopoverPoint,
  containerRect: DOMRect,
  viewportScale = 1,
): PopoverPoint => ({
  x: toLocalPixels(client.x - containerRect.left, viewportScale),
  y: toLocalPixels(client.y - containerRect.top, viewportScale),
});

export const screenRectToLocalRect = (
  screenRect: Pick<DOMRect, 'left' | 'top' | 'width' | 'height'>,
  containerRect: Pick<DOMRect, 'left' | 'top'>,
  viewportScale = 1,
): PopoverRect => ({
  x: toLocalPixels(screenRect.left - containerRect.left, viewportScale),
  y: toLocalPixels(screenRect.top - containerRect.top, viewportScale),
  width: Math.max(1, toLocalPixels(screenRect.width, viewportScale)),
  height: Math.max(1, toLocalPixels(screenRect.height, viewportScale)),
});

/**
 * 将节点 icon 的图坐标包围盒转为相对 canvas 容器的矩形（含缩放/平移）。
 * XFlow/X6 Graph 公共 API 为 localToClient（不是 localToClientPoint）。
 */
export const getNodeIconRectInContainer = (
  graph: Graph,
  nodeId: string,
  containerRect: DOMRect,
  visual: IconLayout = NODE_ICON_LAYOUT,
  viewportScale = 1,
): PopoverRect | null => {
  const cell = graph.getCellById(nodeId);
  if (!cell || !cell.isNode()) return null;

  // 优先用真实 SVG image 的屏幕包围盒，避开坐标 API 差异
  const view = graph.findViewByCell(cell);
  const imageEl = view?.container?.querySelector?.('image') as SVGImageElement | null;
  if (imageEl) {
    return screenRectToLocalRect(
      imageEl.getBoundingClientRect(),
      containerRect,
      viewportScale,
    );
  }

  const pos = cell.getPosition();
  const iconLocalX = pos.x + (visual.nodeWidth - visual.iconSize) / 2;
  const iconLocalY = pos.y + visual.iconTop;
  const toClient = resolveLocalToClient(graph);
  if (!toClient) return null;

  const topLeft = toClient(iconLocalX, iconLocalY);
  const bottomRight = toClient(
    iconLocalX + visual.iconSize,
    iconLocalY + visual.iconSize,
  );

  return screenRectToLocalRect(
    {
      left: topLeft.x,
      top: topLeft.y,
      width: bottomRight.x - topLeft.x,
      height: bottomRight.y - topLeft.y,
    },
    containerRect,
    viewportScale,
  );
};

type LocalToClientFn = (x: number, y: number) => PopoverPoint;

const resolveLocalToClient = (graph: Graph): LocalToClientFn | null => {
  const g = graph as Graph & {
    localToClient?: LocalToClientFn;
    localToClientPoint?: LocalToClientFn;
    coord?: { localToClientPoint?: LocalToClientFn };
  };
  if (typeof g.localToClient === 'function') {
    return (x, y) => g.localToClient!(x, y);
  }
  if (typeof g.localToClientPoint === 'function') {
    return (x, y) => g.localToClientPoint!(x, y);
  }
  if (typeof g.coord?.localToClientPoint === 'function') {
    return (x, y) => g.coord!.localToClientPoint!(x, y);
  }
  return null;
};

const getContainerLocalSize = (container: HTMLElement): PopoverSize => ({
  // client* 是未乘 CSS scale 的布局尺寸，与 position:absolute 坐标系一致
  width: container.clientWidth,
  height: container.clientHeight,
});

export const resolveNodePopoverPosition = (
  graph: Graph | null,
  nodeId: string,
  container: HTMLElement | null,
  popover: PopoverSize = NODE_POPOVER_ESTIMATE,
  viewportScale = 1,
): PopoverPoint | null => {
  if (!graph || !container) return null;
  const containerRect = container.getBoundingClientRect();
  const icon = getNodeIconRectInContainer(
    graph,
    nodeId,
    containerRect,
    NODE_ICON_LAYOUT,
    viewportScale,
  );
  if (!icon) return null;
  return placeBesideIcon(icon, popover, getContainerLocalSize(container));
};

export const resolveEdgePopoverPosition = (
  event: MouseEvent,
  container: HTMLElement | null,
  popover: PopoverSize = EDGE_POPOVER_ESTIMATE,
  viewportScale = 1,
): PopoverPoint | null => {
  if (!container) return null;
  const containerRect = container.getBoundingClientRect();
  return placeNearCursor(
    clientToContainerPoint(
      { x: event.clientX, y: event.clientY },
      containerRect,
      viewportScale,
    ),
    popover,
    getContainerLocalSize(container),
  );
};
