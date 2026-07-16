import dayjs from 'dayjs';
import { formatOpsDisplayTime } from '@/components/ops-analysis-widgets/date-time';
import { getValueByPath } from '@/components/ops-analysis-config-sections';
import type { DashboardActionParamMapping } from '@/components/ops-analysis-widgets';

export interface ChartDataItem {
  name: string;
  value: number;
}

export interface SeriesDataItem {
  name: string;
  data: number[];
}

export interface LineBarChartData {
  categories: string[];
  values?: number[];
  series?: SeriesDataItem[];
}

export type PieChartData = ChartDataItem[];

export type OpsChartThemeName = 'light' | 'dark';

export const resolveOpsChartThemeName = (): OpsChartThemeName => {
  if (
    typeof document !== 'undefined' &&
    document.documentElement.classList.contains('dark')
  ) {
    return 'dark';
  }
  return 'light';
};

export const getOpsChartTheme = (themeName: OpsChartThemeName) => {
  const isDarkTheme = themeName === 'dark';

  return {
    axisLabelColor: isDarkTheme ? 'rgba(255,255,255,0.64)' : '#7f92a7',
    axisLineColor: isDarkTheme ? 'rgba(255,255,255,0.14)' : '#e5ebf4',
    splitLineColor: isDarkTheme ? 'rgba(255,255,255,0.12)' : '#e8eef7',
    tooltipBackgroundColor: isDarkTheme
      ? 'rgba(7, 29, 44, 0.96)'
      : '#ffffff',
    tooltipBorderColor: isDarkTheme
      ? 'rgba(255,255,255,0.12)'
      : '#e6e9ee',
    tooltipTextColor: isDarkTheme ? 'rgba(255,255,255,0.88)' : '#1e252e',
    tooltipShadow: isDarkTheme
      ? '0 12px 32px rgba(0,0,0,0.36)'
      : '0 8px 24px rgba(15,23,42,0.12)',
    pieTitleColor: isDarkTheme ? 'rgba(255,255,255,0.58)' : '#7a8699',
    pieValueColor: isDarkTheme ? 'rgba(255,255,255,0.92)' : '#2a3547',
    pieBorderColor: isDarkTheme ? 'rgba(7, 29, 44, 0.96)' : '#fff',
    zoomBrushColor: isDarkTheme
      ? 'rgba(46, 132, 255, 0.14)'
      : 'rgba(24, 144, 255, 0.12)',
    zoomBrushBorderColor: isDarkTheme
      ? 'rgba(96, 165, 250, 0.52)'
      : 'rgba(24, 144, 255, 0.42)',
    axisPointerColor: isDarkTheme
      ? 'rgba(96, 165, 250, 0.72)'
      : 'rgba(60, 102, 240, 0.55)',
    legendHeaderBg: isDarkTheme ? 'rgba(255,255,255,0.06)' : '#f7f9fc',
    legendRowBg: isDarkTheme ? 'rgba(255,255,255,0.03)' : '#fbfcfe',
    legendHoverBg: isDarkTheme ? 'rgba(255,255,255,0.08)' : '#eef4ff',
    panelBg: isDarkTheme ? 'var(--color-bg-1)' : '#ffffff',
    panelSubtleBg: isDarkTheme ? 'rgba(255,255,255,0.03)' : '#fbfdff',
    panelBorderColor: isDarkTheme ? 'var(--color-border-2)' : '#e6edf7',
    panelShadow: isDarkTheme
      ? '0 10px 28px rgba(0, 0, 0, 0.24)'
      : '0 10px 30px rgba(31, 63, 104, 0.08)',
    singleValueColor: isDarkTheme ? 'rgba(255,255,255,0.94)' : '#1e40af',
    singleValueGlow: isDarkTheme
      ? 'none'
      : '0 4px 14px rgba(30, 64, 175, 0.08)',
    singleValueMetaColor: isDarkTheme
      ? 'rgba(255,255,255,0.52)'
      : '#7f92a7',
    singleValueSurface: isDarkTheme
      ? 'rgba(255,255,255,0.02)'
      : '#fcfdff',
    lineWidth: isDarkTheme ? 2 : 2,
    lineAreaOpacity: isDarkTheme ? 0.1 : 0.06,
    lineOpacity: isDarkTheme ? 0.94 : 0.92,
  };
};

