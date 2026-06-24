import ChartNode from '../components/chartNode';
import { Graph, Node } from '@antv/x6';
import { register } from '@antv/x6-react-shape';
import { NODE_DEFAULTS, PORT_DEFAULTS } from '../constants/nodeDefaults';
import {
  buildTechFramePath,
  getNodeGlowAttrs,
  resolveConfiguredNodeSize,
  toRgbaColor,
} from './nodeRenderEffects';
import { createPortConfig } from './topologyUtils';
import { iconList } from '@/app/cmdb/utils/common';
import type {
  TopologyNodeData,
  BaseNodeData,
  CreatedNodeConfig,
} from '@/app/ops-analysis/types/topology';

const NODE_TYPE_MAP = {
  'icon': 'icon-node',
  'single-value': 'single-value-node',
  'text': 'text-node',
  'chart': 'chart-node',
  'basic-shape': 'basic-shape-node'
} as const;

const DEFAULT_ICON_PATH = '/assets/icons/cc-default_默认.svg';

const getBasicShapeAttrs = (nodeConfig: TopologyNodeData, shapeType?: string): Record<string, any> => {
  const { BASIC_SHAPE_NODE } = NODE_DEFAULTS;
  const backgroundColor = nodeConfig.styleConfig?.backgroundColor;
  const borderColor = nodeConfig.styleConfig?.borderColor;
  const borderWidth = nodeConfig.styleConfig?.borderWidth;
  const lineType = nodeConfig.styleConfig?.lineType;
  const renderEffect = nodeConfig.styleConfig?.renderEffect;
  const frameVariant = nodeConfig.styleConfig?.frameVariant;
  const width = nodeConfig.styleConfig?.width || BASIC_SHAPE_NODE.width;
  const height = nodeConfig.styleConfig?.height || BASIC_SHAPE_NODE.height;
  const effectiveBorderColor = borderColor || BASIC_SHAPE_NODE.borderColor;
  const effectiveBorderWidth = Math.max(Number(borderWidth) || 1, 1);

  const isTransparent = !backgroundColor ||
    backgroundColor === 'transparent' ||
    backgroundColor === 'none' ||
    backgroundColor === '' ||
    backgroundColor === 'rgba(0,0,0,0)';

  const baseAttrs: any = {
    body: {
      fill: isTransparent ? BASIC_SHAPE_NODE.backgroundColor : backgroundColor,
      stroke: effectiveBorderColor,
      strokeWidth: borderWidth || 0,
      rx: 16,
      ry: 16,
      opacity: 1
    },
    frame: { display: 'none' },
    innerFrame: { display: 'none' },
  };

  if (renderEffect === 'glow') {
    Object.assign(
      baseAttrs.body,
      getNodeGlowAttrs(effectiveBorderColor, effectiveBorderWidth),
    );
  } else if (['glass', undefined].includes(renderEffect)) {
    baseAttrs.body.filter = 'drop-shadow(2px 4px 6px rgba(0, 0, 0, 0.25))';
    baseAttrs.body.stroke = toRgbaColor(effectiveBorderColor, 0.8);
  } else {
    baseAttrs.body.filter = '';
  }

  if (frameVariant === 'tech') {
    baseAttrs.body.stroke = 'transparent';
    baseAttrs.body.strokeWidth = 0;
    baseAttrs.body.rx = 10;
    baseAttrs.body.ry = 10;
    baseAttrs.frame = {
      display: 'block',
      d: buildTechFramePath(width, height, { cornerSize: 24 }),
      fill: 'none',
      stroke: effectiveBorderColor,
      strokeWidth: effectiveBorderWidth,
      filter: renderEffect === 'glow'
        ? getNodeGlowAttrs(effectiveBorderColor, effectiveBorderWidth).filter
        : baseAttrs.body.filter,
      pointerEvents: 'none',
    };
    baseAttrs.innerFrame = {
      display: 'block',
      d: buildTechFramePath(width, height, { inset: 9, cornerSize: 18 }),
      fill: 'none',
      stroke: toRgbaColor(effectiveBorderColor, 0.34),
      strokeWidth: Math.max(effectiveBorderWidth - 1, 1),
      pointerEvents: 'none',
    };
  }

  if (lineType === 'dashed') {
    baseAttrs.body.strokeDasharray = '8,4';
  } else if (lineType === 'dotted') {
    baseAttrs.body.strokeDasharray = '2,2';
  } else {
    baseAttrs.body.strokeDasharray = '';
  }

  if (shapeType === 'circle') {
    baseAttrs.body.rx = '50%';
    baseAttrs.body.ry = '50%';
  } else if (shapeType === 'polygon') {
    baseAttrs.body.rx = 0;
    baseAttrs.body.ry = 0;
  }

  return baseAttrs;
};

