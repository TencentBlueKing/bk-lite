import { describe, expect, it } from 'vitest';
import en from '@/app/log/locales/en.json';
import zh from '@/app/log/locales/zh.json';
import menu from '@/app/log/constants/menu.json';
import { buildPassiveIntegrationDetailMenu } from '../integrationDetailMenu';
import { buildSourceDeviceSearchUrl } from '../source-device/sourceDeviceSearch';

const titles = {
  configurationTitle: '配置',
  extractorTitle: '提取器',
  introductionTitle: '简介'
};

function menuRoutes(nodes: Array<{ url?: string; isNotMenuItem?: boolean; children?: unknown[] }>, url: string) {
  const matches = [];
  const visit = (items: typeof nodes) => {
    for (const item of items) {
      if (item.url === url) matches.push(item);
      if (Array.isArray(item.children)) visit(item.children as typeof nodes);
    }
  };
  visit(nodes);
  return matches;
}

describe('syslog source device navigation', () => {
  it('keeps passive detail menus on configuration, extractors, and introduction', () => {
    expect(buildPassiveIntegrationDetailMenu(titles).map((item) => item.url)).toEqual([
      '/log/integration/list/detail/configure',
      '/log/integration/list/detail/extractor',
      '/log/integration/list/detail/output'
    ]);
  });

  it('registers the hidden route and copy in both languages', () => {
    for (const tree of [menu.zh, menu.en]) {
      const matches = menuRoutes(tree, '/log/integration/list/detail/source-device');
      expect(matches).toHaveLength(1);
      expect(matches[0].isNotMenuItem).toBe(true);
      expect(matches[0].name).toBe('integration_source_device');
    }
    expect(zh.log.sourceDevice.menuTitle).toBe('来源设备');
    expect(en.log.sourceDevice.menuTitle).toBe('Source devices');
    expect(zh.log.sourceDevice.treeNode).toBe('{name}来源');
    expect(en.log.sourceDevice.treeNode).toBe('{name} sources');
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
