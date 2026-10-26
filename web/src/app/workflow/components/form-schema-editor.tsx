'use client';

import { DeleteOutlined, HolderOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Checkbox, Form, Input, InputNumber, Select, Switch, Tag } from 'antd';
import { useEffect, useState } from 'react';

import { useTranslation } from '@/utils/i18n';
import { changeFormFieldWidget, createFormFieldSchema, formFieldWidget } from '../lib/form-field-registry';
import type { FileFieldOptions, FormFieldWidget, JsonSchema, TargetFieldBinding } from '../lib/types';
import { WorkflowPermission } from './workflow-permission';
import { schemaProperties } from './workflow-schema-form';

function uniqueFieldKey(used: Set<string>) {
  let key = 'field';
  let suffix = 2;
  while (used.has(key)) key = `field_${suffix++}`;
  return key;
}

function TargetSelectorOptions({
  schema,
  disabled,
  required,
  onChange,
}: {
  schema: JsonSchema;
  disabled: boolean;
  required: boolean;
  onChange: (schema: JsonSchema) => void;
}) {
  const { t } = useTranslation();
  const binding = schema['x-target-binding'] as TargetFieldBinding;
  const minCount = required ? 1 : 0;
  const patch = (next: Partial<TargetFieldBinding>) => {
    const maxCount = Math.max(1, Number(next.maxCount ?? binding.maxCount) || 1);
    const updated = { ...binding, ...next, minCount, maxCount };
    onChange({ ...schema, minItems: minCount, maxItems: maxCount, 'x-target-binding': updated });
  };
  return <div className="col-span-2 grid grid-cols-2 gap-4 rounded-lg bg-[var(--color-fill-1)] p-4">
    <Form.Item className="mb-0" label={t('workflowOrchestration.editor.targetSources', '主机来源')}><Checkbox.Group disabled={disabled} value={binding.allowedSources} options={[{ label: t('workflowOrchestration.editor.nodeManagement', '节点管理'), value: 'node_mgmt' }, { label: t('workflowOrchestration.editor.jobPlatform', '作业平台'), value: 'job_mgmt' }]} onChange={(values) => values.length && patch({ allowedSources: values as TargetFieldBinding['allowedSources'] })} /></Form.Item>
    <Form.Item className="mb-0" label={t('workflowOrchestration.editor.operatingSystems', '操作系统')}><Checkbox.Group disabled={disabled} value={binding.allowedOperatingSystems} options={[{ label: 'Linux', value: 'linux' }, { label: 'Windows', value: 'windows' }]} onChange={(values) => patch({ allowedOperatingSystems: values as TargetFieldBinding['allowedOperatingSystems'] })} /></Form.Item>
    <Form.Item className="mb-0 col-span-2 sm:col-span-1" label={t('workflowOrchestration.editor.maximumTargets', '最多选择')}><InputNumber disabled={disabled} className="w-full" min={1} max={100} value={binding.maxCount} onChange={(value) => patch({ maxCount: Number(value || 1) })} /></Form.Item>
  </div>;
}

function FileUploadOptions({ schema, disabled, onChange }: { schema: JsonSchema; disabled: boolean; onChange: (schema: JsonSchema) => void }) {
  const { t } = useTranslation();
  const options = schema['x-file-options'] as FileFieldOptions;
  const patch = (next: Partial<FileFieldOptions>) => {
    const updated = { ...options, ...next };
    const nextSchema: JsonSchema = {
      ...schema,
      properties: {
        ...schema.properties,
        kind: { ...schema.properties?.kind, type: 'string', enum: ['uploaded'] },
        format: { ...schema.properties?.format, type: 'string', enum: updated.accept },
        size: { ...schema.properties?.size, type: 'integer', minimum: 1, maximum: updated.maxSizeMiB * 1024 * 1024 },
      },
      'x-file-options': updated,
    };
    onChange(nextSchema);
  };
  return <div className="col-span-2 grid grid-cols-2 gap-4 rounded-lg bg-[var(--color-fill-1)] p-4">
    <Form.Item className="mb-0" label={t('workflowOrchestration.editor.fileTypes', '允许文件类型')}><Select mode="multiple" disabled={disabled} value={options.accept} options={[{ value: 'docx', label: 'Word (.docx)' }, { value: 'xlsx', label: 'Excel (.xlsx)' }]} onChange={(values) => values.length && patch({ accept: values })} /></Form.Item>
    <Form.Item className="mb-0" label={t('workflowOrchestration.editor.maxFileSize', '单文件大小上限（MiB）')}><InputNumber disabled={disabled} className="w-full" min={1} max={5} value={options.maxSizeMiB} onChange={(value) => patch({ maxSizeMiB: Number(value || 1) })} /></Form.Item>
  </div>;
}

type SchemaEditorContext = 'form' | 'webhook' | 'nats';

