export const APPLICATION_TOPOLOGY_SCALE = {
  min: 0.25,
  max: 2.5,
  step: 0.2,
} as const;

/** 图例留在画布坐标里，不跟拓扑缩放。 */
export const APPLICATION_TOPOLOGY_LEGEND_FONT = 15;
/** 节点标题是 text-base。层名用同一字号。 */
export const APPLICATION_TOPOLOGY_NODE_TITLE_FONT = 16;
/** 左侧层级卡片在缩放为 1 时的宽度。要放下图标和「应用服务层」这类五字层名。放大后按比例变宽，缩小时不低于可读宽度。 */
const LAYER_CARD_WIDTH_PX = 168;
const LAYER_CARD_MIN_PX = 112;

/** 层级卡片跟随拓扑缩放，和节点标题保持同一套比例。 */
export function applicationTopologyChromeScale(viewScale: number): number {
  if (!Number.isFinite(viewScale) || viewScale <= 0) return 1;
  return viewScale;
}

export function applicationTopologyLabelRailWidth(viewScale: number): number {
  const scale = applicationTopologyChromeScale(viewScale);
  return Math.max(LAYER_CARD_MIN_PX, Math.round(LAYER_CARD_WIDTH_PX * scale));
}

export function clampApplicationTopologyScale(scale: number): number {
  if (!Number.isFinite(scale)) return 1;
  return Math.min(
    APPLICATION_TOPOLOGY_SCALE.max,
    Math.max(APPLICATION_TOPOLOGY_SCALE.min, scale),
  );
}

/** 层名卡片右缘到拓扑色块左缘的间距。 */
export const APPLICATION_TOPOLOGY_LABEL_GAP = 10;

/** 适配视口时可以比手动缩放更小，避免层数一多就冲出页面。 */
const FIT_SCALE_MIN = 0.05;

/**
 * 五带都留在视口里。左侧层名栏占掉的宽度，右侧留出同样大小，
 * 拓扑在整块区域里居中。放大到分层高度或簇宽度先碰到边。
 */
export function fitApplicationTopologyLayers(input: {
  viewportWidth: number;
  viewportHeight: number;
  clusterX: number;
  clusterWidth: number;
  layerHeight: number;
  labelRailWidth?: number;
  labelGap?: number;
  padding?: number;
}): { scale: number; x: number; y: number } {
  const padding = input.padding ?? 8;
  const rail = Math.max(0, input.labelRailWidth ?? 0);
  const labelGap = rail > 0 ? Math.max(0, input.labelGap ?? APPLICATION_TOPOLOGY_LABEL_GAP) : 0;
  const leftInset = padding + rail + labelGap;
  const rightInset = leftInset;
  const availW = Math.max(1, input.viewportWidth - leftInset - rightInset);
  const availH = Math.max(1, input.viewportHeight - padding * 2);
  const clusterWidth = Math.max(1, input.clusterWidth);
  const layerHeight = Math.max(1, input.layerHeight);
  const scale = Math.min(
    APPLICATION_TOPOLOGY_SCALE.max,
    Math.max(FIT_SCALE_MIN, Math.min(availW / clusterWidth, availH / layerHeight)),
  );
  const clusterCenter = input.clusterX + clusterWidth / 2;
  const contentCenter = leftInset + availW / 2;
  let x = contentCenter - clusterCenter * scale;
  const clusterLeft = x + input.clusterX * scale;
  if (clusterLeft < leftInset) {
    x += leftInset - clusterLeft;
  }
  return {
    scale,
    x,
    y: (input.viewportHeight - layerHeight * scale) / 2,
  };
}

const VIEWPORT_SCALE_SNAP = 0.004;

/**
 * 大屏用 CSS 把设计尺寸拉开，组件自己的布局盒子不变。
 * 排版用拉开之后的可见宽高；再把可见坐标缩回布局盒子，抵消不均匀拉伸。
 */
