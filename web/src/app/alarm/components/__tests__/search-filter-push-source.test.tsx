import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import SearchFilter from '../searchFilter';
import { buildIntegrationEventSearchParams } from '../../(pages)/integration/detail/integrationEventListRequest';

const api = vi.hoisted(() => ({ getPushSourceIdOptions: vi.fn() }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/alarm/api/integration', () => ({ useSourceApi: () => api }));

afterEach(cleanup);
beforeAll(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addListener: vi.fn(), removeListener: vi.fn() });
});
beforeEach(() => {
  api.getPushSourceIdOptions.mockReset().mockResolvedValue(['k8s', 'k8s-bk-lite-k3s']);
});

const attrList = [
  { attr_id: 'title', attr_name: '标题', attr_type: 'str', option: [] },
  { attr_id: 'push_source_id', attr_name: '监控源', attr_type: 'push_source', option: [] },
];

const chooseMonitorSourceField = async () => {
  fireEvent.mouseDown(screen.getAllByRole('combobox')[0]);
  fireEvent.click(await screen.findByText('监控源', { selector: '.ant-select-item-option-content' }));
  const valueSelect = await screen.findByRole('combobox', { name: 'alarmCommon.pushSourceSelect' });
  await waitFor(() => expect(api.getPushSourceIdOptions).toHaveBeenCalled());
  return valueSelect;
};

it('监控源下拉可搜索目录项', async () => {
  const onSearch = vi.fn();
  render(<SearchFilter attrList={attrList} onSearch={onSearch} />);
  const valueSelect = await chooseMonitorSourceField();
  fireEvent.mouseDown(valueSelect);
  fireEvent.click(await screen.findByText('k8s-bk-lite-k3s', { selector: '.ant-select-item-option-content' }));
  expect(onSearch).toHaveBeenLastCalledWith(
    { field: 'push_source_id', type: 'push_source', value: ['k8s-bk-lite-k3s'] },
    ['k8s-bk-lite-k3s']
  );
});

it('监控源支持自定义录入', async () => {
  const onSearch = vi.fn();
  render(<SearchFilter attrList={attrList} onSearch={onSearch} />);
  const valueSelect = await chooseMonitorSourceField();
  fireEvent.change(valueSelect, { target: { value: 'cluster-new' } });
  fireEvent.keyDown(valueSelect, { key: 'Enter', keyCode: 13 });
  expect(onSearch).toHaveBeenLastCalledWith(
    { field: 'push_source_id', type: 'push_source', value: ['cluster-new'] },
    ['cluster-new']
  );
});

it('可同时勾选多个监控源', async () => {
  const onSearch = vi.fn();
  render(<SearchFilter attrList={attrList} onSearch={onSearch} />);
  fireEvent.mouseDown(await chooseMonitorSourceField());
  fireEvent.click(await screen.findByText('k8s', { selector: '.ant-select-item-option-content' }));
  fireEvent.click(await screen.findByText('k8s-bk-lite-k3s', { selector: '.ant-select-item-option-content' }));
  expect(onSearch).toHaveBeenLastCalledWith(
    { field: 'push_source_id', type: 'push_source', value: ['k8s', 'k8s-bk-lite-k3s'] },
    ['k8s', 'k8s-bk-lite-k3s']
  );
});

it('空选择不带监控源筛选参数，多选发 JSON 数组', () => {
  expect(buildIntegrationEventSearchParams(null)).toEqual({});
  expect(buildIntegrationEventSearchParams({ field: 'push_source_id', type: 'push_source', value: [] })).toEqual({});
  expect(buildIntegrationEventSearchParams({ field: 'title', type: 'str', value: 'CPU' })).toEqual({ title: 'CPU' });
  expect(
    buildIntegrationEventSearchParams({
      field: 'push_source_id',
      type: 'push_source',
      value: ['k8s', 'k8s-bk-lite-k3s'],
    })
  ).toEqual({ push_source_ids: JSON.stringify(['k8s', 'k8s-bk-lite-k3s']) });
});
