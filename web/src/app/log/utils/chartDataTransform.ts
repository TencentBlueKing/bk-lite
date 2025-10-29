import dayjs from 'dayjs';
import { formatNumericValue } from './common';

export interface ChartDataItem {
  name: string;
  value: number;
}

export interface SeriesDataItem {
  name: string;
  data: (number | null)[];
}

export interface LineBarChartData {
  categories: string[];
  values?: (number | null)[];
  series?: SeriesDataItem[];
}

export type PieChartData = ChartDataItem[];

export interface LineChartConfig {
  type: 'single' | 'multiple';
  key: string;
  value: string;
  tooltipField?: string;
}

/**
 * 通用数据转换函数
 * 支持多种数据格式转换为图表数据
 */
export class ChartDataTransformer {
  /**
   * 格式化时间显示
   */
  static formatTimeValue(value: any): string {
    if (typeof value === 'number') {
      // 数字时间戳
      return dayjs(value * 1000).format('MM-DD HH:mm:ss');
    } else if (typeof value === 'string') {
      // 检查是否是 ISO 8601 格式的时间字符串
      const dateValue = dayjs(value);
      if (dateValue.isValid()) {
        return dateValue.format('MM-DD HH:mm:ss');
      }
      // 如果不是有效的时间字符串，直接返回
      return value;
    }
    return String(value);
  }

