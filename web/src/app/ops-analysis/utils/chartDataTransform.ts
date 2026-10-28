import dayjs from 'dayjs';
import { formatOpsDisplayTime } from '@/app/ops-analysis/utils/dateTime';
import {
  chartLinkFields,
  chartLinkTime,
  type ChartLinkPoint,
} from '@/app/ops-analysis/utils/interactionLink';
import { coerceTopNNumericValue, unwrapTopNData } from '@/app/ops-analysis/utils/topNData';

export interface ChartDataItem {
  name: string;
  value: number;
  __link?: ChartLinkPoint;
}

export interface SeriesDataItem {
  name: string;
  data: Array<number | null>;
  points?: ChartLinkPoint[];
}

export interface LineBarChartData {
  categories: string[];
  values?: Array<number | null>;
  series?: SeriesDataItem[];
  points?: ChartLinkPoint[];
}

export interface PieScalarField {
  field: string;
  label?: string;
}

export interface ChartFieldMapping {
  dimensionField?: string;
  valueField?: string;
  pieScalarFields?: PieScalarField[];
}

export const toPieFieldMapping = (config?: {
  dimensionField?: string;
  valueField?: string;
  pieScalarFields?: PieScalarField[];
}): ChartFieldMapping => ({
  dimensionField: config?.dimensionField,
  valueField: config?.valueField,
  pieScalarFields: config?.pieScalarFields,
});

export type PieChartData = ChartDataItem[];

const DECIMAL_NUMBER_PATTERN =
  /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;

const parseFiniteDecimal = (value: unknown): number => {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : Number.NaN;
  }

  if (typeof value !== 'string') {
    return Number.NaN;
  }

  const normalizedValue = value.trim();
  if (!DECIMAL_NUMBER_PATTERN.test(normalizedValue)) {
    return Number.NaN;
  }

  const numericValue = Number(normalizedValue);
  return Number.isFinite(numericValue) ? numericValue : Number.NaN;
};

const isPlainRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const hasExplicitFieldMapping = (mapping?: ChartFieldMapping) =>
  Boolean(mapping?.dimensionField?.trim() || mapping?.valueField?.trim());

