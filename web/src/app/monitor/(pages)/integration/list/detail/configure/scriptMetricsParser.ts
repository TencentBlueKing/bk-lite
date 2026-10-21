export interface BusinessMetricItem {
  /** 脚本 stdout 短名；勾选、分组、单位与落库均按名。 */
  key: string;
  name: string;
  value: number | string;
  tags?: Record<string, string>;
  /** 同一短名下的全部采样；确认只写一行。 */
  samples?: Array<{ value: number | string; tags?: Record<string, string> }>;
  /** 脚本占用的保留标签键，确认时拦截。 */
  reservedTagKeys?: string[];
  /** 指标目录分组 ID，确认时写入 metric_group。 */
  metric_group?: number | null;
  /** 指标目录单位 ID（Cascader 叶子 unit_id）。 */
  unit?: string;
  /** 指标目录描述，允许空字符串。 */
  description?: string;
  /** 指标目录数据类型，已有枚举指标不改单位。 */
  data_type?: string;
  /** 用户在调试表改过分组时，已有指标才 PATCH metric_group。 */
  editedGroup?: boolean;
  /** 用户在调试表改过单位时，已有指标才 PATCH unit。 */
  editedUnit?: boolean;
}

export type ScriptOutputFormat =
  | 'prometheus'
  | 'influx'
  | 'key_value'
  | 'mixed'
  | 'empty'
  | 'unknown';

export type ScriptOutputLineIssueCode =
  | 'influx'
  | 'key_value'
  | 'invalid'
  | 'unquoted_labels'
  | 'missing_value'
  | 'invalid_name'
  | 'invalid_value';

export interface ScriptOutputLineIssue {
  line: number;
  text: string;
  code: ScriptOutputLineIssueCode;
}

export interface ParsedScriptOutput {
  selfMetrics: {
    up: number;
    duration_ms?: number;
    exit_code: number;
  };
  businessMetrics: BusinessMetricItem[];
  hasMetrics: boolean;
  isTruncated: boolean;
  isTimeout: boolean;
  isNodeUnavailable: boolean;
  outputFormat: ScriptOutputFormat;
  lineIssues: ScriptOutputLineIssue[];
  unsupportedProductionFormat: boolean;
  exceedsSeriesLimit: boolean;
  seriesCount: number;
}

export const SCRIPT_MAX_SERIES = 50;

const SELF_METRIC_NAMES = new Set(['up', 'duration', 'duration_ms', 'duration_seconds', 'exit_code', 'run_duration']);
/** 展示层隐藏的平台内置维度。精确 key，不做前缀匹配。 */
export const HIDDEN_PLATFORM_TAG_KEYS = new Set([
  'instance_id',
  'agent_id',
  'plugin_id',
  'instance_type',
  'collect_type',
  'config_id',
  'config_type',
  'host',
  'script',
  'bklite_script_reserved_keys'
]);
/** @deprecated 展示层已全部隐藏平台内置维度；保留空集以免旧调用方误放开。 */
export const VISIBLE_PLATFORM_TAG_KEYS = new Set<string>();
/** 脚本自定义标签不得使用。精确 key，不做前缀匹配。 */
export const RESERVED_SCRIPT_TAG_KEYS = new Set([
  'instance_id',
  'instance_type',
  'collect_type',
  'config_type',
  'plugin_id',
  'agent_id',
  'config_id',
  'script'
]);
const RESERVED_CONFLICT_TAG = 'bklite_script_reserved_keys';
const UNRENDERED_PLACEHOLDER_RE = /\$\{[^}]+\}|\{\{[^}]+\}\}/;
const NUMERIC_OR_DETECT_PREFIX_RE = /^(?:detect_)?\d+_/;
const HEX32_PREFIX_RE = /^[A-Fa-f0-9]{32}_/;
const HEALTH_LEAF_RE = /^(?:parse_errors|truncated|up|duration(?:_ms|_seconds)?|exit_code)$/i;
const SCRIPT_HEALTH_NAME_RE =
  /(?:^|_)bklite_script_(?:parse_errors|truncated|up|duration(?:_ms|_seconds)?|exit_code)(?:_|$)/i;