  /**
   * 转换为折线图/柱状图数据格式
   */
  static transformToLineBarData(
    rawData: any,
    config?: LineChartConfig
  ): LineBarChartData {
    // 如果传入了config，使用新的逻辑处理
    if (config) {
      return this.transformTimeSeriesData(rawData, config);
    }

    // 保持原有逻辑不变
    if (!rawData) {
      return { categories: [], values: [] };
    }

    if (Array.isArray(rawData) && rawData.length === 0) {
      return { categories: [], values: [] };
    }

    if (Array.isArray(rawData) && rawData.length > 0) {
      // 检查是否是新的对象格式 [{name: "xxx", count: 20}, ...]
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
      // 检查是否是多维数据（多个系列）
      else if (
        rawData[0] &&
        typeof rawData[0] === 'object' &&
        rawData[0].namespace_id &&
        rawData[0].data
      ) {
        const allCategoriesSet = new Set<string>();
        rawData.forEach((namespace: any) => {
          if (namespace.data && Array.isArray(namespace.data)) {
            // 支持新的数据格式 [{name: number, value: string}, ...]
            if (
              namespace.data.length > 0 &&
              typeof namespace.data[0] === 'object' &&
              'name' in namespace.data[0] &&
              'value' in namespace.data[0]
            ) {
              namespace.data.forEach((item: any) => {
                // 格式化时间显示
                const category = this.formatTimeValue(item.name);
                allCategoriesSet.add(category);
              });
            } else {
              // 原有格式 [[key, value], ...]
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
            // 支持新的数据格式 [{name: number, value: string}, ...]
            if (
              namespace.data.length > 0 &&
              typeof namespace.data[0] === 'object' &&
              'name' in namespace.data[0] &&
              'value' in namespace.data[0]
            ) {
              namespace.data.forEach((item: any) => {
                // 格式化时间显示
                const category = this.formatTimeValue(item.name);
                dataMap[category] = parseFloat(item.value) || 0;
              });
            } else {
              // 原有格式 [[key, value], ...]
              namespace.data.forEach((item: any[]) => {
                dataMap[item[0]] = item[1];
              });
            }
          }

          const values = categories.map((category) => dataMap[category] || 0);

          return {
            name: namespace.namespace_id,
            data: values,
          };
        });

        return { categories, series };
      } else {
        // 原有的二维数组格式 [[key, value], ...]
        const categories = rawData.map((item: any[]) => item[0]);
        const values = rawData.map((item: any[]) => item[1]);
        return { categories, values };
      }
    }

    // 处理单个namespace的情况
    if (
      rawData &&
      rawData.namespace_id &&
      rawData.data &&
      Array.isArray(rawData.data)
    ) {
      const categories: string[] = [];
      const values: number[] = [];

      // 支持新的数据格式 [{name: number, value: string}, ...]
      if (
        rawData.data.length > 0 &&
        typeof rawData.data[0] === 'object' &&
        'name' in rawData.data[0] &&
        'value' in rawData.data[0]
      ) {
        rawData.data.forEach((item: any) => {
          // 格式化时间显示
          const category = this.formatTimeValue(item.name);
          categories.push(category);
          values.push(parseFloat(item.value) || 0);
        });
      } else {
        // 原有格式 [[key, value], ...]
        rawData.data.forEach((item: any[]) => {
          categories.push(item[0]);
          values.push(item[1]);
        });
      }

      return { categories, values };
    }

    return { categories: [], values: [] };
  }

  /**
   * 转换为饼图数据格式
   */
  static transformToPieData(rawData: any): PieChartData {
    if (!rawData) {
      return [];
    }

    // 如果是数组且第一个元素有namespace_id，取第一个namespace的数据
    if (
      Array.isArray(rawData) &&
      rawData.length > 0 &&
      rawData[0] &&
      rawData[0].namespace_id &&
      rawData[0].data
    ) {
      return this.transformToPieData(rawData[0].data);
    }

    // 如果数据有data属性且是数组
    if (rawData && rawData.data && Array.isArray(rawData.data)) {
      return this.transformToPieData(rawData.data);
    }

    // 如果直接是数组
    if (Array.isArray(rawData)) {
      // 检查是否是对象数组格式 [{name: 'xxx', value: 'xxx'}]
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
      // 检查是否是二维数组格式 [[timestamp, value], ...]
      else if (
        rawData.length > 0 &&
        Array.isArray(rawData[0]) &&
        rawData[0].length >= 2
      ) {
        return rawData.map((item: any[]) => {
          const name = this.formatTimeValue(item[0]);
          return {
            name: name,
            value: parseFloat(item[1]) || 0,
          };
        });
      }
      // 如果已经是正确的格式
      else if (
        rawData.length > 0 &&
        typeof rawData[0] === 'object' &&
        'name' in rawData[0] &&
        'value' in rawData[0]
      ) {
        return rawData;
      }
    }

    // 处理单个namespace的情况，取前几个数据作为饼图
    if (
      rawData &&
      rawData.namespace_id &&
      rawData.data &&
      Array.isArray(rawData.data)
    ) {
      return this.transformToPieData(rawData.data.slice(0, 10)); // 饼图只取前10个数据
    }

    return [];
  }

  /**
   * 检查数据是否为多系列格式
   */
  static isMultiSeriesData(rawData: any): boolean {
    return (
      Array.isArray(rawData) &&
      rawData.length > 0 &&
      rawData[0] &&
      typeof rawData[0] === 'object' &&
      rawData[0].namespace_id &&
      rawData[0].data
    );
  }

  /**
   * 检查数据是否有效
   */
  static hasValidData(data: LineBarChartData | PieChartData): boolean {
    if (Array.isArray(data)) {
      return data.length > 0;
    }
    return data.categories && data.categories.length > 0;
  }

  /**
   * 转换时间序列数据为折线图格式
   * 支持单线和多线图表
   */
  static transformTimeSeriesData(
    rawData: any[],
    config: LineChartConfig
  ): LineBarChartData {
    if (!Array.isArray(rawData) || rawData.length === 0) {
      return { categories: [], values: [] };
    }

    const { type, key, value } = config;

    if (type === 'single') {
      return this.transformSingleLine(rawData, { key, value });
    } else if (type === 'multiple') {
      return this.transformMultipleLines(rawData, { key, value });
    }

    return { categories: [], values: [] };
  }

  /**
   * 转换单线数据
   */
  private static transformSingleLine(
    rawData: any[],
    displayMaps: { key: string; value: string }
  ): LineBarChartData {
    const categories: string[] = [];
    const values: (number | null)[] = [];

    // 按时间排序
    const sortedData = rawData
      .filter((item) => item._time && item[displayMaps.value] !== undefined)
      .sort(
        (a, b) => new Date(a._time).getTime() - new Date(b._time).getTime()
      );

    sortedData.forEach((item) => {
      const timeStr = this.formatTimeValue(item._time);
      const value = formatNumericValue(item[displayMaps.value]);

      categories.push(timeStr);
      values.push(typeof value === 'number' ? value : null);
    });

    return { categories, values };
  }

  /**
   * 转换多线数据
   */
  private static transformMultipleLines(
    rawData: any[],
    displayMaps: { key: string; value: string }
  ): LineBarChartData {
    // 获取所有唯一的时间点
    const allTimes = [...new Set(rawData.map((item) => item._time))]
      .filter((time) => time)
      .sort((a, b) => new Date(a).getTime() - new Date(b).getTime());

    const categories = allTimes.map((time) => this.formatTimeValue(time));

    // 获取所有唯一的系列名称（根据key字段分组）
    const seriesNames = [
      ...new Set(
        rawData
          .filter((item) => item[displayMaps.key])
          .map((item) => item[displayMaps.key])
      ),
    ];

    // 如果没有系列名称，创建一个默认系列
    if (seriesNames.length === 0) {
      const values: (number | null)[] = [];
      const timeValueMap: { [key: string]: number | null } = {};

      // 构建时间值映射
      rawData.forEach((item) => {
        if (item._time && item[displayMaps.value] !== undefined) {
          const timeStr = this.formatTimeValue(item._time);
          const value = formatNumericValue(item[displayMaps.value]);
          timeValueMap[timeStr] = typeof value === 'number' ? value : null;
        }
      });

      // 填充数据，缺失的时间点用null填充（让折线断开）
      categories.forEach((category) => {
        values.push(timeValueMap[category] ?? null);
      });

      return { categories, values };
    }

    // 为每个系列构建数据
    const series = seriesNames.map((seriesName) => {
      const timeValueMap: { [key: string]: number | null } = {};

      // 获取该系列的所有数据点
      rawData
        .filter((item) => item[displayMaps.key] === seriesName)
        .forEach((item) => {
          if (item._time && item[displayMaps.value] !== undefined) {
            const timeStr = this.formatTimeValue(item._time);
            const value = formatNumericValue(item[displayMaps.value]);
            timeValueMap[timeStr] = typeof value === 'number' ? value : null;
          }
        });

      // 根据所有时间点填充数据，缺失的用null填充（让折线断开）
      const data = categories.map((category) => timeValueMap[category] ?? null);

      return {
        name: seriesName,
        data,
      };
    });

    return { categories, series };
  }
}
