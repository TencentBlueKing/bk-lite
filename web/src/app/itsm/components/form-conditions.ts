import isEqualWith from 'lodash/isEqualWith';
import type { FormFieldSchema } from '../types';

// JSON 中布尔值和数值在 Python 条件引擎中可以比较，包括列表内的元素。
const isNumber = (value: unknown) => typeof value === 'number' || typeof value === 'boolean';
const equal = (left: unknown, right: unknown) => isEqualWith(left, right, (a, b) =>
  isNumber(a) && isNumber(b) ? Number(a) === Number(b) : undefined);

function compare(left: unknown, right: unknown): number | undefined {
  if (isNumber(left) && isNumber(right)) return Number(left) - Number(right);
  if (typeof left === 'string' && typeof right === 'string') {
    // 服务端按 Unicode 码点排序。
    return compare(Array.from(left, char => char.codePointAt(0)), Array.from(right, char => char.codePointAt(0)));
  }
  if (Array.isArray(left) && Array.isArray(right)) {
    for (let i = 0; i < Math.min(left.length, right.length); i++) {
      if (!equal(left[i], right[i])) return compare(left[i], right[i]);
    }
    return left.length - right.length;
  }
  return undefined;
}

const includes = (collection: unknown, value: unknown) => {
  if (Array.isArray(collection)) return collection.some(item => equal(item, value));
  if (typeof collection === 'string') return typeof value === 'string' && collection.includes(value);
  return collection != null && typeof collection === 'object' && typeof value === 'string' && Object.hasOwn(collection, value);
};

export function matches(rule: FormFieldSchema['visibleWhen'], values: Record<string, unknown>): boolean {
  if (!rule) return true;
  if ('logic' in rule) return rule.logic === 'and'
    ? rule.items.every(item => matches(item, values))
    : rule.items.some(item => matches(item, values));

  const actual = rule.field.split('.').reduce<unknown>((obj, key) =>
    obj && typeof obj === 'object' && !Array.isArray(obj) && Object.hasOwn(obj, key) ? obj[key] : null, values) ?? null;
  const expected = rule.value ?? null;
  switch (rule.op) {
    case '=': return equal(actual, expected);
    case '!=': return !equal(actual, expected);
    case 'in': return Array.isArray(actual) ? actual.some(item => includes(expected, item)) : includes(expected, actual);
    case 'not_in': return !includes(expected, actual);
    case 'contains': return includes(actual, expected);
    case 'is_empty':
    case 'not_empty': {
      const empty = actual == null || actual === '' || (typeof actual === 'object' && Object.keys(actual).length === 0);
      return rule.op === 'is_empty' ? empty : !empty;
    }
    default: {
      const order = compare(actual, expected);
      if (order === undefined) return false;
      switch (rule.op) {
        case '>': return order > 0;
        case '>=': return order >= 0;
        case '<': return order < 0;
        case '<=': return order <= 0;
        default: return false;
      }
    }
  }
}
