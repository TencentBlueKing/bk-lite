import type { FormFieldSchema } from '../types';

type Config = Record<string, unknown>;
export type BindingSource = 'item' | 'form' | 'system' | 'output' | 'literal';
export interface Binding { source: BindingSource; key: string }
export interface Option { value: string; label: string }

export function jobMode(config: Config) {
  return config.mode === 'each' || (!config.mode && config.table_key) ? 'each' : 'once';
}

export function jobBadge(config: Config) {
  if (jobMode(config) === 'once') return '作业 · 单次';
  return config.dispatch_mode === 'parallel' || (!config.dispatch_mode && !config.batch_size)
    ? '作业 · 逐项并发' : `作业 · 每批 ${config.batch_size || 1} 项`;
}

export function jobBindings(config: Config): Record<string, Binding> {
  return Object.fromEntries(Object.entries(config.params || {}).map(([name, value]) => [
    name, typeof value === 'string' ? { source: 'item', key: value } : value,
  ]));
}

export function jobFormFields(fields: FormFieldSchema[]): FormFieldSchema[] {
  return fields.flatMap(field => {
    if (['tab', 'section'].includes(field.type)) return jobFormFields(field.children || []);
    return ['description', 'divider'].includes(field.type) ? [] : [field];
  });
}

export function upstreamJobOutputs(
  current: string,
  nodes: { id: string; data: { label: string; auto?: Config } }[],
  edges: { source: string; target: string }[],
): Option[] {
  const parents = new Map<string, string[]>();
  for (const edge of edges) {
    const links = parents.get(edge.target) || [];
    links.push(edge.source);
    parents.set(edge.target, links);
  }
  const reachable = new Set([current]);
  const pending = [...(parents.get(current) || [])];
  while (pending.length) {
    const id = pending.pop()!;
    if (reachable.has(id)) continue;
    reachable.add(id);
    pending.push(...(parents.get(id) || []));
  }
  const options = new Map<string, Option>();
  for (const { id, data } of nodes) {
    if (id === current || !reachable.has(id) || data.auto?.kind !== 'integration') continue;
    const key = data.auto.result_field;
    if (typeof key === 'string' && key) options.set(key, { value: key, label: `${data.label} · ${key}` });
  }
  return Array.from(options.values());
}
