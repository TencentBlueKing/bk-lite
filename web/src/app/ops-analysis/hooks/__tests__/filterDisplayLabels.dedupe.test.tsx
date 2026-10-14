import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import UnifiedFilterBar from '@/app/ops-analysis/components/unifiedFilter/unifiedFilterBar';
import {
  FilterTemplateProvider,
  useFilterTemplateText,
} from '@/app/ops-analysis/context/filterTemplate';
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
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

const biz: UnifiedFilterDefinition = {
  id: 'biz__string',
  key: 'biz',
  name: '业务',
  type: 'string',
  order: 1,
  enabled: true,
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'dynamic',
      sourceRef: { type: 'rest_api', value: 'cmdb/biz_list' },
      valueField: 'id',
      labelField: 'name',
    },
  },
};

const room: UnifiedFilterDefinition = {
  id: 'room__string',
  key: 'room',
  name: '机房',
  type: 'string',
  order: 2,
  enabled: true,
  inputConfig: {
    control: 'select',
    optionsSource: {
      type: 'dynamic',
      sourceRef: { type: 'rest_api', value: 'cmdb/room_list' },
      valueField: 'id',
      labelField: 'name',
    },
  },
};

const Probe = ({ text }: { text: string }) => {
  const resolved = useFilterTemplateText(text);
  return <span data-testid="resolved">{resolved}</span>;
};

const renderCanvas = ({
  withBar,
  nested = false,
  canvasId = 'canvas-a',
}: {
  withBar: boolean;
  nested?: boolean;
  canvasId?: string;
}) => {
  const applied = { 'biz__string': '42', 'room__string': '7' };
  const probe = <Probe text="$biz$ / $room$" />;
  const canvas = nested ? (
    <FilterTemplateProvider
      definitions={[biz, room]}
      appliedValues={applied}
      resolveEnabled
      canvasId={canvasId}
    >
      {probe}
    </FilterTemplateProvider>
  ) : probe;

  return render(
    <FilterTemplateProvider
      definitions={[biz, room]}
      appliedValues={applied}
      resolveEnabled={!nested}
      canvasId={canvasId}
    >
      {withBar && (
        <UnifiedFilterBar
          definitions={[biz]}
          values={{ 'biz__string': '42' }}
          onSearch={vi.fn()}
        />
      )}
      {canvas}
    </FilterTemplateProvider>,
  );
};

