import type {
  AvailableInstance,
  LoginAuthBinding,
  LoginAuthBindingPayload,
} from '@/app/system-manager/api/login-auth';

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
  return {
    ...basePayload,
    unmatched_user_action: unmatchedAction,
    default_group_name:
      unmatchedAction === 'create' ? values.default_group_name?.trim() || '' : '',
  };
}
