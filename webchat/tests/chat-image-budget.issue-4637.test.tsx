import assert from 'node:assert/strict';
import test from 'node:test';

import React from 'react';
import { act, create, type ReactTestInstance, type ReactTestRenderer } from 'react-test-renderer';

import type { Message } from '../packages/webchat-core/src/types';
import { Chat, type ChatProps } from '../packages/webchat-ui/src/Chat';
import { FloatingButton } from '../packages/webchat-ui/src/FloatingButton';

interface TestFile {
  arrayBuffer: () => Promise<ArrayBuffer>;
  name: string;
  size: number;
  type: string;
}

class ControlledFileReader {
  static pending: ControlledFileReader[] = [];
  static aborted: ControlledFileReader[] = [];

  error: DOMException | null = null;
  file?: TestFile;
  onabort: FileReader['onabort'] = null;
  onerror: FileReader['onerror'] = null;
  onload: FileReader['onload'] = null;

  readAsDataURL(file: Blob) {
    this.file = file as unknown as TestFile;
    ControlledFileReader.pending.push(this);
  }

  abort() {
    ControlledFileReader.aborted.push(this);
    this.onabort?.call(
      this as unknown as FileReader,
      { target: this } as unknown as ProgressEvent<FileReader>,
    );
  }

  finish(dataUrl = `data:${this.file?.name}`) {
    this.onload?.call(
      this as unknown as FileReader,
      { target: { result: dataUrl } } as unknown as ProgressEvent<FileReader>,
    );
  }

  fail() {
    this.error = new DOMException('read failed');
    this.onerror?.call(
      this as unknown as FileReader,
      { target: this } as unknown as ProgressEvent<FileReader>,
    );
  }

  static reset() {
    ControlledFileReader.pending = [];
    ControlledFileReader.aborted = [];
  }
}

const pngHeader = (width: number, height: number): ArrayBuffer => {
  const bytes = new Uint8Array(24);
  bytes.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 0);
  const view = new DataView(bytes.buffer);
  view.setUint32(16, width);
  view.setUint32(20, height);
  return bytes.buffer;
};

const imageFile = (name: string, size = 1, width = 1, height = 1): File =>
  ({ arrayBuffer: async () => pngHeader(width, height), name, size, type: 'image/png' }) as File;

const unknownImageFile = (name: string, size = 1): File =>
  ({ arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer, name, size, type: 'image/avif' }) as File;

const flush = async () => {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
};

const renderChat = (props: ChatProps = {}): ReactTestRenderer => {
  ControlledFileReader.reset();
  let renderer!: ReactTestRenderer;
  act(() => {
    renderer = create(<Chat enableStorage={false} {...props} />);
  });
  return renderer;
};

const fileInput = (root: ReactTestInstance): ReactTestInstance =>
  root.find((node) => node.type === 'input' && node.props.type === 'file');

const selectFiles = async (root: ReactTestInstance, files: File[]) => {
  await act(async () => {
    fileInput(root).props.onChange({ target: { files, value: 'selected' } });
  });
  await flush();
};

const pasteFiles = async (root: ReactTestInstance, files: File[]) => {
  const pasteTarget = root.find((node) => typeof node.props.onPaste === 'function');
  await act(async () => {
    pasteTarget.props.onPaste({
      clipboardData: {
        items: files.map((file) => ({ getAsFile: () => file, type: file.type })),
      },
      preventDefault: () => undefined,
    });
  });
  await flush();
};

const finishReaders = async (readers: readonly ControlledFileReader[]) => {
  await act(async () => {
    readers.forEach((reader) => reader.finish());
    await Promise.resolve();
  });
  await flush();
};

const previews = (root: ReactTestInstance): ReactTestInstance[] =>
  root.findAll((node) => node.type === 'img' && /^Upload /.test(node.props.alt ?? ''));

globalThis.FileReader = ControlledFileReader as unknown as typeof FileReader;
Object.assign(globalThis, {
  document: {
    addEventListener: () => undefined,
    getElementById: () => ({}),
    removeEventListener: () => undefined,
  },
  window: { innerHeight: 800 },
});

test('Chat 默认预算在上传和粘贴入口读取前原子拒绝超限批次', async () => {
  const errors: Error[] = [];
  const renderer = renderChat({ onError: (error) => errors.push(error) });

  await selectFiles(renderer.root, Array.from({ length: 5 }, (_, index) => imageFile(`${index}.png`)));
  assert.equal(ControlledFileReader.pending.length, 0);
  assert.match(errors[0]?.message ?? '', /最多选择 4 张/);

  await pasteFiles(renderer.root, Array.from({ length: 5 }, (_, index) => imageFile(`p${index}.png`)));
  assert.equal(ControlledFileReader.pending.length, 0);
  assert.match(errors[1]?.message ?? '', /最多选择 4 张/);
  renderer.unmount();
});

