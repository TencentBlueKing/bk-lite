import assert from 'node:assert/strict';
import test from 'node:test';

import type { WebChatConfig } from '../packages/webchat-core/src/types';
import {
  DEFAULT_IMAGE_BUDGET,
  parseImageDimensions,
  pendingImageBytes,
  pendingImagePixels,
  pendingImagesReducer,
  readImageBatch,
  resolveImageBudget,
  validateImageBatch,
  validateImagePixelBudget,
  type InspectedImageFile,
  type ImageFile,
  type PendingImage,
} from '../packages/webchat-ui/src/imageBudget';

const imageFile = (name: string, size: number): ImageFile => ({
  name,
  size,
  type: 'image/png',
});

const pendingImage = (name: string, size: number): PendingImage => ({
  dataUrl: `data:image/png;base64,${name}`,
  height: 1,
  name,
  pixels: 1,
  previewable: true,
  size,
  width: 1,
});

const pngHeader = (width: number, height: number): Uint8Array => {
  const bytes = new Uint8Array(24);
  bytes.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 0);
  new DataView(bytes.buffer).setUint32(16, width);
  new DataView(bytes.buffer).setUint32(20, height);
  return bytes;
};

const animatedPngHeader = (width: number, height: number): Uint8Array => {
  const bytes = new Uint8Array(32);
  bytes.set(pngHeader(width, height));
  bytes.set([0x61, 0x63, 0x54, 0x4c], 28);
  return bytes;
};

const inspectedImage = (name: string, width: number, height: number): InspectedImageFile => ({
  file: imageFile(name, 1),
  height,
  pixels: width * height,
  width,
});

test('旧调用方默认接受四张共十六 MiB 的图片', () => {
  const typedConfig: WebChatConfig = {};
  const budget = resolveImageBudget(typedConfig);
  const files = Array.from({ length: 4 }, (_, index) => imageFile(`${index}.png`, 4 * 1024 * 1024));

  assert.deepEqual(budget, DEFAULT_IMAGE_BUDGET);
  assert.deepEqual(validateImageBatch([], files, budget), { ok: true });
});

test('格式头预检读取 PNG 尺寸并拒绝单图或累计解码像素超限', () => {
  assert.deepEqual(parseImageDimensions(pngHeader(2048, 1024)), {
    height: 1024,
    pixels: 2048 * 1024,
    width: 2048,
  });

  assert.deepEqual(
    validateImagePixelBudget([], [inspectedImage('bomb.png', 32768, 32768)], DEFAULT_IMAGE_BUDGET),
    {
      limit: DEFAULT_IMAGE_BUDGET.maxImagePixels,
      ok: false,
      reason: 'image-pixels',
    },
  );
  const selected = [pendingImage('selected.png', 1)];
  selected[0].pixels = DEFAULT_IMAGE_BUDGET.maxTotalImagePixels;
  assert.deepEqual(
    validateImagePixelBudget(selected, [inspectedImage('next.png', 1, 1)], DEFAULT_IMAGE_BUDGET),
    {
      limit: DEFAULT_IMAGE_BUDGET.maxTotalImagePixels,
      ok: false,
      reason: 'total-pixels',
    },
  );
  assert.equal(pendingImagePixels(selected), DEFAULT_IMAGE_BUDGET.maxTotalImagePixels);
});

test('动画格式不按单帧尺寸低估内存，降级为不解码的安全占位', () => {
  const gif = new Uint8Array([0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 1, 0, 1, 0]);

  assert.equal(parseImageDimensions(gif), null);
  assert.equal(parseImageDimensions(animatedPngHeader(32, 32)), null);
});

test('未知格式沿用原始字节预算且默认不进入浏览器像素解码', () => {
  const unknown: InspectedImageFile = {
    file: imageFile('legacy.avif', 1),
    height: null,
    pixels: null,
    width: null,
  };

  assert.deepEqual(validateImagePixelBudget([], [unknown], DEFAULT_IMAGE_BUDGET), { ok: true });
  assert.equal(DEFAULT_IMAGE_BUDGET.allowUnknownImagePreview, false);
});

