export type AdvancedLogic = 'AND' | 'OR';

export interface AdvancedCondition {
  path: string[];
  field: string;
  type: string;
  value?: string | number | boolean | (string | number)[];
  start?: string;
  end?: string;
}

export interface AdvancedFilter {
  logic: AdvancedLogic;
  conditions: AdvancedCondition[];
}

export interface AssocEdge {
  model_asst_id: string;
  src_model_id: string;
  dst_model_id: string;
  asst_id?: string;
}

export interface PathChoice {
  path: string[];
  label: string;
  depth: 0 | 1 | 2;
  endModelId: string;
}

const OPERATORS: Record<string, { value: string; label: string }[]> = {
  str: [
    { value: 'str=', label: '等于' },
    { value: 'str<>', label: '不等于' },
    { value: 'str*', label: '包含' },
    { value: 'str!*', label: '不包含' },
    { value: 'empty', label: '为空' },
    { value: 'not_empty', label: '不为空' },
  ],
  int: [
    { value: 'int=', label: '等于' },
    { value: 'int<>', label: '不等于' },
    { value: 'int>', label: '大于' },
    { value: 'int<', label: '小于' },
    { value: 'empty', label: '为空' },
    { value: 'not_empty', label: '不为空' },
  ],
  enum: [
    { value: 'list_any[]', label: '属于' },
    { value: 'list_none[]', label: '不属于' },
    { value: 'empty', label: '为空' },
    { value: 'not_empty', label: '不为空' },
  ],
  time: [
    { value: 'time<', label: '早于' },
    { value: 'time>', label: '晚于' },
    { value: 'time', label: '时间范围' },
    { value: 'empty', label: '为空' },
    { value: 'not_empty', label: '不为空' },
  ],
};

export function operatorsFor(attrType: string) {
  if (attrType === 'float') return OPERATORS.int;
  if (attrType === 'user' || attrType === 'organization') {
    return [
      { value: 'list[]', label: '属于' },
      { value: 'empty', label: '为空' },
      { value: 'not_empty', label: '不为空' },
    ];
  }
  if (attrType === 'bool') {
    return [
      { value: 'bool', label: '等于' },
      { value: 'empty', label: '为空' },
      { value: 'not_empty', label: '不为空' },
    ];
  }
  if (attrType === 'tag') return OPERATORS.enum;
  return OPERATORS[attrType] || OPERATORS.str;
}

export function operatorNeedsValue(type: string) {
  return type !== 'empty' && type !== 'not_empty';
}

export function otherModelId(edge: AssocEdge, currentModelId: string) {
  if (edge.src_model_id === currentModelId && edge.dst_model_id === currentModelId) return currentModelId;
  if (edge.src_model_id === currentModelId) return edge.dst_model_id;
  if (edge.dst_model_id === currentModelId) return edge.src_model_id;
  return null;
}

export function directedRelationLabel(
  edge: AssocEdge,
  relationName: (asstId?: string) => string,
  modelName: (modelId: string) => string,
) {
  return [modelName(edge.src_model_id), relationName(edge.asst_id), modelName(edge.dst_model_id)]
    .filter(Boolean)
    .join(' ');
}

export function buildPathChoices(
  modelId: string,
  edgesByModel: Record<string, AssocEdge[]>,
  relationName: (asstId?: string) => string,
  modelName: (modelId: string) => string,
): PathChoice[] {
  const choices: PathChoice[] = [{ path: [], label: '当前模型', depth: 0, endModelId: modelId }];
  for (const edge of edgesByModel[modelId] || []) {
    const next = otherModelId(edge, modelId);
    if (!next) continue;
    const firstLabel = directedRelationLabel(edge, relationName, modelName);
    choices.push({ path: [edge.model_asst_id], label: firstLabel, depth: 1, endModelId: next });
    for (const second of edgesByModel[next] || []) {
      if (second.model_asst_id === edge.model_asst_id) continue;
      const end = otherModelId(second, next);
      if (!end) continue;
      choices.push({
        path: [edge.model_asst_id, second.model_asst_id],
        label: `${firstLabel} > ${directedRelationLabel(second, relationName, modelName)}`,
        depth: 2,
        endModelId: end,
      });
    }
  }
  return choices;
}

export function summarizeCondition(pathLabel: string, fieldName: string, operatorLabel: string, value: string) {
  const head = pathLabel === '当前模型' ? fieldName : `${pathLabel}.${fieldName}`;
  return value ? `${head} ${operatorLabel} ${value}` : `${head} ${operatorLabel}`;
}

export function choiceForDepth(choices: PathChoice[], depth: 0 | 1 | 2) {
  return choices.find((item) => item.depth === depth) || choices[0];
}

export interface PathCascaderOption {
  label: string;
  value: string;
  children?: PathCascaderOption[];
}

const CURRENT_PATH_VALUE = 'current';

/** 一跳是可直接选中的节点，二跳收在它下面。选中「MySQL 运行于 主机」时终点是主机。 */
export function buildPathCascader(choices: PathChoice[]): PathCascaderOption[] {
  const options: PathCascaderOption[] = [];
  const nodes = new Map<string, PathCascaderOption>();
  for (const choice of choices) {
    if (choice.path.length === 0) {
      options.push({ label: choice.label, value: CURRENT_PATH_VALUE });
      continue;
    }
    if (choice.path.length === 1) {
      const node: PathCascaderOption = { label: choice.label, value: choice.path[0] };
      nodes.set(choice.path[0], node);
      options.push(node);
      continue;
    }
    const parent = nodes.get(choice.path[0]);
    if (!parent) continue;
    const childLabel = choice.label.includes(' > ')
      ? choice.label.split(' > ').slice(1).join(' > ')
      : choice.label;
    parent.children = [...(parent.children || []), { label: childLabel, value: choice.path[1] }];
  }
  return options;
}

export function pathToCascaderValue(path: string[]) {
  return path.length ? path : [CURRENT_PATH_VALUE];
}

export function cascaderValueToPath(value: Array<string | number | null> | undefined) {
  return (value || []).map(String).filter((item) => item && item !== CURRENT_PATH_VALUE);
}

export function conditionValueText(condition: Pick<AdvancedCondition, 'type' | 'value' | 'start' | 'end'>) {
  if (!operatorNeedsValue(condition.type)) return '';
  if (condition.type === 'time') return `${condition.start || ''}~${condition.end || ''}`;
  if (Array.isArray(condition.value)) return condition.value.join(',');
  return condition.value == null ? '' : String(condition.value);
}

export function exportFilterPayload(
  exportType: string,
  queryList: unknown[] | null | undefined,
  advanced: AdvancedFilter | null | undefined,
) {
  if (exportType !== 'all') return {};
  const payload: { query_list?: unknown[]; advanced_filter?: AdvancedFilter } = {};
  if (queryList?.length) payload.query_list = queryList;
  if (advanced?.conditions?.length) payload.advanced_filter = advanced;
  return payload;
}
