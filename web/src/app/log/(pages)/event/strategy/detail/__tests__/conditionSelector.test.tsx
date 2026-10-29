import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

import ConditionFilter from '../conditionSelector';

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

afterEach(() => {
  cleanup();
});

describe('条件函数选择', () => {
  it('选择速率后不渲染字段，阈值可以输入小数', () => {
    const onChange = vi.fn();
    render(
      <ConditionFilter
        data={[{ func: 'count_rate', field: '_msg', op: '>', value: '' }]}
        fields={['service', '_msg']}
        term="or"
        onTermChange={vi.fn()}
        onChange={onChange}
      />
    );

    expect(screen.getAllByRole('combobox')).toHaveLength(2);
    expect(screen.queryByText('service')).toBeNull();
    expect(screen.queryByRole('radio', { name: 'log.event.compareKindAbsolute' })).toBeNull();
    expect(screen.queryByRole('radio', { name: 'log.event.compareKindDelta' })).toBeNull();
    expect(screen.queryByRole('radio', { name: 'log.event.compareKindPercent' })).toBeNull();
    expect(screen.getByText('log.event.countRateUnit')).toBeTruthy();

    fireEvent.change(screen.getAllByPlaceholderText('log.event.enterThreshold')[0], {
      target: { value: '0.5' },
    });
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ func: 'count_rate', field: '_msg', value: '0.5' }),
    ]);
  });

  it('选择变化量后显示上一窗提示', () => {
    render(
      <ConditionFilter
        data={[{ func: 'count_delta', field: '_msg', op: '>', value: '50' }]}
        fields={['service']}
        term="or"
        onTermChange={vi.fn()}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText('log.event.countDeltaTip')).toBeTruthy();
  });

  it('选择变化率后出现对照下拉和百分号', () => {
    render(
      <ConditionFilter
        data={[
          {
            func: 'count',
            field: '_msg',
            op: '>',
            value: '50',
            compare: { kind: 'percent', to: 'offset_24h' },
          },
        ]}
        fields={['service', '_msg']}
        term="or"
        onTermChange={vi.fn()}
        onChange={vi.fn()}
      />
    );

    expect(
      (screen.getByRole('radio', { name: 'log.event.compareKindPercent' }) as HTMLInputElement).checked
    ).toBe(true);
    expect(screen.getByText('log.event.compareOffsetHours')).toBeTruthy();
    expect(screen.getByLabelText('log.event.compareOffsetCountHour')).toBeTruthy();
    expect(screen.getByText('%')).toBeTruthy();
    expect(screen.getByText('log.event.percentTip')).toBeTruthy();
  });

  it('选择分位数后出现分位下拉，同时保留字段', () => {
    render(
      <ConditionFilter
        data={[
          {
            func: 'quantile',
            field: 'duration',
            op: '>',
            value: '2000',
            params: { quantile: 0.95 },
          },
        ]}
        fields={['duration']}
        term="or"
        onTermChange={vi.fn()}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText('P95')).toBeTruthy();
    expect(screen.getByText('duration')).toBeTruthy();
  });

  it('计数函数仍然渲染字段选择', () => {
    render(
      <ConditionFilter
        data={[{ func: 'count', field: null, op: null, value: '' }]}
        fields={['service']}
        term="or"
        onTermChange={vi.fn()}
        onChange={vi.fn()}
      />
    );

    expect(screen.getAllByRole('combobox')).toHaveLength(3);
    expect(screen.queryByLabelText('log.event.deleteCondition')).toBeNull();
  });

  it('选择占比后出现分子筛选、提示和百分号', () => {
    const onChange = vi.fn();
    render(
      <ConditionFilter
        data={[
          {
            func: 'ratio',
            field: '_msg',
            op: '>',
            value: '5',
            params: { filter: 'status:500' },
          },
        ]}
        fields={['service', '_msg']}
        term="or"
        onTermChange={vi.fn()}
        onChange={onChange}
      />
    );

    expect(screen.getByPlaceholderText('log.event.ratioFilter')).toBeTruthy();
    expect(screen.getByDisplayValue('status:500')).toBeTruthy();
    expect(screen.getByText('log.event.ratioFilterTip')).toBeTruthy();
    expect(screen.getByText('%')).toBeTruthy();
    expect(screen.queryByText('service')).toBeNull();

    fireEvent.change(screen.getByPlaceholderText('log.event.ratioFilter'), {
      target: { value: 'message:ERR' },
    });
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({
        func: 'ratio',
        field: '_msg',
        params: { filter: 'message:ERR' },
      }),
    ]);
  });

  it('栏头切换全部条件', () => {
    const onTermChange = vi.fn();
    render(
      <ConditionFilter
        data={[{ func: 'count', field: '_msg', op: '>', value: '' }]}
        fields={['service']}
        term="or"
        onTermChange={onTermChange}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText('log.event.termAny')).toBeTruthy();
    expect(screen.getByText('log.event.termAll')).toBeTruthy();
    fireEvent.click(screen.getByRole('radio', { name: 'log.event.termAll' }));
    expect(onTermChange).toHaveBeenCalledWith('and');
  });

  it('多条条件时每条都可删除，并显示序号', () => {
    const first = { func: 'count', field: 'level', op: '>', value: '100' };
    const second = { func: 'avg', field: 'duration', op: '>', value: '20' };
    const onChange = vi.fn();
    render(
      <ConditionFilter
        data={[first, second]}
        fields={['level', 'duration']}
        term="or"
        onTermChange={vi.fn()}
        onChange={onChange}
      />
    );

    expect(
      screen.getAllByLabelText('log.event.conditionIndex').map((node) => node.textContent)
    ).toEqual(['1', '2']);
    const deleteButtons = screen.getAllByLabelText('log.event.deleteCondition');
    expect(deleteButtons).toHaveLength(2);
    fireEvent.click(deleteButtons[0]);
    expect(onChange).toHaveBeenCalledWith([second]);
  });

  it('比较符收起和下拉都只显示中文', () => {
    render(
      <ConditionFilter
        data={[{ func: 'count', field: '_msg', op: '=', value: '1' }]}
        fields={['_msg']}
        term="or"
        onTermChange={vi.fn()}
        onChange={vi.fn()}
      />
    );

    const selected = screen.getByText('log.equalto');
    expect(selected.closest('.ant-select-selection-item')).toBeTruthy();
    expect(selected.closest('.ant-select-selection-item')?.textContent).toBe('log.equalto');

    fireEvent.mouseDown(selected.closest('.ant-select')!.querySelector('.ant-select-selector')!);
    const optionText = (label: string) =>
      screen.getAllByText(label).find((node) => node.closest('.ant-select-item-option'))?.closest('.ant-select-item-option')?.textContent;
    expect(optionText('log.equalto')).toBe('log.equalto');
    expect(optionText('log.notequalTo')).toBe('log.notequalTo');
    expect(optionText('log.moreThan')).toBe('log.moreThan');
    expect(optionText('log.lessThan')).toBe('log.lessThan');
    expect(
      [...document.querySelectorAll('.ant-select-item-option')].map((node) => node.textContent)
    ).toEqual(['log.equalto', 'log.notequalTo', 'log.moreThan', 'log.lessThan']);
  });

  it('变化量和变化率不提供包括、不包括，并清掉已选的包括', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <ConditionFilter
        data={[{ func: 'count', field: 'level', op: 'in', value: 'error' }]}
        fields={['level']}
        term="or"
        onTermChange={vi.fn()}
        onChange={onChange}
      />
    );

    fireEvent.click(screen.getByRole('radio', { name: 'log.event.compareKindDelta' }));
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({
        op: null,
        compare: expect.objectContaining({ kind: 'delta' }),
      }),
    ]);

    rerender(
      <ConditionFilter
        data={[{ func: 'count', field: 'level', op: '>', value: '10', compare: { kind: 'percent', to: 'previous_window' } }]}
        fields={['level']}
        term="or"
        onTermChange={vi.fn()}
        onChange={onChange}
      />
    );
    fireEvent.mouseDown(screen.getByText('log.moreThan').closest('.ant-select')!.querySelector('.ant-select-selector')!);
    expect(
      [...document.querySelectorAll('.ant-select-item-option')].map((node) => node.textContent)
    ).toEqual(['log.equalto', 'log.notequalTo', 'log.moreThan', 'log.lessThan']);
  });

  it('点击添加条件时在末尾追加空条件', () => {
    const current = { func: 'count', field: '_msg', op: '>', value: '1' };
    const onChange = vi.fn();
    render(
      <ConditionFilter
        data={[current]}
        fields={['_msg']}
        term="or"
        onTermChange={vi.fn()}
        onChange={onChange}
      />
    );

    fireEvent.click(screen.getByText('log.event.addCondition'));
    expect(onChange).toHaveBeenCalledWith([
      current,
      { field: null, op: null, value: '' },
    ]);
  });

  it('变化率阈值是数字框，可以输入负数', () => {
    const onChange = vi.fn();
    render(
      <ConditionFilter
        data={[
          {
            func: 'count',
            field: '_msg',
            op: '>',
            value: '',
            compare: { kind: 'percent', to: 'previous_window' },
          },
        ]}
        fields={['_msg']}
        term="or"
        onTermChange={vi.fn()}
        onChange={onChange}
      />
    );

    expect(screen.getAllByRole('spinbutton')).toHaveLength(3);
    expect(screen.getByText('%')).toBeTruthy();
    fireEvent.change(screen.getAllByPlaceholderText('log.event.enterThreshold')[0], {
      target: { value: '-30' },
    });
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ value: '-30' }),
    ]);
  });

  it('新建计数当前值的运算符只有四个数值比较，阈值仍是文本框', () => {
    render(
      <ConditionFilter
        data={[{ func: 'count', field: null, op: null, value: '' }]}
        fields={['service']}
        term="or"
        onTermChange={vi.fn()}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByRole('textbox')).toBe(screen.getByPlaceholderText('log.event.enterThreshold'));
    expect(screen.queryByRole('spinbutton')).toBeNull();
    expect(screen.queryByLabelText('log.event.alarmLevel')).toBeNull();

    fireEvent.mouseDown(
      screen.getByText('log.event.selectCriteria').closest('.ant-select')!.querySelector('.ant-select-selector')!
    );
    expect(
      [...document.querySelectorAll('.ant-select-item-option')].map((node) => node.textContent)
    ).toEqual(['log.equalto', 'log.notequalTo', 'log.moreThan', 'log.lessThan']);
  });

  it('旧的包括条件在当前值下仍然回显', () => {
    render(
      <ConditionFilter
        data={[{ func: 'count', field: 'level', op: 'in', value: 'error' }]}
        fields={['level']}
        term="or"
        onTermChange={vi.fn()}
        onChange={vi.fn()}
      />
    );

    const selected = screen.getByText('log.include');
    expect(selected.closest('.ant-select-selection-item')).toBeTruthy();
    fireEvent.mouseDown(selected.closest('.ant-select')!.querySelector('.ant-select-selector')!);
    expect(
      [...document.querySelectorAll('.ant-select-item-option')].map((node) => node.textContent)
    ).toContain('log.include');
  });

  it('大于运算符并列三档阈值，留空的档不写入', () => {
    const onChange = vi.fn();
    render(
      <ConditionFilter
        data={[{ func: 'count', field: '_msg', op: '>', value: '12' }]}
        fields={['_msg']}
        term="or"
        onTermChange={vi.fn()}
        onChange={onChange}
      />
    );

    expect(screen.getAllByPlaceholderText('log.event.enterThreshold')).toHaveLength(3);
    expect(screen.getByText('log.event.warning')).toBeTruthy();
    expect(screen.getByText('log.event.error')).toBeTruthy();
    expect(screen.getByText('log.event.critical')).toBeTruthy();
    fireEvent.change(screen.getAllByPlaceholderText('log.event.enterThreshold')[1], {
      target: { value: '60' },
    });
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({
        value: '12',
        thresholds: [
          { level: 'warning', value: '12' },
          { level: 'error', value: '60' },
        ],
      }),
    ]);
  });

  it('等于的级别挂在阈值上，填写一档会清掉其他档', () => {
    const onChange = vi.fn();
    render(
      <ConditionFilter
        data={[{ func: 'count', field: 'level', op: '=', value: 'error' }]}
        fields={['level']}
        term="or"
        onTermChange={vi.fn()}
        onChange={onChange}
      />
    );

    const thresholds = screen.getAllByPlaceholderText('log.event.enterThreshold');
    expect(thresholds).toHaveLength(3);
    expect(screen.queryByRole('combobox', { name: 'log.event.alarmLevel' })).toBeNull();
    expect(screen.getByText('log.event.warning')).toBeTruthy();
    expect(screen.getByText('log.event.critical')).toBeTruthy();
    fireEvent.change(thresholds[2], { target: { value: 'fatal' } });
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({
        value: 'fatal',
        thresholds: [{ level: 'critical', value: 'fatal' }],
      }),
    ]);
  });
});
