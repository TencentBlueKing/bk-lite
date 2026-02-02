/**
 * 表单数据转换工具函数
 * 用于在表单编辑格式和后端数据格式之间进行转换
 */

/**
 * 对象转键值对数组（用于 environment 环境变量）
 * @param obj - 对象，如 {NODE_ENV: 'production', PORT: '8080'}
 * @returns 键值对数组，如 [{key: 'NODE_ENV', value: 'production'}, {key: 'PORT', value: '8080'}]
 * 
 * 边界处理：
 * - null/undefined → []
 * - {} → []
 */
export const objectToPairs = (obj: Record<string, string> | null | undefined): Array<{ key: string; value: string }> => {
  if (!obj) return [];
  return Object.entries(obj).map(([key, value]) => ({ key, value }));
};

/**
 * 键值对数组转对象（提交时使用）
 * @param pairs - 键值对数组
 * @returns 对象
 * 
 * 边界处理：
 * - null/undefined → {}
 * - [] → {}
 * - 只保留 key 和 value 都存在且非空的项
 */
export const pairsToObject = (pairs: Array<{ key: string; value: string }> | null | undefined): Record<string, string> => {
  if (!pairs || pairs.length === 0) return {};
  
  const result: Record<string, string> = {};
  pairs.forEach((pair) => {
    if (pair.key && pair.value) {
      result[pair.key] = pair.value;
    }
  });
  
  return result;
};

/**
 * 字符串数组转对象数组（用于 command/args）
 * @param arr - 字符串数组，如 ['npm', 'start']
 * @param fieldName - 字段名，如 'command' 或 'arg'
 * @returns 对象数组，如 [{command: 'npm'}, {command: 'start'}]
 * 
 * 边界处理：
 * - null/undefined → []
 * - [] → []
 */
export const stringArrayToPairs = <T extends string>(
  arr: string[] | null | undefined,
  fieldName: T
): Array<Record<T, string>> => {
  if (!arr) return [];
  return arr.map((item) => ({ [fieldName]: item } as Record<T, string>));
};

/**
 * 对象数组转字符串数组（提交时使用）
 * @param pairs - 对象数组
 * @param fieldName - 字段名
 * @returns 字符串数组
 * 
 * 边界处理：
 * - null/undefined → []
 * - [] → []
 * - 过滤掉值为空的项
 */
export const pairsToStringArray = <T extends string>(
  pairs: Array<Record<T, string>> | null | undefined,
  fieldName: T
): string[] => {
  if (!pairs || pairs.length === 0) return [];
  
  const result: string[] = [];
  pairs.forEach((pair) => {
    const value = pair[fieldName];
    if (value) {
      result.push(value);
    }
  });
  
  return result;
};

/**
 * 数字数组转对象数组（用于 ports）
 * @param arr - 数字数组，如 [8080, 3000]
 * @param fieldName - 字段名，如 'port'
 * @returns 对象数组，如 [{port: 8080}, {port: 3000}]
 * 
 * 边界处理：
 * - null/undefined → []
 * - [] → []
 */
export const numberArrayToPairs = <T extends string>(
  arr: number[] | null | undefined,
  fieldName: T
): Array<Record<T, number>> => {
  if (!arr) return [];
  return arr.map((item) => ({ [fieldName]: item } as Record<T, number>));
};

/**
 * 对象数组转数字数组（提交时使用）
 * @param pairs - 对象数组
 * @param fieldName - 字段名
 * @returns 数字数组
 * 
 * 边界处理：
 * - null/undefined → []
 * - [] → []
 * - 过滤掉值为 0、null、undefined 的项
 * - 强制类型转换为 Number
 */
export const pairsToNumberArray = <T extends string>(
  pairs: Array<Record<T, number | string>> | null | undefined,
  fieldName: T
): number[] => {
  if (!pairs || pairs.length === 0) return [];
  
  const result: number[] = [];
  pairs.forEach((pair) => {
    const value = pair[fieldName];
    if (value) {
      result.push(Number(value));
    }
  });
  
  return result;
};

/**
 * 对象数组转对象数组（用于复杂对象如 volumes）
 * @param arr - 源对象数组
 * @param transform - 转换函数
 * @returns 转换后的对象数组
 * 
 * 边界处理：
 * - null/undefined → []
 * - [] → []
 */
export const transformObjectArray = <T, R>(
  arr: T[] | null | undefined,
  transform: (item: T) => R
): R[] => {
  if (!arr) return [];
  return arr.map(transform);
};
