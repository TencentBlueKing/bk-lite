import { EdgeCreationData } from '@/app/ops-analysis/types/topology';
import { NODE_DEFAULTS, PORT_DEFAULTS, COLORS, SPACING } from '../constants/nodeDefaults';

// 通用工具函数
export const getValueByPath = (obj: any, path: string): any => {
  if (!obj || !path) return undefined;

  // 处理特殊的数据结构：包含 namespace_id 和 data 的数组
  if (Array.isArray(obj) && obj.length > 0) {
    const firstItem = obj[0];

    // 如果是特殊的数据结构
    if (firstItem && typeof firstItem === 'object' && firstItem.namespace_id && firstItem.data) {
      if (path === 'namespace_id') {
        return firstItem.namespace_id;
      }

      if (path.startsWith('data.')) {
        const fieldPath = path.substring(5); // 移除 'data.' 前缀

        // 如果 data 是数组，取第一个元素
        if (Array.isArray(firstItem.data) && firstItem.data.length > 0) {
          return getValueByPath(firstItem.data[0], fieldPath);
        } else if (typeof firstItem.data === 'object' && firstItem.data !== null) {
          return getValueByPath(firstItem.data, fieldPath);
        }
      }
    }
  }

  // 标准路径解析
  return path.split('.').reduce((current, key) => {
    if (current === null || current === undefined) return undefined;

    // 处理数组索引
    if (Array.isArray(current)) {
      const index = parseInt(key, 10);
      if (!isNaN(index) && index >= 0 && index < current.length) {
        return current[index];
      }
      // 如果key不是数字，尝试在数组的每个元素中查找
      return current.length > 0 && current[0] && typeof current[0] === 'object'
        ? current[0][key]
        : undefined;
    }

    return current[key];
  }, obj);
};

export const formatDisplayValue = (
  value: any,
  unit?: string,
  decimalPlaces?: number,
  conversionFactor?: number
): string => {
  if (value === null || value === undefined) return '--';

  // 如果是对象，直接转字符串
  if (typeof value === 'object') return JSON.stringify(value);

  // 尝试转换为数字并应用换算系数
  const numValue = typeof value === 'string' ? parseFloat(value) : value;

  if (typeof numValue === 'number' && !isNaN(numValue)) {
    // 应用换算系数
    const factor = conversionFactor !== undefined ? conversionFactor : 1;
    const convertedValue = numValue * factor;

    // 格式化小数位
    let formattedValue = decimalPlaces !== undefined
      ? convertedValue.toFixed(decimalPlaces)
      : String(convertedValue);

    // 添加单位
    if (unit && unit.trim()) {
      formattedValue += unit;
    }

    return formattedValue;
  }

  return String(value);
};

/**
 * 计算文本宽度的工具函数
 * @param text 要计算的文本内容
 * @param fontSize 字体大小
 * @param fontFamily 字体族，默认为系统字体
 * @returns 文本宽度（像素）
 */
export const calculateTextWidth = (text: string, fontSize: number, fontFamily: string = 'system-ui, -apple-system, sans-serif'): number => {
  // 创建一个临时的canvas来测量文本宽度
  const canvas = document.createElement('canvas');
  const context = canvas.getContext('2d');

  if (!context) {
    // 降级方案：根据字符数量估算宽度
    return text.length * fontSize * 0.6;
  }

  context.font = `${fontSize}px ${fontFamily}`;
  const metrics = context.measureText(text);

  // 清理canvas元素
  canvas.remove();

  return metrics.width;
};

/**
 * 调整单值节点大小以适应文本内容
 * @param node X6节点实例
 * @param text 要显示的文本
 * @param minWidth 最小宽度，默认120
 * @param padding 内边距，默认20
 */
