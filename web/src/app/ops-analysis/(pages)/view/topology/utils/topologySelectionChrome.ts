import type { Node } from '@antv/x6';
import { COLORS, SPACING } from '../constants/nodeDefaults';

/** 与拓扑 SVG 节点 highlightCell 相同的选中描边。 */
export const TOPOLOGY_SELECTED_STROKE = COLORS.PRIMARY;
export const TOPOLOGY_SELECTED_STROKE_WIDTH = SPACING.STROKE_WIDTH.DEFAULT;
export const TOPOLOGY_CHART_NODE_CLASS = 'ops-topology-chart-node';
export const TOPOLOGY_CHART_NODE_SELECTED_CLASS =
  'ops-topology-chart-node--selected';

interface TopologyNodeChromeData {
  type?: string;
  styleConfig?: { borderColor?: string };
}

const normalizeStroke = (stroke: unknown): string =>
  String(stroke ?? '').trim().toLowerCase();

export const isTopologyNodeSelectionChrome = (
  node: Pick<Node, 'getAttrByPath'>,
): boolean =>
  normalizeStroke(node.getAttrByPath('body/stroke')) ===
  normalizeStroke(TOPOLOGY_SELECTED_STROKE);

export const highlightTopologyNode = (node: Pick<Node, 'setAttrByPath'>): void => {
  node.setAttrByPath('body/stroke', TOPOLOGY_SELECTED_STROKE);
  node.setAttrByPath('body/strokeWidth', TOPOLOGY_SELECTED_STROKE_WIDTH);
};

export const getTopologyNodeResetStroke = (
  nodeData: TopologyNodeChromeData | undefined,
): string => {
  if (nodeData?.type === 'single-value') {
    return nodeData.styleConfig?.borderColor || 'transparent';
  }
  if (nodeData?.type === 'text') {
    return 'transparent';
  }
  return nodeData?.styleConfig?.borderColor || COLORS.BORDER.DEFAULT;
};

export const resetTopologyNodeChrome = (
  node: Pick<Node, 'getData' | 'setAttrByPath'>,
): void => {
  node.setAttrByPath('body/stroke', getTopologyNodeResetStroke(node.getData()));
  node.setAttrByPath('body/strokeWidth', SPACING.STROKE_WIDTH.THIN);
};
