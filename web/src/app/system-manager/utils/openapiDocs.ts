import type {
  OpenAPIDocsCatalog,
  OpenAPIJsonSchema,
  OpenAPIService,
} from '@/app/system-manager/api/settings';

export const OPENAPI_GATEWAY_PREFIX = '/openapi/v1';

export const gatewayUrl = (path: string): string =>
  `${OPENAPI_GATEWAY_PREFIX}/${path.replace(/^\//, '')}`;

export interface OpenAPIDocRow {
  key: string;
  kind: 'internal' | 'external';
  service: string;
  method: string;
  path: string;
  summary: string;
  docUrl: string;
  inject: string;
  permission: string;
  requestSchema: OpenAPIJsonSchema;
  responseSchema: OpenAPIJsonSchema | null;
  searchText: string;
}

export interface OpenAPISchemaFieldRow {
  name: string;
  schema: OpenAPIJsonSchema;
  required: boolean;
  depth: number;
}

export interface OpenAPIFilterOptions {
  query?: string;
  service?: string;
  method?: string;
  kind?: string;
}

const asSearchText = (parts: Array<string | undefined | null>): string =>
  parts
    .filter((item): item is string => Boolean(item && item.trim()))
    .join(' ')
    .toLowerCase();

const flattenService = (service: OpenAPIService): OpenAPIDocRow[] => {
  if (service.kind === 'external') {
    const path = gatewayUrl(service.name);
    return [
      {
        key: `external:${service.name}`,
        kind: 'external',
        service: service.name,
        method: '',
        path,
        summary: '',
        docUrl: service.doc_url || '',
        inject: '',
        permission: '',
        requestSchema: { type: 'object', properties: {} },
        responseSchema: null,
        searchText: asSearchText([service.kind, service.name, path, service.doc_url]),
      },
    ];
  }

  return (service.endpoints || []).map((endpoint) => {
    const path = gatewayUrl(endpoint.path);
    const requestSchema = endpoint.request_schema || { type: 'object', properties: {} };
    const responseSchema = endpoint.response_schema ?? null;
    const fieldNames = [
      ...flattenSchemaFields(requestSchema),
      ...(responseSchema ? flattenSchemaFields(responseSchema) : []),
    ].map((field) => field.name);
    return {
      key: `internal:${endpoint.method}:${endpoint.path}`,
      kind: 'internal' as const,
      service: service.name,
      method: endpoint.method,
      path,
      summary: endpoint.summary || '',
      docUrl: '',
      inject: endpoint.inject || '',
      permission: endpoint.permission || '',
      requestSchema,
      responseSchema,
      searchText: asSearchText([
        service.kind,
        service.name,
        endpoint.method,
        path,
        endpoint.summary,
        endpoint.inject,
        endpoint.permission,
        ...fieldNames,
      ]),
    };
  });
};

export const flattenOpenApiCatalog = (catalog: OpenAPIDocsCatalog | undefined): OpenAPIDocRow[] =>
  (catalog?.services || []).flatMap(flattenService);

export const filterOpenApiRows = (
  rows: OpenAPIDocRow[],
  options: OpenAPIFilterOptions
): OpenAPIDocRow[] => {
  const needle = (options.query || '').trim().toLowerCase();
  const service = options.service;
  const method = options.method ? options.method.toUpperCase() : undefined;
  const kind = options.kind;

  return rows.filter((row) => {
    if (needle && !row.searchText.includes(needle)) {
      return false;
    }
    if (service && service !== 'all' && row.service !== service) {
      return false;
    }
    if (method && method !== 'ALL' && row.method.toUpperCase() !== method) {
      return false;
    }
    if (kind && kind !== 'all' && row.kind !== kind) {
      return false;
    }
    return true;
  });
};

const schemaTypes = (schema: OpenAPIJsonSchema): string[] => {
  const types = Array.isArray(schema.type) ? [...schema.type] : schema.type ? [schema.type] : [];
  if (schema.nullable && !types.includes('null')) {
    types.push('null');
  }
  return types;
};

