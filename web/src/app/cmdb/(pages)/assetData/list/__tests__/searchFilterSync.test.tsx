import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';
import type { AttrFieldType } from '@/app/cmdb/types/assetManage';
import SearchFilter from '../searchFilter';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/app/cmdb/api/userConfig', () => ({
  useSavedFiltersApi: () => ({ saveFilters: vi.fn() }),
}));

const hostAttrs = [
  { attr_id: 'ip_addr', attr_name: '内网IP', attr_type: 'str' },
  { attr_id: 'hostname', attr_name: '主机名称', attr_type: 'str' },
] as AttrFieldType[];

const appAttrs = [
  { attr_id: 'inst_name', attr_name: '应用系统', attr_type: 'str' },
] as AttrFieldType[];

function FilterPair() {
  return (
    <>
      <SearchFilter
        attrList={hostAttrs}
        displayFieldKeys={['ip_addr', 'hostname']}
        proxyOptions={[]}
        userList={[]}
        onSearch={vi.fn()}
      />
      <SearchFilter
        attrList={appAttrs}
        proxyOptions={[]}
        userList={[]}
        syncSearchAttr={false}
        onSearch={vi.fn()}
      />
    </>
  );
}

describe('搜索字段和列表缓存', () => {
  beforeEach(() => {
    useAssetDataStore.setState({
      searchAttr: 'inst_name',
      case_sensitive: false,
      user_configs: {},
    });
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: () => ({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    });
  });

  it('列表把不可见的 inst_name 改成自己的第一个字段，弹窗不写回去', async () => {
    render(<FilterPair />);
    await screen.findByText('内网IP');
    await screen.findByText('应用系统');
    expect(useAssetDataStore.getState().searchAttr).toBe('ip_addr');
  }, 20000);
});
