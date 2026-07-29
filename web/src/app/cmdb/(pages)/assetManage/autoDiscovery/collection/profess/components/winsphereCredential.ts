import { PASSWORD_PLACEHOLDER } from '@/app/cmdb/constants/professCollection';

export interface WinSphereCredential {
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

export const createWinSphereCredential = (): Required<WinSphereCredential> => ({
  user: '',
  password: '',
  https_port: 443,
  verify_tls: false,
});

export const buildWinSphereCredential = (
  value: WinSphereCredential,
): WinSphereCredential => {
  const credential: WinSphereCredential = {
    user: trim(value.user),
    https_port: Number(value.https_port ?? 443),
    verify_tls: toBoolean(value.verify_tls),
  };
  const password = trim(value.password);
  if (password && password !== PASSWORD_PLACEHOLDER) {
    credential.password = password;
  }
  return credential;
};

export const restoreWinSphereCredential = (
  value: WinSphereCredential | WinSphereCredential[] | undefined,
  isCopy: boolean,
): Required<WinSphereCredential> => {
  const item = getCredentialItem(value);
  return {
    user: trim(item.user),
    password: isCopy ? '' : PASSWORD_PLACEHOLDER,
    https_port: Number(item.https_port ?? 443),
    verify_tls: toBoolean(item.verify_tls),
  };
};

export const validateWinSphereCredential = (
  value: WinSphereCredential,
): keyof WinSphereCredential | null => {
  if (!trim(value.user)) return 'user';
  if (!trim(value.password)) return 'password';
  const port = Number(value.https_port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return 'https_port';
  }
  if (typeof value.verify_tls !== 'boolean') return 'verify_tls';
  return null;
};
