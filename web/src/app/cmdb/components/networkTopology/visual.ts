import { NETWORK_TOPO_VISUAL } from './x6Visual';

export const NETWORK_TOPOLOGY_VIEWBOX = {
  width: 920,
  height: 520,
};

export const NETWORK_TOPOLOGY_VISUAL = {
  node: {
    width: NETWORK_TOPO_VISUAL.node.width,
    height: NETWORK_TOPO_VISUAL.node.height,
    radius: NETWORK_TOPO_VISUAL.node.radius,
    iconColumnWidth: NETWORK_TOPO_VISUAL.node.iconColumnWidth,
    iconPlateSize: NETWORK_TOPO_VISUAL.node.iconPlateSize,
    iconSize: NETWORK_TOPO_VISUAL.node.iconSize,
    labelX: NETWORK_TOPO_VISUAL.node.label.x,
    labelWidth: NETWORK_TOPO_VISUAL.node.label.width,
  },
  layout: {
    columnGap: NETWORK_TOPO_VISUAL.layout.columnGap,
    rowGap: NETWORK_TOPO_VISUAL.layout.rowGap,
    paddingX: 72,
    paddingY: 72,
  },
  edge: {
    stroke: '#9fb8d5',
    activeStroke: '#ff4d4f',
    selectedStroke: '#0070fa',
  },
  status: {
    normal: '#39c78f',
    warning: '#f5b544',
    error: '#ff4d4f',
    critical: '#ff4d4f',
  },
} as const;
