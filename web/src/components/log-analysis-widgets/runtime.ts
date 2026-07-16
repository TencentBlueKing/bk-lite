import dayjs from 'dayjs';
import type {
  LineBarChartData,
  LineChartConfig,
  PieChartData,
} from '@/components/log-analysis-widgets/types';

export const formatNumericValue = (value: any): string | number => {
  try {
    if (value === null || value === undefined || value === '') {
      return '--';
    }
    if (typeof value === 'number') {
      if (isFinite(value)) {
        return Number(value.toFixed(2));
      }
      return value;
    }
    if (typeof value === 'string') {
      const trimmedValue = value.trim();
      if (trimmedValue === '') {
        return value;
      }
      const numValue = Number(trimmedValue);
      if (!isNaN(numValue) && isFinite(numValue)) {
        return Number(numValue.toFixed(2));
      }
    }
    return value;
  } catch {
    return value;
  }
};

export class ChartDataTransformer {
  static formatTimeValue(value: any): string {
    if (typeof value === 'number') {
      return dayjs(value * 1000).format('MM-DD HH:mm:ss');
    }
    if (typeof value === 'string') {
      const dateValue = dayjs(value);
      if (dateValue.isValid()) {
        return dateValue.format('MM-DD HH:mm:ss');
      }
      return value;
    }
    return String(value);
  }

  static transformToLineBarData(
    rawData: any,
    config?: LineChartConfig,
  ): LineBarChartData {
    if (config) {
      return this.transformTimeSeriesData(rawData, config);
    }

    if (!rawData) {
      return { categories: [], values: [] };
    }

    if (Array.isArray(rawData) && rawData.length === 0) {
      return { categories: [], values: [] };
    }

    if (Array.isArray(rawData) && rawData.length > 0) {
      if (
        rawData[0] &&
        typeof rawData[0] === 'object' &&
        'name' in rawData[0] &&
        'count' in rawData[0]
      ) {
        const categories = rawData.map((item: any) => item.name);
        const values = rawData.map((item: any) => item.count);
        return { categories, values };
      }
      if (
        rawData[0] &&
        typeof rawData[0] === 'object' &&
        rawData[0].namespace_id &&
        rawData[0].data
      ) {
        const allCategoriesSet = new Set<string>();
        rawData.forEach((namespace: any) => {
          if (namespace.data && Array.isArray(namespace.data)) {
            if (
              namespace.data.length > 0 &&
              typeof namespace.data[0] === 'object' &&
              'name' in namespace.data[0] &&
              'value' in namespace.data[0]
            ) {
              namespace.data.forEach((item: any) => {
                const category = this.formatTimeValue(item.name);
                allCategoriesSet.add(category);
              });
            } else {
              namespace.data.forEach((item: any[]) => {
                allCategoriesSet.add(item[0]);
              });
            }
          }
        });
        const categories = Array.from(allCategoriesSet).sort();

        const series = rawData.map((namespace: any) => {
          const dataMap: { [key: string]: number } = {};
          if (namespace.data && Array.isArray(namespace.data)) {
            if (
              namespace.data.length > 0 &&
              typeof namespace.data[0] === 'object' &&
              'name' in namespace.data[0] &&
              'value' in namespace.data[0]
            ) {
              namespace.data.forEach((item: any) => {
                const category = this.formatTimeValue(item.name);
                dataMap[category] = parseFloat(item.value) || 0;
              });
            } else {
              namespace.data.forEach((item: any[]) => {
                dataMap[item[0]] = item[1];
              });
            }
          }

          return {
            name: namespace.namespace_id,
            data: categories.map((category) => dataMap[category] || 0),
          };
        });

        return { categories, series };
      }

      const categories = rawData.map((item: any[]) => item[0]);
      const values = rawData.map((item: any[]) => item[1]);
      return { categories, values };
    }

    if (
      rawData &&
      rawData.namespace_id &&
      rawData.data &&
      Array.isArray(rawData.data)
    ) {
      const categories: string[] = [];
      const values: number[] = [];

      if (
        rawData.data.length > 0 &&
        typeof rawData.data[0] === 'object' &&
        'name' in rawData.data[0] &&
        'value' in rawData.data[0]
      ) {
        rawData.data.forEach((item: any) => {
          categories.push(this.formatTimeValue(item.name));
          values.push(parseFloat(item.value) || 0);
        });
      } else {
        rawData.data.forEach((item: any[]) => {
          categories.push(item[0]);
          values.push(item[1]);
        });
      }

      return { categories, values };
    }

    return { categories: [], values: [] };
  }

