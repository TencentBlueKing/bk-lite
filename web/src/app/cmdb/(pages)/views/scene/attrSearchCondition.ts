import type { AttrFieldType } from '@/app/cmdb/types/assetManage';

export const MAX_SEARCH_LENGTH = 128;

export const UNSUPPORTED_SEARCH_ATTR_TYPES = new Set([
  'attachment',
  'image',
  'table',
]);

export interface AttrSearchClause {
  field: string;
  type: string;
  value?: string | number | boolean | Array<string | number>;
  start?: string;
  end?: string;
  accurate?: boolean;
}

export const searchableAttrs = (attrList: AttrFieldType[]): AttrFieldType[] =>
  attrList.filter((attr) => !UNSUPPORTED_SEARCH_ATTR_TYPES.has(attr.attr_type));

export const defaultSearchField = (attrList: AttrFieldType[]): string => {
  const attrs = searchableAttrs(attrList);
  return attrs.find((attr) => attr.attr_id === 'inst_name')?.attr_id || attrs[0]?.attr_id || '';
};

export const isEmptySearchValue = (attr: AttrFieldType | undefined, value: unknown): boolean => {
  if (value === false || value === 0) return false;
  if (value == null || value === '') return true;
  if (Array.isArray(value) && !value.length) return true;
  if (attr?.attr_type === 'time') {
    return !Array.isArray(value) || !value[0] || !value[1];
  }
  return false;
};

const boundText = (value: unknown): string => {
  if (typeof value !== 'string') return '';
  return value.trim().slice(0, MAX_SEARCH_LENGTH);
};

export const buildAttrSearchCondition = (
  attr: AttrFieldType | undefined,
  value: unknown,
  exact = false
): AttrSearchClause | null => {
  if (!attr?.attr_id) return null;
  if (isEmptySearchValue(attr, value)) return null;

  if (attr.attr_id === 'cloud') {
    const text = typeof value === 'number' ? String(value) : boundText(value);
    if (!text && typeof value !== 'number') return null;
    return {
      field: attr.attr_id,
      type: typeof value === 'number' ? 'int=' : 'str=',
      value: typeof value === 'number' ? value : text,
    };
  }

  switch (attr.attr_type) {
    case 'enum': {
      const selected = (Array.isArray(value) ? value : [value]).filter(
        (item) => item !== '' && item != null
      ) as Array<string | number>;
      if (!selected.length) return null;
      return { field: attr.attr_id, type: 'list_any[]', value: selected };
    }
    case 'str': {
      const text = boundText(value);
      if (!text) return null;
      return {
        field: attr.attr_id,
        type: exact ? 'str=' : 'str*',
        value: text,
      };
    }
    case 'user':
    case 'organization': {
      const selected = (Array.isArray(value) ? value : [value]).filter(
        (item) => item !== '' && item != null
      ) as Array<string | number>;
      if (!selected.length) return null;
      return { field: attr.attr_id, type: 'list[]', value: selected };
    }
    case 'int': {
      const number = typeof value === 'number' ? value : Number(value);
      if (!Number.isFinite(number)) return null;
      return { field: attr.attr_id, type: 'int=', value: number };
    }
    case 'tag': {
      const selected = (Array.isArray(value) ? value : value ? [value] : [])
        .map((item) => boundText(item))
        .filter(Boolean);
      if (!selected.length) return null;
      return {
        field: attr.attr_id,
        type: 'list_any[]',
        value: selected,
        accurate: true,
      };
    }
    case 'bool':
      if (value !== true && value !== false) return null;
      return { field: attr.attr_id, type: 'bool', value };
    case 'time': {
      const start = boundText(Array.isArray(value) ? value[0] : '');
      const end = boundText(Array.isArray(value) ? value[1] : '');
      if (!start || !end) return null;
      return { field: attr.attr_id, type: 'time', start, end };
    }
    default: {
      const text = boundText(value);
      if (!text) return null;
      return {
        field: attr.attr_id,
        type: exact ? 'str=' : 'str*',
        value: text,
      };
    }
  }
};
