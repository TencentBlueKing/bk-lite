import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { message } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { ParamInputConfigEditor } from '@/app/ops-analysis/components/paramInputConfigEditor';

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

vi.mock('@/utils/i18n', () => {
  const t = (key: string, _fallback?: string, values?: Record<string, string>) => {
      const text: Record<string, string> = {
        'paramInput.title': '参数输入配置',
        'paramInput.dynamic.source': '数据源',
        'paramInput.dynamic.valueField': '值字段',
        'paramInput.dynamic.labelField': '展示字段',
        'paramInput.dynamic.valueFieldPlaceholder': '请选择值字段',
        'paramInput.dynamic.labelFieldPlaceholder': '请选择展示字段',
        'paramInput.dynamic.fieldNamePlaceholder': '输入或选择字段名',
        'paramInput.dynamic.queryParams': '选项查询参数',
        'paramInput.dynamic.queryParamAlias': '别名',
        'paramInput.dynamic.queryParamTechnicalName': '参数名',
        'paramInput.dynamic.valueMode': '取值方式',
        'paramInput.dynamic.valueOrRef': '值/引用',
        'paramInput.dynamic.fixedValue': '固定值',
        'paramInput.dynamic.dollarRef': '引用参数',
        'paramInput.dynamic.selectUpstream': '选择上游筛选',
        'paramInput.dynamic.noRefCandidates': '暂无其它可引用的筛选',
        'paramInput.dynamic.originGlobalFilter': '全局筛选',
        'paramInput.dynamic.originComponentParam': '组件参数',
        'paramInput.dynamic.refChoice': '{origin} · {name}',
        'paramInput.dynamic.refChoiceWithKey': '{origin} · {name} ({key})',
        'paramInput.dynamic.refChoiceWithHint': '{origin} · {name} · {hint}',
        'paramInput.dynamic.cycle': '查询入参存在循环：{path}',
        'paramInput.dynamic.depth': '查询入参依赖超过 3 级：{path}',
        'paramInput.dynamic.ambiguousRef': '同名筛选有多条，请按来源选择具体一项',
        'paramInput.dynamic.previewFixedOnly': '引用参数在运行时生效，预览仅使用已填固定值',
        'paramInput.dynamic.queryParamValue': '填写固定值',
        'paramInput.dynamic.preview': '预览',
        'paramInput.dynamic.testFailed': '选项源不可用',
        'common.confirm': '确认',
        'common.cancel': '取消',
        'dashboard.componentSwitch': '组件内切换',
        'dashboard.componentSwitchDisabledByQueryRef': '查询入参含有引用时不能开启组件内切换',
      };
      return (text[key] || key).replace(/\{(\w+)\}/g, (_, name) => values?.[name] ?? '');
  };
  return {
    useTranslation: () => ({ t }),
  };
});

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

const deviceSource = {
  id: 9,
  name: '设备列表',
  rest_api: 'cmdb/devices',
  params: [
    { name: 'room_id', type: 'string', alias_name: '机房', value: 'should-not-override-ref' },
    { name: 'zone_id', type: 'number', alias_name: '区域', value: 7 },
    { name: 'area_code', type: 'string', alias_name: '片区', value: 'from-source' },
    { name: 'note', type: 'string', alias_name: '备注', value: null },
    { name: 'raw_only', type: 'string', alias_name: '', value: '' },
  ],
  field_schema: [
    { key: 'id', title: '编号', value_type: 'string' },
    { key: 'name', title: '名称', value_type: 'string' },
  ],
};

const globalFilterContext = {
  scope: 'globalFilter' as const,
  self: { id: 'device_id__string', key: 'device_id' },
  globalFilters: [
    { id: 'site_id__string', key: 'site_id', label: '监控对象', type: 'string', enabled: true },
  ],
  componentParams: [
    { name: 'secret', label: '别的组件', type: 'string' },
  ],
};

