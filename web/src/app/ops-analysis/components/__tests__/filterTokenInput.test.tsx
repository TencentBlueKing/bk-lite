import React, { useState } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfigProvider } from 'antd';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { FilterTokenInput } from '@/app/ops-analysis/components/filterTokenInput';
import type { UnifiedFilterDefinition } from '@/app/ops-analysis/types/dashBoard';

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
});

afterEach(cleanup);

const biz: UnifiedFilterDefinition = {
  id: 'biz__string',
  key: 'biz',
  name: '业务',
  type: 'string',
  order: 1,
  enabled: true,
};

const disabledBiz: UnifiedFilterDefinition = {
  ...biz,
  id: 'biz__number',
  type: 'number',
  name: '业务数',
  enabled: false,
  order: 2,
};

const translate = (
  key: string,
  fallback?: string,
  values?: Record<string, string | number>,
) => {
  if (key === 'dashboard.filterTokenHint') return '输入 $ 插入筛选';
  if (key === 'dashboard.filterTokenSeparator') return '、';
  if (key === 'dashboard.filterTokenUnmatched' && values) {
    return `${values.tokens} 未匹配到筛选项`;
  }
  return fallback ?? key;
};

const Harness = () => {
  const [value, setValue] = useState('');
  return (
    <FilterTokenInput
      t={translate}
      value={value}
      onChange={setValue}
      definitions={[biz, disabledBiz]}
    />
  );
};

