'use client';

import React from 'react';
import { Button, Checkbox, Form, Input, InputNumber, Select, Switch, message } from 'antd';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import type { ItsmBinding } from '@/app/alarm/types/settings';

export interface ItsmFormField {
  key: string;
  name: string;
  type: string;
  required?: boolean;
  options?: { key: string; name: string }[];
}

const TITLE_KEY = 'ticket__title';
const ALERT_FIELDS = ['title', 'content', 'level', 'status', 'alert_id', 'resource_name', 'resource_id', 'resource_type', 'item', 'source_names'];
const CUSTOM_PATH = /^(labels|enrichment|event)\.[\w.-]+$/;
const LONG_TEXT = /richtext|textarea/i;
const MULTIPLE = /checkbox|multi/i;
const NUMBER = /number/i;
const USER = /user|reporter|member/i;

type Source = 'none' | ItsmBinding['from'];

function emptyConst(field: ItsmFormField): unknown {
  return field.options?.length && MULTIPLE.test(field.type) ? [] : '';
}

/** 换工单时保留同名字段的映射，并给标题和第一个长文本字段预填告警标题、内容。 */
export function defaultBindings(fields: ItsmFormField[], current: ItsmBinding[]): ItsmBinding[] {
  const keys = new Set(fields.map((field) => field.key));
  const kept = current.filter((item) => keys.has(item.name));
  if (!kept.some((item) => item.name === TITLE_KEY)) kept.unshift({ name: TITLE_KEY, from: 'field', value: 'title' });
  const bound = new Set(kept.map((item) => item.name));
  const longText = fields
    .filter((field) => field.key !== TITLE_KEY && LONG_TEXT.test(field.type) && !bound.has(field.key))
    .sort((a, b) => Number(Boolean(b.required)) - Number(Boolean(a.required)))[0];
  if (longText && !kept.some((item) => item.from === 'field' && item.value === 'content')) {
    kept.push({ name: longText.key, from: 'field', value: 'content' });
  }
  return kept;
}

function AlertFieldSelect({ value, onChange }: { value: unknown; onChange: (value: string) => void }) {
  const { t } = useTranslation();
  const [search, setSearch] = React.useState('');
  const current = String(value ?? '');
  const custom = [current, search.trim()].filter((path, index, list) =>
    path && !ALERT_FIELDS.includes(path) && list.indexOf(path) === index && (path === current || CUSTOM_PATH.test(path)));
  const options = [
    ...ALERT_FIELDS.map((key) => ({
      value: key,
      search: `${t(`itsm.alertFields.${key}`)} ${key}`,
      label: <span>{t(`itsm.alertFields.${key}`)}<span className="ml-2 text-xs text-[var(--color-text-3)]">{key}</span></span>,
    })),
    ...custom.map((path) => ({ value: path, search: path, label: path === current ? path : t('itsm.customPath', undefined, { path }) })),
  ];
  return <Select
    showSearch
    className="w-full"
    aria-label={t('itsm.fieldPath')}
    value={current || undefined}
    placeholder={t('itsm.pickAlertField')}
    options={options}
    filterOption={(input, option) => String(option?.search ?? '').toLowerCase().includes(input.toLowerCase())}
    onSearch={setSearch}
    onChange={(path: string) => { setSearch(''); onChange(path); }}
    notFoundContent={<span className="text-xs">{t('itsm.customPathTip')}</span>}
  />;
}

