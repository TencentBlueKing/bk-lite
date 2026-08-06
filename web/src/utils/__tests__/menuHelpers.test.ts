import { describe, expect, it } from 'vitest';

import { findMatchedMenuPath, isMenuPathMatch } from '../menuHelpers';
import type { MenuItem } from '@/types/index';

const apmMenus: MenuItem[] = [
  { title: '首页', url: '/apm', name: 'home', icon: 'shouye' },
  {
    title: '服务',
    url: '/apm/services',
    name: 'services',
    icon: 'daohang-yunyingfenxishi',
    children: [
      { title: '服务', url: '/apm/services', name: 'services', icon: 'daohang-yunyingfenxishi' },
      { title: '服务拓扑', url: '/apm/topology', name: 'services', icon: 'guanlian' },
      { title: 'SLO', url: '/apm/slo', name: 'services', icon: 'mulu' },
    ],
  },
  { title: '探索', url: '/apm/traces', name: 'traces', icon: 'search-f' },
  { title: '事件', url: '/apm/events', name: 'Alert', icon: 'weiwangguanicon-defuben-' },
  { title: '集成', url: '/apm/integration/add', name: 'Integration', icon: 'zichan-quanbushebei' },
];

describe('isMenuPathMatch', () => {
  it('matches exact and descendant paths on segment boundary', () => {
    expect(isMenuPathMatch('/apm', '/apm')).toBe(true);
    expect(isMenuPathMatch('/apm', '/apm/services')).toBe(true);
    expect(isMenuPathMatch('/apm/services', '/apm/services')).toBe(true);
    expect(isMenuPathMatch('/apm/services', '/apm/services/abc')).toBe(true);
  });

  it('does not match unrelated siblings by raw string prefix alone', () => {
    expect(isMenuPathMatch('/apm/services', '/apm')).toBe(false);
    expect(isMenuPathMatch('/apm/service', '/apm/services')).toBe(false);
  });
});

describe('findMatchedMenuPath', () => {
  it('prefers /apm/services over app-root /apm for service pages', () => {
    const matched = findMatchedMenuPath(apmMenus, '/apm/services');
    expect(matched?.[0]?.title).toBe('服务');
    expect(matched?.[0]?.url).toBe('/apm/services');
  });

  it('keeps home active on exact /apm', () => {
    const matched = findMatchedMenuPath(apmMenus, '/apm');
    expect(matched?.[0]?.title).toBe('首页');
    expect(matched?.[0]?.url).toBe('/apm');
  });

  it('matches service detail under services top-level item', () => {
    const matched = findMatchedMenuPath(apmMenus, '/apm/services/svc-1');
    expect(matched?.[0]?.url).toBe('/apm/services');
  });

  it('matches topology under services first-layer when path is topology', () => {
    const matched = findMatchedMenuPath(apmMenus, '/apm/topology');
    expect(matched?.[0]?.url).toBe('/apm/services');
    expect(matched?.some((item) => item.url === '/apm/topology')).toBe(true);
  });
});
