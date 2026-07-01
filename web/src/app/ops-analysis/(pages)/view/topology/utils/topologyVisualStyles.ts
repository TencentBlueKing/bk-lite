import { COLORS, NODE_DEFAULTS, SPACING } from '../constants/nodeDefaults';
import type {
  EdgeConnectionType,
  EdgeStyleConfig,
  TopologyEdgeVisual,
} from '@/app/ops-analysis/types/topology';

export const getTopologyDeviceNodeVisual = () => ({
  width: NODE_DEFAULTS.ICON_NODE.width,
  height: NODE_DEFAULTS.ICON_NODE.height,
  borderRadius: NODE_DEFAULTS.ICON_NODE.borderRadius,
  iconSize: 70,
  labelDirection: 'bottom' as const,
});

export const getTopologyEdgeVisual = (
  connectionType: EdgeConnectionType = 'single',
  styleConfig?: EdgeStyleConfig
) : TopologyEdgeVisual => {
  const marker = { name: 'block', size: 8 };
  const markers = {
    none: { sourceMarker: null, targetMarker: null },
    single: { sourceMarker: null, targetMarker: marker },
    double: { sourceMarker: marker, targetMarker: marker },
  };

  const lineAttrs: TopologyEdgeVisual['attrs']['line'] = {
    stroke: styleConfig?.lineColor || COLORS.EDGE.DEFAULT,
    strokeWidth: styleConfig?.lineWidth || SPACING.STROKE_WIDTH.THIN,
    ...markers[connectionType],
  };

  if (styleConfig?.lineStyle === 'dotted') {
    lineAttrs.strokeDasharray = '3 3';
  } else if (styleConfig?.lineStyle === 'point') {
    lineAttrs.strokeDasharray = '1 3';
  } else if (styleConfig?.lineStyle === 'line') {
    lineAttrs.strokeDasharray = null;
  }

  if (
    connectionType === 'single' &&
    styleConfig?.enableAnimation &&
    (styleConfig?.lineStyle === 'dotted' || styleConfig?.lineStyle === 'point')
  ) {
    lineAttrs.class = 'edge-flow-animation';
  }

  return {
    attrs: {
      line: lineAttrs,
    },
    labels: [],
  };
};

export const getTopologyEdgeLabelVisual = (text: string = '') => ({
  attrs: {
    text: {
      text,
      fill: '#333',
      fontSize: 12,
      textAnchor: 'middle',
      textVerticalAnchor: 'middle',
    },
  },
  position: 0.5,
});