export const adjustSingleValueNodeSize = (node: any, text: string, minWidth: number = 120, padding: number = 20) => {
  if (!node || !text) return;

  const nodeData = node.getData();
  const styleConfig = nodeData?.styleConfig || {};
  const fontSize = styleConfig.fontSize || NODE_DEFAULTS.SINGLE_VALUE_NODE.fontSize;
  const hasName = !!(nodeData?.name && nodeData.name.trim());

  // 计算文本宽度
  const textWidth = calculateTextWidth(text, fontSize);

  // 计算节点应该的宽度（文本宽度 + 内边距，但不小于最小宽度）
  const targetWidth = Math.max(textWidth + padding, minWidth);
  const currentSize = node.getSize();

  // 如果有名称，确保节点高度足够容纳内容和名称（都在边框内）
  const nameFontSize = styleConfig.nameFontSize || 12;
  const minHeightForName = hasName ? Math.max(80, fontSize + nameFontSize + 24) : NODE_DEFAULTS.SINGLE_VALUE_NODE.height;
  const targetHeight = Math.max(minHeightForName, NODE_DEFAULTS.SINGLE_VALUE_NODE.height);

  const needsWidthUpdate = Math.abs(targetWidth - currentSize.width) > 10;
  const needsHeightUpdate = Math.abs(targetHeight - currentSize.height) > 5;

  if (needsWidthUpdate || needsHeightUpdate) {
    const newWidth = needsWidthUpdate ? targetWidth : currentSize.width;
    const newHeight = needsHeightUpdate ? targetHeight : currentSize.height;

    node.resize(newWidth, newHeight);

    // 更新端口配置以适应新尺寸
    const newPortConfig = createPortConfig(PORT_DEFAULTS.FILL_COLOR, { width: newWidth, height: newHeight });
    node.prop('ports', newPortConfig);

    // 更新节点数据中的配置
    const updatedNodeData = {
      ...nodeData,
      styleConfig: {
        ...styleConfig,
        width: newWidth,
        height: newHeight,
      }
    };
    node.setData(updatedNodeData);
  }
};

// 创建端口组的通用函数 - 使用X6内置位置定位器
const createPortGroup = (positionName: string, fillColor = PORT_DEFAULTS.FILL_COLOR) => ({
  position: {
    name: positionName,
  },
  attrs: {
    circle: {
      magnet: PORT_DEFAULTS.MAGNET,
      stroke: PORT_DEFAULTS.STROKE_COLOR,
      r: PORT_DEFAULTS.RADIUS,
      fill: fillColor,
      opacity: PORT_DEFAULTS.OPACITY.HIDDEN,
    },
  },
});

// 创建标准端口配置的通用函数 - 根据节点尺寸动态生成密集端口
export const createPortConfig = (fillColor = PORT_DEFAULTS.FILL_COLOR, nodeSize = { width: 120, height: 80 }) => {
  const portGroups: any = {};
  const portItems: any[] = [];

  // 主要的四个端口（可见）
  const mainPorts = ['top', 'bottom', 'left', 'right'];
  mainPorts.forEach(portName => {
    portGroups[portName] = createPortGroup(portName, fillColor);
    portItems.push({ id: portName, group: portName });
  });

  // 固定像素间隔配置
  const PIXEL_INTERVAL = 12; // 每12像素一个端口
  const MIN_DISTANCE_FROM_CORNER = 8; // 距离角落的最小距离

  // 水平边（top, bottom）- 根据节点宽度动态生成
  ['top', 'bottom'].forEach(side => {
    const y = side === 'top' ? '0%' : '100%';
    const availableWidth = nodeSize.width - 2 * MIN_DISTANCE_FROM_CORNER;
    const numPorts = Math.floor(availableWidth / PIXEL_INTERVAL);

    for (let i = 1; i <= numPorts; i++) {
      const portName = `${side}-${i}`;
      const xPos = MIN_DISTANCE_FROM_CORNER + i * PIXEL_INTERVAL;
      const xPercent = (xPos / nodeSize.width) * 100;

      // 跳过与主端口位置重叠的端口（中心附近）
      if (Math.abs(xPercent - 50) < 8) continue;

      portGroups[portName] = {
        position: {
          name: 'absolute',
          args: { x: `${xPercent}%`, y: y }
        },
        attrs: {
          circle: {
            magnet: PORT_DEFAULTS.MAGNET,
            stroke: PORT_DEFAULTS.STROKE_COLOR,
            r: PORT_DEFAULTS.RADIUS,
            fill: fillColor,
            opacity: 0, // 完全隐藏
          },
        },
      };
      portItems.push({ id: portName, group: portName });
    }
  });

  // 垂直边（left, right）- 根据节点高度动态生成
  ['left', 'right'].forEach(side => {
    const x = side === 'left' ? '0%' : '100%';
    const availableHeight = nodeSize.height - 2 * MIN_DISTANCE_FROM_CORNER;
    const numPorts = Math.floor(availableHeight / PIXEL_INTERVAL);

    for (let i = 1; i <= numPorts; i++) {
      const portName = `${side}-${i}`;
      const yPos = MIN_DISTANCE_FROM_CORNER + i * PIXEL_INTERVAL;
      const yPercent = (yPos / nodeSize.height) * 100;

      // 跳过与主端口位置重叠的端口（中心附近）
      if (Math.abs(yPercent - 50) < 10) continue;

      portGroups[portName] = {
        position: {
          name: 'absolute',
          args: { x: x, y: `${yPercent}%` }
        },
        attrs: {
          circle: {
            magnet: PORT_DEFAULTS.MAGNET,
            stroke: PORT_DEFAULTS.STROKE_COLOR,
            r: PORT_DEFAULTS.RADIUS,
            fill: fillColor,
            opacity: 0, // 完全隐藏
          },
        },
      };
      portItems.push({ id: portName, group: portName });
    }
  });

  return {
    groups: portGroups,
    items: portItems,
  };
};
export const createEdgeLabel = (text: string = '') => {
  return {
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
  };
};