test('Chat 在上传和粘贴入口按累计原始字节拒绝且不启动读取', async () => {
  const errors: Error[] = [];
  const renderer = renderChat({ maxImageCount: 4, maxTotalImageBytes: 3, onError: (error) => errors.push(error) });

  await selectFiles(renderer.root, [imageFile('upload.png', 4)]);
  assert.equal(ControlledFileReader.pending.length, 0);
  assert.match(errors[0]?.message ?? '', /图片总大小不能超过/);

  await pasteFiles(renderer.root, [imageFile('paste.png', 4)]);
  assert.equal(ControlledFileReader.pending.length, 0);
  assert.match(errors[1]?.message ?? '', /图片总大小不能超过/);
  renderer.unmount();
});

test('Chat 在 FileReader 前拒绝解码像素炸弹，正常 PNG 仍可预览', async () => {
  const errors: Error[] = [];
  const renderer = renderChat({ maxImagePixels: 4_000_000, onError: (error) => errors.push(error) });

  await selectFiles(renderer.root, [imageFile('bomb.png', 1024, 32768, 32768)]);
  assert.equal(ControlledFileReader.pending.length, 0);
  assert.match(errors[0]?.message ?? '', /像素/);

  await selectFiles(renderer.root, [imageFile('normal.png', 1024, 1920, 1080)]);
  assert.equal(ControlledFileReader.pending.length, 1);
  await finishReaders([ControlledFileReader.pending[0]]);
  assert.deepEqual(previews(renderer.root).map((node) => node.props.src), ['data:normal.png']);
  renderer.unmount();
});

test('Chat 未知格式默认接受但不解码预览，显式兼容配置可恢复旧预览', async () => {
  const received: Message[] = [];
  const strictRenderer = renderChat({ onMessageReceived: (message) => received.push(message) });
  await selectFiles(strictRenderer.root, [unknownImageFile('legacy.avif')]);
  assert.equal(ControlledFileReader.pending.length, 1);
  await finishReaders([ControlledFileReader.pending[0]]);
  assert.equal(previews(strictRenderer.root).length, 0);
  assert.match(strictRenderer.root.findByProps({ role: 'status' }).props['aria-label'], /legacy\.avif.*安全占位/);
  const sender = strictRenderer.root.find((node) => typeof node.props.onSubmit === 'function');
  await act(async () => {
    sender.props.onSubmit('未知格式仍发送');
    await Promise.resolve();
  });
  let sentStatus = '';
  for (let attempt = 0; attempt < 20 && !sentStatus; attempt += 1) {
    await act(async () => new Promise((resolve) => setTimeout(resolve, 5)));
    sentStatus = strictRenderer.root.findAllByProps({ role: 'status' })
      .map((node) => String(node.props['aria-label'] ?? ''))
      .find((label) => /图片已发送/.test(label)) ?? '';
  }
  assert.match(sentStatus, /图片已发送.*未在浏览器解码预览/);
  assert.deepEqual(received[0]?.content, [
    { image_url: 'data:legacy.avif', type: 'image_url' },
    { message: '未知格式仍发送', type: 'message' },
  ]);
  assert.deepEqual(received[0]?.metadata, { unpreviewedImageIndexes: [0] });
  strictRenderer.unmount();

  const compatRenderer = renderChat({ allowUnknownImagePreview: true });
  await selectFiles(compatRenderer.root, [unknownImageFile('legacy.avif')]);
  assert.equal(ControlledFileReader.pending.length, 1);
  await finishReaders([ControlledFileReader.pending[0]]);
  assert.deepEqual(previews(compatRenderer.root).map((node) => node.props.src), ['data:legacy.avif']);
  compatRenderer.unmount();
});

test('Chat 显式放宽后有界读取、乱序完成仍保序，移除后释放累计预算', async () => {
  const renderer = renderChat({
    imageReadConcurrency: 2,
    maxImageCount: 2,
    maxTotalImageBytes: 8,
  });

  await selectFiles(renderer.root, [imageFile('first.png', 4), imageFile('second.png', 4)]);
  assert.equal(ControlledFileReader.pending.length, 2);
  await finishReaders([ControlledFileReader.pending[1], ControlledFileReader.pending[0]]);
  assert.deepEqual(previews(renderer.root).map((node) => node.props.src), [
    'data:first.png',
    'data:second.png',
  ]);

  const readCountBeforeReject = ControlledFileReader.pending.length;
  await pasteFiles(renderer.root, [imageFile('overflow.png', 1)]);
  assert.equal(ControlledFileReader.pending.length, readCountBeforeReject);

  act(() => {
    renderer.root.findAll((node) => node.type === 'button' && node.children.includes('×'))[0].props.onClick();
  });
  const readCount = ControlledFileReader.pending.length;
  await pasteFiles(renderer.root, [imageFile('replacement.png', 4)]);
  assert.equal(ControlledFileReader.pending.length, readCount + 1);
  await finishReaders([ControlledFileReader.pending.at(-1)!]);
  assert.deepEqual(previews(renderer.root).map((node) => node.props.src), [
    'data:second.png',
    'data:replacement.png',
  ]);
  renderer.unmount();
});