export const normalizeIsolationPrefixes = (raw: unknown): string[] => {
  if (!Array.isArray(raw)) {
    return [];
  }
  const prefixes: string[] = [];
  raw.forEach((item) => {
    const text = String(item || '');
    if (text && !prefixes.includes(text)) {
      prefixes.push(text);
    }
  });
  return prefixes;
};

const PROMETHEUS_MEASUREMENT_PREFIX = 'prometheus_';

const isProtectedSelfMonitorName = (name: string): boolean => {
  const lower = String(name || '').toLowerCase();
  if (!lower) {
    return false;
  }
  if (lower === 'bklite_script' || HEALTH_LEAF_RE.test(lower)) {
    return true;
  }
  if (SCRIPT_HEALTH_NAME_RE.test(lower)) {
    return true;
  }
  if (lower.startsWith('bklite_script_')) {
    return HEALTH_LEAF_RE.test(lower.slice('bklite_script_'.length));
  }
  return lower.startsWith('bklite_script.');
};

/**
 * 去掉隔离前缀与 prometheus_ measurement 前缀，得到脚本 stdout 名。
 * 自监控 bklite_script_* / 健康叶名保持平台名。
 * 例：bklite_script_2_prometheus_mock_requests_total -> mock_requests_total
 *     prometheus_host_cpu_usage_percent -> host_cpu_usage_percent
 */
export const cleanMeasurementName = (rawName: string, isolationPrefixes: string[] = []): string => {
  let name = String(rawName || '');
  let changed = true;
  while (name && changed) {
    changed = false;
    for (const prefix of isolationPrefixes) {
      if (prefix && name.startsWith(prefix) && name.length > prefix.length) {
        name = name.slice(prefix.length);
        changed = true;
      }
    }
    if (name.startsWith('bklite_script_')) {
      const after = name.slice('bklite_script_'.length);
      // 健康指标本身是 bklite_script_parse_errors，不能把 parse_ 当成 config_id 剥掉。
      if (!HEALTH_LEAF_RE.test(after)) {
        const isolation = after.match(/^([^_]+)_/);
        if (isolation) {
          name = after.slice(isolation[0].length);
          changed = true;
          continue;
        }
      }
    }
    if (NUMERIC_OR_DETECT_PREFIX_RE.test(name)) {
      name = name.replace(NUMERIC_OR_DETECT_PREFIX_RE, '');
      changed = true;
      continue;
    }
    if (HEX32_PREFIX_RE.test(name)) {
      name = name.replace(HEX32_PREFIX_RE, '');
      changed = true;
      continue;
    }
    if (name.toLowerCase().startsWith(PROMETHEUS_MEASUREMENT_PREFIX)) {
      const rest = name.slice(PROMETHEUS_MEASUREMENT_PREFIX.length);
      if (rest && !isProtectedSelfMonitorName(rest)) {
        name = rest;
        changed = true;
      }
    }
  }
  return name;
};

/** 展示层隐藏平台内置维度；精确黑名单，无前缀匹配。 */
export const isHiddenPlatformDimensionKey = (key: string): boolean => {
  const tagKey = String(key || '').trim();
  if (!tagKey) {
    return true;
  }
  if (HIDDEN_PLATFORM_TAG_KEYS.has(tagKey)) {
    return true;
  }
  return tagKey.toLowerCase().startsWith('bklite_script_');
};

export const visibleDimensionItems = <T extends { name?: string }>(
  items: T[] = []
): T[] =>
  items.filter((item) => {
    const name = String(item?.name || '').trim();
    return Boolean(name) && !isHiddenPlatformDimensionKey(name);
  });

