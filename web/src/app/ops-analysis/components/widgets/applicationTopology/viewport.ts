export const APPLICATION_TOPOLOGY_SCALE = {
  min: 0.25,
  max: 2.5,
  step: 0.2,
} as const;

/** 层名与节点标题同一套字号，再乘拓扑缩放。图例留在画布坐标里，不跟拓扑缩放。 */
export const APPLICATION_TOPOLOGY_LAYER_LABEL_FONT = 16;
export const APPLICATION_TOPOLOGY_LEGEND_FONT = 15;
const LAYER_LABEL_RAIL_MIN_PX = 96;

export function applicationTopologyChromeScale(viewScale: number): number {
  if (!Number.isFinite(viewScale) || viewScale <= 0) return 1;
  return viewScale;
}

export function applicationTopologyLabelRailWidth(viewScale: number): number {
  const font = APPLICATION_TOPOLOGY_LAYER_LABEL_FONT * applicationTopologyChromeScale(viewScale);
  return Math.max(LAYER_LABEL_RAIL_MIN_PX, Math.round(font * 5 + 16));
}

export function clampApplicationTopologyScale(scale: number): number {
  if (!Number.isFinite(scale)) return 1;
  return Math.min(
    APPLICATION_TOPOLOGY_SCALE.max,
    Math.max(APPLICATION_TOPOLOGY_SCALE.min, scale),
  );
}

/**
 * 五带都留在视口里，节点簇相对整个组件居中（扣掉左侧层名栏），
 * 并放大到分层高度或簇宽度先碰到边。
 */
export function fitApplicationTopologyLayers(input: {
  viewportWidth: number;
  viewportHeight: number;
  clusterX: number;
  clusterWidth: number;
  layerHeight: number;
  labelRailWidth?: number;
  padding?: number;
}): { scale: number; x: number; y: number } {
  const padding = input.padding ?? 8;
  const rail = Math.max(0, input.labelRailWidth ?? 0);
  const availW = Math.max(1, input.viewportWidth - padding * 2);
  const availH = Math.max(1, input.viewportHeight - padding * 2);
  const clusterWidth = Math.max(1, input.clusterWidth);
  const layerHeight = Math.max(1, input.layerHeight);
  const scale = clampApplicationTopologyScale(
    Math.min(availW / clusterWidth, availH / layerHeight),
  );
  let x =
    (input.viewportWidth - clusterWidth * scale) / 2
    - input.clusterX * scale
    - rail / 2;
  const clusterLeft = x + input.clusterX * scale;
  if (clusterLeft < padding) {
    x += padding - clusterLeft;
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
