export type InstallIpUniquenessKind = 'duplicate' | 'exists';

export interface InstallIpUniquenessError {
  kind: InstallIpUniquenessKind;
  ip: string;
}

export function normalizeInstallIp(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '';
  }
  return String(value).trim();
}

function rowIp(row: unknown): string {
  if (!row || typeof row !== 'object' || !('ip' in row)) {
    return '';
  }
  return normalizeInstallIp((row as { ip?: unknown }).ip);
}

export function collectIpsFromRows(rows: readonly unknown[]): string[] {
  return rows.map(rowIp).filter(Boolean);
}

export function findInstallIpUniquenessError(
  rows: readonly unknown[],
  existingIps: Iterable<string> = [],
  occupiedIps: Iterable<string> = []
): InstallIpUniquenessError | null {
  const existing = new Set(
    Array.from(existingIps, (ip) => normalizeInstallIp(ip)).filter(Boolean)
  );
  const occupied = new Set(
    Array.from(occupiedIps, (ip) => normalizeInstallIp(ip)).filter(Boolean)
  );
  const seen = new Set<string>();
  for (const row of rows) {
    const ip = rowIp(row);
    if (!ip) {
      continue;
    }
    if (seen.has(ip) || occupied.has(ip)) {
      return { kind: 'duplicate', ip };
    }
    seen.add(ip);
    if (existing.has(ip)) {
      return { kind: 'exists', ip };
    }
  }
  return null;
}