export const isSelfMetricName = (name: string, isolationPrefixes: string[] = []): boolean => {
  const raw = String(name || '');
  const cleaned = cleanMeasurementName(raw, isolationPrefixes);
  return [raw, cleaned].some((candidate) => {
    const lower = candidate.toLowerCase();
    if (!lower) {
      return false;
    }
    if (lower.startsWith('bklite_script_') || lower.startsWith('bklite_script.')) {
      return true;
    }
    if (SELF_METRIC_NAMES.has(lower) || lower === 'bklite_script') {
      return true;
    }
    return SCRIPT_HEALTH_NAME_RE.test(lower);
  });
};

export const isReservedScriptTagKey = (key: string): boolean => {
  const tagKey = String(key || '').trim();
  if (!tagKey) {
    return false;
  }
  const lower = tagKey.toLowerCase();
  if (RESERVED_SCRIPT_TAG_KEYS.has(tagKey) || RESERVED_SCRIPT_TAG_KEYS.has(lower)) {
    return true;
  }
  return lower.startsWith('bklite_script_');
};

/** 指标 ID 黑名单：保留标签 + config_id + bklite_script_ 前缀。 */
export const RESERVED_SCRIPT_METRIC_NAMES = new Set<string>([
  ...RESERVED_SCRIPT_TAG_KEYS,
  'config_id'
]);

export const isReservedScriptMetricId = (name: string): boolean => {
  const text = String(name || '').trim();
  if (!text) {
    return false;
  }
  const lower = text.toLowerCase();
  if (
    RESERVED_SCRIPT_METRIC_NAMES.has(text) ||
    RESERVED_SCRIPT_METRIC_NAMES.has(lower)
  ) {
    return true;
  }
  return lower.startsWith('bklite_script_');
};

export const collectReservedScriptTagKeys = (
  tags?: Record<string, string>
): string[] => {
  if (!tags) {
    return [];
  }
  const found: string[] = [];
  const mark = (key: string) => {
    if (key && !found.includes(key)) {
      found.push(key);
    }
  };
  const marker = String(tags[RESERVED_CONFLICT_TAG] || '');
  marker
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .forEach(mark);
  Object.keys(tags).forEach((key) => {
    const tagKey = String(key || '').trim();
    if (!tagKey || tagKey === RESERVED_CONFLICT_TAG) {
      return;
    }
    if (tagKey.toLowerCase().startsWith('bklite_script_')) {
      mark(tagKey);
    }
  });
  return found;
};

export const keepStoredTags = (
  tags?: Record<string, string>
): Record<string, string> | undefined => {
  if (!tags) {
    return undefined;
  }
  const out: Record<string, string> = {};
  Object.entries(tags).forEach(([key, raw]) => {
    const tagKey = String(key || '').trim();
    const tagValue = raw == null ? '' : String(raw);
    if (!tagKey || tagKey === RESERVED_CONFLICT_TAG) {
      return;
    }
    if (!tagValue || UNRENDERED_PLACEHOLDER_RE.test(tagKey) || UNRENDERED_PLACEHOLDER_RE.test(tagValue)) {
      return;
    }
    if (out[tagKey] === undefined) {
      out[tagKey] = tagValue;
    }
  });
  return Object.keys(out).length ? out : undefined;
};

export const cleanDisplayTags = (
  tags?: Record<string, string>
): Record<string, string> | undefined => {
  const stored = keepStoredTags(tags);
  if (!stored) {
    return undefined;
  }
  const out: Record<string, string> = {};
  Object.entries(stored).forEach(([tagKey, tagValue]) => {
    if (isHiddenPlatformDimensionKey(tagKey)) {
      return;
    }
    out[tagKey] = tagValue;
  });
  return Object.keys(out).length ? out : undefined;
};

export const formatScriptMetricLabels = (
  tags?: Record<string, string>
): string => {
  const visible = cleanDisplayTags(tags);
  if (!visible) {
    return '';
  }
  return Object.entries(visible)
    .map(([key, value]) => `${key}="${value}"`)
    .join(', ');
};

