// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { replayChatContent } from '@bk-lite/chat-content/events';
import CustomChatSSE from '..';
import type { CustomChatMessage } from '@/app/opspilot/types/global';

vi.mock('next-auth/react', () => ({ useSession: () => ({ data: null }) }));
vi.mock('@/context/auth', () => ({ useAuth: () => ({ token: 'fixture' }) }));
vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string, fallback?: string) => fallback || key }),
}));

beforeEach(() => {
  HTMLElement.prototype.scrollTo = vi.fn();
  vi.stubGlobal('matchMedia', () => ({ matches: false, addListener() {}, removeListener() {} }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const cards = ['old', 'active'].map(choice_id => replayChatContent([{
  type: 'CUSTOM', name: 'user_choice_request', value: { choice_id, title: choice_id, options: ['确认执行', '取消'] },
}]).userChoiceRequests![0]);
const history: CustomChatMessage[] = [{ role: 'bot', id: 'row', content: '', userChoiceRequests: cards }];
const props = { initialMessages: history, showHeader: false, requirePermission: false, conversationHistoryEnabled: false };

it('技能对话只续接最后一张真实卡，发送失败后允许再次点选或手输', async () => {
  const post = vi.fn().mockResolvedValue(new Response(null, { status: 503 }));
  vi.stubGlobal('fetch', post);
  const send = vi.fn(async (_text: string, _history?: unknown[], msg?: CustomChatMessage) => ({
    url: '/fixture', payload: { content: msg?.content, choice: msg?.choiceId, option: msg?.choiceOption, reply: msg?.replyToChoiceId },
  }));
  const view = render(<CustomChatSSE {...props} handleSendMessage={send} />);
  const confirm = () => view.getByRole('button', { name: '确认执行' });
  fireEvent.click(confirm());
  await waitFor(() => expect(post).toHaveBeenCalledOnce());
  expect(JSON.parse(post.mock.calls[0][1].body)).toEqual({ content: '确认执行', choice: 'active', option: '确认执行' });
  await waitFor(() => expect(confirm().hasAttribute('disabled')).toBe(false));
  fireEvent.change(view.getByPlaceholderText('回复上面的问题...'), { target: { value: '不管了' } });
  fireEvent.click(view.getByRole('button', { name: '发送消息' }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(JSON.parse(post.mock.calls[1][1].body)).toEqual({ content: '不管了', reply: 'active' });
  await waitFor(() => expect(confirm().hasAttribute('disabled')).toBe(false));
  fireEvent.change(view.getByPlaceholderText('输入你的回答...'), { target: { value: '二' } });
  fireEvent.keyDown(view.getByPlaceholderText('输入你的回答...'), { key: 'Enter', code: 'Enter', keyCode: 13 });
  await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
  expect(JSON.parse(post.mock.calls[2][1].body)).toEqual({ content: '二', reply: 'active' });
});

it('只读技能历史无法操作待确认问题', () => {
  const view = render(<CustomChatSSE {...props} mode="display" />);
  expect(view.queryAllByRole('button', { name: '确认执行' })).toHaveLength(0);
});