function FieldKeyEditor({
  fieldKey,
  readOnly,
  usedKeys,
  onChange,
}: {
  fieldKey: string;
  readOnly: boolean;
  usedKeys: string[];
  onChange: (nextKey: string) => void;
}) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState(fieldKey);
  const [error, setError] = useState<string>();
  const fieldKeyHint = t('workflowOrchestration.editor.fieldKeyHint', '小写字母开头，可包含数字和下划线');
  const duplicateMessage = t('workflowOrchestration.editor.duplicateFieldKeyInline', '字段标识已存在');

  useEffect(() => {
    setDraft(fieldKey);
    setError(undefined);
  }, [fieldKey]);

  const validate = (nextKey: string) => {
    if (!nextKey || !/^[a-z][a-z0-9_]{0,63}$/.test(nextKey)) return fieldKeyHint;
    if (nextKey !== fieldKey && usedKeys.includes(nextKey)) return duplicateMessage;
    return undefined;
  };

  const commit = () => {
    const nextError = validate(draft);
    setError(nextError);
    if (!nextError && draft !== fieldKey) onChange(draft);
  };

  return <Form component={false} layout="vertical">
    <Form.Item
      className="mb-0"
      label={t('workflowOrchestration.editor.fieldKey', '字段标识')}
      tooltip={fieldKeyHint}
      validateStatus={error ? 'error' : undefined}
      help={error}
    >
      <Input
        disabled={readOnly}
        placeholder="field_key"
        value={draft}
        aria-invalid={error ? 'true' : undefined}
        onChange={(event) => {
          const nextKey = event.target.value;
          setDraft(nextKey);
          setError(validate(nextKey));
        }}
        onBlur={commit}
        onPressEnter={(event) => {
          event.preventDefault();
          event.currentTarget.blur();
        }}
      />
    </Form.Item>
  </Form>;
}

