import ChartNode from '../components/chartNode';
import { Graph, Node } from '@antv/x6';
import type { Attr } from '@antv/x6/es/registry/attr';
import { register } from '@antv/x6-react-shape';
import { NODE_DEFAULTS, PORT_DEFAULTS } from '../constants/nodeDefaults';
import { createPortConfig } from './topologyUtils';
import {
  getBasicShapeAttrs,
  getLabelAttrsByDirection,
  resolveConfiguredNodeSize,
  resolveNodePosition,
} from './nodeStyleUtils';
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
  const { x, y } = resolveNodePosition(nodeConfig);

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
  const attrs: Attr.CellAttrs = {
    body: {
      fill: nodeConfig.styleConfig?.backgroundColor || 'transparent',
      stroke: nodeConfig.styleConfig?.borderColor || 'transparent',
      strokeWidth: NODE_DEFAULTS.SINGLE_VALUE_NODE.strokeWidth,
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
