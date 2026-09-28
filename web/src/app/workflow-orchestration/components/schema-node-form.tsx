'use client';

import { CloseCircleOutlined, DeleteOutlined, LinkOutlined, PlusOutlined } from '@ant-design/icons';
import { Alert, Button, Collapse, Form, Input, InputNumber, Select, Switch } from 'antd';
import { useEffect, useState, type DragEvent, type ReactNode } from 'react';

import CodeEditor from '@/components/code-editor';
import { useTranslation } from '@/utils/i18n';

import { JsonValueInput } from './json-value-input';
import {
  compileNodeInputBinding,
  compatibleDataReferences,
  parseNodeInputBinding,
  type DataReferenceOption,
} from '../lib/data-references';
import type { JsonSchema } from '../lib/types';
import { WorkflowPermission } from './workflow-permission';

interface Props {
  schema?: JsonSchema;
  uiSchema?: Record<string, unknown>;
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  references?: DataReferenceOption[];
  fieldActions?: Record<string, ReactNode>;
}

export const WORKFLOW_REFERENCE_MIME = 'application/x-bklite-workflow-reference';

function defaultLiteral(schema: JsonSchema): unknown {
  if ('default' in schema) return schema.default;
  if (schema.type === 'boolean') return false;
  if (schema.type === 'array') return [];
  if (schema.type === 'object') return {};
  return undefined;
}

interface CapabilityProfileUi {
  key: string;
  version: string;
  name: string;
  description: string;
  input_schema: JsonSchema;
}

interface CapabilitySelectorUi {
  kind: string;
  field: string;
  profiles: CapabilityProfileUi[];
  active_when?: Record<string, unknown[]>;
}

function capabilitySelector(uiSchema?: Record<string, unknown>): CapabilitySelectorUi | undefined {
  const candidate = uiSchema?.capability_selector;
  if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) return undefined;
  const value = candidate as Partial<CapabilitySelectorUi>;
  if (typeof value.field !== 'string' || !Array.isArray(value.profiles)) return undefined;
  return value as CapabilitySelectorUi;
}

export function resolveSchemaForNodeInput(
  schema: JsonSchema | undefined,
  uiSchema: Record<string, unknown> | undefined,
  value: Record<string, unknown>,
): JsonSchema {
  const base = schema || {};
  const selector = capabilitySelector(uiSchema);
  if (!selector) return base;
  if (selector.active_when && Object.entries(selector.active_when).some(([key, allowed]) => !allowed.includes(value[key] ?? base.properties?.[key]?.default))) return base;
  const selectorSchema = base.properties?.[selector.field];
  const selected = value[selector.field] ?? selectorSchema?.default;
  const profile = selector.profiles.find((item) => item.key === selected);
  if (!profile) return base;
  return {
    ...base,
    properties: { ...(base.properties || {}), ...(profile.input_schema.properties || {}) },
    required: [...new Set([...(base.required || []), ...(profile.input_schema.required || [])])],
    additionalProperties: false,
  };
}

export function defaultNodeInputValues(
  schema: JsonSchema | undefined,
  uiSchema: Record<string, unknown> | undefined,
): Record<string, unknown> {
  const selector = capabilitySelector(uiSchema);
  const baseDefaults = Object.fromEntries(Object.entries(schema?.properties || {}).flatMap(([key, field]) => (
    field.default === undefined ? [] : [[key, field.default]]
  )));
  const selected = selector ? baseDefaults[selector.field] : undefined;
  const effective = resolveSchemaForNodeInput(schema, uiSchema, baseDefaults);
  const profileDefaults = Object.fromEntries(Object.entries(effective.properties || {}).flatMap(([key, field]) => (
    field.default === undefined ? [] : [[key, field.default]]
  )));
  return { ...baseDefaults, ...profileDefaults, ...(selector && selected !== undefined ? { [selector.field]: selected } : {}) };
}

