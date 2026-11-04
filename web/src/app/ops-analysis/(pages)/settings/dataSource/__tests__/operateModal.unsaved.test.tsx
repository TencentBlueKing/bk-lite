import React from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Modal } from 'antd';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import OperateModal from '../operateModal';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

const row = {
  id: 7,
  name: '验收-级联指标图',
  source_type: 'nats',
  rest_api: 'demo/accept_cascade_chart_params',
  desc: '仅本地验收',
  params: [],
  chart_type: ['line'],
  namespaces: [1],
  tag: [1],
  groups: [1],
} as unknown as DatasourceItem;

const {
  translate,
  userInfo,
  opsAnalysis,
  namespaceApi,
  dataConnectionApi,
  dataSourceApi,
} = vi.hoisted(() => {
  const translate = (key: string) => key;
  const userInfo = {
    selectedGroup: { id: 1 },
    isSuperUser: true,
    groupTree: [{ id: 1, name: 'Default', hasAuth: true, subGroups: [] }],
  };
  const opsAnalysis = {
    namespaceList: [{ id: 1, name: 'PERM-NS-1' }],
    namespacesLoading: false,
    refreshNamespaces: async () => undefined,
  };
  const namespaceApi = {
    getTagList: async () => [{ id: 1, name: '监控' }],
  };
  const dataConnectionApi = {
    getDataConnectionList: async () => ({ items: [] }),
    createDataConnection: async () => undefined,
  };
  const savedRow = {
    id: 7,
    name: '验收-级联指标图',
    source_type: 'nats',
    rest_api: 'demo/accept_cascade_chart_params',
    desc: '仅本地验收',
    params: [],
    chart_type: ['line'],
    namespaces: [1],
    tag: [1],
    groups: [1],
  };
  const dataSourceApi = {
    createDataSource: async () => undefined,
    updateDataSource: async () => undefined,
    patchDataSource: async () => undefined,
    deleteDataSource: async () => undefined,
    previewDataSource: async () => undefined,
    previewDataSourceConfig: async () => undefined,
    submitExcelMaterialization: async () => undefined,
    retryExcelMaterialization: async () => undefined,
    getDataSourceDetail: async (id: number) =>
      id === 8 ? { ...savedRow, id: 8, groups: [1, 4] } : savedRow,
    testDataSourceConnection: async () => undefined,
    testDataSourceConnectionConfig: async () => undefined,
    extractDataSourceConnection: async () => undefined,
  };
  return {
    translate,
    userInfo,
    opsAnalysis,
    namespaceApi,
    dataConnectionApi,
    dataSourceApi,
  };
});

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', ResizeObserverStub);
  Element.prototype.scrollTo = () => undefined;
});

let confirmSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  confirmSpy = vi.spyOn(Modal, 'confirm');
});

afterEach(() => {
  confirmSpy.mockRestore();
  Modal.destroyAll();
  cleanup();
});

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: translate,
  }),
}));

vi.mock('@/context/userInfo', () => ({
  useUserInfoContext: () => userInfo,
}));

vi.mock('@/app/ops-analysis/context/common', () => ({
  useOpsAnalysis: () => opsAnalysis,
}));

vi.mock('@/app/ops-analysis/api/namespace', () => ({
  useNamespaceApi: () => namespaceApi,
}));

vi.mock('@/app/ops-analysis/api/dataConnection', () => ({
  useDataConnectionApi: () => dataConnectionApi,
}));

vi.mock('@/app/ops-analysis/api/dataSource', () => ({
  useDataSourceApi: () => dataSourceApi,
}));

describe('data source drawer unsaved guard', () => {
  it('closes an untouched edit drawer without the discard prompt', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(
      <OperateModal open mode="edit" currentRow={row} onClose={onClose} />,
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('验收-级联指标图')).toBeTruthy();
    });

    await user.click(screen.getByRole('button', { name: 'common.cancel' }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('still asks before closing after a real edit', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(
      <OperateModal open mode="edit" currentRow={row} onClose={onClose} />,
    );

    const name = await screen.findByDisplayValue('验收-级联指标图');
    await user.clear(name);
    await user.type(name, '改过的名称');
    await user.click(screen.getByRole('button', { name: 'common.cancel' }));

    expect(onClose).not.toHaveBeenCalled();
    expect(confirmSpy).toHaveBeenCalledTimes(1);
  });

  it('closes when a saved group is outside the current organization tree', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const outsideTreeRow = {
      ...row,
      id: 8,
      groups: [1, 4],
    } as DatasourceItem;

    render(
      <OperateModal open mode="edit" currentRow={outsideTreeRow} onClose={onClose} />,
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('验收-级联指标图')).toBeTruthy();
    });

    await user.click(screen.getByRole('button', { name: 'common.cancel' }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('closes an untouched create drawer after the default namespace is filled in', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();

    render(<OperateModal open mode="add" onClose={onClose} />);

    await waitFor(() => {
      const checkbox = screen.getByRole('checkbox', { name: 'PERM-NS-1' }) as HTMLInputElement;
      expect(checkbox.checked).toBe(true);
    });

    await user.click(screen.getByRole('button', { name: 'common.cancel' }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(confirmSpy).not.toHaveBeenCalled();
  });
});
