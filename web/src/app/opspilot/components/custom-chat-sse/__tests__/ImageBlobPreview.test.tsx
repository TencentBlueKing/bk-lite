// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';
import type { UploadFile } from 'antd/es/upload/interface';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ImageBlobPreview from '../ImageBlobPreview';

const createUploadFile = (uid: string, file: File): UploadFile => ({
  uid,
  name: file.name,
  status: 'done',
  originFileObj: file as UploadFile['originFileObj'],
});

describe('ImageBlobPreview', () => {
  const createObjectURL = vi.fn<(blob: Blob | MediaSource) => string>();
  const revokeObjectURL = vi.fn<(url: string) => void>();

  beforeEach(() => {
    createObjectURL.mockReset();
    revokeObjectURL.mockReset();
    createObjectURL
      .mockReturnValueOnce('blob:first')
      .mockReturnValueOnce('blob:second');
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('同一文件重复渲染只创建一个预览 URL', async () => {
    const source = new File(['image'], 'preview.png', { type: 'image/png' });
    const file = createUploadFile('1', source);
    const { rerender } = render(<ImageBlobPreview file={file} />);

    await waitFor(() => expect(document.querySelector('img')?.src).toContain('blob:first'));
    rerender(<ImageBlobPreview file={{ ...file, name: 'renamed.png' }} />);

    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(revokeObjectURL).not.toHaveBeenCalled();
  });

  it('文件替换时释放旧 URL 并为新文件创建 URL', async () => {
    const first = createUploadFile(
      '1',
      new File(['first'], 'first.png', { type: 'image/png' }),
    );
    const second = createUploadFile(
      '1',
      new File(['second'], 'second.png', { type: 'image/png' }),
    );
    const { rerender } = render(<ImageBlobPreview file={first} />);

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledOnce());
    rerender(<ImageBlobPreview file={second} />);
    await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(2));

    expect(revokeObjectURL).toHaveBeenCalledWith('blob:first');
    expect(document.querySelector('img')?.src).toContain('blob:second');
  });

  it('文件项卸载时释放当前 URL', async () => {
    const file = createUploadFile(
      '1',
      new File(['image'], 'preview.png', { type: 'image/png' }),
    );
    const { unmount } = render(<ImageBlobPreview file={file} />);

    await waitFor(() => expect(createObjectURL).toHaveBeenCalledOnce());
    unmount();

    expect(revokeObjectURL).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:first');
  });
});