export const formatSchemaType = (schema: OpenAPIJsonSchema): string => {
  const types = schemaTypes(schema);
  if (types.length) {
    return types
      .map((type) => {
        if (type !== 'array' || !schema.items) return type;
        return `array<${formatSchemaType(schema.items)}>`;
      })
      .join(' | ');
  }
  if (schema.properties) return 'object';
  if (schema.items) return `array<${formatSchemaType(schema.items)}>`;
  return 'any';
};

export const flattenSchemaFields = (
  schema: OpenAPIJsonSchema,
): OpenAPISchemaFieldRow[] => {
  const rows: OpenAPISchemaFieldRow[] = [];

  const visitProperties = (
    properties: Record<string, OpenAPIJsonSchema>,
    requiredNames: string[],
    prefix: string,
    depth: number,
  ) => {
    for (const [name, childSchema] of Object.entries(properties)) {
      const path = prefix ? `${prefix}.${name}` : name;
      rows.push({
        name: path,
        schema: childSchema,
        required: requiredNames.includes(name),
        depth,
      });

      if (childSchema.properties) {
        visitProperties(
          childSchema.properties,
          childSchema.required || [],
          path,
          depth + 1,
        );
      }
      if (childSchema.items?.properties) {
        visitProperties(
          childSchema.items.properties,
          childSchema.items.required || [],
          `${path}[]`,
          depth + 1,
        );
      }
    }
  };

  if (schema.properties) {
    visitProperties(schema.properties, schema.required || [], '', 0);
  } else {
    rows.push({ name: '$', schema, required: true, depth: 0 });
  }
  return rows;
};

const hasOwn = (value: object, key: string): boolean =>
  Object.prototype.hasOwnProperty.call(value, key);

export const generateSchemaExample = (schema: OpenAPIJsonSchema): unknown => {
  if (hasOwn(schema, 'default')) {
    return schema.default;
  }
  if (schema.enum?.length) {
    return schema.enum[0];
  }

  const type = schemaTypes(schema).find((item) => item !== 'null') || 'null';
  if (type === 'object' || schema.properties) {
    return Object.fromEntries(
      Object.entries(schema.properties || {}).map(([name, childSchema]) => [
        name,
        generateSchemaExample(childSchema),
      ]),
    );
  }
  if (type === 'array' || schema.items) {
    return schema.items ? [generateSchemaExample(schema.items)] : [];
  }
  if (type === 'integer' || type === 'number') {
    return schema.minimum ?? 1;
  }
  if (type === 'boolean') {
    return true;
  }
  if (type === 'null') {
    return null;
  }
  if (type === 'string' && schema.format === 'uuid') {
    return '00000000-0000-4000-8000-000000000000';
  }
  return 'string';
};

export const generateSamplePayload = (
  schema: OpenAPIJsonSchema,
): Record<string, unknown> | null => {
  const sample = generateSchemaExample(schema);
  if (!sample || Array.isArray(sample) || typeof sample !== 'object') {
    return null;
  }
  return Object.keys(sample).length ? sample as Record<string, unknown> : null;
};

export type OpenApiDocsTokenKind = 'personal' | 'system';

export const absoluteGatewayUrl = (path: string, origin = ''): string => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const normalizedOrigin = origin.replace(/\/+$/, '');
  return normalizedOrigin ? `${normalizedOrigin}${normalizedPath}` : normalizedPath;
};

