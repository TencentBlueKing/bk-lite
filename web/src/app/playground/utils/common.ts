import { MetricItem, ListItem } from "@/app/playground/types";
import { useLocalizedTime } from "@/hooks/useLocalizedTime";

export const handleFileRead = (text: string) => {
  // 统一换行符为 \n
  const lines = text.replace(/\r\n|\r|\n/g, '\n')?.split('\n').filter(line => line.trim() !== '');
  if (!lines.length) return [];

  const headers = ['timestamp', 'value'];
  const data = lines.slice(1).map((line) => {
    const values = line.split(',');
    return headers.reduce((obj: Record<string, any>, key, idx) => {
      const value = values[idx];

      if (key === 'timestamp') {
        obj[key] = new Date(value).getTime() / 1000;
      }
      // else if (key === 'label') {
      //   // 🎯 处理 label 字段：如果值不存在或为空或转换为 NaN，则设为 0
      //   const numValue = Number(value);
      //   obj[key] = (!value || value.trim() === '' || isNaN(numValue)) ? 0 : numValue;
      // }
      else {
        // 处理其他数字字段（如 value）
        const numValue = Number(value);
        obj[key] = isNaN(numValue) ? 0 : numValue;
      }

      // obj['index'] = index;
      return obj;
    }, {});
  });

  return data;
};

export const handleClassFile = (text: string) => {
  // 统一换行符为 \n
  const lines = text.replace(/\r\n|\r|\n/g, '\n')?.split('\n').filter(line => line.trim() !== '');
  if (!lines.length) return {
    train_data: [],
    headers: []
  };

  const headers = lines[0].split(',');

  const data = lines.slice(1).map((line) => {
    const values = line.split(',');

    return headers.reduce((obj: Record<string, any>, key, idx) => {
      const value = values[idx];

      if (key === 'timestamp') {
        const timestamp = new Date(value).getTime();
        obj[key] = timestamp / 1000;
      } else {
        const numValue = Number(value);
        obj[key] = isNaN(numValue) ? value : numValue;
      }


      return obj;
    }, {});
  });

  return {
    train_data: data,
    headers
  };
}

// 柱形图或者折线图单条线时，获取其最大值、最小值、平均值和最新值、和
export const calculateMetrics = (data: any[], key = 'value1') => {
  if (!data || data.length === 0) return {};
  const values = data.map((item) => item[key]);
  const maxValue = Math.max(...values);
  const minValue = Math.min(...values);
  const sumValue = values.reduce((sum, value) => sum + value, 0);
  const avgValue = sumValue / values.length;
  const latestValue = values[values.length - 1];
  return {
    maxValue,
    minValue,
    avgValue,
    sumValue,
    latestValue,
  };
};

// 判断一个字符串是否是字符串的数组
export const isStringArray = (input: string): boolean => {
  try {
    if (typeof input !== 'string') {
      return false;
    }
    const parsed = JSON.parse(input);
    if (!Array.isArray(parsed)) {
      return false;
    }
    return true;
  } catch {
    return false;
  }
};

// 根据指标枚举获取值
export const getEnumValue = (metric: MetricItem, id: number | string) => {
  const { unit: input = '' } = metric || {};
  if (!id && id !== 0) return '--';
  if (isStringArray(input)) {
    return (
      JSON.parse(input).find((item: ListItem) => item.id === id)?.name || id
    );
  }
  return isNaN(+id)
    ? id
    : (+id).toFixed(2);
};

// 格式化数据为百分比形式
export const formatProbability = (probability: number | undefined): string => {
  if (probability === undefined || probability === null) return '';
  return `${(probability * 100).toFixed(2)}%`;
};

// 获取随机颜色
export const generateUniqueRandomColor = (() => {
  const generatedColors = new Set<string>();
  return (): string => {
    const letters = '0123456789ABCDEF';
    let color;
    do {
      color = '#';
      for (let i = 0; i < 6; i++) {
        color += letters[Math.floor(Math.random() * 16)];
      }
    } while (generatedColors.has(color));
    generatedColors.add(color);
    return color;
  };
})();

// 图标中x轴的时间回显处理
export const useFormatTime = () => {
  const { convertToLocalizedTime } = useLocalizedTime();
  const formatTime = (timestamp: number, minTime: number, maxTime: number) => {
    const totalTimeSpan = maxTime - minTime;
    const time = new Date(timestamp * 1000) + '';
    if (totalTimeSpan === 0) {
      return convertToLocalizedTime(time, 'YYYY-MM-DD HH:mm:ss');
    }
    if (totalTimeSpan <= 24 * 60 * 60) {
      // 如果时间跨度在一天以内，显示小时分钟
      return convertToLocalizedTime(time, 'HH:mm:ss');
    }
    if (totalTimeSpan <= 30 * 24 * 60 * 60) {
      // 如果时间跨度在一个月以内，显示月日
      return convertToLocalizedTime(time, 'MM-DD HH:mm');
    }
    if (totalTimeSpan <= 365 * 24 * 60 * 60) {
      // 如果时间跨度在一年以内，显示年月日
      return convertToLocalizedTime(time, 'YYYY-MM-DD');
    }
    // 否则显示年月
    return convertToLocalizedTime(time, 'YYYY-MM');
  };
  return { formatTime };
};