/** 展示层只显示维度名；平台内置维度仍隐藏。跨采样取并集。 */
export const unionVisibleDimensionNames = (
  tags?: Record<string, string>,
  samples?: Array<{ tags?: Record<string, string> }>
): string[] => {
  const names: string[] = [];
  const add = (source?: Record<string, string>) => {
    Object.keys(cleanDisplayTags(source) || {}).forEach((key) => {
      if (!names.includes(key)) {
        names.push(key);
      }
    });
  };
  add(tags);
  samples?.forEach((sample) => add(sample.tags));
  return names;
};

const mergeStoredTags = (
  current?: Record<string, string>,
  incoming?: Record<string, string>
): Record<string, string> | undefined => {
  if (!incoming) {
    return current;
  }
  if (!current) {
    return { ...incoming };
  }
  const merged = { ...current };
  Object.entries(incoming).forEach(([key, value]) => {
    if (merged[key] === undefined) {
      merged[key] = value;
    }
  });
  return merged;
};

const mergeReservedTagKeys = (
  current: string[] | undefined,
  incoming: string[]
): string[] => {
  const merged = [...(current || [])];
  incoming.forEach((key) => {
    if (key && !merged.includes(key)) {
      merged.push(key);
    }
  });
  return merged;
};

/**
 * 解析 Influx Line Protocol 格式行
 * 格式：measurement[,tag_k=tag_v...] field_k=field_v[,field_k2=field_v2...] [timestamp]
 */
const parseInfluxLine = (
  line: string,
  isolationPrefixes: string[]
): { measurement: string; tags: Record<string, string>; fields: Record<string, any> } | null => {
  const parts = line.trim().split(/\s+/);
  if (parts.length < 2) return null;

  const headerPart = parts[0];
  const fieldsPart = parts[1];

  const headerTokens = headerPart.split(',');
  const measurement = cleanMeasurementName(headerTokens[0], isolationPrefixes);
  const tags: Record<string, string> = {};
  for (let i = 1; i < headerTokens.length; i++) {
    const eqIdx = headerTokens[i].indexOf('=');
    if (eqIdx !== -1) {
      tags[headerTokens[i].slice(0, eqIdx)] = headerTokens[i].slice(eqIdx + 1);
    }
  }

  const fieldTokens = fieldsPart.split(',');
  const fields: Record<string, any> = {};
  for (const token of fieldTokens) {
    const eqIdx = token.indexOf('=');
    if (eqIdx !== -1) {
      const k = token.slice(0, eqIdx);
      let v: any = token.slice(eqIdx + 1);
      // 去掉整数后缀 i
      if (typeof v === 'string' && v.endsWith('i') && !isNaN(Number(v.slice(0, -1)))) {
        v = Number(v.slice(0, -1));
      } else if (!isNaN(Number(v))) {
        v = Number(v);
      } else if (v.startsWith('"') && v.endsWith('"')) {
        v = v.slice(1, -1);
      }
      fields[k] = v;
    }
  }

  if (Object.keys(fields).length === 0) return null;

  return { measurement, tags, fields };
};

const PROM_METRIC_NAME_RE = /^[A-Za-z_:][A-Za-z0-9_:]*$/;
const PROM_VALUE_RE =
  /^(?:[+-]?(?:NaN|Inf(?:inity)?|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?))$/i;

const parsePromLabels = (
  raw: string
): { tags: Record<string, string>; ok: boolean } => {
  const tags: Record<string, string> = {};
  const remain = raw.trim();
  if (!remain) {
    return { tags, ok: true };
  }
  const re = /([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*"([^"]*)"\s*(?:,\s*|$)/g;
  let last = 0;
  let match: RegExpExecArray | null = re.exec(remain);
  while (match) {
    if (match.index !== last) {
      return { tags, ok: false };
    }
    tags[match[1]] = match[2];
    last = re.lastIndex;
    match = re.exec(remain);
  }
  if (last !== remain.length) {
    return { tags, ok: false };
  }
  return { tags, ok: true };
};

