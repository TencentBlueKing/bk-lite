import { describe, expect, it } from 'vitest';
import en from '@/app/log/locales/en.json';
import zh from '@/app/log/locales/zh.json';
import menu from '@/app/log/constants/menu.json';
import { buildPassiveIntegrationDetailMenu } from '../../list/detail/integrationDetailMenu';
import { buildSourceDeviceSearchUrl } from '../sourceDeviceSearch';

const titles = {
  configurationTitle: '配置',
  extractorTitle: '提取器',
  introductionTitle: '简介'
};

interface MenuNode {
  title?: string;
  url?: string;
  name?: string;
  isNotMenuItem?: boolean;
  children?: unknown[];
}

function menuRoutes(nodes: MenuNode[], url: string) {
  const matches: MenuNode[] = [];
  const visit = (items: MenuNode[]) => {
    for (const item of items) {
      if (item.url === url) matches.push(item);
      if (Array.isArray(item.children)) visit(item.children as MenuNode[]);
    }
  };
  visit(nodes);
  return matches;
}

describe('source device navigation', () => {
  it('keeps passive detail menus on configuration, extractors, and introduction', () => {
    expect(buildPassiveIntegrationDetailMenu(titles).map((item) => item.url)).toEqual([
      '/log/integration/list/detail/configure',
      '/log/integration/list/detail/extractor',
      '/log/integration/list/detail/output'
    ]);
  });

  it('lists source devices as an integration page right after log receive', () => {
    for (const [tree, title] of [
      [menu.zh, '来源设备'],
      [menu.en, 'Source devices']
    ] as const) {
      const integration = (tree as MenuNode[]).find((item) => item.url === '/log/integration');
      const siblings = (integration?.children || []) as MenuNode[];
      const index = siblings.findIndex((item) => item.url === '/log/integration/source-device');
      expect(siblings[index - 1]?.url).toBe('/log/integration/receive');
      expect(siblings[index]).toMatchObject({ name: 'source_device', title });
      expect(siblings[index].isNotMenuItem).toBeUndefined();

      const legacy = menuRoutes(tree as MenuNode[], '/log/integration/list/detail/source-device');
      expect(legacy).toHaveLength(1);
      expect(legacy[0].isNotMenuItem).toBe(true);
    }
    expect(zh.log.sourceDevice.receiveType).toBe('接收类型');
    expect(en.log.sourceDevice.receiveType).toBe('Receive type');
    expect(zh.log.sourceDevice.syslog).toBe('系统日志');
    expect(en.log.sourceDevice.syslog).toBe('Syslog');
    expect(zh.log.sourceDevice.searchPlaceholder).toBe('搜索源 IP 或主机名');
    expect(en.log.sourceDevice.searchPlaceholder).toBe('Search source IP or hostname');
    expect(zh.log.sourceDevice.hostname).toBe('主机名');
    expect(en.log.sourceDevice.silent).toBe('Silent');
  });

  it('opens search with the api query and millisecond window, including an empty hostname', () => {
    const url = buildSourceDeviceSearchUrl({
      search_query:
        'collect_type:"syslog" AND cloud_region_id:"1" AND source_ip:"10.0.0.8" AND hostname:""',
      search_start: 1764000000000,
      search_end: 1764003600000
    });
    const params = new URLSearchParams(url.slice('/log/search?'.length));
    expect(params.get('query')).toBe(
      'collect_type:"syslog" AND cloud_region_id:"1" AND source_ip:"10.0.0.8" AND hostname:""'
    );
    expect(params.get('startTime')).toBe('1764000000000');
    expect(params.get('endTime')).toBe('1764003600000');
  });
});