function KeyValueField({ schema, value, references, onChange }: { schema: JsonSchema; value: unknown; references: DataReferenceOption[]; onChange: (value: unknown) => void }) {
  const { t } = useTranslation();
  const objectValue = value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
  const entries = Object.entries(objectValue);
  const valueSchema = typeof schema.additionalProperties === 'object' ? schema.additionalProperties : { jsonEditorAllowed: true };
  const rename = (oldKey: string, nextKey: string) => {
    if (!nextKey || (nextKey !== oldKey && Object.hasOwn(objectValue, nextKey))) return;
    onChange(Object.fromEntries(entries.map(([key, item]) => [key === oldKey ? nextKey : key, item])));
  };
  const remove = (removedKey: string) => onChange(Object.fromEntries(entries.filter(([key]) => key !== removedKey)));
  const add = () => {
    if (schema.maxProperties && entries.length >= schema.maxProperties) return;
    let key = 'field';
    let suffix = 2;
    while (Object.hasOwn(objectValue, key)) key = `field_${suffix++}`;
    onChange({ ...objectValue, [key]: '' });
  };
  return <div className="flex flex-col gap-3">
    {entries.map(([key, item], index) => <section key={index} className="rounded-md border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-3">
      <div className="mb-3 flex items-center gap-2">
        <Input aria-label={t('workflowOrchestration.editor.mappingKey', '映射字段名')} value={key} onChange={(event) => rename(key, event.target.value.trim())} />
        <WorkflowPermission operation="Edit"><Button type="text" danger aria-label={t('workflowOrchestration.editor.deleteMappingField', '删除映射字段 {number}', { number: index + 1 })} icon={<DeleteOutlined />} onClick={() => remove(key)} /></WorkflowPermission>
      </div>
      <BindingEditor schema={valueSchema} value={item} references={references} onChange={(next) => onChange({ ...objectValue, [key]: next })} />
    </section>)}
    <WorkflowPermission operation="Edit" className="block"><Button type="dashed" icon={<PlusOutlined />} disabled={Boolean(schema.maxProperties && entries.length >= schema.maxProperties)} onClick={add}>
      {t('workflowOrchestration.editor.addMappingField', '添加映射字段')}
    </Button></WorkflowPermission>
  </div>;
}

