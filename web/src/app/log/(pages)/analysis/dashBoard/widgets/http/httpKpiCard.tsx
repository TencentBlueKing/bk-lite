import React from 'react';
import ComKpiCard from '../comKpiCard';

const toNumber = (value: unknown) => {
  const parsed = Number.parseFloat(String(value ?? 0));
  return Number.isNaN(parsed) ? 0 : parsed;
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
  const currentResult = calculateMetricValue(rawData, config);
  const previousResult = calculateMetricValue(prevData, config);

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
