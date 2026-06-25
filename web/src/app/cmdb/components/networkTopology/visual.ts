export const NETWORK_TOPOLOGY_VIEWBOX = {
  width: 920,
  height: 520,
};

export const NETWORK_TOPOLOGY_VISUAL = {
  node: {
    width: 230,
    height: 60,
    radius: 7,
    iconColumnWidth: 46,
    iconPlateSize: 28,
    iconSize: 18,
    labelX: 58,
    labelWidth: 154,
  },
  layout: {
    columnGap: 660,
    rowGap: 154,
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