const COLOR_LIST = [
  '84,112,198',
  '145,204,117',
  '250,200,88',
  '238,102,102',
  '115,192,222',
  '59,162,114',
  '252,132,82',
  '154,96,180',
  '234,124,204',
  '50,197,233',
  '204,117,117',
  '204,117,181',
  '163,117,204',
  '117,154,204',
  '117,166,204',
  '117,198,204',
  '117,204,169',
  '142,204,117',
  '193,204,117',
  '204,147,117',
];

const getRandomColor = () => {
  let rgb;
  let saturationValue;
  let lightnessValue;

  do {
    const [hue, saturation, lightness] = [
      Math.floor(Math.random() * 360),
      Math.floor(Math.random() * 81) + 10,
      Math.floor(Math.random() * 51) + 50,
    ];
    const [red, green, blue] = hslToRgb(hue, saturation, lightness);
    rgb = { red, green, blue };
    saturationValue = saturation;
    lightnessValue = lightness;
  } while (
    (rgb.red === 255 && rgb.green === 255 && rgb.blue === 255) ||
    (rgb.red === rgb.green && rgb.green === rgb.blue) ||
    saturationValue < 20 ||
    lightnessValue > 90
  );

  return `rgba(${rgb.red}, ${rgb.green}, ${rgb.blue}, 1)`;
};

const hslToRgb = (
  hue: number,
  saturation: number,
  lightness: number,
) => {
  const saturationRatio = saturation / 100;
  const lightnessRatio = lightness / 100;
  const chroma =
    (1 - Math.abs(2 * lightnessRatio - 1)) * saturationRatio;
  const intermediate =
    chroma * (1 - Math.abs(((hue / 60) % 2) - 1));
  const match = lightnessRatio - chroma / 2;
  const phase = Math.floor(hue / 60);
  const rgb =
    phase === 0
      ? [chroma, intermediate, 0]
      : phase === 1
        ? [intermediate, chroma, 0]
        : phase === 2
          ? [0, chroma, intermediate]
          : phase === 3
            ? [0, intermediate, chroma]
            : phase === 4
              ? [intermediate, 0, chroma]
              : [chroma, 0, intermediate];

  return [
    Math.round((rgb[0] + match) * 255),
    Math.round((rgb[1] + match) * 255),
    Math.round((rgb[2] + match) * 255),
  ];
};

export const randomColorForLegend = (themeName?: OpsChartThemeName) => {
  const maxColorsTotal = 1000;
  const maxColorsCount = 80;
  const customColorsRow = 4;
  const resolvedThemeName = themeName ?? resolveOpsChartThemeName();
  let colors: string[] = [];
  const opacity =
    resolvedThemeName === 'dark'
      ? [1, 0.92, 0.84, 0.76]
      : [1, 0.8, 0.6, 0.4];

  for (let index = 0; index < customColorsRow; index += 1) {
    colors = colors.concat(
      COLOR_LIST.map((value) => `rgba(${value}, ${opacity[index]})`),
    );
  }

  if (maxColorsTotal > maxColorsCount) {
    for (let index = 0; index < maxColorsTotal - maxColorsCount; index += 1) {
      colors.push(getRandomColor());
    }
  }

  return colors;
};

export class ChartDataTransformer {
  static formatCategoryValue(value: any): string {
    if (value === undefined || value === null) return '';
    return String(value);
  }

  private static isUnixTimestampLike(value: any): boolean {
    if (typeof value === 'string' && !/^\d+(\.\d+)?$/.test(value.trim())) {
      return false;
    }

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
      return false;
    }

    const secondsValue =
      numericValue > 9999999999 ? numericValue / 1000 : numericValue;

