import type { CredentialPoolItem } from '@/app/cmdb/types/autoDiscovery';

export const VAULT_AUTH_FIELDS = new Set([
  'username', 'user', 'password', 'auth_method', 'authType', 'private_key',
  'passphrase', 'accessKey', 'accessSecret', 'access_key', 'access_secret',
  'secret_key', 'secret_id', 'client_id', 'client_secret', 'tenant_id',
  'token', 'community', 'security_level', 'level', 'auth_protocol',
  'auth_password', 'priv_protocol', 'priv_password', 'integrity', 'authkey',
  'privacy', 'privkey', 'enable_password', 'user_domain_name', 'extra', 'secret',
]);

export function isVaultAuthField(key: string, item: CredentialPoolItem): boolean {
  if (key === 'enable_password' && ['platform_api', 'ssh'].includes(item.vault_type_key || '')) return false;
  return VAULT_AUTH_FIELDS.has(key)
    || (key === 'version' && (item.vault_type_key === 'snmp' || item.snmp_port !== undefined));
}
