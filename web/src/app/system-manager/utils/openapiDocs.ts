import type {
  OpenAPIDocsCatalog,
  OpenAPIFieldSpec,
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
  requestSchema: Record<string, OpenAPIFieldSpec>;
  searchText: string;
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
        requestSchema: {},
        searchText: asSearchText([service.kind, service.name, path, service.doc_url]),
      },
    ];
  }

  return (service.endpoints || []).map((endpoint) => {
    const path = gatewayUrl(endpoint.path);
    const fieldNames = Object.keys(endpoint.request_schema || {});
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
      requestSchema: endpoint.request_schema || {},
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

export const generateSamplePayload = (
  schema: Record<string, OpenAPIFieldSpec>
): Record<string, unknown> | null => {
  const keys = Object.keys(schema);
  if (!keys.length) return null;
  const payload: Record<string, unknown> = {};

  for (const [key, spec] of Object.entries(schema)) {
    if (spec.default !== undefined) {
      payload[key] = spec.default;
    } else if (Array.isArray(spec.choices) && spec.choices.length > 0) {
      payload[key] = spec.choices[0];
    } else {
      const type = (spec.type || '').toLowerCase();
      if (type.includes('int') || type.includes('number') || type.includes('float')) {
        payload[key] = spec.min_value ?? 1;
      } else if (type.includes('bool')) {
        payload[key] = true;
      } else if (type.includes('list') || type.includes('array')) {
        payload[key] = [];
      } else if (type.includes('dict') || type.includes('object') || type.includes('json')) {
        payload[key] = {};
      } else {
        payload[key] = key.endsWith('_id') ? 1 : 'string';
      }
    }
  }
  return payload;
};

export const generateCurlCommand = (row: OpenAPIDocRow): string => {
  if (row.kind === 'external' || !row.method) {
    return '';
  }
  const method = row.method.toUpperCase();
  const url = row.path;
  const isBodyMethod = ['POST', 'PUT', 'PATCH'].includes(method);
  const sample = isBodyMethod ? generateSamplePayload(row.requestSchema) : null;

  const lines = [
    `curl -X ${method} "${url}"`,
    `  -H "Authorization: Bearer <API_TOKEN>"`,
  ];

  if (sample && Object.keys(sample).length > 0) {
    lines.push(`  -H "Content-Type: application/json"`);
    lines.push(`  -d '${JSON.stringify(sample, null, 2)}'`);
  } else if (!isBodyMethod && row.requestSchema && Object.keys(row.requestSchema).length > 0) {
    const sampleParams = generateSamplePayload(row.requestSchema);
    if (sampleParams) {
      const queryStr = Object.entries(sampleParams)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
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
    return choices.map((item) => String(item)).join(', ');
  }
  return String(choices);
};

export const formatChoicesDisplay = (choices: unknown): string =>
  formatChoices(choices) || '--';

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
  spec: Pick<OpenAPIFieldSpec, 'min_value' | 'max_value'>,
): boolean => spec.min_value != null || spec.max_value != null;

export const formatFieldRange = (
  minValue?: number | null,
  maxValue?: number | null,
): string => {
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
