import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import menu from '@/app/rum/constants/menu.json';
import rumEn from '@/app/rum/locales/en.json';
import rumZh from '@/app/rum/locales/zh.json';
import { flattenMessages } from '@/app/apm/__tests__/intl';
import { findMatchedMenuPath } from '@/utils/menuHelpers';
import type { MenuItem } from '@/types/index';

const rumRoot = join(process.cwd(), 'src/app/rum');

const visibleTitles = (items?: { title?: string; isNotMenuItem?: boolean }[]) =>
  (items || []).flatMap((item) => (item.title && !item.isNotMenuItem ? [item.title] : []));

const asMenus = (locale: 'zh' | 'en'): MenuItem[] => menu[locale] as MenuItem[];

const menuIdentity = (items: MenuItem[]): unknown =>
  items.map((item) => ({
    url: item.url,
    name: item.name,
    hidden: Boolean(item.isNotMenuItem),
    children: item.children ? menuIdentity(item.children) : undefined,
  }));

describe('RUM 顶栏信息架构', () => {
  it.each(['zh', 'en'] as const)('%s 一级顺序为体验 · 质量 · 事件 · 集成 · 数据治理', (locale) => {
    const expected = locale === 'zh'
      ? ['体验', '质量', '事件', '集成', '数据治理']
      : ['Experience', 'Quality', 'Events', 'Integration', 'Governance'];
    expect(menu[locale].map((item) => item.title)).toEqual(expected);
  });

  it('体验默认会话，不含应用', () => {
    const experience = menu.zh.find((item) => item.title === '体验');
    expect(experience?.url).toBe('/rum/sessions');
    expect(experience?.name).toBe('sessions');
    expect(visibleTitles(experience?.children)).toEqual(['会话', '视图与性能', '转化漏斗']);
    expect(experience?.children?.some((item) => item.url === '/rum/applications')).toBe(false);
  });

  it('质量、事件、数据治理默认落到对应列表', () => {
    expect(menu.zh.find((item) => item.title === '质量')?.url).toBe('/rum/errors');
    expect(menu.zh.find((item) => item.title === '事件')?.url).toBe('/rum/alert-events');
    expect(visibleTitles(menu.zh.find((item) => item.title === '事件')?.children)).toEqual([
      '告警',
      '策略',
    ]);
    expect(menu.zh.find((item) => item.title === '数据治理')?.url).toBe('/rum/compliance');
  });

  it('中英菜单共用同一套 url 与权限 name', () => {
    expect(menuIdentity(asMenus('zh'))).toEqual(menuIdentity(asMenus('en')));
  });

  it('中英 RUM 文案 key 对齐', () => {
    expect(Object.keys(flattenMessages(rumZh)).sort()).toEqual(
      Object.keys(flattenMessages(rumEn)).sort(),
    );
  });

  it('集成是应用与接入，不含添加接入或接入实例', () => {
    const integration = menu.zh.find((item) => item.title === '集成');
    expect(integration?.url).toBe('/rum/applications');
    expect(integration?.name).toBe('applications');
    expect(visibleTitles(integration?.children)).toEqual(['应用', '接入']);
    expect(integration?.children?.some((item) => item.url === '/rum/setup' && !item.isNotMenuItem)).toBe(true);
    expect(integration?.children?.some((item) => item.url === '/rum/setup/[name]' && item.isNotMenuItem)).toBe(true);
    expect(
      integration?.children?.some((item) => item.url === '/rum/applications/[name]/overview' && item.isNotMenuItem),
    ).toBe(true);
    expect(menu.zh.some((group) => visibleTitles(group.children).includes('添加接入'))).toBe(false);
    expect(menu.zh.some((group) => visibleTitles(group.children).includes('接入实例'))).toBe(false);
  });

  it('应用详情高亮应用，接入详情高亮接入', () => {
    expect(findMatchedMenuPath(asMenus('zh'), '/rum/applications/store/overview')?.[0].title).toBe('集成');
    expect(findMatchedMenuPath(asMenus('zh'), '/rum/applications/store/overview')?.[1].title).toBe('应用');
    expect(findMatchedMenuPath(asMenus('zh'), '/rum/setup/store')?.[0].title).toBe('集成');
    expect(findMatchedMenuPath(asMenus('zh'), '/rum/setup/store')?.[1].title).toBe('接入');
    expect(findMatchedMenuPath(asMenus('zh'), '/rum/sessions/abc')?.[0].title).toBe('体验');
  });

  it('RUM 根路径仍落到应用列表', () => {
    expect(readFileSync(join(rumRoot, 'page.tsx'), 'utf8')).toMatch(/redirect\('\/rum\/applications'\)/);
  });
});
