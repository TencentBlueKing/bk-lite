import { describe, expect, it } from 'vitest';

import {
  findMatchedMenuPath,
  getDeepestMatchedMenuItems,
  getFirstLayerSiblingMenuItems,
  isMenuPathMatch,
} from '../menuHelpers';
import type { MenuItem } from '@/types/index';

const menu = (item: Partial<MenuItem> & Pick<MenuItem, 'name' | 'url'>): MenuItem => ({
  title: '',
  icon: '',
  operation: [],
  ...item,
});

/** Target APM directoryized menu tree. */
const apmMenus: MenuItem[] = [
  menu({ title: '首页', url: '/apm/home', name: 'home', icon: 'shouye' }),
  menu({
    title: '服务',
    url: '/apm/services',
    name: 'services',
    icon: 'daohang-yunyingfenxishi',
    children: [
      menu({ title: '服务', url: '/apm/services', name: 'services', icon: 'daohang-yunyingfenxishi' }),
      menu({ title: '服务拓扑', url: '/apm/services/topology', name: 'services', icon: 'guanlian' }),
      menu({ title: 'SLO', url: '/apm/services/slo', name: 'services', icon: 'mulu' }),
    ],
  }),
  menu({
    title: '探索',
    url: '/apm/explore/traces',
    name: 'traces',
    icon: 'search-f',
    children: [
      menu({ title: '调用链', url: '/apm/explore/traces', name: 'traces', icon: 'search-f' }),
      menu({ title: '端点', url: '/apm/explore/endpoints', name: 'endpoints', icon: 'rizhi' }),
      menu({ title: '错误', url: '/apm/explore/errors', name: 'errors', icon: 'weiwangguanicon-defuben-' }),
    ],
  }),
  menu({
    title: '事件',
    url: '/apm/events/alerts',
    name: 'Alert',
    icon: 'weiwangguanicon-defuben-',
    children: [
      menu({ title: '告警', url: '/apm/events/alerts', name: 'events', icon: 'weiwangguanicon-defuben-' }),
      menu({ title: '策略', url: '/apm/events/policies', name: 'policies', icon: 'shezhi' }),
    ],
  }),
  menu({
    title: '集成',
    url: '/apm/integration/add',
    name: 'Integration',
    icon: 'zichan-quanbushebei',
    children: [
      menu({ title: '添加接入', url: '/apm/integration/add', name: 'integration_add', icon: 'settings-fill' }),
      menu({ title: '接入实例', url: '/apm/integration/instances', name: 'integration_instances', icon: 'caijiqi' }),
      menu({ title: '应用管理', url: '/apm/integration/applications', name: 'applications', icon: 'mulu' }),
      menu({ url: '/apm/integration', name: 'integration_add', isNotMenuItem: true }),
    ],
  }),
];

const jobExecutionMenus: MenuItem[] = [
  menu({
    title: '作业执行',
    url: '/job/execution',
    name: 'execution',
    children: [
      menu({ title: '快速执行', url: '/job/execution/quick-exec', name: 'quick_exec' }),
      menu({ title: '文件分发', url: '/job/execution/file-dist', name: 'file_dist' }),
      menu({ title: '定时任务', url: '/job/execution/cron-task', name: 'cron_task' }),
      menu({ title: '作业记录', url: '/job/execution/job-record', name: 'job_record' }),
    ],
  }),
];

const cmdbAutoDiscoveryMenus: MenuItem[] = [
  menu({
    title: '管理',
    url: '/cmdb/assetManage',
    name: 'manage',
    children: [
      menu({
        title: '自动发现',
        url: '/cmdb/assetManage/autoDiscovery',
        name: 'autoDiscovery',
        children: [
          menu({ title: '采集', url: '/cmdb/assetManage/autoDiscovery/collection', name: 'collection' }),
          menu({ title: 'SOID特征库', url: '/cmdb/assetManage/autoDiscovery/featureLibrary/soid', name: 'soid' }),
          menu({ title: '采集工具', url: '/cmdb/assetManage/autoDiscovery/featureLibrary/collectionTool', name: 'tool' }),
        ],
      }),
    ],
  }),
];

describe('isMenuPathMatch', () => {
  it('matches exact and descendant paths on segment boundary', () => {
    expect(isMenuPathMatch('/apm/home', '/apm/home')).toBe(true);
    expect(isMenuPathMatch('/apm/services', '/apm/services')).toBe(true);
    expect(isMenuPathMatch('/apm/services', '/apm/services/topology')).toBe(true);
    expect(isMenuPathMatch('/apm/home', '/apm/services')).toBe(false);
  });

  it('does not match unrelated siblings by raw string prefix alone', () => {
    expect(isMenuPathMatch('/apm/services', '/apm/home')).toBe(false);
    expect(isMenuPathMatch('/apm/service', '/apm/services')).toBe(false);
  });
});