    return secondsValue >= 946684800 && secondsValue <= 4102444800;
  }

  static shouldFormatAsTimeDimension(values: any[]): boolean {
    const normalizedValues = values.filter(
      (value) => value !== undefined && value !== null && value !== '',
    );

    if (normalizedValues.length === 0) {
      return false;
    }

    const validCount = normalizedValues.filter((value) => {
      if (typeof value === 'number') {
        return this.isUnixTimestampLike(value);
      }

      if (typeof value === 'string') {
        const trimmed = value.trim();
        if (!trimmed) return false;

        if (this.isUnixTimestampLike(trimmed)) {
          return true;
        }

        const hasExplicitDateMarkers = /[-/:T\s]/.test(trimmed);
        if (!hasExplicitDateMarkers) return false;
        if (!/^\d/.test(trimmed)) return false;

        return dayjs(trimmed).isValid();
      }

      return false;
    }).length;

    return validCount > 0 && validCount === normalizedValues.length;
  }

  static formatDimensionValue(
    value: any,
    shouldFormatAsTime: boolean,
  ): string {
    return shouldFormatAsTime
      ? this.formatTimeValue(value)
      : this.formatCategoryValue(value);
  }

  static isStructurallyEmpty(rawData: any): boolean {
    if (!rawData) return true;
    if (Array.isArray(rawData)) return rawData.length === 0;
    if (typeof rawData === 'object') {
      const values = Object.values(rawData);
      if (values.length === 0) return true;
      return values.every((value) => Array.isArray(value) && value.length === 0);
    }
    return false;
  }

  private static dataToMap(
    data: any[],
    shouldFormatAsTime: boolean,
  ): { [key: string]: number } {
    const map: { [key: string]: number } = {};
    if (data.length === 0) return map;
    if (
      typeof data[0] === 'object' &&
      !Array.isArray(data[0]) &&
      'name' in data[0] &&
      'value' in data[0]
    ) {
      data.forEach((item: any) => {
        map[this.formatDimensionValue(item.name, shouldFormatAsTime)] =
          parseFloat(item.value) || 0;
      });
    } else if (Array.isArray(data[0]) && data[0].length >= 2) {
      data.forEach((item: any[]) => {
        map[this.formatDimensionValue(item[0], shouldFormatAsTime)] =
          parseFloat(item[1]) || 0;
      });
    }
    return map;
  }

  static formatTimeValue(value: any): string {
    let dateValue: any = null;

    if (typeof value === 'number') {
      dateValue = dayjs(this.isUnixTimestampLike(value) ? value * 1000 : value);
    } else if (typeof value === 'string') {
      if (this.isUnixTimestampLike(value)) {
        dateValue = dayjs(Number(value) * 1000);
      } else {
        const trimmed = value.trim();
        const hasExplicitDateMarkers = /[-/:T\s]/.test(trimmed);
        if (!hasExplicitDateMarkers || !/^\d/.test(trimmed)) {
          return value;
        }
        dateValue = dayjs(value);
      }
    }

    if (dateValue && dateValue.isValid()) {
      if (
        dateValue.hour() === 0 &&
        dateValue.minute() === 0 &&
        dateValue.second() === 0
      ) {
        return formatOpsDisplayTime(value, 'MM-DD');
      }
      return formatOpsDisplayTime(value, 'MM-DD HH:mm');
    }

    return String(value);
  }

  static transformToLineBarData(rawData: any): LineBarChartData {
    if (!rawData) {
      return { categories: [], values: [] };
    }

    if (Array.isArray(rawData)) {
      if (rawData.length === 0) {
        return { categories: [], values: [] };
      }

      if (
        rawData[0] &&
        typeof rawData[0] === 'object' &&
        'name' in rawData[0] &&
        'count' in rawData[0]
      ) {
        return {
          categories: rawData.map((item: any) => item.name),
          values: rawData.map((item: any) => item.count),
        };
      }

      if (
        rawData[0] &&
        typeof rawData[0] === 'object' &&
        !Array.isArray(rawData[0]) &&
        'name' in rawData[0] &&
        'value' in rawData[0]
      ) {
        const shouldFormatAsTime = this.shouldFormatAsTimeDimension(
          rawData.map((item: any) => item.name),
        );
        return {
          categories: rawData.map((item: any) =>
            this.formatDimensionValue(item.name, shouldFormatAsTime),
          ),
          values: rawData.map((item: any) => parseFloat(item.value) || 0),
        };
      }

      if (Array.isArray(rawData[0]) && rawData[0].length >= 2) {
        const shouldFormatAsTime = this.shouldFormatAsTimeDimension(
          rawData.map((item: any[]) => item[0]),
        );
        return {
          categories: rawData.map((item: any[]) =>
            this.formatDimensionValue(item[0], shouldFormatAsTime),
          ),
          values: rawData.map((item: any[]) => item[1]),
        };
      }

      return { categories: [], values: [] };
    }

    if (typeof rawData === 'object') {
      const keys = Object.keys(rawData);
      const isMultiSeries =
        keys.length > 0 && keys.every((key) => Array.isArray(rawData[key]));
      if (isMultiSeries) {
        const rawCategories: any[] = [];
        keys.forEach((key) => {
          rawData[key].forEach((item: any) => {
            if (Array.isArray(item) && item.length >= 2) {
              rawCategories.push(item[0]);
            } else if (item && typeof item === 'object' && 'name' in item) {
              rawCategories.push(item.name);
            }
          });
        });

        const shouldFormatAsTime =
          this.shouldFormatAsTimeDimension(rawCategories);
        const allCategoriesSet = new Set<string>();
        keys.forEach((key) => {
          rawData[key].forEach((item: any) => {
            if (Array.isArray(item) && item.length >= 2) {
              allCategoriesSet.add(
                this.formatDimensionValue(item[0], shouldFormatAsTime),
              );
            } else if (item && typeof item === 'object' && 'name' in item) {
              allCategoriesSet.add(
                this.formatDimensionValue(item.name, shouldFormatAsTime),
              );
            }
          });
        });
        const categories = Array.from(allCategoriesSet).sort();
        const series = keys.map((key) => {
          const dataMap = this.dataToMap(rawData[key], shouldFormatAsTime);
          return {
            name: key,
            data: categories.map((category) => dataMap[category] || 0),
          };
        });
        return { categories, series };
      }
    }

    return { categories: [], values: [] };
  }

  static transformToPieData(rawData: any): PieChartData {
    if (!rawData) return [];

    if (Array.isArray(rawData)) {
      if (rawData.length === 0) return [];

      if (
        typeof rawData[0] === 'object' &&
        !Array.isArray(rawData[0]) &&
        'name' in rawData[0] &&
        'value' in rawData[0]
      ) {
        return rawData.map((item: any) => ({
          name: this.formatCategoryValue(item.name),
          value: parseFloat(item.value) || 0,
        }));
      }

      if (Array.isArray(rawData[0]) && rawData[0].length >= 2) {
        return rawData.map((item: any[]) => ({
          name: this.formatCategoryValue(item[0]),
          value: parseFloat(item[1]) || 0,
        }));
      }

      if (
        typeof rawData[0] === 'object' &&
        'name' in rawData[0] &&
        'count' in rawData[0]
      ) {
        return rawData.map((item: any) => ({
          name: item.name,
          value: item.count,
        }));
      }
    }

    return [];
  }

  static isMultiSeriesData(rawData: any): boolean {
    if (!rawData || Array.isArray(rawData)) return false;
    if (typeof rawData === 'object') {
      const keys = Object.keys(rawData);
      return keys.length > 0 && keys.every((key) => Array.isArray(rawData[key]));
    }
    return false;
  }

  static hasValidData(data: LineBarChartData | PieChartData): boolean {
    if (Array.isArray(data)) {
      return data.length > 0;
    }
    return !!(data.categories && data.categories.length > 0);
  }

  static validateLineBarData(rawData: any, errorMessage?: string) {
    if (this.isStructurallyEmpty(rawData)) {
      return { isValid: true };
    }

    try {
      const transformedData = this.transformToLineBarData(rawData);

      if (!transformedData.categories || transformedData.categories.length === 0) {
        return { isValid: false, message: errorMessage || '数据格式不匹配' };
      }

      const hasValidData = transformedData.series
        ? transformedData.series.some((series) => (
          series.data &&
          series.data.length > 0 &&
          series.data.some(
            (value) => typeof value === 'number' && !Number.isNaN(value),
          )
        ))
        : transformedData.values &&
          transformedData.values.some(
            (value) => typeof value === 'number' && !Number.isNaN(value),
          );

      if (!hasValidData) {
        return { isValid: false, message: errorMessage || '数据格式不匹配' };
      }

      return { isValid: true };
    } catch {
      return { isValid: false, message: errorMessage || '数据格式不匹配' };
    }
  }

  static validatePieData(rawData: any, errorMessage?: string) {
    if (this.isStructurallyEmpty(rawData)) {
      return { isValid: true };
    }

    try {
      const transformedData = this.transformToPieData(rawData);

      if (!transformedData || transformedData.length === 0) {
        return { isValid: false, message: errorMessage || '数据格式不匹配' };
      }

      const hasValidValues = transformedData.some(
        (item) =>
          item &&
          typeof item.value === 'number' &&
          !Number.isNaN(item.value) &&
          item.value > 0,
      );

      if (!hasValidValues) {
        return { isValid: false, message: errorMessage || '数据格式不匹配' };
      }

      return { isValid: true };
    } catch {
      return { isValid: false, message: errorMessage || '数据格式不匹配' };
    }
  }
}

