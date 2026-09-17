export const isCloudRegionAttr = (attrId?: string): boolean =>
  attrId === 'cloud' || attrId === 'cloud_id';

export const parseCloudRegionId = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isInteger(value)) {
    return value;
  }
  if (typeof value === 'string') {
    const text = value.trim();
    if (/^-?\d+$/.test(text)) {
      return Number(text);
    }
  }
  return null;
};

export const toCloudSelectValue = (value: unknown): number | undefined => {
  const parsed = parseCloudRegionId(value);
  return parsed === null ? undefined : parsed;
};

export const buildHostCloudQueryList = (
  cloudRegion: unknown,
): Array<{ field: string; type: string; value: number }> => {
  const cloudId = parseCloudRegionId(cloudRegion);
  if (cloudId === null) {
    return [];
  }
  return [{ field: 'cloud', type: 'int=', value: cloudId }];
};

export const buildCloudRegionQueryCondition = (
  field: string,
  value: unknown,
): { field: string; type: string; value: number } | null => {
  const cloudId = parseCloudRegionId(value);
  if (cloudId === null) {
    return null;
  }
  return { field, type: 'int=', value: cloudId };
};