const getLabelAttrsByDirection = (direction: 'top' | 'bottom' | 'left' | 'right' = 'bottom') => {
  switch (direction) {
    case 'top':
      return {
        textAnchor: 'middle',
        textVerticalAnchor: 'bottom',
        refX: '50%',
        refY: '0%',
        refY2: '-8',
        textWrap: { width: '90%', ellipsis: true }
      };
    case 'bottom':
      return {
        textAnchor: 'middle',
        textVerticalAnchor: 'top',
        refX: '50%',
        refY: '100%',
        refY2: '8',
        textWrap: { width: '90%', ellipsis: true }
      };
    case 'left':
      return {
        textAnchor: 'end',
        textVerticalAnchor: 'middle',
        refX: '0%',
        refX2: '-5',
        refY: '50%',
        refY2: '1',
        textWrap: { width: '60px', ellipsis: true }
      };
    case 'right':
      return {
        textAnchor: 'start',
        textVerticalAnchor: 'middle',
        refX: '100%',
        refX2: '5',
        refY: '50%',
        refY2: '1',
        textWrap: { width: '60px', ellipsis: true }
      };
    default:
      return {
        textAnchor: 'middle',
        textVerticalAnchor: 'top',
        refX: '50%',
        refY: '100%',
        refY2: '8',
        textWrap: { width: '90%', ellipsis: true }
      };
  }
};

const registerIconNode = () => {
  const { ICON_NODE } = NODE_DEFAULTS;

  Graph.registerNode('icon-node', {
    inherit: 'rect',
    width: ICON_NODE.width,
    height: ICON_NODE.height,
    markup: [
      { tagName: 'rect', selector: 'body' },
      { tagName: 'image', selector: 'image' },
      { tagName: 'text', selector: 'label' }
    ],
    attrs: {
      body: {
        fill: ICON_NODE.backgroundColor,
        stroke: ICON_NODE.borderColor,
        strokeWidth: ICON_NODE.strokeWidth,
        rx: ICON_NODE.borderRadius,
        ry: ICON_NODE.borderRadius
      },
      image: {
        fill: ICON_NODE.backgroundColor,
        refWidth: '70%',
        refHeight: '70%',
        refX: '50%',
        refY: '50%',
        refX2: '-36%',
        refY2: '-35%',
        'xlink:href': DEFAULT_ICON_PATH
      },
      label: {
        fill: ICON_NODE.textColor,
        fontSize: ICON_NODE.fontSize,
        fontWeight: ICON_NODE.fontWeight,
        textAnchor: 'middle',
        textVerticalAnchor: 'top',
        refX: '50%',
        refY: '100%',
        refY2: '20',
        textWrap: { width: '90%', ellipsis: true }
      }
    }
  }, true);
};

const registerSingleValueNode = () => {
  const { SINGLE_VALUE_NODE } = NODE_DEFAULTS;

  Graph.registerNode('single-value-node', {
    inherit: 'rect',
    width: SINGLE_VALUE_NODE.width,
    height: SINGLE_VALUE_NODE.height,
    markup: [
      { tagName: 'rect', selector: 'body' },
      { tagName: 'text', selector: 'label' },
      { tagName: 'text', selector: 'nameLabel' }
    ],
    attrs: {
      body: {
        fill: SINGLE_VALUE_NODE.backgroundColor,
        stroke: SINGLE_VALUE_NODE.borderColor,
        strokeWidth: SINGLE_VALUE_NODE.strokeWidth,
        rx: SINGLE_VALUE_NODE.borderRadius,
        ry: SINGLE_VALUE_NODE.borderRadius,
      },
      label: {
        fill: SINGLE_VALUE_NODE.textColor,
        fontSize: SINGLE_VALUE_NODE.fontSize,
        fontFamily: SINGLE_VALUE_NODE.fontFamily,
        textAnchor: 'middle',
        textVerticalAnchor: 'middle',
        refX: '50%',
        refY: '38%',
        textWrap: false
      },
      nameLabel: {
        fill: '#666666',
        fontSize: 12,
        fontFamily: SINGLE_VALUE_NODE.fontFamily,
        textAnchor: 'middle',
        textVerticalAnchor: 'middle',
        refX: '50%',
        refY: '72%',
        textWrap: { width: '90%', ellipsis: true },
        display: 'none'
      }
    }
  }, true);
};

