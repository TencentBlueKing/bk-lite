import React, { useState } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import LogQueryInput from '..';

const getFieldValues = vi.fn();

vi.mock('@/app/log/api/integration', () => ({
  default: () => ({ getFieldValues })
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key })
}));

const ControlledInput = ({
  logGroups = ['group-a'],
  fields = ['host.name', 'host.os.family', 'level']
}: {
  logGroups?: React.Key[];
  fields?: string[];
}) => {
  const [value, setValue] = useState('');
  return (
    <LogQueryInput
      value={value}
      onChange={setValue}
      availableFields={fields}
      logGroups={logGroups}
      timeRange={{ mode: 'absolute', start: 1000, end: 2000 }}
      placeholder="query-input"
      allowClear
    />
  );
};

describe('LogQueryInput', () => {
  beforeEach(() => {
    getFieldValues.mockReset();
    getFieldValues.mockResolvedValue({ values: [] });
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn()
    }));
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      }
    );
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('聚焦空片段时展示字段，并在选择后补充冒号', async () => {
    const user = userEvent.setup();
    render(<ControlledInput />);

    const input = screen.getByPlaceholderText('query-input') as HTMLInputElement;
    await user.click(input);

    const hostOptions = screen.getAllByText('host.name');
    expect(hostOptions.length).toBeGreaterThan(0);
    await user.click(hostOptions.at(-1)!);

    expect(input.value).toBe('host.name:');
  });

  it('支持用键盘选择字段候选', async () => {
    const user = userEvent.setup();
    render(<ControlledInput />);

    const input = screen.getByPlaceholderText('query-input') as HTMLInputElement;
    await user.click(input);
    await user.keyboard('{Enter}');

    expect(input.value).toBe('host.name:');
  });

  it('Tab 也可以选中当前高亮的字段候选', async () => {
    const user = userEvent.setup();
    render(<ControlledInput />);

    const input = screen.getByPlaceholderText('query-input') as HTMLInputElement;
    await user.click(input);
    await user.keyboard('{Tab}');

    expect(input.value).toBe('host.name:');
  });

  it('传入 onPressEnter 时回车触发搜索而不是选中候选', async () => {
    const user = userEvent.setup();
    const onPressEnter = vi.fn();
    const SearchInput = () => {
      const [value, setValue] = useState('');
      return (
        <LogQueryInput
          value={value}
          onChange={setValue}
          onPressEnter={onPressEnter}
          availableFields={['host.name', 'level']}
          logGroups={['group-a']}
          timeRange={{ mode: 'absolute', start: 1000, end: 2000 }}
          placeholder="query-input"
        />
      );
    };
    render(<SearchInput />);

    const input = screen.getByPlaceholderText('query-input') as HTMLInputElement;
    await user.click(input);
    await user.keyboard('{Enter}');

    expect(onPressEnter).toHaveBeenCalledTimes(1);
    expect(input.value).toBe('');
  });

  it('方向键高亮的字段与回车选中的字段一致', async () => {
    const user = userEvent.setup();
    render(<ControlledInput />);

    const input = screen.getByPlaceholderText('query-input') as HTMLInputElement;
    await user.click(input);
    fireEvent.keyDown(input, {
      key: 'ArrowDown',
      code: 'ArrowDown',
      keyCode: 40,
      which: 40
    });
    await user.keyboard('{Enter}');

    expect(input.value).toBe('host.os.family:');
  });

  it('方向键高亮的字段与 Tab 选中的字段一致', async () => {
    const user = userEvent.setup();
    render(<ControlledInput />);

    const input = screen.getByPlaceholderText('query-input') as HTMLInputElement;
    await user.click(input);
    fireEvent.keyDown(input, {
      key: 'ArrowDown',
      code: 'ArrowDown',
      keyCode: 40,
      which: 40
    });
    await user.keyboard('{Tab}');

    expect(input.value).toBe('host.os.family:');
  });

  it('输入 message 时不会吞掉最后一个字母', async () => {
    const user = userEvent.setup();
    render(<ControlledInput fields={['message', 'host']} />);

    const input = screen.getByPlaceholderText('query-input') as HTMLInputElement;
    await user.click(input);
    await user.type(input, 'message');

    expect(['message', 'message:']).toContain(input.value);
  });

  it('字段候选中不展示内部时间与流字段', async () => {
    const user = userEvent.setup();
    render(
      <ControlledInput
        fields={['@timestamp', '_stream_id', '_stream', 'host.name', 'message']}
      />
    );

    const input = screen.getByPlaceholderText('query-input') as HTMLInputElement;
    await user.click(input);

    expect(screen.queryByText('@timestamp')).toBeNull();
    expect(screen.queryByText('_stream_id')).toBeNull();
    expect(screen.queryByText('_stream')).toBeNull();
    expect(screen.getAllByText('host.name').length).toBeGreaterThan(0);
  });

  it('选择 @metadata 字段时会加上 LogsQL 引号', async () => {
    const user = userEvent.setup();
    render(<ControlledInput fields={['@metadata.beat', 'host.name']} />);

    const input = screen.getByPlaceholderText('query-input') as HTMLInputElement;
    await user.click(input);
    await user.click(screen.getAllByText('@metadata.beat').at(-1)!);

    expect(input.value).toBe('"@metadata.beat":');
  });

  it('按当前日志分组和时间范围加载字段值并安全插入', async () => {
    vi.useFakeTimers();
    getFieldValues.mockResolvedValue({
      values: [
        { value: 'api "primary"', hits: 8 },
        { value: 'worker', hits: 3 }
      ]
    });
    render(<ControlledInput />);

    const input = screen.getByPlaceholderText('query-input') as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: 'host.name:' } });
    fireEvent.input(input, {
      target: { value: 'host.name:', selectionStart: 10 }
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
      await Promise.resolve();
    });
    expect(getFieldValues).toHaveBeenCalledTimes(1);
    expect(getFieldValues.mock.calls[0][0]).toEqual({
      filed: 'host.name',
      start_time: new Date(1000).toISOString(),
      end_time: new Date(2000).toISOString(),
      limit: 50,
      log_groups: ['group-a']
    });

    fireEvent.click(screen.getAllByText('api "primary"').at(-1)!);
    expect(input.value).toBe('host.name:"api \\"primary\\""');
  });

  it('没有日志分组时保留自由输入但不请求候选值', async () => {
    vi.useFakeTimers();
    render(<ControlledInput logGroups={[]} />);

    const input = screen.getByPlaceholderText('query-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'level:' } });
    fireEvent.input(input, {
      target: { value: 'level:', selectionStart: 6 }
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });

    expect(input.value).toBe('level:');
    expect(getFieldValues).not.toHaveBeenCalled();
  });

  it('日志分组变化时取消旧的字段值请求', async () => {
    vi.useFakeTimers();
    getFieldValues.mockImplementation(() => new Promise(() => undefined));
    const { rerender } = render(<ControlledInput logGroups={['group-a']} />);

    const input = screen.getByPlaceholderText('query-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'level:' } });
    fireEvent.input(input, {
      target: { value: 'level:', selectionStart: 6 }
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
    });
    const oldSignal = getFieldValues.mock.calls[0][1].signal as AbortSignal;

    rerender(<ControlledInput logGroups={['group-b']} />);

    expect(oldSignal.aborted).toBe(true);
  });
});
