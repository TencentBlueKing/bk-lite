'use client';
import { cloneElement, useEffect, useRef, useState, type ReactElement } from 'react';
import { Button, Form, Spin } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useItsmApi } from '../api/useItsmApi';
import type { FormChoice, FieldFetchBinding, FormFieldSchema, FormSchema } from '../types';

export function fetchDependencies(cfg?: FieldFetchBinding): string[] {
  if (!cfg) return [];
  if (!cfg.inputs && !cfg.transform_params) return cfg.dependencies || [];
  const keys = new Set<string>();
  function visit(value: unknown) {
    if (typeof value === 'string') {
      const key = /^\$\{form\.([\p{L}\p{N}_]+)\}$/u.exec(value)?.[1];
      if (key) keys.add(key);
    } else if (value && typeof value === 'object') {
      Object.values(value).forEach(visit);
    }
  }
  visit(cfg.inputs);
  visit(cfg.transform_params);
  return [...keys].sort();
}

export interface FetchContext { service_id?: number; ticket_id?: number; task_id?: number; preview?: boolean; schema?: FormSchema }
interface Result { options: FormChoice[]; fills: Record<string, Record<string, unknown>>; value: unknown; receipt: string; has_more?: boolean }
export type SharedFieldFetches = Map<string, { promise: Promise<unknown>; expiresAt: number; checks: Array<() => boolean> }>;
const MAX_CONCURRENT_FETCHES = 6;
let activeFetches = 0;
const pendingFetches: Array<() => void> = [];
let nextFetch = 0;

function drainFetches() {
  while (activeFetches < MAX_CONCURRENT_FETCHES && nextFetch < pendingFetches.length) pendingFetches[nextFetch++]();
  if (nextFetch === pendingFetches.length) {
    pendingFetches.length = 0;
    nextFetch = 0;
  }
}

function fetchWithLimit<T>(request: () => Promise<T>, isCurrent: () => boolean): Promise<T | undefined> {
  return new Promise((resolve, reject) => {
    pendingFetches.push(() => {
      if (!isCurrent()) { resolve(undefined); return; }
      activeFetches += 1;
      Promise.resolve().then(request).then(resolve, reject).finally(() => { activeFetches -= 1; drainFetches(); });
    });
    drainFetches();
  });
}

function fetchShared<T>(cache: SharedFieldFetches, key: string, request: () => Promise<T>, isCurrent: () => boolean): Promise<T | undefined> {
  const now = Date.now();
  for (const [savedKey, saved] of cache) if (saved.expiresAt <= now) cache.delete(savedKey);
  const existing = cache.get(key);
  if (existing) {
    existing.checks.push(isCurrent);
    return existing.promise as Promise<T | undefined>;
  }
  const checks = [isCurrent];
  const promise = fetchWithLimit(request, () => checks.some(check => check()));
  const entry = { promise, expiresAt: now + 30_000, checks };
  cache.set(key, entry);
  void promise.then(
    result => { if (result === undefined && cache.get(key) === entry) cache.delete(key); },
    () => { if (cache.get(key) === entry) cache.delete(key); },
  );
  return promise;
}

interface FetchProps {
  field: FormFieldSchema; context: FetchContext; children: ReactElement; id?: string; value?: unknown; onChange?: (...args: unknown[]) => void;
}
export interface FieldStore {
  rememberOptions?: (options: FormChoice[]) => void;
  getFieldValue: (key: string) => unknown;
  setFieldValue: (key: string, value: unknown) => void;
  isFieldTouched: (key: string) => boolean;
  requestValues: () => Record<string, unknown>;
}

function rememberSelection(store: FieldStore, field: FormFieldSchema, value: unknown, options: FormChoice[]) {
  if (!store.rememberOptions) return;
  const saved = (store.getFieldValue('_field_labels') as Record<string, FormChoice[]> | undefined)?.[field.key] || [];
  const labels = new Map(saved.map(option => [option.value, option.label]));
  function visit(nodes: FormChoice[], path: string[]) {
    for (const item of nodes) {
      const names = [...path, item.label];
      labels.set(item.value, field.showCascadePath === false ? item.label : names.join(' / '));
      if (item.children) visit(item.children, names);
    }
  }
  visit(options, []);
  const selected = Array.isArray(value) ? value : [value];
  store.rememberOptions(selected.filter(key => labels.has(key)).map(key => ({value: key, label: labels.get(key)!})));
}