export function FormSchemaEditor({ value, onChange, readOnly, context = 'form' }: { value: JsonSchema; onChange: (value: JsonSchema) => void; readOnly: boolean; context?: SchemaEditorContext }) {
  const { t } = useTranslation();
  const properties = schemaProperties(value);
  const required = new Set(value.required || []);
  const isForm = context === 'form';
  const fieldTypeOptions = isForm ? [
    { value: 'input', label: t('workflowOrchestration.editor.singleLine', '单行文本') }, { value: 'textarea', label: t('workflowOrchestration.editor.multiLine', '多行文本') }, { value: 'number', label: t('workflowOrchestration.editor.number', '数字') }, { value: 'switch', label: t('workflowOrchestration.editor.switch', '开关') }, { value: 'select', label: t('workflowOrchestration.editor.select', '下拉单选') }, { value: 'radio', label: t('workflowOrchestration.editor.radio', '单选') }, { value: 'multiselect', label: t('workflowOrchestration.editor.multiSelect', '多选') },
    { value: 'target-selector', label: t('workflowOrchestration.editor.targetSelector', '主机选择器') }, { value: 'file-upload', label: t('workflowOrchestration.editor.fileUpload', '文件上传') },
  ] : [
    { value: 'input', label: t('workflowOrchestration.editor.stringType', '字符串') },
    { value: 'textarea', label: t('workflowOrchestration.editor.longTextType', '长文本') },
    { value: 'number', label: t('workflowOrchestration.editor.numberType', '数字') },
    { value: 'switch', label: t('workflowOrchestration.editor.booleanType', '布尔值') },
    { value: 'select', label: t('workflowOrchestration.editor.enumType', '枚举') },
    { value: 'multiselect', label: t('workflowOrchestration.editor.stringArrayType', '字符串数组') },
  ];
  const addFieldLabel = context === 'webhook'
    ? t('workflowOrchestration.editor.addWebhookInputField', '添加请求输入字段')
    : context === 'nats'
      ? t('workflowOrchestration.editor.addEventField', '添加事件字段')
      : t('workflowOrchestration.editor.addFormField', '添加表单字段');
  const newFieldTitle = context === 'webhook'
    ? t('workflowOrchestration.editor.newWebhookInputField', '新请求字段')
    : context === 'nats'
      ? t('workflowOrchestration.editor.newEventField', '新事件字段')
      : t('workflowOrchestration.editor.newField', '新字段');
  const changeField = (oldKey: string, nextKey: string, nextSchema: JsonSchema) => {
    if (nextKey !== oldKey && properties.some(([key]) => key === nextKey)) return;
    const nextProperties: Record<string, JsonSchema> = {};
    for (const [key, schema] of properties) nextProperties[key === oldKey ? nextKey : key] = key === oldKey ? nextSchema : schema;
    onChange({ ...value, type: 'object', properties: nextProperties, required: [...required].map((key) => key === oldKey ? nextKey : key), additionalProperties: false });
  };
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const reorder = (from: number, to: number) => {
    if (from === to) return;
    const entries = [...properties];
    const [moved] = entries.splice(from, 1);
    entries.splice(to, 0, moved);
    onChange({ ...value, type: 'object', properties: Object.fromEntries(entries), required: value.required || [], additionalProperties: false });
  };
  const usedKeys = properties.map(([item]) => item);
  return <div className="flex flex-col gap-3">
    {properties.map(([key, schema], index) => {
      const widget = formFieldWidget(schema);
      const setSchema = (nextSchema: JsonSchema) => changeField(key, key, nextSchema);
      return <section key={index} className="overflow-hidden rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg)]">
        <div
          className="flex h-10 items-center justify-between border-b border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3"
          draggable={!readOnly}
          onDragStart={() => setDragIndex(index)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={() => {
            if (dragIndex !== null) reorder(dragIndex, index);
            setDragIndex(null);
          }}
        >
          <div className="flex min-w-0 items-center gap-2"><HolderOutlined className="text-[var(--color-text-4)]" /><span className="truncate text-sm font-medium text-[var(--color-text-1)]">{t('workflowOrchestration.editor.fieldNumber', '字段 {number}', { number: index + 1 })}</span><Tag bordered={false} color={required.has(key) ? 'blue' : 'default'}>{required.has(key) ? t('workflowOrchestration.editor.required', '必填') : t('workflowOrchestration.editor.optional', '选填')}</Tag></div>
          {!readOnly ? <WorkflowPermission operation="Edit"><Button type="text" danger size="small" aria-label={t('workflowOrchestration.editor.deleteField', '删除字段 {number}', { number: index + 1 })} icon={<DeleteOutlined />} onClick={() => onChange({ ...value, properties: Object.fromEntries(properties.filter(([item]) => item !== key)), required: [...required].filter((item) => item !== key) })} /></WorkflowPermission> : null}
        </div>
        <div className="grid grid-cols-2 gap-4 p-4">
          <Form.Item className="mb-0" label={t('workflowOrchestration.editor.displayName', '显示名称')}><Input disabled={readOnly} value={String(schema.title || '')} placeholder={t('workflowOrchestration.editor.hostExample', '例如：目标主机')} onChange={(event) => setSchema({ ...schema, title: event.target.value })} /></Form.Item>
          <FieldKeyEditor fieldKey={key} readOnly={readOnly} usedKeys={usedKeys} onChange={(nextKey) => changeField(key, nextKey, schema)} />
          <Form.Item className="mb-0" label={t('workflowOrchestration.editor.fieldType', '字段类型')}><Select disabled={readOnly} value={widget} options={fieldTypeOptions} onChange={(next: FormFieldWidget) => {
            const nextSchema = changeFormFieldWidget(schema, next);
            if (next === 'target-selector' && nextSchema['x-target-binding']) {
              const minCount = required.has(key) ? 1 : 0;
              setSchema({
                ...nextSchema,
                minItems: minCount,
                'x-target-binding': { ...nextSchema['x-target-binding'], minCount },
              });
              return;
            }
            setSchema(nextSchema);
          }} /></Form.Item>
          <div className="flex min-h-14 flex-col items-start gap-2"><div className="text-sm text-[var(--color-text-1)]">{t('workflowOrchestration.editor.requiredField', '必填字段')}</div><Switch aria-label={t('workflowOrchestration.editor.fieldRequired', '字段 {number} 必填', { number: index + 1 })} disabled={readOnly} checked={required.has(key)} onChange={(checked) => {
            const nextRequired = checked ? [...required, key] : [...required].filter((item) => item !== key);
            if (widget === 'target-selector' && schema['x-target-binding']) {
              const minCount = checked ? 1 : 0;
              const binding = { ...schema['x-target-binding'], minCount };
              onChange({
                ...value,
                required: nextRequired,
                properties: {
                  ...(value.properties || {}),
                  [key]: { ...schema, minItems: minCount, 'x-target-binding': binding },
                },
              });
              return;
            }
            onChange({ ...value, required: nextRequired });
          }} /></div>
          {['select', 'radio', 'multiselect'].includes(widget) ? <Form.Item className="col-span-2 mb-0" label={t('workflowOrchestration.editor.options', '选项')} tooltip={t('workflowOrchestration.editor.optionsHint', '输入一个选项后按 Enter 添加')}><Select mode="tags" open={false} suffixIcon={null} disabled={readOnly} value={(widget === 'multiselect' ? schema.items?.enum : schema.enum)?.map(String) || []} onChange={(values) => setSchema(widget === 'multiselect' ? { ...schema, items: { type: 'string', enum: values } } : { ...schema, enum: values })} /></Form.Item> : null}
          {widget === 'target-selector' ? <TargetSelectorOptions schema={schema} disabled={readOnly} required={required.has(key)} onChange={setSchema} /> : null}
          {widget === 'file-upload' ? <FileUploadOptions schema={schema} disabled={readOnly} onChange={setSchema} /> : null}
        </div>
      </section>;
    })}
    {!readOnly ? <WorkflowPermission operation="Edit" className="block"><Button block type="dashed" icon={<PlusOutlined />} onClick={() => {
      const key = uniqueFieldKey(new Set(properties.map(([item]) => item)));
      onChange({ ...value, type: 'object', properties: { ...(value.properties || {}), [key]: createFormFieldSchema('input', newFieldTitle) }, required: value.required || [], additionalProperties: false });
    }}>{addFieldLabel}</Button></WorkflowPermission> : null}
  </div>;
}
