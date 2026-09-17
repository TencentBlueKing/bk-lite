import type { FilterItem } from '@/app/cmdb/store';

/** 与模型字符串 ipv4 校验一致，仅用于列表检索拆分。 */
const IPV4_PATTERN =
  /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;

/** 英文逗号、中文逗号、分号、空格、换行、全角空格均可作为 IP 分隔。 */
const IP_TOKEN_SEPARATORS = /[\s,;，、；]+/;

export const MULTI_IP_SEARCH_ATTR_IDS = new Set(['ip_addr', 'public_ip']);
export const MULTI_IP_SEARCH_LIMIT = 200;

export interface MultiIpParseResult {
  ips: string[];
  invalidCount: number;
  truncated: boolean;
}

export type MultiIpSearchResolution =
  | { action: 'clear'; condition: { field: string }; parsed: MultiIpParseResult }
  | { action: 'reject'; condition: null; parsed: MultiIpParseResult }
  | { action: 'search'; condition: FilterItem; parsed: MultiIpParseResult };

export function isMultiIpSearchAttr(attrId?: string): boolean {
  return !!attrId && MULTI_IP_SEARCH_ATTR_IDS.has(attrId);
}

export function normalizeMultiIpPaste(text: string): string {
  return text.replace(new RegExp(IP_TOKEN_SEPARATORS.source, 'g'), ',').replace(/^,+|,+$/g, '');
}

export function applyMultiIpPaste(
  current: string,
  pasted: string,
  selectionStart = current.length,
  selectionEnd = current.length,
): string {
  return `${current.slice(0, selectionStart)}${normalizeMultiIpPaste(pasted)}${current.slice(selectionEnd)}`;
}

export function formatMultiIpInputValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join(',');
  }
  if (value == null) return '';
  return String(value);
}

export function parseMultiIpSearchInput(raw: unknown): MultiIpParseResult {
  const tokens = formatMultiIpInputValue(raw)
    .split(IP_TOKEN_SEPARATORS)
    .map((token) => token.trim())
    .filter(Boolean);

  const seen = new Set<string>();
  const ips: string[] = [];
  let invalidCount = 0;
  for (const token of tokens) {
    if (!IPV4_PATTERN.test(token)) {
      invalidCount += 1;
      continue;
    }
    if (seen.has(token)) continue;
    seen.add(token);
    ips.push(token);
  }

  const truncated = ips.length > MULTI_IP_SEARCH_LIMIT;
  return {
    ips: truncated ? ips.slice(0, MULTI_IP_SEARCH_LIMIT) : ips,
    invalidCount,
    truncated,
  };
}

export function collectMultiIpSearchNotices(
  resolution: MultiIpSearchResolution,
): Array<{ id: string; values?: Record<string, number> }> {
  if (resolution.action === 'reject') {
    return [{ id: 'FilterBar.multiIpNoValid' }];
  }
  const notices: Array<{ id: string; values?: Record<string, number> }> = [];
  if (resolution.parsed.invalidCount) {
    notices.push({
      id: 'FilterBar.multiIpIgnoredInvalid',
      values: { count: resolution.parsed.invalidCount },
    });
  }
  if (resolution.parsed.truncated) {
    notices.push({
      id: 'FilterBar.multiIpTruncated',
      values: { limit: MULTI_IP_SEARCH_LIMIT },
    });
  }
  return notices;
}

export function resolveMultiIpSearch(
  field: string,
  raw: unknown,
  isExact?: boolean,
): MultiIpSearchResolution {
  const parsed = parseMultiIpSearchInput(raw);
  const blank = !formatMultiIpInputValue(raw).trim();

  if (blank) {
    return { action: 'clear', condition: { field }, parsed };
  }
  if (!parsed.ips.length) {
    return { action: 'reject', condition: null, parsed };
  }
  if (parsed.ips.length === 1) {
    return {
      action: 'search',
      condition: {
        field,
        type: isExact ? 'str=' : 'str*',
        value: parsed.ips[0],
      },
      parsed,
    };
  }
  return {
    action: 'search',
    condition: {
      field,
      type: 'str[]',
      value: parsed.ips,
    },
    parsed,
  };
}
