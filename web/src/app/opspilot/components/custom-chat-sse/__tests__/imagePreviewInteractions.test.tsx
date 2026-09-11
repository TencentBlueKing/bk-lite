// @vitest-environment jsdom

import React from 'react';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../hooks/useSSEStream', () => ({
  useSSEStream: () => ({
    handleSSEStream: vi.fn(),
    stopSSEConnection: vi.fn(),
  }),
}));

vi.mock('../hooks/useSendMessage', () => ({
  useSendMessage: () => ({ sendMessage: mocks.sendMessage }),
}));

vi.mock('../toolCallRenderer', () => ({
  initToolCallTooltips: vi.fn(),
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

vi.mock('@ant-design/icons', () => {
  const Icon = () => <span />;
  return {
    DeleteOutlined: Icon,
    FullscreenExitOutlined: Icon,
    FullscreenOutlined: Icon,
    LoadingOutlined: Icon,
    PictureOutlined: Icon,
    RightOutlined: Icon,
    SendOutlined: Icon,
  };
});

import CustomChatSSE from '..';

const createUpload = (uid: string, name: string) =>
  Object.assign(new File(['image'], name, { type: 'image/png' }), { uid });

describe('CustomChatSSE 图片预览资源', () => {
  const createObjectURL = vi.fn<(blob: Blob | MediaSource) => string>();
  const revokeObjectURL = vi.fn<(url: string) => void>();

  beforeEach(() => {
    let sequence = 0;
    createObjectURL.mockImplementation(() => `blob:preview-${++sequence}`);
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    });
    mocks.sendMessage.mockReset();
  });

  afterEach(() => {
    cleanup();
    mocks.nextUpload = null;
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  const renderChat = () => render(
    <CustomChatSSE
      showHeader={false}
      requirePermission={false}
      conversationHistoryEnabled={false}
    />,
  );

  it('点击删除图片会卸载对应预览并释放 URL', async () => {
    const view = renderChat();
    mocks.nextUpload = createUpload('first', 'first.png');
    fireEvent.click(view.getByTestId('image-upload'));
    mocks.nextUpload = createUpload('second', 'second.png');
    fireEvent.click(view.getByTestId('image-upload'));

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(2));
    fireEvent.click(view.getAllByRole('button', { name: '删除图片' })[0]);

    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:preview-1'));
    expect(view.getAllByRole('img')).toHaveLength(1);
    expect(revokeObjectURL).toHaveBeenCalledOnce();
  });

  it('点击发送会释放全部预览并保持图片发送数据', async () => {
    const view = renderChat();
    mocks.nextUpload = createUpload('first', 'first.png');
    fireEvent.click(view.getByTestId('image-upload'));
    mocks.nextUpload = createUpload('second', 'second.png');
    fireEvent.click(view.getByTestId('image-upload'));

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(2));
    fireEvent.click(view.getByRole('button', { name: '发送消息' }));

    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(mocks.sendMessage).toHaveBeenCalledOnce());
    expect(view.queryAllByRole('img')).toHaveLength(0);
    expect(mocks.sendMessage).toHaveBeenCalledWith(
      '',
      [],
      [
        expect.objectContaining({ id: 'first', name: 'first.png', status: 'done' }),
        expect.objectContaining({ id: 'second', name: 'second.png', status: 'done' }),
      ],
    );
  });
});
