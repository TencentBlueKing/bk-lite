// @vitest-environment jsdom

import React from 'react';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  nextUpload: null as (File & { uid: string }) | null,
  sendMessage: vi.fn(),
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

import CustomChatSSE from '@/app/opspilot/components/custom-chat-sse';



const attachment = {id:1,name:'fixture.png',mime:'image/png',size:7,status:'ready'};
const messages = [{id:'fixture',role:'user' as const,content:'fixture',attachments:[attachment]}];
const active = new Set<string>();
let sequence = 0;
beforeEach(()=>{
  HTMLElement.prototype.scrollTo=vi.fn();
  vi.stubGlobal('URL',{...URL,createObjectURL:vi.fn(()=>{const url=`blob:fixture-${++sequence}`;active.add(url);return url;}),revokeObjectURL:vi.fn((url:string)=>active.delete(url))});
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,blob:async()=>new Blob(['fixture'],{type:'image/png'})})));
});
afterEach(()=>{cleanup();active.clear();vi.unstubAllGlobals();vi.clearAllMocks();});
const chat=(initialMessages=messages)=><CustomChatSSE showHeader={false} requirePermission={false} initialMessages={initialMessages}/>;
it('历史图片显示期间有效，卸载后释放预览 URL',async()=>{
  const view=render(chat());
  await waitFor(()=>expect(view.getByAltText('fixture.png').getAttribute('src')).toContain('blob:fixture-'));
  expect(active.size).toBe(1);
  view.rerender(chat());expect(URL.createObjectURL).toHaveBeenCalledOnce();
  view.unmount();expect(active.size).toBe(0);
});

it('替换历史消息释放旧图片，移除最后附件释放新图片', async () => {
  const view = render(chat());
  await waitFor(() => expect(active.size).toBe(1));
  const oldUrl = view.getByAltText('fixture.png').getAttribute('src');
  const next = [{ ...messages[0], attachments: [{ ...attachment, id: 2, name: 'next.png' }] }];
  view.rerender(chat(next));
  await waitFor(() => expect(view.getByAltText('next.png').getAttribute('src')).toContain('blob:fixture-'));
  expect(active.size).toBe(1);
  expect(URL.revokeObjectURL).toHaveBeenCalledWith(oldUrl);
  view.rerender(chat([{ ...messages[0], attachments: [] }]));
  await waitFor(() => expect(active.size).toBe(0));
});

it('挂起下载在卸载后完成不会创建 URL 或调度 UI 回调', async () => {
  let release!: (blob: Blob) => void;
  vi.mocked(fetch).mockResolvedValue({ ok: true, blob: () => new Promise<Blob>((resolve) => { release = resolve; }) } as Response);
  const view = render(chat());
  await waitFor(() => expect(release).toBeTypeOf('function'));
  view.unmount();
  await act(async () => release(new Blob(['late'])));
  expect(URL.createObjectURL).not.toHaveBeenCalled();
});

it('同 ID 附件移除后重新加入，旧下载结果不能覆盖新预览', async () => {
  let release!: (blob: Blob) => void;
  vi.mocked(fetch).mockResolvedValueOnce({ ok: true, blob: () => new Promise<Blob>((resolve) => { release = resolve; }) } as Response);
  const view = render(chat());
  await waitFor(() => expect(release).toBeTypeOf('function'));
  view.rerender(chat([{ ...messages[0], attachments: [] }]));
  await waitFor(() => expect(view.queryByAltText('fixture.png')).toBeNull());
  view.rerender(chat());
  await waitFor(() => expect(view.getByAltText('fixture.png').getAttribute('src')).toContain('blob:fixture-'));
  const currentUrl = view.getByAltText('fixture.png').getAttribute('src');
  await act(async () => release(new Blob(['obsolete'])));
  expect(view.getByAltText('fixture.png').getAttribute('src')).toBe(currentUrl);
  expect(active.size).toBe(1);
  expect(URL.createObjectURL).toHaveBeenCalledOnce();
});

it('下载拒绝或非成功响应不登记 URL', async () => {
  for (const mode of ['reject', 'http']) {
    if (mode === 'reject') vi.mocked(fetch).mockRejectedValueOnce(new Error('fixture failure'));
    else vi.mocked(fetch).mockResolvedValueOnce({ ok: false } as Response);
    const view = render(chat());
    await act(async () => {});
    view.unmount();
    expect(active.size).toBe(0);
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  }
});

it('StrictMode 与重复挂载卸载都保持 URL 收支平衡', async () => {
  for (let cycle = 0; cycle < 10; cycle += 1) {
    const view = render(<React.StrictMode>{chat()}</React.StrictMode>);
    await waitFor(() => expect(view.getByAltText('fixture.png').getAttribute('src')).toContain('blob:fixture-'));
    expect(active.size).toBe(1);
    view.unmount();
    expect(active.size).toBe(0);
  }
});

it('刷新相同历史附件复用仍有效的 URL', async () => {
  const view = render(chat());
  await waitFor(() => expect(view.getByAltText('fixture.png').getAttribute('src')).toContain('blob:fixture-'));
  const currentUrl = view.getByAltText('fixture.png').getAttribute('src');
  view.rerender(chat([{ ...messages[0], attachments: [{ ...attachment }] }]));
  await waitFor(() => expect(view.getByAltText('fixture.png').getAttribute('src')).toBe(currentUrl));
  expect(URL.createObjectURL).toHaveBeenCalledOnce();
});
