import { describe, expect, it } from 'vitest';

import {
  findMatchedMenuPath,
  getFirstLayerSiblingMenuItems,
  isMenuPathMatch,
} from '../menuHelpers';
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
  {
    title: '探索',
    url: '/apm/traces',
    name: 'traces',
    icon: 'search-f',
    children: [
      { title: '调用链', url: '/apm/traces', name: 'traces', icon: 'search-f' },
      { title: '端点', url: '/apm/endpoints', name: 'endpoints', icon: 'rizhi' },
      { title: '错误', url: '/apm/errors', name: 'errors', icon: 'weiwangguanicon-defuben-' },
    ],
  },
  {
    title: '事件',
    url: '/apm/events',
    name: 'Alert',
    icon: 'weiwangguanicon-defuben-',
    children: [
      { title: '告警', url: '/apm/events', name: 'Alert', icon: 'weiwangguanicon-defuben-' },
      { title: '策略', url: '/apm/policies', name: 'policies', icon: 'shezhi' },
    ],
  },
  {
    title: '集成',
    url: '/apm/integration/add',
    name: 'Integration',
    icon: 'zichan-quanbushebei',
    children: [
      { title: '添加接入', url: '/apm/integration/add', name: 'integration_add', icon: 'settings-fill' },
      { title: '应用管理', url: '/apm/integration/applications', name: 'applications', icon: 'mulu' },
      { title: '接入实例', url: '/apm/integration/instances', name: 'integration_instances', icon: 'caijiqi' },
      { url: '/apm/integration', name: 'integration_add', isNotMenuItem: true },
    ],
  },
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

  it('prefers integration over app-root /apm for integration pages', () => {
    const matched = findMatchedMenuPath(apmMenus, '/apm/integration/add');
    expect(matched?.[0]?.title).toBe('集成');
    expect(matched?.[0]?.url).toBe('/apm/integration/add');
  });
});

describe('getFirstLayerSiblingMenuItems', () => {
  it('returns integration secondary items instead of empty after /apm home was added', () => {
    const siblings = getFirstLayerSiblingMenuItems(apmMenus, '/apm/integration/add')
      .filter((item) => !item.isNotMenuItem)
      .map((item) => item.title);
    expect(siblings).toEqual(['添加接入', '应用管理', '接入实例']);
  });

  it('returns services secondary items for topology paths', () => {
    const siblings = getFirstLayerSiblingMenuItems(apmMenus, '/apm/topology')
      .filter((item) => !item.isNotMenuItem)
      .map((item) => item.title);
    expect(siblings).toEqual(['服务', '服务拓扑', 'SLO']);
  });

  it('returns explore secondary items for endpoints', () => {
    const siblings = getFirstLayerSiblingMenuItems(apmMenus, '/apm/endpoints')
      .filter((item) => !item.isNotMenuItem)
      .map((item) => item.title);
    expect(siblings).toEqual(['调用链', '端点', '错误']);
  });
});