export const extractComparableValue = (
  data: unknown,
  selectedField?: string,
): number | string | null => {
  if (data === null || data === undefined) {
    return null;
  }

  if (selectedField) {
    const extracted = getValueByPath(data, selectedField);
    if (typeof extracted === 'number' || typeof extracted === 'string') {
      return extracted;
    }
    return null;
  }

  if (typeof data === 'number' || typeof data === 'string') {
    return data;
  }

  if (Array.isArray(data) && data.length > 0) {
    const firstItem = data[0];
    if (firstItem && typeof firstItem === 'object') {
      const values = Object.values(firstItem as Record<string, unknown>);
      for (const value of values) {
        if (typeof value === 'number') return value;
      }
      for (const value of values) {
        if (
          typeof value === 'string' &&
          !Number.isNaN(parseFloat(value))
        ) {
          return value;
        }
      }
    }
  }

  if (typeof data === 'object') {
    const values = Object.values(data as Record<string, unknown>);
    for (const value of values) {
      if (typeof value === 'number') return value;
    }
  }

  return null;
};

export const toComparableNumber = (
  value: number | string | null,
): number | null => {
  if (value === null) {
    return null;
  }
  const numericValue = typeof value === 'string' ? parseFloat(value) : value;
  return typeof numericValue === 'number' && !Number.isNaN(numericValue)
    ? numericValue
    : null;
};

