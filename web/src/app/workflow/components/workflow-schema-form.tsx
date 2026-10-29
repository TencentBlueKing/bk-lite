'use client';

import { Checkbox, Form, Input, InputNumber, Radio, Select, Switch } from 'antd';

import type { JsonSchema } from '../lib/types';

export function schemaProperties(schema: JsonSchema) {
  return Object.entries(schema.properties || {});
}

export function missingRequiredFields(schema: JsonSchema, value: Record<string, unknown>) {
  return (schema.required || []).filter((key) => {
    const item = value[key];
    return item === undefined || item === null || item === '' || (Array.isArray(item) && item.length === 0);
  });
}

export function WorkflowSchemaForm({
  schema,
  value,
  onChange,
  disabled = false,
}: {
  schema: JsonSchema;
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  disabled?: boolean;
}) {
  return (
    <Form layout="vertical">
      {schemaProperties(schema).map(([key, field]) => {
        const type = Array.isArray(field.type) ? field.type[0] : field.type;
        const required = schema.required?.includes(key);
        const label = field.title || key;
        const choices = type === 'array' ? field.items?.enum : field.enum;
        const setValue = (next: unknown) => onChange({ ...value, [key]: next });
        const controlId = `workflow-input-${key}`;

        if (choices && field['x-widget'] === 'radio') {
          return <Form.Item key={key} label={label} htmlFor={controlId} required={required}><Radio.Group id={controlId} disabled={disabled} value={value[key]} options={choices.map((item) => ({ value: item, label: String(item) }))} onChange={(event) => setValue(event.target.value)} /></Form.Item>;
        }
        if (choices) {
          return <Form.Item key={key} label={label} htmlFor={controlId} required={required}><Select id={controlId} disabled={disabled} mode={type === 'array' ? 'multiple' : undefined} value={value[key] as string | string[] | undefined} options={choices.map((item) => ({ value: item, label: String(item) }))} onChange={setValue} /></Form.Item>;
        }
        if (type === 'boolean') {
          return <Form.Item key={key} label={label} htmlFor={controlId} required={required}>{field['x-widget'] === 'switch'
            ? <Switch id={controlId} disabled={disabled} checked={Boolean(value[key])} onChange={setValue} />
            : <Checkbox id={controlId} disabled={disabled} checked={Boolean(value[key])} onChange={(event) => setValue(event.target.checked)} />}</Form.Item>;
        }
        if (type === 'number' || type === 'integer') {
          return <Form.Item key={key} label={label} htmlFor={controlId} required={required}><InputNumber id={controlId} disabled={disabled} className="w-full" value={typeof value[key] === 'number' ? value[key] as number : undefined} min={field.minimum} max={field.maximum} onChange={setValue} /></Form.Item>;
        }
        if (field['x-widget'] === 'textarea') {
          return <Form.Item key={key} label={label} htmlFor={controlId} required={required}><Input.TextArea id={controlId} disabled={disabled} rows={4} value={String(value[key] ?? '')} onChange={(event) => setValue(event.target.value)} /></Form.Item>;
        }
        return <Form.Item key={key} label={label} htmlFor={controlId} required={required}><Input id={controlId} disabled={disabled} value={String(value[key] ?? '')} onChange={(event) => setValue(event.target.value)} /></Form.Item>;
      })}
    </Form>
  );
}
