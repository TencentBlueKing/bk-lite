import type { AuthSource } from '@/app/system-manager/types/security';

export type SourceType = 'wechat' | 'bk_login' | 'bk_lite';

export interface WeChatFormValues {
  name: string;
  app_id: string;
  app_secret: string;
  enabled: boolean;
  redirect_uri: string;
  callback_url: string;
}

export interface BkLoginFormValues {
  name: string;
  source_type: string;
  enabled: boolean;
  namespace: string;
  root_group: string;
  app_id: string;
  app_token: string;
  bk_url: string;
  sync: boolean;
  sync_time: string;
  default_roles: number[];
}

export interface BkLiteFormValues {
  name: string;
  source_type: string;
  enabled: boolean;
  namespace: string;
  root_group: string;
  domain: string;
  sync: boolean;
  sync_time: string;
  default_roles: number[];
}

export type AuthSourceFormValues = WeChatFormValues | BkLoginFormValues | BkLiteFormValues;

export interface CreateAuthSourcePayload {
  name: string;
  source_type: string;
  enabled?: boolean;
  other_config: {
    namespace?: string;
    root_group?: string;
    domain?: string;
    app_id?: string;
    app_token?: string;
    bk_url?: string;
    default_roles?: number[];
    sync?: boolean;
    sync_time?: string;
  };
}

export function buildUpdatePayload(
  sourceType: SourceType,
  values: AuthSourceFormValues,
  selectedRoles: number[]
): Partial<AuthSource> {
  if (sourceType === 'wechat') {
    const v = values as WeChatFormValues;
    return {
      name: v.name,
      app_id: v.app_id,
      app_secret: v.app_secret,
      enabled: v.enabled,
      other_config: {
        redirect_uri: v.redirect_uri,
        callback_url: v.callback_url,
      },
    };
  }

  if (sourceType === 'bk_login') {
    const v = values as BkLoginFormValues;
    return {
      name: v.name,
      source_type: v.source_type,
      enabled: v.enabled,
      other_config: {
        namespace: v.namespace,
        root_group: v.root_group,
        app_id: v.app_id,
        app_token: v.app_token,
        bk_url: v.bk_url,
        default_roles: selectedRoles,
        sync: v.sync,
        sync_time: v.sync_time,
      },
    };
  }

  const v = values as BkLiteFormValues;
  return {
    name: v.name,
    source_type: v.source_type,
    enabled: v.enabled,
    other_config: {
      namespace: v.namespace,
      root_group: v.root_group,
      domain: v.domain,
      default_roles: selectedRoles,
      sync: v.sync,
      sync_time: v.sync_time,
    },
  };
}

export function buildCreatePayload(
  values: BkLoginFormValues | BkLiteFormValues,
  selectedRoles: number[]
): CreateAuthSourcePayload {
  if (values.source_type === 'bk_login') {
    const v = values as BkLoginFormValues;
    return {
      name: v.name,
      source_type: v.source_type,
      enabled: v.enabled,
      other_config: {
        namespace: v.namespace,
        root_group: v.root_group,
        app_id: v.app_id,
        app_token: v.app_token,
        bk_url: v.bk_url,
        default_roles: selectedRoles,
        sync: v.sync,
        sync_time: v.sync_time,
      },
    };
  }

  const v = values as BkLiteFormValues;
  return {
    name: v.name,
    source_type: v.source_type,
    enabled: v.enabled,
    other_config: {
      namespace: v.namespace,
      root_group: v.root_group,
      domain: v.domain,
      default_roles: selectedRoles,
      sync: v.sync,
      sync_time: v.sync_time,
    },
  };
}

export function populateFormFromSource(source: AuthSource): Record<string, any> {
  if (source.source_type === 'wechat') {
    return {
      name: source.name,
      app_id: source.app_id,
      app_secret: source.app_secret,
      enabled: source.enabled,
      redirect_uri: source.other_config.redirect_uri,
      callback_url: source.other_config.callback_url,
    };
  }

  if (source.source_type === 'bk_login') {
    const { other_config } = source;
    return {
      name: source.name,
      source_type: source.source_type,
      namespace: other_config?.namespace,
      root_group: other_config?.root_group,
      app_id: other_config?.app_id,
      app_token: other_config?.app_token,
      bk_url: other_config?.bk_url,
      sync: other_config?.sync || false,
      sync_time: other_config?.sync_time || '00:00',
      enabled: source.enabled,
      default_roles: other_config?.default_roles || [],
    };
  }

  const { other_config } = source;
  return {
    name: source.name,
    source_type: source.source_type,
    namespace: other_config?.namespace,
    root_group: other_config?.root_group,
    domain: other_config?.domain,
    sync: other_config?.sync || false,
    sync_time: other_config?.sync_time || '00:00',
    enabled: source.enabled,
    default_roles: other_config?.default_roles || [],
  };
}

export function getDefaultRolesFromSource(source: AuthSource): number[] {
  return source.other_config?.default_roles || [];
}

export function getFieldsToResetOnTypeChange(newSourceType: string): string[] {
  if (newSourceType === 'bk_login') {
    return ['namespace', 'domain', 'sync', 'sync_time'];
  }
  return ['app_id', 'app_token', 'bk_url'];
}
