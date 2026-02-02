import type { AlgorithmConfig, FieldConfig } from '@/app/mlops/types/task';
import { get } from 'lodash';

/**
 * 逗号分隔字符串转数组（自动转换数字）
 */
export const stringToArray = (str: string): any[] => {
  if (!str) return [];
  return str.split(',').map(item => {
    const trimmed = item.trim();
    const num = Number(trimmed);
    return isNaN(num) ? trimmed : num;
  });
};

/**
 * 数组转逗号分隔字符串
 */
export const arrayToString = (arr: any[]): string => {
  return arr ? arr.join(',') : '';
};

/**
 * 转换单个组的数据（表单 → API）
 * @param formValues 表单数据
 * @param fields 字段配置数组
 * @returns 转换后的对象
 */
export const transformGroupData = (formValues: any, fields: FieldConfig[]): any => {
  const result: any = {};

  fields.forEach(field => {
    const fieldName = Array.isArray(field.name) ? field.name : [field.name];
    const value = get(formValues, fieldName);

    if (value === undefined) return;

    // 转换 stringArray 类型
    if (field.type === 'stringArray' && typeof value === 'string') {
      setNestedValue(result, fieldName, stringToArray(value));
    } else {
      setNestedValue(result, fieldName, value);
    }
  });

  return result;
};

/**
 * 反向转换单个组的数据（API → 表单）
 * @param apiData API数据
 * @param fields 字段配置数组
 * @param groupPrefix 组前缀（如 'hyperparams'）
 * @returns 表单数据对象
 */
export const reverseTransformGroupData = (apiData: any, fields: FieldConfig[]): any => {
  const result: any = {};

  fields.forEach(field => {
    const fieldName = Array.isArray(field.name) ? field.name : [field.name];
    
    // 从完整路径读取值，支持跨组字段
    const value = get(apiData, fieldName);

    if (value === undefined) return;

    // 转换 stringArray 类型
    if (field.type === 'stringArray' && Array.isArray(value)) {
      setNestedValue(result, fieldName, arrayToString(value));
    } else {
      setNestedValue(result, fieldName, value);
    }
  });

  return result;
};

/**
 * 从配置中提取默认值
 * @param config 算法配置
 * @returns 默认值对象
 */
export const extractDefaultValues = (config: AlgorithmConfig): any => {
  const result: any = {};

  Object.entries(config.groups).forEach(([, groupConfigs]) => {
    groupConfigs.forEach(groupConfig => {
      groupConfig.fields.forEach(field => {
        if (field.defaultValue !== undefined) {
          const fieldName = Array.isArray(field.name) ? field.name : [field.name];
          setNestedValue(result, fieldName, field.defaultValue);
        }
      });
    });
  });

  return result;
};

/**
 * 设置嵌套对象的值
 * @param obj 目标对象
 * @param path 路径数组
 * @param value 值
 */
const setNestedValue = (obj: any, path: (string | number)[], value: any): void => {
  if (path.length === 0) return;

  let current = obj;
  for (let i = 0; i < path.length - 1; i++) {
    const key = path[i];
    if (!current[key] || typeof current[key] !== 'object') {
      current[key] = {};
    }
    current = current[key];
  }

  current[path[path.length - 1]] = value;
};
