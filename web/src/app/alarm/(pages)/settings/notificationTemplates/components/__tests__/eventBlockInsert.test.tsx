import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import EventBlockInsert from '../eventBlockInsert';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, _defaultMessage?: string, values?: Record<string, string | number>) => {
      if (!values) return key;
      return Object.entries(values).reduce(
        (text, [name, value]) => text.replace(`{${name}}`, String(value)),
        key,
      );
    },
  }),
}));

const catalog = {
  max_rows: 100,
  max_columns: 10,
  default_limit: 10,
  default_order: '-start_time',
  orders: [{ value: '-start_time', label: '发生时间 倒序' }],
  limits: [10, 'all'] as Array<number | 'all'>,
  fields: [
    { path: 'level', label: '事件级别' },
    { path: 'resource_name', label: '资源名称' },
  ],
  json_roots: [
    { root: 'tags', label: '事件标签' },
    { root: 'labels', label: '事件标记' },
    { root: 'enrichment', label: '富化数据' },
  ],
};

describe('插入事件表格', () => {
  it('点开 JSON 根之后才出现键名输入，并把手填路径插进声明', () => {
    const onApply = vi.fn();
    render(<EventBlockInsert catalog={catalog} source="" onApply={onApply} />);

    fireEvent.click(screen.getByText('settings.notificationTemplate.insertEventBlock'));
    expect(screen.queryByPlaceholderText('settings.notificationTemplate.eventBlockKeyPlaceholder')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /事件标签 tags/ }));
    fireEvent.change(screen.getByPlaceholderText('settings.notificationTemplate.eventBlockKeyPlaceholder'), {
      target: { value: 'alert' },
    });
    fireEvent.click(screen.getAllByText('settings.notificationTemplate.eventBlockAdd')[0]);

    expect(screen.getByDisplayValue(/tags\.alert/)).toBeTruthy();
    fireEvent.click(screen.getAllByText('settings.notificationTemplate.insertEventBlock').at(-1)!);
    expect(onApply).toHaveBeenCalledWith(expect.stringContaining('tags.alert as tags_alert'));
    expect(onApply.mock.calls[0][0]).not.toContain('format=');
  });

  it('正文里已有事件表格时按钮变蓝，并回显 JSON 列，声明可以改', () => {
    const onApply = vi.fn();
    const source = '{{@ events limit=all order=-start_time columns=level as 事件级别, tags.environment @}}';
    render(<EventBlockInsert catalog={catalog} source={source} onApply={onApply} />);

    const trigger = screen.getAllByRole('button', { name: 'settings.notificationTemplate.insertEventBlock' })[0];
    expect(trigger.className).toContain('ant-btn-primary');

    fireEvent.click(trigger);
    const snippet = screen.getByDisplayValue(/tags\.environment as tags_environment/);
    expect(snippet.getAttribute('readonly')).toBeNull();
    expect(screen.getByRole('button', { name: /事件标签 tags/ }).className).toContain('ant-btn-primary');

    fireEvent.change(snippet, { target: { value: (snippet as HTMLTextAreaElement).value.replace('tags_environment', '环境') } });
    fireEvent.click(screen.getAllByRole('button', { name: 'settings.notificationTemplate.insertEventBlock' }).at(-1)!);
    expect(onApply).toHaveBeenCalledWith(expect.stringContaining('tags.environment as 环境'));
  });
});