export const getChangePercent = (
  currentValue: number | null,
  baselineValue: number | null,
): number | null => {
  if (currentValue === null || baselineValue === null) {
    return null;
  }
  if (baselineValue !== 0) {
    return ((currentValue - baselineValue) / baselineValue) * 100;
  }
  if (currentValue > 0) {
    return 100;
  }
  return null;
};

const hashSeed = (seedSource: string) => {
  let hash = 2166136261;
  for (let index = 0; index < seedSource.length; index += 1) {
    hash ^= seedSource.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
};

const createSeededRandom = (seedSource: string) => {
  let seed = hashSeed(seedSource) || 1;
  return () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 0xffffffff;
  };
};

export const buildFallbackSparkline = (
  baseValue: number | null,
  baselineValue: number | null,
  seedSource: string,
): number[] => {
  const resolvedBase = Math.abs(baseValue ?? baselineValue ?? 100) || 100;
  const random = createSeededRandom(seedSource);
  const amplitudeRatio = 0.04 + random() * 0.03;
  const amplitude = Math.max(resolvedBase * amplitudeRatio, 6);
  const delta =
    baselineValue !== null && baseValue !== null ? baseValue - baselineValue : 0;
  const direction = delta === 0 ? 0 : delta > 0 ? 1 : -1;
  const relativeDelta =
    baselineValue !== null && baseValue !== null
      ? Math.abs(delta) / Math.max(Math.abs(baselineValue), 1)
      : 0;
  const trendSpan =
    direction === 0
      ? 0
      : amplitude * (1.5 + Math.min(relativeDelta, 1.5) * 1.8);
  const primaryFrequency = 2 + Math.round(random() * 2);
  const secondaryFrequency = 4 + Math.round(random() * 2);
  const tertiaryFrequency = 6 + Math.round(random() * 3);
  const primaryPhase = random() * Math.PI * 0.35;
  const secondaryPhase = random() * Math.PI * 0.45;
  const tertiaryPhase = random() * Math.PI * 0.55;
  const secondaryWeight = 0.18 + random() * 0.14;
  const tertiaryWeight = 0.08 + random() * 0.08;

  return Array.from({ length: 24 }, (_, index) => {
    const progress = index / 23;
    const envelope = Math.sin(progress * Math.PI);
    const primaryWave = Math.sin(
      progress * Math.PI * primaryFrequency + primaryPhase,
    );
    const secondaryWave = Math.sin(
      progress * Math.PI * secondaryFrequency + secondaryPhase,
    );
    const tertiaryWave = Math.sin(
      progress * Math.PI * tertiaryFrequency + tertiaryPhase,
    );
    const oscillation =
      envelope *
      amplitude *
      (0.55 * primaryWave +
        secondaryWeight * secondaryWave +
        tertiaryWeight * tertiaryWave);
    const trendBase = resolvedBase + (progress - 0.5) * trendSpan * direction;
    const value = trendBase + oscillation;
    return Number(value.toFixed(2));
  });
};

