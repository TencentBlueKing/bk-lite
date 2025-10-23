import dayjs from 'dayjs';

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
  static transformToLineBarData(rawData: any): LineBarChartData {
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
            if (namespace.data.length > 0 && typeof namespace.data[0] === 'object' && 'name' in namespace.data[0] && 'value' in namespace.data[0]) {
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
            if (namespace.data.length > 0 && typeof namespace.data[0] === 'object' && 'name' in namespace.data[0] && 'value' in namespace.data[0]) {
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
    if (rawData && rawData.namespace_id && rawData.data && Array.isArray(rawData.data)) {
      const categories: string[] = [];
      const values: number[] = [];

      // 支持新的数据格式 [{name: number, value: string}, ...]
      if (rawData.data.length > 0 && typeof rawData.data[0] === 'object' && 'name' in rawData.data[0] && 'value' in rawData.data[0]) {
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
    if (Array.isArray(rawData) && rawData.length > 0 && rawData[0] && rawData[0].namespace_id && rawData[0].data) {
      return this.transformToPieData(rawData[0].data);
    }

    // 如果数据有data属性且是数组
    if (rawData && rawData.data && Array.isArray(rawData.data)) {
      return this.transformToPieData(rawData.data);
    }

    // 如果直接是数组
    if (Array.isArray(rawData)) {
      // 检查是否是对象数组格式 [{name: 'xxx', value: 'xxx'}]
      if (rawData.length > 0 && typeof rawData[0] === 'object' && 'name' in rawData[0] && 'value' in rawData[0]) {
        return rawData.map((item: any) => ({
          name: this.formatTimeValue(item.name),
          value: parseFloat(item.value) || 0,
        }));
      }
      // 检查是否是二维数组格式 [[timestamp, value], ...]
      else if (rawData.length > 0 && Array.isArray(rawData[0]) && rawData[0].length >= 2) {
        return rawData.map((item: any[]) => {
          const name = this.formatTimeValue(item[0]);
          return {
            name: name,
            value: parseFloat(item[1]) || 0,
          };
        });
      }
      // 如果已经是正确的格式
      else if (rawData.length > 0 && typeof rawData[0] === 'object' && 'name' in rawData[0] && 'value' in rawData[0]) {
        return rawData;
      }
    }

    // 处理单个namespace的情况，取前几个数据作为饼图
    if (rawData && rawData.namespace_id && rawData.data && Array.isArray(rawData.data)) {
      return this.transformToPieData(rawData.data.slice(0, 10)); // 饼图只取前10个数据
    }

    return [];
  }

  /**
   * 检查数据是否为多系列格式 
   */
  static isMultiSeriesData(rawData: any): boolean {
    return Array.isArray(rawData) &&
      rawData.length > 0 &&
      rawData[0] &&
      typeof rawData[0] === 'object' &&
      rawData[0].namespace_id &&
      rawData[0].data;
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
   * 校验原始数据是否可以转换为折线图/柱状图数据
   */
  static validateLineBarData(rawData: any, errorMessage?: string): { isValid: boolean; message?: string } {
    // 数据为空时图表组件会显示 Empty 状态，不需要校验
    if (!rawData || (Array.isArray(rawData) && rawData.length === 0)) {
      return { isValid: true };
    }

    try {
      const transformedData = this.transformToLineBarData(rawData);

      if (!transformedData.categories || transformedData.categories.length === 0) {
        return { isValid: false, message: errorMessage || '数据格式不匹配' };
      }

      // 检查数值数据
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

  /**
   * 校验原始数据是否可以转换为饼图数据
   */
  static validatePieData(rawData: any, errorMessage?: string): { isValid: boolean; message?: string } {
    // 数据为空时图表组件会显示 Empty 状态，不需要校验
    if (!rawData) {
      return { isValid: true };
    }

    try {
      const transformedData = this.transformToPieData(rawData);

      if (!transformedData || transformedData.length === 0) {
        return { isValid: true }; // 空数据让图表组件自行处理
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
