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
  let trimmed = value.trim();
  if (!trimmed || trimmed === '--') return '';
  // 仅剥成对包裹引号；保留名称内的 ()[]（如 process_name=edge(paren)）。
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'")) ||
    (trimmed.startsWith('`') && trimmed.endsWith('`'))
  ) {
    trimmed = trimmed.slice(1, -1).trim();
  }
  if (!trimmed || trimmed === '--') return '';
  if (looksOpaque(trimmed)) return '';
  return trimmed;
};

export const isOpaqueIdentifier = (value?: string | null) => {
  const normalized = normalizeDisplayText(value);
  if (!normalized) return true;
  return looksOpaque(normalized);
};

const resolveInstanceIdValues = (item: any): string[] => {
  if (Array.isArray(item?.instance_id_values) && item.instance_id_values.length) {
    return item.instance_id_values.map((value: unknown) => String(value ?? '')).filter(Boolean);
  }
  return parsePythonTupleString(String(item?.instance_id || '')) || [];
};

export const buildInstanceDisplayName = (item: any) => {
  const idValues = resolveInstanceIdValues(item);
  const identityLeaf = idValues.length > 1 ? normalizeDisplayText(idValues[idValues.length - 1]) : '';
  const primaryName =
    normalizeDisplayText(item.instance_name) ||
    normalizeDisplayText(item.name) ||
    normalizeDisplayText(item.process_name) ||
    identityLeaf;
  const hostPort = normalizeDisplayText(item.host && item.port ? `${item.host}:${item.port}` : '');
  const endpoint = normalizeDisplayText(item.endpoint) || normalizeDisplayText(item.url);
  const fallbackHost = normalizeDisplayText(item.host) || normalizeDisplayText(item.ip);

  // 复合身份（进程/Pod 等）展示末段名称，不回退成主机 IP，也不拼 host:port。
  if (idValues.length > 1) {
    return primaryName || '--';
  }

  if (primaryName && hostPort && !primaryName.includes(hostPort)) {
    return `${primaryName} (${hostPort})`;
  }
  return primaryName || hostPort || endpoint || fallbackHost || normalizeDisplayText(item.instance_id) || '--';
};

export const buildInstanceSearchTokens = (item: any, displayName: string) => {
  const idValues = resolveInstanceIdValues(item);
  const tokens = [
    displayName,
    normalizeDisplayText(item.instance_name),
    normalizeDisplayText(item.name),
    normalizeDisplayText(item.process_name)
  ];

  if (idValues.length > 1) {
    // 复合身份只按末段（process_name / pod 等）搜索，避免主机 IP 命中该主机下全部子实例。
    tokens.push(normalizeDisplayText(idValues[idValues.length - 1]));
  } else {
    tokens.push(
      normalizeDisplayText(item.host),
      normalizeDisplayText(item.ip),
      normalizeDisplayText(item.port),
      normalizeDisplayText(item.endpoint),
      normalizeDisplayText(item.url),
      normalizeDisplayText(item.instance_id)
    );
  }

  return Array.from(new Set(tokens.filter(Boolean)));
};

export interface DashboardInstanceOption {
  label: string;
  value: string;
  instanceIdValues: string[];
  searchTokens?: string[];
  interval?: number;
}

export const buildClusterFilterOptions = (options: readonly DashboardInstanceOption[]) => {
  const seen = new Map<string, { label: string; value: string; searchTokens: string[] }>();
  options.forEach((item) => {
    const cluster = item.instanceIdValues[0];
    if (cluster && !seen.has(cluster)) {
      seen.set(cluster, { label: cluster, value: cluster, searchTokens: [cluster] });
    }
  });
  return Array.from(seen.values());
};

export const filterInstanceOptionsByCluster = (
  options: readonly DashboardInstanceOption[],
  cluster?: string
) => (cluster ? options.filter((item) => item.instanceIdValues[0] === cluster) : [...options]);

export const selectFirstInstanceInCluster = (
  options: readonly DashboardInstanceOption[],
  cluster: string
) => options.find((item) => item.instanceIdValues[0] === cluster);

