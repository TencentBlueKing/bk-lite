import type {
  BusinessTemplate,
  ProviderManifest,
} from '@/app/system-manager/types/integration-center';
import type {
  AvailableInstance,
  UserSyncSource,
  UserSyncSourceBasicFormValues,
  UserSyncSourceCreateFormValues,
  UserSyncSourceStrategyFormValues,
} from '@/app/system-manager/types/user-sync';

export interface PaginatedResponse<T> {
  count: number;
  items: T[];
}

export function normalizeUserSyncList<T>(
  response: T[] | PaginatedResponse<T>
): T[] {
  if (Array.isArray(response)) return response;
  return (response as PaginatedResponse<T>).items ?? [];
}

export function buildSchedulePayload(
  values: UserSyncSourceStrategyFormValues
): UserSyncSource['schedule_config'] {
  switch (values.schedule_mode) {
    case 'daily':
      return { mode: 'daily', time: values.time ?? '', timezone: 'Asia/Shanghai' };
    case 'weekly':
      return {
        mode: 'weekly',
        time: values.time ?? '',
        weekdays: values.weekdays ?? [],
        timezone: 'Asia/Shanghai',
      };
    case 'interval_hours':
      return {
        mode: 'interval_hours',
        interval_hours: values.interval_hours ?? 1,
        timezone: 'Asia/Shanghai',
      };
    case 'disabled':
    default:
      return { mode: 'disabled', timezone: 'Asia/Shanghai' };
  }
}

export function parseScheduleConfig(
  scheduleConfig: UserSyncSource['schedule_config'] | null | undefined
): Pick<UserSyncSourceStrategyFormValues, 'schedule_mode' | 'time' | 'weekdays' | 'interval_hours'> {
  const mode = scheduleConfig?.mode ?? 'disabled';
  return {
    schedule_mode: mode,
    time: scheduleConfig?.time ?? '',
    weekdays: Array.isArray(scheduleConfig?.weekdays) ? scheduleConfig.weekdays : [],
    interval_hours: (scheduleConfig?.interval_hours as UserSyncSourceStrategyFormValues['interval_hours']) ?? 1,
  };
}

export function resolveUserSyncTemplate(
  instanceId: number | undefined,
  availableInstances: AvailableInstance[],
  providers: ProviderManifest[],
): BusinessTemplate | null {
  if (!instanceId) return null;
  const instance = availableInstances.find((item) => item.id === instanceId);
  if (!instance) return null;
  const provider = providers.find((item) => item.key === instance.provider_key);
  if (!provider) return null;
  const capability = provider.capabilities.find((item) => item.key === 'user_sync');
  if (!capability?.business_template) return null;
  return provider.business_templates?.[capability.business_template] ?? null;
}

export function getWriteOnlyKeys(template: BusinessTemplate | null): Set<string> {
  if (!template) return new Set();
  const keys = new Set<string>();
  for (const group of template.groups) {
    for (const field of group.fields) {
      if (field.write_only) keys.add(field.key);
    }
  }
  return keys;
}

export function getUserSyncTemplateField(template: BusinessTemplate | null, fieldKey: string) {
  if (!template) return null;
  for (const group of template.groups) {
    for (const field of group.fields) {
      if (field.key === fieldKey) return field;
    }
  }
  return null;
}

export function getDefaultDepartmentIdType(template: BusinessTemplate | null): string {
  const field = getUserSyncTemplateField(template, 'department_id_type');
  if (!field) return '';
  if (typeof field.default === 'string' && field.default) return field.default;
  const firstOption = field.options[0]?.value;
  return typeof firstOption === 'string' ? firstOption : '';
}

export function getRootDepartmentFieldKey(template: BusinessTemplate | null): string {
  if (!template) return 'root_department_id';
  for (const group of template.groups) {
    for (const field of group.fields) {
      if (field.key.startsWith('root_')) {
        return field.key;
      }
    }
  }
  return 'root_department_id';
}

export function getEffectiveRootDepartmentFieldKey(
  source: Pick<UserSyncSource, 'root_scope_field'> | null | undefined,
  template: BusinessTemplate | null,
): string {
  const rootScopeField = source?.root_scope_field?.trim();
  return rootScopeField || getRootDepartmentFieldKey(template);
}

function hasUsableFieldDefault(defaultValue: unknown): boolean {
  return defaultValue !== undefined && defaultValue !== null && defaultValue !== '';
}

