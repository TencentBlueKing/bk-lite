import { PASSWORD_PLACEHOLDER } from '@/app/cmdb/constants/professCollection';

export interface WinSphereCredential {
  user?: string;
  password?: string;
  https_port?: number | string;
  verify_tls?: boolean;
}

export const createWinSphereCredential = (): Required<WinSphereCredential> => ({
  user: '',
  password: '',
  https_port: 443,
  verify_tls: false,
});

const trim = (value: unknown) => String(value ?? '').trim();

export const buildWinSphereCredential = (
  value: WinSphereCredential,
): WinSphereCredential => {
  const credential: WinSphereCredential = {
    user: trim(value.user),
    https_port: Number(value.https_port || 443),
    verify_tls: Boolean(value.verify_tls),
  };
  const password = trim(value.password);
  if (password && password !== PASSWORD_PLACEHOLDER) {
    credential.password = password;
  }
  return credential;
};

export const restoreWinSphereCredential = (
  value: WinSphereCredential | undefined,
  isCopy: boolean,
): Required<WinSphereCredential> => ({
  user: trim(value?.user),
  password: isCopy ? '' : PASSWORD_PLACEHOLDER,
  https_port: Number(value?.https_port || 443),
  verify_tls: Boolean(value?.verify_tls),
});

export const validateWinSphereCredential = (
  value: WinSphereCredential,
): keyof WinSphereCredential | null => {
  if (!trim(value.user)) return 'user';
  if (!trim(value.password)) return 'password';
  const port = Number(value.https_port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return 'https_port';
  }
  return null;
};
