import React from 'react';
import ComKpiCard from '../comKpiCard';

const toNumber = (value: unknown) => {
  const parsed = Number.parseFloat(String(value ?? 0));
  return Number.isNaN(parsed) ? 0 : parsed;
};

/**
 * 将多查询结果（keyed object）按 _time 合并为单一行数组。
 * 单查询结果（普通数组）直接返回。
 */
const normalizeMultiQueryData = (data: any): any[] => {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== 'object') return [];

  const keys = Object.keys(data);
  if (keys.length === 0) return [];

  // 按 _time 聚合所有子查询的字段
  const timeMap = new Map<string, Record<string, unknown>>();
  for (const key of keys) {
    const rows = data[key];
    if (!Array.isArray(rows)) continue;
    for (const row of rows) {
      const time = String(row._time ?? '');
      if (!timeMap.has(time)) {
        timeMap.set(time, { _time: time });
      }
      const merged = timeMap.get(time)!;
      for (const [field, value] of Object.entries(row)) {
        if (field !== '_time') {
          merged[field] = value;
        }
      }
    }
  }

  // 按 _time 排序返回
  return Array.from(timeMap.values()).sort((a, b) =>
    String(a._time).localeCompare(String(b._time))
  );
};

const calculateMetricValue = (rows: any[], config: any) => {
  const calculation = config?.calculation || 'sum';

  if (!Array.isArray(rows) || rows.length === 0) {
    return { value: undefined, trendData: [] as number[] };
  }

  if (calculation === 'ratio') {
    const numeratorField = config?.numeratorField;
    const denominatorField = config?.denominatorField;
    const multiplier = Number(config?.multiplier || 1);
    const numeratorTotal = rows.reduce(
      (sum, row) => sum + toNumber(row[numeratorField]),
      0
    );
    const denominatorTotal = rows.reduce(
      (sum, row) => sum + toNumber(row[denominatorField]),
      0
    );
    const value =
      denominatorTotal > 0
        ? (numeratorTotal / denominatorTotal) * multiplier
        : 0;
    const trendData = rows.map((row) => {
      const denominator = toNumber(row[denominatorField]);
      return denominator > 0
        ? (toNumber(row[numeratorField]) / denominator) * multiplier
        : 0;
    });
    return { value, trendData };
  }

  if (calculation === 'weightedAverage') {
    const valueField = config?.valueField;
    const weightField = config?.weightField;
    const weightedTotal = rows.reduce(
      (sum, row) =>
        sum + toNumber(row[valueField]) * toNumber(row[weightField]),
      0
    );
    const weightTotal = rows.reduce(
      (sum, row) => sum + toNumber(row[weightField]),
      0
    );
    const value = weightTotal > 0 ? weightedTotal / weightTotal : 0;
    const trendData = rows.map((row) => toNumber(row[valueField]));
    return { value, trendData };
  }

  const valueField = config?.valueField || config?.displayMaps?.value;
  const trendData = rows.map((row) => toNumber(row[valueField]));
  const value = trendData.reduce((sum, current) => sum + current, 0);
  return { value, trendData };
};

const calculateHttpMetric = (rawData: any, prevData: any, config: any) => {
  const currentResult = calculateMetricValue(normalizeMultiQueryData(rawData), config);
  const previousResult = calculateMetricValue(normalizeMultiQueryData(prevData), config);

  let pct: number | null = null;
  if (
    typeof currentResult.value === 'number' &&
    typeof previousResult.value === 'number'
  ) {
    if (previousResult.value !== 0) {
      pct =
        ((currentResult.value - previousResult.value) / previousResult.value) *
        100;
    } else if (currentResult.value > 0) {
      pct = 100;
    }
  }

  return {
    currentValue: currentResult.value,
    changePercent: pct,
    trendData: currentResult.trendData
  };
};

const HttpKpiCard: React.FC<any> = (props) => {
  return <ComKpiCard {...props} calculateMetric={calculateHttpMetric} />;
};

export default HttpKpiCard;
