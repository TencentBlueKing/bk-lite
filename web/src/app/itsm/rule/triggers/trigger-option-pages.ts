import type { TriggerDraft, TriggerItem, TriggerOptions } from './trigger-config';

interface Selection {
  workflows?: number[];
  forms?: number[];
  services?: number[];
  statuses?: string[];
  groups?: number[];
  channels?: number[];
  templates?: number[];
}

export interface TriggerOptionsQuery {
  page: number;
  selected?: Selection;
}

const maxSelected = 50;

function putSelected<T extends number | string>(values: T[]): T[] {
  return [...new Set(values)].slice(0, maxSelected);
}

export function savedTriggerChoices(draft: TriggerDraft, item?: TriggerItem): Selection {
  const keys: Required<Selection> = {
    workflows: [...(draft.scope.workflow_ids ?? [])],
    forms: [...(draft.scope.form_ids ?? [])],
    services: [...(draft.scope.service_ids ?? [])],
    statuses: [],
    groups: [],
    channels: [],
    templates: [],
  };
  for (const action of draft.actions) {
    if (action.type === 'status') keys.statuses.push(action.value);
    if (!action.notice) continue;
    keys.groups.push(...action.notice.recipients.group_ids);
    for (const channel of action.notice.channels) {
      if (channel.type === 'im') keys.channels.push(channel.channel_id);
      if (channel.template_id) keys.templates.push(channel.template_id);
    }
  }

  const validId = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
  function collect(condition: unknown) {
    if (!condition || typeof condition !== 'object') return;
    const { items, field, value } = condition as Record<string, unknown>;
    if (Array.isArray(items)) {
      items.forEach(collect);
      return;
    }
    const values = Array.isArray(value) ? value : [value];
    if (field === '$ticket.status' || field === 'status') {
      keys.statuses.push(...values.filter((entry): entry is string => typeof entry === 'string'));
    } else if (field === '$ticket.workflow_id' || field === '$ticket.service_id') {
      const ids = field === '$ticket.workflow_id' ? keys.workflows : keys.services;
      ids.push(...values.filter(validId));
    }
  }
  if (item?.config?.when) collect(item.config.when);
  keys.statuses = keys.statuses.filter(value => value.length > 0 && value.length <= 32);
  return Object.fromEntries(Object.entries(keys).map(([key, values]) => [
    key, putSelected<string | number>(key === 'statuses' ? values : values.filter(validId)),
  ]).filter(([, values]) => values.length));
}

function mergeRows<Row>(previous: Row[], current: Row[], key: keyof Row): Row[] {
  return [...new Map([...previous, ...current].map(row => [row[key], row])).values()];
}

function mergeFieldGroups<Group extends { workflow_id?: number; form_id?: number; service_ids?: number[] }>(previous: Group[], current: Group[]): Group[] {
  const groups = new Map<string, Group>();
  for (const group of [...previous, ...current]) {
    const key = group.workflow_id !== undefined ? `workflow:${group.workflow_id}` : `form:${group.form_id}`;
    const cached = groups.get(key);
    groups.set(key, cached
      ? { ...group, service_ids: [...new Set([...(cached.service_ids ?? []), ...(group.service_ids ?? [])])] }
      : group);
  }
  return [...groups.values()];
}

export function mergeTriggerPages(previous: TriggerOptions, current: TriggerOptions): TriggerOptions {
  const priorSystem = new Map(previous.system_fields?.map(field => [field.key, field]));
  const notice = previous.notice && current.notice ? {
    groups: mergeRows(previous.notice.groups, current.notice.groups, 'id'),
    channels: mergeRows(previous.notice.channels, current.notice.channels, 'id'),
    templates: mergeRows(previous.notice.templates, current.notice.templates, 'id'),
    form_field_groups: mergeFieldGroups(previous.notice.form_field_groups, current.notice.form_field_groups),
  } : current.notice ?? previous.notice;
  return {
    ...current,
    workflows: mergeRows(previous.workflows, current.workflows, 'id'),
    forms: mergeRows(previous.forms, current.forms, 'id'),
    services: mergeRows(previous.services, current.services, 'id'),
    statuses: mergeRows(previous.statuses, current.statuses, 'key'),
    system_fields: current.system_fields?.map(field => ({
      ...field,
      ...(field.options && { options: mergeRows(priorSystem.get(field.key)?.options ?? [], field.options, 'value') }),
    })) ?? previous.system_fields,
    form_field_groups: mergeFieldGroups(previous.form_field_groups ?? [], current.form_field_groups ?? []),
    notice,
  };
}
