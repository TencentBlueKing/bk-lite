import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import UnifiedFilterBar from '@/app/ops-analysis/components/unifiedFilter/unifiedFilterBar';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';

const { getDataSourceList, getSourceDataByApiId } = vi.hoisted(() => ({
  getDataSourceList: vi.fn(),
  getSourceDataByApiId: vi.fn(),
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getDataSourceList,
    getSourceDataByApiId,
  }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const monitorObject: UnifiedFilterDefinition = {
  id: 'object_id__string',
  key: 'object_id',
  name: '监控对象',
  type: 'string',
  defaultValue: null,
  order: 0,
  enabled: true,
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'static',
      staticItems: [{ label: '对象B', value: 'object-b' }],
    },
  },
};

const metric: UnifiedFilterDefinition = {
  id: 'metric_id__string',
  key: 'metric_id',
  name: '指标',
  type: 'string',
  defaultValue: null,
  order: 1,
  enabled: true,
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'dynamic',
      sourceId: 9,
      valueField: 'id',
      labelField: 'name',
      queryParams: { object_id: { ref: 'object_id' } },
    },
  },
};

const instance: UnifiedFilterDefinition = {
  id: 'instance_id__string',
  key: 'instance_id',
  name: '实例',
  type: 'string',
  defaultValue: null,
  order: 2,
  enabled: true,
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'static',
      staticItems: [{ label: '实例1', value: 'instance-1' }],
    },
  },
};

const selectOf = (label: string): HTMLElement => {
  const field = screen.getByText(`${label}:`).parentElement;
  const select = field?.querySelector<HTMLElement>('.ant-select');
  if (!select) throw new Error(`missing select for ${label}`);
  return select;
};

describe('unified filter option loading width', () => {
  afterEach(() => {
    cleanup();
    getSourceDataByApiId.mockReset();
    getDataSourceList.mockReset();
  });

  it('keeps the loading dropdown shell and parks the spinner in the arrow slot', async () => {
    let finish: (value: { data: unknown[]; warnings: string[] }) => void = () => undefined;
    getSourceDataByApiId.mockImplementation(
      () => new Promise((resolve) => {
        finish = resolve;
      }),
    );

    render(
      <UnifiedFilterBar
        definitions={[monitorObject, metric, instance]}
        values={{
          [monitorObject.id]: 'object-b',
          [metric.id]: null,
          [instance.id]: null,
        }}
        onSearch={vi.fn()}
      />,
    );

    const loaded = selectOf('监控对象');
    const loading = selectOf('指标');
    const following = selectOf('实例');

    expect(loading.classList.contains('ant-select-loading')).toBe(true);
    expect(loading.style.width).toBe(loaded.style.width);
    expect(loading.style.minWidth).toBe('220px');
    expect(loading.style.minWidth).toBe(loaded.style.minWidth);
    expect(following.style.width).toBe(loaded.style.width);
    expect(following.style.minWidth).toBe(loaded.style.minWidth);

    const placeholder = loading.querySelector('.ant-select-selection-placeholder');
    expect(placeholder?.textContent).toBe('指标');
    expect(loading.parentElement?.querySelector(':scope > .ant-spin')).toBeNull();

    const spinner = loading.querySelector('.anticon-loading');
    expect(spinner).not.toBeNull();
    expect(spinner?.closest('.ant-select-arrow')).toBe(loading.querySelector('.ant-select-arrow'));
    expect(spinner?.closest('.ant-select-selector')).toBeNull();
    expect(getComputedStyle(loading.querySelector('.ant-select-arrow') as Element).position).toBe('absolute');

    expect(screen.getByText('对象B')).toBeTruthy();
    expect(getSourceDataByApiId).toHaveBeenCalledWith(9, { object_id: 'object-b' }, undefined);

    finish({ data: [{ id: 'cpu', name: 'CPU' }], warnings: [] });
    await waitFor(() => {
      expect(selectOf('指标').classList.contains('ant-select-loading')).toBe(false);
    });
    const settled = selectOf('指标');
    expect(settled.style.width).toBe(loaded.style.width);
    expect(settled.style.minWidth).toBe(loaded.style.minWidth);
    expect(settled.querySelector('.anticon-loading')).toBeNull();
    expect(settled.querySelector('.ant-select-selection-placeholder')?.textContent).toBe('指标');
  });
});