describe('FilterTokenInput', () => {
  it('输入 $ 后插入启用筛选的变量，提示只在聚焦时挂在输入框下方', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const hint = screen.getByText('输入 $ 插入筛选');
    expect(hint.className).toContain('hidden');
    expect(hint.className).toContain('group-focus-within:block');
    expect(hint.parentElement?.className).toContain('flex-col');
    await user.type(screen.getByRole('textbox'), '$');

    const option = await screen.findByRole('option', { name: '业务$biz$ · text' });
    expect(option.textContent).not.toContain('文本');
    expect(option.textContent).not.toContain('（');
    expect(screen.queryByRole('option', { name: /业务数/ })).toBeNull();
    await user.click(option);

    expect(screen.getByRole('textbox')).toHaveProperty('value', '$biz$');
  });

  it('没有启用筛选时不提示，输入 $ 也不打开菜单', async () => {
    const user = userEvent.setup();
    render(
      <FilterTokenInput
        t={translate}
        value=""
        definitions={[disabledBiz]}
      />,
    );

    expect(screen.queryByText('输入 $ 插入筛选')).toBeNull();
    await user.type(screen.getByRole('textbox'), '$');
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('把匹配不到的变量合并显示在输入框下方', () => {
    render(
      <FilterTokenInput
        t={translate}
        value="$gone$ $biz$ $gone$ $room:number$"
        definitions={[biz, disabledBiz]}
      />,
    );

    expect(screen.getByRole('status').textContent).toBe('$gone$、$room:number$ 未匹配到筛选项');
  });

  it('补上变量结尾的 $ 只关闭菜单，不再当作新的 $', async () => {
    const user = userEvent.setup();
    render(
      <ConfigProvider theme={{ token: { motion: false } }}>
        <Harness />
      </ConfigProvider>,
    );
    const input = screen.getByRole('textbox');

    await user.type(input, '$biz$');

    expect(input).toHaveProperty('value', '$biz$');
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('菜单关掉之后，变量结尾的 $ 不再打开新菜单', async () => {
    const user = userEvent.setup();
    render(
      <ConfigProvider theme={{ token: { motion: false } }}>
        <Harness />
      </ConfigProvider>,
    );
    const input = screen.getByRole('textbox');

    await user.type(input, '$biz');
    expect(await screen.findByRole('listbox')).toBeTruthy();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).toBeNull();

    await user.type(input, '$');

    expect(input).toHaveProperty('value', '$biz$');
    expect(screen.queryByRole('listbox')).toBeNull();
  });

  it('筛选下拉和交互下拉都只在左侧显示名称，右侧用英文类型', async () => {
    const user = userEvent.setup();
    const department: UnifiedFilterDefinition = {
      id: 'department__string',
      key: 'department',
      name: '使用部门',
      type: 'string',
      order: 1,
      enabled: true,
    };
    const count: UnifiedFilterDefinition = {
      ...department,
      id: 'count__number',
      key: 'count',
      name: '数量',
      type: 'number',
      order: 2,
    };
    const range: UnifiedFilterDefinition = {
      ...department,
      id: 'range__timeRange',
      key: 'range',
      name: '时间范围',
      type: 'timeRange',
      order: 3,
    };
    const day: UnifiedFilterDefinition = {
      ...department,
      id: 'day__dateRange',
      key: 'day',
      name: '日期',
      type: 'dateRange',
      order: 4,
    };
    const { unmount } = render(
      <FilterTokenInput
        t={translate}
        value=""
        definitions={[department, count, range, day]}
      />,
    );

    await user.type(screen.getByRole('textbox'), '$');
    expect(screen.queryByText('筛选条件')).toBeNull();
    const departmentOption = screen.getByRole('option', { name: '使用部门$department$ · text' });
    expect(departmentOption.querySelector('span.shrink-0')?.textContent).toBe('使用部门');
    const departmentMeta = departmentOption.querySelector('span.truncate');
    expect(departmentMeta?.textContent).toBe('$department$ · text');
    expect(departmentMeta?.className).toContain('text-right');
    expect(departmentMeta?.className).toContain('max-w-64');
    expect(departmentMeta?.className).toContain('text-(--color-text-3)');
    expect(screen.getByRole('option', { name: '数量$count$ · number' })).toBeTruthy();
    expect(screen.getByRole('option', { name: '时间范围$range$ · timeRange' })).toBeTruthy();
    expect(screen.getByRole('option', { name: '日期$day$ · dateRange' })).toBeTruthy();
    unmount();

    render(
      <FilterTokenInput
        t={translate}
        value=""
        variables={[
          { token: '$department$', label: '使用部门', group: '筛选条件', valueType: 'text' },
          { token: '$__series.name$', label: '名称', group: '数据点', example: 'up' },
          { token: '$__value.numeric$', label: '数值', group: '数据点', example: '1' },
          { token: '$__value.time$', label: '时间', group: '数据点' },
          { token: '$__data.fields.instance_count$', label: 'instance_count', group: '数据字段', example: '12' },
          { token: '$__data.fields.created_at$', label: 'created_at', group: '数据字段', example: '2025-10-15T00:00:00.000Z' },
          { token: '$__data.fields.note$', label: 'note', group: '数据字段' },
          {
            token: '$__data.fields.very_long_field_name_that_should_truncate$',
            label: '长字段',
            group: '数据字段',
            example: 'kept',
          },
        ]}
      />,
    );

    await user.type(screen.getByRole('textbox'), '$');
    expect(screen.getByText('筛选条件')).toBeTruthy();
    expect(screen.getByText('数据点')).toBeTruthy();
    expect(screen.getByText('数据字段')).toBeTruthy();

    const nameOption = screen.getByRole('option', { name: '名称$__series.name$ · text' });
    expect(nameOption.textContent).not.toContain('up');
    expect(screen.getByRole('option', { name: '数值$__value.numeric$ · number' }).textContent).not.toContain('1');
    expect(screen.getByRole('option', { name: '时间$__value.time$ · time' })).toBeTruthy();
    expect(screen.getByRole('option', { name: 'instance_count$__data.fields.instance_count$ · number' }).textContent).not.toContain('12');
    expect(screen.getByRole('option', { name: 'created_at$__data.fields.created_at$ · time' })).toBeTruthy();
    const unknown = screen.getByRole('option', { name: 'note$__data.fields.note$' });
    expect(unknown.textContent).toBe('note$__data.fields.note$');
    const longOption = screen.getByRole('option', { name: /长字段/ });
    const longMeta = longOption.querySelector('span.truncate');
    expect(longMeta?.className).toContain('truncate');
    expect(longMeta?.className).toContain('max-w-64');
    expect(longOption.querySelector('span.shrink-0')?.className).toContain('shrink-0');
    expect(longMeta?.textContent).not.toContain('kept');
  });

  it('只有一组时也显示分组标题', async () => {
    const user = userEvent.setup();
    render(
      <FilterTokenInput
        t={translate}
        value=""
        variables={[
          { token: '$__series.name$', label: '系列', group: '数据点', example: 'cpu' },
          { token: '$__value.numeric$', label: '数值', group: '数据点', example: '1' },
        ]}
      />,
    );

    await user.type(screen.getByRole('textbox'), '$');
    expect(screen.getByText('数据点')).toBeTruthy();
    expect(screen.getAllByRole('option')).toHaveLength(2);
  });

  it('组字过程中的回车留给输入法，不插入高亮变量', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByRole('textbox');

    await user.type(input, '$');
    expect(await screen.findByRole('listbox')).toBeTruthy();

    fireEvent.keyDown(input, { key: 'Enter', isComposing: true });
    expect(input).toHaveProperty('value', '$');
    expect(screen.getByRole('listbox')).toBeTruthy();

    fireEvent.keyDown(input, { key: 'Enter', keyCode: 229 });
    expect(input).toHaveProperty('value', '$');

    fireEvent.keyDown(input, { key: 'ArrowDown', keyCode: 229 });
    expect(screen.getByRole('option', { name: '业务$biz$ · text' }).getAttribute('aria-selected')).toBe('true');
  });
});