export function resolveApplicationTopologyViewportBox(input: {
  contentWidth: number;
  contentHeight: number;
  visualWidth: number;
  visualHeight: number;
}): {
  contentWidth: number;
  contentHeight: number;
  visualWidth: number;
  visualHeight: number;
  contentScaleX: number;
  contentScaleY: number;
} {
  const contentWidth = Math.max(1, input.contentWidth);
  const contentHeight = Math.max(1, input.contentHeight);
  let visualWidth = Math.max(1, input.visualWidth);
  let visualHeight = Math.max(1, input.visualHeight);
  let contentScaleX = contentWidth / visualWidth;
  let contentScaleY = contentHeight / visualHeight;
  if (Math.abs(contentScaleX - 1) < VIEWPORT_SCALE_SNAP) {
    contentScaleX = 1;
    visualWidth = contentWidth;
  }
  if (Math.abs(contentScaleY - 1) < VIEWPORT_SCALE_SNAP) {
    contentScaleY = 1;
    visualHeight = contentHeight;
  }
  return {
    contentWidth,
    contentHeight,
    visualWidth,
    visualHeight,
    contentScaleX,
    contentScaleY,
  };
}

/**
 * 层数把高度撑满时加宽，换更多列去用上左右空档。
 * 高度还空着时收窄，让同一层少排几个、多排一行。
 */
export function resolveApplicationTopologyLaneWidth(input: {
  viewportWidth: number;
  viewportHeight: number;
  labelRailWidth?: number;
  labelGap?: number;
  padding?: number;
  measure: (laneWidth: number) => { width: number; height: number };
}): number {
  const viewportWidth = Math.max(1, input.viewportWidth);
  const viewportHeight = Math.max(1, input.viewportHeight);
  const padding = input.padding ?? 8;
  const rail = Math.max(0, input.labelRailWidth ?? 0);
  const labelGap = rail > 0 ? Math.max(0, input.labelGap ?? APPLICATION_TOPOLOGY_LABEL_GAP) : 0;
  const side = padding + rail + labelGap;
  const target = Math.max(1, viewportWidth - side * 2);
  const availH = Math.max(1, viewportHeight - padding * 2);
  const fitted = (laneWidth: number) => {
    const measured = input.measure(laneWidth);
    const view = fitApplicationTopologyLayers({
      viewportWidth,
      viewportHeight,
      clusterX: 0,
      clusterWidth: measured.width,
      layerHeight: measured.height,
      labelRailWidth: input.labelRailWidth,
      labelGap: input.labelGap,
      padding: input.padding,
    });
    return {
      visualWidth: measured.width * view.scale,
      visualHeight: measured.height * view.scale,
    };
  };

  let bestLane = viewportWidth;
  let best = fitted(viewportWidth);
  let lane = viewportWidth;
  for (let step = 0; step < 8; step += 1) {
    if (best.visualWidth >= target - 1) break;
    lane *= 1.45;
    const next = fitted(lane);
    if (next.visualWidth <= best.visualWidth + 0.5) break;
    bestLane = lane;
    best = next;
  }

  for (let step = 0; step < 5; step += 1) {
    if (best.visualHeight >= availH * 0.9) break;
    const nextLane = bestLane * 0.82;
    if (nextLane < 280) break;
    const next = fitted(nextLane);
    if (next.visualWidth < target * 0.9) break;
    if (next.visualHeight <= best.visualHeight + 0.5) break;
    bestLane = nextLane;
    best = next;
  }
  return bestLane;
}

export function zoomApplicationTopologyAt(input: {
  scale: number;
  x: number;
  y: number;
  pointerX: number;
  pointerY: number;
  nextScale: number;
}): { scale: number; x: number; y: number } {
  const scale = clampApplicationTopologyScale(input.nextScale);
  const ratio = scale / clampApplicationTopologyScale(input.scale);
  return {
    scale,
    x: input.pointerX - (input.pointerX - input.x) * ratio,
    y: input.pointerY - (input.pointerY - input.y) * ratio,
  };
}
