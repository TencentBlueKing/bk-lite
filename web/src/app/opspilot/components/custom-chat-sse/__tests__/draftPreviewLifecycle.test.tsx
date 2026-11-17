// @vitest-environment jsdom

import React from 'react';
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  nextUpload: null as (File & { uid: string }) | null,
  sendMessage: vi.fn(),
  upload: vi.fn(),
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
  useSendMessage: () => ({ sendMessage: mocks.sendMessage }),
}));

vi.mock('@/app/opspilot/components/custom-chat-sse/toolCallRenderer', () => ({
  initToolCallTooltips: vi.fn(),
  setToolCallRendererLocale: vi.fn(),
}));

vi.mock('antd', () => {
  const Wrapper = ({ children }: { children?: React.ReactNode }) => <>{children}</>;
  const Upload = ({
    children,
    beforeUpload,
  }: {
    children?: React.ReactNode;
    beforeUpload: (file: File & { uid: string }) => unknown;
  }) => (
    <div
      data-testid="image-upload"
      onClick={() => mocks.nextUpload && beforeUpload(mocks.nextUpload)}
    >
      {children}
    </div>
  );
  Upload.LIST_IGNORE = 'LIST_IGNORE';

  return {
    Button: Wrapper,
    Checkbox: Wrapper,
    Flex: Wrapper,
    Image: Object.assign(
      ({ src, alt }: { src?: string; alt?: string }) => <img src={src} alt={alt} />,
      { PreviewGroup: Wrapper },
    ),
    Input: {
      TextArea: ({
        autoSize,
        bordered,
        ...props
      }: React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
        autoSize?: unknown;
        bordered?: boolean;
      }) => (
        <textarea
          aria-label="消息输入"
          data-auto-size={Boolean(autoSize)}
          data-bordered={bordered}
          {...props}
        />
      ),
    },
    Popconfirm: Wrapper,
    Popover: Wrapper,
    Spin: Wrapper,
    Tooltip: Wrapper,
    Upload,
    message: {
      error: vi.fn(),
      loading: () => vi.fn(),
      success: vi.fn(),
    },
  };
});

vi.mock('@ant-design/icons', async (original) => {
  const Icon = () => <span />;
  return {
    ...await original(),
    DeleteOutlined: Icon,
    DownloadOutlined: Icon,
    PaperClipOutlined: Icon,
    FullscreenExitOutlined: Icon,
    FullscreenOutlined: Icon,
    LoadingOutlined: Icon,
    PictureOutlined: Icon,
    RightOutlined: Icon,
    SendOutlined: Icon,
  };
});

vi.mock('@/app/opspilot/components/custom-chat-sse/chatAttachments', async (original) => ({
  ...await original(),
  uploadChatAttachment: (...args: unknown[]) => mocks.upload(...args),
}));

import CustomChatSSE from '..';


const active = new Set<string>();
const revoked: string[] = [];
let sequence = 0;
const metadata = { id: 1, name: 'fixture.png', mime: 'image/png', size: 7, status: 'ready' };

