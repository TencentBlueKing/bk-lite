export const HUB_COLOR = '#0070fa';

export const NETWORK_TOPO_VISUAL = {
  node: {
    width: 272,
    height: 74,
    radius: 8,
    iconColumnWidth: 62,
    iconPlateSize: 34,
    iconSize: 22,
    defaultBody: {
      stroke: '#dbe7f4',
      strokeWidth: 1,
      fill: '#ffffff',
      filter:
        'drop-shadow(0 12px 26px rgba(37, 72, 111, 0.08)) drop-shadow(0 1px 2px rgba(15, 23, 42, 0.04))',
    },
    activeBody: {
      stroke: HUB_COLOR,
      strokeWidth: 2,
      fill: '#ffffff',
      filter:
        'drop-shadow(0 14px 30px rgba(0,112,250,0.14)) drop-shadow(0 1px 2px rgba(15, 23, 42, 0.05))',
    },
    iconPlate: {
      fill: '#edf7ff',
      stroke: '#cfe6ff',
    },
    label: {
      x: 78,
      width: 170,
      fill: '#1f2a37',
      subFill: '#8797aa',
    },
  },
  layout: {
    columnGap: 560,
    rowGap: 142,
  },
  edge: {
    stroke: '#9fb8d5',
    strokeWidth: 1.15,
    selectedStroke: HUB_COLOR,
  },
  label: {
    textFill: '#60758d',
    bgFill: '#ffffff',
    bgStroke: '#d7e5f3',
  },
  portLabelPosition: {
    source: 0.22,
    target: 0.78,
  },
  canvas: {
    background:
      'radial-gradient(circle at 18% 14%, rgba(225, 241, 255, 0.34), transparent 30%), radial-gradient(circle at 78% 20%, rgba(232, 250, 246, 0.26), transparent 28%), linear-gradient(180deg, #fcfeff 0%, #f9fcff 100%)',
    borderRadius: 10,
    overflow: 'hidden' as const,
    border: '1px solid #e5eef8',
  },
  grid: {
    color: 'rgba(116, 145, 181, 0.22)',
    thickness: 1,
  },
  minimap: {
    border: '1px solid #dbe8f6',
    borderRadius: 6,
    bottom: 16,
    right: 16,
    position: 'absolute' as const,
    background: 'rgba(255, 255, 255, 0.88)',
    boxShadow: '0 12px 28px rgba(42, 72, 116, 0.10)',
  },
} as const;

export const buildNetworkTopoPortLabel = (position: number, text: string) => ({
  position,
  markup: [
    { tagName: 'rect', selector: 'bg' },
    { tagName: 'text', selector: 'txt' },
  ],
  attrs: {
    txt: {
      text: text || '--',
      fill: NETWORK_TOPO_VISUAL.label.textFill,
      fontSize: 12,
      fontWeight: 600,
      textAnchor: 'middle',
      textVerticalAnchor: 'middle',
    },
    bg: {
      ref: 'txt',
      refWidth: '142%',
      refHeight: '142%',
      refX: '-21%',
      refY: '-21%',
      fill: NETWORK_TOPO_VISUAL.label.bgFill,
      stroke: NETWORK_TOPO_VISUAL.label.bgStroke,
      strokeWidth: 1,
      rx: 5,
      ry: 5,
      filter: 'drop-shadow(0 2px 4px rgba(42, 72, 116, 0.08))',
    },
  },
});
