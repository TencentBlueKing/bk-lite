export const TRIGGER_EVENTS = [
  'ticket_create', 'ticket_update', 'ticket_suspend', 'ticket_recovery',
  'ticket_back', 'ticket_withdraw', 'ticket_end', 'ticket_finish',
  'ticket_close', 'ticket_terminate', 'ticket_urging', 'activity_into',
] as const;

export const TRIGGER_ACTIONS = [
  { value: 'tag', labelKey: 'tag' },
  { value: 'notice', labelKey: 'notice' },
  { value: 'status', labelKey: 'changeStatus' },
] as const;

export const TRIGGER_SCOPES = [
  { key: 'workflow_ids', options: 'workflows', labelKey: 'triggerScopeWorkflow' },
  { key: 'form_ids', options: 'forms', labelKey: 'triggerScopeForm' },
  { key: 'service_ids', options: 'services', labelKey: 'triggerScopeService' },
] as const;

export const TRIGGER_OPERATORS = [
  { value: '=', labelKey: 'eq' },
  { value: '!=', labelKey: 'triggerNotEqual' },
  { value: '>', labelKey: 'triggerGreater' },
  { value: '>=', labelKey: 'triggerGreaterOrEqual' },
  { value: '<', labelKey: 'triggerLess' },
  { value: '<=', labelKey: 'triggerLessOrEqual' },
  { value: 'contains', labelKey: 'contains' },
  { value: 'in', labelKey: 'triggerIn' },
  { value: 'not_in', labelKey: 'triggerNotIn' },
  { value: 'is_empty', labelKey: 'triggerEmpty' },
  { value: 'not_empty', labelKey: 'triggerNotEmpty' },
] as const;

type ScopeKey = typeof TRIGGER_SCOPES[number]['key'];
export type ScopeMode = 'all' | 'include' | 'exclude';
type Scope = { mode: ScopeMode } & Partial<Record<ScopeKey, number[]>>;
type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
type Logic = 'and' | 'or';
interface Condition { field: string; op: string; value?: JsonValue }
interface ConditionGroup { logic: Logic; items: (Condition | ConditionGroup)[] }
export const TRIGGER_NOTICE_ROLES = ['creator', 'current_assignees'] as const;
type NoticeRole = typeof TRIGGER_NOTICE_ROLES[number];
export type NoticeChannel =
  | { type: 'site'; template_id?: number }
  | { type: 'im'; channel_id: number; template_id?: number };

export interface TriggerNotice {
  content_mode?: 'template' | 'custom';
  recipients: {
    roles: NoticeRole[];
    users: string[];
    group_ids: number[];
    field_keys: string[];
  };
  channels: NoticeChannel[];
}

interface TriggerAction { type: string; value: string; notice?: TriggerNotice }

interface TriggerConfig {
  scope?: Scope;
  when?: Condition | ConditionGroup | null;
  actions?: TriggerAction[];
  response?: string;
  name?: string;
}

export interface TriggerItem {
  id: number;
  name: string;
  event: string;
  action: string;
  config?: TriggerConfig | null;
  is_enabled: boolean;
}

export interface TriggerFieldOption {
  label: string;
  value: string | number | boolean;
}

export interface TriggerField {
  key: string;
  label: string;
  type: 'text' | 'number' | 'boolean' | 'list';
  options?: TriggerFieldOption[];
}

interface FormFieldGroup<Field> {
  name: string;
  workflow_id?: number;
  form_id?: number;
  service_ids?: number[];
  fields: Field[];
}

export interface TriggerNoticeOptions {
  groups: { id: number; name: string }[];
  channels: { id: number; name: string }[];
  templates: { id: number; event: string; channel_type: 'site' | 'im'; title_tpl: string }[];
  form_field_groups: FormFieldGroup<{ key: string; label: string }>[];
}

export type TriggerOptions = Record<typeof TRIGGER_SCOPES[number]['options'], { id: number; name: string }[]> & {
  statuses: { key: string; name: string }[];
  system_fields?: TriggerField[];
  form_field_groups?: FormFieldGroup<TriggerField>[];
  notice?: TriggerNoticeOptions;
  has_more?: boolean;
};

export type ValueMode = 'text' | 'number' | 'boolean' | 'json';

export interface ConditionRow {
  kind: 'condition';
  id: string;
  field: string;
  op: string;
  valueType: ValueMode;
  input: string;
  manualField?: boolean;
}

export interface ConditionGroupDraft {
  kind: 'group';
  id: string;
  logic: Logic;
  items: (ConditionRow | ConditionGroupDraft)[];
}

export interface ActionRow extends TriggerAction {
  id: string;
}

export interface TriggerDraft {
  name: string;
  event: string;
  scope: Scope;
  when: ConditionGroupDraft;
  actions: ActionRow[];
}

let rowSequence = 0;
const nextRowId = () => String(++rowSequence);

export function newCondition(): ConditionRow {
  return { kind: 'condition', id: nextRowId(), field: '', op: '=', valueType: 'text', input: '' };
}

