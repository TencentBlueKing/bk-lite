import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const saveFilters = vi.hoisted(() => vi.fn());

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/cmdb/api', () => ({
  useModelApi: () => ({
    getModelAssociations: async () => [],
    getModelAttrList: async () => [],
  }),
}));
vi.mock('@/app/cmdb/api/userConfig', () => ({ useSavedFiltersApi: () => ({ saveFilters }) }));
vi.mock('@/app/cmdb/store', () => ({
  useAssetDataStore: (selector: (state: { query_list: never[]; user_configs: object; updateUserConfig: () => void }) => unknown) =>
    selector({ query_list: [], user_configs: {}, updateUserConfig: vi.fn() }),
}));

import AdvancedFilterDrawer from '../advancedFilterDrawer';

const attrList = [{
  attr_id: 'version',
  attr_name: '版本',
  attr_type: 'str',
  is_required: false,
  editable: true,
  option: [],
}];

describe('高级筛选抽屉', () => {
  beforeEach(() => saveFilters.mockReset());

  it('新增条件默认查当前模型，关闭不应用，重置只清草稿', async () => {
    const onApply = vi.fn();
    const onClose = vi.fn();
    render(
      <AdvancedFilterDrawer
        open
        modelId="mysql"
        applied={{ logic: 'OR', conditions: [{ path: [], field: 'version', type: 'str*', value: '8.0' }] }}
        attrList={attrList}
        userList={[]}
        assoTypes={[]}
        models={[]}
        onClose={onClose}
        onApply={onApply}
      />,
    );

    expect(screen.getByText('AdvancedFilter.condition'.replace('{n}', '1') || '条件 1')).toBeTruthy();
    fireEvent.click(screen.getByText('AdvancedFilter.reset'));
    expect(screen.queryByText('AdvancedFilter.condition'.replace('{n}', '1'))).toBeNull();

    fireEvent.click(screen.getByText(/\+ AdvancedFilter.addCondition/));
    expect(screen.getByText('AdvancedFilter.condition'.replace('{n}', '1'))).toBeTruthy();
    expect(screen.getAllByText('AdvancedFilter.currentModel').length).toBeGreaterThan(1);

    fireEvent.click(screen.getByLabelText('Close'));
    expect(onClose).toHaveBeenCalled();
    expect(onApply).not.toHaveBeenCalled();
    await act(async () => {
      await Promise.resolve();
    });
  });
});