describe('findMatchedMenuPath', () => {
  it('prefers /apm/services over /apm/home for service pages', () => {
    const matched = findMatchedMenuPath(apmMenus, '/apm/services');
    expect(matched?.[0]?.title).toBe('服务');
    expect(matched?.[0]?.url).toBe('/apm/services');
  });

  it('keeps home active on /apm/home', () => {
    const matched = findMatchedMenuPath(apmMenus, '/apm/home');
    expect(matched?.[0]?.title).toBe('首页');
    expect(matched?.[0]?.url).toBe('/apm/home');
  });

  it('matches service detail under services top-level item', () => {
    const matched = findMatchedMenuPath(apmMenus, '/apm/services/svc-1');
    expect(matched?.[0]?.url).toBe('/apm/services');
  });

  it('matches nested topology under services', () => {
    const matched = findMatchedMenuPath(apmMenus, '/apm/services/topology');
    expect(matched?.[0]?.url).toBe('/apm/services');
    expect(matched?.some((item) => item.url === '/apm/services/topology')).toBe(true);
  });

  it('matches explore endpoints under explore first-layer', () => {
    const matched = findMatchedMenuPath(apmMenus, '/apm/explore/endpoints');
    expect(matched?.[0]?.url).toBe('/apm/explore/traces');
    expect(matched?.some((item) => item.url === '/apm/explore/endpoints')).toBe(true);
  });

  it('prefers integration over home for integration pages', () => {
    const matched = findMatchedMenuPath(apmMenus, '/apm/integration/add');
    expect(matched?.[0]?.title).toBe('集成');
    expect(matched?.[0]?.url).toBe('/apm/integration/add');
  });
});

describe('getFirstLayerSiblingMenuItems', () => {
  it('returns integration secondary items', () => {
    const siblings = getFirstLayerSiblingMenuItems(apmMenus, '/apm/integration/add')
      .filter((item) => !item.isNotMenuItem)
      .map((item) => item.title);
    expect(siblings).toEqual(['添加接入', '接入实例', '应用管理']);
  });

  it('returns services secondary items for nested topology', () => {
    const siblings = getFirstLayerSiblingMenuItems(apmMenus, '/apm/services/topology')
      .filter((item) => !item.isNotMenuItem)
      .map((item) => item.title);
    expect(siblings).toEqual(['服务', '服务拓扑', 'SLO']);
  });

  it('returns explore secondary items for endpoints', () => {
    const siblings = getFirstLayerSiblingMenuItems(apmMenus, '/apm/explore/endpoints')
      .filter((item) => !item.isNotMenuItem)
      .map((item) => item.title);
    expect(siblings).toEqual(['调用链', '端点', '错误']);
  });

  it('returns event secondary items for policies', () => {
    const siblings = getFirstLayerSiblingMenuItems(apmMenus, '/apm/events/policies')
      .filter((item) => !item.isNotMenuItem)
      .map((item) => item.title);
    expect(siblings).toEqual(['告警', '策略']);
  });
});

describe('getDeepestMatchedMenuItems', () => {
  it('falls back to siblings when the deepest match is a leaf (job)', () => {
    const items = getDeepestMatchedMenuItems(jobExecutionMenus, '/job/execution/quick-exec')
      .map((item) => item.title);
    expect(items).toEqual(['快速执行', '文件分发', '定时任务', '作业记录']);
  });

  it('falls back to siblings when the deepest match is a leaf (cmdb auto-discovery)', () => {
    const items = getDeepestMatchedMenuItems(
      cmdbAutoDiscoveryMenus,
      '/cmdb/assetManage/autoDiscovery/collection',
    ).map((item) => item.title);
    expect(items).toEqual(['采集', 'SOID特征库', '采集工具']);
  });

  it('returns children when the deepest match still has children', () => {
    const items = getDeepestMatchedMenuItems(apmMenus, '/apm/services')
      .filter((item) => !item.isNotMenuItem)
      .map((item) => item.title);
    expect(items).toEqual(['服务', '服务拓扑', 'SLO']);
  });
});

const skillMenus: MenuItem[] = [
  menu({
    title: '智能体',
    url: '/opspilot/skill',
    name: 'skill_list',
    hasDetail: true,
    children: [
      menu({
        title: '设置',
        url: '/opspilot/skill/detail/settings',
        icon: 'shezhi',
        name: 'skill_setting',
      }),
      menu({
        title: '调用日志',
        url: '/opspilot/skill/detail/invocationLogs',
        icon: 'talk-line',
        name: 'skill_invocation_logs',
      }),
      menu({
        title: '对话',
        url: '/opspilot/skill/chat',
        name: 'skill_chat',
        isNotMenuItem: true,
      }),
    ],
  }),
];

describe('getDeepestMatchedMenuItems', () => {
  it('falls back to parent siblings when current page is a leaf (opspilot skill)', () => {
    const items = getDeepestMatchedMenuItems(
      skillMenus,
      '/opspilot/skill/detail/settings'
    ).map((item) => item.title);
    expect(items).toEqual(['设置', '调用日志']);
  });

  it('still prefers deeper APM routes over app-root /apm when resolving secondary items', () => {
    const items = getDeepestMatchedMenuItems(apmMenus, '/apm/integration/add').map(
      (item) => item.title
    );
    expect(items).toEqual(['添加接入', '接入实例', '应用管理']);
  });

  it('returns empty on app-root leaf without siblings (APM home)', () => {
    expect(getDeepestMatchedMenuItems(apmMenus, '/apm')).toEqual([]);
  });
});
