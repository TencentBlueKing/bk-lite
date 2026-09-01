const UNSUPPORTED_FILTER_ATTR_TYPES = new Set(['attachment', 'image']);

export function isSearchableFilterAttr(attrType: string): boolean {
  return !UNSUPPORTED_FILTER_ATTR_TYPES.has(attrType);
}

export function visibleSearchableFilterAttrs<
  T extends { attr_id: string; attr_type: string },
>(attrList: T[], displayFieldKeys?: string[] | null): T[] {
  const searchable = attrList.filter((attr) =>
    isSearchableFilterAttr(attr.attr_type),
  );
  if (!displayFieldKeys?.length) {
    return searchable;
  }

  const byId = new Map(searchable.map((attr) => [attr.attr_id, attr]));
  const visible: T[] = [];
  for (const key of displayFieldKeys) {
    const attr = byId.get(key);
    if (attr) visible.push(attr);
  }
  return visible;
}
