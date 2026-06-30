import type {
  InstanceStatus,
  IntegrationInstance,
  TemplateField,
  ProviderManifest
} from '@/app/system-manager/types/integration-center';
import type { Rule } from 'antd/es/form';

export type IntegrationPrimaryStatusKey = 'started' | 'pending' | 'error' | 'inactive';
export type IntegrationPrimaryStatusTone = 'success' | 'default' | 'error';
export type IntegrationSummaryTone = 'success' | 'error' | 'neutral';
export interface IntegrationSummaryItem {
  label: string;
  value: string;
  tone: IntegrationSummaryTone;
}
export const INTEGRATION_DETAIL_TAB_ORDER = ['base', 'user_sync', 'login_auth', 'im_notification'] as const;

export type IntegrationDetailTab = typeof INTEGRATION_DETAIL_TAB_ORDER[number];

export function getAvailableIntegrationTabs(
  instance: Pick<IntegrationInstance, 'capability_status'>,
): IntegrationDetailTab[] {
  return INTEGRATION_DETAIL_TAB_ORDER.filter(
    (tabKey) => tabKey === 'base' || Boolean(instance.capability_status?.[tabKey]),
  );
}

export function getIntegrationDetailSectionDescription(
  activeTab: IntegrationDetailTab,
  t: (key: string, fallback?: string) => string,
) {
  if (activeTab === 'base') {
    return t('system.integrationCenter.baseConnectionDesc');
  }

  return t('system.integrationCenter.capabilityDesc');
}

export function canEnterCreateInfoStep(provider: Pick<ProviderManifest, 'key'> | null) {
  return Boolean(provider);
}

export function getCreateModalFooterMode(input: {
  step: 'provider' | 'basic_info';
  hasSelection: boolean;
  creating: boolean;
}) {
  if (input.step === 'provider') {
    return {
      showNext: true,
      disableNext: !input.hasSelection,
      showCreate: false,
      showCreateAndConfigure: false,
    };
  }

  return {
    showNext: false,
    disableNext: false,
    showCreate: !input.creating,
    showCreateAndConfigure: !input.creating,
  };
}


export function resolveIntegrationProviderIcon(providerKey: string) {
  const providerIconMap: Record<string, string> = {
    feishu: 'feishu',
    ad: 'ad',
    ldap: 'LDAP',
    oidc: 'OIDC',
    saml: 'SAML',
    github: 'github-fill',
    wechat: 'wechat'
  };
  return providerIconMap[providerKey] || 'jicheng';
}

export function filterIntegrationInstancesByName<T extends { name: string }>(
  instances: T[],
  keyword: string
) {
  const normalizedKeyword = keyword.trim().toLowerCase();
  if (!normalizedKeyword) {
    return instances;
  }

  return instances.filter((item) => item.name.toLowerCase().includes(normalizedKeyword));
}

export function filterIntegrationProvidersByQuery<T extends { name: string; description: string }>(
  providers: T[],
  keyword: string
) {
  const normalizedKeyword = keyword.trim().toLowerCase();
  if (!normalizedKeyword) {
    return providers;
  }

  return providers.filter((item) => {
    const name = item.name.toLowerCase();
    const description = (item.description || '').toLowerCase();
    return name.includes(normalizedKeyword) || description.includes(normalizedKeyword);
  });
}

export function isIntegrationInstanceStarted(capabilityStatus: Record<string, string>) {
  return Object.values(capabilityStatus || {}).some((status) => status === 'ready');
}

export function getIntegrationPrimaryStatusMeta(
  instanceStatus: InstanceStatus,
  capabilityStatus: Record<string, InstanceStatus>,
): { key: IntegrationPrimaryStatusKey; tone: IntegrationPrimaryStatusTone } {
  if (Object.values(capabilityStatus || {}).some((status) => status === 'ready')) {
    return { key: 'started', tone: 'success' };
  }

  if (
    instanceStatus === 'verification_failed' ||
    Object.values(capabilityStatus || {}).some((status) => status === 'verification_failed')
  ) {
    return { key: 'error', tone: 'error' };
  }

  if (
    instanceStatus === 'pending_verification' ||
    Object.values(capabilityStatus || {}).some((status) => status === 'pending_verification')
  ) {
    return { key: 'pending', tone: 'default' };
  }

  return { key: 'inactive', tone: 'default' };
}