const registerTextNode = () => {
  const { TEXT_NODE } = NODE_DEFAULTS;

  Graph.registerNode('text-node', {
    inherit: 'rect',
    width: TEXT_NODE.width,
    height: TEXT_NODE.height,
    markup: [
      { tagName: 'rect', selector: 'body' },
      { tagName: 'text', selector: 'label' }
    ],
    attrs: {
      body: {
        fill: TEXT_NODE.backgroundColor,
        stroke: TEXT_NODE.borderColor,
        strokeWidth: TEXT_NODE.strokeWidth,
        rx: 6,
        ry: 6
      },
      label: {
        fill: TEXT_NODE.textColor,
        fontSize: TEXT_NODE.fontSize,
        fontWeight: TEXT_NODE.fontWeight,
        textAnchor: 'middle',
        textVerticalAnchor: 'middle',
        refX: '50%',
        refY: '50%',
        textWrap: { width: '85%', height: '85%', ellipsis: false }
      }
    }
  }, true);
};

const registerBasicShapeNode = () => {
  const { BASIC_SHAPE_NODE } = NODE_DEFAULTS;

  Graph.registerNode('basic-shape-node', {
    inherit: 'rect',
    width: BASIC_SHAPE_NODE.width,
    height: BASIC_SHAPE_NODE.height,
    markup: [
      { tagName: 'rect', selector: 'body' },
      { tagName: 'path', selector: 'frame' },
      { tagName: 'path', selector: 'innerFrame' },
    ],
    attrs: {
      body: {
        fill: BASIC_SHAPE_NODE.backgroundColor,
        stroke: BASIC_SHAPE_NODE.borderColor,
        strokeWidth: BASIC_SHAPE_NODE.borderWidth,
        rx: BASIC_SHAPE_NODE.borderRadius,
        ry: BASIC_SHAPE_NODE.borderRadius,
        opacity: 1
      },
      frame: { display: 'none' },
      innerFrame: { display: 'none' },
    }
  }, true);
};

const registerChartNode = () => {
  const { CHART_NODE } = NODE_DEFAULTS;

  register({
    shape: 'chart-node',
    width: CHART_NODE.width,
    height: CHART_NODE.height,
    component: ChartNode
  });
};

const registeredNodes = new Set<string>();
const TOPOLOGY_NODE_SHAPES = [
  'icon-node',
  'single-value-node',
  'text-node',
  'basic-shape-node',
  'chart-node',
];

export const registerNodes = () => {
  try {
    TOPOLOGY_NODE_SHAPES.forEach((shape) => {
      try {
        Graph.unregisterNode(shape);
      } catch {
        // Shape may not have been registered in this runtime yet.
      }
    });

    registerIconNode();
    registerSingleValueNode();
    registerTextNode();
    registerBasicShapeNode();
    registerChartNode();
    registeredNodes.add('icon-node');
    registeredNodes.add('single-value-node');
    registeredNodes.add('text-node');
    registeredNodes.add('basic-shape-node');
    registeredNodes.add('chart-node');
  } catch (error) {
    console.warn('节点注册失败:', error);
  }
};

export const getRegisteredNodeShape = (nodeType: string): string => {
  return NODE_TYPE_MAP[nodeType as keyof typeof NODE_TYPE_MAP] || 'icon-node';
};

const getIconUrl = (nodeConfig: TopologyNodeData): string => {
  if (nodeConfig.logoType === 'default' && nodeConfig.logoIcon) {
    if (iconList) {
      const iconItem = iconList.find(item => item.key === nodeConfig.logoIcon);
      if (iconItem) {
        return `/assets/icons/${iconItem.url}.svg`;
      }
    }
    return `/assets/icons/${nodeConfig.logoIcon}.svg`;
  }

  if (nodeConfig.logoType === 'custom' && nodeConfig.logoUrl) {
    return nodeConfig.logoUrl;
  }

  return DEFAULT_ICON_PATH;
};