const scalarPieFields = (mapping?: ChartFieldMapping): PieScalarField[] => {
  const fields = (mapping?.pieScalarFields || [])
    .map((item) => ({
      field: String(item?.field || '').trim(),
      label: String(item?.label || '').trim(),
    }))
    .filter((item) => item.field);
  return fields.length >= 2 ? fields : [];
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

    const secondsValue = numericValue > 9999999999 ? numericValue / 1000 : numericValue;

    return secondsValue >= 946684800 && secondsValue <= 4102444800;
  }

  static shouldFormatAsTimeDimension(values: any[]): boolean {
    const normalizedValues = values.filter(
      (value) => value !== undefined && value !== null && value !== ''
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

        // 必须以数字开头才可能是日期/时间，排除 "node-1"、"host-a" 等带连字符的普通标签
        // （dayjs 宽松解析会把这类字符串误判为合法日期）
        if (!/^\d/.test(trimmed)) return false;

        return dayjs(trimmed).isValid();
      }

      return false;
    }).length;

    return validCount > 0 && validCount === normalizedValues.length;
  }

  static formatDimensionValue(value: any, shouldFormatAsTime: boolean): string {
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
    shouldFormatAsTime: boolean
  ): { [key: string]: number } {
    const map: { [key: string]: number } = {};
    if (data.length === 0) return map;
    if (typeof data[0] === 'object' && !Array.isArray(data[0]) && 'name' in data[0] && 'value' in data[0]) {
      data.forEach((item: any) => {
        map[this.formatDimensionValue(item.name, shouldFormatAsTime)] = parseFloat(item.value) || 0;
      });
    } else if (Array.isArray(data[0]) && data[0].length >= 2) {
      data.forEach((item: any[]) => {
        map[this.formatDimensionValue(item[0], shouldFormatAsTime)] = parseFloat(item[1]) || 0;
      });
    }
    return map;
  }

  private static linkPoint(input: {
    seriesName?: string;
    dimension?: unknown;
    dimensionKey?: string;
    isTime?: boolean;
    numeric: number | null;
    raw?: unknown;
    row?: unknown;
  }): ChartLinkPoint {
    const time = chartLinkTime(input.dimension, Boolean(input.isTime));
    const fields = chartLinkFields(input.row);
    const text = typeof input.numeric === 'number' && Number.isFinite(input.numeric)
      ? String(input.numeric)
      : typeof input.raw === 'string'
        ? input.raw
        : '';
    return {
      ...(input.seriesName ? { seriesName: input.seriesName } : {}),
      ...(time ? { time } : {}),
      ...(!time && input.dimensionKey ? { axisField: input.dimensionKey } : {}),
      ...(typeof input.numeric === 'number' && Number.isFinite(input.numeric)
        ? { numeric: input.numeric }
        : {}),
      ...(text ? { text } : {}),
      ...(input.raw !== undefined ? { raw: input.raw } : {}),
      ...(fields ? { fields } : {}),
    };
  }

  private static pointsForRows(
    rows: any[],
    shouldFormatAsTime: boolean,
    read: (row: any) => { dimension: unknown; raw: unknown; numeric: number | null },
    seriesName?: string,
    dimensionKey?: string,
  ): ChartLinkPoint[] {
    return rows.map((row) => {
      const item = read(row);
      return this.linkPoint({
        seriesName,
        dimension: item.dimension,
        dimensionKey,
        isTime: shouldFormatAsTime,
        numeric: item.numeric,
        raw: item.raw,
        row: Array.isArray(row)
          ? (!shouldFormatAsTime && dimensionKey
            ? { [dimensionKey]: item.dimension }
            : undefined)
          : row,
      });
    });
  }

  private static dataToPointMap(
    data: any[],
    shouldFormatAsTime: boolean,
    seriesName: string,
  ): Record<string, ChartLinkPoint> {
    const map: Record<string, ChartLinkPoint> = {};
    if (data.length === 0) return map;
    if (typeof data[0] === 'object' && !Array.isArray(data[0]) && 'name' in data[0] && 'value' in data[0]) {
      data.forEach((item: any) => {
        const key = this.formatDimensionValue(item.name, shouldFormatAsTime);
        map[key] = this.linkPoint({
          seriesName,
          dimension: item.name,
          dimensionKey: 'name',
          isTime: shouldFormatAsTime,
          numeric: Number.isFinite(parseFloat(item.value)) ? parseFloat(item.value) : null,
          raw: item.value,
          row: item,
        });
      });
    } else if (Array.isArray(data[0]) && data[0].length >= 2) {
      data.forEach((item: any[]) => {
        const key = this.formatDimensionValue(item[0], shouldFormatAsTime);
        const numeric = Number.isFinite(parseFloat(item[1])) ? parseFloat(item[1]) : null;
        map[key] = this.linkPoint({
          seriesName,
          dimension: item[0],
          dimensionKey: 'name',
          isTime: shouldFormatAsTime,
          numeric,
          raw: item[1],
          row: shouldFormatAsTime ? undefined : { name: item[0] },
        });
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
        // 非日期标记、或不以数字开头（如 "node-1"）一律按原始类目返回，不当时间格式化
        if (!hasExplicitDateMarkers || !/^\d/.test(trimmed)) {
          return value;
        }
        dateValue = dayjs(value);
      }
    }

    if (dateValue && dateValue.isValid()) {
      // 午夜：日/月桶统一带年，避免跨年刻度撞名（如多个 01-01）
      if (dateValue.hour() === 0 && dateValue.minute() === 0 && dateValue.second() === 0) {
        return formatOpsDisplayTime(value, 'YYYY-MM-DD');
      }
      return formatOpsDisplayTime(value, 'MM-DD HH:mm');
    }

    return String(value);
  }

  static transformToLineBarData(
    rawData: any,
    mapping?: ChartFieldMapping,
  ): LineBarChartData {
    if (hasExplicitFieldMapping(mapping)) {
      return this.transformMappedLineBar(rawData, mapping);
    }

    if (!rawData) {
      return { categories: [], values: [] };
    }

    if (Array.isArray(rawData)) {
      if (rawData.length === 0) {
        return { categories: [], values: [] };
      }

      // [{name, count}] format
      if (rawData[0] && typeof rawData[0] === 'object' && 'name' in rawData[0] && 'count' in rawData[0]) {
        return {
          categories: rawData.map((item: any) => item.name),
          values: rawData.map((item: any) => item.count),
          points: this.pointsForRows(rawData, false, (item) => ({
            dimension: item.name,
            raw: item.count,
            numeric: Number.isFinite(Number(item.count)) ? Number(item.count) : null,
          }), undefined, 'name'),
        };
      }

      // [{name, value}] format
      if (rawData[0] && typeof rawData[0] === 'object' && !Array.isArray(rawData[0]) && 'name' in rawData[0] && 'value' in rawData[0]) {
        const shouldFormatAsTime = this.shouldFormatAsTimeDimension(
          rawData.map((item: any) => item.name)
        );
        return {
          categories: rawData.map((item: any) =>
            this.formatDimensionValue(item.name, shouldFormatAsTime)
          ),
          values: rawData.map((item: any) => parseFloat(item.value) || 0),
          points: this.pointsForRows(rawData, shouldFormatAsTime, (item) => ({
            dimension: item.name,
            raw: item.value,
            numeric: Number.isFinite(parseFloat(item.value)) ? parseFloat(item.value) : null,
          }), undefined, 'name'),
        };
      }

      // [[key, value], ...] format
      if (Array.isArray(rawData[0]) && rawData[0].length >= 2) {
        const shouldFormatAsTime = this.shouldFormatAsTimeDimension(
          rawData.map((item: any[]) => item[0])
        );
        return {
          categories: rawData.map((item: any[]) =>
            this.formatDimensionValue(item[0], shouldFormatAsTime)
          ),
          values: rawData.map((item: any[]) => item[1]),
          points: this.pointsForRows(rawData, shouldFormatAsTime, (item) => ({
            dimension: item[0],
            raw: item[1],
            numeric: Number.isFinite(parseFloat(item[1])) ? parseFloat(item[1]) : null,
          }), undefined, 'name'),
        };
      }

      return { categories: [], values: [] };
    }

    // Object-keyed multi-series: { seriesName: [[x,y], ...], ... }
    if (typeof rawData === 'object') {
      const keys = Object.keys(rawData);
      const isMultiSeries = keys.length > 0 && keys.every((k) => Array.isArray(rawData[k]));
      if (isMultiSeries) {
        const rawCategories: any[] = [];
        keys.forEach((k) => {
          rawData[k].forEach((item: any) => {
            if (Array.isArray(item) && item.length >= 2) {
              rawCategories.push(item[0]);
            } else if (item && typeof item === 'object' && 'name' in item) {
              rawCategories.push(item.name);
            }
          });
        });

        const shouldFormatAsTime = this.shouldFormatAsTimeDimension(rawCategories);
        const allCategoriesSet = new Set<string>();
        const categoryValue = new Map<string, unknown>();
        keys.forEach((k) => {
          rawData[k].forEach((item: any) => {
            const raw = Array.isArray(item) && item.length >= 2
              ? item[0]
              : item && typeof item === 'object' && 'name' in item
                ? item.name
                : undefined;
            if (raw === undefined) return;
            const key = this.formatDimensionValue(raw, shouldFormatAsTime);
            allCategoriesSet.add(key);
            if (!categoryValue.has(key)) categoryValue.set(key, raw);
          });
        });
        const categories = Array.from(allCategoriesSet).sort();
        const series = keys.map((k) => {
          const dataMap = this.dataToMap(rawData[k], shouldFormatAsTime);
          const pointMap = this.dataToPointMap(rawData[k], shouldFormatAsTime, k);
          return {
            name: k,
            data: categories.map((cat) => dataMap[cat] || 0),
            points: categories.map((cat) => pointMap[cat] ?? this.linkPoint({
              seriesName: k,
              dimension: categoryValue.get(cat),
              dimensionKey: 'name',
              isTime: shouldFormatAsTime,
              numeric: null,
              row: shouldFormatAsTime ? undefined : { name: categoryValue.get(cat) },
            })),
          };
        });
        return { categories, series };
      }
    }

    return { categories: [], values: [] };
  }

  private static transformMappedLineBar(
    rawData: unknown,
    mapping?: ChartFieldMapping,
  ): LineBarChartData {
    const rows = unwrapTopNData(rawData).filter(isPlainRecord);
    const dimensionField = mapping?.dimensionField?.trim() || '';
    const valueField = mapping?.valueField?.trim() || '';
    const dimensionValues = rows.map((row) => row[dimensionField]);
    const shouldFormatAsTime = this.shouldFormatAsTimeDimension(dimensionValues);

    return {
      categories: dimensionValues.map((value) =>
        this.formatDimensionValue(value, shouldFormatAsTime),
      ),
      values: rows.map((row) => coerceTopNNumericValue(row[valueField])),
      points: rows.map((row) => this.linkPoint({
        dimension: row[dimensionField],
        dimensionKey: dimensionField || undefined,
        isTime: shouldFormatAsTime,
        numeric: coerceTopNNumericValue(row[valueField]),
        raw: row[valueField],
        row,
      })),
    };
  }

  private static transformMappedPie(
    rawData: unknown,
    mapping?: ChartFieldMapping,
  ): PieChartData {
    const dimensionField = mapping?.dimensionField?.trim() || '';
    const valueField = mapping?.valueField?.trim() || '';
    const slices: PieChartData = [];

    unwrapTopNData(rawData).forEach((item) => {
      if (!isPlainRecord(item)) {
        return;
      }
      const value = coerceTopNNumericValue(item[valueField]);
      if (value === null) {
        return;
      }
      slices.push({
        name: this.formatCategoryValue(item[dimensionField]),
        value,
        __link: this.linkPoint({
          seriesName: this.formatCategoryValue(item[dimensionField]) || undefined,
          dimension: item[dimensionField],
          numeric: value,
          raw: item[valueField],
          row: item,
        }),
      });
    });

    return slices;
  }

  static transformToPieData(
    rawData: any,
    mapping?: ChartFieldMapping,
  ): PieChartData {
    const scalarFields = scalarPieFields(mapping);
    if (
      scalarFields.length >= 2
      && isPlainRecord(rawData)
      && !this.isMultiSeriesData(rawData)
    ) {
      return scalarFields.map((item) => {
        const raw = rawData[item.field];
        const missing = raw === null || raw === undefined || raw === '';
        const value = missing ? 0 : parseFiniteDecimal(raw);
        const name = item.label || item.field;
        return {
          name,
          value,
          __link: this.linkPoint({
            seriesName: name,
            dimension: item.field,
            numeric: Number.isFinite(value) ? value : null,
            raw,
            row: rawData,
          }),
        };
      });
    }

    if (hasExplicitFieldMapping(mapping)) {
      return this.transformMappedPie(rawData, mapping);
    }

    if (!rawData) return [];

    if (Array.isArray(rawData)) {
      if (rawData.length === 0) return [];

      // [{name, value}]
      if (typeof rawData[0] === 'object' && !Array.isArray(rawData[0]) && 'name' in rawData[0] && 'value' in rawData[0]) {
        return rawData.map((item: any) => ({
          name: this.formatCategoryValue(item.name),
          value: parseFiniteDecimal(item.value),
          __link: this.linkPoint({
            seriesName: this.formatCategoryValue(item.name) || undefined,
            dimension: item.name,
            numeric: parseFiniteDecimal(item.value),
            raw: item.value,
            row: item,
          }),
        }));
      }

      // [[key, value], ...]
      if (Array.isArray(rawData[0]) && rawData[0].length >= 2) {
        return rawData.map((item: any[]) => ({
          name: this.formatCategoryValue(item[0]),
          value: parseFiniteDecimal(item[1]),
          __link: this.linkPoint({
            seriesName: this.formatCategoryValue(item[0]) || undefined,
            dimension: item[0],
            numeric: parseFiniteDecimal(item[1]),
            raw: item[1],
          }),
        }));
      }

      // [{name, count}]
      if (typeof rawData[0] === 'object' && 'name' in rawData[0] && 'count' in rawData[0]) {
        return rawData.map((item: any) => ({
          name: item.name,
          value: parseFiniteDecimal(item.count),
          __link: this.linkPoint({
            seriesName: this.formatCategoryValue(item.name) || undefined,
            dimension: item.name,
            numeric: parseFiniteDecimal(item.count),
            raw: item.count,
            row: item,
          }),
        }));
      }
    }

    return [];
  }

  static isMultiSeriesData(rawData: any): boolean {
    if (!rawData || Array.isArray(rawData)) return false;
    if (typeof rawData === 'object') {
      const keys = Object.keys(rawData);
      return keys.length > 0 && keys.every((k) => Array.isArray(rawData[k]));
    }
    return false;
  }

  static hasValidData(data: LineBarChartData | PieChartData): boolean {
    if (Array.isArray(data)) {
      return data.length > 0;
    }
    return data.categories && data.categories.length > 0;
  }

  static validateLineBarData(
    rawData: any,
    errorMessage?: string,
    mapping?: ChartFieldMapping,
  ): { isValid: boolean; message?: string } {
    if (this.isStructurallyEmpty(rawData)) {
      return { isValid: true };
    }

    try {
      const transformedData = this.transformToLineBarData(rawData, mapping);

      if (!transformedData.categories || transformedData.categories.length === 0) {
        return { isValid: false, message: errorMessage || 'dashboard.dataFormatMismatch' };
      }

      if (hasExplicitFieldMapping(mapping)) {
        return { isValid: true };
      }

      const hasValidData = transformedData.series
        ? transformedData.series.some(series =>
          series.data && series.data.length > 0 &&
          series.data.some(val => typeof val === 'number' && !isNaN(val))
        )
        : transformedData.values &&
        transformedData.values.some(val => typeof val === 'number' && !isNaN(val));

      if (!hasValidData) {
        return { isValid: false, message: errorMessage || 'dashboard.dataFormatMismatch' };
      }

      return { isValid: true };
    } catch {
      return { isValid: false, message: errorMessage || 'dashboard.dataFormatMismatch' };
    }
  }

  static validatePieData(
    rawData: any,
    errorMessage?: string,
    mapping?: ChartFieldMapping,
  ): { isValid: boolean; message?: string } {
    if (this.isStructurallyEmpty(rawData)) {
      return { isValid: true };
    }

    try {
      const transformedData = this.transformToPieData(rawData, mapping);

      if (
        hasExplicitFieldMapping(mapping)
        && (!transformedData || transformedData.length === 0)
        && unwrapTopNData(rawData).some(isPlainRecord)
      ) {
        return { isValid: true };
      }

      if (!transformedData || transformedData.length === 0) {
        return { isValid: false, message: errorMessage || 'dashboard.dataFormatMismatch' };
      }

      const hasValidValues = transformedData.every(item =>
        item &&
        typeof item.value === 'number' &&
        Number.isFinite(item.value) &&
        item.value >= 0
      );

      if (!hasValidValues) {
        return { isValid: false, message: errorMessage || 'dashboard.dataFormatMismatch' };
      }

      return { isValid: true };
    } catch {
      return { isValid: false, message: errorMessage || 'dashboard.dataFormatMismatch' };
    }
  }
}