export function resolveIntegrationPrimaryStatusColor(tone: IntegrationPrimaryStatusTone) {
  if (tone === 'success') {
    return 'green';
  }
  if (tone === 'error') {
    return 'red';
  }
  return 'default';
}

export function formatIntegrationInstanceDisplayName(
  instance: {
    name: string;
    provider_key: string;
    provider_name?: string;
    provider?: { name: string } | null;
  },
  t: (key: string, fallback?: string) => string,
): string {
  const providerDisplayName = t(`system.integrationCenter.provider.${instance.provider_key}`);
  return `${instance.name} / ${providerDisplayName}`;
}

export function getIntegrationCapabilityEnabled(
  instance: Pick<IntegrationInstance, 'capability_enabled'>,
  capabilityKey: string,
): boolean {
  return Boolean(instance.capability_enabled?.[capabilityKey]);
}

export function getIntegrationCapabilityTagColor(
  instance: IntegrationInstance,
  capabilityKey: string,
): 'green' | 'default' {
  const enabled = getIntegrationCapabilityEnabled(instance, capabilityKey);
  const ready = instance.capability_status?.[capabilityKey] === 'ready';
  return enabled && ready ? 'green' : 'default';
}

export interface IntegrationInstanceCardItem {
  id: number;
  name: string;
  icon: string;
  description: string;
  tagList: unknown[];
  raw: IntegrationInstance;
  provider?: ProviderManifest;
}

export function getIntegrationProviderDisplayName(
  providerKey: string,
  t: (key: string, fallback?: string) => string,
): string {
  return t(`system.integrationCenter.provider.${providerKey}`, providerKey);
}

export function buildIntegrationInstanceCardItem(
  instance: IntegrationInstance,
  provider?: ProviderManifest,
  t?: (key: string, fallback?: string) => string,
): IntegrationInstanceCardItem {
  return {
    id: instance.id,
    name: instance.name,
    icon: resolveIntegrationProviderIcon(instance.provider_key),
    description: t
      ? getIntegrationProviderDisplayName(instance.provider_key, t)
      : instance.provider?.name || instance.provider_key,
    tagList: [],
    raw: instance,
    provider,
  };
}

export function getIntegrationCapabilityLabel(
  key: string,
  t?: (key: string, fallback?: string) => string,
) {
  const capabilityLabelMap: Record<string, string> = {
    user_sync: t ? t('system.integrationCenter.capability.userSync') : 'user_sync',
    login_auth: t ? t('system.integrationCenter.capability.loginAuth') : 'login_auth',
    im_notification: t ? t('system.integrationCenter.capability.imNotification') : 'im_notification',
  };

  return capabilityLabelMap[key] || key;
}

export function getIntegrationCapabilityStatusText(
  status: string,
  t?: (key: string, fallback?: string) => string,
) {
  const status_map: Record<string, any> = {
    'ready': t('system.integrationCenter.primaryStatus.started'),
    'verification_failed': t('system.integrationCenter.primaryStatus.error'),
    'pending_verification': t('system.integrationCenter.primaryStatus.pending'),
    'default': t('system.integrationCenter.primaryStatus.inactive')
  };

  if(status) return status_map[status];
  return status_map['default'];
}

export function getIntegrationTestStatusText(
  status: string,
  t?: (key: string, fallback?: string) => string,
) {
  const test_map: Record<string, any> = {
    'ready': t('system.integrationCenter.testStatusReady'),
    'verification_failed': t('system.integrationCenter.testStatusFailed'),
    'pending_verification': t('system.integrationCenter.primaryStatus.pending'),
    'default': t('system.integrationCenter.testStatusPending')
  };
  if(status) return test_map[status];
  return test_map['default'];
}