const getRenderEffectBodyAttrs = (
  nodeConfig: TopologyNodeData,
  defaultStrokeWidth = 1,
): Record<string, any> => {
  const renderEffect = nodeConfig.styleConfig?.renderEffect;
  if (renderEffect === 'glow') {
    return getNodeGlowAttrs(nodeConfig.styleConfig?.borderColor, defaultStrokeWidth);
  }
  if (renderEffect === 'glass') {
    return {
      stroke: toRgbaColor(nodeConfig.styleConfig?.borderColor, 0.72),
      strokeWidth: Math.max(Number(defaultStrokeWidth) || 0, 1),
      filter: 'drop-shadow(2px 4px 6px rgba(0, 0, 0, 0.22))',
    };
  }

  return { filter: '' };
};

const createIconNode = (nodeConfig: TopologyNodeData, baseNodeData: BaseNodeData): CreatedNodeConfig => {
  const logoUrl = getIconUrl(nodeConfig);
  const { ICON_NODE } = NODE_DEFAULTS;

  const iconPadding = nodeConfig.styleConfig?.iconPadding || 0;
  const iconSize = Math.max(10, 100 - iconPadding * 2);
  const width = nodeConfig.styleConfig?.width || ICON_NODE.width;
  const height = nodeConfig.styleConfig?.height || ICON_NODE.height;

  const textDirection = nodeConfig.styleConfig?.textDirection || 'bottom';
  const labelAttrs = getLabelAttrsByDirection(textDirection);

  const hasName = !!(nodeConfig.name && nodeConfig.name.trim());

  return {
    ...baseNodeData,
    width,
    height,
    attrs: {
      body: {
        stroke: nodeConfig.styleConfig?.borderColor || ICON_NODE.borderColor,
        strokeWidth: ICON_NODE.strokeWidth,
        fill: nodeConfig.styleConfig?.backgroundColor || ICON_NODE.backgroundColor,
        rx: ICON_NODE.borderRadius,
        ry: ICON_NODE.borderRadius,
        ...getRenderEffectBodyAttrs(nodeConfig, ICON_NODE.strokeWidth),
      },
      image: {
        'xlink:href': logoUrl,
        refWidth: `${iconSize}%`,
        refHeight: `${iconSize}%`,
        refX: '50%',
        refY: '50%',
        refX2: `-${iconSize / 2}%`,
        refY2: `-${iconSize / 2}%`,
      },
      label: {
        fill: nodeConfig.styleConfig?.textColor || ICON_NODE.textColor,
        fontSize: nodeConfig.styleConfig?.fontSize || ICON_NODE.fontSize,
        fontWeight: ICON_NODE.fontWeight,
        text: hasName ? nodeConfig.name : '',
        display: hasName ? 'block' : 'none',
        ...labelAttrs
      }
    },
    ports: createPortConfig(PORT_DEFAULTS.FILL_COLOR, { width, height })
  };
};

const createSingleValueNode = (nodeConfig: TopologyNodeData, baseNodeData: BaseNodeData): CreatedNodeConfig => {
  const valueConfig = nodeConfig.valueConfig || {};
  const hasDataSource = !!(valueConfig.dataSource && (valueConfig.selectedFields?.length ?? 0) > 0);
  const hasName = !!(nodeConfig.name && nodeConfig.name.trim());
  const initialText = hasDataSource ? 'loading' : '--';
  const { width, height } = resolveConfiguredNodeSize(
    nodeConfig.styleConfig,
    {
      width: NODE_DEFAULTS.SINGLE_VALUE_NODE.width,
      height: NODE_DEFAULTS.SINGLE_VALUE_NODE.height,
    },
  );

  return {
    ...baseNodeData,
    width,
    height,
    data: {
      ...baseNodeData.data,
      valueConfig: valueConfig,
      isLoading: hasDataSource,
      hasError: false
    },
    attrs: {
      body: {
        fill: nodeConfig.styleConfig?.backgroundColor || 'transparent',
        stroke: nodeConfig.styleConfig?.borderColor || 'transparent',
        strokeWidth: NODE_DEFAULTS.SINGLE_VALUE_NODE.strokeWidth,
        ...getRenderEffectBodyAttrs(nodeConfig, NODE_DEFAULTS.SINGLE_VALUE_NODE.strokeWidth),
      },
      label: {
        fill: nodeConfig.styleConfig?.textColor,
        fontSize: nodeConfig.styleConfig?.fontSize,
        refY: hasName ? '38%' : '50%',
        text: initialText,
        textWrap: false
      },
      nameLabel: {
        text: hasName ? nodeConfig.name : '',
        fill: nodeConfig.styleConfig?.nameColor || '#666666',
        fontSize: nodeConfig.styleConfig?.nameFontSize || 12,
        display: hasName ? 'block' : 'none'
      }
    },
    ports: createPortConfig(PORT_DEFAULTS.FILL_COLOR, { width, height })
  };
};

