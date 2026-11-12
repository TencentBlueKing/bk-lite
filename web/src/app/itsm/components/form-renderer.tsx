'use client';

import { Button, Checkbox, DatePicker, Divider, Empty, Form, Input, InputNumber, Radio, Select, Tabs, Upload, message } from 'antd';
import type { FormInstance } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { FULL_ROW_TYPES } from '../constants/field-catalog';
import type { FormFieldSchema, FormSchema } from '../types';
import AIEditor from '@/app/opspilot/components/ai-editor';
import { useItsmApi } from '../api/useItsmApi';
import GroupTreeSelect from '@/components/group-tree-select';
import { UserSelector } from './user-selector';
import { TableField, SignatureField } from './structured-fields';
import { SubProcessField } from './subprocess-field';

function RichTextField({
  disabled,
  value,
  onChange,
  placeholder,
}: {
  disabled: boolean;
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
}) {
  if (disabled) {
    return <div className="whitespace-pre-wrap">{value || ''}</div>;
  }
  return (
    <div className="h-64">
      <AIEditor placeholder={placeholder} value={value} onChange={onChange} />
    </div>
  );
}

function AttachmentField({ disabled, value, onChange }: { disabled: boolean; value?: string[]; onChange?: (value: string[]) => void }) {
  const api = useItsmApi();
  return (
    <Upload
      disabled={disabled}
      customRequest={async (options) => {
        const file = options.file as File;
        try {
          const signed = await api.presignAttachment(file.name) as { url: string; object_name: string };
          const response = await fetch(signed.url, { method: 'PUT', body: file });
          if (!response.ok) {
            throw new Error('上传失败');
          }
          onChange?.([...(value || []), signed.object_name]);
          options.onSuccess?.({});
        } catch (error) {
          message.error(error instanceof Error ? error.message : '上传失败');
          options.onError?.(error as Error);
        }
      }}
    >
      <Button disabled={disabled}>上传附件</Button>
    </Upload>
  );
}

interface FormRendererProps {
  schema: FormSchema;
  form?: FormInstance;
  hideSubmit?: boolean;
  initialValues?: Record<string, unknown>;
  fieldPerm?: Record<string, 'hidden' | 'read' | 'edit'>;
  readOnly?: boolean;
  onSubmit: (values: Record<string, unknown>) => void;
}

const matches = (rule: FormFieldSchema['visibleWhen'], values: Record<string, unknown>) => {
  if (!rule) {
    return true;
  }
  return rule.items.every((item) => {
    if (!('op' in item)) {
      return true;
    }
    const current = values[item.field];
    if (item.op === '=') {
      return String(current ?? '') === String(item.value ?? '');
    }
    if (item.op === '!=') {
      return String(current ?? '') !== String(item.value ?? '');
    }
    if (item.op === 'is_empty') {
      return current == null || current === '';
    }
    if (item.op === 'not_empty') {
      return current != null && current !== '';
    }
    return true;
  });
};

const DATE_TYPES = new Set(['date', 'time', 'datetime', 'dateRange']);

const asDayjs = (value: unknown): Dayjs | null => {
  if (value == null || value === '') {
    return null;
  }
  if (dayjs.isDayjs(value)) {
    return value;
  }
  const parsed = dayjs(value as string | number | Date);
  return parsed.isValid() ? parsed : null;
};

const pickerValue = (field: FormFieldSchema, value: unknown) => {
  if (field.type === 'dateRange') {
    return Array.isArray(value) ? value.map(asDayjs) : null;
  }
  return asDayjs(value);
};

const storedValue = (field: FormFieldSchema, value: unknown) => {
  if (field.type === 'dateRange') {
    return Array.isArray(value)
      ? value.map((item) => (dayjs.isDayjs(item) ? item.format('YYYY-MM-DD') : item))
      : value;
  }
  if (!dayjs.isDayjs(value)) {
    return value;
  }
  if (field.type === 'time') {
    return value.format('HH:mm:ss');
  }
  if (field.type === 'datetime') {
    return value.format('YYYY-MM-DD HH:mm:ss');
  }
  return value.format('YYYY-MM-DD');
};

const dateItemProps = (field: FormFieldSchema) => (
  DATE_TYPES.has(field.type)
    ? {
      getValueProps: (value: unknown) => ({ value: pickerValue(field, value) }),
      normalize: (value: unknown) => storedValue(field, value),
    }
    : {}
);

