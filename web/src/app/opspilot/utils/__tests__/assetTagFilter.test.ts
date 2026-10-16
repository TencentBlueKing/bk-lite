import { describe, expect, it } from 'vitest';
import {
  clearAssetFilter,
  collectTagChips,
  filterTaggedAssets,
  normalizeUserTags,
} from '../assetTagFilter';

const labelFor = (value: string, kind: 'system' | 'user') => {
  if (kind === 'system' && value === 'container') return '容器';
  if (kind === 'user' && value === 'search') return '搜索';
  return value;
};

const items = [
  { id: 1, name: 'MySQL', description: '数据库', systemTags: ['database'], userTags: [] as string[] },
  { id: 2, name: 'CMDB', description: '资产', systemTags: ['asset', 'platform_app'], userTags: ['机房'] },
  { id: 3, name: 'Clock', description: '时间', systemTags: [] as string[], userTags: [] as string[] },
  { id: 4, name: 'Kubernetes', description: '容器编排', systemTags: ['container'], userTags: ['容器'] },
];

const chips = collectTagChips(items, labelFor);

describe('asset tag filter', () => {
  it('shows everything when no tag is lit, including untagged items', () => {
    const visible = filterTaggedAssets(items, {
      selectedTags: [],
      keyword: '',
      chips,
      systemTags: (item) => item.systemTags,
      userTags: (item) => item.userTags,
      name: (item) => item.name,
      description: (item) => item.description,
    });
    expect(visible.map((item) => item.id)).toEqual([1, 2, 3, 4]);
  });

  it('keeps an item when it matches any lit tag, and hides untagged items', () => {
    const visible = filterTaggedAssets(items, {
      selectedTags: ['database', 'asset'],
      keyword: '',
      chips,
      systemTags: (item) => item.systemTags,
      userTags: (item) => item.userTags,
      name: (item) => item.name,
      description: (item) => item.description,
    });
    expect(visible.map((item) => item.id)).toEqual([1, 2]);
  });

  it('narrows the tag result by name or description', () => {
    const visible = filterTaggedAssets(items, {
      selectedTags: ['database', 'asset'],
      keyword: '资产',
      chips,
      systemTags: (item) => item.systemTags,
      userTags: (item) => item.userTags,
      name: (item) => item.name,
      description: (item) => item.description,
    });
    expect(visible.map((item) => item.id)).toEqual([2]);
  });

  it('treats a user tag that repeats a system label as the same chip', () => {
    const container = chips.find((chip) => chip.value === 'container');
    expect(container?.label).toBe('容器');
    expect(chips.filter((chip) => chip.label === '容器')).toHaveLength(1);
    const visible = filterTaggedAssets(items, {
      selectedTags: ['container'],
      keyword: '',
      chips,
      systemTags: (item) => item.systemTags,
      userTags: (item) => item.userTags,
      name: (item) => item.name,
      description: (item) => item.description,
    });
    expect(visible.map((item) => item.id)).toEqual([4]);
  });

  it('clears filter conditions when the asset type changes and keeps the selection', () => {
    const selectedIds = [2, 3];
    const next = clearAssetFilter({ selectedTags: ['asset'], keyword: 'cmdb' });
    expect(next).toEqual({ selectedTags: [], keyword: '' });
    expect(selectedIds).toEqual([2, 3]);
  });

  it('trims, drops blanks, and dedupes user tags', () => {
    expect(normalizeUserTags(['  值班  ', '值班', '', '  '])).toEqual(['值班']);
  });
});
