// @vitest-environment jsdom

import React from 'react';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  download: vi.fn(),
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { token: 'test-token' } } }),
}));

vi.mock('@/context/auth', () => ({
  useAuth: () => ({ token: 'test-token' }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string, defaultMessage?: string) => defaultMessage ?? key,
  }),
}));

vi.mock('@/app/opspilot/components/custom-chat-sse/hooks/useSSEStream', () => ({
  useSSEStream: () => ({
    handleSSEStream: vi.fn(),
    stopSSEConnection: vi.fn(),
  }),
}));

vi.mock('@/app/opspilot/components/custom-chat-sse/hooks/useSendMessage', () => ({
  useSendMessage: () => ({ sendMessage: vi.fn() }),
}));

vi.mock('@/app/opspilot/components/custom-chat-sse/toolCallRenderer', () => ({
  initToolCallTooltips: vi.fn(),
  setToolCallRendererLocale: vi.fn(),
}));

vi.mock('antd', () => {
  const Wrapper = ({ children }: { children?: React.ReactNode }) => <>{children}</>;
  return {
    Button: Wrapper,
    Checkbox: Wrapper,
    Flex: Wrapper,
    Image: Object.assign(
      ({ src, alt }: { src?: string; alt?: string }) => <img src={src} alt={alt} />,
      { PreviewGroup: Wrapper },
    ),
    Input: { TextArea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea aria-label="消息输入" {...props} /> },
    Modal: Wrapper,
    Popconfirm: Wrapper,
    Popover: Wrapper,
    Spin: Wrapper,
    Tooltip: Wrapper,
    Upload: Object.assign(Wrapper, { LIST_IGNORE: 'LIST_IGNORE' }),
    message: { error: vi.fn(), loading: () => vi.fn(), success: vi.fn() },
  };
});

vi.mock('@ant-design/icons', async (original) => {
  const Icon = () => <span />;
  return { ...await original(), DeleteOutlined: Icon, DownloadOutlined: Icon, PaperClipOutlined: Icon, FullscreenExitOutlined: Icon, FullscreenOutlined: Icon, LoadingOutlined: Icon, PictureOutlined: Icon, RightOutlined: Icon, SendOutlined: Icon };
});

vi.mock('@/app/opspilot/components/custom-chat-sse/chatAttachments', async (original) => ({
  ...await original(),
  downloadChatAttachmentBlob: () => mocks.download(),
}));

import CustomChatSSE from '..';

const attachment = { id: 1, name: 'fixture.png', mime: 'image/png', size: 7, status: 'ready' as const };
const messages = [{ id: 'fixture', role: 'user' as const, content: 'fixture', attachments: [attachment] }];
const active = new Set<string>();
let sequence = 0;

beforeEach(() => {
  HTMLElement.prototype.scrollTo = vi.fn();
  sequence = 0;
  active.clear();
  mocks.download.mockResolvedValue(new Blob(['fixture'], { type: 'image/png' }));
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: () => {
      const url = `blob:fixture-${++sequence}`;
      active.add(url);
      return url;
    },
    revokeObjectURL: (url: string) => active.delete(url),
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

const chat = (initialMessages = messages) => (
  <CustomChatSSE showHeader={false} requirePermission={false} conversationHistoryEnabled={false} initialMessages={initialMessages} />
);

it('历史图片显示期间有效，卸载后释放预览 URL', async () => {
  const view = render(chat());
  await waitFor(() => expect(view.getByAltText('fixture.png').getAttribute('src')).toContain('blob:fixture-'));
  expect(active.size).toBe(1);
  view.unmount();
  expect(active.size).toBe(0);
});

it('挂起下载在卸载后完成不会创建 URL', async () => {
  let release!: (blob: Blob) => void;
  mocks.download.mockImplementationOnce(() => new Promise<Blob>((resolve) => { release = resolve; }));
  const view = render(chat());
  await waitFor(() => expect(release).toBeTypeOf('function'));
  view.unmount();
  await act(async () => release(new Blob(['late'])));
  expect(active.size).toBe(0);
});

it('替换历史消息会释放旧图片 URL', async () => {
  const view = render(chat());
  await waitFor(() => expect(active.size).toBe(1));
  view.rerender(chat([{ ...messages[0], attachments: [{ ...attachment, id: 2, name: 'next.png' }] }]));
  await waitFor(() => expect(view.getByAltText('next.png').getAttribute('src')).toContain('blob:fixture-'));
  expect(active.size).toBe(1);
});
