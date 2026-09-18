import { describe, expect, it } from 'vitest';

import {
  buildRelationshipTabHref,
  DEFAULT_RELATIONSHIP_TAB,
  isAllowedRelationshipTab,
  isRelationshipMenuActive,
  normalizeRelationshipTab,
  relationshipGatesSettled,
} from '../relationshipViewNavigation';

describe('relationship view navigation', () => {
  it('切换视图时保留实例参数并同步 tab', () => {
    const params = new URLSearchParams(
      'model_id=switch&inst_uuid=uuid-1&tab=network'
    );

    expect(
      buildRelationshipTabHref(
        '/cmdb/assetData/detail/relationships',
        params,
        DEFAULT_RELATIONSHIP_TAB
      )
    ).toBe(
      '/cmdb/assetData/detail/relationships?model_id=switch&inst_uuid=uuid-1&tab=list'
    );
  });

  it('快捷视图与关联关系父菜单保持互斥选中', () => {
    const shortcuts = [
      'network',
      'appOverview',
      'rackView',
      'roomView',
    ];

    expect(isRelationshipMenuActive(true, 'network', shortcuts)).toBe(false);
    expect(isRelationshipMenuActive(true, 'roomView', shortcuts)).toBe(false);
    expect(isRelationshipMenuActive(true, 'list', shortcuts)).toBe(true);
    expect(isRelationshipMenuActive(true, 'topo', shortcuts)).toBe(true);
    expect(isRelationshipMenuActive(false, 'list', shortcuts)).toBe(false);
  });
});

describe('relationship tab gate', () => {
  const alwaysAllowed = ['list', 'topo'] as const;

  it('does not rewrite or treat gates as settled while themes or widget are loading', () => {
    expect(
      relationshipGatesSettled({
        themesReady: false,
        widgetStatus: 'ready',
      }),
    ).toBe(false);
    expect(
      relationshipGatesSettled({
        themesReady: true,
        widgetStatus: 'loading',
      }),
    ).toBe(false);
    expect(
      relationshipGatesSettled({
        themesReady: true,
        widgetStatus: 'ready',
      }),
    ).toBe(true);
    expect(
      relationshipGatesSettled({
        themesReady: true,
        widgetStatus: 'unavailable',
      }),
    ).toBe(true);

    expect(
      normalizeRelationshipTab({
        requestedTab: 'network',
        allowedTabs: alwaysAllowed,
        gatesSettled: false,
      }),
    ).toEqual({
      tab: 'network',
      shouldRewrite: false,
    });
    expect(isAllowedRelationshipTab('network', alwaysAllowed)).toBe(false);
  });

  it('rewrites an illegal network tab to list after gates settle', () => {
    expect(
      normalizeRelationshipTab({
        requestedTab: 'network',
        allowedTabs: alwaysAllowed,
        gatesSettled: true,
      }),
    ).toEqual({
      tab: DEFAULT_RELATIONSHIP_TAB,
      shouldRewrite: true,
    });
    expect(
      normalizeRelationshipTab({
        requestedTab: 'ipam',
        allowedTabs: alwaysAllowed,
        gatesSettled: true,
      }),
    ).toEqual({
      tab: 'list',
      shouldRewrite: true,
    });
  });

  it('keeps a legal network tab and does not rewrite', () => {
    const allowed = ['list', 'topo', 'network'];
    expect(
      normalizeRelationshipTab({
        requestedTab: 'network',
        allowedTabs: allowed,
        gatesSettled: true,
      }),
    ).toEqual({
      tab: 'network',
      shouldRewrite: false,
    });
    expect(isAllowedRelationshipTab('network', allowed)).toBe(true);
  });
});
