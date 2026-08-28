import type { Node } from '@antv/x6';
import { COLORS, SPACING } from '../constants/nodeDefaults';

/** 选中描边锁定为语义主色，hover 不得换成别的蓝。 */
export const TOPOLOGY_SELECTED_STROKE = 'var(--color-primary)';
export const TOPOLOGY_SELECTED_STROKE_WIDTH = SPACING.STROKE_WIDTH.DEFAULT;
export const TOPOLOGY_CHART_NODE_CLASS = 'ops-topology-chart-node';
export const TOPOLOGY_CHART_NODE_SELECTED_CLASS =
  'ops-topology-chart-node--selected';

interface TopologyNodeChromeData {
  type?: string;
  styleConfig?: { borderColor?: string };
}

const normalizeStroke = (stroke: unknown): string =>
  String(stroke ?? '').trim().toLowerCase().replace(/\s+/g, '');

const SELECTED_STROKE_VALUES = new Set([
  normalizeStroke(TOPOLOGY_SELECTED_STROKE),
  normalizeStroke(COLORS.PRIMARY),
]);

export const isTopologyNodeSelectionChrome = (
  node: Pick<Node, 'getAttrByPath'>,
): boolean =>
  SELECTED_STROKE_VALUES.has(normalizeStroke(node.getAttrByPath('body/stroke')));

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

/**
 * Unselected hover probe. Selected nodes must not receive a second outline.
 */
const applyUnselectedHoverStroke = (
  node: Pick<Node, 'setAttrByPath'>,
): void => {
  highlightTopologyNode(node);
};

/**
 * Hover is a pass-over probe. Selected chrome is persistent `--color-primary`:
 * hovering a selected node does not swap, restyle, or stack another outline.
 */
export const applyTopologyNodeHoverChrome = (
  node: Pick<Node, 'setAttrByPath'>,
  isSelected: boolean,
): void => {
  if (isSelected) {
    return;
  }
  applyUnselectedHoverStroke(node);
};

/**
 * Leaving a node must not clear selected chrome. Only unselected nodes reset.
 */
export const clearTopologyNodeHoverChrome = (
  node: Pick<Node, 'getData' | 'setAttrByPath'>,
  isSelected: boolean,
): void => {
  if (isSelected) {
    highlightTopologyNode(node);
    return;
  }
  resetTopologyNodeChrome(node);
};
