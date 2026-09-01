export const LAYER_KEYS = [
  'root',
  'service',
  'host',
  'appService',
  'infrastructure',
] as const;

export type LayerKey = (typeof LAYER_KEYS)[number];

export const LAYER_TITLE_KEYS: Record<LayerKey, string> = {
  root: 'ApplicationResourceOverview.layerSystem',
  service: 'ApplicationResourceOverview.layerServiceTier',
  host: 'ApplicationResourceOverview.layerHost',
  appService: 'ApplicationResourceOverview.layerAppService',
  infrastructure: 'ApplicationResourceOverview.layerInfrastructure',
};

export const LAYOUT_NODE = {
  width: 248,
  height: 68,
} as const;

export const COL_STRIDE = 272;
export const ROW_STRIDE = 88;
export const BAND_PAD_Y = 28;
export const LAYER_GAP = 32;
export const CANVAS_PAD_X = 24;
export const LAYER_LABEL_RAIL_PX = 132;
export const ORIGIN_X = LAYOUT_NODE.width / 2 + CANVAS_PAD_X;
export const START_Y = 24;
export const DEFAULT_LANE_WIDTH = 1100;

export interface LayerBand {
  key: LayerKey;
  top: number;
  bottom: number;
  labelY: number;
}

export interface PackedNodePosition {
  id: string;
  x: number;
  y: number;
  layer: LayerKey;
}

export function columnsForLaneWidth(laneWidth: number): number {
  const usable = Math.max(laneWidth - 32, COL_STRIDE);
  return Math.max(1, Math.floor(usable / COL_STRIDE));
}

export function packLayeredNodes(params: {
  layers: Record<LayerKey, Array<{ id: string }>>;
  laneWidth: number;
}): { positions: PackedNodePosition[]; bands: LayerBand[] } {
  const columns = columnsForLaneWidth(params.laneWidth);
  const gridWidth = Math.max(0, columns - 1) * COL_STRIDE;
  const positions: PackedNodePosition[] = [];
  const bands: LayerBand[] = [];
  let yCursor = START_Y;

  for (const key of LAYER_KEYS) {
    const nodes = params.layers[key] || [];
    const centeredRoot = key === 'root' && nodes.length <= 1;
    const layerColumns = centeredRoot ? 1 : columns;
    const rows = Math.max(1, Math.ceil(nodes.length / layerColumns));
    const top = yCursor;
    const firstCenterY = top + BAND_PAD_Y + LAYOUT_NODE.height / 2;
    const lastCenterY = firstCenterY + (rows - 1) * ROW_STRIDE;
    const bottom = lastCenterY + LAYOUT_NODE.height / 2 + BAND_PAD_Y;

    nodes.forEach((node, index) => {
      const row = Math.floor(index / layerColumns);
      const col = index % layerColumns;
      const x = centeredRoot
        ? ORIGIN_X + gridWidth / 2
        : ORIGIN_X + col * COL_STRIDE;
      positions.push({
        id: node.id,
        x,
        y: firstCenterY + row * ROW_STRIDE,
        layer: key,
      });
    });

    bands.push({
      key,
      top,
      bottom,
      labelY: (firstCenterY + lastCenterY) / 2,
    });
    yCursor = bottom + LAYER_GAP;
  }

  return { positions, bands };
}

export function resolveBandIndex(centerY: number, bands: LayerBand[]): number {
  if (!bands.length) return 0;
  const containing = bands.findIndex((band) => centerY >= band.top && centerY <= band.bottom);
  if (containing >= 0) return containing;
  return bands.reduce((nearest, band, index) => {
    const nearestMid = (bands[nearest].top + bands[nearest].bottom) / 2;
    const mid = (band.top + band.bottom) / 2;
    return Math.abs(centerY - mid) < Math.abs(centerY - nearestMid) ? index : nearest;
  }, 0);
}
