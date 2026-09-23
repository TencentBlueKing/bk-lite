export const DEFAULT_WINRM_CERTIFICATE_VALIDATION = false;

export interface VersionedPackage {
  id?: string | number;
  version?: string;
}

const parseVersionPart = (part?: string): number => {
  if (!part) {
    return 0;
  }
  if (!/^\d+$/.test(part)) {
    throw new Error('invalid version part');
  }
  return Number.parseInt(part, 10);
};

export function parseControllerVersion(
  version: string
): [number, number, number] {
  if (!version) {
    return [0, 0, 0];
  }
  try {
    const parts = version.trim().toLowerCase().replace(/^v/, '').split('.').slice(0, 3);
    return [
      parseVersionPart(parts[0]),
      parseVersionPart(parts[1]),
      parseVersionPart(parts[2])
    ];
  } catch {
    return [0, 0, 0];
  }
}

export function pickLatestPackage<T extends VersionedPackage>(
  packages: T[]
): T | undefined {
  if (!packages.length) {
    return undefined;
  }
  return [...packages].sort((left, right) => {
    const leftVersion = parseControllerVersion(String(left.version ?? ''));
    const rightVersion = parseControllerVersion(String(right.version ?? ''));
    for (let index = 0; index < 3; index += 1) {
      if (rightVersion[index] !== leftVersion[index]) {
        return rightVersion[index] - leftVersion[index];
      }
    }
    return Number(right.id ?? 0) - Number(left.id ?? 0);
  })[0];
}

interface NodeIdentityDraft extends Record<string, unknown> {
  ip?: string | null;
  node_name?: string | null;
}

export function applyIpAsDefaultNodeName<T extends NodeIdentityDraft>(
  row: T,
  nextIp: string
) {
  const shouldSyncNodeName =
    row.node_name === undefined ||
    row.node_name === null ||
    row.node_name === '' ||
    row.node_name === row.ip;

  return {
    ...row,
    ip: nextIp,
    ...(shouldSyncNodeName ? { node_name: nextIp } : {})
  };
}

export function applyWinrmCertificateValidation<T extends object>(
  rows: T[],
  enabled: boolean
): Array<T & { winrm_cert_validation: boolean }> {
  return rows.map((row) => ({
    ...row,
    winrm_cert_validation: enabled
  }));
}

const toOrganizationId = (value: unknown): number | null => {
  const id = Number(value);
  if (!Number.isInteger(id) || id <= 0) {
    return null;
  }
  return id;
};

export function mergeCurrentOrganization(
  organizations: unknown,
  currentOrganizationId?: unknown
): number[] {
  const current = toOrganizationId(currentOrganizationId);
  const merged: number[] = current == null ? [] : [current];
  const seen = new Set(merged);
  const values = Array.isArray(organizations)
    ? organizations
    : organizations == null || organizations === ''
      ? []
      : [organizations];

  values.forEach((value) => {
    const id = toOrganizationId(value);
    if (id == null || seen.has(id)) {
      return;
    }
    seen.add(id);
    merged.push(id);
  });
  return merged;
}
