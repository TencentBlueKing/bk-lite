import type { TableDataItem } from '../types';
import { getCollectorOperationSelection } from './nodeOperation';

const CPU_ARCHITECTURE_ALIASES: Record<string, string> = {
  x86_64: 'x86_64',
  amd64: 'x86_64',
  arm64: 'arm64',
  aarch64: 'arm64'
};

export interface CollectorPackageRecord {
  id?: string | number;
  version?: unknown;
  os?: unknown;
  cpu_architecture?: unknown;
  name?: unknown;
}

export interface CollectorPackageVersionOption {
  value: string | number;
  label: string;
}

export type CollectorInstallTarget =
  | {
      ok: true;
      os: string;
      cpuArchitecture: string;
    }
  | {
      ok: false;
      reason:
        | 'no_selection'
        | 'mixed_operating_system'
        | 'mixed_cpu_architecture'
        | 'unknown_architecture'
        | 'missing_target';
    };

export const normalizeCollectorCpuArchitecture = (value: unknown) => {
  const normalized = String(value ?? '')
    .trim()
    .toLowerCase();
  return CPU_ARCHITECTURE_ALIASES[normalized] || '';
};

const normalizeOperatingSystem = (value: unknown) =>
  String(value ?? '')
    .trim()
    .toLowerCase();

export const describeCollectorInstallTarget = (
  nodes: Array<Pick<TableDataItem, 'operating_system' | 'cpu_architecture'>>,
  fallback?: { os?: unknown; cpuArchitecture?: unknown }
): CollectorInstallTarget => {
  if (nodes.length) {
    const selection = getCollectorOperationSelection(nodes as TableDataItem[]);
    if (selection.disabled) {
      return { ok: false, reason: selection.reason };
    }
    const cpuArchitecture = normalizeCollectorCpuArchitecture(
      selection.cpuArchitecture
    );
    if (!cpuArchitecture) {
      return { ok: false, reason: 'unknown_architecture' };
    }
    return {
      ok: true,
      os: selection.operatingSystem.trim().toLowerCase(),
      cpuArchitecture
    };
  }

  const os = normalizeOperatingSystem(fallback?.os);
  const cpuArchitecture = normalizeCollectorCpuArchitecture(
    fallback?.cpuArchitecture
  );
  if (!os || !cpuArchitecture) {
    return { ok: false, reason: 'missing_target' };
  }
  return { ok: true, os, cpuArchitecture };
};

export const buildCollectorPackageListParams = ({
  objectName,
  os,
  cpuArchitecture
}: {
  objectName?: unknown;
  os?: unknown;
  cpuArchitecture?: unknown;
}) => {
  const object = String(objectName ?? '').trim();
  const normalizedOs = normalizeOperatingSystem(os);
  const normalizedArchitecture = normalizeCollectorCpuArchitecture(
    cpuArchitecture
  );
  if (!object || !normalizedOs || !normalizedArchitecture) {
    return null;
  }
  return {
    object,
    os: normalizedOs,
    cpu_architecture: normalizedArchitecture,
    type: 'collector' as const
  };
};

export const asCollectorPackageList = (
  data: unknown
): CollectorPackageRecord[] => {
  if (Array.isArray(data)) {
    return data as CollectorPackageRecord[];
  }
  if (data && typeof data === 'object' && Array.isArray((data as { items?: unknown }).items)) {
    return (data as { items: CollectorPackageRecord[] }).items;
  }
  return [];
};

const packageIdentity = (pkg: CollectorPackageRecord) => {
  const os = normalizeOperatingSystem(pkg.os);
  const cpuArchitecture = normalizeCollectorCpuArchitecture(
    pkg.cpu_architecture
  );
  return { os, cpuArchitecture };
};

const comparePackageVersionDesc = (
  left: CollectorPackageRecord,
  right: CollectorPackageRecord
) => {
  const versionOrder = String(right.version ?? '').localeCompare(
    String(left.version ?? ''),
    undefined,
    { numeric: true, sensitivity: 'base' }
  );
  if (versionOrder !== 0) {
    return versionOrder;
  }
  return Number(right.id ?? 0) - Number(left.id ?? 0);
};

export const selectCollectorPackageVersions = (
  packages: CollectorPackageRecord[],
  os: string,
  cpuArchitecture: string
) => {
  const targetOs = normalizeOperatingSystem(os);
  const targetArchitecture = normalizeCollectorCpuArchitecture(cpuArchitecture);
  const matches = packages.filter((pkg) => {
    if (pkg.id === undefined || pkg.id === null || pkg.id === '') {
      return false;
    }
    const identity = packageIdentity(pkg);
    return (
      identity.os === targetOs && identity.cpuArchitecture === targetArchitecture
    );
  });

  const sorted = [...matches].sort(comparePackageVersionDesc);
  const seenVersions = new Set<string>();
  const unique: CollectorPackageRecord[] = [];
  sorted.forEach((pkg) => {
    const version = String(pkg.version ?? '');
    if (seenVersions.has(version)) {
      return;
    }
    seenVersions.add(version);
    unique.push(pkg);
  });

  const options: CollectorPackageVersionOption[] = unique.map((pkg) => {
    const version = String(pkg.version ?? '');
    const identity = packageIdentity(pkg);
    return {
      value: pkg.id as string | number,
      label: `${version} (${identity.os} / ${identity.cpuArchitecture})`
    };
  });

  return {
    packages: unique,
    options,
    defaultPackageId: options[0]?.value
  };
};
