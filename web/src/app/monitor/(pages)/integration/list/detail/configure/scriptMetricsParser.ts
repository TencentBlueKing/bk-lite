export interface BusinessMetricItem {
  key: string;
  name: string;
  value: number | string;
  tags?: Record<string, string>;
  /** 脚本占用的保留标签键，确认时拦截。 */
  reservedTagKeys?: string[];
  /** 指标目录分组 ID，确认时写入 metric_group。 */
  metric_group?: number | null;
  /** 指标目录单位 ID（Cascader 叶子 unit_id）。 */
  unit?: string;
  /** 指标目录描述，允许空字符串。 */
  description?: string;
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
}

const SELF_METRIC_NAMES = new Set(['up', 'duration', 'duration_ms', 'duration_seconds', 'exit_code', 'run_duration']);
const GENERIC_INFLUX_FIELDS = new Set(['value', 'gauge', 'counter', 'untyped']);
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
  if (HIDDEN_PLATFORM_TAG_KEYS.has(tagKey) || RESERVED_SCRIPT_TAG_KEYS.has(tagKey)) {
    return true;
  }
  return tagKey.toLowerCase().startsWith('bklite_script_');
};

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
  if (RESERVED_SCRIPT_TAG_KEYS.has(tagKey)) {
    return true;
  }
  return tagKey.toLowerCase().startsWith('bklite_script_');
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

export const cleanDisplayTags = (
  tags?: Record<string, string>
): Record<string, string> | undefined => {
  if (!tags) {
    return undefined;
  }
  const out: Record<string, string> = {};
  Object.entries(tags).forEach(([key, raw]) => {
    const tagKey = String(key || '').trim();
    const tagValue = raw == null ? '' : String(raw);
    if (isHiddenPlatformDimensionKey(tagKey)) {
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

const businessMetricName = (measurement: string, fieldName: string): string => {
  const meas = String(measurement || '');
  const field = String(fieldName || '');
  // Telegraf prometheus 封装：measurement=prometheus，字段才是脚本 stdout 名。
  if (meas.toLowerCase() === 'prometheus' && field && !GENERIC_INFLUX_FIELDS.has(field.toLowerCase())) {
    return field;
  }
  if (!field || meas === field || GENERIC_INFLUX_FIELDS.has(field.toLowerCase())) {
    return meas;
  }
  return `${meas}_${field}`;
};

const stableTagKey = (tags?: Record<string, string>): string => {
  if (!tags) {
    return '';
  }
  return Object.keys(tags)
    .sort()
    .map((key) => `${key}=${tags[key]}`)
    .join(',');
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

/**
 * 解析 Prometheus 格式行
 * 格式：metric_name{tag1="val1"} 123
 */
const parsePrometheusLine = (
  line: string,
  isolationPrefixes: string[]
): { name: string; value: number | string; tags: Record<string, string> } | null => {
  const promMatch = line.match(/^([A-Za-z0-9_:][A-Za-z0-9_:]*)(?:\{([^}]*)\})?\s+([^\s]+)(?:\s+\d+)?$/);
  if (!promMatch) return null;

  const name = cleanMeasurementName(promMatch[1], isolationPrefixes);
  const tagsStr = promMatch[2] || '';
  const valStr = promMatch[3];
  const tags: Record<string, string> = {};

  if (tagsStr) {
    const tagPairs = tagsStr.match(/([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*"([^"]*)"/g);
    if (tagPairs) {
      tagPairs.forEach((pair) => {
        const [k, v] = pair.split('=').map((s) => s.trim().replace(/^"|"$/g, ''));
        if (k && v !== undefined) tags[k] = v;
      });
    }
  }

  const value = !isNaN(Number(valStr)) ? Number(valStr) : valStr;
  return { name, value, tags };
};

/**
 * 解析简单 key=value 或 key: value 格式
 */
const parseKeyValueLine = (
  line: string,
  isolationPrefixes: string[]
): { name: string; value: number | string } | null => {
  const kvMatch = line.match(/^([A-Za-z0-9_:][A-Za-z0-9_:]*)\s*[:=]\s*([^\s]+)$/);
  if (!kvMatch) return null;
  const name = cleanMeasurementName(kvMatch[1], isolationPrefixes);
  const valStr = kvMatch[2];
  const value = !isNaN(Number(valStr)) ? Number(valStr) : valStr;
  return { name, value };
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
  const businessMetrics: BusinessMetricItem[] = [];
  const seenKeys = new Set<string>();

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
    const cleanedTags = cleanDisplayTags(tags);
    const reservedTagKeys = collectReservedScriptTagKeys(tags);
    const metricKey = `${stdoutName}|${stableTagKey(cleanedTags)}`;
    if (seenKeys.has(metricKey)) {
      return;
    }
    seenKeys.add(metricKey);
    businessMetrics.push({
      key: metricKey,
      name: stdoutName,
      value,
      tags: cleanedTags,
      reservedTagKeys
    });
  };

  if (stdout) {
    const lines = stdout.split('\n');
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line || line.startsWith('#')) continue;

      // 1. 尝试 Influx Line Protocol
      const influxData = parseInfluxLine(line, isolationPrefixes);
      if (influxData) {
        const { measurement, tags, fields } = influxData;
        for (const [fieldName, fieldValue] of Object.entries(fields)) {
          const lowerName = fieldName.toLowerCase();
          if (
            isSelfMetricName(fieldName, isolationPrefixes) ||
            isSelfMetricName(measurement, isolationPrefixes)
          ) {
            if (lowerName.includes('up') && typeof fieldValue === 'number') up = fieldValue;
            if (lowerName.includes('exit_code') && typeof fieldValue === 'number') exitCode = fieldValue;
            if (lowerName.includes('duration') && typeof fieldValue === 'number') {
              durationMs = lowerName.includes('second') ? Math.round(fieldValue * 1000) : fieldValue;
            }
            continue;
          }
          pushBusinessMetric(businessMetricName(measurement, fieldName), fieldValue, tags);
        }
        continue;
      }

      // 2. 尝试 Prometheus Line
      const promData = parsePrometheusLine(line, isolationPrefixes);
      if (promData) {
        const { name, value, tags } = promData;
        const lowerName = name.toLowerCase();
        if (isSelfMetricName(name, isolationPrefixes)) {
          if (lowerName.includes('up') && typeof value === 'number') up = value;
          if (lowerName.includes('exit_code') && typeof value === 'number') exitCode = value;
          if (lowerName.includes('duration') && typeof value === 'number') {
            durationMs = lowerName.includes('second') ? Math.round(value * 1000) : value;
          }
          continue;
        }
        pushBusinessMetric(name, value, tags);
        continue;
      }

      // 3. 尝试 Key-Value Line
      const kvData = parseKeyValueLine(line, isolationPrefixes);
      if (kvData) {
        const { name, value } = kvData;
        const lowerName = name.toLowerCase();
        if (isSelfMetricName(name, isolationPrefixes)) {
          if (lowerName.includes('up') && typeof value === 'number') up = value;
          if (lowerName.includes('exit_code') && typeof value === 'number') exitCode = value;
          if (lowerName.includes('duration') && typeof value === 'number') {
            durationMs = lowerName.includes('second') ? Math.round(value * 1000) : value;
          }
          continue;
        }
        pushBusinessMetric(name, value);
      }
    }
  }

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
    isNodeUnavailable
  };
};
