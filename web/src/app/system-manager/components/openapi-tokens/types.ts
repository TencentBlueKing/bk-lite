export type OpenApiTokenTab = 'personal' | 'system';

export type OpenApiTokenExpiryStatus = 'active' | 'expired' | 'never';

export type OpenApiTokenExpiryPreset = 'never' | '3m' | '1m' | 'custom';

export type OpenApiTokenScopeMode = 'all' | 'allowlist';

export interface OpenApiTokenScope {
  mode: OpenApiTokenScopeMode;
  endpoints?: string[];
}

export interface OpenApiTokenCatalogEndpoint {
  key: string;
  label: string;
  method?: string;
  path?: string;
}

export interface OpenApiTokenServiceCatalog {
  name: string;
  kind: 'internal' | 'external';
  label: string;
  endpoints: OpenApiTokenCatalogEndpoint[];
}

export interface PersonalOpenApiTokenRow {
  id: number;
  name: string;
  preview: string;
  teamName: string;
  createdAt: string;
  expiresAt: string | null;
  status: OpenApiTokenExpiryStatus;
  scope: OpenApiTokenScope | null;
}

export interface SystemOpenApiTokenRow {
  id: number;
  name: string;
  systemId: string;
  preview: string;
  createdAt: string;
  createdBy: string;
  expiresAt: string | null;
  enabled: boolean;
  status: OpenApiTokenExpiryStatus;
  scope: OpenApiTokenScope | null;
}

export interface OpenApiTokenCreateFormValues {
  name?: string;
  systemId?: string;
  expiryPreset?: OpenApiTokenExpiryPreset;
  expiresAt?: unknown;
  scopeMode?: OpenApiTokenScopeMode;
  scopeEndpoints?: string[];
}
