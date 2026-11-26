'use client';

import { Button, Divider, Empty, Form, Input, InputNumber, Select, Tabs, Upload, message } from 'antd';
import type { FormInstance } from 'antd';
import { FULL_ROW_TYPES } from '../constants/field-catalog';
import type { FormFieldSchema, FormSchema } from '../types';
import { useItsmApi } from '../api/useItsmApi';
import GroupTreeSelect from '@/components/group-tree-select';
import { basicFieldControl, dateItemProps } from './basic-field-control';
import { TableField, SignatureField, isRequiredColumn } from './structured-fields';
import { FieldFetchControl, type FetchContext } from './field-fetch-control';
import { matches } from './form-conditions';
import { SubProcessField } from './subprocess-field';

function AttachmentField({ disabled, value, onChange, field, context }: { field: string; context?: FetchContext; disabled: boolean; value?: string[]; onChange?: (value: string[]) => void }) {
  const api = useItsmApi();
  return (
    <Upload
      disabled={disabled}
      customRequest={async (options) => {
        const file = options.file as File;
        try {
          const signed = await api.presignAttachment(file.name, context?.ticket_id, context?.ticket_id ? { field, task_id: context.task_id } : undefined) as { url: string; object_name: string };
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
  fetchContext?: FetchContext;
  form?: FormInstance;
  hideSubmit?: boolean;
  initialValues?: Record<string, unknown>;
  fieldPerm?: Record<string, 'hidden' | 'read' | 'edit' | 'readonly' | 'editable' | 'required'>;
  readOnly?: boolean;
  onSubmit: (values: Record<string, unknown>) => void;
}

const TABLE_TYPES = new Set(['table', 'nestedTable', 'task', 'cab']);
const control = (field: FormFieldSchema, disabled: boolean, context?: FetchContext, fieldPerm?: FormRendererProps['fieldPerm']) => {
  if (field.type === 'calculate') {
    return <InputNumber className="w-full" disabled placeholder={field.placeholder || String(field.props?.expr || '')} />;
  }
  if (field.type === 'organization' || field.type === 'userGroup' || field.type === 'multiUserGroup' || field.type === 'group') {
    const multiple = field.type === 'multiUserGroup' || field.type === 'group';
    return <GroupTreeSelect multiple={multiple} showSearch disabled={disabled} placeholder={field.placeholder || '选择组织'} />;
  }
  if (field.type === 'cmdb' || field.type === 'multiCmdb' || field.type === 'singleAssociateConfig' || field.type === 'associateConfig') {
    const multiple = field.type === 'multiCmdb' || field.type === 'associateConfig';
    return <Select mode={multiple ? 'multiple' : undefined} disabled={disabled} options={field.source?.options || []} placeholder={field.placeholder || '请选择'} />;
  }
  if (field.type === 'description') {
    return <div>{field.hint || field.label}</div>;
  }
  if (field.type === 'divider') {
    return <Divider />;
  }
  if (field.type === 'attachment') {
    return <AttachmentField field={field.key} context={context} disabled={disabled} />;
  }
  if (TABLE_TYPES.has(field.type)) {
    return <TableField field={field} disabled={disabled} context={context} fieldPerm={fieldPerm} />;
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
  return basicFieldControl(field, disabled);
};

const emptyCell = (value: unknown) => value == null || value === '' || (Array.isArray(value) && !value.length);

function emptyTablePlaceholder(rows: unknown): boolean {
  return Array.isArray(rows) && rows.length === 1 && rows[0] != null && typeof rows[0] === 'object'
    && Object.entries(rows[0]).every(([key, value]) => ['_field_receipts','_field_labels','_itsm_row_ref'].includes(key) || emptyCell(value));
}

const SPANS: Record<number, string> = { 3: 'col-span-3', 4: 'col-span-4', 6: 'col-span-6', 8: 'col-span-8', 9: 'col-span-9', 12: 'col-span-12', 24: 'col-span-12' };

function FieldItems({ fields, fieldPerm, readOnly, fetchContext, rules = [] }: { rules?: FormSchema['rules']; fetchContext?: FetchContext; fields: FormFieldSchema[]; fieldPerm: NonNullable<FormRendererProps['fieldPerm']>; readOnly: boolean }) {
  return <>{fields.map((field) => <Form.Item key={field.key} noStyle shouldUpdate>
    {({ getFieldsValue }) => {
      const perm = fieldPerm[field.key] || fieldPerm['*'] || 'edit';
      const values = getFieldsValue(true);
      const visibilityRules = rules.filter(rule => rule.field === field.key && rule.type === 'visible');
      const visibleWhen = visibilityRules.length ? visibilityRules[visibilityRules.length - 1].when : field.visibleWhen;
      const required = field.required || perm === 'required' || rules.some(rule => rule.field === field.key && rule.type === 'required' && matches(rule.when, values));
      if (field.state === 'hidden' || perm === 'hidden' || !matches(visibleWhen, values)) return null;
      const locked = readOnly || ['read', 'readonly'].includes(perm) || field.state === 'readonly' || field.state === 'disabled';
      if (field.type === 'tab' || field.type === 'section') {
        const children = <div className="grid grid-cols-12 gap-x-4 gap-y-1"><FieldItems rules={rules} fields={field.children || []} fieldPerm={fieldPerm} readOnly={locked} fetchContext={fetchContext} /></div>;
        return <div className="col-span-12 rounded-lg border border-[var(--color-border)] p-3">
          {field.type === 'tab' ? <Tabs items={[{ key: field.key, label: field.label || '标签', children }]} /> : <><div className="mb-2 text-sm font-medium text-[var(--color-text-1)]">{field.label}</div>{children}</>}
        </div>;
      }
      const table = TABLE_TYPES.has(field.type);
      const requiredColumns = table ? field.children?.filter(column => isRequiredColumn(column, fieldPerm)) || [] : [];
      return <Form.Item
        className={`${SPANS[FULL_ROW_TYPES.has(field.type) ? 12 : (field.span || 6)] || 'col-span-6'} ${field.rowBreak ? 'col-start-1' : ''}`}
        name={field.key} label={field.type === 'divider' ? undefined : field.label} extra={field.hint}
        validateTrigger={table ? [] : undefined}
        rules={locked ? [] : [
          ...(required ? [table ? { type: 'array' as const, required: true, min: 1, message: '请至少添加一行',
            transform: (rows: unknown) => !requiredColumns.length && emptyTablePlaceholder(rows) ? [] : rows,
          } : { required: true }] : []),
          ...(requiredColumns.length ? [{
            validator: async (_: unknown, rows: Record<string, unknown>[]) => {
              if (!required && emptyTablePlaceholder(rows)) return;
              for (const [index, row] of (Array.isArray(rows) ? rows : []).entries()) {
                const empty = requiredColumns.find(column => matches(column.visibleWhen, row || {}) && emptyCell(row?.[column.key]));
                if (empty) throw new Error(`请填写第 ${index + 1} 行的${empty.label}`);
              }
            },
          }] : []),
        ]}
        {...dateItemProps(field)}
      >{field.fetch && fetchContext && !locked ? <FieldFetchControl field={field} context={fetchContext}>{control(field, locked, fetchContext, fieldPerm)!}</FieldFetchControl> : control(field, locked, fetchContext, fieldPerm)}</Form.Item>;
    }}
  </Form.Item>)}</>;
}

export function FormRenderer({ fetchContext, form, hideSubmit = false, schema, initialValues, fieldPerm = {}, readOnly = false, onSubmit }: FormRendererProps) {
  const values = { ...initialValues };
  function initializeFields(fields: FormFieldSchema[]) {
    for (const field of fields) {
      const permission = fieldPerm[field.key] || fieldPerm['*'];
      if (['hidden', 'readonly', 'disabled'].includes(field.state || '') || ['read', 'readonly', 'hidden'].includes(permission)) continue;
      if (TABLE_TYPES.has(field.type)) {
        const rows = values[field.key];
        if (rows == null || (Array.isArray(rows) && !rows.length)) {
          values[field.key] = Array.isArray(field.default) && field.default.length ? field.default : [{}];
        }
      } else if (field.type === 'select' && !field.fetch && field.props?.defaultFirstOption === true) {
        const first = field.source?.options?.[0];
        if (first && (values[field.key] == null || values[field.key] === '')) values[field.key] = first.value;
      } else if (field.children) {
        initializeFields(field.children);
      }
    }
  }
  if (!readOnly && !fetchContext?.ticket_id) initializeFields(schema.fields || []);
  return <Form form={form} layout="vertical" initialValues={values} onFinish={(values) => onSubmit(values as Record<string, unknown>)}>
    <Form.Item name="_field_receipts" hidden><Input /></Form.Item>
    {schema.fields?.length ? <div className="grid grid-cols-12 gap-x-4 gap-y-1"><FieldItems rules={schema.rules} fields={schema.fields} fieldPerm={fieldPerm} readOnly={readOnly} fetchContext={fetchContext} /></div>
    : <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] py-8"><Empty description="当前表单暂无可展示的字段内容" /></div>}
    {readOnly || hideSubmit || !schema.fields?.length ? null : <div className="mt-2 flex justify-end border-t border-[var(--color-border)] pt-4"><Button type="primary" htmlType="submit">提交</Button></div>}
  </Form>;
}
