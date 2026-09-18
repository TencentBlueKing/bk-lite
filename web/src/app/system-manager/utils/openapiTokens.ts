import type {
  OpenApiTokenCreateFormValues,
  OpenApiTokenExpiryStatus,
  OpenApiTokenScope,
  OpenApiTokenServiceCatalog,
  PersonalOpenApiTokenRow,
  SystemOpenApiTokenRow,
} from '@/app/system-manager/components/openapi-tokens/types';
import type {
  OpenAPIDocsCatalog,
  SystemApiTokenListItem,
  UserApiSecretListItem,
} from '@/app/system-manager/api/settings';

export interface MenuTreeNode {
  name: string;
  display_name?: string;
  operation?: string[];
  children?: MenuTreeNode[];
}

export const asList = <T>(data: T[] | { items?: T[] } | null | undefined): T[] => {
  if (Array.isArray(data)) {
    return data;
  }
  if (data && Array.isArray(data.items)) {
    return data.items;
  }
  return [];
};

export const expiryStatus = (
  expiresAt?: string | null,
): OpenApiTokenExpiryStatus => {
  if (!expiresAt) {
    return 'never';
  }
  return Date.parse(expiresAt) <= Date.now() ? 'expired' : 'active';
};

export const SCOPE_ALL: OpenApiTokenScope = { mode: 'all' };

export const isOpenApiTokenScope = (scope: unknown): scope is OpenApiTokenScope => {
  if (!scope || typeof scope !== 'object' || Array.isArray(scope)) {
    return false;
  }
  const mode = (scope as OpenApiTokenScope).mode;
  if (mode === 'all') {
    return !('endpoints' in scope);
  }
  const endpoints = (scope as OpenApiTokenScope).endpoints;
  return mode === 'allowlist' && Array.isArray(endpoints) && endpoints.length > 0;
};

export const normalizeClientScope = (scope?: unknown): OpenApiTokenScope => (
  isOpenApiTokenScope(scope) ? scope : SCOPE_ALL
);

export const docsToCatalog = (
  docs?: OpenAPIDocsCatalog | null,
): OpenApiTokenServiceCatalog[] => (
  (docs?.services || []).flatMap((service): OpenApiTokenServiceCatalog[] => {
    if (service.kind === 'external') {
      return [{
        name: service.name,
        kind: 'external',
        label: service.name,
        endpoints: [{
          key: `EXTERNAL ${service.name}`,
          label: service.name,
        }],
      }];
    }
    const endpoints = (service.endpoints || []).map((endpoint) => ({
      key: `${endpoint.method} ${endpoint.path}`,
      label: endpoint.summary || endpoint.path,
      method: endpoint.method,
      path: endpoint.path,
    }));
    if (!endpoints.length) {
      return [];
    }
    return [{
      name: service.name,
      kind: 'internal',
      label: service.name,
      endpoints,
    }];
  })
);

export const formValuesToWritePayload = (values: OpenApiTokenCreateFormValues) => {
  const scope: OpenApiTokenScope = values.scopeMode === 'allowlist'
    ? {
      mode: 'allowlist',
      endpoints: Array.from(new Set(values.scopeEndpoints || [])),
    }
    : SCOPE_ALL;
  return {
    name: values.name || '',
    expires_at: toExpiresAtIso(values.expiresAt),
    scope,
  };
};

export const formatScopeLabel = (
  scope: OpenApiTokenScope | null | undefined,
  allLabel: string,
): string => {
  const normalized = normalizeClientScope(scope);
  if (normalized.mode === 'all') {
    return allLabel;
  }
  return (normalized.endpoints || []).join(', ') || '—';
};

export const toExpiresAtIso = (value: unknown): string | null => {
  if (!value) {
    return null;
  }
  if (typeof value === 'string') {
    return value;
  }
  if (
    typeof value === 'object'
    && value !== null
    && 'toISOString' in value
    && typeof (value as { toISOString: () => string }).toISOString === 'function'
  ) {
    return (value as { toISOString: () => string }).toISOString();
  }
  return null;
};

export const toPersonalRow = (item: UserApiSecretListItem): PersonalOpenApiTokenRow => ({
  id: item.id,
  name: item.name || '',
  preview: item.api_secret_preview,
  teamName: item.team_name || String(item.team),
  createdAt: item.created_at,
  expiresAt: item.expires_at ?? null,
  status: expiryStatus(item.expires_at),
  scope: normalizeClientScope(item.scope),
});

export const toSystemRow = (item: SystemApiTokenListItem): SystemOpenApiTokenRow => ({
  id: item.id,
  name: item.name || '',
  systemId: item.system_id,
  preview: item.api_secret_preview,
  createdAt: item.created_at,
  createdBy: item.created_by || '',
  expiresAt: item.expires_at ?? null,
  enabled: item.enabled,
  status: expiryStatus(item.expires_at),
  scope: normalizeClientScope(item.scope),
});

export const findMenuOperations = (
  menus: MenuTreeNode[] | undefined,
  menuName: string,
): string[] => {
  const walk = (nodes: MenuTreeNode[] | undefined): string[] | null => {
    for (const menu of nodes || []) {
      if (menu.name === menuName) {
        return menu.operation || [];
      }
      const nested = walk(menu.children);
      if (nested !== null) {
        return nested;
      }
    }
    return null;
  };
  return walk(menus) ?? [];
};

export const canManageByOperations = (operations: string[]): boolean => (
  operations.includes('Add')
  || operations.includes('Edit')
  || operations.includes('Delete')
);

export const isDuplicateTokenNameError = (error: unknown): boolean => {
  const message = error instanceof Error ? error.message : String(error ?? '');
  return /name already exists/i.test(message);
};
