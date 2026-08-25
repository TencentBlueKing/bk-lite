// @vitest-environment jsdom

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { TopologyNodeData } from '@/app/ops-analysis/types/topology';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';

const testState = vi.hoisted(() => ({
  fetchWidgetData: vi.fn(),
  fetchCompareData: vi.fn(),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/app/ops-analysis/api/topology', () => ({
  useTopologyApi: () => ({
    saveTopology: vi.fn(),
    getTopologyDetail: vi.fn(),
  }),
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => ({
    getSourceDataByApiId: vi.fn(),
  }),
  withRuntimeSourceDataErrorSuppression: <T>(fn: T) => fn,
}));

vi.mock('@/app/ops-analysis/utils/widgetDataTransform', async () => {
  const actual = await vi.importActual<
    typeof import('@/app/ops-analysis/utils/widgetDataTransform')
      >('@/app/ops-analysis/utils/widgetDataTransform');
  return {
    ...actual,
    fetchWidgetData: (...args: unknown[]) => testState.fetchWidgetData(...args),
  };
});

vi.mock('@/app/ops-analysis/utils/compareQuery', async () => {
  const actual = await vi.importActual<
    typeof import('@/app/ops-analysis/utils/compareQuery')
      >('@/app/ops-analysis/utils/compareQuery');
  return {
    ...actual,
    fetchCompareData: (...args: unknown[]) => testState.fetchCompareData(...args),
  };
});

vi.mock('../../utils/singleValueNodeError', () => ({
  clearSingleValueFetchError: vi.fn(),
  resetSingleValueFetchErrorVisual: vi.fn(),
  showSingleValueFetchError: vi.fn(
    (node: { getData: () => Record<string, unknown>; setData: (next: Record<string, unknown>) => void }, errorMessage: string) => {
      node.setData({
        ...node.getData(),
        isLoading: false,
        hasError: true,
        fetchError: true,
        errorMessage,
      });
    },
  ),
  SINGLE_VALUE_ERROR_PLACEHOLDER: '--',
}));

vi.mock('../../utils/topologyUtils', async () => {
  const actual = await vi.importActual<
    typeof import('../../utils/topologyUtils')
      >('../../utils/topologyUtils');
  return {
    ...actual,
    adjustSingleValueNodeSize: vi.fn(),
  };
});

vi.mock('../../utils/registerNode', () => ({
  createNodeByType: vi.fn(),
  updateNodeAttributes: vi.fn(),
}));

import { updateNodeAttributes } from '../../utils/registerNode';
import { useGraphData } from '../useGraphData';
import { useGraphNodeOperations } from '../useGraphNodeOperations';

const chartValueConfig: ValueConfig = {
  dataSource: 7,
  chartType: 'pie',
};

const singleValueNode: TopologyNodeData = {
  id: 'sv-1',
  type: 'single-value',
  name: 'cpu',
  valueConfig: {
    dataSource: 7,
    selectedFields: ['cpu'],
  },
};

const createFakeNode = (initial: Record<string, unknown> = {}) => {
  let data: Record<string, unknown> = { ...initial };
  return {
    getData: () => data,
    setData: (next: Record<string, unknown>) => {
      data = { ...next };
    },
    setAttrByPath: vi.fn(),
    isNode: () => true,
  };
};

const createFakeGraph = (nodes: Record<string, ReturnType<typeof createFakeNode>>) => ({
  getCellById: (id: string) => nodes[id] ?? null,
});

afterEach(() => {
  testState.fetchWidgetData.mockReset();
  testState.fetchCompareData.mockReset();
  vi.mocked(updateNodeAttributes).mockReset();
});

