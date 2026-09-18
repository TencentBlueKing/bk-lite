import { PASSWORD_PLACEHOLDER } from '@/app/cmdb/constants/professCollection';
import type { CredentialSchema } from '@/app/cmdb/types/autoDiscovery';

export interface WinSphereCredential {
  credential_id?: string;
  credential_source?: 'inline' | 'vault';
  vault_credential_id?: string;
  vault_type_key?: string;
  user?: string;
  password?: string;
  https_port?: number | string;
  verify_tls?: boolean;
}

const trim = (value: unknown) => String(value ?? '').trim();
const toBoolean = (value: unknown) => {
  if (typeof value === 'boolean') return value;
  return ['1', 'true', 'yes', 'on'].includes(trim(value).toLowerCase());
};

const getCredentialItem = (
  value: WinSphereCredential | WinSphereCredential[] | undefined,
): WinSphereCredential => {
  if (Array.isArray(value)) {
    return value.length === 1 && value[0] ? value[0] : {};
  }
  return value || {};
};

export const createWinSphereCredential = (
  schema: CredentialSchema,
): Required<WinSphereCredential> => Object.fromEntries(
  schema.fields.map((field) => [
    field.key,
    field.default ?? (field.type === 'boolean' ? false : ''),
  ]),
) as Required<WinSphereCredential>;

export const buildWinSphereCredential = (
  value: WinSphereCredential,
  schema: CredentialSchema,
): WinSphereCredential => {
  const credential: WinSphereCredential = {};
  schema.fields.forEach((field) => {
    const key = field.key as keyof WinSphereCredential;
    const rawValue = value[key];
    if (field.type === 'password') {
      const password = trim(rawValue);
      if (password && password !== PASSWORD_PLACEHOLDER) {
        credential[key] = password as never;
      }
      return;
    }
    const normalized = field.type === 'integer'
      ? Number(rawValue ?? field.default)
      : field.type === 'boolean'
        ? toBoolean(rawValue ?? field.default)
        : trim(rawValue);
    credential[key] = normalized as never;
  });
  credential.credential_source = value.credential_source || 'inline';
  credential.credential_id = value.credential_id;
  if (credential.credential_source === 'vault') {
    delete credential.user;
    delete credential.password;
    credential.vault_credential_id = value.vault_credential_id;
    credential.vault_type_key = value.vault_type_key;
  }
  return credential;
};

export const restoreWinSphereCredential = (
  value: WinSphereCredential | WinSphereCredential[] | undefined,
  isCopy: boolean,
  schema: CredentialSchema,
): WinSphereCredential => {
  const item = getCredentialItem(value);
  const restored: WinSphereCredential = { ...createWinSphereCredential(schema) };
  schema.fields.forEach((field) => {
    const key = field.key as keyof WinSphereCredential;
    const rawValue = item[key];
    if (field.type === 'password') {
      restored[key] = (isCopy ? '' : PASSWORD_PLACEHOLDER) as never;
    } else if (field.type === 'integer') {
      restored[key] = Number(rawValue ?? field.default) as never;
    } else if (field.type === 'boolean') {
      restored[key] = toBoolean(rawValue ?? field.default) as never;
    } else {
      restored[key] = trim(rawValue) as never;
    }
  });
  restored.credential_source = item.credential_source || 'inline';
  restored.credential_id = item.credential_id;
  if (restored.credential_source === 'vault') {
    delete restored.user;
    delete restored.password;
    restored.vault_credential_id = item.vault_credential_id;
    restored.vault_type_key = item.vault_type_key;
  }
  return restored;
};

export const validateWinSphereCredential = (
  value: WinSphereCredential,
  schema: CredentialSchema,
): string | null => {
  if (value.credential_source === 'vault' && !value.vault_credential_id) {
    return 'vault_credential_id';
  }
  for (const field of schema.fields) {
    if (value.credential_source === 'vault' && (field.key === 'user' || field.key === 'password')) {
      continue;
    }
    const rawValue = value[field.key as keyof WinSphereCredential];
    if (field.required && field.type !== 'boolean' && !trim(rawValue)) {
      return field.key;
    }
    if (field.type === 'integer') {
      const parsed = Number(rawValue);
      if (
        !Number.isInteger(parsed)
        || (field.min !== undefined && parsed < field.min)
        || (field.max !== undefined && parsed > field.max)
      ) {
        return field.key;
      }
    }
    if (field.type === 'boolean' && typeof rawValue !== 'boolean') {
      return field.key;
    }
  }
  return null;
};