const control = (field: FormFieldSchema, disabled: boolean) => {
  if (field.type === 'number' || field.type === 'calculate') {
    return <InputNumber className="w-full" disabled={disabled || field.type === 'calculate'} placeholder={field.placeholder || String(field.props?.expr || '')} />;
  }
  if (field.type === 'textarea') {
    return <Input.TextArea disabled={disabled} rows={field.rows} placeholder={field.placeholder} />;
  }
  if (field.type === 'radio') {
    return <Radio.Group className={field.optionLayout === 'vertical' ? 'flex flex-col gap-1' : ''} disabled={disabled} options={field.source?.options || []} />;
  }
  if (field.type === 'checkbox') {
    return <Checkbox.Group className={field.optionLayout === 'vertical' ? 'flex flex-col gap-1' : ''} disabled={disabled} options={field.source?.options || []} />;
  }
  if (field.type === 'date') {
    return <DatePicker className="w-full" disabled={disabled} />;
  }
  if (field.type === 'time') {
    return <DatePicker className="w-full" picker="time" disabled={disabled} />;
  }
  if (field.type === 'datetime') {
    return <DatePicker className="w-full" showTime disabled={disabled} />;
  }
  if (field.type === 'dateRange') {
    return <DatePicker.RangePicker className="w-full" disabled={disabled} />;
  }
  if (field.type === 'organization' || field.type === 'userGroup' || field.type === 'multiUserGroup' || field.type === 'group') {
    const multiple = field.type === 'multiUserGroup' || field.type === 'group';
    return <GroupTreeSelect multiple={multiple} showSearch disabled={disabled} placeholder={field.placeholder || '选择组织'} />;
  }
  if (field.type === 'user' || field.type === 'multiUser') {
    return <UserSelector multiple={field.type === 'multiUser'} disabled={disabled} placeholder={field.placeholder || '搜索用户'} />;
  }
  if (field.type === 'cascade' || field.type === 'multiCascade' || field.type === 'select' || field.type === 'multiselect' || field.type === 'cmdb' || field.type === 'multiCmdb' || field.type === 'singleAssociateConfig' || field.type === 'associateConfig') {
    const multiple = field.type === 'multiselect' || field.type === 'multiCascade' || field.type === 'multiCmdb' || field.type === 'associateConfig';
    return <Select mode={multiple ? 'multiple' : undefined} disabled={disabled} options={field.source?.options || []} placeholder={field.placeholder || '请选择'} />;
  }
  if (field.type === 'description') {
    return <div>{field.hint || field.label}</div>;
  }
  if (field.type === 'divider') {
    return <Divider />;
  }
  if (field.type === 'attachment') {
    return <AttachmentField disabled={disabled} />;
  }
  if (field.type === 'richtext') {
    return <RichTextField disabled={disabled} placeholder={field.placeholder} />;
  }
  if (field.type === 'table' || field.type === 'nestedTable' || field.type === 'task' || field.type === 'cab') {
    return <TableField field={field} disabled={disabled} />;
  }
  if (field.type === 'link') {
    const href = String(field.props?.href || '');
    return href ? <a className="text-sm text-[var(--color-primary)]" href={href} target="_blank" rel="noreferrer">{field.label || href}</a> : <span className="text-sm text-[var(--color-text-3)]">未设置链接</span>;
  }
  if (field.type === 'subProcessForm') {
    return <SubProcessField field={field} disabled={disabled} />;
  }
  if (field.type === 'signature') {
    return <SignatureField disabled={disabled} />;
  }
  if (field.type === 'tab') {
    return null;
  }
  return <Input disabled={disabled} placeholder={field.placeholder} />;
};

const SPANS: Record<number, string> = { 3: 'col-span-3', 4: 'col-span-4', 6: 'col-span-6', 8: 'col-span-8', 9: 'col-span-9', 12: 'col-span-12', 24: 'col-span-12' };

function FieldItems({ fields, fieldPerm, readOnly }: { fields: FormFieldSchema[]; fieldPerm: NonNullable<FormRendererProps['fieldPerm']>; readOnly: boolean }) {
  return <>{fields.map((field) => <Form.Item key={field.key} noStyle shouldUpdate>
    {({ getFieldsValue }) => {
      const perm = fieldPerm[field.key] || fieldPerm['*'] || 'edit';
      if (field.state === 'hidden' || perm === 'hidden' || !matches(field.visibleWhen, getFieldsValue())) return null;
      const locked = readOnly || ['read', 'readonly'].includes(perm) || field.state === 'readonly' || field.state === 'disabled';
      if (field.type === 'tab' || field.type === 'section') {
        const children = <div className="grid grid-cols-12 gap-x-4 gap-y-1"><FieldItems fields={field.children || []} fieldPerm={fieldPerm} readOnly={locked} /></div>;
        return <div className="col-span-12 rounded-lg border border-[var(--color-border)] p-3">
          {field.type === 'tab' ? <Tabs items={[{ key: field.key, label: field.label || '标签', children }]} /> : <><div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">{field.label}</div>{children}</>}
        </div>;
      }
      return <Form.Item
        className={`${SPANS[FULL_ROW_TYPES.has(field.type) ? 12 : (field.span || 6)] || 'col-span-6'} ${field.rowBreak ? 'col-start-1' : ''}`}
        name={field.key} label={field.type === 'divider' ? undefined : field.label} extra={field.hint}
        rules={(field.required || String(perm) === 'required') && !locked ? [{ required: true }] : []}
        {...dateItemProps(field)}
      >{control(field, locked)}</Form.Item>;
    }}
  </Form.Item>)}</>;
}

export function FormRenderer({ form, hideSubmit = false, schema, initialValues, fieldPerm = {}, readOnly = false, onSubmit }: FormRendererProps) {
  return <Form form={form} layout="vertical" initialValues={initialValues} onFinish={(values) => onSubmit(values as Record<string, unknown>)}>
    {schema.fields?.length ? <div className="grid grid-cols-12 gap-x-4 gap-y-1"><FieldItems fields={schema.fields} fieldPerm={fieldPerm} readOnly={readOnly} /></div>
    : <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] py-8"><Empty description="当前表单暂无可展示的字段内容" /></div>}
    {readOnly || hideSubmit || !schema.fields?.length ? null : <div className="mt-2 flex justify-end border-t border-[var(--color-border)] pt-4"><Button type="primary" htmlType="submit">提交</Button></div>}
  </Form>;
}