export function FieldFetchControl(props: FetchProps) {
  const form = Form.useFormInstance();
  const refs = fetchDependencies(props.field.fetch);
  const depKey = Form.useWatch(values => JSON.stringify(refs.map(key => values[key] ?? null)), form);
  return <ScopedFetchControl {...props} path={props.field.key} depKey={depKey} store={{
    getFieldValue: key => form.getFieldValue(key), setFieldValue: (key, value) => form.setFieldValue(key, value),
    isFieldTouched: key => form.isFieldTouched(key), requestValues: () => form.getFieldsValue(true),
  }} />;
}

export function ScopedFetchControl({ field, context, children, value, onChange, id, store, path, depKey, sharedFetches }: FetchProps & {
  store: FieldStore; path: string; depKey?: string; sharedFetches?: SharedFieldFetches;
}) {
  const api = useItsmApi();
  const currentStore = useRef(store);
  currentStore.current = store;
  const cfg = field.fetch!;
  const refs = fetchDependencies(cfg);
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const manualRequest = useRef<{ depKey: string; contextKey: string; binding: string; query: string; page: number; values: Record<string, unknown> }>(undefined);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [awaitingRefresh, setAwaitingRefresh] = useState(false);
  const sequence = useRef(0);
  const changed = useRef(false);
  const defaultFirst = field.type === 'select' && field.props?.defaultFirstOption === true;
  const binding = JSON.stringify(cfg);
  const contextKey = JSON.stringify(context);
  const previousDeps = useRef<string | undefined>(undefined);
  const resultRef = useRef<Result | null>(null);
  const first = useRef(true);
  useEffect(() => {
    const seq = ++sequence.current;
    if (!api.ready || depKey === undefined) return;
    const form = currentStore.current;
    const dependenciesChanged = previousDeps.current !== undefined && previousDeps.current !== depKey;
    previousDeps.current = depKey;
    if (dependenciesChanged) {
      setPage(1); setResult(null); resultRef.current = null;
      setError('');
      if (cfg.trigger === 'manual') setAwaitingRefresh(true);
      const receipts = { ...(form.getFieldValue('_field_receipts') as Record<string, string[]> | undefined) };
      delete receipts[field.key];
      form.setFieldValue('_field_receipts', receipts);
      if (cfg.mode === 'options' || cfg.enforce) form.setFieldValue(field.key, undefined);
    }
    if (refs.some(key => form.getFieldValue(key) == null || form.getFieldValue(key) === '')) {
      manualRequest.current = undefined;
      setLoading(false);
      return;
    }
    const request = manualRequest.current;
    if (cfg.trigger === 'manual' && (!request || request.depKey !== depKey || request.contextKey !== contextKey || request.binding !== binding || request.query !== query || request.page !== page)) {
      manualRequest.current = undefined;
      setLoading(false);
      return;
    }
    setLoading(true); setError('');
    const timer = setTimeout(() => {
      if (cfg.trigger === 'manual') {
        manualRequest.current = undefined;
        setAwaitingRefresh(false);
      }
      const values = cfg.trigger === 'manual' ? request!.values : form.requestValues();
      const fetchRequest = () => api.fetchField({ ...JSON.parse(contextKey), field: path, values, query, page: dependenciesChanged ? 1 : page });
      const isCurrent = () => sequence.current === seq;
      const share = sharedFetches && !context.ticket_id && !refs.length && !field.visibleWhen && cfg.mode === 'options' && cfg.trigger !== 'manual';
      const cacheKey = JSON.stringify([contextKey, path, binding, query, page]);
      if (refresh) sharedFetches?.delete(cacheKey);
      void (share ? fetchShared(sharedFetches, cacheKey, fetchRequest, isCurrent) : fetchWithLimit(fetchRequest, isCurrent)).then(raw => {
        if (raw === undefined) return;
        if (sequence.current !== seq || JSON.stringify(refs.map(key => form.getFieldValue(key) ?? null)) !== depKey) return;
        const next = raw as Result;
        const prior = page > 1 && !dependenciesChanged ? resultRef.current : null;
        const options = [...new Map([...(prior?.options || []), ...next.options].map(option => [option.value, option])).values()];
        const merged = { ...next, options, fills: { ...prior?.fills, ...next.fills } };
        resultRef.current = merged; setResult(merged);
        const receipts = (form.getFieldValue('_field_receipts') || {}) as Record<string, string[]>;
        if (next.receipt) form.setFieldValue('_field_receipts', { ...receipts, [field.key]: [...(dependenciesChanged ? [] : receipts[field.key] || []), next.receipt].slice(-20) });
        const current = form.getFieldValue(field.key);
        const option = next.options[0];
        if (defaultFirst && cfg.mode === 'options' && !query && (page === 1 || dependenciesChanged) && (current == null || current === '') && option) {
          form.setFieldValue(field.key, option.value);
          for (const [key, v] of Object.entries(next.fills?.[String(option.value)] || {})) {
            if (!form.isFieldTouched(key)) form.setFieldValue(key, v);
          }
        }
        if (cfg.mode === 'options') rememberSelection(form, field, form.getFieldValue(field.key), options);
        if (cfg.mode !== 'options' && (cfg.enforce || (!changed.current && (!first.current || form.getFieldValue(field.key) == null || form.getFieldValue(field.key) === '')))) form.setFieldValue(field.key, next.value);
        first.current = false;
      }).catch((cause: unknown) => { if (sequence.current === seq) setError(cause instanceof Error ? cause.message : '取数失败，请重试'); })
        .finally(() => { if (sequence.current === seq) setLoading(false); });
    }, 300);
    return () => { clearTimeout(timer); sequence.current++; };
    // 配置和上下文以稳定序列化值参与依赖，避免表单重绘触发重复请求。
  }, [api.ready, api.fetchField, binding, contextKey, depKey, query, page, refresh, path, field.key, defaultFirst, sharedFetches]);
  const refreshCurrent = (nextPage: number) => {
    manualRequest.current = { depKey, contextKey, binding, query, page: nextPage, values: currentStore.current.requestValues() };
    setPage(nextPage);
    setRefresh(n => n + 1);
  };
  const update = (...args: unknown[]) => {
    changed.current = true; onChange?.(...args);
    const input = args[0];
    const selected = input && typeof input === 'object' && 'target' in input ? (input.target as { value?: unknown }).value : input;
    const form = currentStore.current;
    if (cfg.mode === 'options') rememberSelection(form, field, selected, result?.options || []);
    const fills = result?.fills?.[String(selected)];
    if (fills) for (const [key, next] of Object.entries(fills)) if (!form.isFieldTouched(key)) form.setFieldValue(key, next);
  };
  const missing = refs.some(key => store.getFieldValue(key) == null || store.getFieldValue(key) === '');
  const props: Record<string, unknown> = { id, value, onChange: update };
  if (missing && cfg.mode === 'options') props.disabled = true;
  if (cfg.enforce && cfg.mode !== 'options') props.disabled = true;
  const tree = ['cascade', 'multiCascade'].includes(field.type);
  if (cfg.mode === 'options') props[tree ? 'treeData' : 'options'] = result?.options || [];
  if (['select', 'multiselect'].includes(field.type)) Object.assign(props, {
    showSearch: true, filterOption: false, loading, onSearch: (text: string) => { setQuery(text); setPage(1); },
  });
  return <div className="flex flex-col gap-1">
    {cloneElement(children as ReactElement<Record<string, unknown>>, props)}
    <div className="flex items-center gap-2 text-xs text-[var(--color-text-3)]">
      {loading && <Spin size="small" />}
      <Button size="small" type="text" icon={<ReloadOutlined />} aria-label="刷新取数" title="刷新取数" disabled={loading || missing} onClick={() => refreshCurrent(1)} />
      {result?.has_more && <Button size="small" type="link" disabled={loading} onClick={() => refreshCurrent(page + 1)}>加载更多</Button>}
      {awaitingRefresh && !loading && <span>依赖已变化，请刷新取数</span>}
      {error && <span role="alert" className="text-[var(--color-fail)]">{error}</span>}
    </div>
  </div>;
}
