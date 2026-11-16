'use client';
import { cloneElement, useEffect, useRef, useState, type ReactElement } from 'react';
import { Button, Form, Spin } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useItsmApi } from '../api/useItsmApi';
import type { FormFieldSchema, FormSchema } from '../types';

export interface FetchContext { service_id?: number; ticket_id?: number; preview?: boolean; schema?: FormSchema }
interface Result { options: { value: string | number; label: string }[]; fills: Record<string, Record<string, unknown>>; value: unknown; receipt: string; has_more?: boolean }
export function FieldFetchControl({ field, context, children, value, onChange, id }: {
  field: FormFieldSchema; context: FetchContext; children: ReactElement; id?: string; value?: unknown; onChange?: (...args: unknown[]) => void;
}) {
  const api = useItsmApi();
  const form = Form.useFormInstance();
  const cfg = field.fetch!;
  const refs = cfg.dependencies || [];
  const depKey = Form.useWatch(values => JSON.stringify(refs.map(key => values[key] ?? null)), form);
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const sequence = useRef(0);
  const changed = useRef(false);
  const binding = JSON.stringify(cfg);
  const contextKey = JSON.stringify(context);
  const previousDeps = useRef<string | undefined>(undefined);
  const resultRef = useRef<Result | null>(null);
  const first = useRef(true);
  useEffect(() => {
    const seq = ++sequence.current;
    if (!api.ready || depKey === undefined) return;
    const dependenciesChanged = previousDeps.current !== undefined && previousDeps.current !== depKey;
    previousDeps.current = depKey;
    if (dependenciesChanged) { setPage(1); setResult(null); resultRef.current = null; }
    if (refs.some(key => [null, undefined, ''].includes(form.getFieldValue(key)))) { setLoading(false); return; }
    if (cfg.trigger === 'manual' && refresh === 0) return;
    setLoading(true); setError('');
    const timer = setTimeout(() => {
      void api.fetchField({ ...JSON.parse(contextKey), field: field.key, values: form.getFieldsValue(true), query, page: dependenciesChanged ? 1 : page }).then(raw => {
        if (sequence.current !== seq) return;
        const next = raw as Result;
        const prior = page > 1 && !dependenciesChanged ? resultRef.current : null;
        const options = [...new Map([...(prior?.options || []), ...next.options].map(option => [option.value, option])).values()];
        const merged = { ...next, options, fills: { ...prior?.fills, ...next.fills } };
        resultRef.current = merged; setResult(merged);
        const receipts = form.getFieldValue('_field_receipts') || {};
        form.setFieldValue('_field_receipts', { ...receipts, [field.key]: [...(dependenciesChanged ? [] : receipts[field.key] || []), next.receipt].slice(-20) });
        if (cfg.mode !== 'options' && (cfg.enforce || (!changed.current && (!first.current || form.getFieldValue(field.key) == null || form.getFieldValue(field.key) === '')))) form.setFieldValue(field.key, next.value);
        if (dependenciesChanged && cfg.mode === 'options') form.setFieldValue(field.key, undefined);
        first.current = false;
      }).catch((cause: unknown) => { if (sequence.current === seq) setError(cause instanceof Error ? cause.message : '取数失败，请重试'); })
        .finally(() => { if (sequence.current === seq) setLoading(false); });
    }, 300);
    return () => { clearTimeout(timer); sequence.current++; };
    // 配置和上下文以稳定序列化值参与依赖，避免表单重绘触发重复请求。
  }, [api.ready, api.fetchField, binding, contextKey, depKey, query, page, refresh, form, field.key]);
  const update = (...args: unknown[]) => {
    changed.current = true; onChange?.(...args);
    const input = args[0];
    const selected = input && typeof input === 'object' && 'target' in input ? (input.target as { value?: unknown }).value : input;
    const fills = result?.fills[String(selected)];
    if (fills) for (const [key, next] of Object.entries(fills)) if (!form.isFieldTouched(key)) form.setFieldValue(key, next);
  };
  const props: Record<string, unknown> = { id, value, onChange: update };
  if (cfg.enforce && cfg.mode !== 'options') props.disabled = true;
  const tree = ['cascade', 'multiCascade'].includes(field.type);
  if (cfg.mode === 'options' && result) props[tree ? 'treeData' : 'options'] = result.options;
  if (['select', 'multiselect'].includes(field.type)) Object.assign(props, {
    showSearch: true, filterOption: false, loading, onSearch: (text: string) => { setQuery(text); setPage(1); },
  });
  return <div className="flex flex-col gap-1">
    {cloneElement(children as ReactElement<Record<string, unknown>>, props)}
    <div className="flex items-center gap-2 text-xs text-[var(--color-text-3)]">
      {loading && <Spin size="small" />}
      <Button size="small" type="text" icon={<ReloadOutlined />} aria-label="刷新取数" title="刷新取数" disabled={loading} onClick={() => setRefresh(n => n + 1)} />
      {result?.has_more && <Button size="small" type="link" disabled={loading} onClick={() => setPage(n => n + 1)}>加载更多</Button>}
      {error && <span role="alert" className="text-[var(--color-fail)]">{error}</span>}
    </div>
  </div>;
}
