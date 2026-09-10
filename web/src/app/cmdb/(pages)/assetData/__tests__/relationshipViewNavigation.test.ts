import { describe, expect, it } from 'vitest';

import {
  buildRelationshipTabHref,
  DEFAULT_RELATIONSHIP_TAB,
  isRelationshipMenuActive,
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
    const shortcuts = ['network', 'appOverview', 'rackView', 'roomView'];

    expect(isRelationshipMenuActive(true, 'network', shortcuts)).toBe(false);
    expect(isRelationshipMenuActive(true, 'list', shortcuts)).toBe(true);
    expect(isRelationshipMenuActive(true, 'topo', shortcuts)).toBe(true);
    expect(isRelationshipMenuActive(false, 'list', shortcuts)).toBe(false);
  });
});
