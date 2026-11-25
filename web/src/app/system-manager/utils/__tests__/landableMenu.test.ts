import { describe, expect, it } from 'vitest';

import { customMenuLacksLandablePage, hasLandableMenuPage } from '@/app/system-manager/utils/landableMenu';

const directory = {
  title: '目录',
  name: 'folder',
  children: [{ title: '子目录', name: 'nested', children: [] }],
};

describe('hasLandableMenuPage', () => {
  it('rejects an empty list and a tree that only contains directories', () => {
    expect(hasLandableMenuPage([])).toBe(false);
    expect(hasLandableMenuPage([directory])).toBe(false);
    expect(hasLandableMenuPage([{ url: '/system-manager/channel/detail', isNotMenuItem: true }])).toBe(false);
  });

  it('accepts a directory once it contains a real page', () => {
    expect(hasLandableMenuPage([
      { ...directory, children: [{ name: 'search', url: '/cmdb/search' }] },
    ])).toBe(true);
    expect(hasLandableMenuPage([
      { name: 'application_list', url: '/system-manager/application', hasDetail: true, children: [] },
    ])).toBe(true);
  });
});

describe('customMenuLacksLandablePage', () => {
  it('blocks enable for an empty directory tree and still blocks a missing menu list', () => {
    expect(customMenuLacksLandablePage({ menus: [directory], menu_count: 1 })).toBe(true);
    expect(customMenuLacksLandablePage({ menus: [], menu_count: 0 })).toBe(true);
    expect(customMenuLacksLandablePage({ menu_count: 0 })).toBe(true);
    expect(customMenuLacksLandablePage({
      menus: [{ name: 'search', url: '/cmdb/search' }],
      menu_count: 1,
    })).toBe(false);
  });
});
