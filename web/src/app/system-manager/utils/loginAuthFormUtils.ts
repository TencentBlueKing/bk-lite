import type {
  AvailableInstance,
  LoginAuthBinding,
  LoginAuthBindingPayload,
} from '@/app/system-manager/api/login-auth';
import type {
  BusinessTemplate,
  ProviderManifest,
} from '@/app/system-manager/types/integration-center';

export function isBuiltinLoginAuthBinding(providerKey?: string | null): boolean {
  return providerKey === 'bk_lite_builtin';
}

const LOGIN_AUTH_UNMATCHED_ACTION_PROVIDERS = new Set(['wechat', 'feishu', 'wecom', 'blueking']);

export function shouldShowLoginAuthUnmatchedUserAction(providerKey?: string | null): boolean {
  return LOGIN_AUTH_UNMATCHED_ACTION_PROVIDERS.has(providerKey || '');
}

export function getLoginAuthInstanceNotFoundContent({
  loading,
  hasAvailableInstances,
  loadingText,
  emptyText,
}: {
  loading: boolean;
  hasAvailableInstances: boolean;
  loadingText: string;
  emptyText: string;
}): string | undefined {
  if (loading) {
    return loadingText;
  }

  return hasAvailableInstances ? undefined : emptyText;
}

export function getLoginAuthUnavailableEditingInstance(
  availableInstances: AvailableInstance[],
  editingBinding: LoginAuthBinding | null,
): AvailableInstance | null {
  if (!editingBinding || availableInstances.some((item) => item.id === editingBinding.integration_instance)) {
    return null;
  }

  return {
    id: editingBinding.integration_instance,
    name: editingBinding.integration_instance_name,
    provider_key: editingBinding.provider_key || '',
    provider_name: '',
  };
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
  // 微信可能带上已保存的默认组织。飞书、企微、蓝鲸的表单不收集该字段，提交空值，
  // 由后端在创建时进入 OpsPilotGuest。
  const defaultGroupName = providerKey === 'wechat' && unmatchedAction === 'create'
    ? values.default_group_name?.trim() || ''
    : '';
  return {
    ...basePayload,
    unmatched_user_action: unmatchedAction,
    default_group_name: defaultGroupName,
  };
}