test('Chat 在前一批仍读取时立即按预留预算拒绝后续超限批次', async () => {
  const errors: Error[] = [];
  const renderer = renderChat({
    imageReadConcurrency: 1,
    maxImageCount: 2,
    maxTotalImageBytes: 8,
    onError: (error) => errors.push(error),
  });

  await selectFiles(renderer.root, [imageFile('first.png', 4), imageFile('second.png', 4)]);
  assert.equal(ControlledFileReader.pending.length, 1);

  await selectFiles(renderer.root, [imageFile('queued-overflow.png', 1)]);
  assert.equal(ControlledFileReader.pending.length, 1);
  assert.match(errors[0]?.message ?? '', /最多选择 2 张/);

  await finishReaders([ControlledFileReader.pending[0]]);
  await finishReaders([ControlledFileReader.pending[1]]);
  renderer.unmount();
});

test('FloatingButton 将预算配置透传给 Chat', async () => {
  const errors: Error[] = [];
  ControlledFileReader.reset();
  let renderer!: ReactTestRenderer;
  act(() => {
    renderer = create(
      <FloatingButton maxImageCount={1} onError={(error) => errors.push(error)} />,
    );
  });
  await act(async () => {
    renderer.root.find((node) => node.type === 'button' && node.props.title === '打开对话').props.onClick();
    await new Promise((resolve) => setTimeout(resolve, 20));
  });

  await selectFiles(renderer.root, [imageFile('one.png'), imageFile('two.png')]);
  assert.equal(ControlledFileReader.pending.length, 0);
  assert.match(errors[0]?.message ?? '', /最多选择 1 张/);
  renderer.unmount();
});

test('Chat 发送期间使正在读取的旧批次失效，不回填预览', async () => {
  const renderer = renderChat({ imageReadConcurrency: 1 });
  await selectFiles(renderer.root, [imageFile('late.png'), imageFile('never-started.png')]);
  const reader = ControlledFileReader.pending[0];
  const sender = renderer.root.find((node) => typeof node.props.onSubmit === 'function');

  await act(async () => {
    sender.props.onSubmit('先发送文字');
    reader.finish();
    await Promise.resolve();
  });
  await flush();

  assert.deepEqual(ControlledFileReader.aborted, [reader]);
  assert.equal(ControlledFileReader.pending.length, 1);
  assert.equal(previews(renderer.root).length, 0);
  renderer.unmount();
});

test('Chat 发送时同步释放旧批次预算，允许下一条消息立即选择图片', async () => {
  const errors: Error[] = [];
  const renderer = renderChat({
    imageReadConcurrency: 1,
    maxImageCount: 1,
    onError: (error) => errors.push(error),
  });
  await selectFiles(renderer.root, [imageFile('stale.png')]);
  const staleReader = ControlledFileReader.pending[0];
  const sender = renderer.root.find((node) => typeof node.props.onSubmit === 'function');

  await act(async () => {
    sender.props.onSubmit('先发送文字');
    await Promise.resolve();
  });
  await selectFiles(renderer.root, [imageFile('next.png')]);
  assert.equal(errors.length, 0);

  await finishReaders([staleReader]);
  const nextReader = ControlledFileReader.pending[1];
  assert.equal(nextReader.file?.name, 'next.png');
  await finishReaders([nextReader]);
  assert.deepEqual(previews(renderer.root).map((node) => node.props.src), ['data:next.png']);
  renderer.unmount();
});

test('Chat 发送已完成图片后清空预览与账本并保持消息协议', async () => {
  const received: Message[] = [];
  const renderer = renderChat({ onMessageReceived: (message) => received.push(message) });
  await selectFiles(renderer.root, [imageFile('sent.png', 4)]);
  await finishReaders([ControlledFileReader.pending[0]]);
  assert.equal(previews(renderer.root).length, 1);

  const sender = renderer.root.find((node) => typeof node.props.onSubmit === 'function');
  await act(async () => {
    sender.props.onSubmit('图片说明');
    await Promise.resolve();
  });
  assert.equal(previews(renderer.root).length, 0);
  assert.deepEqual(received[0]?.content, [
    { image_url: 'data:sent.png', type: 'image_url' },
    { message: '图片说明', type: 'message' },
  ]);

  const startedBeforeRefill = ControlledFileReader.pending.length;
  await selectFiles(
    renderer.root,
    Array.from({ length: 4 }, (_, index) => imageFile(`refill-${index}.png`, 4)),
  );
  assert.equal(ControlledFileReader.pending.length, startedBeforeRefill + 2);
  renderer.unmount();
});

