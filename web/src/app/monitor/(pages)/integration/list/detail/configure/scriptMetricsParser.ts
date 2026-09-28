export interface BusinessMetricItem {
  key: string;
  name: string;
  value: number | string;
  tags?: Record<string, string>;
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

export const isSelfMetricName = (name: string): boolean => {
  const lower = name.toLowerCase();
  if (lower.startsWith('bklite_script_') || lower.startsWith('bklite_script.')) {
    return true;
  }
  return (
    SELF_METRIC_NAMES.has(lower) ||
    lower === 'bklite_script'
  );
};

/**
 * 清理 measurement 前缀（例如 bklite_script_123_disk_free -> disk_free）
 */
const cleanMeasurementName = (rawName: string): string => {
  return rawName.replace(/^bklite_script_[^_]+_/, '');
};

/**
 * 解析 Influx Line Protocol 格式行
 * 格式：measurement[,tag_k=tag_v...] field_k=field_v[,field_k2=field_v2...] [timestamp]
 */
const parseInfluxLine = (line: string): { measurement: string; tags: Record<string, string>; fields: Record<string, any> } | null => {
  const parts = line.trim().split(/\s+/);
  if (parts.length < 2) return null;

  const headerPart = parts[0];
  const fieldsPart = parts[1];

  const headerTokens = headerPart.split(',');
  const measurement = cleanMeasurementName(headerTokens[0]);
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
const parsePrometheusLine = (line: string): { name: string; value: number | string; tags: Record<string, string> } | null => {
  const promMatch = line.match(/^([a-zA-Z_][a-zA-Z0-9_]*)(?:\{([^}]*)\})?\s+([^\s]+)(?:\s+\d+)?$/);
  if (!promMatch) return null;

  const name = cleanMeasurementName(promMatch[1]);
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
const parseKeyValueLine = (line: string): { name: string; value: number | string } | null => {
  const kvMatch = line.match(/^([a-zA-Z_][a-zA-Z0-9_]*)\s*[:=]\s*([^\s]+)$/);
  if (!kvMatch) return null;
  const name = cleanMeasurementName(kvMatch[1]);
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

  if (stdout) {
    const lines = stdout.split('\n');
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line || line.startsWith('#')) continue;

      // 1. 尝试 Influx Line Protocol
      const influxData = parseInfluxLine(line);
      if (influxData) {
        const { measurement, tags, fields } = influxData;
        for (const [fieldName, fieldValue] of Object.entries(fields)) {
          const lowerName = fieldName.toLowerCase();
          if (isSelfMetricName(fieldName) || isSelfMetricName(measurement)) {
            if (lowerName.includes('up') && typeof fieldValue === 'number') up = fieldValue;
            if (lowerName.includes('exit_code') && typeof fieldValue === 'number') exitCode = fieldValue;
            if (lowerName.includes('duration') && typeof fieldValue === 'number') {
              durationMs = lowerName.includes('second') ? Math.round(fieldValue * 1000) : fieldValue;
            }
            continue;
          }
          const metricKey = `${measurement}.${fieldName}`;
          if (!seenKeys.has(metricKey)) {
            seenKeys.add(metricKey);
            businessMetrics.push({
              key: metricKey,
              name: measurement === fieldName ? measurement : `${measurement}_${fieldName}`,
              value: fieldValue,
              tags: Object.keys(tags).length ? tags : undefined
            });
          }
        }
        continue;
      }

      // 2. 尝试 Prometheus Line
      const promData = parsePrometheusLine(line);
      if (promData) {
        const { name, value, tags } = promData;
        const lowerName = name.toLowerCase();
        if (isSelfMetricName(name)) {
          if (lowerName.includes('up') && typeof value === 'number') up = value;
          if (lowerName.includes('exit_code') && typeof value === 'number') exitCode = value;
          if (lowerName.includes('duration') && typeof value === 'number') {
            durationMs = lowerName.includes('second') ? Math.round(value * 1000) : value;
          }
          continue;
        }
        if (!seenKeys.has(name)) {
          seenKeys.add(name);
          businessMetrics.push({
            key: name,
            name,
            value,
            tags: Object.keys(tags).length ? tags : undefined
          });
        }
        continue;
      }

      // 3. 尝试 Key-Value Line
      const kvData = parseKeyValueLine(line);
      if (kvData) {
        const { name, value } = kvData;
        const lowerName = name.toLowerCase();
        if (isSelfMetricName(name)) {
          if (lowerName.includes('up') && typeof value === 'number') up = value;
          if (lowerName.includes('exit_code') && typeof value === 'number') exitCode = value;
          if (lowerName.includes('duration') && typeof value === 'number') {
            durationMs = lowerName.includes('second') ? Math.round(value * 1000) : value;
          }
          continue;
        }
        if (!seenKeys.has(name)) {
          seenKeys.add(name);
          businessMetrics.push({
            key: name,
            name,
            value
          });
        }
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
