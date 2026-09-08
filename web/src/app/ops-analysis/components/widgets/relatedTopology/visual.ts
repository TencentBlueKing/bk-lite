import {
  NETWORK_TOPO_CARD_VISUAL,
  NETWORK_TOPO_VISUAL,
} from '@/app/cmdb/components/networkTopology/x6Visual';

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

export const RELATED_TOPOLOGY_CANVAS_STYLE = {
  background: NETWORK_TOPO_VISUAL.canvas.background,
  border: NETWORK_TOPO_VISUAL.canvas.border,
  borderRadius: NETWORK_TOPO_VISUAL.canvas.borderRadius,
  overflow: NETWORK_TOPO_VISUAL.canvas.overflow,
} as const;
