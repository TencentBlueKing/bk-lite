import type { AttrFieldType } from '@/app/cmdb/types/assetManage';
import { INST_UUID_COLUMN_KEY } from '@/app/cmdb/utils/instUuid';

const UNSUPPORTED_FILTER_ATTR_TYPES = new Set(['attachment', 'image']);

/** 列表筛选用的合成属性。只有列配置选中 UUID 时才放进检索字段。 */
export function instanceUuidFilterAttr(attrName: string): AttrFieldType {
  return {
    attr_id: INST_UUID_COLUMN_KEY,
    attr_name: attrName,
    attr_type: 'str',
    is_required: false,
    editable: false,
    option: [],
  };
}

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
