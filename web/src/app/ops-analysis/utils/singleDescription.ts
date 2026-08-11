import { getValueByPath } from '@/app/ops-analysis/utils/objectPath';

/** 从单值数据中解析可选说明文案；未选字段或空值返回 undefined。 */
export const resolveSingleDescriptionText = (
  rawData: unknown,
  descriptionField?: string,
): string | undefined => {
  const field = descriptionField?.trim();
  if (!field) return undefined;
  const value = getValueByPath(rawData, field);
  if (value === null || value === undefined) return undefined;
  const text = String(value);
  return text === '' ? undefined : text;
};
