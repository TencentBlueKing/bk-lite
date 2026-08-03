export interface WebsiteRequestKeyValue {
  key?: unknown;
  value?: unknown;
}

const normalizeEntries = (entries: WebsiteRequestKeyValue[] = []) =>
  entries.filter((entry) => String(entry?.key ?? '').trim() || String(entry?.value ?? '').trim());

export const normalizeWebsiteRequestEntries = (
  entries: WebsiteRequestKeyValue[] = [],
  fieldName = '请求参数',
) => {
  const normalized = [];
  for (const entry of normalizeEntries(entries)) {
    const key = String(entry.key ?? '').trim();
    if (!key) throw new Error(`${fieldName}名称不能为空`);
    normalized.push({ key, value: String(entry.value ?? '') });
  }
  return normalized;
};
export const buildWebsiteRequestUrl = (
  baseUrl: string,
  entries: WebsiteRequestKeyValue[] = [],
) => {
  const url = new URL(baseUrl);
  if (url.search) {
    throw new Error('URL 不允许包含 query 参数，请在请求参数中填写');
  }
  if (url.hash) {
    throw new Error('URL 不允许包含 fragment');
  }
  for (const entry of normalizeEntries(entries)) {
    const key = String(entry.key ?? '').trim();
    if (!key) throw new Error('请求参数名称不能为空');
    url.searchParams.append(key, String(entry.value ?? ''));
  }
  return url.toString();
};

export const validateWebsiteRequestHeaders = (entries: WebsiteRequestKeyValue[] = []) => {
  const names = new Set<string>();
  for (const entry of normalizeEntries(entries)) {
    const key = String(entry.key ?? '').trim();
    if (!key) throw new Error('请求头名称不能为空');
    const normalized = key.toLowerCase();
    if (normalized === 'authorization') {
      throw new Error('Authorization 请求头请使用认证配置');
    }
    if (names.has(normalized)) {
      throw new Error(`请求头名称重复：${key}`);
    }
    names.add(normalized);
  }
  return normalizeEntries(entries).map((entry) => ({
    key: String(entry.key).trim(),
    value: String(entry.value ?? ''),
  }));
};

export const splitWebsiteRequestUrl = (requestUrl: string) => {
  const url = new URL(requestUrl);
  const entries: WebsiteRequestKeyValue[] = [];
  url.searchParams.forEach((value, key) => entries.push({ key, value }));
  url.search = '';
  url.hash = '';
  return { baseUrl: url.toString(), entries };
};
