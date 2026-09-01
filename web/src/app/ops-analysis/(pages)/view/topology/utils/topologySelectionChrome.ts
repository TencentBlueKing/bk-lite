import type { Node } from '@antv/x6';
import { COLORS, SPACING } from '../constants/nodeDefaults';

/** 选中描边锁定为语义主色，hover 不得换成别的蓝。 */
export const TOPOLOGY_SELECTED_STROKE = 'var(--color-primary)';
export const TOPOLOGY_SELECTED_STROKE_WIDTH = SPACING.STROKE_WIDTH.DEFAULT;
/** 浏览态 hover：1px 边框色，不得套用选中主色。 */
export const TOPOLOGY_VIEW_HOVER_STROKE = 'var(--color-border-2)';
export const TOPOLOGY_VIEW_HOVER_STROKE_WIDTH = SPACING.STROKE_WIDTH.THIN;
export const TOPOLOGY_CHART_NODE_CLASS = 'ops-topology-chart-node';
export const TOPOLOGY_CHART_NODE_SELECTED_CLASS =
  'ops-topology-chart-node--selected';
export const TOPOLOGY_CHART_NODE_HOVER_CLASS = 'ops-topology-chart-node--hover';

export type TopologyNodeChromeKind = 'rest' | 'view-hover' | 'selected';

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

const VIEW_HOVER_STROKE_VALUES = new Set([
  normalizeStroke(TOPOLOGY_VIEW_HOVER_STROKE),
]);

export const isTopologyNodeSelectionChrome = (
  node: Pick<Node, 'getAttrByPath'>,
): boolean =>
  SELECTED_STROKE_VALUES.has(normalizeStroke(node.getAttrByPath('body/stroke')));

export const isTopologyNodeViewHoverChrome = (
  node: Pick<Node, 'getAttrByPath'>,
): boolean =>
  VIEW_HOVER_STROKE_VALUES.has(
    normalizeStroke(node.getAttrByPath('body/stroke')),
  );

export const getTopologyNodeChromeKind = (
  node: Pick<Node, 'getAttrByPath'>,
): TopologyNodeChromeKind => {
  if (isTopologyNodeSelectionChrome(node)) {
    return 'selected';
  }
  if (isTopologyNodeViewHoverChrome(node)) {
    return 'view-hover';
  }
  return 'rest';
};

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

const applyViewHoverStroke = (node: Pick<Node, 'setAttrByPath'>): void => {
  node.setAttrByPath('body/stroke', TOPOLOGY_VIEW_HOVER_STROKE);
  node.setAttrByPath('body/strokeWidth', TOPOLOGY_VIEW_HOVER_STROKE_WIDTH);
};

/**
 * Hover is a pass-over probe.
 * Edit: unselected hover uses selected chrome; selected `--color-primary` stays.
 * View: unselected hover is 1px `--color-border-2`; selected chrome is unchanged.
 */
export const applyTopologyNodeHoverChrome = (
  node: Pick<Node, 'setAttrByPath'>,
  isSelected: boolean,
  isEditMode = true,
): void => {
  if (isSelected) {
    return;
  }
  if (!isEditMode) {
    applyViewHoverStroke(node);
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