export function newConditionGroup(items: ConditionGroupDraft['items'] = [], logic: Logic = 'and'): ConditionGroupDraft {
  return { kind: 'group', id: nextRowId(), logic, items };
}

export function newTriggerAction(action: TriggerAction = { type: 'tag', value: '' }): ActionRow {
  return { ...action, id: nextRowId() };
}

export function newTriggerNotice(): TriggerNotice {
  return { content_mode: 'template', recipients: { roles: ['creator'], users: [], group_ids: [], field_keys: [] }, channels: [{ type: 'site' }] };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readTriggerScope(value: unknown): Scope {
  if (value === undefined || value === null) return { mode: 'all' };
  if (!isRecord(value) || (value.mode !== 'all' && value.mode !== 'include' && value.mode !== 'exclude')) return { mode: 'include' };
  if (Object.keys(value).some(key => key !== 'mode' && !TRIGGER_SCOPES.some(scope => scope.key === key))) return { mode: 'include' };
  const scope: Scope = { mode: value.mode };
  if (scope.mode === 'all') return scope;
  for (const { key } of TRIGGER_SCOPES) {
    const ids = value[key];
    if (ids === undefined) continue;
    if (!Array.isArray(ids) || !ids.every(id => Number.isInteger(id) && id > 0)) return { mode: 'include' };
    scope[key] = ids;
  }
  return scope;
}

export function scopedFormFieldGroups<Field>(groups: FormFieldGroup<Field>[], scope: Scope) {
  if (scope.mode !== 'include') return groups;
  const active = TRIGGER_SCOPES.filter(({ key }) => scope[key]?.length);
  return groups.filter(group => active.length > 0 && active.every(({ key }) => {
    const ids = scope[key] ?? [];
    if (key === 'workflow_ids') return group.workflow_id !== undefined && ids.includes(group.workflow_id);
    if (key === 'form_ids') return group.form_id !== undefined && ids.includes(group.form_id);
    return group.service_ids?.some(id => ids.includes(id));
  }));
}

function isId(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
}

function readTriggerNotice(notice: unknown): TriggerNotice {
  const source = isRecord(notice) ? notice : {};
  const recipients = isRecord(source.recipients) ? source.recipients : {};
  const strings = (items: unknown) => Array.isArray(items) ? items.filter((item): item is string => typeof item === 'string') : [];
  const channels: NoticeChannel[] = [];
  for (const item of Array.isArray(source.channels) ? source.channels : []) {
    if (!isRecord(item)) continue;
    const template = isId(item.template_id) ? { template_id: item.template_id } : {};
    if (item.type === 'site') channels.push({ type: 'site', ...template });
    if (item.type === 'im' && isId(item.channel_id)) channels.push({ type: 'im', channel_id: item.channel_id, ...template });
  }
  return {
    ...(source.content_mode === 'template' || source.content_mode === 'custom' ? { content_mode: source.content_mode } : {}),
    recipients: {
      roles: TRIGGER_NOTICE_ROLES.filter(role => strings(recipients.roles).includes(role)),
      users: strings(recipients.users),
      group_ids: Array.isArray(recipients.group_ids) ? recipients.group_ids.filter(isId) : [],
      field_keys: strings(recipients.field_keys),
    },
    channels,
  };
}

export function readTriggerActions(item: TriggerItem): TriggerAction[] {
  const blank = { type: 'tag', value: '' };
  const config: unknown = item.config;
  if (config != null && !isRecord(config)) return [blank];
  if (isRecord(config) && 'actions' in config) {
    if (!Array.isArray(config.actions) || !config.actions.length) return [blank];
    return config.actions.map((row: unknown) => {
      if (!isRecord(row) || typeof row.type !== 'string') return blank;
      if (row.type === 'notice' && 'notice' in row) {
        return { type: 'notice', value: typeof row.value === 'string' ? row.value : '', notice: readTriggerNotice(row.notice) };
      }
      if (typeof row.value !== 'string') return blank;
      return { type: row.type, value: row.value };
    });
  }
  const value = item.config?.response || item.config?.name || (item.action === 'notice' ? item.name : '');
  return [{ type: item.action, value: typeof value === 'string' ? value : '' }];
}

export function triggerValueModes(op: string): ValueMode[] {
  if (op === 'in' || op === 'not_in') return ['json'];
  if (op === 'is_empty' || op === 'not_empty') return [];
  if (['>', '>=', '<', '<='].includes(op)) return ['number', 'text'];
  return ['text', 'number', 'boolean', 'json'];
}

function readCondition(node: unknown): ConditionRow | ConditionGroupDraft {
  if (!isRecord(node)) return newCondition();
  if ('logic' in node) {
    if ((node.logic !== 'and' && node.logic !== 'or') || !Array.isArray(node.items) || !node.items.length) {
      return newConditionGroup([newCondition()]);
    }
    return newConditionGroup(node.items.map(readCondition), node.logic);
  }

  const op = node.op === 'eq' ? '=' : typeof node.op === 'string' ? node.op : '';
  const modes = triggerValueModes(op);
  let valueType: ValueMode = 'text';
  if (modes.length === 1) valueType = modes[0];
  else if (typeof node.value === 'number') valueType = 'number';
  else if (typeof node.value === 'boolean') valueType = 'boolean';
  else if (typeof node.value === 'object') valueType = 'json';

  const input = valueType === 'json' ? JSON.stringify(node.value) ?? '' : String(node.value ?? '');
  return { kind: 'condition', id: nextRowId(), field: typeof node.field === 'string' ? node.field : '', op, valueType, input };
}

export function readTriggerDraft(item?: TriggerItem): TriggerDraft {
  const config = item?.config;
  const condition: unknown = config?.when;
  const noCondition = condition == null || (isRecord(condition) && (
    Object.keys(condition).length === 0 || (condition.field === '' && (condition.op === 'eq' || condition.op === '=') && condition.value === '')
  ));
  const when = noCondition ? newConditionGroup() : readCondition(condition);

  return {
    name: item?.name ?? '',
    event: item?.event ?? 'ticket_create',
    scope: readTriggerScope(config?.scope),
    when: when.kind === 'group' ? when : newConditionGroup([when]),
    actions: item ? readTriggerActions(item).map(newTriggerAction) : [newTriggerAction()],
  };
}

function writeCondition(row: ConditionRow | ConditionGroupDraft): Condition | ConditionGroup {
  if (row.kind === 'group') {
    if (!row.items.length) throw new Error('itsm.rule.triggerConditionGroupRequired');
    return { logic: row.logic, items: row.items.map(writeCondition) };
  }

  const field = row.field.trim();
  if (!/^[^.\s]+(?:\.[^.\s]+)*$/.test(field)) throw new Error('itsm.rule.triggerFieldRequired');
  const { op, input, valueType } = row;
  if (!TRIGGER_OPERATORS.some(operator => operator.value === op)) throw new Error('itsm.rule.triggerOperatorRequired');
  if (!triggerValueModes(op).length) return { field, op };

  let value: JsonValue;
  if (valueType === 'number') {
    if (!input.trim() || !Number.isFinite(Number(input))) throw new Error('itsm.rule.triggerValueNumber');
    value = Number(input);
  } else if (valueType === 'boolean') {
    if (input !== 'true' && input !== 'false') throw new Error('itsm.rule.triggerConditionValueRequired');
    value = input === 'true';
  } else if (valueType === 'json') {
    try {
      value = JSON.parse(input) as JsonValue;
    } catch {
      throw new Error('itsm.rule.triggerValueJson');
    }
    if ((op === 'in' || op === 'not_in') && !Array.isArray(value)) {
      throw new Error('itsm.rule.triggerValueList');
    }
  } else {
    value = input;
  }
  return { field, op, value };
}

export function buildTriggerPayload(draft: TriggerDraft) {
  const name = draft.name.trim();
  if (!name) throw new Error('itsm.rule.triggerNameRequired');
  const scope = { mode: draft.scope.mode } as Scope;
  if (scope.mode !== 'all') {
    TRIGGER_SCOPES.forEach(({ key }) => {
      const ids = draft.scope[key];
      if (ids?.length) scope[key] = ids;
    });
    if (!TRIGGER_SCOPES.some(({ key }) => scope[key]?.length)) throw new Error('itsm.rule.triggerScopeRequired');
  }

  const when = draft.when.items.length ? writeCondition(draft.when) : undefined;
  if (!draft.actions.length) throw new Error('itsm.rule.triggerActionRequired');
  const actions = draft.actions.map(action => {
    if (!TRIGGER_ACTIONS.some(option => option.value === action.type)) throw new Error('itsm.rule.triggerActionRequired');
    const value = action.value.trim();
    if (action.type === 'notice' && action.notice) {
      const { recipients, channels, content_mode } = action.notice;
      if (!Object.values(recipients).some(items => items.length)) throw new Error('itsm.rule.triggerNotifyRecipientsRequired');
      if (!channels.length) throw new Error('itsm.rule.triggerNotifyChannelsRequired');
      if (content_mode === 'custom') {
        if (!value) throw new Error('itsm.rule.triggerNotifyContentRequired');
        const destinations: NoticeChannel[] = channels.map(channel => channel.type === 'site' ? { type: 'site' } : { type: 'im', channel_id: channel.channel_id });
        return { type: 'notice', value, notice: { ...action.notice, channels: destinations } };
      }
      return { type: 'notice', value: content_mode === 'template' ? '' : value, notice: action.notice };
    }
    if (!value) throw new Error('itsm.rule.triggerActionValueRequired');
    return { type: action.type, value };
  });

  return {
    name, event: draft.event, action: actions[0].type,
    config: { scope, ...(when ? { when } : {}), actions },
  };
}