export const buildDashboardActionUrl = (
  rawUrl: string | undefined,
  params: Record<string, string | number | boolean>,
): string => {
  const url = rawUrl?.trim();
  if (!url) return '';

  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') {
      return;
    }
    searchParams.set(key, String(value));
  });

  const queryString = searchParams.toString();
  if (!queryString) return url;

  const [urlWithoutHash, hash = ''] = url.split('#');
  const separator = urlWithoutHash.includes('?') ? '&' : '?';
  const hashFragment = hash ? `#${hash}` : '';

  return `${urlWithoutHash}${separator}${queryString}${hashFragment}`;
};

export const resolveDashboardActionParams = (
  mappings: DashboardActionParamMapping[] | undefined,
  record: Record<string, any>,
): Record<string, string | number | boolean> => {
  const params: Record<string, string | number | boolean> = {};

  (mappings || []).forEach((mapping) => {
    if (!mapping.key) {
      return;
    }

    if (mapping.source === 'rowField') {
      const value = mapping.sourceKey ? record?.[mapping.sourceKey] : undefined;
      if (value === null || value === undefined || value === '') {
        return;
      }
      if (['string', 'number', 'boolean'].includes(typeof value)) {
        params[mapping.key] = value;
      } else {
        params[mapping.key] = String(value);
      }
      return;
    }

    if (
      mapping.source === 'fixed' &&
      mapping.value !== null &&
      mapping.value !== undefined &&
      mapping.value !== ''
    ) {
      params[mapping.key] = mapping.value;
    }
  });

  return params;
};

/**
 * Generate a unique column key for the "operations" action column.
 * Used by useTableConfig when injecting a default action column into displayColumns.
 * Ensures the generated key does not collide with any existing column key.
 */
export const createOperationColumnKey = (displayColumns: Array<{ key: string }>): string => {
  const existingKeys = new Set(displayColumns.map((c) => c.key));
  const base = `column_actions_${Date.now()}`;
  if (!existingKeys.has(base)) {
    return base;
  }
  let suffix = 1;
  let candidate = `${base}_${suffix}`;
  while (existingKeys.has(candidate)) {
    suffix += 1;
    candidate = `${base}_${suffix}`;
  }
  return candidate;
};