function LiteralField({
  schema,
  value,
  references,
  valueLabels,
  onChange,
}: {
  schema: JsonSchema;
  value: unknown;
  references: DataReferenceOption[];
  valueLabels?: Record<string, string>;
  onChange: (value: unknown) => void;
}) {
  const { t } = useTranslation();
  if (schema['x-widget'] === 'textarea') return <Input.TextArea rows={schema['x-rows'] || 4} value={String(value ?? '')} onChange={(event) => onChange(event.target.value)} />;
  if (schema['x-widget'] === 'code') {
    return <CodeEditor
      aria-label={schema.title}
      className="overflow-hidden rounded-md border border-[var(--color-border-1)]"
      height="320px"
      headerOptions={{ copy: true, fullscreen: true }}
      mode={schema['x-code-language'] || 'text'}
      setOptions={{ showPrintMargin: false, useWorker: false, tabSize: 2, fontSize: 14 }}
      theme="monokai"
      value={String(value ?? '')}
      width="100%"
      onChange={(next: string) => onChange(next)}
    />;
  }
  if (schema['x-widget'] === 'json') {
    return <JsonValueInput expectedType={schema.type === 'object' || schema.type === 'array' ? schema.type : 'any'} rows={schema['x-rows'] || 12} value={value} onChange={onChange} />;
  }
  if (schema.enum) {
    return <Select className="w-full" allowClear value={value as string | number | undefined} options={schema.enum.map((item) => ({ value: item as string | number, label: schema['x-enum-labels']?.[String(item)] || String(item) }))} onChange={onChange} />;
  }
  if (schema.type === 'boolean') return <Switch className="self-start" checked={Boolean(value)} onChange={onChange} />;
  if (schema.type === 'integer' || schema.type === 'number') {
    return <InputNumber className="w-full" min={schema.minimum} max={schema.maximum} value={typeof value === 'number' ? value : undefined} onChange={onChange} />;
  }
  if (schema.type === 'array' && schema.items && !['object', 'array'].includes(String(schema.items.type))) {
    const selected = Array.isArray(value) ? value.map(String) : [];
    const enumOptions = schema.items.enum?.map((item) => ({
      value: String(item),
      label: schema.items?.['x-enum-labels']?.[String(item)] || String(item),
    })) || [];
    const labelOptions = selected
      .filter((item) => valueLabels?.[item])
      .map((item) => ({ value: item, label: valueLabels![item] }));
    const options = [...enumOptions, ...labelOptions.filter((item) => !enumOptions.some((option) => option.value === item.value))];
    return <Select
      mode={schema.items.enum ? 'multiple' : 'tags'}
      className="w-full"
      value={selected}
      options={options}
      optionFilterProp="label"
      placeholder={schema.items.enum ? t('workflowOrchestration.editor.selectItems', '请选择') : t('workflowOrchestration.editor.enterAndPressReturn', '输入后按回车添加')}
      onChange={onChange}
    />;
  }
  if (schema.type === 'object' && schema['x-widget'] === 'key-value') {
    return <KeyValueField schema={schema} value={value} references={references} onChange={onChange} />;
  }
  if (schema.type === 'object' && schema.properties) {
    const objectValue = value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
    return (
      <div className="flex flex-col gap-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-3">
        {Object.entries(schema.properties).map(([key, child]) => (
          <div key={key}>
            <div className="mb-1.5 text-xs font-medium text-[var(--color-text-2)]">{child.title || key}</div>
            <BindingEditor schema={child} value={objectValue[key]} references={references} onChange={(next) => onChange({ ...objectValue, [key]: next })} />
          </div>
        ))}
      </div>
    );
  }
  if (schema.type === 'object' || schema.type === 'array' || schema.type == null) {
    return (
      <div className="flex flex-col gap-3">
        {!schema.jsonEditorAllowed && <Alert type="info" showIcon message={t('workflowOrchestration.editor.structureUnavailable', '该结构没有可生成表单的子字段')} description={t('workflowOrchestration.editor.structureUnavailableHint', '请从左侧拖入类型兼容的字段；原子声明 jsonEditorAllowed 后才开放结构化 JSON 固定值。')} />}
        <JsonValueInput
          disabled={!schema.jsonEditorAllowed}
          expectedType={schema.type === 'object' || schema.type === 'array' ? schema.type : 'any'}
          rows={4}
          value={value}
          onChange={onChange}
        />
      </div>
    );
  }
  return (
    <Input
      className="w-full"
      value={String(value ?? '')}
      placeholder={typeof schema['x-placeholder'] === 'string' ? schema['x-placeholder'] : undefined}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

function BindingEditor({
  schema: field,
  value,
  references,
  referenceOnly = false,
  disabled = false,
  valueLabels,
  onChange,
}: {
  schema: JsonSchema;
  value: unknown;
  references: DataReferenceOption[];
  referenceOnly?: boolean;
  disabled?: boolean;
  valueLabels?: Record<string, string>;
  onChange: (value: unknown) => void;
}) {
  const { t } = useTranslation();
  const binding = parseNodeInputBinding(value);
  const compatibleReferences = compatibleDataReferences(references, field);
  const incomingLiteral = binding.kind === 'template' ? binding.template : binding.kind === 'literal' ? binding.value : undefined;
  const incomingReference = binding.kind === 'reference' ? binding.expression : undefined;
  const [literalDraft, setLiteralDraft] = useState<unknown>(incomingLiteral);
  const [isDragOver, setIsDragOver] = useState(false);
  useEffect(() => {
    const next = parseNodeInputBinding(value);
    if (next.kind !== 'reference') setLiteralDraft(next.kind === 'template' ? next.template : next.value);
  }, [value]);
  const hasBrokenReference = Boolean(incomingReference) && !compatibleReferences.some((item) => item.value === incomingReference);
  const acceptDrop = (event: DragEvent<HTMLDivElement>) => {
    const expression = event.dataTransfer.getData(WORKFLOW_REFERENCE_MIME);
    setIsDragOver(false);
    if (!compatibleReferences.some((item) => item.value === expression)) return;
    event.preventDefault();
    onChange(compileNodeInputBinding({ kind: 'reference', expression }));
  };
  const allowDrop = (event: DragEvent<HTMLDivElement>) => {
    const types = Array.from(event.dataTransfer.types || []);
    const expression = event.dataTransfer.getData(WORKFLOW_REFERENCE_MIME);
    if (types.includes(WORKFLOW_REFERENCE_MIME) || compatibleReferences.some((item) => item.value === expression)) {
      event.preventDefault();
      event.dataTransfer.dropEffect = 'copy';
      setIsDragOver(true);
    }
  };
  const dropSurface = (children: ReactNode) => (
    <div
      data-testid="workflow-reference-dropzone"
      className={`w-full rounded-md outline-none transition focus-within:ring-2 focus-within:ring-[var(--color-primary)]/15 ${isDragOver ? 'ring-2 ring-[var(--color-primary)]/35' : ''}`}
      onDragEnter={allowDrop}
      onDragLeave={() => setIsDragOver(false)}
      onDragOverCapture={allowDrop}
      onDropCapture={acceptDrop}
    >
      {children}
    </div>
  );

  if (field['x-binding'] === 'literal-only') {
    return <LiteralField schema={field} value={incomingLiteral ?? defaultLiteral(field)} references={references} valueLabels={valueLabels} onChange={(next) => onChange(compileNodeInputBinding({ kind: 'literal', value: next }))} />;
  }

  if (incomingReference) {
    return dropSurface(<Form.Item
      className="mb-0"
      validateStatus={hasBrokenReference ? 'error' : undefined}
      help={hasBrokenReference
        ? `${t('workflowOrchestration.editor.brokenReference', '失效引用')}：${t('workflowOrchestration.editor.brokenReferenceHint', '来源不存在、类型不兼容或并非所有到达路径都可用。该草稿可以保存，但修复前不能调试或发布。')}`
        : undefined}
    >
      <Input
        readOnly
        status={hasBrokenReference ? 'error' : undefined}
        prefix={<LinkOutlined className="text-[var(--color-primary)]" />}
        suffix={!disabled ? <WorkflowPermission operation="Edit"><Button type="text" size="small" aria-label={t('workflowOrchestration.editor.clearReference', '清除字段引用')} icon={<CloseCircleOutlined />} onClick={() => onChange(compileNodeInputBinding({ kind: 'literal', value: literalDraft ?? defaultLiteral(field) }))} /></WorkflowPermission> : undefined}
        value={incomingReference}
      />
    </Form.Item>);
  }

  if (referenceOnly) {
    return dropSurface(<Select
      className="w-full"
      showSearch
      allowClear
      optionFilterProp="label"
      disabled={disabled}
      placeholder={t('workflowOrchestration.editor.selectOrDropReference', '选择字段，或从左侧拖入')}
      options={compatibleReferences.map((item) => ({ value: item.value, label: item.label }))}
      onChange={(expression) => onChange(
        expression
          ? compileNodeInputBinding({ kind: 'reference', expression })
          : undefined,
      )}
    />);
  }

  return dropSurface(<LiteralField schema={field} value={literalDraft ?? defaultLiteral(field)} references={references} valueLabels={valueLabels} onChange={(next) => { setLiteralDraft(next); onChange(compileNodeInputBinding({ kind: 'literal', value: next })); }} />);
}

export function SchemaNodeField({
  schema,
  value,
  references = [],
  referenceOnly,
  disabled,
  valueLabels,
  onChange,
}: {
  schema: JsonSchema;
  value: unknown;
  references?: DataReferenceOption[];
  referenceOnly?: boolean;
  disabled?: boolean;
  valueLabels?: Record<string, string>;
  onChange: (value: unknown) => void;
}) {
  return <BindingEditor schema={schema} value={value} references={references} referenceOnly={referenceOnly} disabled={disabled} valueLabels={valueLabels} onChange={onChange} />;
}

export function SchemaNodeForm({ schema, uiSchema, value, onChange, references = [], fieldActions = {} }: Props) {
  const { t } = useTranslation();
  const effectiveSchema = resolveSchemaForNodeInput(schema, uiSchema, value);
  const selector = capabilitySelector(uiSchema);
  const isVisible = (key: string) => {
    const fieldUi = uiSchema?.[key];
    if (!fieldUi || typeof fieldUi !== 'object' || Array.isArray(fieldUi)) return true;
    const condition = (fieldUi as Record<string, unknown>)['ui:visibleWhen'];
    if (!condition || typeof condition !== 'object' || Array.isArray(condition)) return true;
    return Object.entries(condition as Record<string, unknown>).every(([source, allowed]) => Array.isArray(allowed) && allowed.includes(value[source]));
  };
  const properties = Object.entries(effectiveSchema.properties || {}).filter(([key]) => isVisible(key));
  if (properties.length === 0) {
    return <Alert type="info" showIcon message={t('workflowOrchestration.editor.noSchemaFields', '该原子没有可声明的 Schema 字段')} description={t('workflowOrchestration.editor.noSchemaFieldsHint', '请先在原子包中补充输入 Schema；普通节点不开放未约束的原始 JSON。')} />;
  }
  const setField = (key: string, next: unknown) => {
    if (selector?.field === key) {
      const profile = selector.profiles.find((item) => item.key === next);
      const retainedKeys = new Set([...(Object.keys(schema?.properties || {})), ...Object.keys(profile?.input_schema.properties || {})]);
      const retained = Object.fromEntries(Object.entries(value).filter(([field]) => retainedKeys.has(field)));
      const defaults = Object.fromEntries(Object.entries(profile?.input_schema.properties || {}).flatMap(([field, fieldSchema]) => (
        fieldSchema.default === undefined || retained[field] !== undefined ? [] : [[field, fieldSchema.default]]
      )));
      onChange({ ...retained, ...defaults, [key]: next });
      return;
    }
    onChange({ ...value, [key]: next });
  };
  const renderFields = (items: typeof properties) => items.map(([key, field]) => {
    const fieldUi = uiSchema?.[key];
    const ui = fieldUi && typeof fieldUi === 'object' && !Array.isArray(fieldUi) ? fieldUi as Record<string, unknown> : {};
    const uiWidget = typeof ui['ui:widget'] === 'string' ? ui['ui:widget'] as JsonSchema['x-widget'] : undefined;
    const codeLanguage = typeof ui['ui:language'] === 'string' ? ui['ui:language'] as JsonSchema['x-code-language'] : undefined;
    const bindingSchema: JsonSchema = {
      ...field,
      ...(uiWidget ? { 'x-widget': uiWidget } : {}),
      ...(codeLanguage ? { 'x-code-language': codeLanguage } : {}),
      ...(uiWidget === 'json' ? { jsonEditorAllowed: true } : {}),
    };
    const hint = String(ui['ui:help'] || field.description || '') || undefined;
    const editor = <BindingEditor schema={bindingSchema} value={value[key]} references={references} onChange={(next) => setField(key, next)} />;
    return <Form.Item className="mb-0" key={key} label={String(ui['ui:label'] || field.title || key)} required={effectiveSchema.required?.includes(key)} tooltip={hint}>
      {fieldActions[key] ? <div className="flex items-start gap-2"><div className="min-w-0 flex-1">{editor}</div><div className="shrink-0">{fieldActions[key]}</div></div> : editor}
    </Form.Item>;
  });
  const basic = properties.filter(([key]) => !(uiSchema?.[key] as Record<string, unknown> | undefined)?.['ui:advanced']);
  const advanced = properties.filter(([key]) => Boolean((uiSchema?.[key] as Record<string, unknown> | undefined)?.['ui:advanced']));
  return <Form className="flex flex-col gap-5" layout="vertical">
    {renderFields(basic)}
    {advanced.length ? <Collapse ghost items={[{ key: 'advanced', label: t('workflowOrchestration.editor.advancedSettings', '高级设置'), children: <div className="flex flex-col gap-5">{renderFields(advanced)}</div> }]} /> : null}
  </Form>;
}
