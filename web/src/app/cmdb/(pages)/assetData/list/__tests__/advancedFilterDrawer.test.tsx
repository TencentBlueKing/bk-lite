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

import AdvancedFilterDrawer, { AdvancedFilterChips } from '../advancedFilterDrawer';

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

  it('标签条件列出 key:value，选中后按这个值应用', async () => {
    const onApply = vi.fn();
    render(
      <AdvancedFilterDrawer
        open
        modelId="host"
        applied={{
          logic: 'AND',
          conditions: [{ path: [], field: 'tag', type: 'list_any[]', value: [] }],
        }}
        attrList={[{
          attr_id: 'tag',
          attr_name: '标签',
          attr_type: 'tag',
          is_required: false,
          editable: true,
          option: {
            mode: 'free',
            options: [
              { key: 'env', value: 'prod' },
              { key: 'env', value: 'test' },
            ],
          },
        }]}
        userList={[]}
        assoTypes={[]}
        models={[]}
        onClose={vi.fn()}
        onApply={onApply}
      />,
    );

    await screen.findByText('标签 属于');
    fireEvent.mouseDown(screen.getAllByRole('combobox').at(-1)!);
    fireEvent.click(await screen.findByText('env:prod', { selector: '.ant-select-item-option-content' }));
    fireEvent.click(screen.getByText('AdvancedFilter.apply'));

    expect(onApply).toHaveBeenCalledWith({
      logic: 'AND',
      conditions: [{ path: [], field: 'tag', type: 'list_any[]', value: ['env:prod'] }],
    });
  });

  it('条件摘要把枚举 id 显示成选项名', async () => {
    render(
      <AdvancedFilterDrawer
        open
        modelId="host"
        applied={{
          logic: 'AND',
          conditions: [{ path: [], field: 'os_type', type: 'list_any[]', value: ['1'] }],
        }}
        attrList={[{
          attr_id: 'os_type',
          attr_name: '操作系统类型',
          attr_type: 'enum',
          is_required: false,
          editable: true,
          option: [{ id: 1, name: 'Linux' }],
        }]}
        userList={[]}
        assoTypes={[]}
        models={[]}
        onClose={vi.fn()}
        onApply={vi.fn()}
      />,
    );

    expect(await screen.findByText('操作系统类型 属于 Linux')).toBeTruthy();
    expect(screen.queryByText('操作系统类型 属于 1')).toBeNull();
  });
});

describe('高级筛选已选条件', () => {
  it('外边标签显示映射名而不是原始值', async () => {
    render(
      <AdvancedFilterChips
        modelId="host"
        filter={{
          logic: 'AND',
          conditions: [
            { path: [], field: 'os_type', type: 'list_any[]', value: ['1'] },
            { path: [], field: 'owner', type: 'list[]', value: ['9'] },
            { path: [], field: 'org', type: 'list[]', value: [2] },
            { path: [], field: 'active', type: 'bool', value: false },
            { path: [], field: 'cloud', type: 'int=', value: 0 },
          ],
        }}
        attrList={[
          { attr_id: 'os_type', attr_name: '操作系统类型', attr_type: 'enum', is_required: false, editable: true, option: [{ id: '1', name: 'Linux' }] },
          { attr_id: 'owner', attr_name: '负责人', attr_type: 'user', is_required: false, editable: true, option: [] },
          { attr_id: 'org', attr_name: '组织', attr_type: 'organization', is_required: false, editable: true, option: [] },
          { attr_id: 'active', attr_name: '启用', attr_type: 'bool', is_required: false, editable: true, option: [] },
          { attr_id: 'cloud', attr_name: '云区域', attr_type: 'int', is_required: false, editable: true, option: [] },
        ]}
        userList={[{ id: '9', username: 'ada', display_name: 'Ada' }]}
        groups={[{ id: '1', name: '总部', subGroups: [{ id: '2', name: '研发' }] }]}
        clouds={[{ proxy_id: '0', proxy_name: 'default' }]}
        assoTypes={[]}
        models={[]}
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByText('操作系统类型 属于 Linux')).toBeTruthy();
    expect(screen.getByText('负责人 属于 Ada(ada)')).toBeTruthy();
    expect(screen.getByText('组织 属于 总部 / 研发')).toBeTruthy();
    expect(screen.getByText('启用 等于 no')).toBeTruthy();
    expect(screen.getByText('云区域 等于 default')).toBeTruthy();
    expect(screen.queryByText(/属于 1$/)).toBeNull();
    await act(async () => {
      await Promise.resolve();
    });
  });
});
