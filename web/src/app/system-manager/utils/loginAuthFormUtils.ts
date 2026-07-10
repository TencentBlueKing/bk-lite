import type {
  AvailableInstance,
  LoginAuthBinding,
  LoginAuthBindingPayload,
} from '@/app/system-manager/api/login-auth';
import type {
  BusinessTemplate,
  ProviderManifest,
} from '@/app/system-manager/types/integration-center';
import { resolveIntegrationProviderIcon } from '@/app/system-manager/utils/integrationCenter';

export function shouldShowLoginAuthUnmatchedUserAction(providerKey?: string | null): boolean {
  return providerKey === 'wechat';
}

export function resolveLoginAuthProviderKey(
  integrationInstanceId: number | undefined,
  availableInstances: AvailableInstance[],
  editingBinding: LoginAuthBinding | null,
): string {
  if (!integrationInstanceId) {
    return editingBinding?.provider_key || '';
  }

  const providerKey = availableInstances.find((item) => item.id === integrationInstanceId)?.provider_key;
  if (providerKey) {
    return providerKey;
  }

  return editingBinding?.provider_key || '';
}

export function resolveLoginAuthDefaultIcon(providerKey?: string | null): string {
  if (!providerKey) {
    return '';
  }

  const icon = resolveIntegrationProviderIcon(providerKey);
  return icon === 'jicheng' ? '' : icon;
}

export function resolveLoginAuthTemplate(
  instanceId: number | undefined,
  availableInstances: AvailableInstance[],
  providers: ProviderManifest[],
): BusinessTemplate | null {
  if (!instanceId) return null;
  const instance = availableInstances.find((item) => item.id === instanceId);
  if (!instance) return null;
  const provider = providers.find((item) => item.key === instance.provider_key);
  if (!provider) return null;
  const capability = provider.capabilities.find((item) => item.key === 'login_auth');
  if (!capability?.business_template) return null;
  return provider.business_templates?.[capability.business_template] ?? null;
}

export function resolveLoginAuthDefaultExternalField(template: BusinessTemplate | null): string {
  if (!template) {
    return '';
  }

  if (template.default_external_match_field) {
    return template.default_external_match_field;
  }

  return template.available_external_fields[0] || '';
}

export function buildLoginAuthBindingPayload(
  values: {
    name: string;
    integration_instance: number;
    icon?: string;
    description?: string;
    external_field: string;
    platform_field: LoginAuthBindingPayload['platform_field'];
    unmatched_user_action?: LoginAuthBindingPayload['unmatched_user_action'];
    default_group_name?: string;
  },
  providerKey: string,
): Omit<LoginAuthBindingPayload, 'order'> {
  const basePayload = {
    name: values.name.trim(),
    integration_instance: values.integration_instance,
    icon: values.icon || '',
    description: values.description || '',
    external_field: values.external_field.trim(),
    platform_field: values.platform_field,
  };

  if (!shouldShowLoginAuthUnmatchedUserAction(providerKey)) {
    return {
      ...basePayload,
      unmatched_user_action: 'deny',
      default_group_name: '',
    };
  }

  const unmatchedAction = values.unmatched_user_action || 'deny';
  // WeChat provider: create 时允许 default_group_name 为空,后端 fallback 到 OpsPilotGuest
  // 非 WeChat provider: create 时必须有 default_group_name(由 modal 必填校验保证)
  return {
    ...basePayload,
    unmatched_user_action: unmatchedAction,
    default_group_name:
      unmatchedAction === 'create' ? values.default_group_name?.trim() || '' : '',
  };
}
