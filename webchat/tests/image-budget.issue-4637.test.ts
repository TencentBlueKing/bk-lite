import assert from 'node:assert/strict';
import test from 'node:test';

import type { WebChatConfig } from '../packages/webchat-core/src/types';
import {
  DEFAULT_IMAGE_BUDGET,
  pendingImageBytes,
  pendingImagesReducer,
  readImageBatch,
  resolveImageBudget,
  validateImageBatch,
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
  name,
  size,
});

test('旧调用方默认接受四张共十六 MiB 的图片', () => {
  const typedConfig: WebChatConfig = {};
  const budget = resolveImageBudget(typedConfig);
  const files = Array.from({ length: 4 }, (_, index) => imageFile(`${index}.png`, 4 * 1024 * 1024));

  assert.deepEqual(budget, DEFAULT_IMAGE_BUDGET);
  assert.deepEqual(validateImageBatch([], files, budget), { ok: true });
});

test('显式配置可以放宽预算，非法值回落为默认值', () => {
  const relaxedConfig: WebChatConfig = {
    imageReadConcurrency: 4,
    maxImageCount: 8,
    maxTotalImageBytes: 32 * 1024 * 1024,
  };

  assert.deepEqual(resolveImageBudget(relaxedConfig), {
    imageReadConcurrency: 4,
    maxImageCount: 8,
    maxTotalImageBytes: 32 * 1024 * 1024,
  });
  assert.deepEqual(
    resolveImageBudget({
      imageReadConcurrency: 0,
      maxImageCount: Number.NaN,
      maxTotalImageBytes: -1,
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
    { dataUrl: 'data:slow.png', name: 'slow.png', size: 3 },
    { dataUrl: 'data:fast.png', name: 'fast.png', size: 2 },
    { dataUrl: 'data:last.png', name: 'last.png', size: 1 },
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

test('移除和发送清理同步释放图片数量与字节账本', () => {
  const selected = [pendingImage('a.png', 3), pendingImage('b.png', 5)];
  const afterRemove = pendingImagesReducer(selected, { index: 0, type: 'remove' });
  const afterSend = pendingImagesReducer(afterRemove, { type: 'clear' });

  assert.deepEqual(afterRemove, [pendingImage('b.png', 5)]);
  assert.equal(pendingImageBytes(afterRemove), 5);
  assert.deepEqual(afterSend, []);
  assert.equal(pendingImageBytes(afterSend), 0);
});
