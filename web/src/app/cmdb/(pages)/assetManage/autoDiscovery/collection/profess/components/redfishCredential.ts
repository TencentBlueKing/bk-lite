import { PASSWORD_PLACEHOLDER } from '@/app/cmdb/constants/professCollection';
import type { CredentialPoolItem } from '@/app/cmdb/types/autoDiscovery';

export function createRedfishCredential(): CredentialPoolItem {
  return {
    username: '',
    password: '',
    port: 443,
    verify_tls: true,
  };
}

export function buildRedfishCredential(
  raw: CredentialPoolItem,
): CredentialPoolItem {
  const credential: CredentialPoolItem = {
    ...(raw.credential_id ? { credential_id: raw.credential_id } : {}),
    username: String(raw.username || raw.user || '').trim(),
    port: Number(raw.port || 443),
    verify_tls: raw.verify_tls !== false,
    credential_source: raw.credential_source || 'inline',
    ...(raw.credential_source === 'vault' ? { vault_credential_id: raw.vault_credential_id, vault_type_key: raw.vault_type_key } : {}),
  };
  const password = String(raw.password || '');
  if (raw.credential_source !== 'vault' && password && password !== PASSWORD_PLACEHOLDER) {
    credential.password = password;
  }
  if (raw.credential_source === 'vault') delete credential.username;
  return credential;
}

export function restoreRedfishCredential(
  raw: CredentialPoolItem,
  isCopy: boolean,
): CredentialPoolItem {
  return {
    ...(raw.credential_id ? { credential_id: raw.credential_id } : {}),
    ...(raw.credential_source !== 'vault' ? {
      username: raw.username || raw.user || '',
      password: isCopy ? '' : PASSWORD_PLACEHOLDER,
    } : {}),
    port: Number(raw.port || 443),
    verify_tls: raw.verify_tls !== false,
    credential_source: raw.credential_source || 'inline',
    ...(raw.credential_source === 'vault' ? { vault_credential_id: raw.vault_credential_id, vault_type_key: raw.vault_type_key } : {}),
  };
}