export const generateCurlCommand = (
  row: OpenAPIDocRow,
  tokenKind: OpenApiDocsTokenKind = 'personal',
  origin = '',
): string => {
  if (row.kind === 'external' || !row.method) {
    return '';
  }
  const method = row.method.toUpperCase();
  const url = absoluteGatewayUrl(row.path, origin);
  const isBodyMethod = method !== 'GET';
  const sample = isBodyMethod ? generateSamplePayload(row.requestSchema) : null;

  const lines = [
    `curl -X ${method} "${url}"`,
    `  -H "Authorization: Bearer <TOKEN>"`,
  ];
  if (tokenKind === 'system') {
    lines.push('  -H "X-Bklite-Acting-User: <username>"');
    lines.push('  -H "X-Bklite-Acting-Team: <team_id>"');
  }

  if (sample && Object.keys(sample).length > 0) {
    lines.push(`  -H "Content-Type: application/json"`);
    lines.push(`  -d '${JSON.stringify(sample, null, 2)}'`);
  } else if (!isBodyMethod) {
    const sampleParams = generateSamplePayload(row.requestSchema);
    if (sampleParams) {
      const queryStr = Object.entries(sampleParams)
        .map(([k, v]) => {
          const value = typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v);
          return `${encodeURIComponent(k)}=${encodeURIComponent(value)}`;
        })
        .join('&');
      if (queryStr) {
        lines[0] = `curl -X ${method} "${url}?${queryStr}"`;
      }
    }
  }

  return lines.join(' \\\n');
};

export const formatChoices = (choices: unknown): string => {
  if (choices == null) {
    return '';
  }
  if (Array.isArray(choices)) {
    return choices
      .map((item) => typeof item === 'object' && item !== null ? JSON.stringify(item) : String(item))
      .join(', ');
  }
  return String(choices);
};

export const formatChoicesDisplay = (choices: unknown): string =>
  formatChoices(choices) || '--';

export const formatSchemaValue = (value: unknown): string => {
  if (value === undefined) return '';
  if (value === null) return 'null';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

export const schemaHasDefault = (schema: OpenAPIJsonSchema): boolean =>
  hasOwn(schema, 'default');

export const injectDescriptionKey = (inject: string): string => {
  switch (inject) {
    case 'team_list':
      return 'system.settings.openapiDocs.injectTeamList';
    case 'team_list_with_user':
      return 'system.settings.openapiDocs.injectTeamListWithUser';
    case 'user_info':
      return 'system.settings.openapiDocs.injectUserInfo';
    default:
      return 'system.settings.openapiDocs.injectUnknown';
  }
};

export const OPENAPI_SECRET_KEY_HREF = '/system-manager/settings/key';

const LINK_PLACEHOLDER = '{link}';

export const splitLinkPlaceholder = (template: string): [string, string] => {
  const index = template.indexOf(LINK_PLACEHOLDER);
  if (index < 0) {
    return [template, ''];
  }
  return [template.slice(0, index), template.slice(index + LINK_PLACEHOLDER.length)];
};

export const formatAuthHeaderPlainText = (
  desc: string,
  hint: string,
  linkLabel: string,
): string => `${desc} ${hint.split(LINK_PLACEHOLDER).join(linkLabel)}`.trim();

export const fieldHasRange = (
  schema: Pick<
    OpenAPIJsonSchema,
    'minimum' | 'maximum' | 'minLength' | 'maxLength' | 'minItems' | 'maxItems'
  >,
): boolean => [
  schema.minimum,
  schema.maximum,
  schema.minLength,
  schema.maxLength,
  schema.minItems,
  schema.maxItems,
].some((value) => value != null);

export const formatFieldRange = (
  schema: Pick<
    OpenAPIJsonSchema,
    'minimum' | 'maximum' | 'minLength' | 'maxLength' | 'minItems' | 'maxItems'
  >,
): string => {
  const minValue = schema.minimum ?? schema.minLength ?? schema.minItems;
  const maxValue = schema.maximum ?? schema.maxLength ?? schema.maxItems;
  const hasMin = minValue != null;
  const hasMax = maxValue != null;
  if (hasMin && hasMax) {
    return `${minValue} ~ ${maxValue}`;
  }
  if (hasMin) {
    return `≥ ${minValue}`;
  }
  if (hasMax) {
    return `≤ ${maxValue}`;
  }
  return '';
};
