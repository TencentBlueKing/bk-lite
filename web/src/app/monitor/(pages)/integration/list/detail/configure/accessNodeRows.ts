import { v4 as uuidv4 } from 'uuid';

const CONTAINER_NODE_TYPE = 'container';

export interface AccessNodeOption {
  id?: string | number;
  value?: string | number;
  name?: string;
  label?: string;
  ip?: string;
  node_type?: string;
  is_container?: boolean;
  disabled?: boolean;
}

type AccessRow = Record<string, unknown> & {
  key?: string;
  node_ids?: unknown;
  instance_name?: unknown;
};

export const nodeIdText = (value: unknown): string => {
  if (Array.isArray(value)) {
    const first = value.find((item) => nodeIdText(item));
    return first == null ? '' : nodeIdText(first);
  }
  if (value == null || value === '') return '';
  return String(value).trim();
};

export const rowHasNodeId = (row: AccessRow | undefined) => Boolean(nodeIdText(row?.node_ids));

export const isContainerNode = (node: AccessNodeOption) =>
  node.is_container === true || String(node.node_type || '').toLowerCase() === CONTAINER_NODE_TYPE;

const optionId = (node: AccessNodeOption) => nodeIdText(node.value) || nodeIdText(node.id);

export const applyNodeIdToEmptyRows = <T extends AccessRow>(rows: T[], nodeIds: unknown): T[] => {
  if (!nodeIdText(nodeIds) || !rows.length) return rows;
  let filled = false;
  const next = rows.map((row) => {
    if (rowHasNodeId(row)) return row;
    filled = true;
    return {
      ...row,
      node_ids: nodeIds,
      node_ids_error: null,
    };
  });
  return filled ? next : rows;
};

export const listUnusedAgentNodes = (
  nodes: AccessNodeOption[],
  rows: AccessRow[],
): AccessNodeOption[] => {
  const used = new Set(
    rows.map((row) => nodeIdText(row.node_ids)).filter(Boolean),
  );
  const seen = new Set<string>();
  const unused: AccessNodeOption[] = [];
  for (const node of nodes) {
    const id = optionId(node);
    if (!id || used.has(id) || seen.has(id)) continue;
    if (node.disabled || isContainerNode(node)) continue;
    seen.add(id);
    unused.push(node);
  }
  return unused;
};

export const buildAgentRowsFromNodes = <T extends AccessRow>(
  nodes: AccessNodeOption[],
  initItems: T,
  createKey: () => string = uuidv4,
): T[] =>
  nodes.map((node) => {
    const nodeId = optionId(node);
    const instanceName = String(node.name || '').trim() || String(node.label || '').trim();
    return {
      ...initItems,
      key: createKey(),
      node_ids: nodeId,
      instance_name: instanceName || initItems.instance_name,
      node_ids_error: null,
      instance_name_error: null,
    };
  });
