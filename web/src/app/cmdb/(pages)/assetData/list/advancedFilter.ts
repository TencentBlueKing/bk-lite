import type { AttrFieldType } from '@/app/cmdb/types/assetManage';
import { isCloudRegionAttr } from '@/app/cmdb/utils/cloudRegion';
import { getTagOptions } from '@/app/cmdb/utils/fieldUtils';
import { displayCollectedTag } from '@/utils/collectedTag';

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

export interface ValueLabel {
  key: string;
  label: string;
}

export interface FilterUserRef {
  id: string | number;
  username?: string;
  display_name?: string;
}

export interface FilterGroupNode {
  id: string | number;
  name?: string;
  subGroups?: FilterGroupNode[];
  children?: FilterGroupNode[];
}

export interface FilterCloudOption {
  proxy_id: string | number;
  proxy_name?: string;
}

export interface FilterLabelContext {
  users?: FilterUserRef[];
  groups?: FilterGroupNode[];
  clouds?: FilterCloudOption[];
  boolYes?: string;
  boolNo?: string;
}

export interface MappedValueOptions {
  decodeTags?: boolean;
  separator?: string;
}

export interface LabelField {
  attr_id?: string;
  attr_type?: string;
  option?: unknown;
}

export function userFilterLabel(user: FilterUserRef): string {
  const account = user.username || '';
  const name = user.display_name || account;
  if (!account) return name || String(user.id ?? '');
  return `${name}(${account})`;
}

export function optionItems(option: unknown): Array<{ label: string; value: string }> {
  if (!Array.isArray(option)) return [];
  return option.flatMap((item) => {
    if (typeof item === 'string' || typeof item === 'number') {
      const value = String(item);
      return value ? [{ label: value, value }] : [];
    }
    if (!item || typeof item !== 'object') return [];
    const record = item as { id?: string | number; name?: string; value?: string | number; label?: string };
    const value = String(record.id ?? record.value ?? '');
    if (!value) return [];
    return [{ label: String(record.name ?? record.label ?? value), value }];
  });
}

function organizationLabels(nodes: FilterGroupNode[] | undefined): ValueLabel[] {
  const labels: ValueLabel[] = [];
  const walk = (list: FilterGroupNode[] | undefined, prefix: string[]) => {
    for (const node of list || []) {
      if (!node || typeof node !== 'object') continue;
      const name = typeof node.name === 'string' ? node.name : '';
      const path = name ? [...prefix, name] : prefix;
      const key = node.id == null || node.id === '' ? '' : String(node.id);
      if (key && path.length) labels.push({ key, label: path.join(' / ') });
      walk(node.subGroups?.length ? node.subGroups : node.children, path);
    }
  };
  walk(nodes, []);
  return labels;
}

export function labelsForField(field: LabelField | undefined, context: FilterLabelContext = {}): ValueLabel[] {
  if (!field) return [];
  if (isCloudRegionAttr(field.attr_id)) {
    return (context.clouds || []).flatMap((item) => {
      const key = item?.proxy_id == null || item.proxy_id === '' ? '' : String(item.proxy_id);
      if (!key) return [];
      return [{ key, label: item.proxy_name || key }];
    });
  }
  switch (field.attr_type) {
    case 'enum':
      return optionItems(field.option).map((item) => ({ key: item.value, label: item.label }));
    case 'tag':
      return getTagOptions({ option: field.option } as AttrFieldType).flatMap((group) =>
        group.options.map((item) => ({ key: String(item.value), label: item.label })),
      );
    case 'user':
      return (context.users || []).map((user) => ({ key: String(user.id), label: userFilterLabel(user) }));
    case 'organization':
      return organizationLabels(context.groups);
    case 'bool':
      return [
        { key: 'true', label: context.boolYes || 'Yes' },
        { key: 'false', label: context.boolNo || 'No' },
      ];
    default:
      return [];
  }
}

function renderMappedToken(
  token: string | number | boolean,
  labels: Map<string, string>,
  decodeTags: boolean,
) {
  const key = String(token);
  return labels.get(key) || (decodeTags ? displayCollectedTag(key) : key);
}

export function displayMappedValue(
  value: AdvancedCondition['value'],
  labels: ValueLabel[] = [],
  options: MappedValueOptions = {},
): string {
  const lookup = new Map(labels.map((item) => [item.key, item.label]));
  const separator = options.separator ?? ', ';
  const render = (token: string | number | boolean) => renderMappedToken(token, lookup, Boolean(options.decodeTags));
  if (Array.isArray(value)) return value.map(render).filter((item) => item !== '').join(separator);
  if (value == null || value === '') return '';
  return render(value);
}

export function displayConditionValue(
  condition: Pick<AdvancedCondition, 'type' | 'value' | 'start' | 'end'>,
  labels: ValueLabel[] = [],
  options: MappedValueOptions = {},
): string {
  if (!operatorNeedsValue(condition.type)) return '';
  if (condition.type === 'time') return conditionValueText(condition);
  return displayMappedValue(condition.value, labels, options);
}

export function displayFieldCondition(
  condition: Pick<AdvancedCondition, 'type' | 'value' | 'start' | 'end'>,
  field: LabelField | undefined,
  context: FilterLabelContext = {},
  options: MappedValueOptions = {},
): string {
  return displayConditionValue(condition, labelsForField(field, context), {
    ...options,
    decodeTags: options.decodeTags ?? field?.attr_type === 'tag',
  });
}

export function exportFilterPayload(
  exportType: string,
  queryList: unknown[] | null | undefined,
  advanced: AdvancedFilter | null | undefined,
  relationFilters?: { model_asst_id: string; inst_uuids: string[] }[] | null,
) {
  if (exportType !== 'all') return {};
  const payload: {
    query_list?: unknown[];
    advanced_filter?: AdvancedFilter;
    relation_filters?: { model_asst_id: string; inst_uuids: string[] }[];
  } = {};
  if (queryList?.length) payload.query_list = queryList;
  if (advanced?.conditions?.length) payload.advanced_filter = advanced;
  if (relationFilters?.length) payload.relation_filters = relationFilters;
  return payload;
}
