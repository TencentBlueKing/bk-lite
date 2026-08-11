import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';

export interface RadarIndicatorConfig {
  key: string;
  label?: string;
}

export interface RadarConfig {
  min?: number;
  max?: number;
  indicators?: RadarIndicatorConfig[];
}

export interface RadarDataPoint {
  label: string;
  value: number;
}

export interface RadarSeriesData {
  indicatorLabels: string[];
  indicatorValues: number[];
  warning?: 'few_indicators' | 'too_many_indicators';
  unsupported?: 'multi_series';
}

const toFiniteNumber = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

export const normalizeRadarRange = (
  radarConfig?: RadarConfig,
  legacy?: { gaugeMin?: number; gaugeMax?: number },
) => {
  const minValue = Number(radarConfig?.min ?? legacy?.gaugeMin ?? 0);
  const maxValue = Number(radarConfig?.max ?? legacy?.gaugeMax ?? 100);
  const safeMin = Number.isFinite(minValue) ? minValue : 0;
  const safeMax =
    Number.isFinite(maxValue) && maxValue > safeMin ? maxValue : safeMin + 100;
  return { min: safeMin, max: safeMax };
};

const parseObjectMode = (
  rawData: Record<string, unknown>,
  indicatorConfigs: RadarIndicatorConfig[],
): RadarDataPoint[] => {
  return indicatorConfigs
    .map((indicator) => {
      const key = String(indicator.key || '').trim();
      if (!key) return null;
      const numberValue = toFiniteNumber(getValueByPath(rawData, key));
      if (numberValue === null) return null;
      return {
        label: indicator.label?.trim() || key,
        value: numberValue,
      };
    })
    .filter((item): item is RadarDataPoint => item !== null);
};

const parseNameValueArrayMode = (rawData: unknown[]): RadarDataPoint[] => {
  return rawData
    .map((item) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) {
        return null;
      }
      const record = item as Record<string, unknown>;
      const label = String(record.name ?? '').trim();
      const numberValue = toFiniteNumber(record.value);
      if (!label || numberValue === null) {
        return null;
      }
      return {
        label,
        value: numberValue,
      };
    })
    .filter((item): item is RadarDataPoint => item !== null);
};

export const resolveRadarSeriesData = (
  rawData: unknown,
  radarConfig?: RadarConfig,
  legacySelectedFields: string[] = [],
): RadarSeriesData => {
  let points: RadarDataPoint[] = [];
  if (
    rawData &&
    typeof rawData === 'object' &&
    !Array.isArray(rawData) &&
    Object.keys(rawData as Record<string, unknown>).length > 0 &&
    Object.values(rawData as Record<string, unknown>).every((value) =>
      Array.isArray(value),
    )
  ) {
    return {
      indicatorLabels: [],
      indicatorValues: [],
      unsupported: 'multi_series',
    };
  }

  if (Array.isArray(rawData)) {
    points = parseNameValueArrayMode(rawData);
  } else if (rawData && typeof rawData === 'object') {
    const explicitIndicators = (radarConfig?.indicators || []).filter(
      (item) => String(item.key || '').trim().length > 0,
    );
    const fallbackIndicators = legacySelectedFields.map((field) => ({
      key: field,
      label: field,
    }));
    const indicators = explicitIndicators.length
      ? explicitIndicators
      : fallbackIndicators;
    points = parseObjectMode(rawData as Record<string, unknown>, indicators);
  }

  if (!points.length) {
    return {
      indicatorLabels: [],
      indicatorValues: [],
    };
  }

  const warning =
    points.length < 3
      ? 'few_indicators'
      : points.length > 8
        ? 'too_many_indicators'
        : undefined;

  return {
    indicatorLabels: points.map((point) => point.label),
    indicatorValues: points.map((point) => point.value),
    ...(warning ? { warning } : {}),
  };
};
