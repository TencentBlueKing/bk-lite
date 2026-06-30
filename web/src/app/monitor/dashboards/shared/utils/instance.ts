/**
 * 判定一个串是否为「不透明标识符」(base64/hash 类、无人类可读含义),用于决定是否在 UI 隐藏。
 * 命中条件:≥12 位 base64 字母表、且不含 `.:/`、且不含「单词分隔结构」。
 *
 * 分隔结构 `[A-Za-z]+[-_][A-Za-z0-9]`:字母单词后接 `-`/`_` 再接字母/数字,如 `mock-postgres`、
 * `PROD-DB-PRIMARY`、`REDIS_CACHE_01`、`postgres_5432`。大小写均视为可读命名,不应隐藏。
 * 真正的不透明串(base64 混合大小写无分隔,如 `bW9ja1Bvc3RncmVzNTQ`)、UUID(分隔前是十六进制
 * 数字而非字母单词,如 `a1b2c3d4-e5f6`)均不匹配此结构 → 仍判定为不透明。
 */
const looksOpaque = (value: string): boolean =>
  /^[A-Za-z0-9+/=_-]{12,}$/.test(value) && !/[.:/]/.test(value) && !/[A-Za-z]+[-_][A-Za-z0-9]/.test(value);

export const normalizeDisplayText = (value?: string | null) => {
  if (!value) return '';
  const trimmed = value.trim();
  if (!trimmed || trimmed === '--') return '';
  const withoutQuotes = trimmed.replace(/^["'`\[(,\s]+|["'`,;\])\s]+$/g, '').trim();
  if (!withoutQuotes || withoutQuotes === '--') return '';
  if (looksOpaque(withoutQuotes)) return '';
  return withoutQuotes;
};

export const isOpaqueIdentifier = (value?: string | null) => {
  const normalized = normalizeDisplayText(value);
  if (!normalized) return true;
  return looksOpaque(normalized);
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

export const buildStorageInstanceId = (values: string[]) => {
  const normalizedValues = values.map((value) => String(value || '').trim()).filter(Boolean);
  if (normalizedValues.length <= 1) {
    return normalizedValues[0] || '';
  }
  return `(${normalizedValues.map((value) => `'${value}'`).join(', ')})`;
};

export const resolveDashboardInstanceIdentity = (params: URLSearchParams) => {
  const rawInstanceId = params.get('instance_id') || '';
  const rawInstanceIdValues = params.get('instance_id_values') || '';
  const storageInstanceId = rawInstanceId.trim() === '--' ? '' : rawInstanceId.trim();
  const parsedLegacyInstanceIds = parseLegacyParamList(rawInstanceId);
  const explicitValues = parseLegacyParamList(rawInstanceIdValues);

  const idValues = explicitValues.length > 0
    ? explicitValues
    : parsedLegacyInstanceIds.length > 0
      ? parsedLegacyInstanceIds
      : storageInstanceId ? [storageInstanceId] : [];

  const instanceId = storageInstanceId || buildStorageInstanceId(idValues);

  return { instanceId, idValues };
};
