import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useTableConfig } from '../useTableConfig';
import type { DisplayColumnRow } from '../../utils/columnProbing';
import { buildWidgetSubmitConfig } from '../../utils/submitConfig';

const styledColumn: DisplayColumnRow = {
  id: 'status-column',
  key: 'status',
  title: 'status',
  visible: true,
  order: 0,
  cellType: 'colorBackground',
  valueMappings: [
    {
      type: 'value',
      value: 'failed',
      result: { text: '失败', color: '#fd666d' },
    },
  ],
  cellThresholdColors: [{ value: '80', color: '#fd666d' }],
};

const otherColumn: DisplayColumnRow = {
  id: 'host-column',
  key: 'host',
  title: '主机',
  visible: true,
  order: 1,
  cellType: 'text',
  valueMappings: [
    { type: 'value', value: 'node-1', result: { text: '节点 1' } },
  ],
};

const renderTableConfig = () =>
  renderHook(() =>
    useTableConfig({
      form: { getFieldValue: vi.fn() } as never,
      chartType: 'table',
      selectedDataSource: undefined,
      availableFields: [
        { key: 'status', title: '状态' },
        { key: 'host_name', title: '主机名' },
      ] as never,
      getSourceDataByApiId: vi.fn(),
      processFormParamsForSubmit: vi.fn(),
      t: (key) => key,
    }),
  );

describe('useTableConfig column field changes', () => {
  it('clears only the changed column cell style when its key changes', () => {
    const { result } = renderTableConfig();
    act(() => result.current.setDisplayColumns([styledColumn, otherColumn]));

    act(() =>
      result.current.handleDisplayColumnChange(
        styledColumn.id,
        'key',
        'host_name',
      ),
    );

    expect(result.current.displayColumns[0]).toEqual({
      id: 'status-column',
      key: 'host_name',
      title: '主机名',
      visible: true,
      order: 0,
    });
    expect(result.current.displayColumns[1]).toEqual(otherColumn);
  });

  it('keeps cell style when the normalized key does not change', () => {
    const { result } = renderTableConfig();
    act(() => result.current.setDisplayColumns([styledColumn]));

    act(() =>
      result.current.handleDisplayColumnChange(styledColumn.id, 'key', 'status'),
    );

    expect(result.current.displayColumns[0]).toEqual({
      ...styledColumn,
      title: '状态',
    });
  });

  it('does not restore cleared style when the changed column is submitted', () => {
    const { result } = renderTableConfig();
    act(() => result.current.setDisplayColumns([styledColumn]));
    act(() =>
      result.current.handleDisplayColumnChange(
        styledColumn.id,
        'key',
        'host_name',
      ),
    );

    const submitted = buildWidgetSubmitConfig({
      values: { name: '健康矩阵', chartType: 'table' },
      chartType: 'table',
      showChartThemeMode: false,
      showTableFilterFields: false,
      selectedFields: [],
      thresholdColors: [],
      filterBindings: {},
      displayColumns: result.current.displayColumns,
      filterFields: [],
      actions: [],
    });

    expect(submitted.config?.tableConfig?.columns?.[0]).toEqual({
      key: 'host_name',
      title: '主机名',
      visible: true,
      order: 0,
      columnType: undefined,
    });
  });
});