const createTextNode = (nodeConfig: TopologyNodeData, baseNodeData: BaseNodeData): CreatedNodeConfig => {
  const { TEXT_NODE } = NODE_DEFAULTS;
  const textContent = nodeConfig.name || '';

  const lines = textContent.split('\n');
  const fontSize = nodeConfig.styleConfig?.fontSize || TEXT_NODE.fontSize;

  const maxLineLength = Math.max(...lines.map(line => line.length), 1);

  const charWidth = fontSize * 0.7;
  const estimatedWidth = Math.max(
    120,
    Math.min(600, maxLineLength * charWidth + 40)
  );

  const lineHeight = fontSize * 1.5;
  const estimatedHeight = Math.max(
    60,
    lines.length * lineHeight + 30
  );
  const width = nodeConfig.styleConfig?.width || estimatedWidth;
  const height = nodeConfig.styleConfig?.height || estimatedHeight;

  return {
    ...baseNodeData,
    width,
    height,
    data: {
      ...baseNodeData.data,
      isPlaceholder: !nodeConfig.name
    },
    attrs: {
      body: {
        fill: nodeConfig.styleConfig?.backgroundColor || TEXT_NODE.backgroundColor,
        stroke: nodeConfig.styleConfig?.borderColor || TEXT_NODE.borderColor,
        strokeWidth: TEXT_NODE.strokeWidth,
        rx: 6,
        ry: 6
      },
      label: {
        fill: nodeConfig.styleConfig?.textColor || TEXT_NODE.textColor,
        fontSize: nodeConfig.styleConfig?.fontSize || TEXT_NODE.fontSize,
        fontWeight: nodeConfig.styleConfig?.fontWeight || TEXT_NODE.fontWeight,
        text: textContent,
        textWrap: false,
        textVerticalAnchor: 'middle',
        textAnchor: 'middle',
        refX: '50%',
        refY: '50%'
      }
    },
    ports: createPortConfig(PORT_DEFAULTS.FILL_COLOR, { width, height })
  };
};

const createBasicShapeNode = (nodeConfig: TopologyNodeData, baseNodeData: BaseNodeData): CreatedNodeConfig => {
  const { BASIC_SHAPE_NODE } = NODE_DEFAULTS;
  const shapeType = nodeConfig.styleConfig?.shapeType;
  const width = nodeConfig.styleConfig?.width || BASIC_SHAPE_NODE.width;
  const height = nodeConfig.styleConfig?.height || BASIC_SHAPE_NODE.height;

  return {
    ...baseNodeData,
    width: width,
    height: height,
    attrs: getBasicShapeAttrs(nodeConfig, shapeType),
    ports: createPortConfig(PORT_DEFAULTS.FILL_COLOR, { width, height })
  };
};

const createChartNode = (nodeConfig: TopologyNodeData, baseNodeData: BaseNodeData): CreatedNodeConfig => {
  return {
    ...baseNodeData,
    width: nodeConfig.styleConfig?.width,
    height: nodeConfig.styleConfig?.height,
    data: {
      ...baseNodeData.data,
      valueConfig: nodeConfig.valueConfig,
      isLoading: !!(nodeConfig.valueConfig?.dataSource),
      rawData: null,
      hasError: false
    },
    ports: createPortConfig()
  };
};