export const isInstanceOptionForIdentity = (
  option: DashboardInstanceOption,
  instanceId: string | number,
  idValues: readonly string[]
) => {
  if (option.value === String(instanceId || '')) return true;
  if (option.instanceIdValues.length !== idValues.length) return false;
  return option.instanceIdValues.every((value, index) => value === idValues[index]);
};

export const parseLegacyParamList = (value?: string | null) => {
  if (!value) return [] as string[];
  const normalized = value
    .replace(/[()\[\]'"`]/g, '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  return Array.from(new Set(normalized));
};

/** 解析 Python 风格存储键，如 ('host', 'a,b') / ('host',) ，保留值内逗号与引号。 */
export const parsePythonTupleString = (value?: string | null): string[] | null => {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed.startsWith('(') || !trimmed.endsWith(')')) return null;

  const parts: string[] = [];
  let index = 1;
  const end = trimmed.length - 1;
  while (index < end) {
    while (index < end && /[\s,]/.test(trimmed[index])) index += 1;
    if (index >= end) break;
    const quote = trimmed[index];
    if (quote !== "'" && quote !== '"') return null;
    index += 1;
    let current = '';
    while (index < end) {
      const ch = trimmed[index];
      if (ch === '\\' && index + 1 < end) {
        current += trimmed[index + 1];
        index += 2;
        continue;
      }
      if (ch === quote) {
        index += 1;
        break;
      }
      current += ch;
      index += 1;
    }
    parts.push(current);
  }
  return parts.length ? parts : null;
};

const escapePythonTupleValue = (value: string) =>
  String(value).replace(/\\/g, '\\\\').replace(/'/g, "\\'");

export const buildStorageInstanceId = (values: string[]) => {
  const normalizedValues = values
    .map((value) => String(value || '').trim())
    .filter(Boolean);
  if (normalizedValues.length <= 1) {
    return normalizedValues[0] || '';
  }
  return `(${normalizedValues
    .map((value) => `'${escapePythonTupleValue(value)}'`)
    .join(', ')})`;
};

/** 写入 URL 的 instance_id_values：JSON 数组，避免值内逗号被拆坏。 */
export const encodeInstanceIdValuesParam = (values: unknown) => {
  if (Array.isArray(values)) {
    return JSON.stringify(values.map((item) => String(item)));
  }
  if (values == null || values === '') return '';
  return String(values);
};

/** 读取 URL 的 instance_id_values：优先 JSON，其次 tuple，最后兼容旧逗号串。 */
export const parseInstanceIdValuesParam = (value?: string | null): string[] => {
  if (!value) return [];
  const trimmed = value.trim();
  if (!trimmed) return [];
  if (trimmed.startsWith('[')) {
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) {
        return parsed.map((item) => String(item));
      }
    } catch {
      // fall through
    }
  }
  const fromTuple = parsePythonTupleString(trimmed);
  if (fromTuple?.length) return fromTuple;
  return parseLegacyParamList(trimmed);
};

export const resolveDashboardInstanceIdentity = (params: URLSearchParams) => {
  const rawInstanceId = params.get('instance_id') || '';
  const rawInstanceIdValues = params.get('instance_id_values') || '';
  const storageInstanceId =
    rawInstanceId.trim() === '--' ? '' : rawInstanceId.trim();
  const fromStorageTuple = parsePythonTupleString(storageInstanceId);
  const explicitValues = parseInstanceIdValuesParam(rawInstanceIdValues);
  // 旧逻辑对 tuple 存储键做逗号拆解会损坏含 , ' () 的 process_name；优先完整解析。
  const idValues =
    explicitValues.length > 0
      ? explicitValues
      : fromStorageTuple && fromStorageTuple.length > 0
        ? fromStorageTuple
        : storageInstanceId
          ? [storageInstanceId]
          : [];

  const instanceId = storageInstanceId || buildStorageInstanceId(idValues);

  return { instanceId, idValues };
};
