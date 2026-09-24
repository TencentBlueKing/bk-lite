import { PASSWORD_PLACEHOLDER } from '@/app/cmdb/constants/professCollection';
import type { CredentialPoolItem } from '@/app/cmdb/types/autoDiscovery';
import { getCredentialDescriptor } from './credentialDescriptors';

export interface PlatformApiCredentialConfig {
  defaultPort: number;
  helpKindKey: string;
  helpInstructionKey: string;
}

export function getPlatformApiCredentialConfig(
  modelId: string,
): PlatformApiCredentialConfig {
  const descriptor = getCredentialDescriptor({ model_id: modelId });
  if (
    !descriptor
    || descriptor.formKind !== 'platform_api'
    || (descriptor.defaultPort == null && modelId !== 'azure')
  ) {
    throw new Error(`未声明平台 API 凭据描述：${modelId}`);
  }
  return {
    defaultPort: descriptor.defaultPort ?? 443,
    helpKindKey: descriptor.credentialKindKey,
    helpInstructionKey: descriptor.instructionKey,
  };
}

export function createPlatformApiCredential(modelId: string): CredentialPoolItem {
  return {
    username: '',
    password: '',
    ...(modelId !== 'azure' ? { port: getPlatformApiCredentialConfig(modelId).defaultPort, verify_tls: true } : {}),
    ...(modelId === 'smartx' ? { source: 'LOCAL' } : {}),
    ...(modelId === 'fusioncompute' ? { user_type: '0', api_version: '8.1' } : {}),
    ...(modelId === 'manageone' ? { region: '', api_version: '8.2.0' } : {}),
    ...(['openstack', 'smartx', 'manageone', 'fusioncompute', 'nutanixhci', 'inspurincloudrail'].includes(modelId) ? { scheme: 'https' } : {}),
    ...(modelId === 'nacos' ? { scheme: 'http' } : {}),
    ...(modelId === 'azure' ? { tenant_id: '', subscription_id: '' } : {}),
    ...(modelId === 'openstack' ? { user_domain_name: 'Default', project_id: '' } : {}),
  };
}

export function buildPlatformApiCredential(
  modelId: string,
  raw: CredentialPoolItem,
): CredentialPoolItem {
  const username = String(raw.username || '').trim();
  const credential: CredentialPoolItem = {
    ...(raw.credential_id ? { credential_id: raw.credential_id } : {}),
    username,
    ...(modelId !== 'azure' ? {
      port: Number(raw.port || getPlatformApiCredentialConfig(modelId).defaultPort),
      verify_tls: modelId === 'smartx' || raw.verify_tls !== false,
    } : {}),
    ...(modelId === 'smartx' ? { source: raw.source || 'LOCAL' } : {}),
    ...(modelId === 'fusioncompute' ? { user_type: raw.user_type ?? '0', api_version: raw.api_version || '8.1' } : {}),
    ...(modelId === 'manageone' ? { region: raw.region || '', api_version: raw.api_version || '8.2.0' } : {}),
    ...(['openstack', 'smartx', 'manageone', 'fusioncompute', 'nutanixhci', 'inspurincloudrail'].includes(modelId) ? { scheme: raw.scheme || 'https' } : {}),
    ...(modelId === 'nacos' ? { scheme: raw.scheme || 'http' } : {}),
    ...(modelId === 'azure' ? { tenant_id: raw.tenant_id || '', subscription_id: raw.subscription_id || '' } : {}),
    ...(modelId === 'openstack' ? { user_domain_name: raw.user_domain_name || 'Default', project_id: raw.project_id || '' } : {}),
  };
  const password = String(raw.password || '').trim();
  if (password && password !== PASSWORD_PLACEHOLDER) {
    credential.password = password;
  }
  return credential;
}

export function restorePlatformApiCredential(
  modelId: string,
  raw: CredentialPoolItem,
  isCopy: boolean,
  endpoint?: string,
): CredentialPoolItem {
  let endpointPort: number | undefined;
  if (endpoint) {
    try {
      const parsed = new URL(
        endpoint.includes('://') ? endpoint : `https://${endpoint}`,
      );
      endpointPort = parsed.port ? Number(parsed.port) : undefined;
    } catch {
      endpointPort = undefined;
    }
  }
  return {
    ...(raw.credential_id ? { credential_id: raw.credential_id } : {}),
    username: raw.username || raw.accessKey || '',
    password: isCopy ? '' : PASSWORD_PLACEHOLDER,
    ...(modelId !== 'azure' ? {
      port: Number(raw.port || endpointPort || getPlatformApiCredentialConfig(modelId).defaultPort),
      verify_tls: modelId === 'smartx' || raw.verify_tls !== false,
    } : {}),
    ...(modelId === 'smartx' ? { source: raw.source || 'LOCAL' } : {}),
    ...(modelId === 'fusioncompute' ? { user_type: raw.user_type ?? '0', api_version: raw.api_version || '8.1' } : {}),
    ...(modelId === 'manageone' ? { region: raw.region || '', api_version: raw.api_version || '8.2.0' } : {}),
    ...(['openstack', 'smartx', 'manageone', 'fusioncompute', 'nutanixhci', 'inspurincloudrail'].includes(modelId) ? { scheme: raw.scheme || 'https' } : {}),
    ...(modelId === 'nacos' ? { scheme: raw.scheme || 'http' } : {}),
    ...(modelId === 'azure' ? { tenant_id: raw.tenant_id || '', subscription_id: raw.subscription_id || '' } : {}),
    ...(modelId === 'openstack' ? { user_domain_name: raw.user_domain_name || 'Default', project_id: raw.project_id || '' } : {}),
  };
}

export function validatePlatformApiCredential(
  credential: CredentialPoolItem,
  modelId?: string,
): 'username' | 'password' | 'port' | null {
  if (credential.credential_source === 'vault' && !credential.vault_credential_id) {
    return 'username';
  }
  if (credential.credential_source !== 'vault' && !String(credential.username || '').trim()) {
    return 'username';
  }
  if (credential.credential_source !== 'vault' && !String(credential.password || '').trim()) {
    return 'password';
  }
  if (modelId === 'azure') return null;
  const port = Number(credential.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return 'port';
  }
  return null;
}