// 根据样式配置获取边线样式
export const getEdgeStyleWithConfig = (
  connectionType: 'none' | 'single' | 'double' = 'single',
  styleConfig?: {
    lineColor?: string;
    lineWidth?: number;
    lineStyle?: 'line' | 'dotted' | 'point';
    enableAnimation?: boolean;
  }
) => {
  const arrowConfig = {
    none: { sourceMarker: null, targetMarker: null },
    single: { sourceMarker: null, targetMarker: { name: 'block', size: 8 } },
    double: {
      sourceMarker: { name: 'block', size: 8 },
      targetMarker: { name: 'block', size: 8 },
    },
  };

  const lineAttrs: any = {
    stroke: styleConfig?.lineColor || COLORS.EDGE.DEFAULT,
    strokeWidth: styleConfig?.lineWidth || SPACING.STROKE_WIDTH.THIN,
    ...arrowConfig[connectionType],
  };

  // 设置线条样式
  if (styleConfig?.lineStyle === 'dotted') {
    lineAttrs.strokeDasharray = '3 3';
  } else if (styleConfig?.lineStyle === 'point') {
    lineAttrs.strokeDasharray = '1 3';
  } else if (styleConfig?.lineStyle === 'line') {
    lineAttrs.strokeDasharray = null;
  }

  // 设置动画
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

export const getEdgeStyleWithLabel = (
  edgeData: EdgeCreationData,
  connectionType: 'none' | 'single' | 'double' = 'single',
  styleConfig?: {
    lineColor?: string;
    lineWidth?: number;
    lineStyle?: 'line' | 'dotted' | 'point';
    enableAnimation?: boolean;
  }
): any => {
  // 如果没有提供样式配置，使用默认配置
  const defaultStyleConfig = {
    lineColor: COLORS.EDGE.DEFAULT,
    lineWidth: 1,
    lineStyle: 'line' as const,
    enableAnimation: false,
  };

  const baseStyle = getEdgeStyleWithConfig(connectionType, styleConfig || defaultStyleConfig);

  if (edgeData.lineType === 'common_line' && edgeData.lineName) {
    (baseStyle as any).labels = [createEdgeLabel(edgeData.lineName)];
  } else {
    (baseStyle as any).labels = [];
  }

  return baseStyle;
};

// 创建边工具配置的通用函数
const createEdgeToolConfig = (opacity: number) => ({
  vertices: {
    name: 'vertices',
    args: {
      attrs: {
        fill: COLORS.PRIMARY,
        opacity,
      },
      snapRadius: 20,
      addable: true,
      removable: true,
      removeRedundancies: true,
    },
  },
  sourceArrowhead: {
    name: 'source-arrowhead',
    args: {
      attrs: {
        d: 'M 0 -6 A 6 6 0 1 0 0 6 A 6 6 0 1 0 0 -6',
        fill: COLORS.PRIMARY,
        stroke: COLORS.BACKGROUND.WHITE,
        strokeWidth: SPACING.STROKE_WIDTH.THIN,
        cursor: 'move',
        opacity,
      },
    },
  },
  targetArrowhead: {
    name: 'target-arrowhead',
    args: {
      attrs: {
        d: 'M 0 -6 A 6 6 0 1 0 0 6 A 6 6 0 1 0 0 -6',
        fill: COLORS.PRIMARY,
        stroke: COLORS.BACKGROUND.WHITE,
        strokeWidth: SPACING.STROKE_WIDTH.THIN,
        cursor: 'move',
        opacity,
      },
    },
  },
});

export const addEdgeTools = (edge: any) => {
  const toolConfig = createEdgeToolConfig(PORT_DEFAULTS.OPACITY.HIDDEN);

  // 添加顶点编辑工具（默认透明）
  edge.addTools(toolConfig.vertices);
  // 添加源端点工具（起点，默认透明）
  edge.addTools(toolConfig.sourceArrowhead);
  // 添加目标端点工具（终点，默认透明）
  edge.addTools(toolConfig.targetArrowhead);
};

// 显示边工具
export const showEdgeTools = (edge: any) => {
  edge.removeTools();

  const toolConfig = createEdgeToolConfig(PORT_DEFAULTS.OPACITY.VISIBLE);

  edge.addTools(toolConfig.vertices);
  edge.addTools(toolConfig.sourceArrowhead);
  edge.addTools(toolConfig.targetArrowhead);
};

// 隐藏边工具
export const hideEdgeTools = (edge: any) => {
  edge.removeTools();
};

// 隐藏所有边的工具
export const hideAllEdgeTools = (graph: any) => {
  graph.getEdges().forEach((edge: any) => {
    hideEdgeTools(edge);
  });
};

export const showPorts = (graph: any, cell: any) => {
  if (cell.isNode()) {
    ['top', 'bottom', 'left', 'right'].forEach((port) =>
      cell.setPortProp(port, 'attrs/circle/opacity', PORT_DEFAULTS.OPACITY.VISIBLE)
    );
  } else if (cell.isEdge()) {
    ['top', 'bottom', 'left', 'right'].forEach((port) => {
      const sourceNode = graph.getCellById(cell.getSourceCellId());
      const targetNode = graph.getCellById(cell.getTargetCellId());
      if (sourceNode) {
        sourceNode.setPortProp(port, 'attrs/circle/opacity', PORT_DEFAULTS.OPACITY.VISIBLE);
      }
      if (targetNode) {
        targetNode.setPortProp(port, 'attrs/circle/opacity', PORT_DEFAULTS.OPACITY.VISIBLE);
      }
    });
  }
};

export const hideAllPorts = (graph: any) => {
  graph.getNodes().forEach((node: any) => {
    ['top', 'bottom', 'left', 'right'].forEach((port: string) =>
      node.setPortProp(port, 'attrs/circle/opacity', PORT_DEFAULTS.OPACITY.HIDDEN)
    );
  });
};

// 计算两个节点之间的最佳连接端口
export const calculateOptimalPorts = (sourceNode: any, targetNode: any): { sourcePort: string; targetPort: string } => {
  const sourceBBox = sourceNode.getBBox();
  const targetBBox = targetNode.getBBox();

  const sourceCenterX = sourceBBox.x + sourceBBox.width / 2;
  const sourceCenterY = sourceBBox.y + sourceBBox.height / 2;
  const targetCenterX = targetBBox.x + targetBBox.width / 2;
  const targetCenterY = targetBBox.y + targetBBox.height / 2;

  const deltaX = targetCenterX - sourceCenterX;
  const deltaY = targetCenterY - sourceCenterY;

  let sourcePort = 'right';
  let targetPort = 'left';

  if (Math.abs(deltaX) > Math.abs(deltaY)) {
    // 水平方向为主
    sourcePort = deltaX > 0 ? 'right' : 'left';
    targetPort = deltaX > 0 ? 'left' : 'right';
  } else {
    // 垂直方向为主
    sourcePort = deltaY > 0 ? 'bottom' : 'top';
    targetPort = deltaY > 0 ? 'top' : 'bottom';
  }

  return { sourcePort, targetPort };
};
