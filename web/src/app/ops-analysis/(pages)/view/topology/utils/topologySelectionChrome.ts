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

/**
 * Unselected hover probe. Shares the selected stroke so hover is visible,
 * but must only be applied when the node is not selected.
 */
const applyUnselectedHoverStroke = (
  node: Pick<Node, 'setAttrByPath'>,
): void => {
  highlightTopologyNode(node);
};

/**
 * Hover is a pass-over probe. Selected chrome is persistent and always wins:
 * hovering a selected node re-asserts the selected stroke instead of swapping
 * it for a hover-only style.
 */
export const applyTopologyNodeHoverChrome = (
  node: Pick<Node, 'setAttrByPath'>,
  isSelected: boolean,
): void => {
  if (isSelected) {
    highlightTopologyNode(node);
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
