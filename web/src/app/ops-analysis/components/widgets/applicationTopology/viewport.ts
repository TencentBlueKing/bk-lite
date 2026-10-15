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

/**
 * 五带都留在视口里。左右各留出一层名栏，拓扑本身居中，
 * 放大到分层高度或簇宽度先碰到边。
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
  const side = rail + labelGap;
  const availW = Math.max(1, input.viewportWidth - padding * 2 - side * 2);
  const availH = Math.max(1, input.viewportHeight - padding * 2);
  const clusterWidth = Math.max(1, input.clusterWidth);
  const layerHeight = Math.max(1, input.layerHeight);
  const scale = clampApplicationTopologyScale(
    Math.min(availW / clusterWidth, availH / layerHeight),
  );
  const clusterCenter = input.clusterX + clusterWidth / 2;
  let x = input.viewportWidth / 2 - clusterCenter * scale;
  const minLeft = padding + side;
  const clusterLeft = x + input.clusterX * scale;
  if (clusterLeft < minLeft) {
    x += minLeft - clusterLeft;
  }
  return {
    scale,
    x,
    y: (input.viewportHeight - layerHeight * scale) / 2,
  };
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
