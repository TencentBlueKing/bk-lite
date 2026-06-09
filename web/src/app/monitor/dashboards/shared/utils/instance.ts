export const normalizeDisplayText = (value?: string | null) => {
  if (!value) return '';
  const trimmed = value.trim();
  if (!trimmed || trimmed === '--') return '';
  const withoutQuotes = trimmed.replace(/^["'`\[(,\s]+|["'`,;\])\s]+$/g, '').trim();
  if (!withoutQuotes || withoutQuotes === '--') return '';
  if (
    /^[A-Za-z0-9+/=_-]{12,}$/.test(withoutQuotes) &&
    !/[.:/]/.test(withoutQuotes) &&
    !/[a-z]+-[a-z]/.test(withoutQuotes)
  ) {
    return '';
  }
  return withoutQuotes;
};

export const isOpaqueIdentifier = (value?: string | null) => {
  const normalized = normalizeDisplayText(value);
  if (!normalized) return true;
  return /^[A-Za-z0-9+/=_-]{12,}$/.test(normalized) && !/[.:/]/.test(normalized) && !/[a-z]+-[a-z]/.test(normalized);
};

export const buildInstanceDisplayName = (item: any) => {
  const primaryName = normalizeDisplayText(item.instance_name) || normalizeDisplayText(item.name);
  const hostPort = normalizeDisplayText(item.host && item.port ? `${item.host}:${item.port}` : '');
  const endpoint = normalizeDisplayText(item.endpoint) || normalizeDisplayText(item.url);
  const fallbackHost = normalizeDisplayText(item.host) || normalizeDisplayText(item.ip);

  if (primaryName && hostPort && !primaryName.includes(hostPort)) {
    return `${primaryName} (${hostPort})`;
  }
  return primaryName || hostPort || endpoint || fallbackHost || normalizeDisplayText(item.instance_id) || '--';
};

export const buildInstanceSearchTokens = (item: any, displayName: string) =>
  Array.from(
    new Set(
      [
        displayName,
        normalizeDisplayText(item.instance_name),
        normalizeDisplayText(item.name),
        normalizeDisplayText(item.host),
        normalizeDisplayText(item.ip),
        normalizeDisplayText(item.port),
        normalizeDisplayText(item.endpoint),
        normalizeDisplayText(item.url),
        normalizeDisplayText(item.instance_id)
      ].filter(Boolean)
    )
  );

export const parseLegacyParamList = (value?: string | null) => {
  if (!value) return [] as string[];
  const normalized = value
    .replace(/[()\[\]'"`]/g, '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  return Array.from(new Set(normalized));
};
