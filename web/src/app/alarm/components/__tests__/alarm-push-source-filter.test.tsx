import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import AlarmFilters from '../alarmFilters';
import type { FiltersConfig } from '../../types/alarms';

const api = vi.hoisted(() => ({ getPushSourceIdOptions: vi.fn(), getAlertSourceOptions: vi.fn() }));
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
  api.getAlertSourceOptions.mockReset().mockResolvedValue([
    { id: 7, name: 'K8s', source_id: 'k8s', source_type: 'nats' },
    { id: 8, name: 'Prometheus', source_id: 'prometheus', source_type: 'prometheus' },
  ]);
});

it('集成源与级别状态一样勾选集成源名称', async () => {
  const onFilterChange = vi.fn();
  render(
    <AlarmFilters
      filters={emptyFilters}
      stateOptions={[]}
      onFilterChange={onFilterChange}
      clearFilters={vi.fn()}
    />
  );

  fireEvent.click(await screen.findByRole('checkbox', { name: 'K8s' }));
  expect(onFilterChange).toHaveBeenLastCalledWith(['K8s'], 'alarm_source');
  expect(screen.queryByRole('combobox', { name: 'alarmCommon.sourceSelect' })).toBeNull();
  await waitFor(() => expect(api.getAlertSourceOptions).toHaveBeenCalled());
});

it('监控源与级别状态一样勾选目录项，并允许手输自定义值', async () => {
  const onFilterChange = vi.fn();
  const { rerender } = render(
    <AlarmFilters
      filters={emptyFilters}
      stateOptions={[]}
      onFilterChange={onFilterChange}
      clearFilters={vi.fn()}
    />
  );

  fireEvent.click(await screen.findByRole('checkbox', { name: 'prod' }));
  expect(onFilterChange).toHaveBeenLastCalledWith(['prod'], 'push_source_ids');
  expect(screen.queryByRole('combobox', { name: 'alarmCommon.pushSourceSelect' })).toBeNull();

  rerender(
    <AlarmFilters
      filters={{ ...emptyFilters, push_source_ids: ['prod'] }}
      stateOptions={[]}
      onFilterChange={onFilterChange}
      clearFilters={vi.fn()}
    />
  );
  const input = screen.getByRole('combobox', { name: 'alarmCommon.pushSourceInput' });
  fireEvent.mouseEnter(input.closest('div') as HTMLElement);
  expect(await screen.findByText('alarmCommon.pushSourceCustomHint')).toBeTruthy();
  fireEvent.change(input, { target: { value: 'k8s-new' } });
  fireEvent.keyDown(input, { key: 'Enter', keyCode: 13 });
  expect(onFilterChange).toHaveBeenLastCalledWith(['prod', 'k8s-new'], 'push_source_ids');
});