export function getUserSyncBusinessConfigDefaults(
  template: BusinessTemplate | null,
  options: { excludeRootScope?: boolean; rootScopeFieldKey?: string } = {},
): Record<string, unknown> {
  if (!template) return {};

  const defaults: Record<string, unknown> = {};
  const rootScopeFieldKey = options.excludeRootScope
    ? (options.rootScopeFieldKey || getRootDepartmentFieldKey(template))
    : '';

  for (const group of template.groups) {
    for (const field of group.fields) {
      if (field.key === rootScopeFieldKey) {
        continue;
      }
      if (!hasUsableFieldDefault(field.default)) {
        continue;
      }
      defaults[field.key] = field.default;
    }
  }

  return defaults;
}

export function mergeUserSyncBusinessConfigWithDefaults(
  currentBusinessConfig: Record<string, unknown> | undefined,
  template: BusinessTemplate | null,
  options: { excludeRootScope?: boolean; rootScopeFieldKey?: string } = {},
): Record<string, unknown> {
  return {
    ...getUserSyncBusinessConfigDefaults(template, options),
    ...(currentBusinessConfig || {}),
  };
}

export function getRootDepartmentInputMode(
  template: BusinessTemplate | null,
): 'department_select' | 'manual_input' {
  if (!template) return 'department_select';
  const field = getUserSyncTemplateField(template, getRootDepartmentFieldKey(template));
  if (field) {
    return field.input_mode === 'manual_input' ? 'manual_input' : 'department_select';
  }
  return 'department_select';
}

export function isDepartmentSelectMode(template: BusinessTemplate | null): boolean {
  return getRootDepartmentInputMode(template) === 'department_select';
}

export function isManualInputMode(template: BusinessTemplate | null): boolean {
  return getRootDepartmentInputMode(template) === 'manual_input';
}

export function shouldFetchDepartmentOptions(input: {
  selectedInstanceId: number | undefined;
  template: BusinessTemplate | null;
}): boolean {
  if (!input.selectedInstanceId) {
    return false;
  }
  return getRootDepartmentInputMode(input.template) === 'department_select';
}

function buildExistingSourcePayload(source: UserSyncSource): Partial<UserSyncSource> {
  return {
    name: source.name,
    integration_instance: source.integration_instance,
    enabled: source.enabled,
    description: source.description,
    root_group_name: source.root_group_name,
    field_mapping: { ...(source.field_mapping || {}) },
    schedule_config: source.schedule_config ? { ...source.schedule_config } : { mode: 'disabled', timezone: 'Asia/Shanghai' },
    business_config: { ...(source.business_config || {}) },
  };
}

function stripEmptyWriteOnlyFields(
  businessConfig: Record<string, unknown>,
  writeOnlyKeys: Set<string>
): Record<string, unknown> {
  const nextConfig = { ...businessConfig };
  for (const key of writeOnlyKeys) {
    const value = nextConfig[key];
    if (value === undefined || value === null || value === '') {
      delete nextConfig[key];
    }
  }
  return nextConfig;
}

export function buildCreateSyncSourcePayload(
  values: UserSyncSourceCreateFormValues,
  fieldMapping: Record<string, string>
): Partial<UserSyncSource> {
  return {
    name: values.name,
    integration_instance: values.integration_instance,
    enabled: true,
    description: values.description,
    root_group_name: values.root_group_name,
    field_mapping: fieldMapping,
    schedule_config: { mode: 'disabled', timezone: 'Asia/Shanghai' },
    business_config: {
      ...(values.business_config || {}),
    },
  };
}

export function buildBasicUpdatePayload(
  source: UserSyncSource,
  values: UserSyncSourceBasicFormValues
): Partial<UserSyncSource> {
  return {
    ...buildExistingSourcePayload(source),
    name: values.name,
    description: values.description,
  };
}

export function buildConfigUpdatePayload(
  source: UserSyncSource,
  businessConfig: Record<string, unknown> | undefined,
  fieldMapping: Record<string, string>
): Partial<UserSyncSource> {
  return {
    ...buildExistingSourcePayload(source),
    field_mapping: fieldMapping,
    business_config: {
      ...(businessConfig || {}),
    },
  };
}

export function buildStrategyUpdatePayload(
  source: UserSyncSource,
  values: UserSyncSourceStrategyFormValues
): Partial<UserSyncSource> {
  return {
    ...buildExistingSourcePayload(source),
    enabled: values.enabled,
    schedule_config: buildSchedulePayload(values),
  };
}

export function buildConfigPreviewPayload(
  source: UserSyncSource,
  businessConfig: Record<string, unknown> | undefined,
  fieldMapping: Record<string, string>,
  writeOnlyKeys: Set<string>
): Record<string, unknown> {
  const payload = buildConfigUpdatePayload(source, businessConfig, fieldMapping);
  return {
    source_id: source.id,
    ...payload,
    business_config: stripEmptyWriteOnlyFields(
      (payload.business_config || {}) as Record<string, unknown>,
      writeOnlyKeys
    ),
  };
}