export function getIntegrationHealthStatusMeta(
  status: string | undefined,
  t: (key: string, fallback?: string) => string,
): { text: string; tone: IntegrationSummaryTone } {
  if (status === 'ready') {
    return { text: t('system.integrationCenter.statusNormal'), tone: 'success' };
  }

  if (status === 'verification_failed') {
    return { text: t('system.integrationCenter.statusAbnormal'), tone: 'error' };
  }

  return { text: t('system.integrationCenter.statusPending'), tone: 'neutral' };
}

export function getIntegrationBaseTestStatusMeta(
  status: string | undefined,
  t: (key: string, fallback?: string) => string,
): { text: string; tone: IntegrationSummaryTone } {
  if (status === 'ready') {
    return { text: t('system.integrationCenter.testStatusHealthy'), tone: 'success' };
  }

  if (status === 'verification_failed') {
    return { text: t('system.integrationCenter.testStatusUnhealthy'), tone: 'error' };
  }

  return { text: t('system.integrationCenter.testStatusUntested'), tone: 'neutral' };
}

export function getIntegrationDetailTopSectionContent(
  instance: Pick<IntegrationInstance, 'provider_key' | 'description'>,
  t: (key: string, fallback?: string) => string,
) {
  const providerName = getIntegrationProviderDisplayName(instance.provider_key, t);
  const providerLabel = `${t('system.integrationCenter.providerTypeLabel')}: ${providerName}`;
  return instance.description ? `${providerLabel} · ${instance.description}` : providerLabel;
}

export function getIntegrationFieldBuckets(fields: TemplateField[]) {
  return {
    credentialFields: fields.filter((field) => field.key === 'app_id' || field.key === 'app_secret'),
    publicInterfaceFields: fields.filter((field) => field.key !== 'app_id' && field.key !== 'app_secret'),
  };
}

export function buildIntegrationFieldRules(field: TemplateField): Rule[] | undefined {
  if (!field.required) {
    return undefined;
  }

  const rule: Rule = {
    required: !field.write_only,
  };

  if (field.field_type === 'string' || field.field_type === 'textarea') {
    rule.whitespace = true;
  }

  return [rule];
}

export function getIntegrationDetailSummaryItems(input: {
  activeTab: IntegrationDetailTab;
  instance: Pick<IntegrationInstance, 'status' | 'capability_status' | 'capability_enabled'>;
  t: (key: string, fallback?: string) => string;
}): IntegrationSummaryItem[] {
  const { activeTab, instance, t } = input;

  if (activeTab === 'base') {
    const connectionStatus = getIntegrationHealthStatusMeta(instance.status, t);
    const testStatus = getIntegrationBaseTestStatusMeta(instance.status, t);
    return [
      { label: t('system.integrationCenter.connectionStatus'), value: connectionStatus.text, tone: connectionStatus.tone },
      { label: t('system.integrationCenter.testStatus'), value: testStatus.text, tone: testStatus.tone },
    ];
  }

  const capabilityEnabled = Boolean(instance.capability_enabled?.[activeTab]);
  const capabilityStatus = getIntegrationHealthStatusMeta(instance.capability_status?.[activeTab], t);
  const capabilityTestStatus = getIntegrationBaseTestStatusMeta(instance.capability_status?.[activeTab], t);
  return [
    {
      label: t('system.integrationCenter.enableStatus'),
      value: capabilityEnabled ? t('system.integrationCenter.enabled') : t('system.integrationCenter.disabled'),
      tone: capabilityEnabled ? 'success' : 'neutral',
    },
    { label: t('system.integrationCenter.connectionStatus'), value: capabilityStatus.text, tone: capabilityStatus.tone },
    { label: t('system.integrationCenter.testStatus'), value: capabilityTestStatus.text, tone: capabilityTestStatus.tone },
  ];
}
