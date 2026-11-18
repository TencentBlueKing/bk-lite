import { expect, it } from 'vitest';
import menu from '../menu.json';
import type { MenuItem } from '@/types';
import { findMatchedMenuPath, getDeepestMatchedMenuItems, shouldRenderSecondLayerMenu } from '@/utils/menuHelpers';

interface MenuConfig { name: string; title: string; url: string; icon?: string; children?: MenuConfig[] }
const hydrate = (items: MenuConfig[]): MenuItem[] => items.map((item) => ({
  icon: '', operation: [], ...item, children: item.children ? hydrate(item.children) : undefined,
}));
const locales: Array<'zh' | 'en'> = ['zh', 'en'];

it.each(locales)('%s keeps page switching local while preserving template permissions and detail navigation', (locale) => {
  const menus = hydrate(menu[locale]);
  expect(menus.slice(0, 2).map((item) => item.name)).toEqual(['skill_list', 'bot_list']);
  for (const path of ['/opspilot/skill', '/opspilot/skill/templates']) {
    expect(shouldRenderSecondLayerMenu(path, menus)).toBe(false);
  }
  const matched = findMatchedMenuPath(menus, '/opspilot/skill/templates');
  expect(matched?.at(-1)?.name).toBe('skill_templates');
  expect(matched?.at(-1)?.withParentPermission).toBe(true);
  expect(matched?.at(-1)?.isNotMenuItem).toBe(true);
  expect(matched?.[0]?.name).toBe('skill_list');
  expect(getDeepestMatchedMenuItems(menus, '/opspilot/skill/detail/settings').map((item) => item.name)).toEqual([
    'skill_setting', 'skill_channel', 'skill_history',
  ]);
});
