import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { IntlProvider } from 'react-intl';
import { afterEach, expect, it, vi } from 'vitest';
import { TriggerMessageContent } from './trigger-message-content';

afterEach(cleanup);

function ContentEditor() {
  const [value, setValue] = useState('');
  return <IntlProvider locale="zh" messages={{
    'itsm.rule.triggerNotifyVariableTicketTitle': '工单标题',
    'itsm.rule.triggerNotifyVariableTicketLink': '工单详情链接',
  }}>
    <TriggerMessageContent ariaLabel="通知内容" value={value} onChange={setValue} />
  </IntlProvider>;
}

function input(textarea: HTMLTextAreaElement, value: string, key: string) {
  fireEvent.change(textarea, { target: { value } });
  textarea.setSelectionRange(value.length, value.length);
  fireEvent.keyUp(textarea, { key });
}

it('输入美元符号展示变量，可用中文名称搜索并按回车插入变量', async () => {
  render(<ContentEditor />);
  const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: '通知内容' });
  act(() => textarea.focus());
  input(textarea, '已提交 $', '$');
  expect(await screen.findByText('工单标题')).toBeTruthy();
  expect(screen.getByText('$ticket_link')).toBeTruthy();

  input(textarea, '已提交 $标题', '题');
  expect(screen.queryByText('$ticket_link')).toBeNull();
  fireEvent.keyDown(textarea, { key: 'Enter', keyCode: 13 });
  expect(textarea.value).toBe('已提交 $ticket_title ');
});

it('按变量标识缩小选项，点击后保留正文和标识', async () => {
  render(<ContentEditor />);
  const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: '通知内容' });
  act(() => textarea.focus());
  input(textarea, '详情 $ticket_l', 'l');
  fireEvent.click(await screen.findByText('工单详情链接'));
  expect(textarea.value).toBe('详情 $ticket_link ');
});

it('变量菜单打开时 Escape 只关闭菜单，下一次才交给编辑页', async () => {
  const onKeyDown = vi.fn();
  render(<div role="dialog" onKeyDown={onKeyDown}><ContentEditor /></div>);
  const textarea = screen.getByRole<HTMLTextAreaElement>('textbox', { name: '通知内容' });
  act(() => textarea.focus());
  input(textarea, '$', '$');
  expect(await screen.findByText('工单标题')).toBeTruthy();
  fireEvent.keyDown(textarea, { key: 'Escape', keyCode: 27 });
  expect(onKeyDown).not.toHaveBeenCalled();
  await waitFor(() => expect(screen.queryByRole('menuitem', { name: /工单标题/ })).toBeNull());
  fireEvent.keyDown(textarea, { key: 'Escape', keyCode: 27 });
  expect(onKeyDown).toHaveBeenCalledTimes(1);
});