test('显式配置可以放宽预算，非法值回落为默认值', () => {
  const relaxedConfig: WebChatConfig = {
    allowUnknownImagePreview: true,
    imageReadConcurrency: 4,
    maxImageCount: 8,
    maxImagePixels: 24 * 1024 * 1024,
    maxTotalImageBytes: 32 * 1024 * 1024,
    maxTotalImagePixels: 48 * 1024 * 1024,
  };

  assert.deepEqual(resolveImageBudget(relaxedConfig), {
    allowUnknownImagePreview: true,
    imageReadConcurrency: 4,
    maxImageCount: 8,
    maxImagePixels: 24 * 1024 * 1024,
    maxTotalImageBytes: 32 * 1024 * 1024,
    maxTotalImagePixels: 48 * 1024 * 1024,
  });
  assert.deepEqual(
    resolveImageBudget({
      imageReadConcurrency: 0,
      maxImageCount: Number.NaN,
      maxImagePixels: 0,
      maxTotalImageBytes: -1,
      maxTotalImagePixels: Number.NaN,
    }),
    DEFAULT_IMAGE_BUDGET
  );
  assert.deepEqual(
    validateImageBatch(
      [],
      Array.from({ length: 8 }, (_, index) => imageFile(`${index}.png`, 4 * 1024 * 1024)),
      resolveImageBudget(relaxedConfig)
    ),
    { ok: true }
  );
});

test('超过数量时原子拒绝整个新批次', () => {
  const current = [pendingImage('selected.png', 1)];
  const incoming = Array.from({ length: 4 }, (_, index) => imageFile(`${index}.png`, 1));

  assert.deepEqual(validateImageBatch(current, incoming, DEFAULT_IMAGE_BUDGET), {
    limit: DEFAULT_IMAGE_BUDGET.maxImageCount,
    ok: false,
    reason: 'count',
  });
  assert.deepEqual(current, [pendingImage('selected.png', 1)]);
});

test('累计原始字节超过总预算时原子拒绝整个新批次', () => {
  const current = [pendingImage('selected.png', 15 * 1024 * 1024)];
  const incoming = [imageFile('a.png', 1024 * 1024), imageFile('b.png', 1)];

  assert.deepEqual(validateImageBatch(current, incoming, DEFAULT_IMAGE_BUDGET), {
    limit: DEFAULT_IMAGE_BUDGET.maxTotalImageBytes,
    ok: false,
    reason: 'bytes',
  });
  assert.equal(pendingImageBytes(current), 15 * 1024 * 1024);
});

test('有界读取保持输入顺序并限制并发峰值', async () => {
  const files = [imageFile('slow.png', 3), imageFile('fast.png', 2), imageFile('last.png', 1)];
  let active = 0;
  let peak = 0;

  const result = await readImageBatch(files, 2, async (file) => {
    active += 1;
    peak = Math.max(peak, active);
    await new Promise((resolve) => setTimeout(resolve, file.name === 'slow.png' ? 20 : 1));
    active -= 1;
    return `data:${file.name}`;
  });

  assert.equal(peak, 2);
  assert.deepEqual(result, [
    { dataUrl: 'data:slow.png', height: null, name: 'slow.png', pixels: null, previewable: false, size: 3, width: null },
    { dataUrl: 'data:fast.png', height: null, name: 'fast.png', pixels: null, previewable: false, size: 2, width: null },
    { dataUrl: 'data:last.png', height: null, name: 'last.png', pixels: null, previewable: false, size: 1, width: null },
  ]);
});

test('读取失败向上传递且不会返回部分批次', async () => {
  const files = [imageFile('ok.png', 1), imageFile('broken.png', 1)];

  await assert.rejects(
    readImageBatch(files, 1, async (file) => {
      if (file.name === 'broken.png') {
        throw new Error('read failed');
      }
      return `data:${file.name}`;
    }),
    /read failed/
  );
});

test('失败批次等待已启动读取收敛后才允许下一批，跨批并发不超限', async () => {
  const firstBatch = [imageFile('broken.png', 1), imageFile('slow.png', 1)];
  const nextBatch = [imageFile('next-a.png', 1), imageFile('next-b.png', 1)];
  let active = 0;
  let peak = 0;

  const read = async (file: ImageFile) => {
    active += 1;
    peak = Math.max(peak, active);
    try {
      await new Promise((resolve) => setTimeout(resolve, file.name === 'broken.png' ? 1 : 20));
      if (file.name === 'broken.png') throw new Error('read failed');
      return `data:${file.name}`;
    } finally {
      active -= 1;
    }
  };

  await assert.rejects(readImageBatch(firstBatch, 2, read), /read failed/);
  await readImageBatch(nextBatch, 2, read);

  assert.equal(peak, 2);
  assert.equal(active, 0);
});

test('移除和发送清理同步释放图片数量与字节账本', () => {
  const selected = [pendingImage('a.png', 3), pendingImage('b.png', 5)];
  const afterRemove = pendingImagesReducer(selected, { index: 0, type: 'remove' });
  const afterSend = pendingImagesReducer(afterRemove, { type: 'clear' });

  assert.deepEqual(afterRemove, [pendingImage('b.png', 5)]);
  assert.equal(pendingImageBytes(afterRemove), 5);
  assert.deepEqual(afterSend, []);
  assert.equal(pendingImageBytes(afterSend), 0);
});