const inspectPrometheusLine = (
  line: string,
  isolationPrefixes: string[]
):
  | { status: 'ok'; name: string; value: number; tags: Record<string, string> }
  | { status: ScriptOutputLineIssueCode } => {
  const promMatch = line.match(
    /^([A-Za-z0-9_:][A-Za-z0-9_:]*)(?:\{([^}]*)\})?(?:\s+(.+))?$/
  );
  if (!promMatch) {
    return { status: 'invalid' };
  }
  const rawName = promMatch[1];
  if (!PROM_METRIC_NAME_RE.test(rawName)) {
    return { status: 'invalid_name' };
  }
  const labelsRaw = promMatch[2];
  const rest = (promMatch[3] || '').trim();
  let tags: Record<string, string> = {};
  if (labelsRaw != null) {
    const parsed = parsePromLabels(labelsRaw);
    if (!parsed.ok) {
      return { status: 'unquoted_labels' };
    }
    tags = parsed.tags;
  }
  if (!rest) {
    return { status: 'missing_value' };
  }
  const valStr = rest.split(/\s+/)[0];
  if (!PROM_VALUE_RE.test(valStr)) {
    return { status: 'invalid_value' };
  }
  return {
    status: 'ok',
    name: cleanMeasurementName(rawName, isolationPrefixes),
    value: Number(valStr),
    tags
  };
};

const looksLikeInfluxLine = (line: string): boolean => {
  if (line.includes('{') || line.includes('}')) {
    return false;
  }
  const parts = line.trim().split(/\s+/);
  if (parts.length < 2) {
    return false;
  }
  return parts[1].includes('=');
};

const looksLikeKeyValueLine = (line: string): boolean =>
  !line.includes('{') &&
  /^[A-Za-z0-9_:][A-Za-z0-9_:]*\s*[:=]\s*\S+$/.test(line);

