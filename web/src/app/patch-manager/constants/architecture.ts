export type CanonicalArchitecture = 'x86_64' | 'arm64';

export const LINUX_ARCHITECTURE_OPTIONS: Array<{
  label: string;
  value: CanonicalArchitecture;
}> = [
  { label: 'x86_64', value: 'x86_64' },
  { label: 'ARM64', value: 'arm64' },
];

export const WINDOWS_ARCHITECTURE_OPTIONS = LINUX_ARCHITECTURE_OPTIONS.filter(
  ({ value }) => value === 'x86_64',
);

export const LINUX_ARCHITECTURE_FILTER_OPTIONS = LINUX_ARCHITECTURE_OPTIONS.map(
  ({ label, value }) => ({ id: value, name: label }),
);

export const WINDOWS_ARCHITECTURE_FILTER_OPTIONS = WINDOWS_ARCHITECTURE_OPTIONS.map(
  ({ label, value }) => ({ id: value, name: label }),
);

const ARCHITECTURE_ALIASES: Record<string, CanonicalArchitecture> = {
  x86_64: 'x86_64',
  amd64: 'x86_64',
  x64: 'x86_64',
  arm64: 'arm64',
  aarch64: 'arm64',
};

const ARCHITECTURE_LABELS: Record<CanonicalArchitecture, string> = {
  x86_64: 'x86_64',
  arm64: 'ARM64',
};

type ArchitectureValues = string | readonly string[] | null | undefined;

interface ApplicableScopeSource {
  source_type: string;
  distro_name?: string | null;
  os_version?: string | null;
  arch?: string | null;
}

export function normalizeArchitecture(value?: string | null): CanonicalArchitecture | '' {
  return value ? ARCHITECTURE_ALIASES[value.trim().toLowerCase()] || '' : '';
}

export function normalizeArchitectures(values: ArchitectureValues): CanonicalArchitecture[] {
  const items = typeof values === 'string' ? values.split(/[,、]/) : values || [];
  return Array.from(new Set(items.map(normalizeArchitecture).filter(Boolean))) as CanonicalArchitecture[];
}

export function formatArchitecture(value?: string | null, fallback = '—'): string {
  const architecture = normalizeArchitecture(value);
  return architecture ? ARCHITECTURE_LABELS[architecture] : fallback;
}

export function formatArchitectures(values: ArchitectureValues, fallback = '—'): string {
  const labels = normalizeArchitectures(values).map((architecture) => ARCHITECTURE_LABELS[architecture]);
  return labels.join('、') || fallback;
}

export function formatSourceApplicableScope(
  source: ApplicableScopeSource,
  wsusLabel = 'Windows（WSUS）',
  fallback = '—',
): string {
  if (source.source_type === 'wsus') return wsusLabel;
  const parts = [
    source.distro_name?.trim(),
    source.os_version?.trim(),
    formatArchitecture(source.arch, ''),
  ].filter(Boolean);
  return parts.join(' · ') || fallback;
}
