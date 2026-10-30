'use client';

import React from 'react';
import { Button, Form, Input, Select, Switch, message } from 'antd';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import type { ItsmBinding } from '@/app/alarm/types/settings';

interface BindingEditorProps { value?: ItsmBinding[]; onChange?: (value: ItsmBinding[]) => void; lockedNames?: string[] }
function BindingEditor({ value = [], onChange, lockedNames = [] }: BindingEditorProps) {
  const { t } = useTranslation();
  const locked = new Set(lockedNames);
  const update = (index: number, change: Partial<ItsmBinding>) => onChange?.(value.map((item, position) => position === index ? { ...item, ...change } : item));
  return <div className="flex flex-col gap-3">
    {value.map((binding, index) => <div key={index} className="flex flex-wrap items-start gap-2">
      <Input className="min-w-0 flex-1" aria-label={t('itsm.fieldName')} placeholder={t('itsm.fieldName')} value={binding.name} readOnly={locked.has(binding.name)} onChange={e => update(index, { name: e.target.value })} />
      <Select className="w-28" value={binding.from} options={[{ value: 'field', label: t('itsm.alertField') }, { value: 'const', label: t('itsm.constant') }]} onChange={from => update(index, { from, value: '' })} />
      {binding.from === 'field' ? <Input className="min-w-0 flex-1" aria-label={t('itsm.fieldPath')} placeholder="title / content / level / resource_name / labels.ip_addr" value={String(binding.value ?? '')} onChange={e => update(index, { value: e.target.value })} /> :
        <JsonValue value={binding.value} onChange={value => update(index, { value })} />}
      {!(locked.has(binding.name) && binding.name === 'ticket__title') && <Button danger type="text" onClick={() => onChange?.(value.filter((_, position) => position !== index))}>{t('common.delete')}</Button>}
    </div>)}
    {!lockedNames.length && <Button disabled={value.length >= 64} onClick={() => onChange?.([...value, { name: '', from: 'field', value: '' }])}>{t('itsm.addField')}</Button>}
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
    <Select className="w-24" value={type} options={['text', 'number', 'boolean', 'json'].map(key => ({ value: key, label: t(`itsm.${key === 'number' ? 'numberType' : key}`) }))}
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
  const [schemaNames, setSchemaNames] = React.useState<string[]>([]);
  const [loadingFields, setLoadingFields] = React.useState(false);
  React.useEffect(() => {
    let cancelled = false;
    setLoadingServices(true);
    get<ItsmService[]>('/alerts/api/itsm_integration/services/')
      .then((list) => { if (!cancelled) setServices(Array.isArray(list) ? list : []); })
      .catch(() => { if (!cancelled) setServiceError(t('itsm.loadServicesFailed')); })
      .finally(() => { if (!cancelled) setLoadingServices(false); });
    return () => { cancelled = true; };
  }, [get, t]);
  const loadFields = async (workflowKey: string) => {
    setLoadingFields(true);
    try {
      const fields = await get<{ key: string; name: string; type: string }[]>(`/alerts/api/itsm_integration/form_fields/?workflow_key=${encodeURIComponent(workflowKey)}`);
      const current = (form.getFieldValue('form_bindings') || []) as ItsmBinding[];
      form.setFieldValue('form_bindings', fields.map((field) => {
        const existing = current.find((item) => item.name === field.key);
        if (existing) return existing;
        return field.key === 'ticket__title' ? { name: field.key, from: 'field' as const, value: 'title' } : { name: field.key, from: 'const' as const, value: '' };
      }));
      setSchemaNames(fields.map((field) => field.key));
    } catch {
      setSchemaNames([]);
      message.error(t('itsm.loadFieldsFailed'));
    } finally {
      setLoadingFields(false);
    }
  };
  const options = services.some((item) => item.value === workflow) || !workflow
    ? services
    : [...services, { value: String(workflow), label: String(workflow) }];
  return <>
    <Form.Item name="connection" label={t('itsm.connection')} rules={[{ required: true }]} extra={!connections.length ? t('itsm.noConnection') : undefined}>
      <Select options={connections} />
    </Form.Item>
    <Form.Item name="workflow_key" label={t('itsm.workflow')} rules={[{ required: true, whitespace: true }]} extra={serviceError || (!loadingServices && !services.length ? t('itsm.servicesEmpty') : undefined)}>
      <Select showSearch optionFilterProp="label" loading={loadingServices || loadingFields} options={options} placeholder={t('itsm.workflowRequired')} onChange={(value) => { void loadFields(String(value)); }} />
    </Form.Item>
    {workflow && <Form.Item label={t('itsm.bindings')} required>
      <Form.Item name="form_bindings" noStyle rules={[{ validator: (_, bindings: ItsmBinding[]) => {
        if (!bindings?.length || !bindings.some(item => item.name === 'ticket__title') || bindings.some(item => !item.name.trim() || item.value == null || (item.from === 'field' && !String(item.value).trim()))) return Promise.reject(new Error(t('itsm.invalidBindings')));
        return Promise.resolve();
      } }]}><BindingEditor lockedNames={schemaNames} /></Form.Item>
    </Form.Item>}
  </>;
}
