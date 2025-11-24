import { MetricItem, ListItem, UserProfile } from "@/app/mlops/types";
import { TrainDataParams, FileReadResult } from "@/app/mlops/types/manage";
import { useLocalizedTime } from "@/hooks/useLocalizedTime";
import { TYPE_FILE_MAP } from "@/app/mlops/constants";
import dayjs from "dayjs";
import JSZip from 'jszip';
import { saveAs } from 'file-saver';

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

export const handleFileRead = (text: string, type: string, include_header = false): FileReadResult => {
  const result: FileReadResult = {
    train_data: []
  };

  try {
    // 统一换行符为 \n
    const lines = text.replace(/\r\n|\r|\n/g, '\n')?.split('\n').filter(line => line.trim() !== '');

    if (lines.length) {
      console.log(TYPE_FILE_MAP[type])
      if(TYPE_FILE_MAP[type] === 'txt') {
        // txt类型文件直接返回读取到的数据
        result.train_data = lines;
      } else if (TYPE_FILE_MAP[type] === 'csv') {
        // csv文件先读取第一行的表头，然后根据表头聚合后续的数据
        const headers = lines[0]?.split(',');

        if (!headers || headers.length === 0) throw new Error('文件格式不正确');
        const data = lines.slice(1).map((line, index) => {
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
            obj['index'] = index;

            return obj;
          }, {});
        });

        result.train_data = data as TrainDataParams[];
        if(include_header) result.headers = headers;
      }
    }
    console.log(result)
    return result;
  } catch (error) {
    console.log(error);
    throw error;
  }
};

// 导出文件为csv
export const exportToCSV = (data: any[], columns: string[]) => {
  // 1. 生成表头
  const headers = columns.join(',');
  // 2. 生成数据行
  const rows = data.map(row =>
    columns.map(col => {
      let value = row[col] || 0;
      if (col === 'timestamp' && value) {
        // 支持秒或毫秒时间戳
        value = dayjs(
          typeof value === 'number'
            ? (value.toString().length === 10 ? value * 1000 : value)
            : value
        ).format('YYYY-MM-DD HH:mm:ss');
      }
      // 处理逗号、引号等特殊字符
      if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
        return `"${value.replace(/"/g, '""')}"`;
      }
      return value ?? '';
    }).join(',')
  );
  // 3. 合并为完整 CSV 字符串
  const csvContent = [headers, ...rows].join('\n');

  // 4. 创建 Blob 并下载
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  return blob;
};

export const getName = (targetID: string, data: UserProfile[] | null) => {
  if (data) {
    const target: UserProfile = data.find(u => u.id == targetID) as UserProfile;
    const name = target?.first_name + target?.last_name;
    return name || '--';
  }
  return '--';
};

// 训练数据集压缩包下载
export const exportTrainFileToZip = async (
  files: Array<{ data: any, columns: string[], filename: string }>,
  zipFilename: string = 'export.zip'
) => {
  const zip = new JSZip();

  files.forEach(({ data, columns, filename }) => {
    if (filename.endsWith('.csv')) {
      const csvBlob = exportToCSV(data, columns);
      zip.file(filename, csvBlob)
    } else if (filename.endsWith('.json')) {
      const jsonBlob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      zip.file(filename, jsonBlob);
    } else if (filename.endsWith('.txt')) {
      const _data = data?.join('\n') || '';
      const txtBlob = new Blob([_data], { type: 'text/plain' });
      zip.file(filename, txtBlob);
    }
  });

  const zipBlob = await zip.generateAsync({ type: 'blob' });
  saveAs(zipBlob, zipFilename)
};