export const createNodeByType = (nodeConfig: TopologyNodeData): CreatedNodeConfig => {
  const shape = getRegisteredNodeShape(nodeConfig.type);

  const x = nodeConfig.position?.x ?? (nodeConfig as any).x ?? 0;
  const y = nodeConfig.position?.y ?? (nodeConfig as any).y ?? 0;

  const baseNodeData: BaseNodeData = {
    id: nodeConfig.id || '',
    x,
    y,
    shape,
    label: nodeConfig.name || '',
    data: { ...nodeConfig },
    ...(nodeConfig.zIndex !== undefined && { zIndex: nodeConfig.zIndex }),
  };
  switch (nodeConfig.type) {
    case 'icon':
      return createIconNode(nodeConfig, baseNodeData);
    case 'single-value':
      return createSingleValueNode(nodeConfig, baseNodeData);
    case 'text':
      return createTextNode(nodeConfig, baseNodeData);
    case 'basic-shape':
      return createBasicShapeNode(nodeConfig, baseNodeData);
    case 'chart':
      return createChartNode(nodeConfig, baseNodeData);
    default:
      return baseNodeData;
  }
};

const updateIconNodeAttributes = (node: Node, nodeConfig: TopologyNodeData) => {
  const logoUrl = getIconUrl(nodeConfig);
  const { ICON_NODE } = NODE_DEFAULTS;

  const iconPadding = nodeConfig.styleConfig?.iconPadding || 0;
  const iconSize = Math.max(10, 100 - iconPadding * 2);
  const width = nodeConfig.styleConfig?.width || ICON_NODE.width;
  const height = nodeConfig.styleConfig?.height || ICON_NODE.height;

  const textDirection = nodeConfig.styleConfig?.textDirection || 'bottom';
  const labelAttrs = getLabelAttrsByDirection(textDirection);

  const hasName = !!(nodeConfig.name && nodeConfig.name.trim());

  node.setAttrs({
    body: {
      stroke: nodeConfig.styleConfig?.borderColor || ICON_NODE.borderColor,
      strokeWidth: ICON_NODE.strokeWidth,
      fill: nodeConfig.styleConfig?.backgroundColor || ICON_NODE.backgroundColor,
      rx: ICON_NODE.borderRadius,
      ry: ICON_NODE.borderRadius,
      ...getRenderEffectBodyAttrs(nodeConfig, ICON_NODE.strokeWidth),
    },
    image: {
      'xlink:href': logoUrl,
      refWidth: `${iconSize}%`,
      refHeight: `${iconSize}%`,
      refX: '50%',
      refY: '50%',
      refX2: `-${iconSize / 2}%`,
      refY2: `-${iconSize / 2}%`,
    },
    label: {
      fill: nodeConfig.styleConfig?.textColor || ICON_NODE.textColor,
      fontSize: nodeConfig.styleConfig?.fontSize || ICON_NODE.fontSize,
      fontWeight: ICON_NODE.fontWeight,
      text: hasName ? nodeConfig.name : '',
      display: hasName ? 'block' : 'none',
      ...labelAttrs
    }
  });

  const { width: currentWidth, height: currentHeight } = node.getSize();

  if (currentWidth !== width || currentHeight !== height) {
    node.resize(width, height);
    node.prop('ports', createPortConfig(PORT_DEFAULTS.FILL_COLOR, { width, height }));
  }
};

const updateSingleValueNodeAttributes = (node: Node, nodeConfig: TopologyNodeData) => {
  const hasName = !!(nodeConfig.name && nodeConfig.name.trim());
  const { width, height } = resolveConfiguredNodeSize(
    nodeConfig.styleConfig,
    {
      width: NODE_DEFAULTS.SINGLE_VALUE_NODE.width,
      height: NODE_DEFAULTS.SINGLE_VALUE_NODE.height,
    },
  );

  const nodeData = node.getData();
  const isLoading = nodeData?.isLoading;

  const shouldSetDefaultText = !isLoading;
  let displayText = '';

  if (shouldSetDefaultText) {
    const currentText = node.getAttrByPath('label/text') as string;
    if (!currentText || currentText === 'loading' || currentText === '无数据') {
      displayText = hasName ? nodeConfig.name || '--' : '--';
    } else {
      displayText = currentText;
    }
  }
  const attrs: any = {
    body: {
      fill: nodeConfig.styleConfig?.backgroundColor || 'transparent',
      stroke: nodeConfig.styleConfig?.borderColor || 'transparent',
      strokeWidth: NODE_DEFAULTS.SINGLE_VALUE_NODE.strokeWidth,
      ...getRenderEffectBodyAttrs(nodeConfig, NODE_DEFAULTS.SINGLE_VALUE_NODE.strokeWidth),
    },
    label: {
      fill: nodeConfig.styleConfig?.textColor,
      fontSize: nodeConfig.styleConfig?.fontSize,
      refY: hasName ? '38%' : '50%',
      textWrap: false
    },
    nameLabel: {
      text: hasName ? nodeConfig.name : '',
      fill: nodeConfig.styleConfig?.nameColor || '#666666',
      fontSize: nodeConfig.styleConfig?.nameFontSize || 12,
      display: hasName ? 'block' : 'none'
    }
  };

  if (shouldSetDefaultText && displayText) {
    attrs.label.text = displayText;
  }

  node.setAttrs(attrs);

  const { width: currentWidth, height: currentHeight } = node.getSize();
  if (currentWidth !== width || currentHeight !== height) {
    node.resize(width, height);
    node.prop('ports', createPortConfig(PORT_DEFAULTS.FILL_COLOR, { width, height }));
  }
};

