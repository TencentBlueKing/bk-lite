import type { Attr } from '@antv/x6/es/registry/attr';
import type { Point, TopologyNodeData } from '@/app/ops-analysis/types/topology';
import { NODE_DEFAULTS } from '../constants/nodeDefaults';

export const resolveConfiguredNodeSize = (
  styleConfig: { width?: number; height?: number } | undefined,
  fallback: { width: number; height: number },
): { width: number; height: number } => ({
  width: Number(styleConfig?.width) || fallback.width,
  height: Number(styleConfig?.height) || fallback.height,
});

export const resolveNodePosition = (nodeConfig: TopologyNodeData): Point => {
  const legacyPosition = nodeConfig as TopologyNodeData & Partial<Point>;

  return {
    x: nodeConfig.position?.x ?? legacyPosition.x ?? 0,
    y: nodeConfig.position?.y ?? legacyPosition.y ?? 0,
  };
};

export const getBasicShapeAttrs = (
  nodeConfig: TopologyNodeData,
  shapeType?: string,
): Attr.CellAttrs => {
  const { BASIC_SHAPE_NODE } = NODE_DEFAULTS;
  const backgroundColor = nodeConfig.styleConfig?.backgroundColor;
  const borderColor = nodeConfig.styleConfig?.borderColor;
  const borderWidth = nodeConfig.styleConfig?.borderWidth;
  const lineType = nodeConfig.styleConfig?.lineType;
  const effectiveBorderColor = borderColor || BASIC_SHAPE_NODE.borderColor;

  const isTransparent =
    !backgroundColor ||
    backgroundColor === 'transparent' ||
    backgroundColor === 'none' ||
    backgroundColor === '' ||
    backgroundColor === 'rgba(0,0,0,0)';

  const bodyAttrs: Attr.ComplexAttrs = {
    fill: isTransparent ? BASIC_SHAPE_NODE.backgroundColor : backgroundColor,
    stroke: effectiveBorderColor,
    strokeWidth: borderWidth || 0,
    rx: 16,
    ry: 16,
    opacity: 1,
  };

  if (lineType === 'dashed') {
    bodyAttrs.strokeDasharray = '8,4';
  } else if (lineType === 'dotted') {
    bodyAttrs.strokeDasharray = '2,2';
  } else {
    bodyAttrs.strokeDasharray = '';
  }

  if (shapeType === 'circle') {
    bodyAttrs.rx = '50%';
    bodyAttrs.ry = '50%';
  } else if (shapeType === 'polygon') {
    bodyAttrs.rx = 0;
    bodyAttrs.ry = 0;
  }

  return {
    body: bodyAttrs,
    frame: { display: 'none' },
    innerFrame: { display: 'none' },
  };
};

export const getLabelAttrsByDirection = (
  direction: 'top' | 'bottom' | 'left' | 'right' = 'bottom',
): Attr.ComplexAttrs => {
  switch (direction) {
    case 'top':
      return {
        textAnchor: 'middle',
        textVerticalAnchor: 'bottom',
        refX: '50%',
        refY: '0%',
        refY2: '-8',
        textWrap: { width: '90%', ellipsis: true },
      };
    case 'bottom':
      return {
        textAnchor: 'middle',
        textVerticalAnchor: 'top',
        refX: '50%',
        refY: '100%',
        refY2: '8',
        textWrap: { width: '90%', ellipsis: true },
      };
    case 'left':
      return {
        textAnchor: 'end',
        textVerticalAnchor: 'middle',
        refX: '0%',
        refX2: '-5',
        refY: '50%',
        refY2: '1',
        textWrap: { width: '60px', ellipsis: true },
      };
    case 'right':
      return {
        textAnchor: 'start',
        textVerticalAnchor: 'middle',
        refX: '100%',
        refX2: '5',
        refY: '50%',
        refY2: '1',
        textWrap: { width: '60px', ellipsis: true },
      };
    default:
      return {
        textAnchor: 'middle',
        textVerticalAnchor: 'top',
        refX: '50%',
        refY: '100%',
        refY2: '8',
        textWrap: { width: '90%', ellipsis: true },
      };
  }
};
