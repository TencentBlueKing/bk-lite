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

export const INTEGRATION_DETAIL_TAB_ORDER = ['base', 'user_sync', 'login_auth', 'im_notification', 'im_group'] as const;

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

export const CAPABILITY_TAG_GAP = 4;

/** 按容器宽度计算一行能放下几个标签；放不下时预留 +N，并至少保留 1 个可截断标签。 */
export function computeVisibleCapabilityTagCount(
  tagWidths: number[],
  containerWidth: number,
  overflowBadgeWidth: number,
  gap = CAPABILITY_TAG_GAP,
): number {
  if (tagWidths.length === 0 || containerWidth <= 0) {
    return 0;
  }

  let allUsed = 0;
  for (let i = 0; i < tagWidths.length; i += 1) {
    allUsed += tagWidths[i] + (i > 0 ? gap : 0);
  }
  if (allUsed <= containerWidth) {
    return tagWidths.length;
  }

  const reserve = Math.max(overflowBadgeWidth, 0) + gap;
  let used = 0;
  let count = 0;
  for (let i = 0; i < tagWidths.length; i += 1) {
    const next = used + (count > 0 ? gap : 0) + tagWidths[i];
    if (next + reserve > containerWidth) {
      break;
    }
    used = next;
    count += 1;
  }
  return Math.max(count, 1);
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


export const DEFAULT_INTEGRATION_PROVIDER_ICON = 'default-provider';

export function resolveIntegrationProviderIcon(providerKey: string) {
  const providerIconMap: Record<string, string> = {
    feishu: 'feishu',
    ad: 'ad',
    ldap: 'LDAP',
    oidc: 'OIDC',
    saml: 'SAML',
    github: 'github-fill',
    wechat: 'wechat',
    wecom: 'wecom',
  };
  return providerIconMap[providerKey] || DEFAULT_INTEGRATION_PROVIDER_ICON;
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

export interface IntegrationProviderQueryItem {
  name: string;
  description: string;
  raw?: Pick<ProviderManifest, 'capabilities'>;
}

export function collectIntegrationCapabilityFilterOptions(
  providers: Array<{ capabilities?: Array<{ key: string }> }>,
  t: (key: string, fallback?: string) => string,
): Array<{ label: string; value: string }> {
  const present = new Set<string>();
  providers.forEach((provider) => {
    (provider.capabilities || []).forEach((capability) => {
      if (capability.key) {
        present.add(capability.key);
      }
    });
  });

  const ordered = INTEGRATION_DETAIL_TAB_ORDER.filter((key) => key !== 'base' && present.has(key));
  const extras = [...present]
    .filter((key) => !ordered.includes(key as (typeof ordered)[number]))
    .sort();

  return [...ordered, ...extras].map((key) => ({
    value: key,
    label: getIntegrationCapabilityLabel(key, t),
  }));
}

function getProviderQueryCapabilityKeys(item: IntegrationProviderQueryItem): string[] {
  return (item.raw?.capabilities || []).map((capability) => capability.key).filter(Boolean);
}

export function filterIntegrationProvidersByQuery<T extends IntegrationProviderQueryItem>(
  providers: T[],
  keyword: string,
  capabilityKeys: string[] = [],
  t?: (key: string, fallback?: string) => string,
) {
  const tokens = keyword.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const requiredKeys = capabilityKeys.filter(Boolean);

  return providers.filter((item) => {
    const itemKeys = getProviderQueryCapabilityKeys(item);
    if (requiredKeys.length > 0 && !requiredKeys.every((key) => itemKeys.includes(key))) {
      return false;
    }
    if (!tokens.length) {
      return true;
    }

    const capabilityLabels = itemKeys.map((key) => getIntegrationCapabilityLabel(key, t).toLowerCase());
    const haystack = [item.name, item.description, ...itemKeys, ...capabilityLabels]
      .join('\n')
      .toLowerCase();
    return tokens.every((token) => haystack.includes(token));
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
  const providerDisplayName =
    instance.provider?.name || instance.provider_name || t(`system.integrationCenter.provider.${instance.provider_key}`, instance.provider_key);
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

export function getIntegrationProviderDescription(
  providerKey: string,
  t: (key: string, fallback?: string) => string,
  fallback = '',
): string {
  return t(`system.integrationCenter.providerDesc.${providerKey}`, fallback);
}

export function buildIntegrationInstanceCardItem(
  instance: IntegrationInstance,
  provider?: ProviderManifest,
): IntegrationInstanceCardItem {
  return {
    id: instance.id,
    name: instance.name,
    icon: resolveIntegrationProviderIcon(instance.provider_key),
    description: instance.provider?.name || instance.provider_key,
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
    im_group: t ? t('system.integrationCenter.capability.imGroup') : 'im_group',
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

export function getIntegrationBaseCapabilityStatusItems(input: {
  instance: Pick<IntegrationInstance, 'status' | 'capability_status' | 'capability_enabled'>;
  t: (key: string, fallback?: string) => string;
}): IntegrationSummaryItem[] {
  const { instance, t } = input;

  return getAvailableIntegrationTabs(instance)
    .filter((tabKey) => tabKey !== 'base')
    .map((capabilityKey) => {
      const capabilityEnabled = Boolean(instance.capability_enabled?.[capabilityKey]);
      const capabilityTestStatus = !capabilityEnabled
        ? { text: t('system.integrationCenter.disabled'), tone: 'neutral' as const }
        : instance.status === 'ready'
          ? instance.capability_status?.[capabilityKey] === 'ready'
            ? { text: t('system.integrationCenter.capabilityValidationPassed'), tone: 'success' as const }
            : instance.capability_status?.[capabilityKey] === 'verification_failed'
              ? { text: t('system.integrationCenter.capabilityValidationFailed'), tone: 'error' as const }
              : { text: t('system.integrationCenter.capabilityValidationPending'), tone: 'neutral' as const }
          : instance.status === 'verification_failed'
            ? { text: t('system.integrationCenter.baseConnectionAbnormal'), tone: 'error' as const }
            : { text: t('system.integrationCenter.baseConnectionPending'), tone: 'neutral' as const };

      return {
        label: getIntegrationCapabilityLabel(capabilityKey, t),
        value: capabilityTestStatus.text,
        tone: capabilityTestStatus.tone,
      };
    });
}

export function getIntegrationDiagnosticMessage(
  code: string | undefined,
  t: (key: string, fallback?: string) => string,
): string {
  const diagnosticKeyMap: Record<string, string> = {
    'provider.invalid_config': 'system.integrationCenter.diagnosticInvalidConfig',
    'provider.auth_failed': 'system.integrationCenter.diagnosticAuthFailed',
    'provider.timeout': 'system.integrationCenter.diagnosticTimeout',
    'provider.invalid_response': 'system.integrationCenter.diagnosticInvalidResponse',
    'provider.request_failed': 'system.integrationCenter.diagnosticRequestFailed',
    'provider.permission_unverified': 'system.integrationCenter.diagnosticPermissionUnverified',
    'provider.bot_not_enabled': 'system.integrationCenter.diagnosticBotNotEnabled',
  };
  return t(diagnosticKeyMap[code || ''] || 'system.integrationCenter.diagnosticRequestFailed');
}

export function getIntegrationDetailTopSectionContent(
  instance: Pick<IntegrationInstance, 'provider_key' | 'description' | 'provider'>,
  t: (key: string, fallback?: string) => string,
) {
  const providerName = instance.provider?.name || getIntegrationProviderDisplayName(instance.provider_key, t);
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
    const testStatus = getIntegrationBaseTestStatusMeta(instance.status, t);
    return [
      { label: t('system.integrationCenter.configurationValidation'), value: testStatus.text, tone: testStatus.tone },
    ];
  }

  const capabilityEnabled = Boolean(instance.capability_enabled?.[activeTab]);
  const capabilityStatusValue = instance.capability_status?.[activeTab];
  const capabilityTestStatus = instance.status === 'ready'
    ? capabilityStatusValue === 'ready'
      ? { text: t('system.integrationCenter.capabilityValidationPassed'), tone: 'success' as const }
      : capabilityStatusValue === 'verification_failed'
        ? { text: t('system.integrationCenter.capabilityValidationFailed'), tone: 'error' as const }
        : { text: t('system.integrationCenter.capabilityValidationPending'), tone: 'neutral' as const }
    : instance.status === 'verification_failed'
      ? { text: t('system.integrationCenter.baseConnectionAbnormal'), tone: 'error' as const }
      : { text: t('system.integrationCenter.baseConnectionPending'), tone: 'neutral' as const };
  return [
    {
      label: t('system.integrationCenter.enableStatus'),
      value: t(capabilityEnabled ? 'system.integrationCenter.enabled' : 'system.integrationCenter.disabled'),
      tone: capabilityEnabled ? 'success' : 'neutral',
    },
    {
      label: t('system.integrationCenter.capabilityConfigurationValidation'),
      value: capabilityTestStatus.text,
      tone: capabilityTestStatus.tone,
    },
  ];
}