beforeEach(() => {
  HTMLElement.prototype.scrollTo = vi.fn();
  active.clear();
  revoked.length = 0;
  mocks.upload.mockResolvedValue(metadata);
  mocks.sendMessage.mockResolvedValue(undefined);
  mocks.nextUpload = Object.assign(new File(['fixture'], 'fixture.png', { type: 'image/png' }), { uid: 'fixture' });
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: () => { const url = `blob:fixture-${++sequence}`; active.add(url); return url; },
    revokeObjectURL: (url: string) => { revoked.push(url); active.delete(url); },
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

const mount = () => render(<CustomChatSSE showHeader={false} requirePermission={false} conversationHistoryEnabled={false} />);
const upload = async (view: ReturnType<typeof mount>) => {
  await act(async () => { fireEvent.click(view.getByTestId('image-upload')); });
  expect(view.getByTestId('attachment-chip')).toBeTruthy();
};

it('图片草稿显示时有效，成功上传后卸载会释放预览', async () => {
  const view = mount();
  await upload(view);
  expect(active.size).toBe(1);
  view.unmount();
  expect(active.size).toBe(0);
});

it('上传失败或超时后卸载仍回收草稿预览', async () => {
  for (const failure of [new Error('fixture failure'), new DOMException('fixture timeout', 'TimeoutError')]) {
    mocks.upload.mockRejectedValueOnce(failure);
    const view = mount();
    await upload(view);
    expect(view.getByTestId('attachment-chip').textContent).toContain(failure instanceof Error ? failure.message : '上传失败');
    expect(active.size).toBe(1);
    view.unmount();
    expect(active.size).toBe(0);
  }
});

it('上传未完成时卸载立即回收，迟到完成不重新创建 URL', async () => {
  let finish!: (value: typeof metadata) => void;
  mocks.upload.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  const view = mount();
  await upload(view);
  expect(active.size).toBe(1);
  view.unmount();
  expect(active.size).toBe(0);
  await act(async () => { finish(metadata); });
  expect(active.size).toBe(0);
  expect(revoked).toHaveLength(1);
});

it('删除图片同步释放登记，卸载不重复注销', async () => {
  const view = mount();
  await upload(view);
  fireEvent.click(view.getByRole('button', { name: '删除图片' }));
  expect(active.size).toBe(0);
  expect(view.queryByTestId('attachment-chip')).toBeNull();
  view.unmount();
  expect(revoked).toHaveLength(1);
});

it.each(['keyboard', 'button'])('通过 %s 发送后释放且附件数据保持不变', async (method) => {
  const view = mount();
  await upload(view);
  if (method === 'keyboard') {
    fireEvent.keyDown(view.getByRole('textbox'), { key: 'Enter', code: 'Enter' });
  } else {
    fireEvent.click(view.getByRole('button', { name: '发送消息' }));
  }
  await waitFor(() => expect(mocks.sendMessage).toHaveBeenCalledOnce());
  expect(mocks.sendMessage).toHaveBeenCalledWith('', [], [expect.objectContaining(metadata)]);
  expect(active.size).toBe(0);
  view.unmount();
  expect(revoked).toHaveLength(1);
});

it('非图片附件不分配预览 URL，删除与卸载不误释放', async () => {
  mocks.nextUpload = Object.assign(new File(['fixture'], 'fixture.txt', { type: 'text/plain' }), { uid: 'plain' });
  mocks.upload.mockResolvedValueOnce({ ...metadata, name: 'fixture.txt', mime: 'text/plain' });
  const view = mount();
  await upload(view);
  expect(active.size).toBe(0);
  fireEvent.click(view.getByRole('button', { name: '删除图片' }));
  view.unmount();
  expect(revoked).toHaveLength(0);
});

it('真实 ReactDOM StrictMode 下重复上传卸载不残留', async () => {
  for (let cycle = 0; cycle < 10; cycle += 1) {
    const view = render(<React.StrictMode><CustomChatSSE showHeader={false} requirePermission={false} /></React.StrictMode>);
    await upload(view);
    expect(active.size).toBe(1);
    view.unmount();
    expect(active.size).toBe(0);
  }
  expect(revoked).toHaveLength(10);
});

it.each(['keyboard', 'button'])('通过 %s 发送文本清空失败草稿时立即释放', async (method) => {
  mocks.upload.mockRejectedValueOnce(new Error('fixture failure'));
  const view = mount();
  await upload(view);
  expect(active.size).toBe(1);
  fireEvent.change(view.getByRole('textbox'), { target: { value: 'fixture text' } });
  if (method === 'keyboard') {
    fireEvent.keyDown(view.getByRole('textbox'), { key: 'Enter', code: 'Enter' });
  } else {
    fireEvent.click(view.getByRole('button', { name: '发送消息' }));
  }
  await waitFor(() => expect(mocks.sendMessage).toHaveBeenCalledOnce());
  expect(mocks.sendMessage).toHaveBeenCalledWith('fixture text', [], []);
  expect(view.queryByTestId('attachment-chip')).toBeNull();
  expect(active.size).toBe(0);
  view.unmount();
  expect(revoked).toHaveLength(1);
});

it.each(['keyboard', 'button'])('混合成功失败草稿通过 %s 发送后回收全部预览', async (method) => {
  const view = mount();
  await upload(view);
  mocks.nextUpload = Object.assign(new File(['fixture'], 'failed.png', { type: 'image/png' }), { uid: 'failed' });
  mocks.upload.mockRejectedValueOnce(new Error('fixture failure'));
  await act(async () => { fireEvent.click(view.getByTestId('image-upload')); });
  expect(active.size).toBe(2);
  expect(view.getAllByTestId('attachment-chip')).toHaveLength(2);
  if (method === 'keyboard') {
    fireEvent.keyDown(view.getByRole('textbox'), { key: 'Enter', code: 'Enter' });
  } else {
    fireEvent.click(view.getByRole('button', { name: '发送消息' }));
  }
  await waitFor(() => expect(mocks.sendMessage).toHaveBeenCalledOnce());
  expect(mocks.sendMessage).toHaveBeenCalledWith('', [], [expect.objectContaining(metadata)]);
  expect(view.queryAllByTestId('attachment-chip')).toHaveLength(0);
  expect(active.size).toBe(0);
  expect(revoked).toHaveLength(2);
  view.unmount();
  expect(revoked).toHaveLength(2);
});
