import { NETWORK_TOPO_VISUAL } from './x6Visual';

export const NETWORK_TOPOLOGY_VIEWBOX = {
  width: 920,
  height: 520,
};

export const NETWORK_TOPOLOGY_VISUAL = {
  node: {
    width: NETWORK_TOPO_VISUAL.node.width,
    height: NETWORK_TOPO_VISUAL.node.height,
    iconSize: NETWORK_TOPO_VISUAL.node.iconSize,
    iconTop: NETWORK_TOPO_VISUAL.node.iconTop,
  },
  layout: {
    columnGap: NETWORK_TOPO_VISUAL.layout.columnGap,
    rowGap: NETWORK_TOPO_VISUAL.layout.rowGap,
    paddingX: 72,
    paddingY: 72,
  },
  edge: {
    stroke: NETWORK_TOPO_VISUAL.edge.stroke,
    activeStroke: '#ff4d4f',
    selectedStroke: NETWORK_TOPO_VISUAL.edge.selectedStroke,
  },
  status: {
    normal: '#39c78f',
    warning: '#f5b544',
    error: '#ff4d4f',
    critical: '#ff4d4f',
  },
} as const;
