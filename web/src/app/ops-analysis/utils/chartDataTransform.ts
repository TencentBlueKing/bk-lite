import dayjs from 'dayjs';
import { formatOpsDisplayTime } from '@/app/ops-analysis/utils/dateTime';

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
        if (!hasExplicitDateMarkers) {
          return value;
        }
        dateValue = dayjs(value);
      }
    }

    if (dateValue && dateValue.isValid()) {
      // 如果时分秒都为0，说明是按天/周/月分组，只显示 MM-DD
      if (dateValue.hour() === 0 && dateValue.minute() === 0 && dateValue.second() === 0) {
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

      // [{name, count}] format
      if (rawData[0] && typeof rawData[0] === 'object' && 'name' in rawData[0] && 'count' in rawData[0]) {
        return {
          categories: rawData.map((item: any) => item.name),
          values: rawData.map((item: any) => item.count),
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
        keys.forEach((k) => {
          rawData[k].forEach((item: any) => {
            if (Array.isArray(item) && item.length >= 2) {
              allCategoriesSet.add(
                this.formatDimensionValue(item[0], shouldFormatAsTime)
              );
            } else if (item && typeof item === 'object' && 'name' in item) {
              allCategoriesSet.add(
                this.formatDimensionValue(item.name, shouldFormatAsTime)
              );
            }
          });
        });
        const categories = Array.from(allCategoriesSet).sort();
        const series = keys.map((k) => {
          const dataMap = this.dataToMap(rawData[k], shouldFormatAsTime);
          return {
            name: k,
            data: categories.map((cat) => dataMap[cat] || 0),
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

      // [{name, value}]
      if (typeof rawData[0] === 'object' && !Array.isArray(rawData[0]) && 'name' in rawData[0] && 'value' in rawData[0]) {
        return rawData.map((item: any) => ({
          name: this.formatCategoryValue(item.name),
          value: parseFloat(item.value) || 0,
        }));
      }

      // [[key, value], ...]
      if (Array.isArray(rawData[0]) && rawData[0].length >= 2) {
        return rawData.map((item: any[]) => ({
          name: this.formatCategoryValue(item[0]),
          value: parseFloat(item[1]) || 0,
        }));
      }

      // [{name, count}]
      if (typeof rawData[0] === 'object' && 'name' in rawData[0] && 'count' in rawData[0]) {
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

  static validateLineBarData(rawData: any, errorMessage?: string): { isValid: boolean; message?: string } {
    if (this.isStructurallyEmpty(rawData)) {
      return { isValid: true };
    }

    try {
      const transformedData = this.transformToLineBarData(rawData);

      if (!transformedData.categories || transformedData.categories.length === 0) {
        return { isValid: false, message: errorMessage || '数据格式不匹配' };
      }

      const hasValidData = transformedData.series
        ? transformedData.series.some(series =>
          series.data && series.data.length > 0 &&
          series.data.some(val => typeof val === 'number' && !isNaN(val))
        )
        : transformedData.values &&
        transformedData.values.some(val => typeof val === 'number' && !isNaN(val));

      if (!hasValidData) {
        return { isValid: false, message: errorMessage || '数据格式不匹配' };
      }

      return { isValid: true };
    } catch {
      return { isValid: false, message: errorMessage || '数据格式不匹配' };
    }
  }

  static validatePieData(rawData: any, errorMessage?: string): { isValid: boolean; message?: string } {
    if (this.isStructurallyEmpty(rawData)) {
      return { isValid: true };
    }

    try {
      const transformedData = this.transformToPieData(rawData);

      if (!transformedData || transformedData.length === 0) {
        return { isValid: false, message: errorMessage || '数据格式不匹配' };
      }

      const hasValidValues = transformedData.some(item =>
        item && typeof item.value === 'number' && !isNaN(item.value) && item.value > 0
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
