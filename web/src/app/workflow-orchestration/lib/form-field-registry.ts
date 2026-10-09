import type {
  FormFieldWidget,
  JsonSchema,
} from './types';

function shared(schema: JsonSchema, title: string): JsonSchema {
  return {
    title: schema.title || title,
    ...(schema.description ? { description: schema.description } : {}),
    ...(schema.sensitive ? { sensitive: true } : {}),
  };
}

export function createFormFieldSchema(
  widget: FormFieldWidget,
  title: string,
): JsonSchema {
  const base = { title, 'x-widget': widget } satisfies JsonSchema;
  if (widget === 'target-selector') {
    return {
      ...base,
      type: 'array',
      items: { type: 'string', pattern: '^(node:[^:]+|manual:[0-9]+)$' },
      minItems: 1,
      maxItems: 100,
      uniqueItems: true,
      'x-target-binding': {
        mode: 'runtime',
        allowedSources: ['node_mgmt', 'job_mgmt'],
        allowedOperatingSystems: ['linux', 'windows'],
        minCount: 1,
        maxCount: 100,
      },
    };
  }
  if (widget === 'file-upload') {
    return {
      ...base,
      type: 'object',
      properties: {
        kind: { type: 'string', enum: ['uploaded'] },
        name: { type: 'string', maxLength: 255 },
        format: { type: 'string', enum: ['docx', 'xlsx'] },
        token: { type: 'string', maxLength: 8192 },
        size: { type: 'integer', minimum: 1, maximum: 5 * 1024 * 1024 },
      },
      required: ['kind', 'name', 'format'],
      additionalProperties: false,
      'x-file-options': {
        accept: ['docx', 'xlsx'],
        maxSizeMiB: 5,
        maxCount: 1,
        sourceModes: ['upload'],
      },
    };
  }
  if (widget === 'number') return { ...base, type: 'number' };
  if (widget === 'switch') return { ...base, type: 'boolean', default: false };
  if (widget === 'multiselect') return { ...base, type: 'array', items: { type: 'string', enum: [] }, uniqueItems: true };
  if (widget === 'select' || widget === 'radio') return { ...base, type: 'string', enum: [] };
  if (widget === 'json' || widget === 'key-value') return { ...base, type: 'object', additionalProperties: true };
  if (widget === 'tags') return { ...base, type: 'array', items: { type: 'string' } };
  return { ...base, type: 'string' };
}

export function formFieldWidget(schema: JsonSchema): FormFieldWidget {
  if (schema['x-widget']) return schema['x-widget'];
  if (schema.type === 'number' || schema.type === 'integer') return 'number';
  if (schema.type === 'boolean') return 'switch';
  if (schema.type === 'array' && schema.items?.enum) return 'multiselect';
  if (schema.enum) return 'select';
  if (schema.type === 'object') return 'json';
  return 'input';
}

export function changeFormFieldWidget(schema: JsonSchema, widget: FormFieldWidget): JsonSchema {
  return {
    ...createFormFieldSchema(widget, schema.title || '新字段'),
    ...shared(schema, '新字段'),
  };
}
