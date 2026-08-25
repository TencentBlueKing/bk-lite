import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import type { LayoutItem } from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import ViewConfig from '@/app/ops-analysis/components/widgetConfig';
import { resolveCardListSettingsRemountKey } from '@/app/ops-analysis/components/widgetConfig/utils/cardListSettingsRemountKey';

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
});

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/hooks/useUnsavedConfirm', () => ({
  default: () => (dirty: boolean, onClose?: () => void) => {
    onClose?.();
  },
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getSourceDataByApiId: vi.fn(),
    getDataSourceDetail: vi.fn(),
  }),
}));

vi.mock('@/app/ops-analysis/components/widgetSelector', () => ({
  default: () => null,
}));

vi.mock('@/app/ops-analysis/components/paramInputConfigEditor', () => ({
  ParamInputConfigEditor: () => null,
}));

vi.mock('@/app/ops-analysis/components/paramsConfig', () => ({
  default: () => null,
}));

vi.mock('@/app/ops-analysis/components/unifiedFilter', () => ({
  FilterBindingPanel: () => null,
}));

vi.mock(
  '@/app/ops-analysis/components/widgetConfig/hooks/useNetworkStatusTopologyConfig',
  () => ({
    useNetworkStatusTopologyConfig: () => ({
      instanceOptions: [],
      instanceOptionsLoading: false,
      resetInstanceOptions: vi.fn(),
      loadInstanceOptions: vi.fn(),
    }),
  }),
);

vi.mock('@/app/ops-analysis/hooks/useSingleValueConfig', () => ({
  useSingleValueConfig: () => ({
    thresholdColors: [],
    setThresholdColors: vi.fn(),
    selectedFields: [],
    setSelectedFields: vi.fn(),
    resetSingleValueConfig: vi.fn(),
  }),
}));

vi.mock('@/app/ops-analysis/components/widgetConfig/hooks/useTableConfig', () => ({
  useTableConfig: () => ({
    displayColumns: [],
    filterFields: [],
    detectedDisplayColumns: [],
    displayColumnsError: '',
    setDisplayColumns: vi.fn(),
    setFilterFields: vi.fn(),
    setDetectedDisplayColumns: vi.fn(),
    setDisplayColumnsError: vi.fn(),
    setParamsChangedAfterProbe: vi.fn(),
    resetTableConfig: vi.fn(),
    handleChartTypeChange: vi.fn(),
    probeDefaultDisplayColumns: vi.fn(async () => []),
  }),
}));

afterEach(cleanup);

const cardListDataSource: DatasourceItem = {
  id: 66,
  name: 'Card List Mock',
  chart_type: ['cardList'],
  field_schema: [
    { key: 'title', title: '标题', value_type: 'string' },
    { key: 'summary', title: '摘要', value_type: 'string' },
    { key: 'severity', title: '级别', value_type: 'string' },
    { key: 'owner', title: '负责人', value_type: 'string' },
  ],
  params: [],
} as DatasourceItem;

const createDraftItem = (): LayoutItem => ({
  i: '',
  x: 0,
  y: 0,
  w: 520,
  h: 360,
  name: '卡片列表',
  description: '',
  valueConfig: {
    dataSource: 66,
    chartType: 'cardList',
    dataSourceParams: [],
    cardList: {
      titleField: 'title',
      descriptionField: 'summary',
    },
  },
});

const editItem = (id: string, withBadge: boolean): LayoutItem => ({
  ...createDraftItem(),
  i: id,
  valueConfig: {
    dataSource: 66,
    chartType: 'cardList',
    dataSourceParams: [],
    cardList: {
      titleField: 'title',
      descriptionField: 'summary',
      ...(withBadge
        ? { badgeField: 'severity' }
        : { trailingPrimaryField: 'owner' }),
    },
  },
});

const buildManager = () => {
  let selectedDataSource: DatasourceItem | undefined = cardListDataSource;
  return {
    selectedDataSource,
    setSelectedDataSource: (next?: DatasourceItem) => {
      selectedDataSource = next;
    },
    ensureDataSource: async () => cardListDataSource,
    setDefaultParamValues: vi.fn(),
    restoreUserParamValues: vi.fn(),
    processFormParamsForSubmit: (params: Record<string, unknown>) => params,
    dataSources: [cardListDataSource],
    dataSourcesLoading: false,
    fetchDataSources: vi.fn(),
    loadCanvasDataSources: vi.fn(),
    findDataSource: () => cardListDataSource,
  };
};

describe('ViewConfig cardList runtime safety', () => {
  it('renders create/close paths with undefined item without crashing', async () => {
    const manager = buildManager();
    const draft = createDraftItem();

    const { rerender } = render(
      <ViewConfig
        open
        item={draft}
        onClose={() => undefined}
        dataSourceManager={manager as never}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('dashboard.cardListSettings')).toBeTruthy();
    });
    expect(screen.getByTestId('card-list-preview')).toBeTruthy();

    expect(() => {
      rerender(
        <ViewConfig
          open={false}
          item={undefined}
          onClose={() => undefined}
          dataSourceManager={manager as never}
        />,
      );
    }).not.toThrow();

    expect(() => {
      rerender(
        <ViewConfig
          open
          item={undefined}
          onClose={() => undefined}
          dataSourceManager={manager as never}
        />,
      );
    }).not.toThrow();
  });

  it('remounts card list settings when switching edit targets', async () => {
    const manager = buildManager();
    const widgetA = editItem('widget-a', true);
    const widgetB = editItem('widget-b', false);

    expect(resolveCardListSettingsRemountKey(widgetA)).toBe('widget-a');
    expect(resolveCardListSettingsRemountKey(widgetB)).toBe('widget-b');
    expect(resolveCardListSettingsRemountKey(undefined)).toBe('new-card-list');
    expect(resolveCardListSettingsRemountKey(createDraftItem())).toBe(
      'new-card-list',
    );

    const { rerender } = render(
      <ViewConfig
        open
        item={widgetA}
        onClose={() => undefined}
        dataSourceManager={manager as never}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId('card-list-optional-badge').getAttribute('aria-expanded'),
      ).toBe('true');
    });

    rerender(
      <ViewConfig
        open
        item={widgetB}
        onClose={() => undefined}
        dataSourceManager={manager as never}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByTestId('card-list-optional-badge').getAttribute('aria-expanded'),
      ).toBe('false');
      expect(
        screen
          .getByTestId('card-list-optional-trailing')
          .getAttribute('aria-expanded'),
      ).toBe('true');
    });
  });
});