const updateTextNodeAttributes = (node: Node, nodeConfig: TopologyNodeData) => {
  const { TEXT_NODE } = NODE_DEFAULTS;
  const textContent = nodeConfig.name || '';

  const lines = textContent.split('\n');
  const fontSize = nodeConfig.styleConfig?.fontSize || TEXT_NODE.fontSize;

  const maxLineLength = Math.max(...lines.map(line => line.length), 1);

  const charWidth = fontSize * 0.7;
  const estimatedWidth = Math.max(
    120,
    Math.min(600, maxLineLength * charWidth + 40)
  );

  const lineHeight = fontSize * 1.5;
  const estimatedHeight = Math.max(
    60,
    lines.length * lineHeight + 30
  );
  const width = nodeConfig.styleConfig?.width || estimatedWidth;
  const height = nodeConfig.styleConfig?.height || estimatedHeight;

  node.resize(width, height);

  node.prop('ports', createPortConfig(PORT_DEFAULTS.FILL_COLOR, { width, height }));

  node.setAttrs({
    body: {
      fill: nodeConfig.styleConfig?.backgroundColor || TEXT_NODE.backgroundColor,
      stroke: nodeConfig.styleConfig?.borderColor || TEXT_NODE.borderColor,
      strokeWidth: TEXT_NODE.strokeWidth,
      rx: 6,
      ry: 6
    },
    label: {
      fill: nodeConfig.styleConfig?.textColor || TEXT_NODE.textColor,
      fontSize: nodeConfig.styleConfig?.fontSize || TEXT_NODE.fontSize,
      fontWeight: nodeConfig.styleConfig?.fontWeight || TEXT_NODE.fontWeight,
      text: textContent,
      textWrap: false,
      textVerticalAnchor: 'middle',
      textAnchor: 'middle',
      refX: '50%',
      refY: '50%'
    }
  });
};

const updateBasicShapeNodeAttributes = (node: Node, nodeConfig: TopologyNodeData) => {
  const shapeType = nodeConfig.styleConfig?.shapeType;
  const attrs = getBasicShapeAttrs(nodeConfig, shapeType);
  node.setAttrs(attrs);

  const width = nodeConfig.styleConfig?.width;
  const height = nodeConfig.styleConfig?.height;
  if (width && height) {
    const { width: currentWidth, height: currentHeight } = node.getSize();

    if (currentWidth !== width || currentHeight !== height) {
      node.resize(width, height);
      node.prop('ports', createPortConfig(PORT_DEFAULTS.FILL_COLOR));
    }
  }
};

export const updateNodeAttributes = (node: Node, nodeConfig: TopologyNodeData): void => {
  if (!node || !nodeConfig) return;

  if (nodeConfig.type !== 'single-value') {
    node.setAttrByPath('label/text', nodeConfig.name);
  }

  node.removeProp('data/styleConfig/thresholdColors');

  node.setData({
    ...node.getData(),
    ...nodeConfig,
  });

  const updateStrategies: Record<string, () => void> = {
    'icon': () => updateIconNodeAttributes(node, nodeConfig),
    'single-value': () => updateSingleValueNodeAttributes(node, nodeConfig),
    'text': () => updateTextNodeAttributes(node, nodeConfig),
    'basic-shape': () => updateBasicShapeNodeAttributes(node, nodeConfig)
  };

  updateStrategies[nodeConfig.type as keyof typeof updateStrategies]?.();
};