describe('topology chart node owner requests', () => {
  it('skips a silent tick while a manual chart request is in flight and still accepts the manual success', async () => {
    const node = createFakeNode({ type: 'chart', rawData: { name: 'A' } });
    const graph = createFakeGraph({ 'chart-1': node });
    let resolveManual: ((value: unknown) => void) | undefined;
    testState.fetchWidgetData.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveManual = resolve;
        }),
    );

    const { result } = renderHook(() =>
      useGraphData(graph as never, vi.fn()),
    );

    void result.current.loadChartNodeData('chart-1', chartValueConfig);
    await Promise.resolve();
    expect(testState.fetchWidgetData).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.loadChartNodeData('chart-1', chartValueConfig, undefined, undefined, undefined, undefined, undefined, {
        silent: true,
      });
    });
    expect(testState.fetchWidgetData).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveManual?.({ name: 'Manual' });
      await Promise.resolve();
    });
    expect(node.getData().rawData).toEqual({ name: 'Manual' });
    expect(node.getData().hasError).toBe(false);
  });

  it('skips a silent tick while a manual chart request is in flight and still records the manual error', async () => {
    const node = createFakeNode({ type: 'chart', rawData: { name: 'A' } });
    const graph = createFakeGraph({ 'chart-1': node });
    let rejectManual: ((reason?: unknown) => void) | undefined;
    testState.fetchWidgetData.mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          rejectManual = reject;
        }),
    );

    const { result } = renderHook(() =>
      useGraphData(graph as never, vi.fn()),
    );

    void result.current.loadChartNodeData('chart-1', chartValueConfig);
    await Promise.resolve();

    await act(async () => {
      await result.current.loadChartNodeData('chart-1', chartValueConfig, undefined, undefined, undefined, undefined, undefined, {
        silent: true,
      });
    });
    expect(testState.fetchWidgetData).toHaveBeenCalledTimes(1);

    await act(async () => {
      rejectManual?.(new Error('manual failed'));
      await Promise.resolve();
    });
    expect(node.getData().rawData).toBeNull();
    expect(node.getData().hasError).toBe(true);
  });

  it('lets a manual chart request become latest while a silent request is in flight', async () => {
    const node = createFakeNode({ type: 'chart', rawData: { name: 'A' } });
    const graph = createFakeGraph({ 'chart-1': node });
    let resolveSilent: ((value: unknown) => void) | undefined;
    let resolveManual: ((value: unknown) => void) | undefined;
    testState.fetchWidgetData
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveSilent = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveManual = resolve;
          }),
      );

    const { result } = renderHook(() =>
      useGraphData(graph as never, vi.fn()),
    );

    void result.current.loadChartNodeData(
      'chart-1',
      chartValueConfig,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      { silent: true },
    );
    await Promise.resolve();

    void result.current.loadChartNodeData('chart-1', chartValueConfig);
    await Promise.resolve();
    expect(testState.fetchWidgetData).toHaveBeenCalledTimes(2);

    await act(async () => {
      resolveSilent?.({ name: 'Stale' });
      await Promise.resolve();
    });
    expect(node.getData().rawData).toEqual({ name: 'A' });

    await act(async () => {
      resolveManual?.({ name: 'Latest' });
      await Promise.resolve();
    });
    expect(node.getData().rawData).toEqual({ name: 'Latest' });
  });

  it('skips the next periodic tick when an older silent chart request is still in flight after a newer manual completes', async () => {
    const node = createFakeNode({ type: 'chart', rawData: { name: 'A' } });
    const graph = createFakeGraph({ 'chart-1': node });
    let resolveSilent: ((value: unknown) => void) | undefined;
    let resolveManual: ((value: unknown) => void) | undefined;
    testState.fetchWidgetData
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveSilent = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveManual = resolve;
          }),
      );

    const { result } = renderHook(() =>
      useGraphData(graph as never, vi.fn()),
    );

    void result.current.loadChartNodeData(
      'chart-1',
      chartValueConfig,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
      { silent: true },
    );
    await Promise.resolve();
    void result.current.loadChartNodeData('chart-1', chartValueConfig);
    await Promise.resolve();
    expect(testState.fetchWidgetData).toHaveBeenCalledTimes(2);

    await act(async () => {
      resolveManual?.({ name: 'Latest' });
      await Promise.resolve();
    });
    expect(node.getData().rawData).toEqual({ name: 'Latest' });

    await act(async () => {
      await result.current.loadChartNodeData(
        'chart-1',
        chartValueConfig,
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        { silent: true },
      );
    });
    expect(testState.fetchWidgetData).toHaveBeenCalledTimes(2);

    await act(async () => {
      resolveSilent?.({ name: 'Stale' });
      await Promise.resolve();
    });
    expect(node.getData().rawData).toEqual({ name: 'Latest' });
  });

  it('skips a visibility tick when an older manual chart request is still in flight after a newer manual completes', async () => {
    const node = createFakeNode({ type: 'chart', rawData: { name: 'A' } });
    const graph = createFakeGraph({ 'chart-1': node });
    let resolveOlder: ((value: unknown) => void) | undefined;
    let resolveNewer: ((value: unknown) => void) | undefined;
    testState.fetchWidgetData
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveOlder = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveNewer = resolve;
          }),
      );

    const { result } = renderHook(() =>
      useGraphData(graph as never, vi.fn()),
    );

    void result.current.loadChartNodeData('chart-1', chartValueConfig);
    await Promise.resolve();
    void result.current.loadChartNodeData('chart-1', chartValueConfig);
    await Promise.resolve();
    expect(testState.fetchWidgetData).toHaveBeenCalledTimes(2);

    await act(async () => {
      resolveNewer?.({ name: 'Latest' });
      await Promise.resolve();
    });
    expect(node.getData().rawData).toEqual({ name: 'Latest' });

    await act(async () => {
      await result.current.loadChartNodeData(
        'chart-1',
        chartValueConfig,
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        { silent: true },
      );
    });
    expect(testState.fetchWidgetData).toHaveBeenCalledTimes(2);

    await act(async () => {
      resolveOlder?.({ name: 'Stale' });
      await Promise.resolve();
    });
    expect(node.getData().rawData).toEqual({ name: 'Latest' });
  });
});

