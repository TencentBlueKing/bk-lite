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
    || descriptor.defaultPort == null
  ) {
    throw new Error(`未声明平台 API 凭据描述：${modelId}`);
  }
  return {
    defaultPort: descriptor.defaultPort,
    helpKindKey: descriptor.credentialKindKey,
    helpInstructionKey: descriptor.instructionKey,
  };
}

export function createPlatformApiCredential(modelId: string): CredentialPoolItem {
  return {
    username: '',
    password: '',
    port: getPlatformApiCredentialConfig(modelId).defaultPort,
    verify_tls: true,
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
    // 兼容 CloudAkSk / encrypted_fields=accessKey|accessSecret 的企业云对象
    accessKey: username,
    port: Number(raw.port || getPlatformApiCredentialConfig(modelId).defaultPort),
    verify_tls: raw.verify_tls !== false,
  };
  const password = String(raw.password || '').trim();
  if (password && password !== PASSWORD_PLACEHOLDER) {
    credential.password = password;
    credential.accessSecret = password;
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
    port: Number(
      raw.port
      || endpointPort
      || getPlatformApiCredentialConfig(modelId).defaultPort,
    ),
    verify_tls: raw.verify_tls !== false,
  };
}

export function validatePlatformApiCredential(
  credential: CredentialPoolItem,
): 'username' | 'password' | 'port' | null {
  if (!String(credential.username || '').trim()) {
    return 'username';
  }
  if (!String(credential.password || '').trim()) {
    return 'password';
  }
  const port = Number(credential.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return 'port';
  }
  return null;
}