/** 探测侧车把 Telegraf 日志 / Influx dump 写进 stdout，不能当成脚本 stdout。 */
export const isCollectorSidecarNoise = (line: string): boolean => {
  const text = String(line || '').trim();
  if (!text) {
    return false;
  }
  if (/^\d{4}-\d{2}-\d{2}T\S+\s+[IWED]!/.test(text)) {
    return true;
  }
  if (/^[IWED]!(?:\s|$)/.test(text)) {
    return true;
  }
  if (/^time=/.test(text)) {
    return true;
  }
  if (/\blevel=(?:debug|info|warn|warning|error)\b/i.test(text) && /\bmsg=/.test(text)) {
    return true;
  }
  if (/^Loading config\b/i.test(text)) {
    return true;
  }
  if (/^Starting Telegraf\b/i.test(text)) {
    return true;
  }
  if (/^Available plugins\b/i.test(text)) {
    return true;
  }
  if (/^Loaded (?:inputs|outputs|processors|aggregators|secretstores)\b/i.test(text)) {
    return true;
  }
  if (/^Tags enabled\b/i.test(text)) {
    return true;
  }
  if (/^Error running agent\b/i.test(text)) {
    return true;
  }
  if (/^\[(?:inputs|outputs|processors|aggregators|agent)\b/i.test(text)) {
    return true;
  }
  return false;
};

const COLLECTOR_IDENTITY_TAG_KEYS = new Set([
  'collect_type',
  'instance_id',
  'config_id',
  'plugin_id',
  'agent_id',
  'instance_type',
  'config_type'
]);

const hasCollectorIdentityTags = (tags: Record<string, string>): boolean =>
  Object.keys(tags).some((key) => COLLECTOR_IDENTITY_TAG_KEYS.has(key.toLowerCase()));

const INFLUX_VALUE_FIELD_PREFERENCE = ['value', 'gauge', 'counter', 'untyped', 'untimed'];

const numericFieldEntries = (fields: Record<string, any>): Array<[string, number]> =>
  Object.entries(fields).flatMap(([key, raw]) =>
    typeof raw === 'number' && Number.isFinite(raw) ? [[key, raw] as [string, number]] : []
  );

const pickInfluxSampleValue = (fields: Record<string, any>): number | undefined => {
  for (const key of INFLUX_VALUE_FIELD_PREFERENCE) {
    const raw = fields[key];
    if (typeof raw === 'number' && Number.isFinite(raw)) {
      return raw;
    }
  }
  const numeric = numericFieldEntries(fields);
  return numeric.length ? numeric[0][1] : undefined;
};

export const parseScriptMetrics = (
  result: Record<string, any> = {},
  startedAt?: string | null,
  finishedAt?: string | null,
  errorMessage?: string
): ParsedScriptOutput => {
  const stdout = String(result?.stdout || result?.result || '').trim();
  const stderr = String(result?.stderr || result?.error || errorMessage || '').trim();
  const isolationPrefixes = normalizeIsolationPrefixes(result?.isolation_name_prefixes);

  let exitCode = 0;
  if (result?.exit_code !== undefined && result?.exit_code !== null) {
    exitCode = Number(result.exit_code);
  } else if (result?.success === false) {
    exitCode = 1;
  }

  let durationMs: number | undefined = result?.duration_ms;
  if (durationMs === undefined && startedAt && finishedAt) {
    const s = new Date(startedAt).getTime();
    const f = new Date(finishedAt).getTime();
    if (!isNaN(s) && !isNaN(f) && f >= s) {
      durationMs = f - s;
    }
  }

  let up = exitCode === 0 ? 1 : 0;
  const metricsByName = new Map<string, BusinessMetricItem>();

  const isTruncated = Boolean(result?.stdout_truncated || result?.stderr_truncated);
  const isTimeout = Boolean(
    stderr.toLowerCase().includes('timeout') ||
    stderr.toLowerCase().includes('timed out') ||
    stdout.toLowerCase().includes('timeout') ||
    stdout.toLowerCase().includes('timed out')
  );
  const isNodeUnavailable = Boolean(
    stderr.includes('节点不存在') ||
    stderr.includes('无法连接') ||
    stderr.toLowerCase().includes('node unavailable') ||
    stderr.toLowerCase().includes('agent offline')
  );

  const pushBusinessMetric = (name: string, value: number | string, tags?: Record<string, string>) => {
    const stdoutName = cleanMeasurementName(name, isolationPrefixes);
    if (!stdoutName || isSelfMetricName(stdoutName, isolationPrefixes)) {
      return;
    }
    const storedTags = keepStoredTags(tags);
    const reservedTagKeys = collectReservedScriptTagKeys(tags);
    const sample = { value, tags: storedTags };
    // 按 stdout 短名合并：多样本同一指标只占一行，不算重复 ID。
    const existing = metricsByName.get(stdoutName);
    if (!existing) {
      metricsByName.set(stdoutName, {
        key: stdoutName,
        name: stdoutName,
        value,
        tags: storedTags,
        reservedTagKeys,
        samples: [sample]
      });
      return;
    }
    existing.samples = [...(existing.samples || []), sample];
    existing.tags = mergeStoredTags(existing.tags, storedTags);
    existing.reservedTagKeys = mergeReservedTagKeys(
      existing.reservedTagKeys,
      reservedTagKeys
    );
  };

  const lineIssues: ScriptOutputLineIssue[] = [];
  let sawPrometheus = false;
  let sawInflux = false;
  let sawKeyValue = false;
  let sawCollectorInflux = false;
  let seriesCount = 0;

  const applySelfMetricValue = (name: string, value: number) => {
    const lowerName = name.toLowerCase();
    if (lowerName.includes('up')) up = value;
    if (lowerName.includes('exit_code')) exitCode = value;
    if (lowerName.includes('duration')) {
      durationMs = lowerName.includes('second') ? Math.round(value * 1000) : value;
    }
  };

  const ingestCollectorInflux = (line: string): boolean => {
    const parsed = parseInfluxLine(line, isolationPrefixes);
    if (!parsed) {
      return false;
    }
    sawCollectorInflux = true;
    const { measurement, tags, fields } = parsed;
    const numeric = numericFieldEntries(fields);
    if (isSelfMetricName(measurement, isolationPrefixes)) {
      numeric.forEach(([fieldName, value]) => {
        applySelfMetricValue(fieldName.includes('up') || fieldName.includes('duration') || fieldName.includes('exit')
          ? fieldName
          : measurement, value);
      });
      return true;
    }
    if (measurement.toLowerCase() === 'prometheus') {
      numeric.forEach(([fieldName, value]) => {
        if (isSelfMetricName(fieldName, isolationPrefixes)) {
          applySelfMetricValue(fieldName, value);
          return;
        }
        seriesCount += 1;
        pushBusinessMetric(fieldName, value, tags);
      });
      return true;
    }
    const value = pickInfluxSampleValue(fields);
    if (value === undefined) {
      return true;
    }
    seriesCount += 1;
    pushBusinessMetric(measurement, value, tags);
    return true;
  };

  if (stdout) {
    const lines = stdout.split(/\r?\n/);
    lines.forEach((rawLine, index) => {
      const line = rawLine.trim();
      if (!line || line.startsWith('#')) return;
      if (isCollectorSidecarNoise(line)) return;
      const lineNo = index + 1;
      const pushIssue = (code: ScriptOutputLineIssueCode) => {
        lineIssues.push({ line: lineNo, text: line, code });
      };

      const promData = inspectPrometheusLine(line, isolationPrefixes);
      if (promData.status === 'ok') {
        sawPrometheus = true;
        const { name, value, tags } = promData;
        if (isSelfMetricName(name, isolationPrefixes)) {
          if (typeof value === 'number') {
            applySelfMetricValue(name, value);
          }
          return;
        }
        seriesCount += 1;
        pushBusinessMetric(name, value, tags);
        return;
      }
      if (line.includes('{') || line.includes('}')) {
        pushIssue(promData.status);
        return;
      }
      if (looksLikeInfluxLine(line)) {
        const influx = parseInfluxLine(line, isolationPrefixes);
        if (influx && hasCollectorIdentityTags(influx.tags)) {
          ingestCollectorInflux(line);
          return;
        }
        if (influx) {
          sawInflux = true;
          pushIssue('influx');
          return;
        }
      }
      if (looksLikeKeyValueLine(line)) {
        sawKeyValue = true;
        pushIssue('key_value');
        return;
      }
      pushIssue(promData.status === 'invalid' ? 'invalid' : promData.status);
    });
  }

  const formatFlags = [sawPrometheus, sawInflux, sawKeyValue].filter(Boolean).length;
  let outputFormat: ScriptOutputFormat = 'empty';
  if (formatFlags > 1) {
    outputFormat = 'mixed';
  } else if (sawPrometheus || (sawCollectorInflux && !sawInflux && !sawKeyValue && !lineIssues.length)) {
    outputFormat = 'prometheus';
  } else if (sawInflux) {
    outputFormat = 'influx';
  } else if (sawKeyValue) {
    outputFormat = 'key_value';
  } else if (lineIssues.length) {
    outputFormat = 'unknown';
  } else if (sawCollectorInflux) {
    outputFormat = 'prometheus';
  }

  const businessMetrics = Array.from(metricsByName.values());
  return {
    selfMetrics: {
      up,
      duration_ms: durationMs,
      exit_code: exitCode
    },
    businessMetrics,
    hasMetrics: businessMetrics.length > 0,
    isTruncated,
    isTimeout,
    isNodeUnavailable,
    outputFormat,
    lineIssues,
    unsupportedProductionFormat: sawInflux || sawKeyValue,
    exceedsSeriesLimit: seriesCount > SCRIPT_MAX_SERIES,
    seriesCount
  };
};