describe('param input query params', () => {
  afterEach(() => {
    cleanup();
    getDataSourceList.mockReset();
    getSourceDataByApiId.mockReset();
  });

  it('shows aliases, keeps saved values, and leaves the query table unbordered', async () => {
    const user = userEvent.setup();
    getDataSourceList.mockResolvedValue([deviceSource]);
    render(
      <ParamInputConfigEditor
        open
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 9,
            valueField: 'id',
            labelField: 'name',
            queryParams: { room_id: { ref: 'site_id' } },
          },
        }}
        optionsQueryContext={globalFilterContext}
      />,
    );

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('机房')).not.toBeNull();
    const roomRow = within(dialog).getByText('room_id').closest('tr');
    const roomCells = Array.from((roomRow as HTMLElement).querySelectorAll('td')).map((cell) => cell.textContent);
    expect(roomCells[0]).toBe('room_id');
    expect(roomCells[1]).toBe('机房');
    expect(roomCells[2]).toContain('引用参数');
    expect(within(dialog).getByText('zone_id').closest('tr')?.textContent).toContain('区域');
    const rawRow = within(dialog).getByText('raw_only').closest('tr');
    expect(within(rawRow as HTMLElement).getByText('—')).not.toBeNull();
    const modeHeader = within(dialog).getByRole('columnheader', { name: '取值方式' });
    const queryTable = modeHeader.closest('table');
    expect(queryTable?.style.tableLayout).toBe('fixed');
    const widths = Array.from(queryTable?.querySelectorAll('col') ?? []).map((col) => col.style.width);
    expect(widths).toEqual(['112px', '112px', '112px']);
    expect(queryTable?.closest('.ant-table-bordered')).toBeNull();
    expect(dialog.querySelector('.ant-table-bordered')).not.toBeNull();
    const headers = within(queryTable as HTMLElement).getAllByRole('columnheader').map((header) => header.textContent);
    expect(headers).toEqual(['参数名', '别名', '取值方式', '值/引用']);
    expect(within(dialog).queryByRole('columnheader', { name: '入参名' })).toBeNull();
    expect(within(dialog).getByRole('columnheader', { name: '值/引用' })).not.toBeNull();
    expect(within(dialog).queryByText('示例值')).toBeNull();
    expect(within(dialog).queryByPlaceholderText('示例值')).toBeNull();
    expect(within(dialog).getByText('引用参数在运行时生效，预览仅使用已填固定值')).not.toBeNull();
    expect((within(dialog).getByRole('button', { name: '预览' }) as HTMLButtonElement).disabled).toBe(false);
    expect(within(dialog).getByText('全局筛选 · 监控对象')).not.toBeNull();
    expect(getSourceDataByApiId).not.toHaveBeenCalled();

    await user.click(within(dialog).getByText('全局筛选 · 监控对象'));
    await waitFor(() => {
      expect(screen.queryByText('组件参数 · 别的组件')).toBeNull();
    });
  });

  it('prefills declared values and keeps a saved literal or reference', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    let resolveList: (value: unknown) => void = () => undefined;
    getDataSourceList.mockReturnValue(new Promise((resolve) => {
      resolveList = resolve;
    }));
    render(
      <ParamInputConfigEditor
        open
        onCancel={vi.fn()}
        onConfirm={onConfirm}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 9,
            valueField: 'id',
            labelField: 'name',
            queryParams: {
              room_id: { ref: 'site_id' },
              area_code: 'saved',
            },
          },
        }}
        optionsQueryContext={globalFilterContext}
      />,
    );

    expect(getSourceDataByApiId).not.toHaveBeenCalled();
    resolveList([deviceSource]);
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByDisplayValue('7')).not.toBeNull();
    expect(within(dialog).getByDisplayValue('saved')).not.toBeNull();
    expect(within(dialog).queryByDisplayValue('from-source')).toBeNull();
    expect(within(dialog).queryByDisplayValue('should-not-override-ref')).toBeNull();
    expect(getSourceDataByApiId).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole('button', { name: /确\s*认/ }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalled());
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({
      optionsSource: expect.objectContaining({
        queryParams: {
          room_id: { ref: 'site_id__string' },
          zone_id: 7,
          area_code: 'saved',
        },
      }),
    }));
  });

  it('previews with filled fixed values only and keeps fields when the trial fails', async () => {
    const user = userEvent.setup();
    getDataSourceList.mockResolvedValue([deviceSource]);
    getSourceDataByApiId
      .mockResolvedValueOnce({ data: [{ id: 1, name: 'n', extra_col: 'e' }] })
      .mockRejectedValueOnce(new Error('later'));
    render(
      <ParamInputConfigEditor
        open
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 9,
            valueField: 'id',
            labelField: 'name',
            queryParams: { room_id: { ref: 'site_id' } },
          },
        }}
        optionsQueryContext={globalFilterContext}
      />,
    );

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByDisplayValue('7')).not.toBeNull();
    const note = within(dialog).getAllByRole('textbox').find((input) => (
      (input as HTMLInputElement).value === ''
    ));
    expect(note).toBeTruthy();
    await user.type(note as HTMLElement, 'typed');
    await user.click(within(dialog).getByRole('button', { name: '预览' }));
    await waitFor(() => expect(getSourceDataByApiId).toHaveBeenCalledTimes(1));
    expect(getSourceDataByApiId).toHaveBeenCalledWith(9, {
      zone_id: 7,
      area_code: 'from-source',
      note: 'typed',
    });
    expect(await within(dialog).findByRole('columnheader', { name: 'extra_col' })).not.toBeNull();

    fireEvent.mouseDown(within(dialog).getByRole('combobox', { name: '值字段' }));
    await waitFor(() => {
      const optionText = [...document.querySelectorAll('.ant-select-item-option')].map((node) => node.textContent);
      expect(optionText).toEqual(expect.arrayContaining(['编号（id）', '名称（name）', 'extra_col']));
      expect(optionText).not.toContain('id');
    });
    fireEvent.keyDown(within(dialog).getByRole('combobox', { name: '值字段' }), { key: 'Escape' });

    await user.click(within(dialog).getByRole('button', { name: '预览' }));
    await waitFor(() => {
      expect(getSourceDataByApiId).toHaveBeenCalledTimes(2);
      expect(within(dialog).queryByRole('columnheader', { name: 'extra_col' })).toBeNull();
    });
    expect(within(dialog).getAllByText('编号（id）').length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText('名称（name）').length).toBeGreaterThan(0);
    fireEvent.mouseDown(within(dialog).getByRole('combobox', { name: '值字段' }));
    await waitFor(() => {
      const optionText = [...document.querySelectorAll('.ant-select-item-option')].map((node) => node.textContent);
      expect(optionText).toContain('extra_col');
      expect(optionText).toContain('编号（id）');
    });
  });

  it('auto previews a source that does not declare params', async () => {
    getDataSourceList.mockResolvedValue([
      {
        id: 4,
        name: '无入参',
        params: [],
        field_schema: [{ key: 'id', title: '编号', value_type: 'string' }],
      },
    ]);
    getSourceDataByApiId.mockResolvedValue({ data: [] });
    render(
      <ParamInputConfigEditor
        open
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 4,
            valueField: 'id',
            labelField: 'name',
          },
        }}
      />,
    );

    await waitFor(() => expect(getSourceDataByApiId).toHaveBeenCalledWith(4, {}));
    expect(getSourceDataByApiId.mock.calls.every(([sourceId, params]) => (
      sourceId === 4 && JSON.stringify(params) === '{}'
    ))).toBe(true);
  });

  it('accepts a typed field name when the source has no schema', async () => {
    const user = userEvent.setup();
    getDataSourceList.mockResolvedValue([
      { id: 4, name: '无结构', params: [{ name: 'q', type: 'string', alias_name: '关键字', value: '' }] },
    ]);
    render(
      <ParamInputConfigEditor
        open
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 4,
            valueField: '',
            labelField: '',
          },
        }}
      />,
    );

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('关键字')).not.toBeNull();
    expect(getSourceDataByApiId).not.toHaveBeenCalled();
    const valueCombo = within(dialog).getByRole('combobox', { name: '值字段' });
    await user.click(valueCombo);
    await user.type(valueCombo, 'device_name{Enter}');
    await waitFor(() => {
      expect(valueCombo.closest('.ant-select')?.querySelector('.ant-select-selection-item')?.textContent).toBe('device_name');
    });
  });

  it('turns component switch off when a query parameter uses a reference', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    getDataSourceList.mockResolvedValue([deviceSource]);
    render(
      <ParamInputConfigEditor
        open
        componentSwitchEnabled
        onCancel={vi.fn()}
        onConfirm={onConfirm}
        value={{
          control: 'select',
          componentSwitch: true,
          optionsSource: {
            type: 'dynamic',
            sourceId: 9,
            valueField: 'id',
            labelField: 'name',
            queryParams: { room_id: { ref: 'site_id' } },
          },
        }}
        optionsQueryContext={globalFilterContext}
      />,
    );

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('机房')).not.toBeNull();
    const label = within(dialog).getByText('组件内切换');
    const item = label.closest('.ant-form-item');
    const toggle = within(item as HTMLElement).getByRole('switch');
    expect((toggle as HTMLButtonElement).disabled).toBe(true);
    expect(toggle.getAttribute('aria-checked')).toBe('false');
    expect(within(dialog).queryByText('局部选项依赖本卡其它局部值和已应用的全局筛选')).toBeNull();

    await user.click(within(dialog).getByRole('button', { name: /确\s*认/ }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalled());
    const saved = onConfirm.mock.calls[0]?.[0];
    expect(saved.componentSwitch).toBeUndefined();
    expect(saved.optionsSource.queryParams.room_id).toEqual({ ref: 'site_id__string' });
  });

  it('auto previews when all query params are filled fixed values', async () => {
    getDataSourceList.mockResolvedValue([deviceSource]);
    getSourceDataByApiId.mockResolvedValue({ data: [{ id: 1, name: 'auto' }] });
    render(
      <ParamInputConfigEditor
        open
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 9,
            valueField: 'id',
            labelField: 'name',
            queryParams: {
              zone_id: 7,
              area_code: 'from-source',
              note: 'custom',
            },
          },
        }}
      />,
    );

    await waitFor(() => expect(getSourceDataByApiId).toHaveBeenCalledTimes(1));
    expect(getSourceDataByApiId).toHaveBeenCalledWith(9, {
      zone_id: 7,
      area_code: 'from-source',
      note: 'custom',
    });
  });

  it('does not auto preview when a query param is a reference', async () => {
    getDataSourceList.mockResolvedValue([deviceSource]);
    getSourceDataByApiId.mockResolvedValue({ data: [{ id: 1, name: 'no-auto' }] });
    render(
      <ParamInputConfigEditor
        open
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 9,
            valueField: 'id',
            labelField: 'name',
            queryParams: {
              room_id: { ref: 'site_id' },
              zone_id: 7,
            },
          },
        }}
        optionsQueryContext={globalFilterContext}
      />,
    );

    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(within(dialog).findByText('机房')).resolves.not.toBeNull());
    expect(getSourceDataByApiId).not.toHaveBeenCalled();
  });

  it('keeps an over-long instance ref in the dropdown and rejects it on confirm', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const errorSpy = vi.spyOn(message, 'error').mockImplementation(() => ({}) as never);
    getDataSourceList.mockResolvedValue([
      {
        id: 11,
        name: '明细列表',
        params: [{ name: 'instance_id', type: 'string', alias_name: '实例' }],
        field_schema: [
          { key: 'id', title: '编号', value_type: 'string' },
          { key: 'name', title: '名称', value_type: 'string' },
        ],
      },
    ]);
    render(
      <ParamInputConfigEditor
        open
        editingParamName="detail_id"
        onCancel={vi.fn()}
        onConfirm={onConfirm}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 11,
            valueField: 'id',
            labelField: 'name',
            queryParams: { instance_id: { ref: 'instance_id__string' } },
          },
        }}
        optionsQueryContext={{
          scope: 'component',
          self: { key: 'detail_id', label: '明细' },
          componentParams: [
            { name: 'detail_id', label: '明细', type: 'string', filterType: 'params' },
          ],
          globalFilters: [
            { id: 'object_id__string', key: 'object_id', label: '监控对象', type: 'string' },
            {
              id: 'metric_id__string',
              key: 'metric_id',
              label: '指标',
              type: 'string',
              queryParams: { object_id: { ref: 'object_id__string' } },
            },
            {
              id: 'instance_id__string',
              key: 'instance_id',
              label: '实例',
              type: 'string',
              queryParams: { metric_id: { ref: 'metric_id__string' } },
            },
          ],
        }}
      />,
    );

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('全局筛选 · 实例')).not.toBeNull();
    await user.click(within(dialog).getByText('全局筛选 · 实例'));
    expect(await screen.findByText('全局筛选 · 监控对象')).not.toBeNull();
    expect(screen.getByText('全局筛选 · 指标')).not.toBeNull();

    await user.click(within(dialog).getByRole('button', { name: /确\s*认/ }));
    const depthMessage = '查询入参依赖超过 3 级：明细 → 实例 → 指标 → 监控对象';
    await waitFor(() => expect(errorSpy).toHaveBeenCalledWith(depthMessage));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(within(dialog).queryByText(/查询入参依赖超过/)).toBeNull();
    expect(within(dialog).queryByText(/__string/)).toBeNull();
    expect(within(dialog).getByText('全局筛选 · 实例')).not.toBeNull();
    errorSpy.mockRestore();
  });

  it('keeps a same-name component param ref and still stores a chosen filter id', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    getDataSourceList.mockResolvedValue([
      {
        id: 12,
        name: '指标列表',
        params: [{ name: 'room_id', type: 'string', alias_name: '机房' }],
        field_schema: [
          { key: 'id', title: '编号', value_type: 'string' },
          { key: 'name', title: '名称', value_type: 'string' },
        ],
      },
    ]);
    const optionsQueryContext = {
      scope: 'component' as const,
      self: { key: 'metric_id' },
      componentParams: [
        { name: 'metric_id', label: '指标', type: 'string', filterType: 'params' },
        { name: 'object_id', label: '监控对象', type: 'string', filterType: 'params', value: 'local-object' },
      ],
      globalFilters: [
        { id: 'object_id__string', key: 'object_id', label: '监控对象', type: 'string', enabled: true },
      ],
    };
    const editor = (ref: string) => (
      <ParamInputConfigEditor
        open
        editingParamName="metric_id"
        onCancel={vi.fn()}
        onConfirm={onConfirm}
        optionsQueryContext={optionsQueryContext}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 12,
            valueField: 'id',
            labelField: 'name',
            queryParams: { room_id: { ref } },
          },
        }}
      />
    );

    const view = render(editor('object_id'));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('组件参数 · 监控对象')).not.toBeNull();
    expect(within(dialog).queryByText('全局筛选 · 监控对象')).toBeNull();
    await user.click(within(dialog).getByRole('button', { name: /确\s*认/ }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    expect(onConfirm.mock.calls[0][0].optionsSource.queryParams).toEqual({
      room_id: { ref: 'object_id' },
    });

    view.rerender(editor('object_id'));
    const reopened = await screen.findByRole('dialog');
    expect(await within(reopened).findByText('组件参数 · 监控对象')).not.toBeNull();
    expect(within(reopened).queryByText('全局筛选 · 监控对象')).toBeNull();

    await user.click(within(reopened).getByText('组件参数 · 监控对象'));
    await user.click(await screen.findByText('全局筛选 · 监控对象'));
    onConfirm.mockClear();
    await user.click(within(reopened).getByRole('button', { name: /确\s*认/ }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    expect(onConfirm.mock.calls[0][0].optionsSource.queryParams).toEqual({
      room_id: { ref: 'object_id__string' },
    });

    view.rerender(editor('object_id__string'));
    const filterView = await screen.findByRole('dialog');
    expect(await within(filterView).findByText('全局筛选 · 监控对象')).not.toBeNull();
    expect(within(filterView).queryByText('组件参数 · 监控对象')).toBeNull();
  });

  it('accepts a global filter id while another param already references the row being edited', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const errorSpy = vi.spyOn(message, 'error').mockImplementation(() => ({}) as never);
    getDataSourceList.mockResolvedValue([
      {
        id: 13,
        name: '指标列表',
        params: [{ name: 'object_id', type: 'string', alias_name: '监控对象' }],
        field_schema: [
          { key: 'id', title: '编号', value_type: 'string' },
          { key: 'name', title: '名称', value_type: 'string' },
        ],
      },
    ]);
    render(
      <ParamInputConfigEditor
        open
        editingParamName="metric_id"
        onCancel={vi.fn()}
        onConfirm={onConfirm}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 13,
            valueField: 'id',
            labelField: 'name',
            queryParams: { object_id: { ref: 'object_id__string' } },
          },
        }}
        optionsQueryContext={{
          scope: 'component',
          self: { key: 'metric_id', label: '指标' },
          componentParams: [
            { name: 'object_id', label: '监控对象', type: 'string', filterType: 'params' },
            { name: 'metric_id', label: '指标', type: 'string', filterType: 'params' },
            {
              name: 'instance_id',
              label: '实例',
              type: 'string',
              filterType: 'params',
              queryParams: { metric_id: { ref: 'metric_id' } },
            },
          ],
          globalFilters: [
            { id: 'object_id__string', key: 'object_id', label: '监控对象', type: 'string' },
            { id: 'metric_id__string', key: 'metric_id', label: '指标', type: 'string' },
          ],
        }}
      />,
    );

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('全局筛选 · 监控对象')).not.toBeNull();
    await user.click(within(dialog).getByRole('button', { name: /确\s*认/ }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    expect(onConfirm.mock.calls[0][0].optionsSource.queryParams).toEqual({
      object_id: { ref: 'object_id__string' },
    });
    expect(errorSpy).not.toHaveBeenCalledWith('同名筛选有多条，请按来源选择具体一项');
    errorSpy.mockRestore();
  });

  it('accepts the global filter that shares the edited component param name', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const errorSpy = vi.spyOn(message, 'error').mockImplementation(() => ({}) as never);
    getDataSourceList.mockResolvedValue([
      {
        id: 13,
        name: '指标列表',
        params: [{ name: 'upstream_id', type: 'string', alias_name: '上游' }],
        field_schema: [
          { key: 'id', title: '编号', value_type: 'string' },
          { key: 'name', title: '名称', value_type: 'string' },
        ],
      },
    ]);
    render(
      <ParamInputConfigEditor
        open
        editingParamName="metric_id"
        onCancel={vi.fn()}
        onConfirm={onConfirm}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 13,
            valueField: 'id',
            labelField: 'name',
            queryParams: { upstream_id: { ref: 'metric_id__string' } },
          },
        }}
        optionsQueryContext={{
          scope: 'component',
          self: { key: 'metric_id', label: '指标' },
          componentParams: [
            { name: 'metric_id', label: '指标', type: 'string', filterType: 'params' },
            {
              name: 'instance_id',
              label: '实例',
              type: 'string',
              filterType: 'params',
              queryParams: { metric_id: { ref: 'metric_id' } },
            },
          ],
          globalFilters: [
            { id: 'metric_id__string', key: 'metric_id', label: '指标', type: 'string' },
          ],
        }}
      />,
    );

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('全局筛选 · 指标')).not.toBeNull();
    await user.click(within(dialog).getByRole('button', { name: /确\s*认/ }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    expect(onConfirm.mock.calls[0][0].optionsSource.queryParams).toEqual({
      upstream_id: { ref: 'metric_id__string' },
    });
    expect(errorSpy).not.toHaveBeenCalledWith('同名筛选有多条，请按来源选择具体一项');
    errorSpy.mockRestore();
  });

  it('rejects a bare name when two filters share a key and accepts a concrete filter id', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const errorSpy = vi.spyOn(message, 'error').mockImplementation(() => ({}) as never);
    getDataSourceList.mockResolvedValue([
      {
        id: 14,
        name: '设备列表',
        params: [{ name: 'room_id', type: 'string', alias_name: '机房' }],
        field_schema: [
          { key: 'id', title: '编号', value_type: 'string' },
          { key: 'name', title: '名称', value_type: 'string' },
        ],
      },
    ]);
    const optionsQueryContext = {
      scope: 'component' as const,
      self: { key: 'detail_id' },
      componentParams: [
        { name: 'detail_id', label: '明细', type: 'string', filterType: 'params' },
      ],
      globalFilters: [
        {
          id: 'site_id__string__aaaaaaaa',
          key: 'site_id',
          label: '机房',
          type: 'string',
          sourceHint: 'cmdb/rooms',
        },
        {
          id: 'site_id__string__bbbbbbbb',
          key: 'site_id',
          label: '机房',
          type: 'string',
          sourceHint: 'monitor/rooms',
        },
      ],
    };
    const editor = (ref: string) => (
      <ParamInputConfigEditor
        open
        editingParamName="detail_id"
        onCancel={vi.fn()}
        onConfirm={onConfirm}
        optionsQueryContext={optionsQueryContext}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 14,
            valueField: 'id',
            labelField: 'name',
            queryParams: { room_id: { ref } },
          },
        }}
      />
    );

    const view = render(editor('site_id'));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('机房')).not.toBeNull();
    await user.click(within(dialog).getByRole('button', { name: /确\s*认/ }));
    await waitFor(() => expect(errorSpy).toHaveBeenCalledWith('同名筛选有多条，请按来源选择具体一项'));
    expect(onConfirm).not.toHaveBeenCalled();

    errorSpy.mockClear();
    view.rerender(editor('site_id__string__aaaaaaaa'));
    const reopened = await screen.findByRole('dialog');
    expect(await within(reopened).findByText('全局筛选 · 机房 · cmdb/rooms')).not.toBeNull();
    await user.click(within(reopened).getByRole('button', { name: /确\s*认/ }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    expect(onConfirm.mock.calls[0][0].optionsSource.queryParams).toEqual({
      room_id: { ref: 'site_id__string__aaaaaaaa' },
    });
    expect(errorSpy).not.toHaveBeenCalledWith('同名筛选有多条，请按来源选择具体一项');
    errorSpy.mockRestore();
  });

  it('scrolls the reference dropdown instead of growing with every option', async () => {
    const user = userEvent.setup();
    getDataSourceList.mockResolvedValue([
      {
        id: 11,
        name: '明细列表',
        params: [{ name: 'instance_id', type: 'string', alias_name: '实例' }],
        field_schema: [
          { key: 'id', title: '编号', value_type: 'string' },
          { key: 'name', title: '名称', value_type: 'string' },
        ],
      },
    ]);
    render(
      <ParamInputConfigEditor
        open
        editingParamName="detail_id"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 11,
            valueField: 'id',
            labelField: 'name',
            queryParams: { instance_id: { ref: 'upstream_0' } },
          },
        }}
        optionsQueryContext={{
          scope: 'component',
          self: { key: 'detail_id', label: '明细' },
          componentParams: [
            { name: 'detail_id', label: '明细', type: 'string' },
            ...Array.from({ length: 12 }, (_, index) => ({
              name: `upstream_${index}`,
              label: `上游${index}`,
              type: 'string',
            })),
          ],
        }}
      />,
    );

    const dialog = await screen.findByRole('dialog');
    await user.click(await within(dialog).findByText('组件参数 · 上游0'));
    const holder = await waitFor(() => {
      const node = document.querySelector('.rc-virtual-list-holder');
      expect(node).not.toBeNull();
      return node as HTMLElement;
    });
    expect(holder.style.maxHeight).toBe('256px');
    expect(holder.style.overflowY === 'auto' || holder.style.overflowY === 'hidden').toBe(true);
  });

  it('does not auto preview when a fixed value is empty', async () => {
    getDataSourceList.mockResolvedValue([deviceSource]);
    getSourceDataByApiId.mockResolvedValue({ data: [{ id: 1, name: 'no-auto' }] });
    render(
      <ParamInputConfigEditor
        open
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 9,
            valueField: 'id',
            labelField: 'name',
            queryParams: {
              zone_id: 7,
              area_code: '',
            },
          },
        }}
      />,
    );

    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(within(dialog).findByDisplayValue('7')).resolves.not.toBeNull());
    expect(getSourceDataByApiId).not.toHaveBeenCalled();
  });

  it('debounces fixed-value preview keystrokes and stops when a value is cleared', async () => {
    const filledSource = {
      id: 21,
      name: '已填来源',
      params: [
        { name: 'room_id', type: 'string', alias_name: '机房', value: 'room-1' },
        { name: 'zone_id', type: 'number', alias_name: '区域', value: 3 },
      ],
      field_schema: [
        { key: 'id', title: '编号', value_type: 'string' },
        { key: 'name', title: '名称', value_type: 'string' },
      ],
    };
    const pending: Array<(value: unknown) => void> = [];
    getDataSourceList.mockResolvedValue([filledSource]);
    getSourceDataByApiId.mockImplementation(() => new Promise((resolve) => {
      pending.push(resolve);
    }));
    render(
      <ParamInputConfigEditor
        open
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
        value={{
          control: 'select',
          optionsSource: {
            type: 'dynamic',
            sourceId: 21,
            valueField: 'id',
            labelField: 'name',
            queryParams: {
              room_id: 'room-1',
              zone_id: 3,
            },
          },
        }}
      />,
    );

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByDisplayValue('room-1')).not.toBeNull();
    await waitFor(() => expect(getSourceDataByApiId).toHaveBeenCalledTimes(1));
    expect(getSourceDataByApiId).toHaveBeenCalledWith(21, {
      room_id: 'room-1',
      zone_id: 3,
    });
    pending[0]?.({ data: [{ id: 1, name: 'kept' }] });
    await act(async () => {
      await Promise.resolve();
    });

    const room = within(dialog).getByDisplayValue('room-1');
    fireEvent.change(room, { target: { value: 'room-12' } });
    fireEvent.change(room, { target: { value: 'room-123' } });
    expect(within(dialog).getByDisplayValue('room-123')).not.toBeNull();
    expect(getSourceDataByApiId).toHaveBeenCalledTimes(1);

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 200));
    });
    expect(getSourceDataByApiId).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(getSourceDataByApiId).toHaveBeenCalledTimes(2));
    expect(getSourceDataByApiId).toHaveBeenLastCalledWith(21, {
      room_id: 'room-123',
      zone_id: 3,
    });

    fireEvent.change(within(dialog).getByDisplayValue('room-123'), { target: { value: '' } });
    expect(within(dialog).getAllByRole('textbox').some((input) => (
      (input as HTMLInputElement).value === ''
    ))).toBe(true);
    pending[pending.length - 1]?.({ data: [{ secret_col: 'nope' }] });
    await act(async () => {
      await Promise.resolve();
    });
    expect(within(dialog).queryByRole('columnheader', { name: 'secret_col' })).toBeNull();
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 350));
    });
    expect(getSourceDataByApiId).toHaveBeenCalledTimes(2);
  });
});