describe('topology single-value node owner requests', () => {
  const dummyState = {} as never;

  it('skips a silent tick while a manual single-value request is in flight and still accepts the manual success', async () => {
    const node = createFakeNode({ type: 'single-value' });
    const graph = createFakeGraph({ 'sv-1': node });
    let resolveManual: ((value: unknown) => void) | undefined;
    testState.fetchCompareData.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveManual = resolve;
        }),
    );

    const { result } = renderHook(() =>
      useGraphNodeOperations({
        graphInstance: graph as never,
        state: dummyState,
        handleSave: vi.fn(),
      }),
    );

    void result.current.updateSingleNodeData(singleValueNode);
    await Promise.resolve();
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.updateSingleNodeData(singleValueNode, undefined, undefined, undefined, {
        silent: true,
      });
    });
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveManual?.({ currentData: { cpu: 42 }, baselineData: null });
      await Promise.resolve();
    });
    expect(node.setAttrByPath).toHaveBeenCalledWith('label/text', '42');
    expect(node.getData().hasError).toBe(false);
  });

  it('skips a silent tick while a manual single-value request is in flight and still records the manual error', async () => {
    const node = createFakeNode({ type: 'single-value' });
    const graph = createFakeGraph({ 'sv-1': node });
    let rejectManual: ((reason?: unknown) => void) | undefined;
    testState.fetchCompareData.mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          rejectManual = reject;
        }),
    );

    const { result } = renderHook(() =>
      useGraphNodeOperations({
        graphInstance: graph as never,
        state: dummyState,
        handleSave: vi.fn(),
      }),
    );

    void result.current.updateSingleNodeData(singleValueNode);
    await Promise.resolve();

    await act(async () => {
      await result.current.updateSingleNodeData(singleValueNode, undefined, undefined, undefined, {
        silent: true,
      });
    });
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(1);

    await act(async () => {
      rejectManual?.(new Error('manual failed'));
      await Promise.resolve();
    });
    expect(node.getData().hasError).toBe(true);
    expect(node.getData().fetchError).toBe(true);
    expect(node.getData().errorMessage).toBe('manual failed');
  });

  it('lets a manual single-value request become latest while a silent request is in flight', async () => {
    const node = createFakeNode({ type: 'single-value' });
    const graph = createFakeGraph({ 'sv-1': node });
    let resolveSilent: ((value: unknown) => void) | undefined;
    let resolveManual: ((value: unknown) => void) | undefined;
    testState.fetchCompareData
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveSilent = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveManual = resolve;
          }),
      );

    const { result } = renderHook(() =>
      useGraphNodeOperations({
        graphInstance: graph as never,
        state: dummyState,
        handleSave: vi.fn(),
      }),
    );

    void result.current.updateSingleNodeData(singleValueNode, undefined, undefined, undefined, {
      silent: true,
    });
    await Promise.resolve();

    void result.current.updateSingleNodeData(singleValueNode);
    await Promise.resolve();
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);

    await act(async () => {
      resolveSilent?.({ currentData: { cpu: 1 }, baselineData: null });
      await Promise.resolve();
    });
    expect(node.setAttrByPath).not.toHaveBeenCalledWith('label/text', '1');

    await act(async () => {
      resolveManual?.({ currentData: { cpu: 9 }, baselineData: null });
      await Promise.resolve();
    });
    expect(node.setAttrByPath).toHaveBeenCalledWith('label/text', '9');
  });

  it('keeps numeric compare mode after editing a node that previously used percent', async () => {
    const node = createFakeNode({ type: 'single-value' });
    const graph = createFakeGraph({ 'sv-1': node });
    testState.fetchCompareData.mockResolvedValue({
      currentData: { cpu: 42 },
      baselineData: { cpu: 40 },
    });

    const { result } = renderHook(() =>
      useGraphNodeOperations({
        graphInstance: graph as never,
        state: {
          editingNodeData: {
            ...singleValueNode,
            valueConfig: {
              ...singleValueNode.valueConfig,
              compare: true,
              compareMode: 'percent',
              filterBindings: { time: 'range' },
            },
          },
          setNodeEditVisible: vi.fn(),
          setEditingNodeData: vi.fn(),
        } as never,
        handleSave: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.handleNodeUpdate({
        name: 'cpu',
        compare: true,
        compareMode: 'value',
        selectedFields: ['cpu'],
        dataSource: 7,
      });
    });

    expect(updateNodeAttributes).toHaveBeenCalledWith(
      node,
      expect.objectContaining({
        valueConfig: expect.objectContaining({
          compare: true,
          compareMode: 'value',
          filterBindings: { time: 'range' },
        }),
      }),
    );

    await waitFor(() => {
      expect(node.setAttrByPath).toHaveBeenCalledWith(
        'label/text',
        expect.stringMatching(/↑2(?!\.)/),
      );
    });
    const label = vi.mocked(node.setAttrByPath).mock.calls
      .filter((call) => call[0] === 'label/text')
      .at(-1)?.[1];
    expect(String(label)).not.toContain('%');
  });

  it('keeps the previous compare mode when period compare is turned off', async () => {
    const node = createFakeNode({ type: 'single-value' });
    const graph = createFakeGraph({ 'sv-1': node });
    testState.fetchCompareData.mockResolvedValue({
      currentData: { cpu: 42 },
      baselineData: { cpu: 40 },
    });

    const { result } = renderHook(() =>
      useGraphNodeOperations({
        graphInstance: graph as never,
        state: {
          editingNodeData: {
            ...singleValueNode,
            valueConfig: {
              ...singleValueNode.valueConfig,
              compare: true,
              compareMode: 'value',
            },
          },
          setNodeEditVisible: vi.fn(),
          setEditingNodeData: vi.fn(),
        } as never,
        handleSave: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.handleNodeUpdate({
        name: 'cpu',
        compare: false,
        selectedFields: ['cpu'],
        dataSource: 7,
      });
    });

    expect(updateNodeAttributes).toHaveBeenCalledWith(
      node,
      expect.objectContaining({
        valueConfig: expect.objectContaining({
          compare: false,
          compareMode: 'value',
        }),
      }),
    );
  });
});
