/** 分享桩和详情接口都可能把 id 收成数字或数字字符串。只认正整数，避免 "12abc" 被 parseInt 截断。 */
export const normalizeDatasourceRecordId = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isInteger(value) && value > 0 && Number.isSafeInteger(value)) {
    return value;
  }
  if (typeof value === 'string') {
    const text = value.trim();
    if (!/^[1-9]\d*$/.test(text)) {
      return undefined;
    }
    const parsed = Number(text);
    return Number.isSafeInteger(parsed) ? parsed : undefined;
  }
  return undefined;
};

export const retainRequestedDatasources = <T extends { id?: unknown }>(
  items: readonly T[],
  requestedIds: readonly number[],
): Array<T & { id: number }> => {
  const wanted = new Set(requestedIds);
  const selected: Array<T & { id: number }> = [];
  items.forEach((item) => {
    const id = normalizeDatasourceRecordId(item?.id);
    if (id === undefined || !wanted.has(id)) {
      return;
    }
    selected.push(item.id === id ? (item as T & { id: number }) : { ...item, id });
  });
  return selected;
};

export const readDatasourceLookupList = (response: unknown): unknown[] => {
  if (Array.isArray(response)) {
    return response;
  }
  if (
    response
    && typeof response === 'object'
    && Array.isArray((response as { items?: unknown }).items)
  ) {
    return (response as { items: unknown[] }).items;
  }
  return [];
};