function ConstValue({ field, value, onChange }: { field: ItsmFormField; value: unknown; onChange: (value: unknown) => void }) {
  const { t } = useTranslation();
  if (field.options?.length) {
    const multiple = MULTIPLE.test(field.type);
    return <Select
      allowClear
      showSearch
      optionFilterProp="label"
      className="w-full"
      aria-label={t('itsm.constant')}
      mode={multiple ? 'multiple' : undefined}
      value={multiple ? (Array.isArray(value) ? value : []) : (value === '' || value == null ? undefined : value)}
      placeholder={t('itsm.pickOption')}
      options={field.options.map((item) => ({ value: item.key, label: item.name }))}
      onChange={(next) => onChange(next ?? (multiple ? [] : ''))}
    />;
  }
  if (typeof value === 'boolean' || (value !== null && typeof value === 'object')) return <JsonValue value={value} onChange={onChange} />;
  if (NUMBER.test(field.type)) {
    return <InputNumber className="w-full" aria-label={t('itsm.constant')} value={typeof value === 'number' ? value : null} onChange={(next) => onChange(next ?? '')} />;
  }
  if (LONG_TEXT.test(field.type)) {
    return <Input.TextArea autoSize={{ minRows: 1, maxRows: 4 }} aria-label={t('itsm.constant')} placeholder={t('itsm.constantPlaceholder')} value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} />;
  }
  return <Input aria-label={t('itsm.constant')} placeholder={t(USER.test(field.type) || USER.test(field.key) ? 'itsm.userPlaceholder' : 'itsm.constantPlaceholder')}
    value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} />;
}

interface SchemaEditorProps { fields: ItsmFormField[]; value?: ItsmBinding[]; onChange?: (value: ItsmBinding[]) => void }
function SchemaBindingEditor({ fields, value = [], onChange }: SchemaEditorProps) {
  const { t } = useTranslation();
  const [focused, setFocused] = React.useState(false);
  const bindings = new Map(value.map((item) => [item.name, item]));
  const known = new Set(fields.map((field) => field.key));
  const rows: { field: ItsmFormField; missing: boolean }[] = [
    ...fields.map((field) => ({ field, missing: false })),
    ...value.filter((item) => !known.has(item.name)).map((item) => ({ field: { key: item.name, name: item.name, type: '' }, missing: true })),
  ];
  const visible = focused ? rows.filter(({ field, missing }) => missing || field.required || bindings.has(field.key)) : rows;
  const put = (name: string, binding: ItsmBinding | null) => {
    if (!binding) { onChange?.(value.filter((item) => item.name !== name)); return; }
    onChange?.(bindings.has(name) ? value.map((item) => item.name === name ? binding : item) : [...value, binding]);
  };
  const changeSource = (field: ItsmFormField, source: Source) => {
    if (source === 'none') put(field.key, null);
    else if (source === 'field') put(field.key, { name: field.key, from: 'field', value: field.key === TITLE_KEY ? 'title' : '' });
    else put(field.key, { name: field.key, from: 'const', value: emptyConst(field) });
  };
  const grid = 'grid grid-cols-[minmax(0,180px)_112px_minmax(0,1fr)] items-start gap-x-3';
  return <div className="rounded border border-[var(--color-border-1)]">
    <div className="flex items-center justify-between border-b border-[var(--color-border-1)] px-3 py-2 text-xs text-[var(--color-text-3)]">
      <span>{t('itsm.mappedCount', undefined, { mapped: String(fields.filter((field) => bindings.has(field.key)).length), total: String(fields.length) })}</span>
      <Checkbox className="text-xs" checked={focused} onChange={(e) => setFocused(e.target.checked)}>{t('itsm.onlyRelevant')}</Checkbox>
    </div>
    <div className={`${grid} border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-1.5 text-xs text-[var(--color-text-3)]`}>
      <span>{t('itsm.columnField')}</span><span>{t('itsm.columnSource')}</span><span>{t('itsm.columnValue')}</span>
    </div>
    {visible.map(({ field, missing }) => {
      const binding = bindings.get(field.key);
      const source: Source = binding?.from ?? 'none';
      return <div key={field.key} className={`${grid} border-b border-[var(--color-border-1)] px-3 py-2 last:border-b-0`} data-testid={`itsm-row-${field.key}`}>
        <div className="min-w-0 pt-1">
          <div className="truncate text-sm" title={field.name}>
            {field.required && <span className="mr-0.5 text-[var(--color-fail)]">*</span>}{field.name}
          </div>
          <div className="truncate text-xs text-[var(--color-text-3)]" title={field.key}>{missing ? t('itsm.missingField') : field.key}</div>
        </div>
        <Select
          aria-label={t('itsm.columnSource')}
          value={source}
          onChange={(next: Source) => changeSource(field, next)}
          options={[
            { value: 'none', label: t('itsm.sourceNone'), disabled: field.key === TITLE_KEY },
            { value: 'field', label: t('itsm.alertField') },
            { value: 'const', label: t('itsm.sourceConst') },
          ]}
        />
        <div className="min-w-0">
          {binding?.from === 'field' && <AlertFieldSelect value={binding.value} onChange={(path) => put(field.key, { ...binding, value: path })} />}
          {binding?.from === 'const' && <ConstValue field={field} value={binding.value} onChange={(next) => put(field.key, { ...binding, value: next })} />}
          {!binding && <div className={`pt-1 text-xs ${field.required ? 'text-[var(--color-warning)]' : 'text-[var(--color-text-3)]'}`}>
            {field.required ? t('itsm.requiredHint') : t('itsm.notMapped')}
          </div>}
        </div>
      </div>;
    })}
  </div>;
}