test('Chat 清空期间使正在读取的旧批次失效，不回填预览', async () => {
  const renderer = renderChat({ showClearButton: true });
  await selectFiles(renderer.root, [imageFile('late-clear.png')]);
  const reader = ControlledFileReader.pending[0];

  act(() => {
    renderer.root.find((node) => node.type === 'button' && node.props.title === '清除对话').props.onClick();
  });
  await act(async () => {
    renderer.root.find((node) => node.type === 'button' && node.children.includes('清除对话')).props.onClick();
    reader.finish();
    await Promise.resolve();
  });
  await flush();

  assert.equal(previews(renderer.root).length, 0);
  renderer.unmount();
});

test('Chat 确认清空已完成图片后释放预览与账本', async () => {
  const renderer = renderChat({ showClearButton: true });
  await selectFiles(renderer.root, [imageFile('cleared.png', 4)]);
  await finishReaders([ControlledFileReader.pending[0]]);
  assert.equal(previews(renderer.root).length, 1);

  act(() => {
    renderer.root.find((node) => node.type === 'button' && node.props.title === '清除对话').props.onClick();
  });
  act(() => {
    renderer.root.find((node) => node.type === 'button' && node.children.includes('清除对话')).props.onClick();
  });
  assert.equal(previews(renderer.root).length, 0);

  const startedBeforeRefill = ControlledFileReader.pending.length;
  await selectFiles(
    renderer.root,
    Array.from({ length: 4 }, (_, index) => imageFile(`clear-refill-${index}.png`, 4)),
  );
  assert.equal(ControlledFileReader.pending.length, startedBeforeRefill + 2);
  renderer.unmount();
});

test('Chat 挂载态读取失败保留既有预览、只报错一次且后续队列可恢复', async () => {
  const errors: Error[] = [];
  const renderer = renderChat({ maxImageCount: 3, onError: (error) => errors.push(error) });
  await selectFiles(renderer.root, [imageFile('kept.png')]);
  await finishReaders([ControlledFileReader.pending[0]]);

  const failedBatchStart = ControlledFileReader.pending.length;
  await selectFiles(renderer.root, [imageFile('broken.png'), imageFile('settled.png')]);
  const broken = ControlledFileReader.pending[failedBatchStart];
  const settled = ControlledFileReader.pending[failedBatchStart + 1];
  await act(async () => {
    broken.fail();
    settled.finish();
    await Promise.resolve();
  });
  await flush();
  assert.equal(errors.length, 1);
  assert.deepEqual(previews(renderer.root).map((node) => node.props.src), ['data:kept.png']);

  const recoveryStart = ControlledFileReader.pending.length;
  await selectFiles(renderer.root, [imageFile('recovered.png')]);
  await finishReaders([ControlledFileReader.pending[recoveryStart]]);
  assert.deepEqual(previews(renderer.root).map((node) => node.props.src), [
    'data:kept.png',
    'data:recovered.png',
  ]);
  renderer.unmount();
});

test('Chat 卸载后使正在读取的旧批次失效', async () => {
  const errors: Error[] = [];
  const renderer = renderChat({ onError: (error) => errors.push(error) });
  await selectFiles(renderer.root, [imageFile('late-unmount.png')]);
  const reader = ControlledFileReader.pending[0];

  act(() => renderer.unmount());
  reader.fail();
  await flush();
  assert.equal(errors.length, 0);
});

test('browser initializer 将预算配置原样传给嵌入式 Chat', async () => {
  const globals = globalThis as typeof globalThis & {
    __webchatRendered?: React.ReactElement;
  };
  const browser = await import('../packages/webchat-ui/src/browser-entry');
  browser.default.default(
    {
      allowUnknownImagePreview: true,
      imageReadConcurrency: 3,
      maxImageCount: 9,
      maxImagePixels: 77,
      maxTotalImageBytes: 99,
      maxTotalImagePixels: 88,
    },
    'target',
  );

  assert.equal(globals.__webchatRendered?.props.maxImageCount, 9);
  assert.equal(globals.__webchatRendered?.props.maxTotalImageBytes, 99);
  assert.equal(globals.__webchatRendered?.props.imageReadConcurrency, 3);
  assert.equal(globals.__webchatRendered?.props.maxImagePixels, 77);
  assert.equal(globals.__webchatRendered?.props.maxTotalImagePixels, 88);
  assert.equal(globals.__webchatRendered?.props.allowUnknownImagePreview, true);
});
