import {
  NETWORK_TOPO_CARD_VISUAL,
  NETWORK_TOPO_VISUAL,
} from '@/app/cmdb/components/networkTopology/x6Visual';
import type { OpsChartThemeMode } from '@/app/ops-analysis/utils/chartTheme';

export const RELATED_TOPOLOGY_VISUAL = {
  nodeWidth: 200,
  nodeHeight: 68,
  iconSize: 44,
  columnGap: 360,
  rowGap: 120,
  canvas: NETWORK_TOPO_VISUAL.canvas,
  grid: NETWORK_TOPO_VISUAL.grid,
  edge: NETWORK_TOPO_VISUAL.edge,
  labelFill: NETWORK_TOPO_VISUAL.label.textFill,
  card: {
    ...NETWORK_TOPO_CARD_VISUAL.node,
    activeBody: {
      ...NETWORK_TOPO_CARD_VISUAL.node.activeBody,
      filter:
        'drop-shadow(0 12px 24px rgba(0,112,250,0.08)) drop-shadow(0 1px 2px rgba(15, 23, 42, 0.04))',
    },
  },
} as const;

export const RELATED_TOPOLOGY_UNMAPPED_FILL = 'var(--color-fill-2)';
export const RELATED_TOPOLOGY_UNMAPPED_STROKE = 'var(--color-border-3)';
export const RELATED_TOPOLOGY_EDGE_LABEL_RECT_FILL = '#fcfeff';

export interface RelatedTopologyGraphChrome {
  cardDefaultBody: {
    stroke: string;
    strokeWidth: number;
    fill: string;
    filter: string;
  };
  cardActiveBody: {
    stroke: string;
    strokeWidth: number;
    fill: string;
    filter: string;
  };
  unmappedFill: string;
  unmappedStroke: string;
  labelFill: string;
  subFill: string;
  edgeStroke: string;
  edgeStrokeWidth: number;
  edgeLabelFill: string;
  edgeLabelRectFill: string;
  gridColor: string;
  gridThickness: number;
}

export const RELATED_TOPOLOGY_DEFAULT_CHROME: RelatedTopologyGraphChrome = {
  cardDefaultBody: {
    stroke: RELATED_TOPOLOGY_VISUAL.card.defaultBody.stroke,
    strokeWidth: RELATED_TOPOLOGY_VISUAL.card.defaultBody.strokeWidth,
    fill: RELATED_TOPOLOGY_VISUAL.card.defaultBody.fill,
    filter: RELATED_TOPOLOGY_VISUAL.card.defaultBody.filter,
  },
  cardActiveBody: {
    stroke: RELATED_TOPOLOGY_VISUAL.card.activeBody.stroke,
    strokeWidth: RELATED_TOPOLOGY_VISUAL.card.activeBody.strokeWidth,
    fill: RELATED_TOPOLOGY_VISUAL.card.activeBody.fill,
    filter: RELATED_TOPOLOGY_VISUAL.card.activeBody.filter,
  },
  unmappedFill: RELATED_TOPOLOGY_UNMAPPED_FILL,
  unmappedStroke: RELATED_TOPOLOGY_UNMAPPED_STROKE,
  labelFill: RELATED_TOPOLOGY_VISUAL.card.label.fill,
  subFill: RELATED_TOPOLOGY_VISUAL.card.label.subFill,
  edgeStroke: RELATED_TOPOLOGY_VISUAL.edge.stroke,
  edgeStrokeWidth: RELATED_TOPOLOGY_VISUAL.edge.strokeWidth,
  edgeLabelFill: RELATED_TOPOLOGY_VISUAL.labelFill,
  edgeLabelRectFill: RELATED_TOPOLOGY_EDGE_LABEL_RECT_FILL,
  gridColor: RELATED_TOPOLOGY_VISUAL.grid.color,
  gridThickness: RELATED_TOPOLOGY_VISUAL.grid.thickness,
};

/** Aligns with network-status-topology `STATUS_TOPOLOGY_PALETTE_DARK`. */
export const RELATED_TOPOLOGY_SCREEN_DARK_CHROME: RelatedTopologyGraphChrome = {
  cardDefaultBody: {
    stroke: 'rgba(124, 193, 251, 0.34)',
    strokeWidth: 1,
    fill: '#14243a',
    filter:
      'drop-shadow(0 10px 22px rgba(0, 8, 20, 0.32)) drop-shadow(0 1px 2px rgba(0, 8, 20, 0.18))',
  },
  cardActiveBody: {
    stroke: '#73A7FF',
    strokeWidth: 2,
    fill: '#1b3150',
    filter:
      'drop-shadow(0 12px 26px rgba(115, 167, 255, 0.22)) drop-shadow(0 1px 2px rgba(0, 8, 20, 0.2))',
  },
  unmappedFill: 'rgba(16, 42, 72, 0.62)',
  unmappedStroke: 'rgba(124, 193, 251, 0.28)',
  labelFill: '#eef4fc',
  subFill: 'rgba(211, 225, 241, 0.82)',
  edgeStroke: 'rgba(168, 196, 228, 0.78)',
  edgeStrokeWidth: RELATED_TOPOLOGY_VISUAL.edge.strokeWidth,
  edgeLabelFill: 'rgba(211, 225, 241, 0.92)',
  edgeLabelRectFill: 'rgba(10, 24, 42, 0.88)',
  gridColor: 'rgba(124, 193, 251, 0.16)',
  gridThickness: RELATED_TOPOLOGY_VISUAL.grid.thickness,
};

export const relatedTopologyGraphChrome = (
  mode?: OpsChartThemeMode,
): RelatedTopologyGraphChrome =>
  mode === 'screen-dark'
    ? RELATED_TOPOLOGY_SCREEN_DARK_CHROME
    : RELATED_TOPOLOGY_DEFAULT_CHROME;

export const RELATED_TOPOLOGY_CANVAS_STYLE = {
  background: NETWORK_TOPO_VISUAL.canvas.background,
  border: NETWORK_TOPO_VISUAL.canvas.border,
  borderRadius: NETWORK_TOPO_VISUAL.canvas.borderRadius,
  overflow: NETWORK_TOPO_VISUAL.canvas.overflow,
} as const;

export const RELATED_TOPOLOGY_SCREEN_CANVAS_STYLE = {
  background:
    'var(--screen-widget-bg, linear-gradient(180deg, rgba(4, 24, 46, 0.86) 0%, rgba(2, 8, 20, 0.92) 100%))',
  border: '1px solid var(--screen-widget-border, rgba(103, 232, 249, 0.16))',
  borderRadius: NETWORK_TOPO_VISUAL.canvas.borderRadius,
  overflow: NETWORK_TOPO_VISUAL.canvas.overflow,
  boxShadow:
    'var(--screen-widget-shadow, inset 0 0 54px rgba(14, 165, 233, 0.08))',
} as const;

export const relatedTopologyCanvasStyle = (usesScreenTheme: boolean) =>
  usesScreenTheme
    ? RELATED_TOPOLOGY_SCREEN_CANVAS_STYLE
    : RELATED_TOPOLOGY_CANVAS_STYLE;