interface BindingEditorProps { value?: ItsmBinding[]; onChange?: (value: ItsmBinding[]) => void }
function BindingEditor({ value = [], onChange }: BindingEditorProps) {
  const { t } = useTranslation();
  const update = (index: number, change: Partial<ItsmBinding>) => onChange?.(value.map((item, position) => position === index ? { ...item, ...change } : item));
  return <div className="flex flex-col gap-3">
    {value.map((binding, index) => <div key={index} className="flex flex-wrap items-start gap-2">
      <Input className="min-w-0 flex-1" aria-label={t('itsm.fieldName')} placeholder={t('itsm.fieldName')} value={binding.name} readOnly={binding.name === TITLE_KEY} onChange={e => update(index, { name: e.target.value })} />
      <Select className="w-28" value={binding.from} options={[{ value: 'field', label: t('itsm.alertField') }, { value: 'const', label: t('itsm.sourceConst') }]} onChange={from => update(index, { from, value: '' })} />
      <div className="min-w-0 flex-[2]">
        {binding.from === 'field' ? <AlertFieldSelect value={binding.value} onChange={path => update(index, { value: path })} /> :
          <JsonValue value={binding.value} onChange={value => update(index, { value })} />}
      </div>
      {binding.name !== TITLE_KEY && <Button danger type="text" onClick={() => onChange?.(value.filter((_, position) => position !== index))}>{t('common.delete')}</Button>}
    </div>)}
    <Button className="self-start" disabled={value.length >= 64} onClick={() => onChange?.([...value, { name: '', from: 'field', value: '' }])}>{t('itsm.addField')}</Button>
  </div>;
}
function JsonValue({ value, onChange }: { value: unknown; onChange: (value: unknown) => void }) {
  const { t } = useTranslation();
  const [type, setType] = React.useState(typeof value === 'string' ? 'text' : typeof value === 'number' ? 'number' : typeof value === 'boolean' ? 'boolean' : 'json');
  const [invalid, setInvalid] = React.useState(false);
  const [draft, setDraft] = React.useState(typeof value === 'string' ? value : JSON.stringify(value));
  React.useEffect(() => {
    // null 保留正在编辑的非法 JSON；有效外部值（包括删行后的值）同步到编辑器。
    if (value == null) return;
    setDraft(type === 'json' ? JSON.stringify(value) : String(value));
    setInvalid(false);
    if (type !== 'json') setType(typeof value === 'string' ? 'text' : typeof value === 'number' ? 'number' : typeof value === 'boolean' ? 'boolean' : 'json');
  }, [value, type]);
  return <div className="flex min-w-0 flex-1 gap-2">
    <Select className="w-24 shrink-0" value={type} options={['text', 'number', 'boolean', 'json'].map(key => ({ value: key, label: t(`itsm.${key === 'number' ? 'numberType' : key}`) }))}
      onChange={kind => { setType(kind); setInvalid(false); onChange(kind === 'text' ? '' : kind === 'number' ? 0 : kind === 'boolean' ? false : {}); }} />
    {type === 'boolean' ? <Switch checked={value as boolean} onChange={onChange} /> : <Input key={type} className="min-w-0 flex-1" status={invalid ? 'error' : undefined}
      value={draft ?? ''} aria-label={t('itsm.constant')}
      onChange={e => {
        setDraft(e.target.value);
        if (type === 'text') { onChange(e.target.value); return; }
        try {
          const parsed: unknown = JSON.parse(e.target.value);
          if (type === 'number' && typeof parsed !== 'number') throw new Error('number required');
          setInvalid(false); onChange(parsed);
        } catch { setInvalid(true); onChange(null); }
      }} />}
  </div>;
}
interface ItsmService { value: string; label: string }
export default function ItsmFields({ connections }: { connections: { value: string; label: string }[] }) {
  const { t } = useTranslation();
  const { get } = useApiClient();
  const form = Form.useFormInstance();
  const workflow = Form.useWatch('workflow_key', form);
  const [services, setServices] = React.useState<ItsmService[]>([]);
  const [loadingServices, setLoadingServices] = React.useState(true);
  const [serviceError, setServiceError] = React.useState('');
  const [fields, setFields] = React.useState<ItsmFormField[]>([]);
  const [loadingFields, setLoadingFields] = React.useState(false);
  const resetBindings = React.useRef(false);
  const tRef = React.useRef(t);
  tRef.current = t;
  React.useEffect(() => {
    let cancelled = false;
    setLoadingServices(true);
    get<ItsmService[]>('/alerts/api/itsm_integration/services/')
      .then((list) => { if (!cancelled) setServices(Array.isArray(list) ? list : []); })
      .catch(() => { if (!cancelled) setServiceError(tRef.current('itsm.loadServicesFailed')); })
      .finally(() => { if (!cancelled) setLoadingServices(false); });
    return () => { cancelled = true; };
  }, [get]);
  React.useEffect(() => {
    if (!workflow) { setFields([]); return; }
    let cancelled = false;
    setLoadingFields(true);
    get<ItsmFormField[]>(`/alerts/api/itsm_integration/form_fields/?workflow_key=${encodeURIComponent(String(workflow))}`)
      .then((list) => {
        if (cancelled) return;
        const schema = Array.isArray(list) ? list : [];
        setFields(schema);
        if (resetBindings.current && schema.length) form.setFieldValue('form_bindings', defaultBindings(schema, form.getFieldValue('form_bindings') || []));
      })
      .catch(() => {
        if (cancelled) return;
        setFields([]);
        message.error(tRef.current('itsm.loadFieldsFailed'));
      })
      .finally(() => {
        if (cancelled) return;
        resetBindings.current = false;
        setLoadingFields(false);
      });
    return () => { cancelled = true; };
  }, [workflow, get, form]);
  const options = services.some((item) => item.value === workflow) || !workflow
    ? services
    : [...services, { value: String(workflow), label: String(workflow) }];
  return <>
    <Form.Item name="connection" label={t('itsm.connection')} rules={[{ required: true }]} extra={!connections.length ? t('itsm.noConnection') : undefined}>
      <Select options={connections} />
    </Form.Item>
    <Form.Item name="workflow_key" label={t('itsm.workflow')} rules={[{ required: true, whitespace: true }]} extra={serviceError || (!loadingServices && !services.length ? t('itsm.servicesEmpty') : undefined)}>
      <Select showSearch optionFilterProp="label" loading={loadingServices || loadingFields} options={options} placeholder={t('itsm.workflowRequired')} onChange={() => { resetBindings.current = true; }} />
    </Form.Item>
    {workflow && <Form.Item label={t('itsm.bindings')} required extra={fields.length ? t('itsm.bindingsHint') : undefined}>
      <Form.Item name="form_bindings" noStyle rules={[{ validator: (_, bindings: ItsmBinding[]) => {
        const title = bindings?.find(item => item.name === TITLE_KEY);
        if (!title || !String(title.value ?? '').trim()) return Promise.reject(new Error(t('itsm.titleRequired')));
        if (bindings.some(item => !item.name.trim() || item.value == null || (item.from === 'field' && !String(item.value).trim()))) return Promise.reject(new Error(t('itsm.invalidBindings')));
        return Promise.resolve();
      } }]}>
        {fields.length ? <SchemaBindingEditor fields={fields} /> : <BindingEditor />}
      </Form.Item>
    </Form.Item>}
  </>;
}
