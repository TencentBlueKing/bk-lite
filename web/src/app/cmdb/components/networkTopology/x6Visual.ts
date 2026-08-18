export const HUB_COLOR = '#0070fa';

/**
 * CMDB 网络拓扑主视觉：对齐运营分析「网络状态拓扑」——
 * Icon 居中为主对象，名称/类型在下方，端口标签纯文字无底框。
 */
export const NETWORK_TOPO_VISUAL = {
  shape: 'topo-network-device-v3',
  node: {
    width: 160,
    height: 120,
    iconSize: 72,
    iconTop: 4,
    labelNameY: 88,
    labelTypeY: 106,
    nameFontSize: 15,
    typeFontSize: 13,
    badgeRadius: 10,
    badgeFontSize: 11,
    selectedStroke: HUB_COLOR,
    /** Soft edge glow for active/center (no hard ring). Keep subtle. */
    activeGlow: {
      haloFill: 'rgba(0, 112, 250, 0.16)',
      haloRadiusExtra: 6,
      haloBlur: 'blur(3px)',
      iconFilter:
        'drop-shadow(0 0 2px rgba(0, 112, 250, 0.55)) drop-shadow(0 0 5px rgba(0, 112, 250, 0.28))',
    },
    /** @deprecated card-only; kept so editing helpers can no-op safely */
    radius: 0,
    defaultBody: {
      fill: 'none',
      stroke: 'none',
      strokeWidth: 0,
      filter: 'none',
    },
    activeBody: {
      fill: 'none',
      stroke: 'none',
      strokeWidth: 0,
      filter: 'none',
    },
  },
  layout: {
    columnGap: 360,
    rowGap: 168,
  },
  edge: {
    stroke: '#9fb8d5',
    strokeWidth: 1.35,
    selectedStroke: HUB_COLOR,
  },
  label: {
    textFill: '#60758d',
  },
  portLabelPosition: {
    source: 0.14,
    target: 0.86,
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

/**
 * 旧卡片节点视觉：应用拓扑总览仍复用 `topo-network-device` 卡片 shape。
 * 网络拓扑已切到 NETWORK_TOPO_VISUAL（icon-centric）。
 */
export const NETWORK_TOPO_CARD_VISUAL = {
  shape: 'topo-network-device',
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
  edge: {
    stroke: '#9fb8d5',
    strokeWidth: 1.15,
    selectedStroke: HUB_COLOR,
  },
  portLabelPosition: {
    source: 0.22,
    target: 0.78,
  },
} as const;

/** 纯文字端口标签，无底框（对齐运营分析网络状态拓扑） */
export const buildNetworkTopoPortLabel = (position: number, text: string) => ({
  position,
  markup: [{ tagName: 'text', selector: 'txt' }],
  attrs: {
    txt: {
      text: text || '--',
      fill: NETWORK_TOPO_VISUAL.label.textFill,
      fontSize: 11,
      fontWeight: 600,
      textAnchor: 'middle',
      textVerticalAnchor: 'middle',
      pointerEvents: 'none',
    },
  },
});