  static transformToPieData(rawData: any): PieChartData {
    if (!rawData) {
      return [];
    }

    if (
      Array.isArray(rawData) &&
      rawData.length > 0 &&
      rawData[0] &&
      rawData[0].namespace_id &&
      rawData[0].data
    ) {
      return this.transformToPieData(rawData[0].data);
    }

    if (rawData && rawData.data && Array.isArray(rawData.data)) {
      return this.transformToPieData(rawData.data);
    }

    if (Array.isArray(rawData)) {
      if (
        rawData.length > 0 &&
        typeof rawData[0] === 'object' &&
        'name' in rawData[0] &&
        'value' in rawData[0]
      ) {
        return rawData.map((item: any) => ({
          name: this.formatTimeValue(item.name),
          value: parseFloat(item.value) || 0,
        }));
      }
      if (
        rawData.length > 0 &&
        Array.isArray(rawData[0]) &&
        rawData[0].length >= 2
      ) {
        return rawData.map((item: any[]) => ({
          name: this.formatTimeValue(item[0]),
          value: parseFloat(item[1]) || 0,
        }));
      }
    }

    if (
      rawData &&
      rawData.namespace_id &&
      rawData.data &&
      Array.isArray(rawData.data)
    ) {
      return this.transformToPieData(rawData.data.slice(0, 10));
    }

    return [];
  }

  static transformTimeSeriesData(
    rawData: any[],
    config: LineChartConfig,
  ): LineBarChartData {
    if (!Array.isArray(rawData) || rawData.length === 0) {
      return { categories: [], values: [] };
    }

    const { type, key, value } = config;

    if (type === 'single') {
      return this.transformSingleLine(rawData, { key, value });
    }
    if (type === 'dual') {
      return this.transformDualFields(rawData, config);
    }
    if (type === 'multiple') {
      return this.transformMultipleLines(rawData, { key, value });
    }

    return { categories: [], values: [] };
  }

  private static transformSingleLine(
    rawData: any[],
    displayMaps: { key: string; value: string },
  ): LineBarChartData {
    const categories: string[] = [];
    const values: (number | null)[] = [];

    const sortedData = rawData
      .filter((item) => item._time && item[displayMaps.value] !== undefined)
      .sort((a, b) => new Date(a._time).getTime() - new Date(b._time).getTime());

    sortedData.forEach((item) => {
      categories.push(this.formatTimeValue(item._time));
      const value = formatNumericValue(item[displayMaps.value]);
      values.push(typeof value === 'number' ? value : null);
    });

    return { categories, values };
  }

  private static transformDualFields(
    rawData: any[],
    config: LineChartConfig,
  ): LineBarChartData {
    const barField = config.barField || config.value;
    const lineField = config.lineField || config.key;
    const barLabel = config.barLabel || barField;
    const lineLabel = config.lineLabel || lineField;

    const sortedData = rawData
      .filter((item) => item._time)
      .sort((a, b) => new Date(a._time).getTime() - new Date(b._time).getTime());

    const categories: string[] = [];
    const barData: (number | null)[] = [];
    const lineData: (number | null)[] = [];

    sortedData.forEach((item) => {
      categories.push(this.formatTimeValue(item._time));
      const bv = formatNumericValue(item[barField]);
      const lv = formatNumericValue(item[lineField]);
      barData.push(typeof bv === 'number' ? bv : null);
      lineData.push(typeof lv === 'number' ? lv : null);
    });

    return {
      categories,
      series: [
        { name: barLabel, data: barData },
        { name: lineLabel, data: lineData },
      ],
    };
  }

  private static transformMultipleLines(
    rawData: any[],
    displayMaps: { key: string; value: string },
  ): LineBarChartData {
    const allTimes = [...new Set(rawData.map((item) => item._time))]
      .filter((time) => time)
      .sort((a, b) => new Date(a as string).getTime() - new Date(b as string).getTime());

    const categories = allTimes.map((time) => this.formatTimeValue(time));
    const seriesNames = [
      ...new Set(
        rawData
          .filter((item) => item[displayMaps.key])
          .map((item) => item[displayMaps.key]),
      ),
    ];

    if (seriesNames.length === 0) {
      const values: (number | null)[] = [];
      const timeValueMap: { [key: string]: number | null } = {};

      rawData.forEach((item) => {
        if (item._time && item[displayMaps.value] !== undefined) {
          const timeStr = this.formatTimeValue(item._time);
          const value = formatNumericValue(item[displayMaps.value]);
          timeValueMap[timeStr] = typeof value === 'number' ? value : null;
        }
      });

      categories.forEach((category) => {
        values.push(timeValueMap[category] ?? null);
      });

      return { categories, values };
    }

    const series = seriesNames.map((seriesName) => {
      const timeValueMap: { [key: string]: number | null } = {};

      rawData
        .filter((item) => item[displayMaps.key] === seriesName)
        .forEach((item) => {
          if (item._time && item[displayMaps.value] !== undefined) {
            const timeStr = this.formatTimeValue(item._time);
            const value = formatNumericValue(item[displayMaps.value]);
            timeValueMap[timeStr] = typeof value === 'number' ? value : null;
          }
        });

      return {
        name: seriesName,
        data: categories.map((category) => timeValueMap[category] ?? null),
      };
    });

    return { categories, series };
  }
}
