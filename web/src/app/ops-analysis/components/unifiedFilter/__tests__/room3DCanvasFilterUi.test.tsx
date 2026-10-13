import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import UnifiedFilterBar from '@/app/ops-analysis/components/unifiedFilter/unifiedFilterBar';
import UnifiedFilterConfigModal from '@/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal';
import {
  ROOM3D_FILTER_ID,
  ROOM3D_FILTER_INPUT_CONFIG,
} from '@/app/ops-analysis/utils/room3DScreenFilter';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';
import type { LayoutItem } from '@/app/ops-analysis/types/dashBoard';

const ROOM_A = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const ROOM_B = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';

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

const translate = (key: string) => {
  const messages: Record<string, string> = {
    'dashboard.room3DFilterName': '机房',
    'dashboard.noFiltersConfigured': '暂未配置筛选项',
    'dashboard.unifiedFilterConfig': '全局筛选',
    'dashboard.filterKey': '参数名',
    'dashboard.filterName': '显示名称',
    'dashboard.defaultValue': '默认值',
    'dashboard.enabled': '启用',
    'dashboard.configure': '配置',
    'common.confirm': '确认',
    'common.cancel': '取消',
    'common.search': '查询',
    'common.reset': '重置',
    'common.inputTip': '请输入',
    'paramInput.controlType': '控件类型',
    'paramInput.control.input': '文本输入',
    'paramInput.control.select': '下拉选择',
    'paramInput.control.radio': '单选框',
    'paramInput.control.organization': '组织选择',
    'dataSource.paramTypes.string': '字符串',
  };
  return messages[key] ?? key;
};

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: translate,
  }),
}));

const roomFilter = (
  overrides: Partial<UnifiedFilterDefinition> = {},
): UnifiedFilterDefinition => ({
  id: ROOM3D_FILTER_ID,
  key: 'server_room_id',
  name: '机房',
  type: 'string',
  defaultValue: null,
  order: 0,
  enabled: true,
  inputConfig: ROOM3D_FILTER_INPUT_CONFIG,
  ...overrides,
});

const roomLayout = (): LayoutItem => ({
  i: 'room',
  x: 0,
  y: 0,
  w: 12,
  h: 8,
  name: '3D机房',
  valueConfig: {
    chartType: 'room3D',
    sceneWidgetType: 'room3D',
  },
});

const openRoomSelect = async () => {
  const placeholder = await screen.findByText('机房', {
    selector: '.ant-select-selection-placeholder',
  });
  const selector = placeholder.closest('.ant-select-selector');
  if (!selector) {
    throw new Error('room select missing');
  }
  fireEvent.mouseDown(selector);
};

describe('room3D canvas filter UI', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
    getDataSourceList.mockReset();
    getSourceDataByApiId.mockReset();
    getDataSourceList.mockResolvedValue({
      items: [
        { id: 17, name: 'CMDB 机房列表（选项）', rest_api: 'cmdb/get_room_list' },
      ],
    });
    getSourceDataByApiId.mockResolvedValue({
      data: {
        items: [
          { inst_uuid: ROOM_B, inst_name: '二号机房', _id: 2 },
          { inst_uuid: ROOM_A, inst_name: '一号机房', _id: 1 },
          { id: 'legacy', name: '旧字段' },
        ],
      },
      warnings: [],
    });
  });

  afterEach(() => {
    cleanup();
  });

  it('loads room options on the filter bar from the catalog and inst_uuid/inst_name', async () => {
    const onSearch = vi.fn();
    render(
      <UnifiedFilterBar
        definitions={[roomFilter()]}
        values={{}}
        onSearch={onSearch}
      />,
    );

    expect(screen.getByText('机房:')).not.toBeNull();
    expect(await screen.findByText('二号机房')).not.toBeNull();
    await waitFor(() => {
      expect(onSearch).toHaveBeenCalledWith({ [ROOM3D_FILTER_ID]: ROOM_B });
      expect(getDataSourceList).toHaveBeenCalledWith({ page_size: -1 });
      expect(getSourceDataByApiId).toHaveBeenCalledWith(17, {}, undefined);
    });
    expect(screen.queryByText('暂无数据')).toBeNull();
    expect(screen.queryByText('旧字段')).toBeNull();
  });

  it('keeps an invisible room default instead of selecting the first option', async () => {
    const missing = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
    const onSearch = vi.fn();
    render(
      <UnifiedFilterBar
        definitions={[roomFilter({ defaultValue: missing })]}
        values={{}}
        onSearch={onSearch}
      />,
    );

    await waitFor(() => {
      expect(onSearch).toHaveBeenCalledWith({ [ROOM3D_FILTER_ID]: missing });
    });
    expect(onSearch.mock.calls.some((call) => call[0]?.[ROOM3D_FILTER_ID] === ROOM_B)).toBe(false);
  });

  it('shows the room filter in the global filter modal when the canvas has room3D', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <UnifiedFilterConfigModal
        open
        onCancel={vi.fn()}
        onConfirm={onConfirm}
        definitions={[]}
        layoutItems={[roomLayout()]}
        dataSources={[]}
      />,
    );

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).queryByText('暂未配置筛选项')).toBeNull();
    expect(within(dialog).getByDisplayValue('机房')).not.toBeNull();
    expect(within(dialog).getByText('server_room_id')).not.toBeNull();

    await openRoomSelect();
    await user.click(await screen.findByText('一号机房'));
    await user.click(within(dialog).getByRole('switch'));
    await user.click(within(dialog).getByRole('button', { name: '确 认' }));

    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });
    expect(onConfirm.mock.calls[0]?.[0]).toEqual([
      expect.objectContaining({
        id: ROOM3D_FILTER_ID,
        name: '机房',
        defaultValue: ROOM_A,
        enabled: false,
        inputConfig: ROOM3D_FILTER_INPUT_CONFIG,
      }),
    ]);
  });

  it('keeps an empty global filter modal when the canvas has no room3D', async () => {
    render(
      <UnifiedFilterConfigModal
        open
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        definitions={[]}
        layoutItems={[{ ...roomLayout(), valueConfig: { chartType: 'line' } }]}
        dataSources={[]}
      />,
    );

    expect(await screen.findByText('暂未配置筛选项')).not.toBeNull();
    expect(screen.queryByDisplayValue('机房')).toBeNull();
  });
});
