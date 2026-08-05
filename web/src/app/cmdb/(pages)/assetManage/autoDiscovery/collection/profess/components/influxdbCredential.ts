import { PASSWORD_PLACEHOLDER } from '@/app/cmdb/constants/professCollection';
import type { CredentialPoolItem } from '@/app/cmdb/types/autoDiscovery';

export type InfluxdbCredential = CredentialPoolItem & {
  scheme?: string;
  port?: number | string;
  verify_tls?: boolean;
  token?: string;
};

interface InfluxdbTargetOption {
  value: string | number;
  origin?: Record<string, unknown>;
}

export function buildInfluxdbTarget(
  selectedId: string | number | undefined,
  options: InfluxdbTargetOption[],
) {
  const instance = options.find((item) => item.value === selectedId)?.origin;
  return {
    ip_range: '',
    instances: instance ? [instance] : [],
  };
}

export function createInfluxdbCredential(): InfluxdbCredential {
  return {
    scheme: 'http',
    port: 8086,
    verify_tls: true,
    token: '',
  };
}

export function buildInfluxdbCredential(
  raw: InfluxdbCredential,
): InfluxdbCredential {
  const credential: InfluxdbCredential = {
    ...(raw.credential_id ? { credential_id: raw.credential_id } : {}),
    scheme: String(raw.scheme || 'http').toLowerCase(),
    port: Number(raw.port || 8086),
    verify_tls: raw.verify_tls !== false,
  };
  const token = typeof raw.token === 'string' ? raw.token.trim() : '';
  if (token && token !== PASSWORD_PLACEHOLDER) {
    credential.token = token;
  }
  return credential;
}

export function restoreInfluxdbCredential(
  raw: InfluxdbCredential,
  isCopy: boolean,
): InfluxdbCredential {
  const hasToken = Boolean(raw.token || raw.password);
  return {
    ...(raw.credential_id ? { credential_id: raw.credential_id } : {}),
    scheme: String(raw.scheme || (raw.ssl ? 'https' : 'http')).toLowerCase(),
    port: Number(raw.port || 8086),
    verify_tls: raw.verify_tls !== false,
    token: isCopy ? '' : hasToken ? PASSWORD_PLACEHOLDER : '',
  };
}

export function validateInfluxdbCredential(
  credential: InfluxdbCredential,
): 'scheme' | 'port' | null {
  if (!['http', 'https'].includes(String(credential.scheme || '').toLowerCase())) {
    return 'scheme';
  }
  const port = Number(credential.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    return 'port';
  }
  return null;
}
