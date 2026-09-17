import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import AlarmFilters from '../alarmFilters';
import type { FiltersConfig } from '../../types/alarms';

const api = vi.hoisted(() => ({ getPushSourceIdOptions: vi.fn() }));
vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('@/app/alarm/context/common', () => ({ useCommon: () => ({ levelList: [], levelMap: {} }) }));
vi.mock('@/app/alarm/api/integration', () => ({ useSourceApi: () => api }));

const emptyFilters: FiltersConfig = {
  level: [],
  state: [],
  alarm_source: [],
  push_source_ids: [],
};

afterEach(cleanup);
beforeAll(() => {
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addListener: vi.fn(), removeListener: vi.fn() });
});
beforeEach(() => {
  api.getPushSourceIdOptions.mockReset().mockResolvedValue(['prod', 'staging']);
});

it('勾选目录项并手输后 onFilterChange 得到 push_source_ids 合并数组', async () => {
  const onFilterChange = vi.fn();
  const { rerender } = render(
    <AlarmFilters
      filters={emptyFilters}
      stateOptions={[]}
      onFilterChange={onFilterChange}
      clearFilters={vi.fn()}
    />
  );

  expect(screen.getByText('alarmCommon.ruleFields.push_source_ids')).toBeTruthy();
  fireEvent.mouseDown(screen.getByRole('combobox', { name: 'alarmCommon.pushSourceSelect' }));
  fireEvent.click(await screen.findByText('prod', { selector: '.ant-select-item-option-content' }));
  expect(onFilterChange).toHaveBeenLastCalledWith(['prod'], 'push_source_ids');

  rerender(
    <AlarmFilters
      filters={{ ...emptyFilters, push_source_ids: ['prod'] }}
      stateOptions={[]}
      onFilterChange={onFilterChange}
      clearFilters={vi.fn()}
    />
  );
  const input = screen.getByRole('combobox', { name: 'alarmCommon.pushSourceInput' });
  fireEvent.change(input, { target: { value: 'k8s-new' } });
  fireEvent.keyDown(input, { key: 'Enter', keyCode: 13 });
  expect(onFilterChange).toHaveBeenLastCalledWith(['prod', 'k8s-new'], 'push_source_ids');
});