describe('筛选标题复用筛选栏选项', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        media: '',
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
    getDataSourceList.mockReset();
    getSourceDataByApiId.mockReset();
    getDataSourceList.mockImplementation(async () => ({
      items: [
        { id: 9, name: '业务列表', rest_api: 'cmdb/biz_list' },
        { id: 8, name: '机房列表', rest_api: 'cmdb/room_list' },
      ],
    }));
    getSourceDataByApiId.mockImplementation(async (id: number) => ({
      data: {
        items: id === 9
          ? [{ id: '42', name: '蓝鲸' }]
          : [{ id: '7', name: '一号机房' }],
      },
      warnings: [],
    }));
  });

  afterEach(() => {
    cleanup();
  });

  it('筛选栏已渲染的筛选用栏里的选项，未渲染的才自己加载', async () => {
    renderCanvas({ withBar: true, nested: true });

    await waitFor(() => {
      expect(screen.getByTestId('resolved').textContent).toBe('蓝鲸 / 一号机房');
    });

    const sourceIds = getSourceDataByApiId.mock.calls.map((call) => call[0]);
    expect(sourceIds.filter((id) => id === 9)).toEqual([9]);
    expect(sourceIds.filter((id) => id === 8)).toEqual([8]);
    expect(getDataSourceList).toHaveBeenCalledTimes(2);
  });

  it('筛选栏不在画布上时，每个动态筛选只加载一次', async () => {
    renderCanvas({ withBar: false });

    await waitFor(() => {
      expect(screen.getByTestId('resolved').textContent).toBe('蓝鲸 / 一号机房');
    });

    const sourceIds = getSourceDataByApiId.mock.calls.map((call) => call[0]).sort();
    expect(sourceIds).toEqual([8, 9]);
    expect(getDataSourceList).toHaveBeenCalledTimes(2);
  });

  it('切换画布后先显示筛选项名称，再显示新画布的选项', async () => {
    let releaseNext: (() => void) | undefined;
    getSourceDataByApiId.mockImplementation((id: number) => {
      if (id !== 9) {
        return Promise.resolve({
          data: { items: [{ id: '7', name: '一号机房' }] },
          warnings: [],
        });
      }
      const callCount = getSourceDataByApiId.mock.calls.filter((call) => call[0] === 9).length;
      if (callCount === 1) {
        return Promise.resolve({
          data: { items: [{ id: '42', name: '蓝鲸' }] },
          warnings: [],
        });
      }
      return new Promise((resolve) => {
        releaseNext = () => resolve({
          data: { items: [{ id: '42', name: '织云' }] },
          warnings: [],
        });
      });
    });

    const view = renderCanvas({ withBar: false, canvasId: 'canvas-a' });
    await waitFor(() => {
      expect(screen.getByTestId('resolved').textContent).toBe('蓝鲸 / 一号机房');
    });

    view.rerender(
      <FilterTemplateProvider
        definitions={[biz, room]}
        appliedValues={{ 'biz__string': '42', 'room__string': '7' }}
        resolveEnabled
        canvasId="canvas-b"
      >
        <Probe text="$biz$ / $room$" />
      </FilterTemplateProvider>,
    );

    await waitFor(() => {
      const text = screen.getByTestId('resolved').textContent ?? '';
      expect(text.startsWith('业务')).toBe(true);
      expect(text.includes('蓝鲸')).toBe(false);
    });
    expect(getSourceDataByApiId.mock.calls.filter((call) => call[0] === 9)).toHaveLength(2);

    releaseNext?.();
    await waitFor(() => {
      expect(screen.getByTestId('resolved').textContent).toBe('织云 / 一号机房');
    });
  });

  it('从没有筛选变成有筛选时，每个动态数据源只请求一次', async () => {
    const view = render(
      <FilterTemplateProvider
        definitions={[]}
        appliedValues={{}}
        resolveEnabled
        canvasId="canvas-a"
      >
        <UnifiedFilterBar definitions={[]} values={{}} onSearch={vi.fn()} />
        <Probe text="$biz$ / $room$" />
      </FilterTemplateProvider>,
    );

    view.rerender(
      <FilterTemplateProvider
        definitions={[biz, room]}
        appliedValues={{ biz__string: '42', room__string: '7' }}
        resolveEnabled
        canvasId="canvas-a"
      >
        <UnifiedFilterBar
          definitions={[biz, room]}
          values={{ biz__string: '42', room__string: '7' }}
          onSearch={vi.fn()}
        />
        <Probe text="$biz$ / $room$" />
      </FilterTemplateProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('resolved').textContent).toBe('蓝鲸 / 一号机房');
    });
    expect(getSourceDataByApiId.mock.calls.filter((call) => call[0] === 9)).toHaveLength(1);
    expect(getSourceDataByApiId.mock.calls.filter((call) => call[0] === 8)).toHaveLength(1);
  });

  it('改一个动态筛选配置只重载该筛选，其他控件和静态选项不进入 loading', async () => {
    const env: UnifiedFilterDefinition = {
      id: 'env__string',
      key: 'env',
      name: '环境',
      type: 'string',
      order: 3,
      enabled: true,
      inputConfig: {
        control: 'select',
        optionsSource: {
          type: 'static',
          staticItems: [{ label: '生产', value: 'prod' }],
        },
      },
    };
    const bizV2: UnifiedFilterDefinition = {
      ...biz,
      inputConfig: {
        control: 'select',
        optionsSource: {
          type: 'dynamic',
          sourceRef: { type: 'rest_api', value: 'cmdb/biz_list_v2' },
          valueField: 'id',
          labelField: 'name',
        },
      },
    };
    getDataSourceList.mockImplementation(async () => ({
      items: [
        { id: 9, name: '业务列表', rest_api: 'cmdb/biz_list' },
        { id: 11, name: '业务列表二', rest_api: 'cmdb/biz_list_v2' },
        { id: 8, name: '机房列表', rest_api: 'cmdb/room_list' },
      ],
    }));
    let releaseV2: (() => void) | undefined;
    getSourceDataByApiId.mockImplementation((id: number) => {
      if (id === 11) {
        return new Promise((resolve) => {
          releaseV2 = () => resolve({
            data: { items: [{ id: '42', name: '织云' }] },
            warnings: [],
          });
        });
      }
      return Promise.resolve({
        data: {
          items: id === 9
            ? [{ id: '42', name: '蓝鲸' }]
            : [{ id: '7', name: '一号机房' }],
        },
        warnings: [],
      });
    });

    const applied = { biz__string: '42', room__string: '7', env__string: 'prod' };
    const view = render(
      <FilterTemplateProvider
        definitions={[biz, room, env]}
        appliedValues={applied}
        resolveEnabled
        canvasId="canvas-a"
      >
        <UnifiedFilterBar
          definitions={[biz, room, env]}
          values={applied}
          onSearch={vi.fn()}
        />
        <Probe text="$biz$ / $room$" />
      </FilterTemplateProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('resolved').textContent).toBe('蓝鲸 / 一号机房');
    });

    view.rerender(
      <FilterTemplateProvider
        definitions={[bizV2, room, env]}
        appliedValues={applied}
        resolveEnabled
        canvasId="canvas-a"
      >
        <UnifiedFilterBar
          definitions={[bizV2, room, env]}
          values={applied}
          onSearch={vi.fn()}
        />
        <Probe text="$biz$ / $room$" />
      </FilterTemplateProvider>,
    );

    await waitFor(() => {
      expect(getSourceDataByApiId.mock.calls.filter((call) => call[0] === 11)).toHaveLength(1);
    });
    const spinCount = (label: string) => (
      screen.getByText(`${label}:`).parentElement?.querySelectorAll('.ant-spin').length ?? 0
    );
    expect(spinCount('业务')).toBe(1);
    expect(spinCount('机房')).toBe(0);
    expect(spinCount('环境')).toBe(0);
    expect(screen.getByTestId('resolved').textContent).toBe('业务 / 一号机房');
    expect(getSourceDataByApiId.mock.calls.filter((call) => call[0] === 9)).toHaveLength(1);
    expect(getSourceDataByApiId.mock.calls.filter((call) => call[0] === 8)).toHaveLength(1);

    releaseV2?.();
    await waitFor(() => {
      expect(screen.getByTestId('resolved').textContent).toBe('织云 / 一号机房');
    });
    expect(getSourceDataByApiId.mock.calls.filter((call) => call[0] === 11)).toHaveLength(1);
    expect(getSourceDataByApiId.mock.calls.filter((call) => call[0] === 8)).toHaveLength(1);
  });
});
