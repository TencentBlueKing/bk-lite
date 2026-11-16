import { expect, it } from 'vitest';
import { samplePaths, sampleAt, listPath, compatiblePaths } from './field-fetch-mapping';
it('从嵌套 API 样本发现列表、行字段及类型，保留根列表路径', () => {
  const data = { data: { items: [{ id: 7, name: '设备', nested: { price: 12 } }] } };
  expect(listPath(data)).toBe('data.items');
  expect(listPath([{ id: 1 }])).toBe('');
  expect(sampleAt(data, 'data.items.0.name')).toBe('设备');
  expect(compatiblePaths(samplePaths(sampleAt(data, 'data.items.0')), 'number').map(p => p.value)).toEqual(['id', 'nested.price']);
  expect(compatiblePaths(samplePaths(data), 'string').map(p => p.value)).toEqual(['data.items.0.name']);
});
it('空列表及多个非标准数组不猜测映射', () => {
  expect(samplePaths([])).toEqual([{ value: '', label: '整个返回值 · array', type: 'array' }]);
  expect(listPath({ first: [], second: [] })).toBeUndefined();
});
